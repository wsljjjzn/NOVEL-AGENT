# spec：DeepSeek 快速路径

**目标**：为 DeepSeek 提供一条优化过的解析与调用策略，**同时不破坏既有的 `flash` / `pro` 档位契约**。

---

## 0. 一句话

> **FastPath 是 `src/llm/` 内部的一个 `Strategy`，不是第二个 LLM 出口。**

它只负责三件事——**模型解析**、**结构化输出模式选择**、**thinking 与 tool_choice 的兼容处理**。
它**不得**包含：重试、预算检查、用量记录、Agent 声明。那些仍归 `src/llm/` 的公共层。

**违反这条的后果**：`AGENTS.md` 约束②（只有一个 LLM 出口）被架空，历史上 18 个 `.chat()` 散点的局面会以另一种形式回来。

---

## 1. 为什么需要 FastPath

DeepSeek 不是"一个普通的 OpenAI 兼容端点"。它有**两个会静默影响正确性**的行为：

| 行为 | 后果 |
|---|---|
| 强 JSON Schema **只在 Responses API 上可用**，Chat Completions 会拒绝（`This response_format type is unavailable now`） | 结构化输出拿不到强约束 |
| V4 **默认开启 thinking**，且 thinking 下**拒绝强制 `tool_choice`** | 模型可能用散文回答而不调输出工具；官方文档明确**足以耗尽重试预算** |

**这两条不是"可以调参绕过"的偏好，是必须显式决策的互斥约束**。通用路径无法替调用方决定，所以需要 fastpath 把决策显式化并集中一处。

---

## 2. 兼容性契约（**不能破坏**）

以下是既有契约，fastpath 必须原样支持。

### 2.1 配置键名

| 键名 | 来源 | 必须继续可用 |
|---|---|---|
| `llm.deepseek_v4_flash` | `config/config.yaml:11` | ✅ |
| `llm.deepseek_v4_pro` | `config/config.yaml:21` | ✅ |
| `llm.flash` / `llm.pro` | 简写形式 | ✅ |
| 任意 `*_flash` / `*_pro` 后缀 | `service.py:348` 的回退链 | ✅ |

**现状不一致**（fastpath 要统一）：

- `llm_client.py:110-111` **硬编码** `cfg.llm.get("deepseek_v4_flash")` → 改配置里的键名会让 `.flash` 变 `None`，`chat()` 抛"模型层未配置"
- `service.py:347-348` **有正确的回退链**

**采用后者的策略，统一到一处。**

### 2.2 环境变量

| 变量 | 必须继续可用 |
|---|---|
| `DEEPSEEK_API_KEY` | ✅ 一个 Key 覆盖两个档位 |
| shell 环境变量 > `.env` > `config.yaml` 的优先级 | ✅ 见 `settings.py:117` |

### 2.3 档位参数（**最容易破坏的一条**）

`model_tier: str = "flash"` 是**贯穿全仓的参数名**，出现在 `character_engine` / `plot_engine` / `chapter_writer` / `base_agent` / `deep` / `lightweight` / `cli` / `tui` 等十余处。

**fastpath 必须继续接受 `"flash"` / `"pro"` 作为输入**，并在内部解析成实际模型。对外接口仍是：

```python
def chat(messages, model_tier="flash", temperature=None, max_tokens=None, timeout=None) -> str
```

> **P5 的 `--tier → --provider/--model` 是新增能力，不是替换。** `--tier` 保留为**已弃用别名**，至少保留到 P5 之后一个版本。

### 2.3 档位参数：**契约，不是待替换物**

`model_tier: str = "flash"` 是**贯穿全仓 10 个模块的透传参数**（实测：`character_engine` / `plot_engine` / `chapter_writer` / `base_agent` / `deep` / `lightweight` / `character_analyzer` / `requirement_agent` / `outline_agent` / `writer_agent` / 两个 `orchestrator` / `service` / `cli`）。

**设计原则：`tier` 是外层兼容契约，内部当不透明字符串透传，不在仓库里扩散改造。**

具体含义：

| 项 | 结论 |
|---|---|
| 改 10 个模块的签名？ | ❌ **不改** |
| 内部 API 加 `ModelRef` 参数？ | ❌ **不加**。新增能力只到 CLI/MCP 边界的参数解析为止 |
| `tier` 在内部怎么流动？ | 原样透传，**不做任何转换** |
| tier→实际模型在哪里解析？ | **只有一处**：`FastPath.resolve_model(tier)` |

**唯一必须做的改动是"把 tier 真的传下去"**（现在有两处没传，见 §2.3.1）。

#### 2.3.1 两处死 tier 的精确形状

**形状 A：调用方收下 tier，调用时不传**

