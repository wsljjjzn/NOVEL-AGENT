# NOVEL-AGENT 目标架构关系图

> 文档性质：**目标态关系说明**。这是 P6-4 前留在根目录的设计文档（将移入 `docs/design/`）。
> ⚠️ 文中引用的 `MCP-ARCHITECTURE.md` 与 `MAF-MIGRATION-PLAN.md` **已不在仓库中**（详见文末说明）；其有效内容已并入本文、[TECH-STACK-SELECTION.md](TECH-STACK-SELECTION.md) 与 [docs/specs/](docs/specs/)。
> 本文回答：**按上述设计做完之后，各组件之间是什么关系。** 不含代码改动。

---

## 1. 一整张图

```
═══════════════════════════════════════════════════════════════════════════════
 驱动层（Driver）—— 三种驱动，两条通道，共用一套权限
═══════════════════════════════════════════════════════════════════════════════
  ① MCP 宿主              ② CLI (tui.py)          ③ TUI (Textual)
  (Claude/DSH/…)              │                        │
      │  MCP 协议             │                        │
      │  · tools/call         │                        │
      │  · resources/read     │                        │
      │  · prompts/get        │                        │
      │  · notifications/*    │                        │
      │                       │                        │
      │  sampling/createMessage                        │
      │  ◄──── 反向回调 ──────┘   （仅走 B1 档时使用）
      ▼                       ▼                        ▼
┌─────────────────────┐  ┌──────────────────────────────────┐
│  MCP Server 适配层   │  │  NovelService（编排层，纯 Python）│
│  · tools/list 声明   │─▶│  · 护栏：备份 / 只往后写 / 空即失败│
│  · A轨 / B轨 分流    │  │  · 跨步骤业务规则                 │
│  · isError 语义      │  │  · 不调 LLM，只调 Agent + 领域原语 │
└─────────────────────┘  └──────────────────────────────────┘
                                     │
═════════════════════════════════════│═══════════════════════════════════════
 调用层（LLM 出口）—— 唯一出口，18 个散点收敛到此
═════════════════════════════════════│═══════════════════════════════════════
                                     ▼
                    ┌────────────────────────────────┐
                    │  Pydantic AI Agent（每个能力一个）│
                    │  · output_type = 现有数据模型     │
                    │  · retries / UsageLimits         │
                    │  · model=None ← 运行时注入        │
                    └────────────────────────────────┘
                                     │  model= 参数（每次调用传入）
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
      MCPSamplingModel        OpenAI 兼容端点        其他 provider
      （走宿主，无 Key）      （deepseek/…/ollama）    （一行配置）
              │                      │                      │
              └──→ 三者都是 `Model` 子类，Agent 代码无差别 ←──┘
                                     │
                            返回：校验过的模型实例
                                    或 异常（不再有空对象）
                                     │
═════════════════════════════════════│═══════════════════════════════════════
 领域层（Domain）—— 零 LLM 依赖，完全不动
═════════════════════════════════════│═══════════════════════════════════════
                                     ▼
   ┌──────────────┬──────────────┬──────────────┬──────────────┐
   │CharacterEngine│ PlotEngine   │ NovelProject │ Preprocessing│
   │ 人格/关系/事件 │ 剧情/世界观   │ 持久化/导出   │ 切块/索引     │
   └──────────────┴──────────────┴──────────────┴──────────────┘
                                     │
                                     ▼
              data/projects/<name>/{project,characters,plots}.json
```

---

## 2. 三条核心关系（按重要性排序）

### 关系 A：唯一 LLM 出口 —— 从 18 个散点收敛到 1 层

**现状**：18 个 `.chat()` 调用点分布在 10 个模块（`character_engine` / `plot_engine` / `chapter_writer` / `deep` / `lightweight` / `base_agent` / `writer_agent` / `outline_agent` / `requirement_agent` / `character_analyzer`），各自手写 JSON 容错，12 处 `except` 有 4 种不同处理方式。

**目标态**：

