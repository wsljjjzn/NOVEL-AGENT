# 契约：失败语义与返回值

**本文件是本项目最重要的规范。** 三条硬规则来自一个真实教训：**"假成功"是历史顽疾**。

---

## 1. 为什么需要这份规范

历史缺陷全部是同一形状——**界面承诺与代码行为偏离，且偏离是静默的**：

| 界面说 | 代码做 | 位置 |
|---|---|---|
| "正在用 pro 生成角色系统" | 硬编码 `flash` | `plot_engine.py:239` |
| "第 N 章写作完成（0 字）**并已保存**" | 空响应**根本不落盘** | `novel_commands.py:341` + `chapter_writer.py:86-88` |
| "剧情笔记写作时会注入 prompt" | `to_prompt_text()` 不输出 `user_notes` | `plot_engine.py:62-91` |
| "已加载风格模板 / 知识库检索" | 结果写进 `raw_input`，**无 prompt 读取该字段** | `orchestrator.py:64-67` |
| "深度分析模型层级 --tier" | `cmd_learn` 从不读 `args.tier` | `kb_commands.py:230` |

**共同根因**：失败与成功返回同一个值，上层无法区分。规范的目的就是让这件事**在类型上不可能**。

---

## 2. 规则一：业务失败是返回值，不是异常

```python
# ✅ 正确
return NovelResult(ok=False, error="模型返回空文本", summary="第 3 章未生成")
```

```python
# ❌ 错误：用异常表达业务失败
raise RuntimeError("模型返回空文本")
```

**异常**只用于**意外错误**：编程错误（`TypeError`）、不可能状态、外部库的意外抛错。

**判据**：如果你能写出"遇到这种情况该怎么办"，那它就是业务失败，应该是返回值。

---

## 3. `NovelResult`：唯一的返回形状

```python
class NovelResult[T](BaseModel):
    ok: bool
    data: T | None = None          # 结构化结果，给 MCP / 测试 / 下游
    summary: str = ""              # 人类可读，给 CLI/TUI 渲染
    warnings: list[str] = []       # 成功但有隐患（例：与目标字数偏差 30%）
    error: str = ""                # ok=False 时必填
```

### 三个字段各自的用途

| 字段 | 给谁 | 为什么不能合并 |
|---|---|---|
| `data` | MCP 的 `structuredContent`、下游代码、测试断言 | **结构化是默认形态**。旧设计只有 `lines: list[str]`，MCP 拿不到可编程的数据 |
| `summary` | CLI/TUI 渲染 | 人读文本无法被程序消费，但它仍需要一个位置 |
| `warnings` | 界面提示 | **成功但有隐患**是最容易被丢掉的一类信息 |

### 校验规则

```python
@model_validator(mode="after")
def _check(self):
    if not self.ok and not self.error:
        raise ValueError("ok=False 时必须给出 error")
    if self.ok and self.error:
        raise ValueError("ok=True 时不应有 error")
    return self
```

---

## 4. 规则二：三态失败语义必须显式区分

**这是最容易做错的地方。** Pydantic AI 是**两态**（拿到校验过的实例，或抛异常），而本项目需要**三态**：

| 状态 | 含义 | 判定方式 | 上层该做什么 |
|---|---|---|---|
| `ok` | 模型产出有效结果 | `output_type` 校验通过，且**内容非空** | 正常落盘 |
| `no_change` | 模型**确实报告"没有变化"** | 校验通过，但内容为空（如 `characters: []`） | **正常成功**，不落盘，不告警 |
| `failed` | 基础设施或解析失败 | 异常 / 校验失败 | **必须报错**，且告知"本次调用仍会计费" |

**为什么必须分开**：把 `no_change` 和 `failed` 混为一谈，就是 A1 那个 bug——"角色分析完成: 0 个角色更新"在模型真的没变化时是对的，在解析失败时是**撒谎**。

### 实现要求

```python
# ❌ 错误：三态塌成两态
try:
    result = await agent.run(prompt, model=m)
    return result.output
except Exception:
    return []          # ← no_change 与 failed 混在一起
```

```python
# ✅ 正确
try:
    result = await agent.run(prompt, model=m)
except UnexpectedModelBehavior as e:
    return NovelResult(ok=False, error=f"结构化输出校验失败：{e}",
                       summary="角色状态未更新（本次调用仍会计费）")
except Exception as e:
    return NovelResult(ok=False, error=f"{type(e).__name__}: {e}",
                       summary="角色分析调用失败，角色状态未更新")

if not result.output.characters:
    return NovelResult(ok=True, data=AnalysisOutcome(no_change=True),
                       summary="第 3 章无角色状态变化")
return NovelResult(ok=True, data=AnalysisOutcome(...))
```

### ⚠️ 有意降级要标注

`character_analyzer.py:130` 的 `_rule_based_extract` 是**有意降级**（LLM 失败时退回规则提取），**与静默失败不同**。这类分支必须：

