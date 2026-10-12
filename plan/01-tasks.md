# 01 — 任务分解

取任务前先读 `README.md` 的铁律与 `00-phases.md` 的阶段定义。

**格式**：每条含 `前置` · `写入范围` · `验收`。写入范围是**建议性约束**，多人并行时不得越界。

---

## P0 · 止血

### P0-1 CLI 改调 NovelService（4 处内联编排）

- **前置**：无
- **写入范围**：`src/interfaces/cli/novel_commands.py`、`src/novel/service.py`
- **做**：`cmd_outline` / `cmd_characters` / `cmd_plot` / `cmd_write` / `cmd_auto` 改为委托 `NovelService` 对应方法。删除 `_fill_characters` 这个内联复刻。
- **验收**：
  - `cmd_characters` 覆盖前产生 `characters.json.bak-<时间戳>`
  - `cmd_auto` 仍从「第一个未写章节」开始（**已修好，别回退**，见 `novel_commands.py:373-381`）
  - `uv run pytest tests/interfaces -q` 全绿

### P0-2 空输出 → 非 0 退出

- **前置**：P0-1
- **写入范围**：`src/interfaces/cli/*.py`
- **做**：`cmd_write` / `cmd_auto` / `cmd_characters` / `cmd_plot` 在引擎返回空结果时报失败并 `return 1`。
  **注意**：`cmd_write:341` 现在打印"写作完成（0 字）**并已保存**"是**假陈述**——`chapter_writer.py:86-88` 空响应根本不落盘。
- **验收**：
  - `uv run na novel write <项目> --chapter N`（mock 空返回）**exit ≠ 0**
  - `cmd_auto` 中途某章失败时整体 **exit ≠ 0**（现在 `400-401` break 后 `405-409` 照常 `return 0`）

### P0-3 契约测试：tier 必须真的传下去

- **前置**：P0-1
- **写入范围**：`tests/interfaces/test_cli_contracts.py`（新建）
- **做**：断言 `design_characters` / `design_chapter_plot` **收到被传入的 tier**，而不是被内部硬编码覆盖。
- **验收**：把 `plot_engine.py` 的 `model_tier="flash"` 改回硬编码时，该测试**必须失败**。

### P0-4 修"护栏即测试前提"用例

- **前置**：无
- **写入范围**：`tests/interfaces/test_tui.py`
- **做**：`test_batch_write_refuses_to_rewrite_existing_chapters`（`:264-277`）现在**没有替换 writer/LLM**，靠护栏生效才不联网。一旦护栏回归，这条用例会从"断言失败"变成"**真调 API 整本重写**"。
- **验收**：该用例显式注入 fake writer；护栏即使回归也只产生断言失败，**不产生网络调用**。

---

## P1 · 模型层

### P1-1 读写往返基线（**必须先做**）

- **前置**：P0
- **写入范围**：`tests/novel/test_model_roundtrip.py`（新建）
- **做**：对 `data/projects/` 下 **5 个真实项目**，读入 `characters.json` / `plots.json` / `project.json` → 序列化 → 与原文逐字节比对，把**当前行为**固化成测试。
- **验收**：5 个项目全部通过；这份测试在 P1-2 之后**必须仍然通过**。
- **为什么**：这是防止 P1 破坏存量数据的**唯一安全网**。先有基线，再改模型。

### P1-2 CharacterProfile / ChapterEvent / PersonalityShift → pydantic

- **前置**：P1-1
- **写入范围**：`src/novel/character_engine.py`、`tests/novel/test_character_engine.py`
- **做**：三个 dataclass → `BaseModel`；`_to_int_0_10` / `_as_str` / `_as_dict` / `_as_str_list` → `field_validator`；`to_dict` / `from_dict` 保留为兼容层。
- **验收**：
  - P1-1 的往返测试通过（**允许字段顺序差异，不允许值差异**）
  - `tests/novel/test_character_engine.py` 的 50 个用例**全绿且未修改断言**
- **禁止**：不改 JSON 文件格式；不做数据迁移。

### P1-3 ChapterPlot / Scene → pydantic

- **前置**：P1-1
- **写入范围**：`src/novel/plot_engine.py`
- **验收**：同 P1-2。

### P1-4 清理两套角色模型的不一致

- **前置**：P1-2
- **写入范围**：`src/models/character.py`、`src/analysis/character_analyzer.py`
- **做**：`character_analyzer.py:64-68` 让模型输出 `{"句式特征","口头禅","语气倾向"}`，而 `DialogueStyle` 字段是 `sentence_pattern/catchphrases/tone_tendency` → pydantic 默认 `extra='ignore'`，**每个提取出的角色都丢掉了声音特征**且不报错。对齐字段名或加 `Field(alias=...)`。
- **验收**：一条测试断言提取出的 `DialogueStyle` **非全默认值**。

