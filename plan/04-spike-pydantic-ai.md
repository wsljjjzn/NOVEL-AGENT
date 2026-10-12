# 04 — Spike 记录：Pydantic AI 可行性验证（2026-10-12）

> 触发：`TECH-STACK-SELECTION.md` §8.2 列出 3 项"仍未验证"，其中"`run_sync()` 在 Textual
> worker 线程中的实际行为"被明确标为 **P1 的第一个 spike，必须先做**。
> 本文是那次 spike 的结果记录。**结论：技术层面可行，已实测通过；但领域模型 pydantic 化
> 被一个前置问题阻塞，见 §4。**
> 复现脚本：`/tmp/pa-spike/`（spike_textual.py / spike_output.py / spike_real_deepseek.py），
> 关键命令已内联到各节，环境销毁后可按命令重建。

---

## 0. 结论速览

| # | 待验证项 | 方法 | 结果 |
|---|---|---|---|
| 1 | 能否装上、与现有依赖是否冲突 | 隔离 venv（Python 3.14.8）装 `pydantic-ai-slim[openai]` | ✅ 2.55.0 装上，无冲突 |
| 2 | 引入后现有测试还绿吗 | 用装好新依赖的解释器跑全量 `tests/` | ✅ **246 passed**（与基线同） |
| 3 | `run_sync()` 在 Textual worker 线程里 | 真起 Textual App + `@work(thread=True)` 调 `run_sync` | ✅ **正常**（1 号未知已消除） |
| 4 | `run_sync()` 在已运行的事件循环里 | 主线程 `asyncio.run` 内直接调 | ✅ 抛 `RuntimeError: This event loop is already running`（可诊断；项目现有用法避开了） |
| 5 | 结构化输出语义 | `output_type=<pydantic 模型>`，正常路径 + 校验失败路径 | ✅ 返回模型实例；失败抛 `UnexpectedModelBehavior`，**不存在"空对象"中间态** |
| 6 | 是否真有 DeepSeek 定向适配 | 读 `pydantic_ai/providers/deepseek.py` 源码 | ✅ 真实存在，且把 thinking / tool_choice / json_schema 的坑写进了代码 |
| 7 | `deepseek:` 前缀写法是否成立 | `infer_model("deepseek:deepseek-v4-flash")` | ✅ 解析为 `OpenAIChatModel` |
| 8 | 真实 DeepSeek 调用能否成功 | 用项目 `.env` 的 Key 做 2 次极小调用（flash 档） | ✅ **两个端点都成功**，成本可计 |
| 9 | `RunUsage.cost` 能否替代手写 cost_tracker | 查 `genai-prices` 是否收录 DeepSeek 定价 + 实测返回值 | ✅ 收录 v4-flash/v4-pro，`cost` 返回真实美元数 |
| 10 | 领域模型换 pydantic 是否安全 | 用真实存档做 load→dump 往返比对 | ❌ **当前 87% 不一致，先解决落盘契约**（§4） |

**总支出**：2 次真实调用 ≈ **$0.00032**（约 ¥0.0023）。

---

## 1. 环境与版本（已实测解析结果）

```bash
uv venv --python <项目 .venv 的 3.14.8 解释器> .venv
uv pip install -r requirements-core.txt pytest     # 复刻项目现状
uv pip install "pydantic-ai-slim[openai]"          # 加底座
```

| 包 | 版本 | 说明 |
|---|---|---|
| pydantic-ai-slim | **2.55.0** | 与文档一致 |
| openai | **3.29.0** | ⚠️ 被**强制抬升**，见 §3 |
| pydantic | 2.14.1 | 满足 `>=2.12` |
| httpx2 | 2.13.1 | pydantic-ai 用的是 `httpx2`，不是 `httpx` |
| genai-prices | 0.1.11 | 成本估算数据源 |
| textual | 8.2.8 | 与项目一致 |

`instructor` 也一并装上了（1.17.0）——它在项目依赖清单里躺了很久但从未被 import，见 §5。

---

## 2. 逐项证据

### 2.1 `run_sync()` × Textual worker（原本的 1 号未知）

