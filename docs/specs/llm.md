# LLM 层（`src/llm/`）

本模块是**唯一的 LLM 出口**。业务代码禁止直接 import `openai` / `pydantic_ai`。

---

## 职责边界

**做**：声明 Agent、解析模型、三档降级、汇总用量。

**不做**：编排（在 `src/novel/service.py`）、渲染（在 `src/interfaces/`）、领域判断（在 `src/novel/`）。

---

## 模型无关：核心设计

**代码里不得出现具体模型名。** 模型由调用方在运行时注入。

```python
# ✅ 构造时不绑定模型
character_analysis_agent = Agent(
    output_type=CharacterAnalysis,
    retries={"output": 2},
)

# ✅ 运行时注入
def analyze(project, chapter, tier: str) -> NovelResult[AnalysisOutcome]:
    result = character_analysis_agent.run_sync(prompt, model=resolve_model(tier))
    ...
```

**依据**：`Agent.__init__` 的 `model` 参数可为 `None`，官方文档明确 *"if not provided, you must provide the model when calling it"*。而 `MCPSamplingModel` 的基类是 `Model`——**它就是一个 Model**。所以宿主采样、OpenAI 兼容端点、其它 provider 三者对 `Agent` 无差别。

### ⚠️ tier 是兼容契约，不向外扩散

**`tier` 在内部当不透明字符串透传，`model_tier` 参数保持原样。**

| 项 | 结论 |
|---|---|
| 改 10 个模块的签名？ | ❌ **不改** |
| 内部 API 加 `ModelRef`？ | ❌ **不加**。新增能力只到 CLI/MCP 边界的参数解析为止 |
| 解析发生在哪？ | **只有一处**：`FastPath.resolve_model(tier)` |
| `--provider` / `--model` 去哪了？ | 只在**最外层入口**，就地解析成 tier 或模型后进入内部 |

**支持多级模型的场景**（`flash` 用便宜档、`pro` 用强档）**天然就是 tier 的语义**——不需要换概念。

完整论证与两处死 tier 的形状见 [`deepseek-fastpath.md`](deepseek-fastpath.md) §2.3。

---

## 三档降级（"不强求"的落地）

| 档 | 触发 | 模型来源 | 需要 Key | 需要 sampling |
|---|---|---|---|---|
| **B1** 宿主采样 | 客户端在 `initialize` 声明了 `sampling` | 宿主按 `modelPreferences` 选 | ❌ | ✅ |
| **B2** provider 配置 | 调用方显式传 `provider` / `model` | `config/models.yaml` | ✅ | ❌ |
| **B3** 交还宿主 | 以上都不可用 | 宿主自己生成 | ❌ | ❌ |

**降级顺序在 capability 协商期决定，不在运行时猜**：`initialize` 时记下 `ClientCapabilities.sampling` 是否存在。

### B3 不是降级方案，是主路径

B3 返回的是 `build_chapter_prompt()` 拼装好的 prompt 包（角色状态 + 前情提要 + 大纲 + 剧情设计 + 未解伏笔）。**任何宿主都能用**，不依赖能力协商。所以 B3 必须**永远可用**——它不依赖 Key，也不依赖 sampling。

---

## provider 注册表（纯数据）

`config/models.yaml`：

```yaml
providers:
  deepseek:
    base_url: "https://api.deepseek.com/v1"
    env: "DEEPSEEK_API_KEY"
    models: {fast: "deepseek-v4-flash", deep: "deepseek-v4-pro"}
  moonshot:
    base_url: "https://api.moonshot.cn/v1"
    env: "MOONSHOT_API_KEY"
    models: {fast: "moonshot-v1-8k", deep: "moonshot-v1-128k"}
  ollama:
    base_url: "http://localhost:11434/v1"
    env: ""
    models: {fast: "qwen2.5:7b", deep: "qwen2.5:14b"}
```

**关键洞察**：DeepSeek / Moonshot / 智谱 / 阿里 / 本地 Ollama **都是 OpenAI 兼容 API**。所以模型无关做成**配置驱动**，换供应商**只改 yaml**。

**验收方式**：加一个新 provider 时，代码零改动。有测试证明这一点。

---

## ⚠️ DeepSeek 的硬约束

DeepSeek 不是"一个普通的 OpenAI 兼容端点"——它有两个会**静默影响正确性**的行为，因此有**独立规格**：

**→ 完整设计见 [`deepseek-fastpath.md`](deepseek-fastpath.md)**

摘要：

