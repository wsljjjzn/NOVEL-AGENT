"""
novel.project_manager — 长篇小说项目管理。

管理：
- 项目创建/加载/保存
- 章节管理（读、写、列表）
- 导出完整小说
"""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from src.utils.file_utils import atomic_write_json


def _project_path(base_dir: str, name: str) -> Path:
    """返回受项目根目录约束的项目路径，拒绝路径穿越与符号链接逃逸。"""
    if not isinstance(name, str) or not name or name != name.strip():
        raise ValueError("项目名不能为空，也不能包含首尾空白")
    candidate = Path(name)
    if name in {".", ".."} or len(candidate.parts) != 1 or candidate.name != name:
        raise ValueError("项目名必须是单个目录名，不能包含路径分隔符")

    root = Path(base_dir).resolve()
    target = (root / name).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("项目路径不能超出项目根目录") from exc
    return target


@dataclass
class ChapterSummary:
    """章节摘要。"""

    number: int
    title: str = ""
    status: str = "待写"  # 待写/已写/需修改
    word_count: int = 0
    summary: str = ""  # 一句话概要


class OutlineItem(BaseModel):
    """大纲条目（P1-2：类型声明交给 pydantic，读盘时自动归一化）。

    - `chapter` 会被夹成非负整数：模型返回 `"3"` 也能读，且**不再**让
      `list_chapters()` 的 `sorted(int + str)` 抛 TypeError（CODE_REVIEW 建议 6）。
    - `expected_content` 容忍 null/非字符串：手工编辑过的存档不能让项目打不开（A4）。
    - `extra="allow"`：不认识的键原样带走，不静默丢字段。
    """

    model_config = ConfigDict(extra="allow", validate_assignment=False)

    chapter: int = 0
    title: str = ""
    expected_content: str = ""
    key_foreshadowing: list[str] = []

    @field_validator("chapter", mode="before")
    @classmethod
    def _coerce_chapter(cls, value):
        if value is None or isinstance(value, bool):
            return 0
        try:
            return max(0, int(str(value).strip()))
        except (TypeError, ValueError):
            return 0

    @field_validator("title", "expected_content", mode="before")
    @classmethod
    def _coerce_text(cls, value):
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)

    @field_validator("key_foreshadowing", mode="before")
    @classmethod
    def _coerce_list(cls, value):
        if value is None:
            return []
        items = value if isinstance(value, list) else [value]
        return [str(item).strip() for item in items if str(item).strip()]