项目的 TUI 调用方式是 `src/tui/app.py:431` 的 `@work(thread=True, exclusive=True, group="llm")`，
即**在 Textual 的 worker 线程里同步调用服务层**。spike 按同样方式起了一个真 App：

```
worker 线程: asyncio_0
结果: 'success (no tool calls)'
异常: 无
结论: ✅ 线程内 run_sync 正常
```

反例（必须知道，否则将来会踩）：

```
【场景 2】主线程事件循环内直接调用 run_sync
  RuntimeError: This event loop is already running
```

→ **约束**：CLI（纯同步）与 TUI（worker 线程）都安全；**任何 async 调用点必须用
`await agent.run()`，不能用 `run_sync()`**。

⚠️ 一个必须处理的细节：pydantic-ai 首次运行会向 stdout 打一个 banner。TUI 下这会**污染界面**。
必须设 `PYDANTIC_AI_NO_BANNER=1`（spike 中已确认该变量生效）。

### 2.2 结构化输出语义

```
【A】正常路径
  返回类型: ReviewReport → score=0.0 issues=[] summary=''
  是模型实例: True
  usage: RunUsage(input_tokens=51, output_tokens=5, requests=1)
  cost: None            ← TestModel 无定价，None 表示"无法定价"而非 0

【B】校验失败路径
  UnexpectedModelBehavior: Exceeded maximum output retries (1)
  → 失败是显式异常，调用方无法把它误当成「模型说没变化」
```

这正是 `CODE_REVIEW.md` 里 12 处"静默失败"想要消除的中间态。

### 2.3 DeepSeek 适配（读源码，不是读文档）

`pydantic_ai/providers/deepseek.py` 里逐条写了：

```python
base_url = 'https://api.deepseek.com'
openai_chat_thinking_field='reasoning_content'
supports_forced_tool_choice = model_name != 'deepseek-reasoner'
supports_forced_tool_choice_with_thinking = not is_v4        # ← V4 在 thinking 下不支持强制 tool_choice
thinking_enabled_by_default = thinks_by_default              # ← V4 / reasoner 默认开 thinking
openai_responses_supports_json_schema_output = True          # ← 强 schema 只在 Responses 端点
openai_responses_supports_interleaved_function_calls = False
```

**注意：没有 `pydantic_ai.models.deepseek` 模块**。正确写法是组合 OpenAI 模型类 + DeepSeek provider：

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.deepseek import DeepSeekProvider

model = OpenAIChatModel("deepseek-v4-flash", provider=DeepSeekProvider(api_key=key))
# 或 infer_model("deepseek:deepseek-v4-flash")   ← 实测可解析
```

### 2.4 真实调用（2 次，flash 档）

```
【Chat Completions (output_type→tool call)】✅ 成功  耗时 1.8s
   输出: score=8 reason='句子语法正确、表达自然清晰，但内容较为平常、信息量有限。'
   usage: in=323 out=193 requests=1
   cost : 0.00016425

【Responses API (json_schema)】✅ 成功  耗时 1.9s
   输出: score=8 reason='句子语法正确、表达清晰自然，但内容比较普通且缺少具体细节。'
   usage: in=323 out=205 requests=1
   cost : 0.000152634
