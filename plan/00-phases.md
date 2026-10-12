# 00 — 阶段定义

每阶段的**目标 / 前置 / 产出 / 退出条件**。任务级分解见 `01-tasks.md`。

---

## P0 · 止血：契约收口

**目标**：消除"假成功"。让失败能被机器看见。

**为什么第一**：这是唯一一类**用户此刻正在被欺骗**的问题——CLI 打印"写作完成（0 字）并已保存"而文件根本没落盘（`chapter_writer.py:86-88` 空响应直接 return，不写盘）。

**前置**：无。

**要解决的 4 个具体缺陷**：

| # | 缺陷 | 位置 |
|---|---|---|
| 1 | 空输出打印成功 + exit 0 | `cli/novel_commands.py` 的 `cmd_write` / `cmd_auto` / `cmd_characters` / `cmd_plot` |
| 2 | 4 处内联编排绕过 `NovelService`（丢护栏） | 同上 |
| 3 | `cmd_characters` 覆盖 `characters.json` 不备份 | `novel_commands.py:206-238` |
| 4 | 测试靠护栏生效才不联网（会烧钱） | `tests/test_tui.py:264-277` |

**产出**：
- CLI 全部改调 `NovelService`
- 空输出 → 非 0 退出
- 一条契约测试：断言 `tier` 真的传到 `design_characters` / `design_chapter_plot`

**退出条件**：`uv run na novel write <项目> --chapter N` 在模型返回空时 **exit ≠ 0**，且 `characters.json` 有 `.bak` 副本。

**不做**：不引入任何新依赖；不抽工具层。

---

## P1 · 模型层：领域模型改 pydantic

**目标**：让领域数据模型能直接当 Pydantic AI 的 `output_type`。

**为什么**：`CharacterProfile` / `ChapterEvent` / `PersonalityShift` 现在是 **dataclass**，`output_type` 虽接受但**校验能力弱**（无 `field_validator`）。项目已手写了 `_to_int_0_10` / `_as_str` / `_as_dict` 一整套防御式转换——改 `field_validator` 是**同一件事的更规范写法**。

**前置**：P0。

**可并行**：是，按模块拆分（角色 / 剧情 / 项目）。

**产出**：
- 三个 dataclass → pydantic `BaseModel`
- 手写转换函数 → `field_validator`
- `to_dict` / `from_dict` 保留为**兼容层**（存量 JSON 不迁移）

**退出条件**：
- 5 个真实项目的 `characters.json` 能读能写，**内容逐字节可比**
- `tests/novel/test_character_engine.py` 的 50 个用例全绿且**未修改断言**

**风险**：这是唯一可能破坏存量数据的阶段。**必须先做读写往返验证**（见 `01-tasks.md` P1-1）。

**不做**：不改 JSON 文件格式；不做数据迁移。

---

## P2 · 工具层：唯一操作真源

**目标**：抽出 `src/tools/`，让 CLI 与 MCP 共用一个操作定义。

**为什么关键**：CLI 与 MCP 已经被迫共享**同一套 18 个操作**。分两次做会得到两套定义——**第四份抄本**。先抽工具层，两个适配器都变薄。

**前置**：P1（操作要返回 pydantic 对象）。

**产出**：
- `NovelResult[T]`：`ok: bool` + `data: T` + `summary: str` + `warnings: list[str]`
- `NovelService` 的 15 个方法改为返回 `NovelResult`
- `src/tools/` 的操作注册表（分 A 轨 / B 轨）

**为什么 `NovelResult` 是必需的**：`NovelService.Result` 现在返回 `title` + `lines: list[str]`——**人类可读的中文文本**。能给 Rich 渲染，**给不了 MCP 的 `structuredContent`**。所以工具层必须返回结构化对象，人类可读文本降级为其中一个字段。

**退出条件**：
- 全部操作返回 `NovelResult`，`data` 是 pydantic 对象
- 操作可从 Python 直接调用，**不经过 CLI 也不经过 MCP**
- A 轨操作**零 LLM 调用**（有测试断言）

