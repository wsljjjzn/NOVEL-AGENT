# NOVEL-AGENT 底座选型报告（技术决策文档）

> 文档性质：**选型决策，非实施方案**。截至本文写作，仓库代码未被修改。
> 审查基线：`bf373df`。环境：**Python 3.14.6**（`.venv` 实测）、pydantic 2.x、openai SDK。
> ⚠️ 本文原引用的 `MAF-MIGRATION-PLAN.md` **已不在仓库中**。MAF 的 checkpoint/middleware 分析有效结论已并入本文；当前计划以 [plan/](plan/) 与 [docs/](docs/) 为准。
> 结论摘要：**推荐 Pydantic AI 作 LLM 调用层底座；编排层保持纯 Python；B 类问题只能靠契约测试治。**

---

## 0. 决策速览

| 问题 | 结论 |
|---|---|
| 有没有比 MAF 更好的底座？ | **有。对你这项目的核心痛点，Pydantic AI 比 MAF 更对症。** |
| 决定性理由 | 你的痛点是**结构化输出不可靠**（C 类，12 处静默失败），而 Pydantic AI 正是以此为核心设计；MAF 没有 DeepSeek 定向适配。 |
| 需要几套东西？ | **Pydantic AI（LLM 层）+ 纯 Python（编排层）** 两件即可；`pydantic-graph` 按需；可观测另算。 |
| 最大认知风险 | 任何框架都**治不了 B 类**（界面契约一致性，7 处已确认偏差）。指望换底座"顺便解决一致性"会落空。 |
| 迁移成本 | LLM 层约 1–2 天（`run_sync()` 兼容你现有的同步 CLI/TUI）；编排层**先不动**。 |
| 何时不该选它 | 需要微软/Azure 生态绑定，或需要 LangGraph 那套现成的 deep-agent 与平台能力。 |

---

## 1. 需求侧：我到底在替什么做选型

选型必须从**待解决的问题**出发，而不是从"哪个框架更强"出发。本项目的需求按优先级排列，全部有实测依据：

| 优先级 | 需求 | 依据（本文档基线） |
|---|---|---|
| **P0** | **LLM 返回必须可靠**：解析失败不能静默变成空结果 | 12 处包裹 `.chat()` 的 `try/except`，**6 处明确有害的静默**（§1.3 明细见 MAF 计划文档） |
| **P0** | **必须能拿到强约束的 JSON Schema** | DeepSeek Chat Completions **拒绝** strict schema（官方错误：`This response_format type is unavailable now`） |
| P1 | 调一次 LLM 只走一条代码路径 | 18 个 `.chat()` 调用点，单一 HTTP 出口 `llm_client.py:245` |
| P1 | 已有同步代码不能被迫全改 async | CLI/TUI 全同步；[novel_commands.py](src/cli/novel_commands.py)、[tui/app.py](src/tui/app.py) |
| P2 | 成本护栏要可靠 | 现 [cost_tracker.py](src/utils/cost_tracker.py) 的 `add_record` 只在 `usage` 非空时执行 → `usage=None` 时预算闸门失效 |
| P2 | 长篇写作能中断续跑 | 50 章项目实测存在（[data/projects](data/projects)）；现靠手写原子写 |
| P3 | 能看到"假成功" | 现无任何 trace/eval 能力 |

**明确的需求边界（同样是约束）**：

- 只用一个供应商（DeepSeek），无多云/多模型诉求 → **不需要** provider 抽象层带来的复杂度
- 单机本地运行，无分布式/多租户诉求 → **不需要** Cosmos/服务端平台能力
- 现有 pydantic 2.x 数据模型是资产 → **应复用**而非重建

---

## 2. 候选清单（只保留真实可选项）