---

## P2 · 工具层

### P2-1 定义 NovelResult

- **前置**：P1-2
- **写入范围**：`src/tools/result.py`（新建）
- **做**：

```python
class NovelResult[T](BaseModel):
    ok: bool
    data: T | None = None
    summary: str = ""          # 人类可读，给 CLI 渲染
    warnings: list[str] = []
    error: str = ""            # ok=False 时必填
```

- **验收**：`summary` 存在时 `ok=False` 仍可渲染（CLI 要能显示失败原因）。

### P2-2 三态失败语义显式化

- **前置**：P2-1
- **写入范围**：`src/tools/result.py`、`docs/specs/contracts.md`
- **做**：把 `AnalysisOutcome` 的 `ok` / `no_change` / `parse_failed` / `llm_failed` 四态**明确映射**到 `NovelResult`。这是 P4 的前置——Pydantic AI 是两态（实例/异常）。
- **验收**：三种情况各有一条测试，且**互相可区分**。

### P2-3 NovelService 15 个方法返回 NovelResult

- **前置**：P2-1
- **写入范围**：`src/novel/service.py`、`tests/novel/test_novel_service.py`
- **做**：`title` + `lines: list[str]` → `NovelResult[T]`。
- **验收**：21 个既有用例全绿（必要时改断言，但**不得放松语义**）。

### P2-4 操作注册表（A 轨 / B 轨）

- **前置**：P2-3
- **写入范围**：`src/tools/registry.py`、`src/tools/novel.py`、`src/tools/kb.py`（新建）
- **做**：操作带 **A 轨（零 LLM）/ B 轨（生成）** 标记。
- **验收**：一条测试断言**所有 A 轨操作在 LLM 被完全禁用时仍可调用**。

### P2-5 build_chapter_prompt（A 轨关键操作）

- **前置**：P2-4
- **写入范围**：`src/tools/novel.py`
- **做**：返回拼装完整的写作 prompt（角色状态 + 前情提要 + 大纲 + 剧情设计 + 未解伏笔），**不调 LLM**。
- **为什么关键**：它是 B3 档（交还宿主）的载体——**让"宿主不支持 sampling"从降级变成天然可用的主路径**。
- **验收**：返回的 prompt 含角色核心欲望/恐惧/背景（验证 A7 修复未回退）。

---

## P3 · 双适配器（**可分两个 agent 并行**）

### P3a · CLI 适配器

- **前置**：P2-4
- **写入范围**：`src/interfaces/cli/*`、`src/pyproject` 入口
- **做**：18 个命令函数 → **渲染器 + 退出码映射**。
- **删除**：`--json` 开关（MCP 天生给结构化数据，方向反了）。
  **但 `--tier` 不删**——它是保留的弃用别名，见 P5-2。
- **验收**：
  - 退出码判断**只在一处**（`0 if result.ok else 1`）
  - `--out` / `--stdout` / `--page` / `--page-size` 等**呈现层参数留在 CLI**，不进工具层

### P3b · MCP 适配器（先只出 A 轨）

- **前置**：P2-4
- **写入范围**：`src/interfaces/mcp/server.py`（新建）
- **做**：
  - `inputSchema` 从 pydantic 模型自动生成
  - 工具级错误 → 结果内 `isError: true`（**禁止协议级错误**）
  - `initialize` 时记录 `ClientCapabilities.sampling` 是否存在
- **验收**：
  - 真实宿主能连上并调用 `project_list`
  - 一条测试断言**失败操作返回 `isError=True` 而非抛异常**
  - `resources` 暴露 `novel://{project}/characters` 等

---

## P4 · LLM 层

### P4-0 四个 spike（**必须先做，否则 P4 可能不成立**）

- **前置**：P2
- **写入范围**：`tests/spikes/`（临时，验证后删除或保留为文档）
- **spike 1**：`agent.run_sync()` 在 **Textual worker 线程**里是否抛异常（`loop.run_until_complete` 遇到运行中的 loop）。→ 决定 TUI 路径可行性。**先走 CLI 验证。**
- **spike 2**：`MCPSamplingModel` 在**服务器进程内**是否可用。→ 不行则 B1 档消失，只剩 B2/B3（**方案不崩，B3 仍可用**）。
- **spike 3（DeepSeek compat）**：Chat Completions 下 `response_format={"type":"json_object"}` + `thinking=False`，**是否真的能让强制 `tool_choice` 生效**。→ 不行则 compat 模式退化为纯 `PromptedOutput`（仍可用，约束更弱）。
- **spike 4（DeepSeek strict）**：Responses API 的 strict JSON Schema 是否可用；**显式传 `message_history`** 是否有效（该 API 无状态）。
- **验收**：四个 spike 各有一页结论，写进 `docs/specs/llm.md` 与 `docs/specs/deepseek-fastpath.md` 的「未验证事项」表（逐条改为已验证/已否定）。