**风险**：碰 `service.py` 全部 15 个方法。`tests/novel/test_novel_service.py` 的 21 个用例是安全网。

**不做**：不实现 MCP 服务器；不重写 CLI。

---

## P3 · 双适配器：CLI 与 MCP

**目标**：CLI 与 MCP 都变成薄适配器，**不含任何编排或参数校验**。

**前置**：P2。

**可并行**：是，CLI 与 MCP **完全独立**，可分两个 agent 同时做。

### P3a · CLI 适配器

从 18 个命令函数缩成 **渲染器 + 退出码映射**。

**`--json` 开关直接删掉**：它存在是因为 CLI 是唯一输出通道。有了工具层，结构化数据是默认形态，**方向反过来了**。

### P3b · MCP 适配器

- `inputSchema` 从 pydantic 模型**自动生成**
- 工具级错误置 `isError: true`（**不放协议级错误**）
- A 轨 / B 轨分流
- capability 协商（`ClientCapabilities.sampling` 是否存在）

**退出条件**：
- 同一操作经 CLI 与经 MCP 产生**结构化等价**的结果（有测试）
- CLI 里不再有任何退出码判断散落在命令里
- MCP 服务器能被真实宿主连上并调用 `project_list`

**不做**：P3b 先只出 A 轨；B 轨（生成）放 P4。

---

## P4 · LLM 层：换 Pydantic AI

**目标**：18 个 `.chat()` 调用点收敛到 `src/llm/`，删掉手写 JSON 容错。

**前置**：P2。

**可并行**：是，按调用点拆（但 `src/llm/` 本身要串行）。

**要删掉的东西**（这是本阶段最大的收益）：

| 组件 | 为什么能删 |
|---|---|
| `llm_client.py` 整个 | 被 `Agent` 替代 |
| `json_utils` 的解析部分 | `output_type` 做校验 |
| `base_agent._try_fix_truncated_json` | 框架回模型重试（**现版本括号闭合顺序写反了**） |
| `cost_tracker` | `result.usage` 替代（多了 `cache_hit_ratio`） |
| `_RateLimiter` | `max_concurrency` 替代 |

**必须先拆开的 12 处 `except`**：区分「**有意降级**」（`character_analyzer.py:130` 的规则兜底）与「**静默失败**」（其余）。**不拆就迁会把 A1 那个 bug 换个地方重新引入。**

### 附带：DeepSeek FastPath（兼容优先）

DeepSeek 有两个会静默影响正确性的行为（强 schema 只在 Responses API 可用；thinking 下拒绝强制 `tool_choice`），因此需要把决策集中到一处。

**关键约束**：FastPath 是 `src/llm/` 内的**策略**，不是第二个出口——只做模型解析 / 输出模式选择 / thinking 兼容，**不得**实现重试、预算、用量、Agent 声明。

**默认走 `compat` 模式**：Chat Completions + `json_object` + `thinking=False`，**端点、Key、模型名、`max_tokens` 全与现状一致**——即零行为变化地补上结构化输出。

**兼容性底线**（完整 8 条见 [`../docs/specs/deepseek-fastpath.md`](../docs/specs/deepseek-fastpath.md) §2）：

- `model_tier="flash"` / `"pro"` **必须继续可用**（贯穿全仓十余处的参数名）
- `deepseek_v4_flash` / `deepseek_v4_pro` 及 `*_flash` / `*_pro` 后缀键名都要能解析
- `ANALYSIS_MAX_TOKENS = 8192` 的显式覆盖**不得回退**
- `budget.max_cny_per_session` **继续写 CNY**
- `tests/test_llm_client.py` 的断言**不得为了让新代码通过而修改**

