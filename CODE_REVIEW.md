# NOVEL-AGENT 代码审查报告

> 审查对象：`D:\Github AIwriter\NOVEL-AGENT`（Python 3.14.7 / pydantic 2.13.5 / openai 1.109.1）
> 审查方式：逐文件通读 + 在项目自带 venv 里跑可复现探针（不改动项目文件）+ 用你自己的生产数据与日志交叉验证
> 重点：**角色引擎（novel.character_engine）**
> 结论：角色引擎的核心承诺——"跨章节人格演变" —— **在生产环境里大部分是失效的**，而且失效方式是静默的：不报错、不算失败、照常计费。

---

## 0. 结论速览

### 0.1 角色引擎：不是"有没有 bug"的问题，是"主要功能没在工作"

| # | 严重度 | 一句话 | 位置 |
|---|--------|--------|------|
| **A1** | 🔴 高 | 写后角色分析**静默失败**：JSON 被 `max_tokens` 截断 → 解析失败 → 返回空 → 日志却写"角色分析完成: 0 个角色更新"。**你的生产日志里已经发生了**，并直接导致两个新项目的 `characters.json` 是 `{}` | `character_engine.py:196-204`、`chapter_writer.py:95-102` |
| **A2** | 🔴 高 | LLM 把老角色标成 `is_new=true` 时，**整个角色档案被重建**：人格、关系网、全部逐章事件一次性清空 | `character_engine.py:212-222` |
| **A3** | 🔴 高 | **人格演变只记录不落地**：`personality_shifts` 里但凡出现 `personality` 中没登记过的特质，就被静默丢弃。生产数据里主角有 14 个、反派 15 个、安德森博士 16 个特质是"记录了但从未生效" | `character_engine.py:248-250` |
| **A4** | 🟠 中高 | `relationship_changes` **落盘即丢**（`to_dict` 漏字段、`load` 不读回）。生产数据里 **100%** 的 `chapter_events` 都缺这个键；同时 `load` 用 `ed["mood"]` 硬索引，手工编辑过的存档会让**整个项目打不开** | `character_engine.py:81-89, 301-312` |
| **A5** | 🟠 中高 | 无别名归并，**同一角色反复登记成多个人**。你的项目里 27 个"角色"包含 林雪／林雪（林辰妹妹）／林雪（林辰妹妹的信号源）、扎克／流浪者扎克、零号／零号（第七十五个信号源）等大量同一人 | `character_engine.py:207-212` |
| **A6** | 🟠 中 | **关系强度恒等于 5**（prompt 模板里根本没要 `intensity`，代码却 `rc.get("intensity", 5)`）；`起始章` 每章被覆盖，实际是"最近变化章" | `character_engine.py:253-260` |
| **A7** | 🟠 中 | 写作 prompt 里的角色卡片**丢掉了核心欲望、核心恐惧、道德准则、背景、外貌**——只在角色"零事件"时才输出 | `character_engine.py:95-127` |
| **A8** | 🟠 中 | 重写同一章 → **重复追加章节事件**，上下文里出现两条"第3章" | `character_engine.py:245` |
| **A9** | 🟠 中 | LLM 输出 `null` 时 `old/new` 变成 `None`，**人格值被写成 `None`**，prompt 里出现"勇敢None/10" | `character_engine.py:225-233, 250` |
| **A10** | 🟠 中 | `role` 字段**永远拿不到**（分析 prompt 的 JSON 模板里没有 `role`），自动发现的角色永远是"配角" | `character_engine.py:138-159, 218` |
| **A11** | 🟠 中 | 乱序写章时 `current_chapter` / "最近3章" 取错（`chapter_events[-1]`、`[-3:]` 假设追加顺序=章号顺序） | `character_engine.py:62-72, 106` |
| **A12** | 🟠 中 | 章节正文**静默截断到 6000 字**，无任何告警 | `character_engine.py:185` |
| **A13** | 🟡 低中 | `get_context_for_writing` 把**所有**角色都塞进 prompt，不看出场 | `character_engine.py:266-276` |
| **A14** | 🟠 中 | 角色引擎**零直接测试**：整个 `tests/` 没有任何文件 import `CharacterEngine`/`CharacterProfile` | — |
| **A15** | 🟠 中 | 项目里有**两套互不相通的角色模型**（`models/character.py` 与 `novel/character_engine.py`），语料学到的角色永远进不了小说写作链路 | `src/models/character.py` vs `src/novel/character_engine.py` |
| **A16** | 🟡 低中 | `generate_characters(tier=...)` 的 tier 参数**是死的**：日志说"用 pro 生成"，实际 `design_characters` 里硬编码 flash | `service.py:197-202`、`plot_engine.py:239` |

### 0.2 全项目层面最要紧的三件事

1. **同一套编排被抄了 4 份，护栏只留在 1 份里。**
   `src/novel/service.py` 是"唯一编排层"的设计意图写在文件头注释里，也确实加了护栏（覆盖前备份、批量续写只往后写、空结果报 `ok=False`）。但 `src/cli/novel_commands.py`、`src/tui/app.py`、`src/api/gradio_app.py` 各自**又抄了一遍**，并且**把护栏全丢了**：
   - `novel auto` / Gradio 一键生成用 `range(1, N+1)` 从第 1 章重写已有正文（service 里明确写着这是它要修掉的 bug，注释就在 `service.py:310-312`）；
   - CLI 生成角色**不备份** `characters.json`（service 会备份）；
   - 空的 LLM 返回在 CLI 里被打印成绿色 `第N章写作完成（0 字）并已保存` 且 `exit 0`。
   **这是当前最大的一类数据损失来源。**

2. **"静默失败 → 假成功"是全局文化，不只是角色引擎。**
   引擎层普遍 `except Exception: return 空结果`，上层无法区分"模型确实没产出"和"基础设施挂了"，于是：
   - 角色分析失败 → "角色分析完成: 0 个角色更新"（A1）；
   - 大纲/剧情解析失败 → 空大纲、空剧情，但 CLI/Gradio 报成功；
   - 写作引擎全章返回空 → `写作完成: xxx (0 字)`，`orchestrator.write()` 正常返回空文章；
   - 审稿 JSON 解析失败 → `score=5.0, issues=[]`，与"干净的好文章"完全无法区分；
   - Level-1 自动修改匹配不到片段 → 报告里照样打 ✅ 并计入"自动修改 N 项"。
   钱都花了，结果没人知道。

3. **持久化层有一组会静默吃掉数据的坑。**
   - `chunk_id = f"{stem}_{index}"` 用**文件名**做全局主键，两个同名文件互相覆盖（你自己的 `index.csv` 里就有两个 `CSGO：我的准星里无活物-hold载物.txt`，各 1.8 万段，实际只入库了一份）；
   - `characters.json` / `project.json` / 检查点文件都是**非原子写**（`open(w)` + `json.dump`）。写到一半被打断 → 下次 `NovelService.load()` 直接抛 `JSONDecodeError`，**项目完全打不开**（已复现）。`CharacterEngine.save` 在**每写一章**都会调用；
   - `outline` 的章号**没有 int 归一化**（`chapters`/`chapter_titles` 有），模型返回 `"chapter": "3"` 会让 `list_chapters()` 的 `sorted(int + str)` 抛 `TypeError`，TUI 章节页签和 `novel show` 一起挂。

---

## 1. 角色引擎：逐条详解（含证据）

### 数据流：断点在哪里

```
写一章
  └─ game_engine.analyze_chapter(chapter_num, chapter_text[:6000], existing_names)
        ├─ LLM(flash, temp=0.3, max_tokens=4096, 无 response_format)   ← ③ 无 JSON 模式/无重试
        ├─ _parse_analysis(response)
        │     ├─ safe_json_parse → 截断/带前后文 → None → return []     ← ① A1 静默失败
        │     ├─ is_new=true → 新建 CharacterProfile 覆盖旧对象          ← ② A2 清空历史
        │     ├─ shifts：trait 不在 personality 里 → 只记录不应用        ← ④ A3
        │     └─ relationships：强度恒 5、起始章被覆盖                  ← ⑤ A6
        └─ engine.save(characters.json)   ← ⑥ A4 relationship_changes 丢失 / 非原子写
              ↓
写下一章时 get_context_for_writing() → get_status_for_chapter()
        └─ 有事件时：不输出 core_desire/core_fear/moral_compass/background/appearance  ← ⑦ A7
```