### P4-1 拆分 12 处 except

- **前置**：P4-0
- **写入范围**：`src/analysis/*`、`src/novel/plot_engine.py`
- **做**：逐条区分「**有意降级**」与「**静默失败**」。`character_analyzer.py:130` 的 `_rule_based_extract` 是**有意降级**（保留并标注），其余是静默失败（改为显式失败）。
- **验收**：每条 except 有注释说明属于哪类；静默失败类全部改为返回 `NovelResult(ok=False)`。

### P4-2 建 src/llm/，迁角色分析

- **前置**：P4-1
- **写入范围**：`src/llm/agents.py`（新建）、`src/novel/character_engine.py`
- **做**：`analyze_chapter_ex` 改用 `Agent(output_type=CharacterAnalysis)`。
- **验收**：`TestModel` 下全绿；显式注入 fake 而非靠"没配 Key"。

### P4-3 ~ P4-6 其余调用点

按模块拆：大纲 / 剧情 / 逐章写作 / 六维审稿。

- **验收（每个）**：原调用点删除；`docs/specs/llm.md` 更新对应一节。

### P4-7 删除死代码

- **前置**：P4-3..P4-6 全部完成
- **写入范围**：`src/utils/llm_client.py`、`src/utils/cost_tracker.py`、`src/utils/json_utils.py`
- **做**：`llm_client.py` 与 `cost_tracker.py` 整体删除；`json_utils` 只保留非解析用途。
- **验收**：全仓 `import openai` 归零（除 `src/llm/`）。

### P4-8 DeepSeek FastPath（兼容优先）

- **前置**：P4-0 spike 3/4、P4-2
- **写入范围**：`src/llm/fastpath/deepseek.py`（新建）、`config/models.yaml`
- **设计见** [`../docs/specs/deepseek-fastpath.md`](../docs/specs/deepseek-fastpath.md)
- **做**：
  - `DeepSeekFastPath` 实现 `resolve_model` / `resolve_output_mode` / `build_model_settings`
  - **默认 `compat` 模式**：Chat Completions + `json_object` + `thinking=False`（**端点、Key、模型名、`max_tokens` 全部与现状一致**）
  - `strict` 模式可选：Responses API + `NativeOutput`（**不得设 `openai_previous_response_id`**）
- **兼容性硬要求（8 条验收）**：见 fastpath 文档 §5。其中最低底线：
  - `model_tier="flash"` / `"pro"` **仍然可用**
  - `tests/test_llm_client.py` **不改断言**全绿
  - `ANALYSIS_MAX_TOKENS = 8192` 的显式覆盖**未被回退**（flash 档也要 8192，4096 会截断角色 JSON —— 这是 A1 的成因）
- **⚠️ 禁止**：FastPath 内实现重试、预算、用量记录、Agent 声明。它只是**解析与设置策略**。违反则架空架构约束②。

### P4-9 键名回退链统一

- **前置**：P4-8
- **写入范围**：`src/llm/fastpath/deepseek.py`
- **做**：统一采用 `service.py:347-348` 的回退策略（`deepseek_v4_{tier}` → `{tier}` → `*_{tier}` 后缀），**删除 `llm_client.py:110-111` 的硬编码键名**。
- **为什么**：现状两处策略不一致——改 `config.yaml` 里的键名会让 `llm_client` 的 `.flash` 变 `None` 并抛"模型层未配置"，而 `service.llm_status` 却能正常显示。
- **验收**：配置里把 `deepseek_v4_flash` 改成别的后缀名，**两个消费者都仍能解析**。

---

## P5 · 模型无关

### P5-1 config/models.yaml

- **前置**：P4
- **写入范围**：`config/models.yaml`（新建）、`src/llm/providers.py`
- **做**：provider 注册表（纯数据）。DeepSeek / Moonshot / 智谱 / Ollama / 任意 OpenAI 兼容端点。DeepSeek 段含 `fastpath:` 配置（见 [`../docs/specs/deepseek-fastpath.md`](../docs/specs/deepseek-fastpath.md)）。
- **验收**：加一个新 provider **只改 yaml**，代码零改动（用测试证明）。

### P5-0 CNY→USD 换算集中化

- **前置**：P4-8
- **写入范围**：`src/llm/budget.py`（新建）
- **做**：`UsageLimits.cost_limit` 用 **USD**，而配置里 `budget.max_cny_per_session: 50` 是 **CNY**。换算集中一处，配置**继续写 CNY**。
- **验收**：配置写 50 → `cost_limit` 拿到约 `50 / 7.25`；**不要让用户改成 USD**。

