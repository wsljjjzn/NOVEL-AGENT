# review_engine — 审稿引擎

> 板块三。**六维并行审稿 + 三级修改**。本文档记录维度定义、失败语义与已知陷阱。
> 行为变更先改这里，再改代码（见 [../plan/02-workflow.md](../../plan/02-workflow.md)）。

---

## 1. 它负责什么

给定一段正文（文章或小说章节），并行调用六个维度的审稿 Agent，把发现的问题按
**修改级别**聚合为「自动修改 / 待确认 / 手动指引」三档，并提供把 Level 1 改动落回
正文的能力。

**明确不做的**：

- 不生成正文（那是 `writing_engine` / `novel.chapter_writer` 的事）
- 不做跨章节的剧情推进（只审「给它的这段文本」，一致性靠外部注入的**作品状态**）
- 不直接落盘（落盘由 CLI / Web / 服务层适配器决定）

审稿引擎**允许**依赖 LLM；它是生成层，不是确定性的 `src/novel/*` 领域层。

---

## 2. 两种维度预设

同一套编排支持两种预设，由 `ReviewOrchestrator(profile=...)` 或
`review(profile=...)` 选择：

### `article`（默认，非虚构/文章）

| key | 中文名 | 关注点 |
|---|---|---|
| `thought` | 思想审稿 | 原创性、逻辑自洽、反例意识、适用范围、价值观 |
| `structure` | 结构审稿 | 信息释放节奏、章节功能、过渡、首尾呼应 |
| `narrative` | 叙事审稿 | 人物立体度、情感节奏、悬念冲突、是否过度煽情 |
| `language` | 语言审稿 | 句长、句式、语气一致、用词、修辞、文体适配 |
| `fact_check` | 事实核查 | `[来源:chunk_id]` 核对、断章取义、数据、未标注主张、幻觉 |
| `proofread` | 校对 | 错别字、标点、的地得、格式、语病、专名一致 |

### `novel`（小说向）

| key | 中文名 | 关注点 |
|---|---|---|
| `character` | 人物一致性 | 人格突变、关系失真、动机一致、说话声音、弧光铺垫 |
| `continuity` | 设定连续性 | 世界观冲突、时间线矛盾、既成事实、称谓、大纲偏离 |
| `foreshadow` | 伏笔回收 | 遗忘的伏笔、突兀回收、新坑可回收性、线索一致、大纲伏笔 |
| `pacing` | 节奏 | 信息密度、场景转换、高潮分布、情绪曲线、篇幅配比 |
| `language` | 语言文风 | 同 `article` 的语言维度 |
| `proofread` | 校对 | 同 `article` 的校对维度 |

**小说预设的关键差异**：涉及情节/人物/设定的问题一律 `level>=2`，
`level=1`（自动改）**只保留可机械替换的字词标点错误**——剧情不是能安全自动改写的。

### 作品状态注入

小说向审稿通过 `review(context=...)` 注入一段**作品状态**（角色档案、开放伏笔、
世界观、前情、本章大纲），见 `context.py::build_novel_context`。审稿 Agent 用它做
一致性核对；注入内容只作参照，不要求照抄。

---

## 3. 对外接口

```python
# src/review_engine/orchestrator.py
ReviewOrchestrator(llm_client=None, profile="article")
  .review(article_text, article_id="", parallel=None,
          model_tier="pro", context="", profile=None) -> AggregatedReview
  .apply_fixes(article_text, aggregated, apply_level2=False) -> str
  .format_report(aggregated) -> str

# src/review_engine/base_agent.py
BaseReviewAgent(name, system_prompt, llm_client=None, key="")
  .review(article_text, article_id="", model_tier="pro", context="") -> ReviewReport

# src/review_engine/fixer.py
ArticleFixer.apply_auto_fixes(text, issues) -> str            # 兼容旧签名
ArticleFixer.apply_auto_fixes_detailed(text, issues) -> FixOutcome   # {text, applied, missed, skipped}
ArticleFixer.apply_confirmed_fixes(text, issues) -> str
ArticleFixer.apply_confirmed_fixes_detailed(text, issues) -> FixOutcome
ArticleFixer.format_review_report(aggregated) -> str

# src/review_engine/context.py
build_novel_context(project=None, engine=None, plot=None, chapter_num=None) -> str
```

模型层：`ReviewReport.status` 为 `ok | failed`（见 [contracts §4](../specs/contracts.md)）。

---

## 4. 不变量

1. **`reports` 长度恒等于预设维度数（6）**。任一维度失败也占位，用 `status="failed"` 标记，
   绝不以「少一个 report」的方式静默降级。
2. **`status="failed"` 的报告不得被计分**：`AggregatedReview.overall_score` 与报告表格只统计 `ok` 维度。
3. **`score` 始终在 [0, 10]**，越界一律夹取，不因模型给出 85 分而抛 `ValidationError`。
4. **`level` 始终是 1/2/3**；`"Level 1"` / `"级别2"` / `"L3"` 等写法都要被识别。
5. **Level 1 的自动修改只在锚点命中时发生**，且必须报告实际命中/未命中数量
   （`applied_fixes` / `missed_fixes`），不允许「没改到也打 ✅」。
6. **自动修改的最小锚点**：`before_text` 去空白后至少 2 个字符；单字符仅在全文唯一时才允许替换。
7. **`apply_fixes` 只改锚点所在片段**，不得因归一化偏移而移动/删除无关正文。
8. **预算耗尽时**：不再发起新的维度调用（取消未启动的 future），已得报告仍随异常/结果保留。
9. **思考保持开启，预算必须容得下它**：该档 `max_tokens` 要能同时装下思考与正文
   （实测单维审稿需 6k~13k tokens，两档配置均为 16384）。审稿还必须
   `json_mode=True`（`response_format=json_object`）——思考开着时模型可能改写成散文，
   实测同一提示词不加约束会拿到无法解析的 `content`。
   空内容要报成「模型未返回任何内容」，不能与「返回了无法解析的 JSON」混为一谈。