| # | 候选 | 版本（已核实） | Python | 定位 |
|---|---|---|---|---|
| **1** | **纯 Python 自建加固** | — | — | 零新依赖，只加中间件与契约测试 |
| **2** | **Pydantic AI** | `pydantic-ai` **2.55.0**（PyPI） | `>=3.11`（**classifier 含 3.14**） | 类型优先的 agent 框架，**有 DeepSeek 定向适配** |
| **3** | **Microsoft Agent Framework** | `agent-framework` **1.21.0**（2026-10-08） | `>=3.10`（含 3.14） | SK+AutoGen 官方后继，graph workflow + checkpoint |
| **4** | **LangGraph** | `langgraph` **1.2.14**（PyPI） | `>=3.10` | 图编排 + 持久化，生态最大 |
| *补* | `pydantic-graph` | 已核实存在（独立库） | — | Pydantic AI 的图底层，**可独立于 AI 使用** |
| *补* | **Langfuse** | `langfuse` **4.17.0**（PyPI） | `>=3.10` | 可观测/评估，开源可自托管——**与上面是并列关系，不是竞争关系** |
| *补* | `openai-agents` | **0.23.1**（PyPI） | `>=3.10` | 官方 SDK；但缺 checkpoint 设计，**对本项目不作为主选** |

---

## 3. 选型标准与权重（先定规则，再看候选）

