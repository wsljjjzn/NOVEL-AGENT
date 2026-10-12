# 模块：`project_manager` — 项目持久化

## 负责

`data/projects/<名>/project.json` 的读写：章节正文、标题、大纲、开放伏笔、元数据。

**不负责**：角色（在 `characters.json`）、剧情设计（在 `plots.json`）。三者是**并列文件**，不互相引用。

## 对外接口

```python
class OutlineItem(BaseModel):          # pydantic v2（P1-2）
    chapter: int                       # 读盘时归一化：模型返回 "3" 也能读（建议 6）
    title: str
    expected_content: str              # 容忍 null（手工编辑过的存档不能让项目打不开）
    key_foreshadowing: list[str]
    # extra="allow"：未知键原样带走

class NovelProject:
    def __init__(self, name: str, base_dir: str = "data/projects")

    # 章节
    def add_chapter(self, number: int, title: str, content: str) -> None
    def get_chapter(self, number: int) -> str
    def list_chapters(self) -> list[ChapterSummary]

    # 大纲
    def set_outline(self, items: list[OutlineItem]) -> None

    # 伏笔
    def add_foreshadowing(self, text: str) -> None
    def resolve_foreshadowing(self, text: str) -> None

    # 上下文组装（零 LLM）
    def get_recap(self, before_chapter: int) -> str
    def get_outline_context(self) -> str

    # 持久化
    def save(self) -> None
    @classmethod
    def load(cls, base_dir: str, name: str) -> "NovelProject"
    def export_novel(self) -> str
```

## 存储格式

```json
{
  "name": "...", "title": "...", "description": "...", "genre": "...",
  "chapters": { "1": "正文…", "2": "…" },
  "chapter_titles": { "1": "标题" },
  "outline": [{ "chapter": 1, "title": "", "expected_content": "", "key_foreshadowing": [] }],
  "metadata": { "total_words": 88809, "chapter_count": 50 },
  "foreshadowing": ["未解伏笔…"]
}
```

**`chapters` / `chapter_titles` 的键是字符串**（JSON 限制），load 时转 int。

## 不变量

| # | 不变量 | 现状 |
|---|---|---|
| 1 | `chapters` / `chapter_titles` 的章号在内存中**一律 int** | ✅ `load` 做了 `int(k)` |
| 2 | `outline[].chapter` **一律 int** | ❌ **已知缺口，见下** |
| 3 | `metadata.total_words` == 所有章节字数之和 | ✅ `add_chapter` 维护 |
| 4 | `save` 是**原子**的 | ❌ **已知缺口，见下** |

## 已知陷阱

### ⚠️ 陷阱 1：`outline` 章号未归一化（**未修**）

`project_manager.py:186` 的 `outline` 解析**不做 int 归一化**，而 `chapters`（`:178`）与 `chapter_titles`（`:181`）都做了。

**后果**：模型返回 `"chapter": "3"`（字符串）会让 `list_chapters()` 的 `sorted(int + str)` 抛 `TypeError`，**TUI 章节页签与 `novel show` 一起挂**。同时所有 `o.chapter == chapter` 的查找失效。

**修法**：三处统一走一个 `_to_int_chapter()`。归在 P6 或独立修。

### ⚠️ 陷阱 2：`save` 非原子写

`project_manager.py:162` 是 `open(w)` + `json.dump`。写到一半被打断 → 下次 `load` 抛 `JSONDecodeError` → **项目完全打不开**。

**注意**：`character_engine.save` **已经是**原子写（`os.replace`），而本模块**不是**。两处不一致。

**修法**：改成与 `character_engine.save` 相同的临时文件 + `os.replace`。

### ⚠️ 陷阱 3：`_get_chapter_summary` 是取前 80 字

不是摘要，是**截断**。`get_recap` 依赖它，所以"前情提要"实际是"前 80 字的截断"。对连贯性有影响，但当前是设计如此——**改动前先确认是否需要真摘要**。

### 陷阱 4：`get_recap` 只取上一章结尾 200 字

`project_manager.py:110` 的 `content.strip()[-200:]`。对长章节可能截在半句话上。

## 测试

`tests/novel/test_project_manager.py`（P1 时新建，配合读写往返基线）。

**必测**：章号 int 归一化（三种输入：int / str / 缺失）、原子写（模拟中断后仍可读）、损坏文件不炸项目。