### A1 🔴 角色分析静默失败：生产日志已证实（最严重的一条）

**代码链**

```python
# character_engine.py:189-198
try:
    response = self.llm.chat([...], model_tier="flash", temperature=0.3)
    return self._parse_analysis(response, chapter_num)
except Exception as e:
    logger.warning(f"角色分析失败: {e}")
    return []                       # ← 失败与"没有变化"返回同一个值

# character_engine.py:200-204
data = safe_json_parse(response)
if not data:
    return []                       # ← 截断的 JSON 也是这个分支，无日志、无重试

# chapter_writer.py:95-102
try:
    updated = self.engine.analyze_chapter(chapter_num, chapter_text, existing_names)
    logger.info(f"角色分析完成: {len(updated)} 个角色更新")   # ← 0 个也报"完成"
except Exception as e:
    logger.warning(f"角色分析跳过: {e}")                     # ← 然后照样 engine.save()
```

**生产证据 1 —— 日志**：`logs/writing_expert_2026-09-22.log`

```
10:42:12 | 写作第 1 章
10:42:27 | LLM 调用: [FLASH] 2589in + 2335out tokens | ¥0.00737   ← 正文
10:42:51 | LLM 调用: [FLASH] 2289in + 4096out tokens | ¥0.01064   ← 角色分析
10:42:51 | 角色分析完成: 0 个角色更新
```

输出 tokens **正好等于 4096**，也就是 `config.yaml` 里 flash 的 `max_tokens`——**响应被硬截断**，JSON 不闭合，`safe_json_parse` 返回 `None`，于是"0 个角色更新"。这一次调用仍然计费 ¥0.0106。

**生产证据 2 —— 数据**：

```
data/projects/雄鱼好的恋爱日记/characters.json              2 字节  → "{}"
data/projects/重生！在ai出现之前的程序员/characters.json     2 字节  → "{}"
```

这两个项目的 `project.json` 与 `characters.json` 的 mtime 只差 0.5 毫秒，说明是**同一次 `write_chapter` 里写下的**：正文写成功了，角色分析产出为空，于是把空字典落盘。因为这两个项目是"直接开写、没先生成角色"，第一次分析时"已有角色"为空，模型必须为每个出场角色输出完整人设 → 输出量最大 → 必然撞 `max_tokens` → 永远为空。**之后每一章都会重复这次注定失败的付费调用。**

**为什么解析这么脆（跨模块的根因，值得单独记一笔）**

- `json_utils.extract_json()` 的文档字符串写着"前后有解释文字时也尝试提取"，但实现只有 `text = text.strip(); return text`，**没有实现**。实测 `safe_json_parse('好的，以下是分析结果：\n{"a":1}\n希望有帮助')` → `None`。
- `find_json_in_text()`（本可以补救带前后文的输出）**没有被任何写作链路调用**；而且它自己的括号匹配不识别字符串里的括号，`find_json_in_text('{"s": "}"}')` → `None`。
- 截断修复只存在于 `review_engine/base_agent.py:62-73`，且**闭合顺序写反**（先补 `]` 再补 `}`，多层嵌套时仍然非法）。角色引擎连这个都没用上。
- `requirements.txt` 声明了 `instructor>=1.0.0`（HANDOVER 也写明"结构化输出控制用 Instructor"），但**全项目零处使用**，也没有用 `response_format={"type":"json_object"}`。

**建议修复（按性价比排序）**

```python
# 1) 立刻止血：给分析调用单独的、足够的输出预算 + JSON 模式
response = self.llm.chat(messages, model_tier="flash", temperature=0.3,
                         max_tokens=8192,
                         response_format={"type": "json_object"})   # 需要 llm_client.chat 透传该参数

# 2) 解析失败必须"可区分"——不要再返回 []
@dataclass
class AnalysisOutcome:
    profiles: list[CharacterProfile]
    ok: bool                      # False = 本次分析没有成功，调用方可重试/告警/记费
    error: str = ""

# 3) 解析器加一层修复（截断时按栈顺序补闭合括号），并复用 find_json_in_text
data = safe_json_parse(response) or find_json_in_text(response)
if not data:
    logger.warning(f"第{chapter_num}章角色分析 JSON 解析失败（{len(response)} 字，可能被截断）")
    return AnalysisOutcome([], ok=False, error="json_parse_failed")

# 4) chapter_writer 不要吞掉，明确上报
outcome = self.engine.analyze_chapter(...)
if not outcome.ok:
    logger.warning(f"第{chapter_num}章角色状态未更新（角色连续性可能断裂）")
```

再补一条：**首次分析不要要求"完整人设"**。要么先跑 `generate_characters`（prompt 里加一句"已有角色为空时仍未识别出的角色也要输出"，并把 `max_tokens` 提到 8192），要么改为每章只分析前 N 个主要角色。

---

### A2 🔴 `is_new=true` 会重建角色档案、清空历史

```python
# character_engine.py:212-222
if char_data.get("is_new") or name not in self._characters:
    profile = CharacterProfile(                # ← 直接 new 一个
        name=name,
        personality=char_data.get("personality", {}),   # 老角色这里通常是 None/{}（prompt 说"仅新角色需要"）
        speaking_style=char_data.get("speaking_style", ""),
        role=char_data.get("role", "配角"),
    )
    self._characters[name] = profile           # ← 旧对象连同 chapter_events/relationships 一起丢掉
```

**复现（已跑通）**

```
分析前: role=主角       人格={'勇敢': 9}   关系=['苏婉']   事件=[(1, '开场：救下苏婉')]
分析后: role=配角       人格={'勇敢': 3}   关系=[]          事件=[(2, '被击溃')]
```

LLM 在长篇小说里把回归角色标成"新出场"是**常见**行为（别名、称号、隔了很多章再出现），代价却是丢掉全部连续性数据。而 `is_new` 是模型可以随便写的布尔值，不该拥有"清空档案"的权限。

**建议修复**：`is_new` 只作为补全提示，永不允许覆盖已有对象。

```python
existing = self._characters.get(name)
if existing is None:
    existing = CharacterProfile(name=name, ...)
    self._characters[name] = existing
    if not existing.personality:                       # 只有真·新角色才吃 personality 字段
        existing.personality = _clean_personality(char_data.get("personality"))
else:
    # 已有角色：只允许"补空"，不允许覆盖非空字段
    for k, v in (char_data.get("personality") or {}).items():
        existing.personality.setdefault(k, v)
    if char_data.get("speaking_style") and not existing.speaking_style:
        existing.speaking_style = char_data["speaking_style"]
```

---

### A3 🔴 人格演变"只记录、不落地"

```python
# character_engine.py:247-250
for shift in shifts:
    if shift.trait in profile.personality:          # ← 新特质直接被丢弃
        profile.personality[shift.trait] = shift.new_value
```

事件里如实记下了"谨慎 2→7"，但人格字典里没有"谨慎"这个键，于是**演变不会发生**。后果：
- 只有初始生成时那 5 个维度（勇敢/善良/冲动/智慧/忠诚）会变；
- 模型报告的"人物成长"绝大部分被扔掉。

**你的真实数据统计**（对 `data/projects/*/characters.json` 全量扫描）：

| 角色 | 记录了但从未生效的特质 |
|------|------------------------|
| 林辰（主角） | 14 个：信任、决心、反抗、反抗意识、同理心、坚定、坚韧、悲悯、成熟度、洞察、洞察力、理解力、谨慎、适应力 |
| 卡尔·霍克（反派） | 15 个：冷漠、城府、多疑、存在确定感、情感表达、掌控欲、控制欲、服从性、果断、沉重负担感、温柔/脆弱、理性掌控感、真诚、被动性、计划性 |
| 安德森博士 | 16 个：内疚感、冷漠/学术超然、固执/偏执、坚持伦理、坚韧、情感投入、情绪稳定性、控制欲、正直、理性、理性客观、目的导向、脆弱、自我宽恕、诚实、隐瞒倾向 |

注意 `洞察` 与 `洞察力`、`反抗` 与 `反抗意识`、`冷漠` 与 `冷漠/学术超然` 同时存在——**没有特质词表归一化**，所以即便修好 A3，人格字典也会被近义键撑成一团。建议引入一份受控特质表（如 20-30 个维度）+ 同义词映射，模型只允许从表里选。

