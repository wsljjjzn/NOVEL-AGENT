# NOVEL-AGENT

长篇小说写作**状态引擎**。

核心价值在于**确定性**——角色人格演变、动态关系网、伏笔闭环台账与长线剧情一致性。
生成能力（写章节、六维审稿）是可选层：大语言模型天然善于文字生成，但**记不住第 3 章埋下的伏笔，也无法精准把控角色在第 20 章的心态演变**。NOVEL-AGENT 即为解决这一断代记忆问题而设计。

---

## 快速上手与环境准备

本项目采用现代 Python 包管理工具 **`uv`**，无需繁琐配置 Python 虚拟环境。

### 1. 安装 `uv`（若已安装可跳过）

- **macOS / Linux**：
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # 或使用 Homebrew: brew install uv
  ```
- **Windows (PowerShell)**：
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

### 2. 克隆项目与配置 API Key

```bash
git clone https://github.com/wsljjjzn/NOVEL-AGENT.git
cd NOVEL-AGENT

# 配置 DeepSeek Key（用于正文生成与六维审稿，纯浏览/编辑本地大纲可跳过）
cp .env.example .env
```
编辑 `.env` 文件填入您的 API Key：
```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```
*(注：一个 Key 同时覆盖 `flash` 廉价大纲档与 `pro` 强力写作档)*

---

## 三大交互形态使用教程

系统提供 **Web 写作 IDE**、**TUI 终端交互面板** 与 **CLI 命令行** 三套界面，数据与逻辑全链路打通。

```
              ┌──────────────────────────────────────────────────┐
              │           Novel Engine (纯确定性领域内核)           │
              └────────────────────────┬─────────────────────────┘
                                       │
     ┌─────────────────────────────────┼─────────────────────────────────┐
     ▼                                 ▼                                 ▼
【Web IDE 版】                  【TUI 终端版】                     【CLI 命令版】
现代写作视效/企划构思/排版居中      全键盘驱动/就地对比审稿            脚本自动化/批量调度
`uv run na-studio`             `uv run na-tui`                  `uv run na novel ...`
```

---

### 一、Web 版：Novel Studio 现代写作 IDE（推荐）

集成了复古单色 CRT 终端动效、全功能写作排版、多重视角联动与六维智能审稿的一体化 Web 工作台。

#### 1. 安装与启动

```bash
# 1. 安装 Web 扩展依赖（仅需一次）
uv sync --extra web

# 2. 一键启动服务（控制台自检后将自动弹出浏览器）
uv run na-studio
```
启动后自动访问本地服务：**http://127.0.0.1:8000**

> **进阶提示**：
> - 自定义端口：`uv run uvicorn src.api.server:app --port 8080 --reload`
> - **纯前端单文件离线预览**：无需启动 Python 后端，直接双击打开 [`web_prototype/index.html`](web_prototype/index.html)，开箱即用，所有设定与编辑内容基于本地浏览器持久化。

#### 2. 界面核心功能指南

- **企划构思视角 (Planning Perspective)**：
  - **默认首页直达**：首屏清晰纵览书名、题材、篇幅统计及整体大纲设定。
  - **分卷与章节目录**：左侧树状层级查看已写/待写章节、字数与概要。
  - **出场角色时间切片**：选中章节时，自动过滤展示在本章登场的角色及其当前性格五维雷达图。
  - **伏笔闭环台账**：实时跟踪待回收与已回收伏笔，点击可双向定位至相关章节。
- **沉浸写作视角 (Writing Perspective)**：
  - **自由伸缩工作区**：鼠标拖拽中缝分割条，自由微调左右分栏宽度。
  - **打字机居中模式**：输入时光标垂直平滑锁定在屏幕正中，杜绝长时间低头视线疲劳。
  - **文学排版定制**：字号（15~21px）、行距（1.6~2.1倍）、衬线宋体/楷体/黑体一键切换。
- **六维审稿与就地改写**：
  - 点击「六维审稿」，对当前章节进行**文笔修辞、剧情张力、伏笔闭环、角色一致性、世界观自洽、节奏把控**综合诊断。
  - 展开审稿条目查看修改建议，支持勾选关键锚点一键写回项目正文。
- **系统设置与导出备份 (Settings)**：
  - **四套终端配色**：黑客翠绿 (Emerald)、琥珀金黄 (Amber)、赛博青蓝 (Cyan)、极简黑白 (B&W)。
  - **视效滤镜**：CRT 阴极射线管扫描线、暗角失真滤镜与开屏自检动画开关。
  - **一键导出**：支持导出全书规范缩进 TXT、导出全案 Markdown、下载三位一体 JSON 备份包。

---

### 二、TUI 版：交互式终端写作界面

基于 Textual 框架打造的纯键盘驱动交互界面，适合服务器无头环境（SSH）或重度键盘流作者。

#### 1. 安装与启动

```bash
# 核心依赖即可运行
uv sync
uv run na-tui
```

#### 2. 常用操作快捷键

| 快捷键 | 作用说明 |
|---|---|
| `1` ~ `4` / `Tab` | 切换面板：**项目大纲**、**角色图谱**、**剧情编排**、**六维审稿** |
| `n` | 新建项目或新建后续章节 |
| `w` | 一键调用模型撰写选中章节正文 |
| `v` | 对当前章节发起六维智能审稿 |
| `Enter` | 在审稿面板中查看问题详情，对比 Diff 并确认就地采纳修改 |
| `s` | 查看当前 LLM 档位配置、API 连通性与本会话累计费用（¥ CNY） |
| `q` | 退出 TUI 界面 |

---

### 三、CLI 版：命令行自动化工具

适合批量批处理、CI 自动化集成或管道脚本调用。

#### 1. 安装

```bash
uv sync
```

#### 2. 命令语法与典型用例

统一通过 `uv run na <子模块>` 调用：

##### ① 小说管理与创作 (`na novel`)

```bash
# 查看项目列表与全局统计
uv run na novel list