| 标准 | 权重 | 理由 |
|---|---|---|
| 能否**强制**结构化输出 | ★★★★★ | 直击 P0；这是最大单项收益 |
| 是否有 **DeepSeek 定向适配** | ★★★★★ | 否则要自己踩 thinking/tool_choice 冲突、Responses API 无状态性 |
| 能否复用**现有 pydantic 模型** | ★★★★ | [src/models/*](src/models) 与领域 dataclass 是存量资产 |
| 对**同步代码**的侵入度 | ★★★★ | CLI/TUI 全同步，全改 async 是纯成本 |
| 版本稳定性 | ★★★★ | 框架半成品比没框架更贵 |
| **对编排层**的强制力 | ★★ | 你已有正确的 `service.py`；框架在这是"锦上添花"而非"雪中送炭" |

> 注意最后一项权重很低——**这是本文与 MAF 计划最大的分歧点，也是修正所在**。上一轮我按"编排一致性"排优先级，导致把 MAF 放在台面上；但既然把三类问题按**证据密度**重排，LLM 调用层的权重明显更高。

---

## 4. 覆盖矩阵：每个候选能治哪一类问题

| 候选 | A 类<br>编排一致性 | B 类<br>界面契约 | C 类<br>结构化输出 | 治好几类 |
|---|---|---|---|---|
| 1. 纯 Python 加固 | ⚠️ 部分（可靠纪律） | ✅ **唯一有效** | ⚠️ 部分（手写校验） | 1 |
| 2. **Pydantic AI** | ⚠️ 部分 | ❌ | ✅ **强** | **1（但最痛的那个）** |
| 3. MAF | ✅ **强** | ❌ | ⚠️ 部分 | 1 |
| 4. LangGraph | ✅ **强** | ❌ | ⚠️ 部分 | 1 |
| **2 + `pydantic-graph`** | ✅ 强 | ❌ | ✅ 强 | **2** |
| 全部 + 契约测试 | ✅ | ✅ | ✅ | **3（但 B 类不是框架给的）** |

**这一行是全文最重要的结论**：

> **没有任何单一底座能覆盖三类。B 类（界面契约一致性）只能由现有代码的改造 + 契约测试修复——换任何框架都不会自动解决。**

所以选型的正确问法是："**哪个底座能把 C 类降到零、并对 A 类给出强制力，同时不破坏我已经做对的 B 类基础设施？**" 答案指向 Pydantic AI。

---

## 5. 推荐方案

### 5.1 分层决定（不是"选一个框架"，而是"每层选一个"）

```
┌─ 界面层 ────────────────────────────────────────────────┐
│ TUI (Textual) · CLI            【不动】                  │
└─────────────────────────────────────────────────────────┘
                    │  都只调 NovelService
┌─ 编排层 ────────────────────────────────────────────────┐
│ src/novel/service.py           【保持纯 Python】          │
│   · 理由：它的护栏语义已是对的设计，且 B 类修复就在这一层   │
│   · 需要显式状态机时 → 再加 pydantic-graph（独立库）      │
└─────────────────────────────────────────────────────────┘
                    │
┌─ LLM 调用层 ────────────────────────────────────────────┐
│ ★ 换成 Pydantic AI ★                                     │
│   · output_type=<pydantic 模型> → 校验或抛错，无"空对象"   │
│   · run_sync() → 现有同步代码几乎不改                     │
│   · DeepSeekProvider + DEEPSEEK_API_KEY（与你 .env 同名） │
│   · RunUsage.cost → 可替代手写 cost_tracker              │
└─────────────────────────────────────────────────────────┘
                    │
┌─ 领域层 ────────────────────────────────────────────────┐
│ CharacterEngine · PlotEngine · NovelProject · Writer     │
│                    【完全不动】                           │
└─────────────────────────────────────────────────────────┘
```

### 5.2 为什么是 Pydantic AI（逐条对应第 3 节标准）

| 标准 | Pydantic AI 的表现 | 证据 |
|---|---|---|
| 强制结构化输出 | ✅ `output_type` 接受 pydantic 模型；校验失败**把错误回给模型重试**（`ModelRetry`）；输出是模型实例**或异常**，中间没有"空对象"这个状态 | [Output 文档](https://pydantic.dev/docs/ai/core-concepts/output/) |
| DeepSeek 定向适配 | ✅ `deepseek:` 前缀、`DeepSeekProvider`、`DEEPSEEK_API_KEY` 同名；**且文档主动写明 DeepSeek 的坑**（thinking 与 tool_choice 冲突、Responses API 无状态、函数调用合并处理） | [DeepSeek 适配页](https://pydantic.dev/docs/ai/models/deepseek/) |
| 复用 pydantic 模型 | ✅ 项目已依赖 pydantic 2.x，`Chunk`/`KnowledgeUnit`/`ReviewReport` 等可直接当 `output_type` | [src/models/*](src/models) |
| 同步侵入度 | ✅ **`run_sync()`** — 官方描述为"plain, synchronous function ... internally just calls `loop.run_until_complete(self.run())`" | [Agent 文档](https://pydantic.dev/docs/ai/core-concepts/agent/) |
| 版本稳定性 | ⚠️ 2.55.0，且**正在 V1→V2 迁移**（有专门 Migration Map）→ **必须锁版本** | 官方有 V1→V2 Migration Map |
| 编排强制力 | ⚠️ 弱（这是它的短板，但正合我意——编排层我建议先不动） | — |

**额外收益（不在原需求内但真实存在）**：

- **`RunUsage.cost`**：内建成本估算（基于 `genai-prices`），可替代你手写的 `cost_tracker` + `llm_usage.db`。⚠️ 仅当 `genai-prices` 收录了 DeepSeek 模型定价时才准确——**需验证**。
- **Usage Limits**：官方有 `Usage Limits` 与 `Concurrency Limiting` 章节（文档目录已核实），语义上对应你的预算闸门与 RPM 限流。
- **`pydantic-evals`**：你项目**完全没有评估环节**——50 章成稿质量全靠人眼。这是"读文献学写作"主线唯一能验证自己有没有变好的手段。
- **`pydantic-graph` 可独立使用**（`pip install pydantic-graph`，不依赖 pydantic-ai），节点的**出边由 `run()` 返回类型推导**并在运行时强制检测，还能 `print(graph)` 直接出 Mermaid 图。

### 5.3 必须同时做的 B 类修复（框架给不了）

这一节是**前置条件**，不做则整个选型只解决 1/3 的问题：

| 动作 | 位置 | 验收 |
|---|---|---|
| `cmd_characters`/`cmd_plot`/`cmd_write`/`cmd_auto` 改为委托 `NovelService` | [novel_commands.py](src/cli/novel_commands.py) | 三处死 `tier` + 两条假成功 + 备份缺口同时消失 |
| 补契约测试：断言 `tier` 真的传到 `design_characters`/`design_chapter_plot` | `tests/` | 空输出路径返回非 0 |
| 修"护栏即测试前提"用例 | [test_tui.py:264-277](tests/test_tui.py#L264-L277) | 必须替换 writer 后再断言，避免护栏回归时真烧钱 |

---

## 6. 分阶段落地（每阶段独立可验收，不签大合同）

| 阶段 | 内容 | 引入依赖 | 工期 | 验收标准 | 风险 |
|---|---|---|---|---|---|
| **P0** | B 类收口：CLI 委托 service + 契约测试 | 无 | **1 天** | 三条护栏在 TUI/CLI 行为一致；空输出 exit ≠ 0 | 极低 |
| **P1** | **换 LLM 调用层为 Pydantic AI** | `pydantic-ai-slim[openai]` | **2–3 天** | 12 处静默失败路径收敛为"模型实例或异常"；`run_sync` 不改调用方签名 | 中（见 §7） |
| **P1.5** | 决定 Responses API vs 关 thinking | 无 | 0.5 天 | 明确选定并记录理由（见 §7.1） | — |
| **P2** | 编排层**保持纯 Python**；状态机痛点出现时再评估 `pydantic-graph` | 按需 | 按需 | 全仓仍只有 1 处编排 | 低 |
| **P3** | 可观测：Langfuse 自托管 或 Logfire | `langfuse` | 1–2 天 | 任一次失败/截断调用可被追溯到 | 低 |
| **P4** | 断点续跑（`pydantic-graph` 持久化 或 自建） | 按需 | 3–5 天 | 30 章中途 kill 后可续写且不重复计费 | 中 |

**为什么 P2 建议"不动编排层"**：你现有的 [service.py](src/novel/service.py) 已经把"唯一编排层"这个判断做对了，TUI 也证明了可行。把编排层一并换掉，等于在一次迁移里同时改变两个变量——一旦出问题无法归因。**先换 LLM 层，观察一个迭代周期，再决定编排层。**

---

## 7. 风险、约束与时效性

### 7.1 ⚠️ DeepSeek 的两个硬约束（决定 P1 怎么做）

**这是全文第二个最重要的技术事实**：

1. **Chat Completions 拿不到强 JSON Schema。** 官方错误：`This response_format type is unavailable now`。
   - → 出路 A：切 **Responses API**（`OpenAIResponsesModel` + `DeepSeekProvider`）可拿严格 Schema，但 DeepSeek 的 Responses 实现**无状态**，且**未支持字段静默忽略**（不报错）。特别地：不要设 `openai_previous_response_id`，否则 Pydantic AI 以为服务端存了历史而丢上下文，**模型静默失去对话**。
   - → 出路 B：`model_settings=OpenAIChatModelSettings(thinking=False)`，让强制工具选择重新生效——**代价是牺牲 V4 的思考能力**，对"深度分析/审稿"可能是净损失。
2. **V4 默认开启 thinking，且 thinking 下拒绝强制 tool_choice。** Pydantic AI 因此发 `tool_choice='auto'`，模型可能用散文回答而不调用输出工具；文档明说在 `deepseek-v4-pro` 上**这足以耗尽重试预算**——即"自动重试"不是免费兜底。

### 7.2 其它风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| **版本漂移** | Pydantic AI 相位 2.55.0 且正在 V1→V2 迁移；MAF 6 个月 21 个 minor 版本 | **锁版本**（`==`），升级前读 Migration Map |
| **`openai` 下限过低（真实炸弹）** | [pyproject.toml](pyproject.toml) 写 `openai>=1.0.0`，而 `pydantic-ai-slim` 要求 `openai>=3.26.0`。本机是 3.3.0 恰好满足，但**干净机器新装可能解析出 1.x** → 与 Pydantic AI 冲突 | 引入 Pydantic AI 的**同一次提交**里把 `openai` 下限抬到 `>=3.26.0` |
| **async 与 Textual 共存** | `run_sync()` 内部用 `loop.run_until_complete`，而 Textual 的 worker 是线程 | P1 的第一步就在 TUI 路径上**实测**，不要等全量迁移完才发现 |
| **依赖体积** | `pydantic-ai-slim[openai]` 是精简入口；全量包更大 | 选 slim |
| **checkpoint/持久化语义** | `pydantic-graph` 文档提及 persistence for pausing and resuming，但**具体语义我未核实** | P4 前先做 spike |
| **观测选型未定** | Langfuse（开源自托管）vs Logfire（Pydantic 商业服务，OTel） | 两者都支持 OpenTelemetry，可后置决定 |

### 7.3 反向条件：什么情况下**不该**选 Pydantic AI

- **需要微软/Azure 深度绑定**（Foundry 托管、Azure 身份、企业合规）→ 选 MAF，接受自己承担 DeepSeek 兼容坑
- **需要 LangGraph 那套现成能力**（deep agents、LangSmith 平台、庞大集成目录）→ 选 LangGraph，接受其 DAG 心智负担
- **完全不接受新依赖**（例如要求依赖面冻结）→ 纯 Python 加固，C 类靠手写校验器，接受其脆弱性
- **模型换成 OpenAI/Gemini**（`NativeOutput` 立刻可用）→ Pydantic AI 的价值**更大**，此时是最优解

---

## 8. 未验证事项（不是决策依据）

### 8.1 已补充核实（脚本直查 PyPI 元数据 + 本机 `.venv`）

| 事原 | 核实结果 | 判定 |
|---|---|---|
| Pydantic AI 是否支持 Python 3.14 | `pydantic-ai` / `-slim` / `-graph` 2.55.0 的 classifiers **均含 `3.14`**（3.11–3.14） | ✅ **无兼容性问题**（先前存疑已澄清） |
| pydantic 版本约束 | 要求 `pydantic>=2.12`；本机 **2.14.1** | ✅ 满足 |
| openai 版本约束 | 要求 `openai>=3.26.0`；本机 **3.3.0** | ✅ 满足 |
| httpx 依赖 | `pydantic-ai-slim` 依赖 `httpx2>=2.7`（非旧 `httpx`）；本机 **httpx2 2.13.1** | ✅ 满足（`httpx` 本机未装，但 slim 核心不依赖它） |
| 成本估算依赖 | `pydantic-ai-slim` **硬依赖 `genai-prices>=0.1.9`** | ✅ 该机制确实存在 |
| `pydantic-graph` 依赖面 | 仅 `pydantic>=2.12`——**确认可独立于 pydantic-ai 使用** | ✅ 印证 §5.2 |

> **⚠️ 一个必须同时做的依赖修正**：[pyproject.toml](pyproject.toml) 声明的是 `openai>=1.0.0`，而 `pydantic-ai-slim` 要求 `openai>=3.26.0`。本机恰好装的是 3.3.0（满足），但**在一台干净机器上按 `pyproject.toml` 全新安装可能解析出 1.x**，届时会与 Pydantic AI 冲突。**加 pydantic-ai 的同时把 `openai` 下限抬到 `>=3.26.0`。**

### 8.2 仍未验证（不是决策依据）

- **`run_sync()` 在 Textual worker 线程中的实际行为**（事件循环是否已在运行 → 是否抛 `RuntimeError`）。**这是 P1 的第一个 spike，必须先做。**
- **`genai-prices` 是否收录 DeepSeek 模型定价**——若不收录，`RunUsage.cost` 对这些请求**不计入总额**，则不能替代现有 `cost_tracker`。
- `Usage Limits` 的**具体参数名与语义**（仅从文档目录确认该特性存在，未读正文）。
- `pydantic-graph` 持久化的具体语义与恢复粒度。
- Langfuse 4.17.0 自托管的运维成本。
- 本文所有工期的**估算性质**（基于代码量，非实测）。

---

## 9. 参考来源

| 内容 | 来源 |
|---|---|
| `output_type` / 三种输出模式 / 输出校验与重试 | [Pydantic AI — Output](https://pydantic.dev/docs/ai/core-concepts/output/) |
| `run_sync()`、`RunUsage.cost`、`agent.iter()`、`pydantic-graph` 关系 | [Pydantic AI — Agents](https://pydantic.dev/docs/ai/core-concepts/agent/) |
| **DeepSeek 适配、strict Schema 仅 Responses API、thinking 与 tool_choice 冲突** | [Pydantic AI — DeepSeek](https://pydantic.dev/docs/ai/models/deepseek/) |
| `pydantic-graph` 状态机、类型推导出边、Mermaid 渲染 | [Pydantic AI — Graphs](https://pydantic.dev/docs/ai/graph/graph/) |
| LangChain/LangGraph 对照（Pydantic 官方视角，需折衷看待） | [Pydantic AI vs LangChain & LangGraph](https://pydantic.dev/docs/ai/comparisons/vs-langchain-langgraph/) |
| MAF 能力与 checkpoint 语义 | 原 `MAF-MIGRATION-PLAN.md` §2/§6.1（**该文件已不在仓库中**）。有效结论：MAF 的 graph workflow 与 checkpoint 设计对本项目**仍然成立**，但 DeepSeek 无定向适配是硬伤；迁移评估以本文 §5、§7 为准 |
| 版本号与 Python 支持 | PyPI: [pydantic-ai](https://pypi.org/project/pydantic-ai)、[agent-framework](https://pypi.org/project/agent-framework)、[langgraph](https://pypi.org/project/langgraph)、[langfuse](https://pypi.org/project/langfuse)、[openai-agents](https://pypi.org/project/openai-agents) |

---

*本文档为选型决策输入，不含任何已实施的代码改动。*
