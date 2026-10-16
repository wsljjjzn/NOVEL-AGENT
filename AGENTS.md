# AGENTS.md

写作专家系统的 agent 工作指南。本项目是 **MCP 服务器 + 模型无关的 LLM 调用层 + 纯确定性领域引擎**。

> 本文件是给 coding agent 的 README。人读的概览在 [`README.md`](README.md)。
> 计划与任务分解在 [`plan/`](plan/)。模块说明在 [`docs/`](docs/)。
> **文档先行**：任何模块的行为变更，先改 `docs/`，再改代码。

---

## 项目是什么

一个长篇小说写作状态引擎。核心价值是**确定性**的——角色人格演变、关系网、伏笔台账、剧情一致性。生成能力（写章节、审稿）是可选层，因为宿主 LLM 本来就会写，但它记不住第 3 章埋了什么伏笔。

**两种用法**：

1. **作为 MCP 服务器**被宿主调用（Claude / DSH / Cursor 等）——主要形态
2. **作为 CLI / TUI** 独立运行——同一套能力的本地驱动

---

## 环境准备（uv）

本项目**只用 uv**。不要用 pip / conda / poetry / 手建 venv。

```bash
uv sync                    # ① 核心：CLI + TUI + MCP + 领域引擎（不含开发工具）
uv run na --help           # 验证
```

**开发与运行是分开的**：`pyproject.toml` 设了 `default-groups = []`，所以 `uv sync` **不会**装 pytest/ruff。
需要开发工具时显式加组：

```bash
uv sync --group dev --group lint --extra ai     # 完整开发环境
uv run pytest
```

> 判断是否分离成功：`uv sync` 后 `uv run python -c "import pytest"` **应当报错**。

**分阶段装可选依赖**（不要一次装全，重型依赖数 GB）：

```bash
uv sync --group dev --extra ai              # ② 开发 + LLM 调用层（常用）
uv sync --extra gpu                         # ③ 语料预处理（torch 系，数 GB）
uv sync --group dev --extra ai --extra gpu  # 全量
```

> ⚠️ `ai` / `gpu` extra 尚未落地；但 `dev`（pytest）与 `lint`（ruff / mypy）依赖组已经可用。
> `test` extra 仍保留，兼容已有命令。当前可用写法：
>
> ```bash
> uv sync --group dev --group lint  # 核心 + 测试与静态检查
> uv sync --extra test              # 兼容写法：核心 + pytest
> uv sync --extra full    # 语料预处理那一大坨（数 GB）
> ```
>
> `ai` / `gpu` 的分层仍属 [`plan/03-uv.md`](plan/03-uv.md) 的后续范围。

### 可调用的命令

`uv run` 会补全以下入口。**不要新增临时脚本，把能力注册成入口。**

| 命令 | 用途 | 当前可用 |
|---|---|---|
| `uv run na` | 主 CLI（novel / article / kb 三组） | ✅ |
| `uv run na-tui` | 交互式终端界面（Textual） | ✅ |
| `uv run na-tools-preprocess` | 批量语料预处理 | ✅ |
| `uv run na-tools-index` | 重建 `index.csv` | ❌ 未实现 |
| `uv run na-tools-doctor` | 环境自检（Python 版本、依赖、Key、数据目录） | ❌ 未实现 |
| `uv run na-mcp` / `na-mcp --http` | MCP 服务器（stdio / Streamable HTTP） | ❌ 未实现（属 plan P3b） |

> 前三条由 `[project.scripts]` 注册，实现在 [`src/cli/entrypoints.py`](src/cli/entrypoints.py)：
> 先把工作目录切到仓库根再委派，因此与"在仓库根跑 `python tui.py`"行为一致
> （数据/日志/语料都是相对仓库根的路径）。
> **未实现的那几条现在跑会报 `Failed to spawn`**，排期见 [`plan/00-phases.md`](plan/00-phases.md)。

**验证优先用 doctor**（⏳ 未实现；先跑这两条）：