---

## 5. 已知陷阱（历史缺陷，已在本轮修复）

| 陷阱 | 原位置 | 现象 | 现状 |
|---|---|---|---|
| **思考吃满输出预算** | `config.yaml` + `base_agent.review` | V4 默认开思考，思考**先于**正文消耗 `max_tokens`：flash 的 4096 被打满 → `content=""`，报告成片「JSON 解析失败」，实际模型一个字都没返回（2026-10-13 flash 档 6 维里 4 维失败） | ✅ **保留思考**，两档 `max_tokens` 提到 16384（实测单维「思考+正文」需 6k~13k）；审稿另传 `json_mode=True`（`response_format=json_object`）保证输出可解析；空内容单独报错并留日志 |
| 偏移串台 | `fixer._find_and_replace` | 用「空白归一化文本的下标」切「原文」，把修复插到文章开头、吃掉换行 | ✅ 改为记录归一化→原文的映射 |
| 假成功 | `base_agent._parse_response` | JSON 解析失败写成「审稿完成」+ score 5.0，与「没问题」不可区分 | ✅ `status="failed"` |
| 0 分被当缺失 | `base_agent._parse_response` | `score or ...` 把合法 0 分抹掉 | ✅ 改为显式 `is None` 判断 |
| 分数越界炸报告 | `base_agent._parse_response` | 模型给 85 分 → `ReviewReport` 校验抛错 → 整份报告被替换成「审稿失败」 | ✅ 结构化分支夹取到 [0,10] |
| Level 标签降级 | `base_agent._safe_int_level` | `"Level 1"` 解析失败退回 2，可自动修的变成待确认 | ✅ 支持 `Level/L/级别/第N级` |
| 退化锚点 | `fixer.apply_auto_fixes` | `before_text="的"` 替换全文第一处 | ✅ 最小锚点 + 唯一性检查 |
| 静默丢 Agent | `orchestrator._review_parallel` | 非预算异常只记日志，`reports` 可少于 6 且无标记 | ✅ 失败维度占位 `status="failed"` |
| 预算穿透 | `orchestrator.review` | 6 个 Pro 并发可一起越过逐调用预算闸 | ✅ 启动前预估 + 取消未启动 future |

其余历史问题（并行用量落库丢行 `cost_tracker`、web 不透传 tier）不在本模块范围，
见 [REVIEW-2026-10-12.md](../../REVIEW-2026-10-12.md)。

---

## 6. 修改级别（三级修改）

| level | 含义 | 处理 |
|---|---|---|
| 1 | 严重错误且**可机械替换** | `apply_auto_fixes` 自动应用 |
| 2 | 需要用户确认 | Web 默认不用；CLI `--level2` 时应用 |
| 3 | 仅参考 | 只出指引，不改文本 |

`severity(critical/warning/info)` 只影响展示图标，不影响级别。

---

## 7. 适配器入口

审稿引擎本身不认识界面；下列入口都只是适配器：

| 入口 | 位置 | 说明 |
|---|---|---|
| Web（Gradio 板块三） | `api/gradio_app.py::handle_review` | 勾选「小说向审稿」时注入作品状态 |
| CLI | `cli/article_commands.py::cmd_review` | `--level2` 才应用 Level 2；有效维度为 0 时非零退出 |
| FastAPI | `api/server.py` `POST /review` | 支持 `profile` / `context`，返回总分与失败维度 |
| **服务层（只审不改）** | `novel/service.py::NovelService.review_chapter(apply_level1=False)` | 返回 `Result.data = AggregatedReview`，供界面生成勾选清单 |
| **服务层（应用勾选）** | `novel/service.py::NovelService.apply_review_fixes` | 只应用传入的条目，落盘前备份 |
| **TUI** | `tui/review.py::ReviewModal`（工作台/阅读器按 `v`） | 选章 → 后台审稿 → **勾选要改的条目** → 应用并落盘 |

### TUI 审稿：勾选哪条就改哪条

审稿**不再自动改写正文**。`ReviewModal` 的流程是：

1. `review_chapter(apply_level1=False, save=False)` —— 只审不改，结果放进 `Result.data`。
2. 从 `AggregatedReview.applicable_issues` 生成勾选清单（Level 1 + 带 before/after 的 Level 2），
   **Level 1 默认勾选、Level 2 默认不勾**，可「全选 / 全不选」。
3. `AggregatedReview.guidance_issues`（Level 3 + 缺 before/after 的条目）只展示为人工指引，不可勾选。
4. 点「应用勾选并保存」才调用 `apply_review_fixes`：只应用被勾选的条目，先备份 `project.json`。

`NovelService` 侧护栏：

1. **空章拒绝**：没有正文的章节不送审（不花冤枉钱，也不会把「审稿成功」挂在空章节上）。
2. **全失败不上报成功**：六个维度全 `failed` 时返回 `ok=False`，并附上失败原因。
3. **写回前备份**：应用修改会覆盖既有正文，落盘前先备份 `project.json`。
4. **只在真的改动了才写盘**：命中 0 处时返回 `ok=False`，不落盘、不备份。
5. **空勾选是业务失败**：`apply_review_fixes(issues=[])` 返回 `ok=False`，绝不"假装改过"。

界面层（`ReviewModal`）额外保证：审稿进行中禁止关闭浮层、同一浮层只允许点一次「开始」与一次「应用」，
避免连点造成重复计费或重复改写。