class NovelProject:
    """长篇小说项目。"""

    @staticmethod
    def project_path(base_dir: str, name: str) -> Path:
        """取得受根目录约束的项目路径，供服务层统一校验。"""
        return _project_path(base_dir, name)

    def __init__(self, name: str, base_dir: str = "data/projects"):
        self.name = name
        self.title = name
        self.description = ""
        self.genre = ""
        self.base_dir = _project_path(base_dir, name)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.chapters: dict[int, str] = {}  # {章号: 内容}
        self.chapter_titles: dict[int, str] = {}  # {章号: 标题}
        self.outline: list[OutlineItem] = []
        self.metadata: dict = {"total_words": 0, "chapter_count": 0}
        self.foreshadowing: list[str] = []  # 开放伏笔
        self.style_guide: dict | None = None  # 行文风格指南与范文片段（可选）

    # ---- 章节管理 ----

    def add_chapter(self, number: int, title: str, content: str):
        self.chapters[number] = content
        self.chapter_titles[number] = title
        if number > self.metadata.get("chapter_count", 0):
            self.metadata["chapter_count"] = number
        self.metadata["total_words"] = sum(len(c) for c in self.chapters.values())

    def get_chapter(self, number: int) -> str:
        return self.chapters.get(number, "")

    def delete_chapter(self, number: int) -> bool:
        """删除指定章节，同时清理正文、标题与对应大纲条目。"""
        existed = False
        if number in self.chapters:
            del self.chapters[number]
            existed = True
        if number in self.chapter_titles:
            del self.chapter_titles[number]
            existed = True
        orig_outline_len = len(self.outline)
        self.outline = [o for o in self.outline if o.chapter != number]
        if len(self.outline) != orig_outline_len:
            existed = True

        all_nums = list(self.chapters.keys()) + [o.chapter for o in self.outline]
        self.metadata["chapter_count"] = max(all_nums) if all_nums else 0
        self.metadata["total_words"] = sum(len(c) for c in self.chapters.values())
        return existed

    def list_chapters(self) -> list[ChapterSummary]:
        result = []
        for num in sorted(set(list(self.chapters.keys()) + [o.chapter for o in self.outline])):
            content = self.chapters.get(num, "")
            status = "已写" if content else "待写"
            result.append(
                ChapterSummary(
                    number=num,
                    title=self.chapter_titles.get(num, ""),
                    status=status,
                    word_count=len(content) if content else 0,
                    summary=self._get_chapter_summary(num, content),
                )
            )
        return result

    def _get_chapter_summary(self, num: int, content: str) -> str:
        """简单摘要：取前 80 字。"""
        if not content:
            return ""
        return content.strip()[:80].replace("\n", " ")

    # ---- 大纲管理 ----

    def set_outline(self, items: list[OutlineItem]):
        self.outline = items

    # ---- 伏笔管理 ----

    def add_foreshadowing(self, text: str):
        if text not in self.foreshadowing:
            self.foreshadowing.append(text)

    def resolve_foreshadowing(self, text: str):
        if text in self.foreshadowing:
            self.foreshadowing.remove(text)

    # ---- 前情提要 ----

    def get_recap(self, before_chapter: int) -> str:
        """生成第 N 章写作时的前情提要。"""
        parts = []
        # 上一章结尾
        prev_chapter = before_chapter - 1
        if prev_chapter in self.chapters:
            content = self.chapters[prev_chapter]
            # 取最后 200 字
            end_text = content.strip()[-200:]
            parts.append(f"**第{prev_chapter}章结尾**: {end_text}")

        # 关键事件（最近 3 章摘要）
        recent_nums = sorted([n for n in self.chapters if n < before_chapter])[-3:]
        for n in recent_nums:
            title = self.chapter_titles.get(n, "")
            summary = self._get_chapter_summary(n, self.chapters[n])
            if summary:
                parts.append(f"**第{n}章「{title}」**: {summary}")

        # 未解伏笔
        if self.foreshadowing:
            parts.append(f"**未解伏笔**: {'; '.join(self.foreshadowing[:5])}")

        return "\n".join(parts)

    # ---- 风格与范文指南（伴生 style_guide.json，零 LLM）----

    def set_style_guide(self, guide: dict) -> None:
        """设置小说的行文风格与参考范例指南。

        支持 dict 或具有 model_dump 方法的模型实例。
        """
        if hasattr(guide, "model_dump"):
            self.style_guide = guide.model_dump()
        elif isinstance(guide, dict):
            self.style_guide = guide
        else:
            raise TypeError("style_guide 必须是 dict 或可序列化模型")
        self.save_style_guide()

    def get_style_guide(self) -> dict | None:
        """获取当前绑定的风格指南。"""
        return self.style_guide

    def clear_style_guide(self) -> None:
        """清空风格指南并清理对应文件。"""
        self.style_guide = None
        self.save_style_guide()

    def save_style_guide(self) -> None:
        """原子保存 style_guide.json（为 None 时清理对应磁盘文件）。"""
        path = self.base_dir / "style_guide.json"
        if self.style_guide is not None:
            atomic_write_json(path, self.style_guide)
        elif path.exists():
            path.unlink(missing_ok=True)

    def get_style_context(self) -> str:
        """组装风格提示词（零 LLM）。"""
        if not self.style_guide:
            return ""
        guide = self.style_guide
        parts = ["## 行文风格与范文指引"]
        name = guide.get("template_name") or guide.get("name") or guide.get("style_name")
        if name:
            parts.append(f"- 参考风格: {name}")

        qual = guide.get("qualitative_profile") or {}
        tone = qual.get("tone") or guide.get("tone")
        if tone:
            parts.append(f"- 语言基调: {tone}")

        rules = guide.get("writing_rules") or guide.get("rules") or []
        if rules:
            parts.append("\n### 必须遵循的写作规则：")
            for r in rules:
                parts.append(f"- {r}")

        forbidden = guide.get("forbidden_patterns") or guide.get("forbidden_words") or []
        if forbidden:
            parts.append("\n### 禁止模式与忌用词：")
            parts.append(f"严禁出现以下词汇或套路：{', '.join(forbidden)}")

        samples = guide.get("representative_samples") or guide.get("few_shot_examples") or []
        if samples:
            parts.append("\n### 范文高光片段（请参考其叙事节奏与笔触）：")
            for i, s in enumerate(samples[:3], 1):
                if isinstance(s, dict):
                    stype = s.get("type", "片段")
                    snippet = s.get("text_snippet") or s.get("text") or ""
                else:
                    stype = "片段"
                    snippet = str(s)
                if snippet:
                    parts.append(f"【示例 {i} · {stype}】\n{snippet.strip()}")

        return "\n".join(parts)

    # ---- 大纲 prompt ----

    def get_outline_context(self) -> str:
        """生成大纲 prompt 需要的上下文。"""
        parts = []
        for item in self.outline:
            status = "已写" if item.chapter in self.chapters else "待写"
            parts.append(f"第{item.chapter}章「{item.title}」[{status}]: {item.expected_content}")
            if item.key_foreshadowing:
                parts.append(f"  伏笔: {'; '.join(item.key_foreshadowing)}")
        return "\n".join(parts) if parts else "暂无大纲"

    # ---- 持久化 ----

    def save(self):
        data = {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "genre": self.genre,
            "chapters": {str(num): content for num, content in self.chapters.items()},
            "chapter_titles": {str(num): title for num, title in self.chapter_titles.items()},
            "outline": [
                {
                    "chapter": o.chapter,
                    "title": o.title,
                    "expected_content": o.expected_content,
                    "key_foreshadowing": o.key_foreshadowing,
                }
                for o in self.outline
            ],
            "metadata": self.metadata,
            "foreshadowing": self.foreshadowing,
        }
        atomic_write_json(self.base_dir / "project.json", data)

    @classmethod
    def load(cls, base_dir: str, name: str):
        path = _project_path(base_dir, name) / "project.json"
        if not path.exists():
            raise FileNotFoundError(f"项目不存在: {path}")

        data = json.loads(path.read_text("utf-8"))
        project = cls(name, base_dir)

        project.title = data.get("title", name)
        project.description = data.get("description", "")
        project.genre = data.get("genre", "")
        project.chapters = {int(k): v for k, v in data.get("chapters", {}).items()}
        project.chapter_titles = {int(k): v for k, v in data.get("chapter_titles", {}).items()}
        project.outline = [
            OutlineItem(
                chapter=o.get("chapter", 0),
                title=o.get("title", ""),
                expected_content=o.get("expected_content", ""),
                key_foreshadowing=o.get("key_foreshadowing", []),
                # 未知键原样带走：手工编辑/新版写出的字段不能在读盘时消失
                **{k: v for k, v in o.items() if k not in OutlineItem.model_fields},
            )
            for o in data.get("outline", [])
            if isinstance(o, dict)
        ]
        project.metadata = data.get("metadata", {})
        project.foreshadowing = data.get("foreshadowing", [])

        style_file = project.base_dir / "style_guide.json"
        if style_file.exists():
            try:
                project.style_guide = json.loads(style_file.read_text("utf-8"))
            except Exception:
                project.style_guide = None

        return project

    def export_novel(self) -> str:
        """导出完整小说文本。"""
        lines = [f"# {self.title}", "", f"*{self.genre}* — {self.description}", "", "---", ""]
        for num in sorted(self.chapters.keys()):
            title = self.chapter_titles.get(num, f"第{num}章")
            lines.append(f"## 第{num}章 {title}")
            lines.append("")
            lines.append(self.chapters[num])
            lines.append("")
        return "\n".join(lines)

    @classmethod
    def list_projects(cls, base_dir: str = "data/projects") -> list[str]:
        p = Path(base_dir)
        if not p.exists():
            return []
        return [d.name for d in p.iterdir() if d.is_dir() and (d / "project.json").exists()]

    @classmethod
    def delete(cls, base_dir: str, name: str) -> bool:
        """删除项目目录（不可恢复）。"""
        import shutil
        try:
            path = _project_path(base_dir, name)
        except ValueError:
            return False
        if not path.exists():
            return False
        shutil.rmtree(path)
        return True