```bash
uv run na novel list          # 能列出项目 = 数据目录 + 核心依赖都正常
uv run python -c "import src.cli.main, src.tui.app; print('核心依赖 OK')"
```

---

## 测试

```bash
uv run pytest                              # 全量（离线，不花钱）
uv run pytest tests/novel -q               # 只跑领域引擎
uv run pytest -k character -q              # 按名字筛
```

**硬规则：测试永不发起真实 LLM 调用。**

- 测试统一使用 Pydantic AI 的 `TestModel` 或显式注入 fake，**不要**靠"本机没配 Key"来保证离线
- 涉及 LLM 的用例必须 `agent.override(model=TestModel())`，见 [`docs/specs/contracts.md`](docs/specs/contracts.md)
- 提交前 `uv run pytest` 必须全绿

---

## 代码风格

```bash
uv run ruff check --fix .
uv run ruff format .
uv run mypy src
```

- **行宽 100**，4 空格缩进
- **注释与文档字符串用中文**（项目既有惯例），**标识符用英文**
- 注释解释**为什么**，不复述**做了什么**
- 不用 `from x import *`

### 三条不可违反的架构约束

违反这三条的改动会被打回，它们比风格重要得多：

**① 领域层零 LLM 依赖。**
`src/novel/*` 的四个引擎（`character_engine` / `plot_engine` / `project_manager` / `chapter_writer` 的 prompt 拼装部分）**不得 import 任何 LLM 相关模块**。它们必须是纯确定性的。这是整个架构的免疫系统，也是迁移风险的隔离带。

**② 只有一个 LLM 出口。**
所有 LLM 调用经过 `src/llm/`。**禁止**在业务代码里直接 import `openai`、`pydantic_ai` 或写 HTTP 请求。新增生成能力＝新增一个 `Agent` 声明，不是新增一处 `client.chat()`。

**③ 操作契约唯一。**
所有可调用操作注册在 `src/tools/`。CLI 和 MCP 都只是**适配器**，不得自己实现编排或参数校验。

---

## 失败语义（最容易写错的地方）

**"假成功"是本项目的历史顽疾**，有三条硬规则：

**① 工具层返回 `ok: bool`，不抛异常表示业务失败。**

```python
# ✅ 业务失败是返回值
return NovelResult(ok=False, summary="模型返回空文本，本次调用仍会计费")

# ❌ 不要用异常表达业务失败
raise RuntimeError("模型返回空文本")
```

**② CLI 退出码由适配器统一映射，不在每个命令里各写一遍。**

```python
# src/interfaces/cli.py —— 只有这一处
return 0 if result.ok else 1
```

**③ MCP 工具级错误必须放在结果里，并置 `isError: true`。**

MCP 规范原文：否则 *"the LLM would not be able to see that an error occurred and self-correct"*。**不要**用协议级错误响应表达工具失败——那会让宿主看不见错误。

详见 [`docs/specs/contracts.md`](docs/specs/contracts.md)。

---

## 模型无关（不要硬编码模型）

**禁止**在代码里出现具体模型名。模型由调用方指定：

```python
# ✅ 构造时不绑定模型
agent = Agent(output_type=CharacterProfile)

# ✅ 运行时注入：宿主采样 / OpenAI 兼容端点 / 其它
agent.run_sync(prompt, model=resolve_model(ctx))
```

供应商配置是**纯数据**（`config/models.yaml`），换供应商只改 yaml，不改代码。

### DeepSeek 快速路径

DeepSeek 有两个会**静默影响正确性**的行为，因此有独立的 fastpath：强 JSON Schema 只在 Responses API 可用；V4 默认开 thinking 且 thinking 下拒绝强制 `tool_choice`（**足以耗尽重试预算**）。

**FastPath 是 `src/llm/` 内的一个策略，不是第二个出口。** 它只做三件事：模型解析、结构化输出模式选择、thinking 与 tool_choice 兼容。**不得**在里面实现重试、预算、用量记录或 Agent 声明。

