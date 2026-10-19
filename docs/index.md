# docs/ — 技术文档

**文档先行**：行为变更先改这里，再改代码。流程见 [`../plan/02-workflow.md`](../plan/02-workflow.md)。

## 索引

| 文档 | 内容 | 什么时候读 |
|---|---|---|
| [`architecture.md`](architecture.md) | 分层、依赖方向、三条架构约束 | **开工前必读** |
| [`specs/contracts.md`](specs/contracts.md) | 失败语义、`NovelResult`、MCP 错误语义 | 改动任何返回值前 |
| [`specs/llm.md`](specs/llm.md) | Agent 声明、模型解析、降级三档 | 改动生成能力前 |
| [`specs/deepseek-fastpath.md`](specs/deepseek-fastpath.md) | **DeepSeek fastpath 与兼容性底线** | **动 LLM 层或模型参数前必读** |
| [`modules/character_engine.md`](modules/character_engine.md) | 角色人格/关系/逐章事件 | 改角色相关 |
| [`modules/plot_engine.md`](modules/plot_engine.md) | 剧情设计、世界观 | 改剧情相关 |
| [`modules/project_manager.md`](modules/project_manager.md) | 项目持久化、原子写、章号归一化 | 改文件读写 |
| [`modules/review_engine.md`](modules/review_engine.md) | 六维审稿、三级修改、失败语义、作品状态注入 | 改审稿相关 |
| [`modules/tools.md`](modules/tools.md) | 操作注册表、A/B 轨 | 新增操作 |
| [`modules/mcp_server.md`](modules/mcp_server.md) | MCP 原语、capability 协商 | 改 MCP 接口 |

## 子目录

- **`specs/`** — 跨模块的契约。改动影响面大，**必须文档先行**。
- **`modules/`** — 单模块说明。改哪个读哪个。
- **`design/`** — 设计决策记录（P6-4 归位）：架构关系图、底座选型、MCP 方案、MAF 评估。
- **`legacy/`** — 过期但仍有参考价值的：`handover.md`（已严重过期）、`code-review-2026-09.md`（**缺陷台账，P4 会用到**）。

## 写模块文档的最小要求

每个 `modules/*.md` 至少回答四个问题：

1. **它负责什么** —— 一句话边界，含**明确不做什么**
2. **对外接口** —— 公开类与函数签名
3. **不变量** —— 什么必须永远成立（例：`chapter_events` 按章号有序且不重复）
4. **已知陷阱** —— 踩过的坑，附 `file:line`

第 3、4 条是本项目文档的重点。**历史缺陷几乎全部来自"不变量没人写下来"**——例如 `chapter_events` 可以重复、`outline` 章号没归一化、`relationship_changes` 落盘即丢。
