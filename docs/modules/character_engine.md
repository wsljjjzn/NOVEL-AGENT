# 模块：`character_engine` — 角色人格引擎

## 负责

`data/projects/<名>/characters.json` 的读写，以及**跨章节的角色状态演变**：人格特质、关系网、逐章事件。

**不负责**：生成角色档案（那在 `plot_engine.design_characters`）；角色**分析**的 LLM 调用（P4 后移到 `src/llm/`）。

## 对外接口

```python
class CharacterProfile(PersistedModel):        # pydantic v2（P1-2）
    name: str
    aliases: list[str]
    role: str                       # 主角 / 反派 / 配角 / 路人
    personality: dict               # {特质: 0-10}；⚠️ 故意保持宽松 dict，见下
    speaking_style: str
    core_desire: str                # 核心欲望（一致性锚点）
    core_fear: str                  # 核心恐惧（一致性锚点）
    moral_compass: dict
    background: str
    appearance: str
    chapter_events: list[ChapterEvent]
    relationships: dict             # 值可能是 dict，也可能是历史遗留的字符串
    arc_summary: str

    # 逐章视图（一律按章号排序）
    def sorted_events(self) -> list[ChapterEvent]
    def upsert_event(self, event: ChapterEvent) -> None
    def recent_events(self, before_chapter: int, window: int = 3) -> list[ChapterEvent]
    def appeared_within(self, chapter_num: int, window: int = 3) -> bool
    def get_status_for_chapter(self, chapter: int) -> str    # 写作用角色卡片
    def fill_missing(self, data: dict) -> list[str]          # 只补空，绝不覆盖

class CharacterEngine:
    def analyze_chapter_ex(self, chapter_num, chapter_text,
                           existing_names=None, model_tier="flash",
                           max_tokens=8192) -> AnalysisOutcome
    def get_context_for_writing(self, chapter_num, focus=None,
                                include_all=False) -> str
    def save(self, path: str) -> None
    def load(self, path: str) -> None
```

## 不变量

| # | 不变量 | 保障方式 |
|---|---|---|
| 1 | `chapter_events` **按章号有序且无重复章号** | `upsert_event` 同章替换 + 排序 |
| 2 | 人格值与关系强度是 **0-10 整数** | `_to_int_0_10`（P1 后改为 `field_validator`） |
| 3 | 写入**原子**（`os.replace`） | `save` 用临时文件 |
| 4 | 单条记录缺字段**不让整个项目打不开** | `from_dict` 全部 `.get()` + 默认值 |
| 5 | `save` 在**每写完一章**都会被调用 | `chapter_writer.write_chapter` |
| 6 | 已有角色**永不被 `is_new` 清空** | `_resolve_existing_name` + `fill_missing` |
| 7 | 名字归一化后同一角色归并 | `_normalize_name` 去括号注释/全角括号/空白 |

### P1-2：为什么模型改成 pydantic，以及三个刻意的选择

领域模型（`CharacterProfile` / `ChapterEvent` / `PersonalityShift`）已从 dataclass
换成 pydantic v2 的 `BaseModel`。校验加在**数据进来时**，落盘格式**不变**。

| 选择 | 原因 |
|---|---|
| `extra="allow"`，不用 pydantic 默认的 `"ignore"` | 默认值会**静默丢掉**档案里不认识的键（CODE_REVIEW A15 点名的坑）。`to_dict` 会把额外键并回去，手工编辑/新版写出的字段不再消失 |
| `personality` / `moral_compass` / `relationships` 保持**无参 `dict`** | 存量档案里有 `{"善良": null}`、关系值是字符串。收紧成 `dict[str, int]` 会让老项目直接打不开；数值兜底放在读取处（`personality_summary` / `_to_int_0_10`） |
| `relationship_changes` 保持**纯 `dict` 列表** | `to_dict` 与写作卡片都用 `isinstance(rc, dict)` 判定；换成嵌套模型会让关系变化在落盘时被静默丢弃（A4 事故的翻版） |
| 不开 `validate_assignment`、不 `frozen` | 引擎会在原地改字段与容器（`profile.personality[t] = v`、`upsert_event` 下标赋值 + `sort`） |
| `to_dict` / `from_dict` 继续保留为兼容层 | 它们是落盘契约，由 `tests/test_roundtrip_baseline.py` 锁住；pydantic 负责构造期归一化 |