**建议修复**

```python
TRAIT_ALIASES = {"洞察力": "洞察", "反抗意识": "反抗", "信任倾向": "信任", ...}

for shift in shifts:
    trait = TRAIT_ALIASES.get(shift.trait, shift.trait)
    if not trait:
        continue
    applied = _clamp(shift.new_value)             # 同时修 A9/H：夹到 0-10
    old = profile.personality.get(trait)
    if old is None:
        profile.personality[trait] = applied      # 允许新维度生长
        logger.info(f"{name} 新增人格维度: {trait}={applied}（{shift.reason}）")
    else:
        profile.personality[trait] = applied
```

顺带：`shift.new_value` 从不夹紧，实测能写进 `{'愤怒': 14, '理智': -3}`，prompt 里就出现 `愤怒14/10, 理智-3/10`。同样来自 LLM 的 `old/new` 为 `null` 时（`s.get("old", 5)` 在键存在但值为 `null` 时返回 `None`）人格值会被写成 `None`，prompt 变成 `勇敢None/10`（A9，已复现）。请统一走一个 `_to_int_0_10(value, default)`。

---

### A4 🟠 中高 `relationship_changes` 落盘即丢 + `load` 硬索引会让项目打不开

```python
# character_engine.py:81-89  to_dict —— 逐章事件里漏了 relationship_changes
"chapter_events": [
    {"chapter": e.chapter, "mood": e.mood, "key_actions": e.key_actions,
     "personality_shifts": [...],
     "skills_gained": e.skills_gained, "belief_changes": e.belief_changes,
     "summary": e.summary}
    for e in self.chapter_events
],

# character_engine.py:301-312  load —— 也没读回
shifts = [PersonalityShift(trait=s["trait"], old_value=s["old"],
                           new_value=s["new"], reason=s["reason"]) ...]   # 硬索引
event = ChapterEvent(chapter=ed["chapter"], mood=ed["mood"], ...)         # 硬索引
```

**证据 1（字段丢失，生产 100% 命中）**：全量扫描真实存档，每个角色的 `chapter_events` **每一条**都缺 `relationship_changes`：

```
林辰       37/37 条缺失      卡尔·霍克 25/25 条缺失
安德森博士  22/22 条缺失      六十个胎儿 12/12 条缺失   ...
```

也就是说"关系是怎么一章一章变坏的"这段历史**从来没被保存过**。虽然全局 `relationships` 里存了最终状态，但演变过程、`reason`、`old` 全丢了——而这正是"长篇连续性"最值钱的部分，也是 `scripts/rebuild_outline.py` 想复用的东西。

**证据 2（硬索引 → 项目打不开）**：手工编辑过、或由早期版本写出的 `characters.json`（缺 `mood` 或 `reason`）会让 `load` 抛 `KeyError`：

```
A) characters.json 里 chapter_events 少了 mood 键 → load 抛异常: KeyError: 'mood'
A2) personality_shifts 里少了 reason 键        → load 抛异常: KeyError: 'reason'
```

而 `NovelService.load()` 没有 try/except，于是 **TUI / CLI / Gradio 三处都打不开这个项目**，用户看到的是一个无从下手的报错。

**证据 3（非原子写 → 项目打不开）**：`save` 是 `open(path,"w")` 后 `json.dump`。我模拟了"写一半被打断"的存档：

```
load 失败 → JSONDecodeError Unterminated string starting at: line 1 column 23
```

而 `CharacterEngine.save()` 在 `chapter_writer.write_chapter()` 里**每写一章都会执行一次**，TUI 里 Ctrl-C、进程被杀、磁盘满，都可能留下半截文件。

**建议修复**

```python
# 1) 序列化对称：to_dict/from_dict 成对写，字段用 .get(..., 默认值) 读
"relationship_changes": e.relationship_changes,          # to_dict 补上
relationship_changes=ed.get("relationship_changes", []), # load 读回
chapter=ed.get("chapter", 0), mood=ed.get("mood", ""),   # 全部改成 .get
"s": sh = {"trait": s.get("trait",""), "old": s.get("old"), ...}

# 2) 原子写 + 备份（顺手解决"半截文件砖化项目"）
def save(self, path: str):
    tmp = Path(path).with_suffix(".json.tmp")
    tmp.write_text(json.dumps({n: p.to_dict() for n, p in self._characters.items()},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)        # 同目录 rename，原子

# 3) load 失败不要炸掉整个项目
try:
    engine.load(char_file)
except Exception as e:
    logger.warning(f"characters.json 损坏（{e}），已跳过角色引擎；原文件保留为 .corrupt")
    shutil.copy2(char_file, char_file.with_suffix(".json.corrupt"))
```

---

### A5 🟠 中高 无别名归并：同一角色被登记成多个人

`_parse_analysis` 用**精确名字**做字典键，`aliases` 字段（甚至模型侧根本没有这个字段）从不参与匹配。生产数据里同一个实体裂成多份：

| 真实项目 | 同一实体的多个条目 |
|---|---|
| 地球毁灭人类开始银河旅行纪元… | 林雪 / 林雪（林辰妹妹）/ 林雪（林辰妹妹的信号源） |
| 同上 | 父亲(神秘人) / 父亲（神秘人） |
| 同上 | 扎克 / 流浪者扎克 |
| 同上 | 第七十七个 / 七十七号 / 第七十七个（信号源） |
| 同上 | 七十三号（白发男人）/ 第七十三号节点 |
| 同上 | 零号 / 零号（第七十五个信号源） |
| 同上 | 艾莉亚 vs 艾莉亚·诺瓦（林辰的关系表里写的是"艾莉亚"→ 悬空引用） |
| 重生校花 | 班主任王建国 / 王建国；刘洋 / 刘阳（两个名字，很可能是同一人被模型写错） |

后果有三重：
1. 写第 N 章时 prompt 里塞进同一人的 3 张互相矛盾的角色卡，模型只能猜；
2. 角色卡数量虚高（该项目 27 个"角色"），吃光 prompt 预算；
3. 关系网指向不存在的名字（悬空边），"关系演变"实际断链。

**建议修复**：入库前做一次归并——名字归一化（去括号后缀、去"流浪者/神秘的"之类修饰）+ 别名匹配 + `difflib`/向量相似度阈值合并；把 `aliases` 真的用起来，并在 prompt 里给出"已有角色（含别名）"。

---

### A6 🟠 中 关系强度恒为 5、`起始章` 被每章覆盖

```python
# character_engine.py:152-153  prompt 模板里的 relationship_changes 只有 4 个键
"relationship_changes": [{"target": "李四", "old": "友好", "new": "怀疑", "reason": "..."}],

# character_engine.py:253-260  代码却去读 intensity
profile.relationships[target] = {
    "状态": rc.get("new", rc.get("status", "")),
    "强度": rc.get("intensity", 5),      # ← prompt 从没要过 intensity → 永远是 5
    "起始章": chapter_num,               # ← 每章覆盖 → 实际是"最近变化章"
}
```

**生产证据**：所有由逐章分析写出的关系，`强度` 一律是 `5`；林辰的关系表里 `起始章` 取值是 `{3, 20, 31, 32, 33, ..., 50}`（散落各章，而不是各关系的*首次*出现章）。`old` 和 `reason` 也被直接丢弃。

（附带一个跨模块同源问题：`design_characters` 的 prompt 示例里写了 `"强度": 5`，模型照抄，所以**初始生成**的关系强度也几乎全是 5。prompt 里的示例值会污染数据，这不是第一次——见 A3 的"19/39 个角色共享同一组 5 个维度"。）

**建议修复**：prompt 模板与解析字段对齐（要么加 `intensity`，要么删掉读取）；`起始章` 用 `setdefault` 只在首次写入；把 `old`/`reason` 存进关系历史。

---

### A7 🟠 中 写作用角色卡片丢掉了最关键的一致性锚点

```python
# character_engine.py:95-127
def get_status_for_chapter(self, chapter: int) -> str:
    if not self.chapter_events:
        return f"【{self.name}】{self.role}。{self.personality_summary()}。{self.speaking_style}"
    parts = [f"【{self.name}】{self.role}"]
    parts.append(f"核心人格: {self.personality_summary()}")
    if self.speaking_style: parts.append(f"说话风格: {self.speaking_style}")
    ... 最近事件 / 关系 ...
    # ← core_desire / core_fear / moral_compass / background / appearance 一个都没输出
```