# 创建新书项目
uv run na novel create "修仙长生劫" --genre "古典仙侠" --desc "穿越修仙界，从炼气期苟起"

# 查看项目角色状态与人格数值
uv run na novel show "修仙长生劫" --chars

# 查看伏笔台账与剧情规划
uv run na novel show "修仙长生劫" --plots

# 撰写单章（指定章号、目标字数与模型档位）
uv run na novel write "修仙长生劫" --chapter 1 --words 3000 --tier pro

# 批量连续续写（从首个未写章节开始往后写 3 章）
uv run na novel auto "修仙长生劫" --count 3 --tier pro

# 单章六维智能审稿并自动写回 Level 1 机械修改
uv run na novel review "修仙长生劫" --chapter 1 --tier pro --apply

# 导出全书正文为整本 TXT
uv run na novel export "修仙长生劫" --out ./dist/book.txt
```

##### ② 语料文献与写作知识库 (`na kb` / 预处理)

```bash
# 检索小说写作手法与设定知识
uv run na kb search "环境烘托与情绪压抑" --top-k 5

# 语料批量预处理与清洗（需要 --extra full）
uv run na-tools-preprocess
```

---

## 依赖管理与开发测试

`pyproject.toml` 实施了严格的**按需分层**设计，开发工具与核心运行依赖互相解耦：

| 同步命令 | 包含组件 | 适用场景 |
|---|---|---|
| `uv sync` | CLI + TUI + 纯确定性领域引擎 | 极简终端运行，体积小 |
| `uv sync --extra web` | + FastAPI + Uvicorn | 运行 Web 版 Novel Studio |
| `uv sync --group dev --group lint --extra web` | + Pytest + Ruff + Mypy + Web | 完整开发、提交门禁自检 |
| `uv sync --extra full` | + ChromaDB + Torch 系语料检索（数 GB） | 深度语料知识库向量处理 |

### 质量门禁与测试运行

本项目遵循**离线自测原则**，所有单元测试均使用 Mock/Fake 测试桩，绝不发起真实计费调用：

```bash
# 运行全量 360+ 项离线单元测试
uv run pytest -q

# 执行静态代码检查与类型检查
uv run ruff check .
uv run mypy src
```

---

## 项目数据布局

所有小说创作产物均保存在本地透明的 JSON 文件中，格式规范、可直接纳管或备份：

```
data/projects/<项目名>/
├── project.json        # 章节正文、分卷大纲、章节标题与开放伏笔
├── characters.json     # 角色档案库（大五人格数值、动态关系网、逐章出场事件）
└── plots.json          # 剧情节点、悬念钩子、开篇高潮规划与世界观
```

---

## 架构原则与设计底线

1. **领域内核零 LLM 依赖**：`src/novel/*` 下的角色、剧情与状态引擎均为纯确定性算法，无任何外部大模型硬编码。
2. **唯一出口与模型无关**：所有生成能力均收敛于 `src/llm/` 与统一的 `NovelTool` 契约，支持动态无缝替换供应商端点。
3. **失败语义明确**：工具层统一返回包含失败原因的结构化结果（`Result(ok=False, ...)`），严防“假成功”吞噬真实异常。

---

## 参与贡献与开发规范

- 编码前请详细阅读 [**`AGENTS.md`**](AGENTS.md) 了解代码规范与不可违反的架构约束。
- 演进路线与分期拆解请参阅 [**`plan/`**](plan/) 目录。
- 提交代码请遵循约定式提交规范：`feat(...)` / `fix(...)` / `refactor(...)`。