直接由 LLM 输出构造（`service.generate_characters`）以前**绕过**所有归一化，
现在与 `from_dict` 走同一套 `field_validator`：`chapter="3"`、`key_actions="一个动作"`、
`relationships={"乙": "描述文本"}` 都会被正确归一化。

## 为什么会话设计成这样（历史）

本模块经历过一轮**严重缺陷修复**（A1–A13），缺陷的共同特征是**静默失效**：不报错、不计失败、照常计费。原文是根目录的 `CODE_REVIEW.md`（P6-4 会移入 `docs/legacy/`）。

修复后的关键设计，**改动时不要回退**：

| 设计 | 为什么 |
|---|---|
| `AnalysisOutcome` 区分 `ok` / `no_change` / `parse_failed` / `llm_failed` | 失败与"没有变化"必须可区分（A1） |
| 分析调用 `max_tokens=8192`（非 config 的 4096） | 4096 会把角色 JSON 硬截断（A1 的成因） |
| `is_new` **只当提示**，是否新建以"归一化名字是否已存在"为准 | 模型把回归角色标成"新出场"是常见行为（A2） |
| 未登记的特质也落地，不静默丢弃 | 否则"人格演变"只存在于事件日志里（A3） |
| `relationship_changes` 进 `to_dict` / `load` | 此前落盘即丢（A4） |
| `fill_missing` 只补空、绝不覆盖 | "本章观察"不能推翻长期设定（A2/A10） |
| 写作卡片无条件输出 `core_desire` / `core_fear` / `moral_compass` / `background` / `appearance` | 此前只要有过事件就全不输出（A7） |
| `get_context_for_writing` 按出场筛选，`ALWAYS_KEEP_ROLES = ("主角","反派")` | 此前无脑塞入全部角色（A13） |

> **`AnalysisOutcome` 的四态是 `NovelResult` 三态的前身**，P2-2 要做显式映射。见 [`../specs/contracts.md`](../specs/contracts.md) §4。

## 已知陷阱

### ⚠️ 陷阱 1：别名归并是**字符串匹配**，不是语义

`_normalize_name` 只处理「全角括号 / 括号注释 / 空白」。它**不会**把 `林雪` 与 `林雪（林辰妹妹的信号源）` 之外的近义写法归并（如 `扎克` vs `流浪者扎克`）。

**生产数据里仍有未归并的**：`林雪` / `林雪（林辰妹妹）` / `林雪（林辰妹妹的信号源）` 三条并存于同一个项目。

**影响**：同一人可能有多张互相矛盾的角色卡进 prompt。

**这是已知限制，不是 bug**——真正的归并需要别名表或相似度阈值（P1-4 的范围）。

### ⚠️ 陷阱 2：`ANALYSIS_TEXT_LIMIT = 6000`

超限时**告警并截断**，只分析前 6000 字。pro 档一章写到 8000 字以上时，**后半章的人物变化全部丢失**。

**这是有意取舍**（截断会告警，不再静默）。改法：超限时按段落多次分析并合并。

### 陷阱 3：`get_context_for_writing` 的 `focus` 参数

传剧情设计里的 `character_appearances` 能得到最好效果。不传时会退化为"主角/反派 + 最近 3 章出场 + 无事件的新角色"。

**兜底行为**：如果筛选结果为空，返回**全部角色**（宁可全给，也不要一个字都不给）。

### 陷阱 4：别名写入是单向的

`_apply_analysis` 在发现新写法时把该写法加进 `profile.aliases`，**但不会更新 `relationships` 里指向旧写法的键**。所以关系网可能指向一个已归并的名字。