```
所有生成性需求 ──→ 一个命名好的 Agent ──→ 一个 Model 实例
                        ↑
              这里是唯一需要写"如何处理失败"的地方
```

**这条关系为什么重要**：它把 C 类问题（12 处静默失败）从"每个调用点都要记得处理"变成"框架默认不给你空对象"。**你要么拿到一个校验过的 `ChapterPlot`，要么拿到一个异常——中间没有"空对象"这个状态可以静默传递。**

| 现有组件 | 目标态关系 |
|---|---|
| `llm_client.chat()` | **消失**。被 `Agent` 替代 |
| `llm_client._RateLimiter` | 由 `max_concurrency` 替代 |
| `llm_client` 的重试/退避 | 由 `retries` / 传输层重试替代 |
| `json_utils.safe_json_parse` / `find_json_in_text` | **消失**。`output_type` 做校验 |
| `base_agent._try_fix_truncated_json`（括号补齐） | **消失** |
| `character_engine._to_int_0_10` / `_as_str` / `_as_dict` | **改写成 `field_validator`**（同一件事的更规范写法） |
| `cost_tracker` | 由 `result.usage` 替代（多了 `cache_hit_ratio`） |

### 关系 B：采样的双向通道 —— MCP 服务器同时是"被调用"与"回调者"

这是最容易看错的一层。MCP 服务器与宿主之间是**双向**的：

```
宿主 ──tools/call──→ NOVEL-AGENT         （宿主驱动服务器：常规方向）
宿主 ←─sampling/createMessage── NOVEL-AGENT  （服务器请求宿主推理：反向）
```

要点：

1. **反向通道是"客户端能力"**。宿主必须在 `initialize` 时声明 `ClientCapabilities.sampling`，否则服务器不能假设它存在。
2. **反馈闭环**：`sampling/createMessage` 的参数里含 `maxTokens`、`systemPrompt`、`messages`；响应里含 **实际使用的模型名 `model`** 和 `stopReason`。**实际模型名可以回写进项目元数据做溯源**——这是"调用方指定模型"的额外红利。
3. **这张图里最重要的机制**：当 `output_type` 校验失败时，Pydantic AI 会把**校验错误连同 schema 一起回给模型重试**。在 MCP 场景下这意味着：
   - 宿主的 LLM 收到"你的 JSON 缺了 X 字段"的提示
   - **LLM 可以自我修正**
   - 而这个修正过程对 NOVEL-AGENT 是透明的

   这正是 CODE_REVIEW A1 那条"截断→解析失败→静默返回 0 个角色更新"的**结构性解药**：以前是"截断了就认命"，现在是"截断了就让模型补"。

4. **⚠️ 一个协议级陷阱**：MCP 工具级错误必须放在结果里并置 `isError: true`，**不能**用协议级错误响应。规范原话是否则 *"the LLM would not be able to see that an error occurred and self-correct"*。你的"假成功"问题若在新架构下违反这条，会**更难被发现**。

### 关系 C：三种驱动，共用一套权限与护栏

```
        MCP 宿主        CLI            TUI
            │            │              │
            └────────────┴──────────────┘
                         │
                  NovelService
                 （唯一编排 + 护栏）
```

**目标态里，A 类一致性由"三种驱动都必须经过 `NovelService`"来保证**，而不是靠自觉。具体约束：

| 驱动 | 允许做什么 | 禁止做什么 |
|---|---|---|
| MCP 服务器 | 调 `NovelService`、调 Agent、读写领域文件 | 自己实现一套编排 |
| CLI | 调 `NovelService` | 内联重写编排（**现在 CLI 有 4 处内联**） |
| TUI | 调 `NovelService` | 直接 new 领域引擎 |

**这条关系是 B 类问题的最终解**——但注意：**它不是框架给的，是架构纪律给的**。换任何底座都不会自动产生这条关系。

---

## 3. 组件级关系清单

