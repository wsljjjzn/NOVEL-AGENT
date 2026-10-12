# 架构

## 分层与依赖方向

依赖**只能向下**，不能反向，也不能跨层回跳。

```
┌─ 驱动层 ────────────────────────────────────────────────┐
│  MCP 宿主   ·   CLI (na)   ·   TUI (na-tui)              │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─ 适配器层 src/interfaces/ ──────────────────────────────┐
│  cli/  ·  tui/  ·  mcp/                                  │
│  只做：参数收集、渲染、退出码映射、协议编解码              │
│  不做：编排、校验、业务判断                               │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─ 工具层 src/tools/ ─────────────────────────────────────┐
│  操作注册表（唯一真源）· NovelResult · A/B 轨标记          │
│  只做：参数校验、调用 service、组装结果                    │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─ 编排层 src/novel/service.py ───────────────────────────┐
│  跨步骤业务规则 · 护栏（备份 / 只往后写 / 空即失败）        │
│  不调 LLM，只调 Agent 与领域原语                          │
└──────────┬──────────────────────────┬───────────────────┘
           ▼                          ▼
┌─ LLM 层 src/llm/ ────────┐  ┌─ 领域层 src/novel/* ──────┐
│  Agent 声明（唯一出口）   │  │  4 个引擎                 │
│  provider 解析           │  │  ★ 零 LLM 依赖 ★         │
│  降级三档                │  │  纯确定性                 │
└──────────┬───────────────┘  └──────────┬────────────────┘
           ▼                             ▼
      Model 实例                 data/projects/<名>/*.json
   （宿主采样 / OpenAI 兼容 / 其他）
```

## 三条不可违反的约束

### ① 领域层零 LLM 依赖

`src/novel/` 的四个引擎**不得 import 任何 LLM 相关模块**。

- **为什么**：这是架构的免疫系统。宿主 LLM 会写字，但记不住第 3 章埋了什么伏笔——**确定性部分才是本项目的核心价值**
- **怎么强制**：`ai` 是 extra（见 [plan/03-uv.md](../plan/03-uv.md)），**依赖图本身就是约束**
- **怎么验证**：`uv sync`（不装 `ai`）后领域引擎的测试必须全绿

### ② 只有一个 LLM 出口

所有 LLM 调用经过 `src/llm/`。业务代码**禁止**直接 `import openai` / `import pydantic_ai`。

- **为什么**：历史上 18 个 `.chat()` 调用点各自手写 JSON 容错，产生 **12 处不同处理方式的静默失败**（台账见 `CODE_REVIEW.md`，P6-4 会移入 `docs/legacy/`）
- **新增生成能力＝新增一个 `Agent` 声明**，不是新增一处 `client.chat()`

### ③ 操作契约唯一

所有可调用操作注册在 `src/tools/`。CLI 与 MCP **都只是适配器**。

- **为什么**：CLI 与 MCP 已被迫共享同一套 18 个操作。分两次做会得到**第四份抄本**
- **判据**：适配器里不应出现业务判断；出现即说明该逻辑该下沉到工具层

---

## 数据流

### 确定性路径（无需 LLM，无需 Key）

```
宿主/用户
  → na project list / MCP project_list
  → src/tools/novel.py::project_list
  → NovelService.list_projects()
  → data/projects/*/project.json
  → NovelResult(data=[...], summary="共 5 个项目")
  → CLI: Rich 表格 + exit 0   /   MCP: structuredContent
```

### 生成路径（三档降级）

```
宿主/用户
  → na novel write <项目> --chapter N  或  MCP generate_chapter
  → src/tools/novel.py::generate_chapter
  → NovelService.write_chapter()
      ├─ 读领域状态（纯确定性）
      ├─ 组装 prompt（build_chapter_prompt，零 LLM）
      ├─ 解析模型：B1 宿主采样 → B2 provider 配置 → B3 交还宿主
      ├─ Agent.run_sync(prompt, model=...)
      └─ 落盘 + 更新角色引擎
  → NovelResult(ok=True, data=ChapterResult(...), summary="第 N 章完成，2,847 字")
```

**B3 档（交还宿主）**：不生成，只返回拼装好的 prompt 包。**这不是降级方案，是天然可用的主路径**——任何宿主都能用，不需要 sampling 能力协商。

---

## 关键不变量

跨模块必须永远成立的事实。破坏任何一条都是 bug。

| # | 不变量 | 位置 |
|---|---|---|
| 1 | `CharacterProfile.chapter_events` **按章号有序且无重复章号** | `character_engine.upsert_event` |
| 2 | 人格值与关系强度是 **0-10 整数**，`None`/越界/非法值一律兜底 | `field_validator` |
| 3 | `characters.json` 写入是**原子**的（`os.replace`） | `character_engine.save` |
| 4 | `save` 在**每写完一章**都被调用 | `chapter_writer.write_chapter` |
| 5 | `chapter_titles` / `chapters` / `outline` 的章号**一律 int** | 三处都要归一化 |
| 6 | 空 LLM 输出**不落盘**（否则留下 0 字幽灵章节） | `chapter_writer` 空检查 |
| 7 | `characters.json` 损坏**不应让整个项目打不开** | `CharacterEngine.load` |
| 8 | 领域层不 import LLM 模块 | 全仓 |

> 第 5 条是**已知缺口**：`project_manager.py:186` 的 `outline` 章号至今未做 int 归一化，模型返回 `"chapter": "3"` 会让 `list_chapters()` 抛 `TypeError`，TUI 章节页签与 `novel show` 一起挂。见 `plan/01-tasks.md`。

---

## 存储布局

```
data/
├── projects/<项目名>/
│   ├── project.json        # 章节正文 + 大纲 + 标题 + 元数据 + 开放伏笔
│   ├── characters.json     # 角色档案（人格/关系/逐章事件）
│   └── plots.json          # 剧情设计 + 世界观
├── knowledge/
│   ├── index.csv           # 语料文件索引（制表符分隔）
│   └── *.db                # SQLite（chunks / knowledge_units / ...）
├── embeddings/             # ChromaDB（当前不存在）
└── user_uploads/           # kb learn 上传的文件
```

**路径是契约，不要改。** 5 个真实项目在 `data/projects/` 下，其中最大的一个有 **50 章 / 88,809 字**。

---

## 目录职责

| 目录 | 职责 | 允许依赖 |
|---|---|---|
| `src/interfaces/` | 适配器：CLI / TUI / MCP / doctor | tools, novel, utils |
| `src/tools/` | 操作注册表（唯一真源） | novel, llm, analysis, utils |
| `src/llm/` | LLM 出口：Agent、provider 解析、降级 | pydantic-ai（extra） |
| `src/novel/` | 领域引擎 | **仅标准库 + pydantic** |
| `src/analysis/` | 板块一：语料分析 | preprocessing, knowledge_base, llm |
| `src/knowledge_base/` | schema + 检索 | utils |
| `src/preprocessing/` | 切块 | utils |
| `src/utils/` | logger / file_utils / json_utils | 仅标准库 |
| `src/tools_scripts/` | 一次性但可复用的工具入口 | 任意 |
