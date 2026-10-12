# NOVEL-AGENT

长篇小说写作**状态引擎**。核心是确定性的——角色人格演变、关系网、伏笔台账、剧情一致性。

生成能力（写章节、审稿）是可选层：你的宿主 LLM 本来就会写，但它**记不住第 3 章埋了什么伏笔、林雪在第 20 章的人格值是多少**。

## 两种用法

### 1. 作为 MCP 服务器（主要形态）

让宿主（Claude / DSH / Cursor 等）驱动：

```bash
uv sync --extra ai
uv run na-mcp                 # stdio
uv run na-mcp --http          # Streamable HTTP
```

宿主会看到两类工具：

- **A 轨（零 LLM）**：查角色状态、查伏笔台账、`build_chapter_prompt`（把该说的都备好）
- **B 轨（生成）**：写大纲、设计角色、写章节——**模型由调用方指定**，也可走宿主自己的模型（不需要 API Key）

### 2. 作为 CLI / TUI 独立运行

```bash
uv sync --extra ai
uv run na novel list                    # 看有哪些项目
uv run na novel show <项目> --chars      # 看角色状态
uv run na novel write <项目> --chapter 5 # 写一章
uv run na-tui                           # 交互式界面
```

## 快速开始

```bash
git clone <repo> && cd NOVEL-AGENT
uv sync --extra ai            # 装核心 + LLM 层
cp .env.example .env          # 填 DEEPSEEK_API_KEY（走宿主采样时不需要）
uv run na-tools-doctor        # 环境自检
uv run na novel list
```

**跑不起来先跑 doctor**：

```bash
uv run na-tools-doctor
```

## 环境分层

本项目**只用 uv**，依赖分三层按需装：

| 命令 | 内容 | 体积 |
|---|---|---|
| `uv sync` | 核心（CLI / TUI / MCP / 领域引擎） | 小 |
| `uv sync --extra ai` | + LLM 调用层（Pydantic AI、MCP SDK） | 中 |
| `uv sync --extra gpu` | + 语料预处理（torch 系） | 数 GB |

开发还要加组：

```bash
uv sync --extra ai --group dev --group lint
uv run pytest
uv run ruff check . && uv run mypy src
```

> **领域引擎零 LLM 依赖**——不装 `--extra ai` 也能用角色/剧情/项目管理。这是刻意设计的：`ai` 是 extra，**依赖图本身就是架构约束**。

## 命令一览

| 命令 | 用途 |
|---|---|
| `uv run na` | 主 CLI（`novel` / `article` / `kb` 三组） |
| `uv run na-tui` | 交互式终端界面 |
| `uv run na-mcp` | MCP 服务器 |
| `uv run na-tools-doctor` | 环境自检 |
| `uv run na-tools-preprocess` | 批量语料预处理 |
| `uv run na-tools-index` | 重建 `index.csv` |

```bash
uv run na --help          # 全部子命令
uv run                    # 列出所有入口
```

## 数据

```
data/projects/<项目名>/
├── project.json        # 章节正文 + 大纲 + 标题 + 开放伏笔
├── characters.json     # 角色档案（人格 / 关系 / 逐章事件）
└── plots.json          # 剧情设计 + 世界观
```

## 文档

| 想了解 | 看 |
|---|---|
| 架构分层与约束 | [`docs/architecture.md`](docs/architecture.md) |
| 失败语义与返回值契约 | [`docs/specs/contracts.md`](docs/specs/contracts.md) |
| LLM 层与模型无关设计 | [`docs/specs/llm.md`](docs/specs/llm.md) |
| 各模块细节与已知陷阱 | [`docs/modules/`](docs/modules/) |
| 设计决策记录 | [`docs/design/`](docs/design/) |
| 历史缺陷台账 | `CODE_REVIEW.md`（P6-4 会移入 `docs/legacy/`） |

## 给贡献者与 AI agent

- **cooding agent 请先读 [`AGENTS.md`](AGENTS.md)**，里面有环境、测试、风格与三条不可违反的架构约束
- 计划与任务分解在 [`plan/`](plan/)——**开工前确认你要做的事属于哪个阶段**
- **文档先行**：行为变更先改 `docs/`，再改代码

## 当前状态

项目正在进行架构迁移（MCP 服务器 + 模型无关 LLM 层）。进度见 [`plan/README.md`](plan/README.md)。

已知未完成项（不要以为已经修好）：

- `outline` 章号未做 int 归一化（`project_manager.py:186`）
- `project.json` / `plots.json` 非原子写（`characters.json` 已是）
- `user_notes` 是假功能——不会被注入 prompt（`plot_engine.py:62-91`）
- `--tier` 是三处死参数（`plot_engine.py:187,239`、`kb_commands.py:230`）

## License

私有项目。