**复现（已跑通）**：一个有章节事件的角色，其卡片里

```
上下文里包含 core_desire?     False
上下文里包含 core_fear?       False
上下文里包含 background?      False
上下文里包含 appearance?      False
上下文里包含 moral_compass?   False
```

也就是说：**只要角色出场过一次，模型就再也看不到这个角色"想要什么、怕什么、底线在哪"**。而 `service.generate_characters` 明明花了钱生成 `core_desire`/`core_fear`（`CHARACTER_SYSTEM_PROMPT` 里明确要求），存进了 `characters.json`，然后在写作时被静默丢弃。这是"角色行为前后不一致"最直接的代码原因。

**建议修复**：把这几项无条件拼进卡片（它们本来就该是每次都要给的），并对"本章未出场"的角色做过滤（顺带 A13）。

---

### A8 🟠 中 重写同一章 → 重复事件

```python
profile.chapter_events.append(event)        # character_engine.py:245，无去重
```

**复现**：第 3 章写两遍后

```
第3章的事件条数: 2
全部事件: [(3, '第一版'), (3, '第一版')]
写第4章时的'最近3章'上下文:
      第3章: 无关键行动（情绪: 紧张）
      第3章: 无关键行动（情绪: 紧张）
```

**生产证据**：`怀里的女孩是黑帮千金` 里，林逸和苏晚晴都有**重复的第 2 章事件**。

注意 `src/models/character.py:79-86` 的 `add_chapter_state` 是**有**去重逻辑的（同章替换），说明这个坑在另一套模型里已经被踩过并修过，只是 `CharacterProfile` 没同步。

**建议修复**：把 A8 和 A11 一起解决——`chapter_events` 始终按章号排序，写入时同章替换：

```python
def upsert_event(self, event: ChapterEvent):
    for i, e in enumerate(self.chapter_events):
        if e.chapter == event.chapter:
            self.chapter_events[i] = event
            break
    else:
        self.chapter_events.append(event)
    self.chapter_events.sort(key=lambda e: e.chapter)
```

---

### A9 🟠 中 `null` 会把人格值写成 `None`

`s.get("old", 5)` 在"键存在但值为 `null`"时返回 `None`（不是 5）。实测：

```
shift: ('勇敢', None, None)  类型: NoneType
人格被写成: {'勇敢': None}
personality_summary() -> '勇敢None/10, 善良7/10'      ← 直接进 prompt
```

**修复**：统一 `_to_int_0_10(value, default)`，对 `None`/字符串/越界值一律兜底并夹紧。

---

### A10 🟠 中 `role` 永远拿不到

分析用的 JSON 模板（`character_engine.py:142-159`）里**没有 `role` 键**，但代码写 `char_data.get("role", "配角")`：

```
分析 prompt 的 JSON 模板包含 'role' 键吗: False
LLM 没给 role 时，新角色 role = '配角'
```

结果：所有**自动发现**的角色都是"配角"，主角/反派信息只在`generate_characters`那一次生成里有；而且一旦触发 A2，连主角的 `role` 都会被重置成"配角"。

**修复**：模板里加 `"role": "主角/反派/配角/路人"`，并在已有角色分支里只补空不覆盖。

---

### A11 🟠 中 乱序写章时状态取错

`current_chapter`/`current_mood` 取 `chapter_events[-1]`，"最近 3 章"取 `[...][-3:]`，都假设追加顺序 == 章号顺序。实测写入顺序 `5, 2, 9, 3`：

```
current_chapter = 3      （期望 9）
current_mood    = m3     （期望 m9）
写第6章时的'最近3章'取到的是: [5, 2, 3]   （期望 3,5,9 这类有序结果）
```

TUI 的角色表格直接显示 `current_mood`（`app.py:341`），所以用户看到的情绪也可能是错的。**修复**：A8 的 `sort(key=chapter)` 一并解决，并把 `recent` 改成显式排序后取最后 3 条。

---

### A12 🟠 中 章节正文静默截断

```python
f"章节内容:\n{chapter_text[:6000]}\n\n"
```

实测传入 20000 字，**只有 6000 字**进入 prompt，且无任何日志。默认目标 2500 字的中文正文约 2500-4000 字，勉强够；但 pro 档一章写到 8000 字以上时，分析只看得到前半章——**后半章发生的人物变化全部丢失**。这正是 A1 的另一面：输入太长会让模型输出更长，更容易撞 `max_tokens`。

**修复**：超出时按段落切分多次分析并合并（或至少 `logger.warning` 明确告知截断，并记录截断比例）。

---

### A13 🟡 低中 角色上下文不做筛选

`get_context_for_writing` 无脑输出全部角色。实测 30 个配角（第 5 章一个都没出场）→ 上下文 467 字全塞进去。50 章、27 个角色时，每章 prompt 都要背着一大堆无关角色卡，既费钱又稀释注意力。

**修复**：优先用 `plot.character_appearances`（剧情设计里已经产出了"本章出场角色"），没有就回退到"最近 3 章出场过的角色 + 全部主角/反派"。

---

### A14 🟠 中 角色引擎零测试

```
tests/ 下没有任何文件 import CharacterEngine / CharacterProfile / PersonalityShift / ChapterEvent
tests/test_character_engine.py 不存在
```

`to_dict`/`load` 往返、`_parse_analysis`、`get_status_for_chapter`、`add_character` 全部**没有一行测试**。这直接解释了为什么 A2/A3/A4 能在生产跑出这么明显的数据损坏却无人发现：项目有 193 个测试（我实跑：**151 passed / 42 因沙箱禁止写系统临时目录而报 PermissionError**，非逻辑失败），`test_plot_engine.py` 都为剧情引擎写了测试，唯独角色引擎没有。

另外 `test_plot_engine.py` 的多数用例**把生产逻辑抄进测试里再断言**（例如 `test_world_building_is_string` 自己写一遍 `if isinstance(wb, str): wb = {}` 然后断言 `wb == {}`），并没有调用 `design_characters`，所以它测试的是测试自己，不是产品代码。

---

### A15 🟠 中 两套互不相通的角色模型

| | `src/models/character.py` | `src/novel/character_engine.py` |
|---|---|---|
| 类型 | pydantic `Character` / `ChapterState` / `RelationshipState` / `DialogueStyle` | dataclass `CharacterProfile` / `ChapterEvent` / `PersonalityShift` |
| 谁在用 | 只被 `analysis/character_analyzer.py` 用，而后者又只被 `scripts/extract_characters.py` 用 | TUI / CLI / Gradio / 写作链路全用它 |
| 核心字段 | `aliases`、`base_profile`、`dialogue_style`、`relationship_details.history`、`arc_summary` | `personality`（0-10 数值）、`speaking_style`、`core_desire/core_fear`、`relationships` |

**两者之间没有任何转换函数。** 结果：板块一从 60GB 语料里辛苦提取的角色档案（含别名、对话风格、关系史）**永远进不了小说写作链路**；`aliases`（本该解决 A5）、`dialogue_style`、`relationship_details.history`（本该解决 A4）在一个模型里被精心声明、在另一个模型里完全不存在。

顺带一个已经生效的 bug：`character_analyzer.py:64-68` 让模型输出 `{"句式特征", "口头禅", "语气倾向"}`，而 `DialogueStyle` 的字段是 `sentence_pattern/catchphrases/tone_tendency`，于是

```python
DialogueStyle(句式特征="短句多", 口头禅=["哼"], 语气倾向="冷淡")
# → 全部是默认空值，且不报错（pydantic 默认 extra='ignore'）
```

**每一个提取出来的角色都丢掉了声音特征。**

**建议**：二选一——把 `CharacterProfile` 作为唯一模型，让 `analysis` 层输出它；或写一个显式的 `CharacterProfile ⇄ Character` 转换器并加往返测试。同时把 prompt 的字段名和模型字段名对齐（或给 `DialogueStyle` 加 `Field(alias=...)` + `populate_by_name=True`）。

---

### A16 🟡 低中 `tier` 参数是死的，而且日志在说谎