### P5-2 --provider/--model（**外层解析，内部不动**）

- **前置**：P5-1、P3a
- **写入范围**：`src/interfaces/cli/*`、`src/llm/fastpath/deepseek.py`、`src/novel/plot_engine.py`、`src/novel/service.py`
- **⚠️ 核心约束**：`tier` **只在外层兼容**，不扩散改造。

  `model_tier` 是贯穿 **10 个模块**的透传参数。**不改它们的签名，不在内部 API 加 `ModelRef`。**

  | 项 | 结论 |
  |---|---|
  | `--provider` / `--model` | 只在**最外层入口**解析，就地转成 tier 或模型 |
  | `tier` 在内部 | 原样透传，不转换 |
  | tier→模型解析 | **只有一处**：`FastPath.resolve_model(tier)` |

- **做**：
  1. **新增** `--provider` / `--model`（外层）
  2. **保留** `--tier` 为已弃用别名（stderr 提示，不删除）
  3. **修两处死 tier**（这是唯一动内部的地方）：
     - `plot_engine.py` 两个方法签名加 `model_tier: str = "flash"`，替换 `:187` / `:239` 的硬编码
     - `service.py` 的 `design_plot` 与 `generate_characters` 把已收下的 `tier` **转发下去**
- **不改**：`character_analyzer.py:126` / `:222`、`lightweight.py:31` / `:45` 的 `"flash"` —— 那是**有意固定用便宜档**的正确设计（轻量分类不需要强模型）

- **顺带**：`kb_commands.py:230` 的 `cmd_learn` 从不读 `args.tier` → 要么转发要么删掉该选项（二选一，别让它继续是死参数）

- **验收**：
  - `--tier pro` **仍能真的改变模型**（不只是显示）
  - `--provider foo --model bar` 能真的改变实际调用的端点
  - `grep -rn 'model_tier="flash"' src/` **只剩 4 处**（上述有意固定的位置）
  - **`git diff --stat` 显示改动文件不超过 4 个**（`plot_engine.py` / `service.py` / `src/llm/` / `src/interfaces/`）

### P5-3 三档降级

- **前置**：P5-2
- **写入范围**：`src/llm/resolve.py`（新建）
- **做**：B1 宿主采样 → B2 provider 配置 → B3 交还宿主（返回 prompt 包）。
- **验收**：宿主不声明 `sampling` 时**不报错**，自动落到 B2 或 B3。

---

## P6 · 环境与文档（全程渐进）

### P6-1 pyproject.toml uv 化

- **前置**：无（可立即做，见 `03-uv.md`）
- **写入范围**：`pyproject.toml`、`uv.lock`、`.gitignore`
- **做**：见 `03-uv.md` 的完整设计。
- **验收**：`03-uv.md` 的四条验证命令全部通过。

### P6-2 入口注册

- **前置**：P6-1
- **写入范围**：`pyproject.toml`、`src/interfaces/cli/__main__.py`
- **做**：注册 `na` / `na-tui` / `na-mcp` / `na-tools-doctor`。`package = true`（现在 `package = false`，**没有包就没有入口点**）。
- **验收**：`uv run na --help` 可用；`uv run`（无参）列出入口。

### P6-3 na-tools-doctor

- **前置**：P6-2
- **写入范围**：`src/interfaces/doctor.py`（新建）
- **做**：检查 Python 版本、已装 extras、API Key、数据目录、模型配置。
- **验收**：任何"跑不起来"的问题，doctor 能给出**可操作的**结论。

### P6-4 文档归位

- **前置**：无
- **写入范围**：根目录 `.md`、`docs/`
- **做**：
  - `HANDOVER.md` → `docs/legacy/handover.md`（**已严重过期**，标注为历史）
  - `CODE_REVIEW.md` → `docs/legacy/code-review-2026-09.md`（**仍是珍贵的缺陷台账**，P4 要用）
  - `TARGET-ARCHITECTURE.md` / `TECH-STACK-SELECTION.md` / `MAF-MIGRATION-PLAN.md` / `MCP-ARCHITECTURE.md` → `docs/design/`
  - 新增 `README.md`（人读）
- **验收**：根目录只剩 `AGENTS.md` `README.md` `pyproject.toml` `uv.lock` `.gitignore` `.env.example` + 目录

### P6-5 CI

- **前置**：P6-1
- **写入范围**：`.github/workflows/ci.yml`（新建）
- **做**：`uv sync --extra ai` → `ruff` → `mypy` → `pytest`。
- **验收**：CI 里**没有** `--extra gpu`（重型依赖不进 CI）。
