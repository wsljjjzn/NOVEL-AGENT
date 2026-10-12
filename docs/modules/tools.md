# 工具层（`src/tools/`）

**唯一操作真源。** CLI 与 MCP 都只是它的适配器。

---

## 为什么这一层存在

CLI 与 MCP 已被迫共享**同一套 18 个操作**。如果分两次做，会得到两套操作定义——**第四份抄本**（本项目已有 3 份内联编排，见根目录 `CODE_REVIEW.md` §2.1）。

先抽工具层，两个适配器都变薄：

```
NovelService     跨操作业务规则（编排、护栏、成本）
       ↓
src/tools/       规范操作 —— 唯一真源
       ↓
   ┌───┴────┐
 CLI 适配器   MCP 适配器
 (Rich/exit)  (JSON Schema/isError)
```

---

## 为什么 `NovelResult` 是必需的

`NovelService` 旧返回是 `title` + `lines: list[str]`——**人类可读的中文文本**（"大纲已生成 5 章"）。

它能给 Rich 渲染，**给不了 MCP 的 `structuredContent`**。所以工具层必须返回结构化对象，人读文本降级为其中一个字段。见 [`../specs/contracts.md`](../specs/contracts.md)。

---

## A 轨 / B 轨

**A 轨（零 LLM）** —— 任何宿主都能用，无需 Key，无需 sampling。

```
project_list / project_create / project_show / project_export
chapter_read / chapter_list
character_status(project, chapter)
character_relationships(project, name)
foreshadowing_ledger(project)
plot_state(project, chapter)
build_outline_prompt(project, chapters, brief)
build_chapter_prompt(project, chapter, target_words)     ★ 关键
validate_chapter(project, chapter)
kb_list / kb_query
```

**★ `build_chapter_prompt` 是关键操作**：它返回拼装完整的写作 prompt，**不调 LLM**。它是 B3 档（交还宿主）的载体，让"宿主不支持 sampling"**从降级变成天然可用的主路径**。

**B 轨（生成）** —— 三档降级，见 [`../specs/llm.md`](../specs/llm.md)。

```
generate_outline(project, chapters, brief, provider?=None, model?=None)
design_characters(project, provider?=None, model?=None)
design_plot(project, chapter, provider?=None, model?=None)
generate_chapter(project, chapter, target_words, provider?=None, model?=None)
review_article(text, provider?=None, model?=None)
```

`provider` / `model` 缺省即"不强求"——由 `src/llm/resolve.py` 按 B1→B2→B3 自行选路。

---

## 硬约束

### ① A 轨必须零 LLM 调用

这决定了 A 轨在"宿主不支持 sampling 且无 Key"时是否可用。

**有测试断言**：LLM 被完全禁用时，所有 A 轨操作仍可调用。

### ② 参数校验在此层，不穿透

业务参数（`chapter` / `target_words` / `instructions`）在工具层校验。**呈现层参数不进工具层**：

| 参数 | 归属 | 理由 |
|---|---|---|
| `chapter` / `target_words` / `instructions` | ✅ 工具层 | 真实业务参数 |
| `provider` / `model` | ✅ 工具层 | 模型由调用方指定 |
| `--out` / `--stdout` | ❌ 仅 CLI | 呈现层 |
| `--page` / `--page-size` / `--raw` | ❌ 仅 CLI | 交互浏览，Agent 不需要分页 |
| `--json` | ❌ **删除** | MCP 天生给结构化数据，方向反了 |
| `--tier` | ❌ **废弃** | 死参数，见 [`../specs/llm.md`](../specs/llm.md) |
| `--import-file` | ⚠️ 拆 | 工具收「大纲文本」，读文件留给 CLI |

### ③ 业务失败是返回值

返回 `NovelResult(ok=False, error=...)`，**不抛异常**。见 [`../specs/contracts.md`](../specs/contracts.md) §2。

---

## 编组与命名

| 模块 | 内容 |
|---|---|
| `src/tools/result.py` | `NovelResult` + `ok/error` 校验 |
| `src/tools/registry.py` | 操作注册表 + A/B 轨标记 |
| `src/tools/novel.py` | 小说相关操作 |
| `src/tools/kb.py` | 知识库相关操作 |

注册表让 MCP 能生成 `tools/list`、CLI 能生成子命令，**都从同一处取**。

---

## 新增操作的流程

1. **先改文档**：本文件加一行到 A 轨或 B 轨清单
2. 在 `src/tools/<组>.py` 实现，返回 `NovelResult`
3. 在 `registry.py` 注册（含轨标记与参数模型）
4. 补测试：至少一条 `ok=True` 路径 + 一条 `ok=False` 路径
5. 若属 A 轨：加进"零 LLM 可用"的断言

**不要**直接改 CLI 或 MCP 来实现新能力——那正是要消灭的模式。