```python
# service.py:197-202
self.log(f"[角色] 用 {tier} 生成角色系统…")          # 说了用 tier
chars, _world = plot.design_characters(               # 但 tier 没传进去
    project.title, project.genre, project.description,
    project.get_outline_context(),
)

# plot_engine.py:221-224 / 239 —— 签名里根本没有 tier，且硬编码 flash
def design_characters(self, novel_title, genre, description, outline_text):
    response = self.llm.chat([...], model_tier="flash", temperature=0.5)
```

CLI（`novel_commands.py:249`）和 TUI（`app.py:469-471`）也都在显示 tier 之后把它丢掉；Gradio 干脆连选项都没有。**用户永远无法用 pro 生成角色系统**，而界面告诉他用了。

同一处还有剧情：`design_chapter_plot` 也硬编码 `model_tier="flash"`（`plot_engine.py:187`），`--tier` 在剧情设计上同样无效。

---

## 2. 其它模块的问题（按主题归纳，均带定位）

### 2.1 编排重复 → 护栏失效（数据损失类，最高优先）

| 现象 | 位置 |
|---|---|
| `novel auto` 与 Gradio 一键生成 `for ch in range(1, N+1)` **重写已有正文**（service 明确拒绝这种写法，注释就在旁边） | `cli/novel_commands.py:373,390`、`api/gradio_app.py:720` vs `novel/service.py:310-320` |
| CLI 生成角色**不备份** `characters.json`、不检查空结果 → `角色已保存 characters.json（0 个）` exit 0 | `cli/novel_commands.py:206-256` vs `service.py:190-206`（还会用私有成员 `engine._characters:233`） |
| Gradio 新建项目**不检查重名** → 把已有小说覆盖成空项目，并显示"已创建" | `api/gradio_app.py:462-475` vs `service.py:111-115` |
| Gradio 全局内存态永不从磁盘重载 → 在 CLI 写完第 5 章后点"保存全部"，**第 5 章从磁盘消失** | `api/gradio_app.py:410-413,539,575-586` vs `service.py` 每次操作都重新 `load()` |
| Gradio 生成角色**无备份**、空结果也报成功 | `api/gradio_app.py:626,715-717` |
| Gradio 保存大纲会把**所有 `key_foreshadowing` 清空**（正则解析不回缩进的"伏笔:"行） | `api/gradio_app.py:528-536` vs `:511-512` |
| Gradio "保存剧情修改"存的 `user_notes` **没有任何代码读取**（`to_prompt_text()` 不输出它）→ 用户以为改了，写作时没用上 | `api/gradio_app.py:548-561`、`plot_engine.py:62-91`，`service.py:254-261` 同样有此缺口 |
| Gradio 角色编辑**只能加不能删**（删掉条目再保存，引擎里还在），且未加载项目时 `_novel_project.base_dir` 触发 `AttributeError` | `api/gradio_app.py:794-815` |
| `--tier` 在 CLI/TUI 显示但被忽略（角色、剧情两处） | `cli/novel_commands.py:249,283`、`tui/app.py:492-497`、`plot_engine.py:187,239` |

### 2.2 静默失败 / 假成功（花费与认知类）

| 现象 | 位置 |
|---|---|
| 章节返回空文本 → CLI 打印绿色 `第N章写作完成（0 字）并已保存`，`exit 0`，`novel auto` 继续烧钱 | `cli/novel_commands.py:336-342,389-395`（service 有正确护栏） |
| 写作引擎全章为空 → `write()` 正常返回空文章并 log `写作完成 (0 字)` | `writing_engine/orchestrator.py:74-91`、`writer_agent.py:57-62` |
| 大纲生成失败被忽略 → 无大纲仍逐章付费调用 | `cli/novel_commands.py:358-363,373-390` |
| 审稿 JSON 解析失败/空响应 → `score=5.0, issues=[]`，与"干净的好文章"无法区分 | `review_engine/base_agent.py:148-163` |
| 6 个审稿 Agent 全失败 → 界面显示"无/无/无"，并把**原文章当成修复后文章**返回 | `review_engine/base_agent.py:117-133`、`api/gradio_app.py:366-378,395-405` |
| Level-1 自动修改匹配不到就跳过，报告里**照样打 ✅ 并计入"自动修改 N 项"**；删除类修改（`after_text=""`）被真值判断静默跳过 | `review_engine/fixer.py:62-71,78,103-110` |
| `_save_knowledge_units` 用一个**没初始化 schema 的新连接**写库，异常只记 `DEBUG` → 全新安装可以跑完 5000 篇 Pro 分析、**零知识单元入库、报表 100% 成功** | `analysis/ingestion.py:162-190`（`batch_analyze_flash.py:20` 日志级别 WARNING，消息不可见） |
| 整个第二层 Flash 轻量分析结果被丢弃（`_save_lightweight_metadata` 是 `pass`，但 `stats["lightweight"]=True` 且 CLI 显示"完成"） | `analysis/ingestion.py:79,146-150` |
| 逐层分析失败 → 返回一份"全默认值"的合法 `DeepAnalysis`，该文件被标记 OK 且永不重试 | `analysis/deep.py:49-62` |
| `--report` 只在同时给了 `--out` 时才写 | `cli/article_commands.py:93-102` |
| `index.csv` 的 `char_count` 永远是 0（`process_single_file` 不返回该键），且失败文件也会被写进索引 | `api/gradio_app.py:122-123,140-147`、`cli/kb_commands.py:86`、`analysis/ingestion.py:63-64` |

### 2.3 成本与预算

| 现象 | 位置 |
|---|---|
| `add_record` 只在"成功且 `usage` 非空"时执行：失败/超时/重试不可见；**若服务端返回 `usage=None`，预算闸门永久失效**（`assert_budget` 永不触发） | `utils/llm_client.py:290-305` |
| `finish_reason` 被丢弃 → `length` 截断（就是 A1 的成因）完全不可见 | 同上 |
| 任何章节的 `max_tokens` 都**不按目标字数推算**，也不检查截断并续写 | `writing_engine/writer_agent.py:50-62`、`config.yaml:14,24` |
| 预算检查只在调用前做一次，6 个并行审稿 Agent 可同时穿过闸门 → 超支可达单次费用的数倍 | `llm_client.py:224-229`、`review_engine/orchestrator.py:123-141` |
| 用量库并发丢行（6 线程审稿 → 6 条用量只落 1 行），且只记 `DEBUG` | `cost_tracker.py:129-155`（连接未设 `check_same_thread=False`） |
| Gradio 模型选择器**不传参**，默认走 pro，界面却显示"模型: V4 Flash" | `api/gradio_app.py:342-359`（`writing_engine/orchestrator.py:35` 默认 `"pro"`） |
| Gradio 一键生成是一键无上限的 `2+2N` 次付费调用，无预估、无确认（`auto_chs` 无最大值；`budget.max_cny_per_session` 默认 0=关闭） | `api/gradio_app.py:695-741,963-970` |
| RPM 限流每实例一份 + 重试绕过限流：GUI 同时构造写作与审稿两个 orchestrator，`pro` 配的 50 RPM 实际可到 100 | `llm_client.py:146-170,229` |
| `update_tier_config` 用默认值（`max_tokens=4096`）覆盖 tier 配置（pro 是 8192），当前无人调用但是个陷阱，且 `tests/test_llm_client.py:35` 把 4096 固化了 | `llm_client.py:334-344` |

### 2.4 数据损坏、并发与规模