1. 保留降级能力
2. **显式标注**：`warnings=["已降级为规则提取，质量可能下降"]`
3. 在文档里写明这是设计选择，不是遗漏

**12 处 `except` 的逐条归类是 P4-1 的任务**，见 [`../../plan/01-tasks.md`](../../plan/01-tasks.md)。

---

## 5. 规则三：错误呈现由适配器统一映射

### CLI

```python
# src/interfaces/cli/main.py —— 只有这一处
def run_command(operation, args) -> int:
    result = operation(**args)
    render(result)                          # 渲染 summary / warnings / data
    return 0 if result.ok else 1
```

**命令函数里不得出现 `return 1`。** 现在 `cmd_write` / `cmd_auto` / `cmd_characters` / `cmd_plot` 各自判断（且有的漏了），**统一到适配器后，四条假成功同时消失**。

### MCP

```python
# src/interfaces/mcp/server.py —— 只有这一处
def to_call_tool_result(result: NovelResult) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=result.summary)],
        structuredContent=result.data.model_dump() if result.data else None,
        isError=not result.ok,          # ← 关键
    )
```

### ⚠️ MCP 错误语义是硬要求

MCP 规范原文：

> Any errors that originate from the tool SHOULD be reported inside the result object, with `isError` set to true, **not** as an MCP protocol-level error response. Otherwise, the LLM would not be able to see that an error occurred and self-correct.

**违反这条的后果比 CLI 更严重**：宿主看不见错误，会以为调用成功了。**"假成功"在新架构下会更难被发现。**

| 情况 | 用哪个 |
|---|---|
| 业务失败（模型返回空、参数不合法、项目不存在） | 结果内 `isError: true` |
| 协议级异常（工具名不存在、服务器内部崩溃） | 协议级错误响应 |

---

## 6. 结构化输出校验失败时怎么办

Pydantic AI 的行为：**把校验错误连同 schema 回给模型重试**。这是 A1 的结构性解药——以前"截断了就认命"，现在"截断了就让模型补"。

**配置要求**：

```python
agent = Agent(
    output_type=CharacterAnalysis,
    retries={"output": 2},     # 默认 1；DeepSeek 会 thinking 冲突，给 2 次余量
)
```

**重试耗尽后**：走 `failed` 分支，**必须报错**，不得返回空对象。

### ⚠️ DeepSeek 的约束（影响本规范的落地）

| 约束 | 后果 | 出路 |
|---|---|---|
| Chat Completions **拒绝** strict JSON Schema（`This response_format type is unavailable now`） | 拿不到强约束 | ① 切 Responses API ② 关 thinking 用 `PromptedOutput` |
| V4 **默认开启 thinking**，且 thinking 下拒绝强制 `tool_choice` | 模型可能用散文回答而不调输出工具 | 同上；**重试预算可能被耗尽**，故不能只靠重试 |

详见 [`llm.md`](llm.md)。

---

## 7. 测试要求

**契约必须有测试守住**，否则会漂移（本项目的 7 处偏差就是这么来的）。

每个契约至少一条测试：

| 契约 | 测试 |
|---|---|
| `ok=False` 必须有 `error` | `test_result_requires_error_when_not_ok` |
| 三态可区分 | `test_no_change_is_not_failure` |
| CLI 退出码 | `test_cli_exit_code_follows_ok` |
| MCP `isError` | `test_mcp_tool_error_sets_is_error` |
| 参数真的透传 | `test_tier_reaches_design_characters` |
| A 轨零 LLM | `test_a_track_operations_work_without_llm` |

**最后一条特别重要**：把 `--tier` 的硬编码改回去时，`test_tier_reaches_design_characters` **必须失败**。测试要能在回归时报警，而不是恰好也因为别的原因通过。

---

## 8. 历史缺陷对照表

P4 迁移时必须逐条确认这些不会重新出现。

| 缺陷 | 原位置 | 本规范对应条款 |
|---|---|---|
| A1 解析失败静默返回空 | `character_engine.py:189-204` | §4 三态 |
| 空响应报"已保存" | `novel_commands.py:341` | §5 CLI 退出码 |
| 失败仍 exit 0 | `novel_commands.py:400-409` | §5 CLI 退出码 |
| 角色生成空结果报成功 | `novel_commands.py:256` | §3 + §5 |
| 剧情设计空结果报成功 | `novel_commands.py:295` | §3 + §5 |
| 审稿全失败显示"无" | `base_agent.py:117-133` | §4 三态 |
| Level-1 没匹配到也打 ✅ | `fixer.py:62-110` | §3 `warnings` |
| 逐层分析失败返回全默认值 | `deep.py:49-62` | §4 `failed` 分支 |
| 轻量分析结果被丢弃（`pass`） | `ingestion.py:150-154` | §3 `data` 字段 |