```

两个端点都成功，**且都在第 1 次请求就成功（`retries=0`）** —— 文档 §7.1 担心的
"V4 thinking 下模型用散文回答、足以耗尽重试预算"在这条最小用例上**没有出现**（不代表长 prompt 下不会）。

**成本信号**：输出只有 2 个字段，却消耗 **193–205 output tokens** —— 说明 thinking 的
reasoning token 计入了输出。**结构化输出的实际成本由 output 主导，不能按"输出很短"估算。**

### 2.5 成本数据源（文档里标"需验证"的那条）

```
deepseek-chat      : $0.27 / MTok in, $1.1  / MTok out
deepseek-v4-flash  : $0.15 / MTok in, $0.6  / MTok out
deepseek-v4-pro    : $0.66 / MTok in, $1.98 / MTok out     ← 与 config/config.yaml 的档位一致
```

→ `RunUsage.cost` **可以**覆盖项目现有的两档，替代手写 `cost_tracker` + `llm_usage.db` 的
可行性成立（替换本身另属 P4 范围）。

---

## 3. 对现有两份文档的两处更正

| 文档 | 原文 | 实测 |
|---|---|---|
| `TECH-STACK-SELECTION.md` §7.2 / §8.1 | "要求 `openai>=3.26.0`；**本机 3.3.0 恰好满足**" | ❌ **不满足**。项目 `.venv` 实际是 **3.16.2**，且 minor `16 < 26`，装 pydantic-ai 会**强制升到 3.29.0**。好消息：升级后现有 **246 项测试全绿** |
| `TECH-STACK-SELECTION.md` §5.2 / §8.2 | "`RunUsage.cost` … **需验证** `genai-prices` 是否收录 DeepSeek" | ✅ **已收录**，见 §2.5，v4-flash/v4-pro 均可定价 |

---

## 4. ⛔ 阻塞项：落盘契约还没锁（P1 的前置）

用真实存档（`data/projects/`，45 个角色）跑项目自己的 `CharacterProfile.from_dict().to_dict()`：

```
总计：45 个角色，39 个 load→dump 后与磁盘不一致（87%）
```

差异收敛为四类，已写进 [`tests/test_roundtrip_baseline.py`](../tests/test_roundtrip_baseline.py)：

| # | 差异 | 性质 |
|---|------|------|
| 1 | 关系表遗留键 `描述` 被丢弃（真实存档 8 条，如"信赖的挚友，隐约察觉他有秘密但从不追问"） | 🔴 **数据丢失** |
| 2 | 字符串关系 `"乙": "父亲，又敬又怕…"` 被改写成 `{状态, 强度, 起始章}` dict | 🟠 格式漂移 |
| 3 | 同章重复的 `chapter_events` 被去重（保留后写入的那条，实测是信息更全的一条） | ✅ 修复性（A8），已直接断言 |
| 4 | 空 `relationship_changes` 键被补写到每个事件（真实存档 100% 缺该键） | 🟠 格式漂移 |

**结论**：`characters.json` 目前**不是**往返稳定的。把 dataclass 换成 pydantic 之前必须先定
落盘契约（字符串关系怎么表示、遗留键留不留、空键要不要写），否则"迁移"会与"顺手改格式"
混在一起，出问题无法归因。这一点 `plan/01-tasks.md` 的 `P1-1` 已经预判到，本 spike 只是
给出了它的实测规模（87%）。

---

## 5. 采用决定

**采用（技术结论已成立）**

1. **Pydantic AI 作为 LLM 调用层底座** —— §0 的 1–9 项全部实测通过，含**真实 DeepSeek 调用**。
   选型结论从"推荐"升级为"已验证"。
2. **`tests/test_roundtrip_baseline.py`（P1-1 基线）** —— 已落地。它把当前 4 类差异分成
   "该修的（strict xfail）"和"是有意修复的（直接断言）"，将来改动会让 xfail 变成 XPASS 而报错，
   逼更新基线，而不是让漂移悄悄变成规范。
3. **领域模型的 pydantic 化**（P1-2 起）—— 方向可行，但**必须先做 §4 的契约决定**。

**暂不采用（并说明为什么）**

- **不把 `pydantic-ai` 写进 `pyproject.toml`**。理由：它要等 `plan/` 的 P0（CLI 委托 service）
  → P1（模型层）→ P2（工具层）→ P3（适配器）之后才有落点。现在就加，会精确复刻
  `instructor` 的教训 —— **依赖在清单里躺着，一行 import 都没有**。等 P4 开工时再加，
  届时把 `openai` 下限一并抬到 `>=3.26.0`。
- **不现在改 `src/novel/*` 的模型**。§4 的契约没定，改了就是引入不可归因的格式变化。

---

## 6. 仍未验证（不影响本次结论）

- 长 prompt / 高并发下 DeepSeek 的 thinking 与强制 tool_choice 是否会真的耗尽重试预算（§2.4 只覆盖最小用例）
- `UsageLimits` 的具体参数名与语义
- `pydantic-graph` 持久化的恢复粒度（P4 断点续跑前需 spike）
- `pydantic-evals` 能否用于"50 章成稿质量"的自动评估
- Langfuse 自托管运维成本（观测选型仍开放）