| 现象 | 位置 |
|---|---|
| `chunk_id` 用文件**主干名**做全局主键 → 同名文件互相覆盖、整份内容丢失（你的 `index.csv` 里已有两个同名 `CSGO…txt`，各 1.8 万段，只入库一份；`_save_chunks` 只计数不告警；`kb delete` 报成功却没删到东西） | `preprocessing/pipeline.py:57`、`analysis/ingestion.py:133-138`、`scripts/batch_preprocess.py:78` |
| 同上根因也污染角色/知识单元 id：`character_analyzer.py:150,189`、`deep.py:218` | — |
| `outline` 章号**不做 int 归一化**（`chapters`/`chapter_titles` 做了）→ 模型给 `"chapter": "3"` 会让 `list_chapters()` 的 `sorted(int+str)` 抛 `TypeError`（TUI 章节页签 + `novel show` 一起挂），且所有 `o.chapter == chapter` 查找失效 | `project_manager.py:186-191` vs `:178-183`、`chapter_writer.py:190` |
| `project.json`/`characters.json`/检查点全部非原子写；检查点在 600 万规模下是 ~700MB JSON 反复全量重写（O(n²) I/O），崩一次全部重跑 | `project_manager.py:162`、`character_engine.py:280`、`scripts/batch_preprocess.py:39-42,105`、`batch_analyze_flash.py:151-156` |
| `chunks` 的索引与实际查询不匹配：`idx_chunks_group` 以 `source_type` 打头而查询按 `source_file` 过滤 → `EXPLAIN` 实测全表扫描 + 临时 B 树排序（61GB 库上每次检索都扫全表） | `knowledge_base/schema.py:130-134`、`knowledge_bridge.py:100-105` |
| 检索层实际上"永远返回空"：ChromaDB 不可用时 `index_chunks` 提前 `return`，BM25 索引再也不建；`_fallback_embed` 返回 768 维零向量而 bge-m3 是 1024 维；索引时把**整个语料**物化进内存（`batch_size = 100` 是个装饰）；而且 `Retriever`/`index_chunks` **没有任何生产调用方**（真检索是 `LIKE '%kw%'`），HANDOVER 里写的"混合检索 + RRF + 每篇最多 2 块的多样性采样"在代码里不存在 | `knowledge_base/retriever.py:57-58,136-147,164,196-197` |
| `RetrievalResult.chunk_id` 默认空串，RRF 用它做合并键 → 4 条结果合并成 1 条 | `retriever.py:13,35-43` |
| SQLite 连接跨线程复用（Gradio 工作线程、成本库、知识库三处），未设 `check_same_thread=False` → 间歇性 `ProgrammingError` | `schema.py:148`、`cost_tracker.py:129`、`knowledge_bridge.py:20-30` |
| 语料清洗：`noise_patterns` 定义了却**从未被 `is_noise` 使用**（只判断 `len < 10`）→ 实测丢掉 5.7% 真实对话（`"主播怎么了？"`），同时把 `'------------'` 这种页分隔线留成 **chunk #0 送给 Pro 模型**；`chunk_size`/`chunk_overlap`/`min_chunk_chars` 全部读而不用（实测 49.5% 的块不足 50 字，单换行文件会变成**一个 14 万字的块**）；`chapter_path` 永远是空串 | `preprocessing/pipeline.py:26-31,48-52,82`、`config.yaml:36` |
| "深度分析全文"实际只看了 **0.058%** 的文档（`chunks[:20]` 拼接）：实测 99.3 万字 → 只送 580 字，且开头两行是 `'------------'`；HANDOVER 声称采样 5000-8000 tokens | `analysis/ingestion.py:85`、`scripts/batch_analyze_flash.py:52` |
| 分析失败的 `ok` 标志被丢弃 → 失败文件永久记为"已完成"，永不重试 | `scripts/batch_preprocess.py:95-99` |
| `Chunk.source_metadata`/`chapter_path` 从不入库，行→模型往返静默丢字段（pydantic `extra='ignore'`） | `models/chunk.py:22-23` vs `ingestion.py:133-137` |
| 9 张表里 6 张（`style_templates`/`writing_requests`/`outlines`/`articles`/`review_reports`/`file_index`）**没有任何写入方**；`style_templates.representative_samples` 连列都没有；`knowledge_units.embedding` 从不写 | `knowledge_base/schema.py:45-127` |
| 模型用 `datetime.now()`（本地朴素时间），DB 默认 `datetime('now')`（UTC）→ 实测差 8 小时，两边比较必然错 | `models/*.py` vs `schema.py:23,41,...` |
| `import_analysis_to_kb.py` 把展示标签 `"000006.txt (15433行)"` 当文件路径存库 → 所有按 `source_file` 的查询/删除永远匹配不到 | `scripts/import_analysis_to_kb.py:51-58` |

### 2.5 输入校验与健壮性（会直接崩）

| 现象 | 位置 |
|---|---|
| 需求解析：`[]`/`"hello"`/`42`/`{"required_elements": null}` 全部抛 `AttributeError`/`TypeError`/`ValidationError`，而 `except` 只捕 `(JSONDecodeError, KeyError)` → **兜底分支不可达**，异常穿透到最外层 | `writing_engine/requirement_agent.py:75-81,93` |
| 大纲解析同上；`{"sections": {...}}`（对象而非数组）→ **静默 0 章节** → 空文章；截断 → 静默退化成 1 章节且 `core_argument=""` | `writing_engine/outline_agent.py:97-112,118` |
| 审稿报告：某个 `before_text: null`（level 3 提示词明说可不填）→ pydantic `ValidationError` → 被泛 `except` 吞掉 → **整份报告变成 `score=0, issues=[]`** | `review_engine/base_agent.py:165-212,127` |
| 截断修复的括号闭合顺序写反（先 `]` 后 `}`），多层嵌套仍然解析失败；`text.count` 还会把字符串里的括号算进去 | `review_engine/base_agent.py:62-73` |
| 合法 `score: 0` 被 `or` 链当作缺失；正则兜底路径不夹紧，`score: 11` → `ValidationError` → 整份报告丢失 | `review_engine/base_agent.py:185-203` |
| TUI 表单里数字字段是自由文本，`int(d["chapters"])` 未校验；异常发生在 screen 回调里，Textual 的 `_handle_exception` 会**直接退出整个应用**（输入 `abc` 即崩） | `tui/app.py:466,497,514-515,533-534,548` |
| Gradio 有两个回调返回值的**个数与 outputs 声明不符**（3 vs 4、1 vs 2）→ Gradio 4 会抛 `ValueError`，或让 `article_state` 保留上一次的文章 | `api/gradio_app.py:342-344,667-669` vs `:935,1006` |
| 一个损坏的 `project.json` 会让 `novel list` 以 `KeyError: 'name'` 死掉（service 版本会跳过损坏文件） | `cli/novel_commands.py:97`、`cli/common.py:150` |
| 章节正文/项目简介/伏笔用 `markup=True` 的 Static 直接渲染未转义文本，含 `[/quote]` 之类内容会抛 `MarkupError` 并退出应用 | `tui/app.py:703,141-151,355-356` |
| `query_units` 的 `"病句" in tags` 在 `tags` 为 NULL 时会 `TypeError`（当前写入方保证非 NULL，属防御缺口） | `knowledge_bridge.py:71` |
| `chardet` 检测不出编码时 `.get("encoding","utf-8")` 返回 `None` → `open(encoding=None)` 用系统 locale；`latin-1` 兜底能解码任意字节 → `raise ValueError("无法解码文件")` **永远不可达**，二进制文件被当乱码入库 | `utils/file_utils.py:20-23,42-50` |
| 线程 worker 无法中止：TUI 里 `esc`/`q` 不停止已在跑的批量写作（继续付费写章），重新进入工作台会因 `_busy=False` 允许第二个并发批量写作；`_run_local` 忽略 `_busy` → 本地保存的剧情笔记可能被 worker 之后的 `plot.save` 覆盖（丢更新） | `tui/app.py:610-611,254,418-429` |
| 项目名未做路径校验：`../../evil` 会在仓库根建目录并写入，绝对路径会直接丢弃 base_dir；`novel_delete` 把同一个原语交给 `rmtree` | `api/gradio_app.py:465,438,485`、`project_manager.py:42-43,218-221` |

### 2.6 已实现但没接上的功能（"假功能"清单）