**退出条件**：
- 业务代码里**零** `import openai` / `import pydantic_ai`
- `docs/specs/contracts.md` 的三态失败语义（`ok` / `no_change` / `failed`）有显式适配
- 用 `TestModel` 能端到端跑通写作流程，**零 token 消耗**
- **`model_tier="flash"` / `"pro"` 仍可用，且 `tests/test_llm_client.py` 未修改断言即通过**

**风险（必须先做的 spike）**：
1. **`run_sync()` 与 Textual worker 线程共存**——`run_sync` 内部用 `loop.run_until_complete`，若线程已有运行中的事件循环会抛异常。**先走 CLI（纯同步、无线程池）**，绕开这个未知数。
2. **DeepSeek compat 模式**：`json_object` + `thinking=False` 是否真能让强制 `tool_choice` 生效。
3. **DeepSeek strict 模式**：Responses API 的 strict schema 是否可用；显式传 `message_history` 是否有效（该 API 无状态）。

---

## P5 · 模型无关：provider 配置化

**目标**：换供应商只改 yaml，不改代码。

**前置**：P4。

**产出**：
- `config/models.yaml`：provider 注册表（DeepSeek / Moonshot / 智谱 / Ollama / 任意 OpenAI 兼容端点），DeepSeek 段含 `fastpath:` 配置
- **新增** `--provider` / `--model`（**只在最外层入口解析**）
- `--tier` **保留为已弃用的别名**
- 三档降级：B1 宿主采样 / B2 provider 配置 / B3 交还宿主
- CNY→USD 换算集中到 `src/llm/budget.py`

**⚠️ `tier` 只在外层兼容，不扩散改造（本阶段的核心约束）**

`model_tier` 是**贯穿 10 个模块的透传参数**（实测：`character_engine` / `plot_engine` / `chapter_writer` / `base_agent` / `deep` / `lightweight` / `character_analyzer` / `requirement_agent` / `outline_agent` / `writer_agent` / 两个 `orchestrator` / `service` / `cli`）。

| 项 | 结论 |
|---|---|
| 改 10 个模块的签名 | ❌ **不改** |
| 内部 API 加 `ModelRef` 参数 | ❌ **不加** |
| `tier` 内部流动方式 | 原样透传，不转换 |
| tier→模型解析位置 | **只有一处**：`FastPath.resolve_model(tier)` |
| `--provider` / `--model` | 只在**最外层入口**解析 |

**支持「便宜档做大纲、强档写正文」本来就需要 tier 的语义，不需要新概念。**

**退出条件**：
- 代码里**零**具体模型名（`deepseek-v4-flash` 之类的字面量只出现在 yaml）
- 加一个 provider 只需编辑 yaml
- `--tier pro` **仍能真的改变模型**（不只是显示）
- `grep -rn 'model_tier="flash"' src/` **只剩 `character_analyzer` / `lightweight` 的 4 处**（那是有意固定用便宜档，属正确设计）
- **除 `plot_engine.py` 与 `service.py` 外，`model_tier` 的签名与调用点零改动**
- 不配 Key 时，若宿主支持 sampling，生成能力仍可用

---

## P6 · 环境与文档（全程渐进）

**目标**：uv 化完成、文档归位、CI。

**前置**：P0 起可渐进推进。

**产出**：
- `pyproject.toml` uv 化（见 `03-uv.md`）
- `default-groups` 设为 `[]`，**运行时环境不含 pytest/ruff**
- 根目录旧文档移入 `docs/`（`HANDOVER.md` / `CODE_REVIEW.md` / 三份设计文档）
- 新增 `README.md`（人读）
- `ruff` / `mypy` 配置进 `pyproject.toml`
- CI：`uv sync --extra ai && uv run pytest`

**退出条件**：
- 干净克隆后四条命令即可跑通（见 `03-uv.md` 的验证清单）
- `uv run --help` / `uv run na --help` 能看清所有入口
- 根目录只剩：`AGENTS.md` `README.md` `pyproject.toml` `uv.lock` `.gitignore` `.env.example` 与目录