详见 [`docs/specs/deepseek-fastpath.md`](docs/specs/deepseek-fastpath.md)。

### 兼容性底线（改这块前必读）

以下是**既有契约**，不得破坏：

| 契约 | 说明 |
|---|---|
| `model_tier="flash"` / `"pro"` | **贯穿 10 个模块的透传参数，必须继续可用**。`--tier` 是**保留的别名**，不是被替换掉的旧参数 |
| 配置键 `deepseek_v4_flash` / `deepseek_v4_pro` | 以及 `flash` / `pro` 简写、任意 `*_flash` / `*_pro` 后缀，都要能解析 |
| `DEEPSEEK_API_KEY` | 一个 Key 覆盖两个档位 |
| `max_tokens` 4096(flash) / 8192(pro) | 且 `character_engine.ANALYSIS_MAX_TOKENS = 8192` 的**显式覆盖不得回退**——4096 会截断角色 JSON，那是 A1 事故的成因 |
| `budget.max_cny_per_session` | 配置**继续写 CNY**（框架的 `cost_limit` 是 USD，换算集中在 `src/llm/budget.py`） |
| `tests/test_llm_client.py` 的断言 | **不得为了让新代码通过而修改** |

### ⚠️ tier 不向外扩散

**`tier` 在内部当不透明字符串透传。** `model_tier` 参数在 10 个模块里保持原样。

- ❌ **不要**为了支持 `--provider` / `--model` 去改这些模块的签名
- ❌ **不要**在内部 API 上加 `ModelRef` 之类的参数
- ✅ `--provider` / `--model` 只在**最外层入口**做参数解析，就地转成 tier 或模型
- ✅ tier→实际模型的解析**只有一处**：`FastPath.resolve_model(tier)`

支持「便宜档做大纲、强档写正文」不需要新概念——**那天然就是 tier 的语义**。

---

## 数据与成本

**数据布局**（不要改动路径约定）：

```
data/projects/<项目名>/{project,characters,plots}.json
data/knowledge/index.csv
data/knowledge/*.db
```

**成本**：

- 预算上限单位是 **USD**（`UsageLimits(cost_limit=...)`），配置里写 CNY 时要换汇率
- `RunUsage.cost` 为 `None` 表示**无法定价**，不是零成本——不要把它当 0 处理
- 任何会产生费用的操作，先在 CLI 确认、在 MCP 返回预估

**不要提交**：`data/` 下的大文件、`logs/`、`.env`、任何 Key。

---

## 提交前检查表

```bash
uv run ruff format . && uv run ruff check --fix .
uv run mypy src
uv run pytest                              # 必须全绿且不联网
```

- [ ] 测试通过，且**没有发起真实 LLM 调用**
- [ ] 涉及行为的改动已先更新 `docs/`
- [ ] 没有引入具体模型名
- [ ] 没有在业务代码里直接 import LLM 库
- [ ] 新能力注册成了 `src/tools/` 的操作，而不是散落的函数
- [ ] 提交信息遵循 Conventional Commits（中文描述）

---

## 提交信息格式

```
<type>(<scope>): <中文描述>
```

`type`：`feat` / `fix` / `refactor` / `docs` / `test` / `chore`
`scope`：`novel` / `llm` / `tools` / `cli` / `mcp` / `analysis` / `docs`

示例：

```
feat(tools): 抽出 NovelTool 层，CLI 与 MCP 共用操作契约
fix(llm): 结构化输出校验失败时回模型重试，不再静默返回空
docs(novel): 补充角色引擎的人格归一化说明
```

---

## 遇到不确定时

1. 先读 [`docs/architecture.md`](docs/architecture.md) 理解分层，再读对应模块文档
2. 先读 [`plan/`](plan/) 确认这件事属于哪个阶段——**不要做计划外的事**
3. 计划里没有的改动，先问，不要自行扩大范围