- `instructor` 声明为依赖、HANDOVER 指定用它做结构化输出 → **零处使用**。
- `writing_engine` 的知识库参考写进 `request.raw_input`，而**没有任何 prompt 读这个字段** → `get_writing_guidance()` 零效果，日志却说查了知识库。
- "全文组装"步骤（`ARTICLE_ASSEMBLER_SYSTEM`）是死代码，`assemble()` 不调 LLM，HANDOVER 承诺的"过渡检查/整体一致检查/首尾呼应"从未运行；要素核验是 `elem.description[:10] in full_text`（空描述恒为 `True`），且 `RequiredElement.verified` 从不写回。
- 配置项 `writing.max_sections` / `min_section_words` / `outline_model` / `writing_model`、`review.auto_fix_level1` / `level2` / `parallel_agents` **全部无人读取**。
- `KNOWLEDGE_UNIT_SYNTHESIS_SYSTEM`（"提取最有价值的 2-4 个知识单元"）从未被调用；实际合成逻辑是"取第一个长度 > 10 的字符串字段"，且 docstring 说 1-3 个、代码 `break` 只给 1 个。
- `WrittenArticle.article_id` 从不赋值 → `cmd_e2e` 传空串给审稿。
- `models/character.py` 的 `relationship_details`、`DialogueStyle.address_others`、`RelationshipState.history`、`style_template.representative_samples`：声明了、文档写了、**没有任何写入方**。
- `api/gradio_app.py` 的 `export_text`/`import_file` 是死代码，却带着同一套路径穿越原语。

---

## 3. 工程与文档问题

1. **`.venv` 里没装 pytest**，`requirements-core.txt` 也不含 pytest（`requirements.txt` 有）。按 `requirements-core.txt` 的一键安装走完，**团队无法运行测试**——这正是 A14 能存在的前提。建议把 `pytest` 加进 `requirements-core.txt`。
2. **HANDOVER.md 已严重过期**，且是仓库里唯一的顶层文档（没有 README）：
   - 完全没有提到现在的角色引擎 / 剧情引擎 / 逐章写作 / TUI（`novel` 子系统，占现存代码量的很大一部分）；
   - 说"74 个单元测试全部通过"，实际是 193 个（我实跑 151 passed + 42 沙箱环境失败）；`requirements-core.txt` 写的是 193；
   - 引用的一堆文档路径 `D:\WORK\PROJECT\...` 在本机不存在；
   - 标题编号重复（两个"十、"）；
   - 承诺的能力与实现不符：例如"混合检索（向量 + BM25）→ RRF 融合 → Cross-Encoder Rerank → 多样性采样（同篇最多取 2 块）"在代码里没有实现，真实检索是 `LIKE '%kw%'`。
3. **测试质量参差**：`test_plot_engine.py` 把生产逻辑抄进测试再断言；`test_analysis.py:213-222` 的 `test_duplicate_chunks_ignored` **把 chunk_id 冲突导致的数据丢失断言成了正确行为**；`test_analysis.py:160-176` 的断言恒真；`test_json_utils.py:54-57` 把"带前后文的 JSON 解析失败"固化成了期望行为。建议把这些用例改成"断言正确的期望"，它们现在是在保护 bug。
4. `scripts/` 下混有 `_check_cp.py`、`_hexdump.py`、`_refactor.py`、`_reset_db.py` 等一次性脚本（`_` 前缀），与正式脚本混放；`git status` 里还有未跟踪的 `data/projects/重生！在ai出现之前的程序员/` 和 `requirements-core.txt`。
5. Bash 之外的杂项：`main.py tui` 会走到 argparse 的 invalid choice（`main.py:15,22-24`）；`kb files --page-size 0` 会 `ZeroDivisionError`。

---

## 4. 建议的修复顺序

**第 0 批（先止血，改动都很小，防止继续丢钱丢数据）**

1. `CharacterEngine.save` 改原子写 + `load` 失败不炸项目（A4-3）。
2. `_parse_analysis` 的 `is_new` 分支改成"只补空、不覆盖"（A2）。
3. 人格 shift 允许新增维度 + 夹紧 0-10 + `None` 兜底（A3/A9）。
4. 角色分析单独放宽 `max_tokens`（8192）并在解析失败时**明确上报**，`chapter_writer` 不再把 `0 个角色更新` 当成功（A1）。
5. CLI/Gradio 的空返回改报失败；`novel auto` / Gradio 一键生成改成"从第一个未写章节开始"（2.1）。
6. `project.json`/`characters.json` 改为原子写；`outline` 章号 int 归一化（2.4）。

**第 1 批（让角色引擎真的工作）**

7. `to_dict`/`load` 字段对称 + 全部用 `.get` 兜底（A4-1/2）。
8. `chapter_events` 去重 + 排序（A8/A11）。
9. 角色卡片补回 `core_desire`/`core_fear`/`moral_compass`/`background`/`appearance`（A7），并按出场筛选（A13）。
10. 关系强度/起始章/`reason` 修正（A6）；prompt 模板补 `role`（A10）。
11. 名字/别名归并（A5）—— 这一步对成稿质量提升最明显，因为它同时消除 prompt 里的矛盾角色卡。

**第 2 批（把"静默失败"改成"显式失败"）**

12. 统一一个"结构化输出"工具：`response_format=json_object` + 修复式解析（字符串感知的括号栈 / `raw_decode`）+ 一次重试；真正用上 `instructor` 或删掉这个依赖。这一条同时修掉角色分析、大纲、剧情、需求解析、审稿解析五处的同类问题。
13. 审稿 `ReviewReport` 增加 `parse_failed` 标记；`fixer` 报告真实 applied/skipped 数量；空文章、空大纲一律报错而非"完成"。

**第 3 批（成本与规模）**

14. 用量在失败路径也记录、`finish_reason` 上浮、预算前移为"预留制"、用量库并发修正、RPM 限流改为全局。
15. `chunk_id` 改用路径哈希（或 `(source_file, paragraph_index)` 复合主键），并把索引补成 `(source_file, ...)`。
16. 语料清洗接上 `noise_patterns`、按 `chunk_size` 合并短段、深层分析改为分层采样（现在只看了 0.058%）。
17. 检索层做决定：要么按 HANDOVER 实现（并修 `index_chunks` 的提前 return、1024 维 embedding、分批索引），要么删掉模块、把文档改对。

**第 4 批（防复发）**

18. 补 `tests/test_character_engine.py`（下面附录 A 给了现成用例）；把测试里那些"保护 bug"的断言改正。
19. 把 CLI/TUI/Gradio 的编排全部改为调用 `NovelService`，杜绝第四份抄本。
20. 重写 HANDOVER.md（或加 README），并把它与代码事实对齐。

---

## 附录 A：建议的角色引擎回归测试（现成可粘贴）

下面这些断言都是本次审查里**已经复现过的真实行为**，修好后应该全绿。建议新建 `tests/test_character_engine.py`（注意：`.venv` 目前没装 pytest，先补进 `requirements-core.txt`）。