```python
# service.py:237-247
def design_plot(self, name: str, chapter: int, tier: str = "flash") -> Result:
    ...
    self.log(f"[剧情] 用 {tier} 设计第{chapter}章…")        # ← 日志说用了 tier
    plot_obj = plot.design_chapter_plot(                    # ← 没传下去
        chapter, {...}, project.get_recap(chapter), project.foreshadowing,
    )
```

**形状 B：签名里根本没有 tier，内部硬编码**

```python
# plot_engine.py:159  签名无 tier
def design_chapter_plot(self, chapter_num, outline_item, prev_summary="", existing_foreshadowing=None):
    response = self.llm.chat([...], model_tier="flash", temperature=0.5)   # ← :187 硬编码
```

两者叠加 = **"正在用 pro 生成" + 实际 flash**。全文共 6 处硬编码 `"flash"`（`plot_engine.py:187` / `:239`、`character_analyzer.py:126` / `:222`、`lightweight.py:31` / `:45`）。

> 后三者（`character_analyzer` / `lightweight`）是**有意固定用便宜档**的合理选择，**不修**。只有 `plot_engine` 的两处是缺陷——因为上层提供了 tier 参数却不生效。

**修法（最小）**：

| 文件 | 改动 |
|---|---|
| `plot_engine.py` | 两个方法签名加 `model_tier: str = "flash"`，替换硬编码 |
| `service.py` | `design_plot` / `generate_characters` 把已有的 `tier` 转发下去 |

**只有 2 个文件、约 5 行。** 不动其余 10 个模块。

### 2.4 输出预算

| 档 | `max_tokens` | 来源 |
|---|---|---|
| flash | 4096 | `config.yaml:14` |
| pro | 8192 | `config.yaml:24` |

**注意**：`character_engine.ANALYSIS_MAX_TOKENS = 8192` 是**显式覆盖**（flash 档也要 8192），因为 4096 会把角色 JSON 硬截断——这是 A1 的成因。**fastpath 不得把这个覆盖改回去。**

### 2.5 计费单位

现有 `cost_tracker` 用 **CNY**（`USD_TO_CNY = 7.25`），配置写 `budget.max_cny_per_session: 50`。

Pydantic AI 的 `UsageLimits.cost_limit` 用 **USD**。**fastpath 负责换算**，配置里仍写 CNY。

### 2.6 测试固化值

`tests/test_llm_client.py` 固化了 `model_tier="flash"/"pro"`、`max_tokens=2048`、`get_tier_info("flash")`。**这些用例不得为了让 fastpath 通过而修改断言。**

---

## 3. 两个模式

### `compat`（默认）—— 最大兼容

```
Chat Completions
  + response_format={"type": "json_object"}     # JSON object 模式（非 strict schema）
  + thinking=False                              # 让强制 tool_choice 生效
```

| 项 | 值 |
|---|---|
| 端点 | `https://api.deepseek.com/v1`（**与现在完全一致**） |
| 结构化输出 | Pydantic AI `PromptedOutput`（客户端校验 + 失败回模型重试） |
| thinking | **关闭** |
| 风险 | 失去 V4 思考能力 |

**默认选它的理由**：**零行为变化**。端点、Key、模型名、`max_tokens` 全部与现状一致，只是补上了 `response_format` 与 thinking 控制。

### `strict`（可选）—— 最强约束

```
Responses API
  + NativeOutput                                # 严格 JSON Schema
```

| 项 | 值 |
|---|---|
| 端点 | DeepSeek Responses API（`OpenAIResponsesModel` + `DeepSeekProvider`） |
| 结构化输出 | `NativeOutput`（**真正的 strict schema**） |
| thinking | 可与强约束共存（Responses API 支持 strict schema） |
| 风险 | **协议无状态**；未支持字段**静默忽略** |

#### ⚠️ strict 模式的两个陷阱

1. **不要设 `openai_previous_response_id`**。设了 Pydantic AI 会以为服务端存了历史而丢掉上下文，**模型静默失去对话**。
2. **未支持字段静默忽略**（不报错）。DeepSeek 只实现了 Responses API 的一部分：
   - 无状态 → `openai_conversation_id` / background mode / message compaction 不可用
   - 原生工具只跑 `WebSearchTool`，其余**忽略而不报错**
   - 图片/文档输入被替换成占位文本而非拒绝
   - `openai_reasoning_summary` 被接受但**不产生 summary**

**因此 strict 模式必须显式传完整 `message_history`**，不能依赖服务端会话。

### 选择方式

```yaml
# config/models.yaml
providers:
  deepseek:
    base_url: "https://api.deepseek.com/v1"
    env: "DEEPSEEK_API_KEY"
    fastpath:
      mode: compat              # compat | strict
      thinking: false           # compat 模式下必须 false（否则丢掉结构化输出）
    models:
      flash: "deepseek-v4-flash"
      pro:   "deepseek-v4-pro"
```