| 约束 | 后果 |
|---|---|
| 强 JSON Schema **只在 Responses API 上可用**（Chat Completions 报 `This response_format type is unavailable now`） | 结构化输出拿不到强约束 |
| V4 **默认开启 thinking**，且 thinking 下**拒绝强制 `tool_choice`** | 模型可能用散文回答；官方文档明确**足以耗尽重试预算** |

**推论**：不能只靠"自动重试"兜底。`retries={"output": 2}` 是余量，不是解药。

**FastPath 的边界**：它是 `src/llm/` 内的策略，**只做**模型解析 / 输出模式选择 / thinking 兼容。**不得**实现重试、预算、用量记录、Agent 声明——否则架空架构约束②。

**兼容性底线**（`flash`/`pro` 档位、配置键名、`max_tokens` 覆盖、CNY 预算）见 fastpath 文档 §2。

---

## 用量与成本

```python
result = agent.run_sync(prompt, model=m, usage_limits=UsageLimits(cost_limit=Decimal("6.90")))
result.usage.cost            # Decimal | None
result.usage.input_tokens
result.usage.output_tokens
result.usage.requests
result.usage.cache_hit_ratio
```

### ⚠️ 三个必须注意的点

| 点 | 说明 |
|---|---|
| **单位是 USD** | `cost_limit` 是美元。配置里的 `max_cny_per_session` 要换汇率（现约 7.25） |
| **`cost=None` 表示无法定价** | 不是零成本。文档明确设计为"未知"与"真的 0"可区分。**不要当 0 处理** |
| **依赖 `genai-prices` 收录该模型** | 未收录则 `cost` 恒为 `None`，预算护栏主键失效。**需验证 DeepSeek 是否被收录** |

---

## 已删除的组件（不要重新引入）

P4 完成后，以下全部删除：

| 组件 | 被什么替代 |
|---|---|
| `src/utils/llm_client.py` 整个 | `Agent` |
| `_RateLimiter` | `max_concurrency` |
| 手写重试 / 指数退避 | `retries` + 传输层重试 |
| `src/utils/json_utils.py` 的解析部分（`safe_json_parse` / `find_json_in_text`） | `output_type` 校验 |
| `base_agent._try_fix_truncated_json`（括号补齐） | 框架回模型重试 |
| `src/utils/cost_tracker.py` | `result.usage` |

> `_try_fix_truncated_json` 现版本的**括号闭合顺序写反了**（先补 `]` 再补 `}`），多层嵌套时仍非法。删掉比修它划算。

---

## 客户端采样：已核实的规范条文

来自 MCP 规范 2025-06-18 与 schema，逐字核实：

| 事实 | 原文要点 |
|---|---|
| 服务器不能强制指定模型 | *"A server **cannot** simply request a specific model by name"* |
| 偏好全部可忽略 | `hints` / `costPriority` / `speedPriority` / `intelligencePriority` 均为 **MAY ignore** |
| 不需要 Key | *"with **no server API keys necessary**"* |
| 人机确认 | *"there **SHOULD** always be a human in the loop with the ability to deny sampling requests"* |
| `systemPrompt` 可能被改 | 客户端 **MAY** 修改或忽略 → **关键约束放 messages 正文** |
| `includeContext` 可能被忽略 | → 需要的内容显式放进 `messages` |
| 响应含实际模型名 | `CreateMessageResult.model` → **可回写项目元数据做溯源** |
| hints 是子串匹配 | `{"name": "pro"}` 会误匹配 → 用有辨识度的前缀（`deepseek` 而非 `pro`） |

**`maxTokens` 是 sampling 的必需参数**，而 `ModelSettings` 里可选——故 `MCPSamplingModel` 有 `default_max_tokens`（默认 16384）。

---

## 未验证事项（P4-0 的 spike 清单）

| # | 待验证 | 若不成立的影响 |
|---|---|---|
| 1 | `agent.run_sync()` 在 **Textual worker 线程**里是否抛异常（`loop.run_until_complete` 遇到运行中的 loop） | **TUI 驱动路径不可用**。先走 CLI（纯同步、无线程池）绕开 |
| 2 | `MCPSamplingModel` 在**服务器进程内**是否可用 | **B1 档消失**，只剩 B2/B3——**方案不崩，B3 仍可用** |
| 3 | MCP Python SDK 服务端发起 sampling 的确切 API | 同上 |
| 4 | `genai-prices` 是否收录 DeepSeek 定价 | 预算护栏失效（`cost` 恒为 `None`） |
| 5 | Pydantic AI 在 Python 3.14.6 上实测可用（classifier 含 3.14，已核实元数据，**未实测安装**） | 需降级解释器 |
| 6 | 目标宿主是否真的支持 sampling | B1 不可达 |

**spike 结论写回本文件。** 完成前不要开始 P4 的实现。