```python
"""tests/test_character_engine.py — 角色引擎回归测试（覆盖本次审查发现的缺陷）。"""
import json
import pytest

from src.novel.character_engine import (
    CharacterEngine, CharacterProfile, ChapterEvent, PersonalityShift,
)


class FakeLLM:
    def __init__(self, response): self.response = response
    def chat(self, messages, model_tier="flash", **kw): return self.response


def test_existing_character_is_never_wiped_when_llm_says_is_new(tmp_path):
    """A2：is_new=true 不能清空老角色的历史。"""
    eng = CharacterEngine(FakeLLM(json.dumps({"characters": [
        {"name": "林辰", "is_new": True, "personality": {"勇敢": 3},
         "mood": "崩溃", "summary": "被击溃"}]}, ensure_ascii=False)))
    old = CharacterProfile(name="林辰", role="主角", personality={"勇敢": 9},
                           relationships={"苏婉": {"状态": "恋人", "强度": 9, "起始章": 1}})
    old.chapter_events.append(ChapterEvent(chapter=1, mood="坚定", summary="开场"))
    eng.add_character(old)

    eng.analyze_chapter(2, "第2章正文", ["林辰"])
    after = eng.get_character("林辰")

    assert after.role == "主角"                       # 不被降级成"配角"
    assert after.personality["勇敢"] == 9             # 不被覆盖
    assert "苏婉" in after.relationships              # 关系网不丢
    assert [e.chapter for e in after.chapter_events] == [1, 2]   # 第1章事件还在


def test_new_trait_in_shift_actually_lands_on_personality():
    """A3：此前没登记过的特质也要生效，而不是静默丢弃。"""
    eng = CharacterEngine(FakeLLM(json.dumps({"characters": [
        {"name": "林辰", "mood": "冷", "summary": "x",
         "personality_shifts": [{"trait": "冷酷", "old": 0, "new": 8, "reason": "被背叛"}]}]},
        ensure_ascii=False)))
    eng.add_character(CharacterProfile(name="林辰", personality={"勇敢": 5}))
    eng.analyze_chapter(2, "第2章", ["林辰"])
    assert eng.get_character("林辰").personality["冷酷"] == 8


def test_personality_values_are_clamped_and_null_safe():
    """A3/A9：越界夹紧、null 不写成人格值。"""
    resp = json.dumps({"characters": [{"name": "林辰", "mood": "x", "summary": "x",
        "personality_shifts": [
            {"trait": "愤怒", "old": 5, "new": 14, "reason": "暴走"},
            {"trait": "理智", "old": None, "new": None, "reason": "未知"}]}]},
        ensure_ascii=False)
    eng = CharacterEngine(FakeLLM(resp))
    eng.add_character(CharacterProfile(name="林辰", personality={"愤怒": 5, "理智": 5}))
    eng.analyze_chapter(2, "正文", ["林辰"])
    pers = eng.get_character("林辰").personality
    assert pers["愤怒"] == 10
    assert pers["理智"] == 5                          # 保持原值，不是 None
    assert all(isinstance(v, int) and 0 <= v <= 10 for v in pers.values())


def test_chapter_events_round_trip_keeps_relationship_changes(tmp_path):
    """A4：存档读档必须保住 relationship_changes。"""
    eng = CharacterEngine(FakeLLM("{}"))
    p = CharacterProfile(name="林辰", personality={"勇敢": 7})
    p.chapter_events.append(ChapterEvent(
        chapter=1, mood="紧张",
        relationship_changes=[{"target": "苏婉", "old": "陌生", "new": "信任", "reason": "救命"}],
        personality_shifts=[PersonalityShift("勇敢", 6, 7, "挺身而出")]))
    eng.add_character(p)

    path = tmp_path / "characters.json"
    eng.save(str(path))
    again = CharacterEngine(FakeLLM("{}"))
    again.load(str(path))

    ev = again.get_character("林辰").chapter_events[0]
    assert ev.relationship_changes == [{"target": "苏婉", "old": "陌生", "new": "信任", "reason": "救命"}]


def test_load_tolerates_hand_edited_files(tmp_path):
    """A4：手工编辑过的存档不能让整个项目打不开。"""
    path = tmp_path / "characters.json"
    path.write_text(json.dumps({"林辰": {"name": "林辰", "chapter_events": [
        {"chapter": 1, "summary": "开场", "personality_shifts": [
            {"trait": "勇敢", "old": 5, "new": 6}]}]}}, ensure_ascii=False), encoding="utf-8")
    CharacterEngine(FakeLLM("{}")).load(str(path))     # 不应抛 KeyError


def test_rewriting_a_chapter_does_not_duplicate_events():
    """A8：重写同一章要替换而不是追加。"""
    eng = CharacterEngine(FakeLLM(json.dumps(
        {"characters": [{"name": "林辰", "mood": "紧张", "summary": "第一版"}]}, ensure_ascii=False)))
    eng.add_character(CharacterProfile(name="林辰"))
    eng.analyze_chapter(3, "第一版", ["林辰"])
    eng.analyze_chapter(3, "第二版", ["林辰"])
    assert [e.chapter for e in eng.get_character("林辰").chapter_events] == [3]


def test_relationship_tracks_first_chapter_and_reason():
    """A6：起始章是首次出现的章，强度不能恒为 5，reason 要留下。"""
    resp = json.dumps({"characters": [{"name": "林辰", "mood": "x", "summary": "x",
        "relationship_changes": [{"target": "苏婉", "old": "陌生", "new": "信任",
                                  "reason": "救命之恩", "intensity": 8}]}]}, ensure_ascii=False)
    eng = CharacterEngine(FakeLLM(resp))
    eng.add_character(CharacterProfile(name="林辰"))
    eng.analyze_chapter(3, "正文", ["林辰"])
    eng.analyze_chapter(7, "正文", ["林辰"])
    rel = eng.get_character("林辰").relationships["苏婉"]
    assert rel["起始章"] == 3
    assert rel["强度"] == 8


def test_writing_context_includes_core_desire_and_fear():
    """A7：角色卡必须带上核心欲望/恐惧等一致性锚点。"""
    p = CharacterProfile(name="林辰", role="主角", personality={"勇敢": 7},
                         core_desire="找回妹妹", core_fear="被信任的人背叛",
                         moral_compass={"诚实": 8}, background="孤儿院", appearance="左眉有疤",
                         relationships={"苏婉": {"状态": "恋人", "强度": 9}})
    p.chapter_events.append(ChapterEvent(chapter=1, mood="紧张"))
    text = p.get_status_for_chapter(2)
    for anchor in ("找回妹妹", "被信任的人背叛", "孤儿院", "左眉有疤"):
        assert anchor in text


def test_analysis_failure_is_reported_not_silently_empty():
    """A1：LLM/解析失败不能伪装成"0 个角色更新"。"""
    class Boom:
        def chat(self, *a, **k): raise RuntimeError("429")
    eng = CharacterEngine(Boom())
    eng.add_character(CharacterProfile(name="林辰"))
    outcome = eng.analyze_chapter(3, "正文", ["林辰"])
    assert getattr(outcome, "ok", True) is False        # 需要 analyze_chapter 返回带 ok 的结果对象


def test_save_is_atomic_so_interruption_cannot_brick_project(tmp_path):
    """A4：写入中断后仍能读回上一份完整存档。"""
    path = tmp_path / "characters.json"
    eng = CharacterEngine(FakeLLM("{}"))
    eng.add_character(CharacterProfile(name="林辰", personality={"勇敢": 7}))
    eng.save(str(path))
    before = path.read_text("utf-8")
    # 模拟中断：残留 .tmp 不应污染正式文件
    (tmp_path / "characters.json.tmp").write_text('{"林辰": {"na', encoding="utf-8")
    again = CharacterEngine(FakeLLM("{}"))
    again.load(str(path))
    assert again.get_character("林辰") is not None
    assert path.read_text("utf-8") == before
```

---

## 附录 B：本次审查的方法与已排除项

- **方法**：4 路并行通读（TUI/CLI、Gradio/Web、写作与审稿引擎、知识库与预处理）+ 我自己精读角色引擎全链路；对角色引擎的每条结论都在项目自带 `.venv` 里跑了可复现探针；并用**你自己的生产数据**（5 个 `data/projects/*/characters.json`、`logs/writing_expert_2026-09-22.log`、`data/knowledge/index.csv`）与真实语料做交叉验证。所有探针文件已删除，未改动任何项目文件。
- **测试实跑结果**：`193 collected → 151 passed, 42 failed`。42 个失败**全部**是我这边沙箱禁止写系统临时目录导致的 `PermissionError`（`tempfile` 相关用例），不是逻辑失败——在本机正常环境应可全绿。
- **已排除（不是 bug，免得再查一遍）**：
  - RRF 的数学是对的（`k=60`、rank 从 0 起 +1），真正的缺陷是合并键可能为空；
  - `_RateLimiter` 令牌桶在并发下实测正确（6 个并发在 rpm=600 下精确间隔 0.1s），问题在于"每实例一份 + 重试绕过"；
  - BM25 的中文分词索引与查询都用 `jieba.cut`，没有空格/字级不一致；
  - 编码检测实测正确（chardet 7.6 对 69B-1MB 的 GBK 样本都返回 GB18030）；残留风险是 `latin-1` 兜底会让错误检测静默产生乱码，而不是抛异常；
  - 向量库 `score = 1.0 - distance` 对 `hnsw:space=cosine` 是正确的；
  - 没有任何用户输入拼进 SQL 字符串（`schema.py:156` 只插两个硬编码字面量）；
  - `character_analyzer` 读 `analysis_results.json` 的"叙事层"键名与实际文件一致；
  - `project_manager`/`plot_engine` 的已写章节与剧情章号 int↔str 往返是一致的（问题只出在 `outline`）；
  - `styles.tcss` 对 Textual 6.2.1 有效（只有一个失效选择器 `#foreshadow-table`）；
  - Gradio 里 `load_btn` 的复用看似可疑但实际正确。

> 另外：仓库根目录残留两个空目录 `pytest-cache-files-2qzaqvfv`、`pytest-cache-files-8z69oqi3`（我首次跑 pytest 时产生的，被沙箱锁住删不掉），可以手工 `rmdir` 清掉。