**默认 `compat`**；`strict` 需显式开启并读取本文档的陷阱清单。

---

## 4. 接口

```python
# src/llm/fastpath/deepseek.py

class DeepSeekFastPath:
    """DeepSeek 的解析与调用策略。不是第二个 LLM 出口。"""

    def resolve_model(self, tier: str | None, provider: str | None,
                      model: str | None) -> ModelRef:
        """tier / provider / model 三选一 → 实际模型。

        优先级：显式 model > provider+model > tier（含旧的 flash/pro 别名）
        """

    def resolve_output_mode(self, needs_structured: bool) -> OutputMode:
        """兼容模式下 + 需要结构化输出 → NativeOutput 不可用时的降级链"""

    def build_model_settings(self, needs_structured: bool) -> dict:
        """按模式补 thinking / tool_choice，避免二者冲突"""
```

### 它**不**做什么

| 不做 | 归谁 |
|---|---|
| 重试与退避 | `retries`（框架） |
| 预算检查 | `UsageLimits`（框架）+ 换算在 fastpath 之外的 `src/llm/budget.py` |
| 用量记录 | `result.usage` |
| Agent 声明 | `src/llm/agents.py` |
| 结构化校验 | `output_type` |

---

## 5. 验收标准

| # | 验收 | 怎么测 |
|---|---|---|
| 1 | `model_tier="flash"` / `"pro"` **仍然可用** | 现有 `tests/test_llm_client.py` **不改断言**全绿 |
| 2 | `deepseek_v4_flash` / `deepseek_v4_pro` 两种键名都能解析 | 参数化测试跑 4 种键名形态 |
| 3 | 改配置键名（如 `myprovider_fast`）**不再导致"模型层未配置"** | 用一个自定义后缀键名的临时配置 |
| 4 | `ANALYSIS_MAX_TOKENS=8192` 的覆盖**未被回退** | 断言角色分析的 `max_tokens` 是 8192 而非 4096 |
| 5 | `DEEPSEEK_API_KEY` 仍能覆盖两个档位 | 现有环境变量优先级测试 |
| 6 | CNY 配置仍生效 | 断言 `cost_limit` 拿到的是 `50 / 7.25` 而非 `50` |
| 7 | **Compatibility 模式下不设 `openai_previous_response_id`** | 断言构造出的 model settings 里该键不存在（strict 模式同样） |
| 8 | FastPath **没有**引入第二条 LLM 出口 | `grep -rn 'import openai' src/ \| grep -v 'src/llm/'` 为空 |

**第 1 条是本次需求的硬底线。**

---

## 6. 任务分解

| 任务 | 内容 | 前置 |
|---|---|---|
| **P4-0d** | spike：DeepSeek 在 Chat Completions 下 `response_format={"type":"json_object"}` + `thinking=False` 是否真的能让强制 `tool_choice` 生效 | P4-0 |
| **P4-0e** | spike：Responses API 的 strict schema 是否可用；`message_history` 显式传递是否有效 | P4-0 |
| **P4-7a** | 实现 `DeepSeekFastPath`（compat 模式） | P4-0d、P4-2 |
| **P4-7b** | 实现 strict 模式（可选） | P4-0e |
| **P4-7c** | 键名回退链统一到 fastpath，删除 `llm_client.py:110-111` 的硬编码 | P4-7a |
| **P5-0** | CNY → USD 换算集中到 `src/llm/budget.py` | P4-7a |
| **P5-4** | `--tier` 标记为弃用别名（**不删除**），新增 `--provider` / `--model` | P5-1 |

> **措辞很重要**：`--tier` 是**保留的别名**，不是被替换掉的旧参数。所有既有调用脚本、`docs/legacy/` 里的示例、以及用户的肌肉记忆都不应该断。
>
> **且 `tier` 只在最外层兼容**——见 §2.3：内部 10 个模块的 `model_tier` 参数**零改动**，`--provider` / `--model` 只在外层入口解析。

---

## 7. 未验证事项

| # | 待验证 | 若不成立 |
|---|---|---|
| 1 | Chat Completions + `json_object` + `thinking=False` 是否真能让 `tool_choice='required'` 生效 | compat 模式退化为纯 `PromptedOutput`（仍可用，但约束更弱） |
| 2 | Responses API 的 strict schema 在 DeepSeek 上是否真的可用 | strict 模式取消，只留 compat |
| 3 | `Message` 里 `systemPrompt` 的传递 | 无影响 |
| 4 | `genai-prices` 是否收录 DeepSeek 模型定价 | `RunUsage.cost` 为 `None`，成本护栏退回自算 |

**第 1、2 条是 P4-0d / P4-0e 的内容。做完再实现 fastpath。**