| 组件 | 依赖谁 | 被谁依赖 | 目标态变化 |
|---|---|---|---|
| **MCP Server 适配层** | `NovelService`、`Agent`、`mcp` SDK | 宿主 | **新增** |
| **NovelService** | 领域引擎、`Agent` | MCP 层 / CLI / TUI | 保留；**删掉 4 份内联抄本** |
| **Agent 层** | `Model`（运行时注入）、pydantic 模型 | `NovelService`、MCP 层 | **新增**，替代 `llm_client.chat()` |
| **MCPSamplingModel** | `ServerSession` | `Agent`（作为 `model=` 参数） | **新增**，B1 档 |
| **Provider 配置**（models.yaml） | — | `Agent` 构造 | **新增**，B2 档 |
| **领域引擎 ×4** | 仅标准库 + pydantic | `NovelService`、MCP A 轨 | **完全不动** |
| **数据模型** | pydantic | `Agent.output_type` | 3 个 dataclass → pydantic |
| ~~`llm_client`~~ | — | — | **删除** |
| ~~`cost_tracker`~~ | — | — | **删除或降为薄封装** |
| ~~`json_utils` 的解析部分~~ | — | — | **删除** |
| ~~`api/gradio_app.py`~~ | — | — | **删除**（1083 行，已被项目标注暂停） |

---

## 4. A 轨 / B 轨的分流关系

MCP 工具按**是否调用 LLM** 分成两轨，这是"不强求"的落地：

```
宿主调 tools/call
        │
        ├─── A 轨：零 LLM ────────────────────────────────┐
        │    project_* / chapter_read / character_status    │
        │    foreshadowing_ledger / validate_chapter        │
        │    ★ build_chapter_prompt  ← 关键：备料不生成      │
        │                                                   │
        │    条件：无。任何宿主都能用                         │
        │    需要 Key：否    需要 sampling：否                │
        │                                                   │
        └─── B 轨：生成 ──────────────────────────────────┤
             generate_outline / design_characters /         │
             generate_chapter / review_article              │
                                                            │
             三档：B1 宿主 sampling（无 Key）                 │
                   B2 provider 配置（调用方指定）             │
                   B3 交还宿主（返回 prompt 包）              │
                                                            ▼
                                        data/projects/<name>/*.json
```

**关键关系：A 轨的 `build_chapter_prompt` 是 B3 档的载体。** 它返回一段拼装完整的 prompt（角色当前状态 + 前情提要 + 大纲 + 剧情设计 + 未解伏笔），宿主拿着直接生成即可。**这让 B3 从"降级方案"变成"天然可用的主路径"**——不依赖任何能力协商。

**上游约束**：A 轨工具**必须零 LLM 调用**。这是硬规则，因为它决定了 A 轨在"宿主不支持 sampling 且无 Key"时是否可用。

---

## 5. 护栏归属关系（谁负责挡住什么）

这是最容易在迁移中丢失的一层。逐条标注归属：

| 护栏 | 现在在哪 | 目标态归属 | 迁移风险 |
|---|---|---|---|
| 会话成本上限 | `llm_client` 预检（CNY） | `UsageLimits(cost_limit=…)`（**USD**） | ⚠️ **单位换算** |
| 用量记账 | `cost_tracker` | `result.usage` | 低 |
| RPM 限流 | `llm_client._RateLimiter` | `max_concurrency` | 低 |
| 输出校验重试 | 手写括号补齐（且写反） | `retries={'output': N}` | 低，且变强 |
| 覆盖前备份 `characters.json` | `NovelService.generate_characters` | **不变**（纯业务） | **CLI 仍在绕过** |
| 批量只往后写 | `NovelService.batch_write` | **不变** | **CLI 是内联复刻** |
| 空输出即失败 | `NovelService`（3 处） | **不变**；MCP 层加 `isError` | ⚠️ MCP 层是新缺口 |
| 三态失败语义 | `AnalysisOutcome` | **需显式适配** | ⚠️ **最高风险** |
| `tier` 参数透传 | 死参数（3 处） | `model=` 运行时注入 | 结构性修好 |

