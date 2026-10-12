# 模块：MCP 服务器（`src/interfaces/mcp/`）

## 负责

把 `src/tools/` 的操作暴露为 MCP 原语。**只是适配器**——不含编排与业务判断。

## 三类原语

### `tools` — 主要形态

A 轨（零 LLM）与 B 轨（生成）都暴露成工具。工具定义从 `src/tools/registry.py` 生成，`inputSchema` **从 pydantic 模型自动派生**。

### `resources` — 让宿主主动读状态

```
novel://{project}/characters     → characters.json
novel://{project}/outline        → 大纲
novel://{project}/foreshadowing  → 伏笔台账
```

配套 `notifications/resources/updated`——**伏笔变化时可主动通知宿主**。

### `prompts` — 用户可选的模板

放 `HANDOVER` 里的写作 SOP：`write_chapter` / `review_article` / `learn_from_corpus` / `cold_start_novel`。

## ⚠️ 错误语义（最容易写错）

规范原文：

> Any errors that originate from the tool SHOULD be reported inside the result object, with `isError` set to true, **not** as an MCP protocol-level error response. Otherwise, the LLM would not be able to see that an error occurred and self-correct.

| 情况 | 用哪个 |
|---|---|
| 业务失败（模型返回空、参数不合法、项目不存在） | 结果内 `isError: true` |
| 协议级异常（工具名不存在、服务器崩溃） | 协议级错误响应 |

```python
CallToolResult(
    content=[TextContent(type="text", text=result.summary)],
    structuredContent=result.data.model_dump() if result.data else None,
    isError=not result.ok,
)
```

**违反这条的后果比 CLI 更严重**：宿主看不见错误，会以为调用成功了。

## Capability 协商

`initialize` 时记下 `ClientCapabilities.sampling` 是否存在，**在协商期决定可用档位**，不要在运行时猜。

`ServerCapabilities.instructions` 用来告知宿主可用能力与降级情况。

## 反向采样（B1 档）

```
宿主 ──tools/call──→ NOVEL-AGENT          （常规方向）
宿主 ←─sampling/createMessage── NOVEL-AGENT（反向：服务器请求宿主推理）
```

### ⚠️ 协议级约束（逐字核实）

| 约束 | 影响 | 应对 |
|---|---|---|
| `sampling` 是**可选**客户端能力 | 宿主可能不声明 | capability 协商；B3 永远可用 |
| **每次 sampling SHOULD 人机确认** | 批量操作不可用（写 50 章 ≈ 50 次弹窗） | 提供服务端批量生成（B2）替代，或设计"逐章确认"为默认交互 |
| `systemPrompt` 客户端 **MAY** 修改或忽略 | 角色卡片 prompt 可能被改写 | **关键约束放 `messages` 正文**，不只放 systemPrompt |
| `includeContext` 客户端 **MAY** 忽略 | 无法假设宿主自动带上你的资源 | 需要的内容显式放进 `messages` |
| `modelPreferences` 全部 **MAY ignore** | 无法保证拿到强模型 | **按能力设计，别假设模型够强** |
| `hints` 是**子串匹配** | `{"name":"pro"}` 会误匹配 | 用有辨识度的前缀（`deepseek` 而非 `pro`） |
| `maxTokens` 是 sampling 的**必需**参数 | 未给会失败 | 走 `MCPSamplingModel` 的 `default_max_tokens`（默认 16384） |

### 红利

`CreateMessageResult.model` 含**实际生成消息的模型名** → **可回写项目元数据做溯源**。

## 降级三档

| 档 | 条件 | 模型来源 | 需要 Key |
|---|---|---|---|
| B1 | 客户端声明了 `sampling` | 宿主按 `modelPreferences` 选 | ❌ |
| B2 | 调用方传 `provider`/`model` | `config/models.yaml` | ✅ |
| B3 | 以上都不可用 | 宿主自己生成（收 prompt 包） | ❌ |

**B3 不是降级方案，是主路径**——依赖 A 轨的 `build_chapter_prompt`。

## 测试

`tests/interfaces/test_mcp.py`：

- 失败操作返回 `isError=True`，**不抛异常**
- `tools/list` 的 `inputSchema` 与 pydantic 模型一致
- 宿主不声明 `sampling` 时**不报错**，自动落到 B2 或 B3
- A 轨工具在 LLM 完全禁用时可用

## 未验证事项

| # | 待验证 | 若不成立 |
|---|---|---|
| 1 | MCP Python SDK 服务端发起 sampling 的**确切 API** | B1 无法实现，只剩 B2/B3 |
| 2 | `MCPSamplingModel` 在**服务器进程内**是否可用 | 同上 |
| 3 | 目标宿主对 `modelPreferences` 的实际尊重程度 | 只能靠 hints，且可能被忽略 |

第 1、2 条是 **P4-0 的 spike**。**做完再实现 B1**。
