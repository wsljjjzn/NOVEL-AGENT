# 模块：`plot_engine` — 剧情引擎

## 负责

`data/projects/<名>/plots.json` 的读写，以及**单章剧情设计**与**世界观设定**。

## 对外接口

```python
class ChapterPlot:
    chapter_num: int; title: str
    scenes: list[Scene]
    opening_hook: str            # 开篇钩子
    climax: str                  # 本章高潮
    ending_hook: str             # 结尾钩子
    foreshadowing_planted: list[str]
    foreshadowing_resolved: list[str]
    character_appearances: dict[str, str]   # {角色名: 出场方式} ★ 给角色引擎筛选用
    emotional_arc: str
    user_notes: str              # 用户手写笔记

    def to_prompt_text(self) -> str    # 进写作 prompt

class PlotEngine:
    def design_chapter_plot(self, chapter_num, outline_item,
                            prev_chapter_summary="",
                            existing_foreshadowing=None) -> ChapterPlot
    def design_characters(self, novel_title, genre, description,
                          outline_text) -> tuple[list[dict], WorldSetting]
    def save(self, path: str) -> None
    def load(self, path: str) -> None
```

## 不变量

| # | 不变量 | 保障 |
|---|---|---|
| 1 | `character_appearances` 是角色引擎 `focus` 参数的数据源 | 由 `service` 与 CLI 传入 |
| 2 | `plots.json` 的末态由**每次 `service` 操作重新 load** | service 无状态设计 |
| 3 | `user_notes` 会进入本章写作提示，且明确标为优先要求 | `ChapterPlot.to_prompt_text()` |
| 4 | `plots.json` 保存是原子的 | 同目录临时文件写完后 `os.replace` |

## 已知陷阱

### 用户剧情笔记

TUI、Gradio 与 `service.save_plot_notes` 写入的 `user_notes` 会由 `to_prompt_text()` 追加到本章剧情设计中，并标记为“用户补充要求（优先遵循）”。因此用户手写的剧情安排会随 `NovelService.write_chapter()` 进入模型提示。

### ⚠️ 陷阱 2：`model_tier` 硬编码（死参数）

`design_chapter_plot`（`:187`）与 `design_characters`（`:239`）**签名里没有 `tier`**，内部硬编码 `model_tier="flash"`。

但上层的日志与界面会显示"正在用 pro 生成…"——**用户永远无法用 pro 生成角色系统，而界面告诉他用了**。

**归 P5-2 修**：改为运行时注入模型。

### 陷阱 3：prompt 模板里的示例值会污染数据

`CHARACTER_SYSTEM_PROMPT` 的关系示例写了 `"强度": 5`，模型照抄 → **初始生成的关系强度几乎全是 5**。

**原则**：prompt 里的示例值会被当真。要么用占位符，要么接受它会污染。

同类问题：`personality` 示例给了 5 个维度（勇敢/善良/冲动/智慧/忠诚），导致**大量角色共享同一组维度**。

### 陷阱 4：`design_characters` 的签名没有 tier，且返回值是裸 dict

返回 `list[dict]` 而非 `list[CharacterProfile]`——所以**服务层要手写字段映射**。P1 后应返回 pydantic 模型。

### 陷阱 5：`WorldSetting` 未被使用

`design_characters` 返回世界观，但**没有任何下游消费者**（`service.generate_characters` 用 `_world` 丢弃）。目前是死数据。

## 测试

`tests/novel/test_plot_engine.py`。**注意**：现有用例多数把生产逻辑抄进测试再断言（如自己写一遍 `if isinstance(wb, str): wb = {}` 再断言），**测的是测试自己**。P1 时应重写为调用真实函数。