**三态语义那条要展开说**：`AnalysisOutcome` 区分 `ok` / `no_change` / `parse_failed` / `llm_failed`。Pydantic AI 是两态（实例 / 异常）。两者**可以互相表达**，但：

- "模型报告的角色为空" → `output_type` 的 `characters: list` 为空
- "解析失败" → 异常

**如果不显式写这个适配，A1 那个 bug 会在新底座里换个位置重新出现。**

---

## 6. 保持不变的东西（重要）

设计做完之后，**这些关系一个字都不变**：

| 关系 | 为什么不变 |
|---|---|
| 领域引擎 ↛ LLM | 它们本来就是纯确定性；这是本项目的核心资产 |
| `service.py` 是唯一编排层 | 换底座不动编排层（这正是第 4 轮的结论） |
| 数据落在 `data/projects/<name>/*.json` | 存储格式与底座无关 |
| `data/projects` 的 5 个真实项目 | 无需迁移 |
| 246 个测试的领域部分 | `test_character_engine.py` 的 50 个可保留 |
| HANDOVER 的三板块划分 | 板块一/二/三仍是功能分区，只是驱动方式变了 |

---

## 7. 关系层面的净收益

| 收益 | 来自哪条关系 |
|---|---|
| C 类（12 处静默失败）根治 | 关系 A：唯一出口 + 无"空对象"状态 |
| 模型无关 | 调用层：`model=` 运行时注入，三种 Model 子类无差别 |
| 不配 Key 也能用 | 关系 B：sampling 反向通道 |
| 批量写章不受确认弹窗阻塞 | 关系 B 的 B2 档 + A 轨备料 |
| 实际模型可溯源 | 关系 B：响应含 `model` 字段 |
| A 类一致性 | 关系 C + 删除 4 份内联抄本 |
| 不花钱就能端到端测试 | 调用层：`TestModel` + `defer_model_check` |
| 依赖面反而更小 | 删除 `llm_client` / `cost_tracker` / `json_utils` 解析部分 |

---

## 8. 未验证事项（影响关系成立与否）

- **`MCPSamplingModel` 在服务器进程内是否可用**——它设计给"服务器回调客户端"，但 Pydantic AI 侧的典型用法方向需实测。**这条若不成立，B1 档消失，只剩 B2/B3**（B3 仍可用，故整体方案不崩）。
- **MCP Python SDK 服务端发起 sampling 的确切 API**——`ServerSession` 的存在说明路径存在，方法名未核实。
- **`run_sync()` 与 Textual worker 线程共存**——`run_sync` 内部用 `loop.run_until_complete`，若该线程已有运行中的事件循环会抛异常。**这是 CLI/TUI 驱动路径成立的前提。**
- **`genai-prices` 是否收录 DeepSeek 定价**——不收录则 `RunUsage.cost` 为 `None`，护栏主键失效（注意 `None` 被设计为"未知"而非 0）。
- 目标宿主对 `modelPreferences` 的**实际尊重程度**（规范只说 MAY）。
- 宿主是否声明 `sampling` 能力——决定 B1 档是否可达。

---

## 9. 一页速记

```
驱动：MCP 宿主 / CLI / TUI        ← 三入口，一套权限
         │
编排：NovelService                 ← 纯 Python，唯一编排，护栏都在这
         │
调用：Agent(output_type=模型)      ← 唯一 LLM 出口，无空对象
         │  model= 运行时注入
模型：MCPSamplingModel / OpenAI 兼容 / 其他   ← 三者无差别
         │
领域：4 个引擎，零 LLM 依赖         ← 完全不动
         │
存储：data/projects/*.json         ← 不变
```

**四条关系线**：
1. 所有 LLM 调用 → 一个 Agent 层
2. MCP 双向（被调用 + 反向采样），校验失败可回模型自修
3. 三种驱动 → 同一个 `NovelService`
4. 领域层 → 零 LLM 依赖（架构的免疫系统）

---

*本文档为目标态关系说明，不含任何已实施的代码改动。*
