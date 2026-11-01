# 契约：全自动巡航舱 (Autopilot Stream) 流水线与事务规范

本文档定义全自动巡航批量写作流水线（Autopilot Stream）的服务契约、执行流转机制与原子事务快照回滚规范。

---

## 1. 架构定位：双轨互通模型 (Dual-Track)

系统在顶层划分为两大平级舱体：
- **工匠工作台 (Craft Studio)**：深度 Human-in-the-Loop 创作，内含 `企划构思`、`剧情棋盘`、`沉浸写作` 三大子视角，提供逐章细纲推敲、六维审稿雷达和角色状态微调。
- **全自动巡航舱 (Autopilot Stream)**：面向多章连续批量生成，闭环驱动「自动细纲推演 ➔ 剧情设计落盘 ➔ 正文撰写 ➔ 静默六维质检自修复 ➔ 角色演变与伏笔沉淀」。

两舱共享相同的底层小说工程数据（`project.json`、`characters.json`、`plots.json`），随时可通过「接管机制 (Takeover)」无缝切换。

---

## 2. 单章流水线执行契约 (`autopilot/step`)

### 输入参数 `AutopilotStepReq`
| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `chapter` | `int` | 必填 | 目标章号（$\ge 1$） |
| `target_words` | `int` | `2500` | 期望单章字数（纯正整数） |
| `model_tier` | `str` | `"pro"` | 推理档位（`flash` 或 `pro`） |
| `auto_outline` | `bool` | `True` | 细纲缺失时自动前瞻脑暴推进剧情节拍 |
| `silent_qa` | `bool` | `True` | 静默六维质检与自修复（跳过人工干预） |
| `auto_evolve` | `bool` | `True` | 自动推进人物演化与伏笔台账落盘 |
| `use_knowledge_base` | `bool` | `False` | 是否注入知识库检索上下文 |
| `knowledge_query` | `str` | `""` | 知识检索自定义关键词 |

### 单步执行闭环 (Sequential Steps)
1. **细纲与剧情对齐**：
   - 检查 `project.outline` 是否存在该章；若缺失且 `auto_outline=True`，根据小说世界观与前文摘要自动前瞻生成细纲并追加；
   - 检查 `plots.json` 是否存在该章剧情设计；若缺失，调用剧情引擎自动推演场景、伏笔埋设与回收并保存；
2. **正文撰写**：
   - 调用 `service.write_chapter` 生成正文并落盘；
   - 校验：空文本或异常即刻返回 `ok=False`，触发熔断停机，防止烧钱；
3. **静默质检与自动修复 (可选)**：
   - 若 `silent_qa=True`，执行六维质检打分；若发现硬伤，由模型执行自修复修润正文；
4. **角色与伏笔沉淀 (可选)**：
   - 若 `auto_evolve=True`，自动分析登场角色并确认状态跃迁，落盘到 `characters.json`。

---

## 3. 原子快照与回滚机制 (Snapshot Transaction)

为保障**“取消巡航不保存”**的铁律，巡航舱引入轻量物理快照机制：

1. **快照创建 (`autopilot/snapshot/create`)**：
   - 在巡航批次启动时调用；
   - 将小说项目的 `project.json`、`characters.json`、`plots.json` 备份到该项目目录下的 `.autopilot_snapshot/`；
2. **快照回滚 (`autopilot/snapshot/rollback`)**：
   - 在用户点击弹窗左侧【✕ 取消巡航 (不保存)】时调用；
   - 物理覆盖还原这三个文件，彻底丢弃本批次生成的一切章节正文、新大纲和角色演化，无损恢复至启动前状态；
   - 清理 `.autopilot_snapshot/` 目录；
3. **快照提交 (`autopilot/snapshot/commit`)**：
   - 在巡航批次全部完工交付或用户暂停接纳成果时调用；
   - 安全删除 `.autopilot_snapshot/` 目录，正式固化写入成果。

---

## 4. 失败与熔断语义
- 任何步骤失败均以结构化返回值 `ok=False, detail=...` 表达，禁止静默假成功；
- 发生连续失败或异常时，流水线主动挂起中断，并在前端弹出明确的告警说明。
