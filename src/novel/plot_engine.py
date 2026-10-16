"""
novel.plot_engine — 剧情引擎。

负责：
- 根据大纲生成详细剧情设计（每章的详细场景、转折、伏笔、人物出场）
- 剧情一致性检查
- 世界观设定维护
"""

import json

from src.utils.file_utils import atomic_write_json
from src.utils.llm_client import LLMClient
from src.utils.logger import logger


class Scene:
    """剧情中的一个场景。"""

    def __init__(
        self, order: int, location: str, characters: list[str], summary: str, purpose: str = ""
    ):
        self.order = order
        self.location = location
        self.characters = characters
        self.summary = summary
        self.purpose = purpose

    def to_dict(self):
        return {
            "order": self.order,
            "location": self.location,
            "characters": self.characters,
            "summary": self.summary,
            "purpose": self.purpose,
        }


class ChapterPlot:
    """单章剧情设计。"""

    def __init__(self, chapter_num: int, title: str = ""):
        self.chapter_num = chapter_num
        self.title = title
        self.scenes: list[Scene] = []
        self.opening_hook: str = ""  # 开篇钩子
        self.climax: str = ""  # 本章高潮
        self.ending_hook: str = ""  # 结尾钩子（承接下一章）
        self.foreshadowing_planted: list[str] = []  # 本章埋下的伏笔
        self.foreshadowing_resolved: list[str] = []  # 本章回收的伏笔
        self.character_appearances: dict[str, str] = {}  # {角色名: 出场方式}
        self.emotional_arc: str = ""  # 本章情感曲线
        self.user_notes: str = ""  # 用户编辑后的剧情笔记（手动修改）

    def to_dict(self) -> dict:
        return {
            "chapter": self.chapter_num,
            "title": self.title,
            "scenes": [s.to_dict() for s in self.scenes],
            "opening_hook": self.opening_hook,
            "climax": self.climax,
            "ending_hook": self.ending_hook,
            "foreshadowing_planted": self.foreshadowing_planted,
            "foreshadowing_resolved": self.foreshadowing_resolved,
            "character_appearances": self.character_appearances,
            "emotional_arc": self.emotional_arc,
            "user_notes": self.user_notes,
        }

    def to_prompt_text(self) -> str:
        """生成可直接嵌入写作 prompt 的剧情摘要。"""
        parts = [f"## 第{self.chapter_num}章剧情设计"]
        if self.opening_hook:
            parts.append(f"\n**开篇钩子**: {self.opening_hook}")

        if self.scenes:
            parts.append("\n**场景列表**:")
            for s in self.scenes:
                chars = "、".join(s.characters[:5]) if s.characters else "无"
                parts.append(f"  {s.order}. [{s.location}] {chars}: {s.summary}")
                if s.purpose:
                    parts.append(f"     目的: {s.purpose}")

        if self.climax:
            parts.append(f"\n**本章高潮**: {self.climax}")
        if self.ending_hook:
            parts.append(f"**结尾钩子**: {self.ending_hook}")
        if self.foreshadowing_planted:
            parts.append(f"\n**本章埋下的伏笔**: {'; '.join(self.foreshadowing_planted)}")
        if self.foreshadowing_resolved:
            parts.append(f"**本章回收的伏笔**: {'; '.join(self.foreshadowing_resolved)}")
        if self.character_appearances:
            parts.append("\n**角色出场**:")
            for name, method in self.character_appearances.items():
                parts.append(f"  - {name}: {method}")
        if self.emotional_arc:
            parts.append(f"\n**情感曲线**: {self.emotional_arc}")
        if self.user_notes.strip():
            parts.append(f"\n**用户补充要求（优先遵循）**: {self.user_notes.strip()}")

        return "\n".join(parts)


class WorldSetting:
    """世界观设定。"""

    def __init__(self):
        self.timeline: str = ""
        self.geography: str = ""
        self.power_system: str = ""  # 修炼体系/魔法体系/科技体系
        self.factions: list[str] = []
        self.custom_rules: list[str] = []  # 特殊规则
        self.notes: str = ""

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if k != "__pydantic_private__"}


class PlotEngine:
    """剧情引擎。"""

    PLOT_DESIGN_SYSTEM = """你是一位剧情设计师。请根据大纲条目，为指定章节设计详细剧情。

输出 JSON 格式：
{
  "opening_hook": "开篇钩子——本章开头如何吸引读者",
  "scenes": [
    {"order": 1, "location": "场景地点", "characters": ["角色1", "角色2"], "summary": "场景概要", "purpose": "此场景的剧情作用"}
  ],
  "climax": "本章最高潮的场景描述",
  "ending_hook": "结尾钩子——如何让读者想看下一章",
  "foreshadowing_planted": ["本章新埋的伏笔"],
  "foreshadowing_resolved": ["本章回收的伏笔（如果有）"],
  "character_appearances": {"角色名": "出场方式与作用"},
  "emotional_arc": "本章情感曲线（如：紧张→舒缓→高潮→余韵）"
}"""

    CHARACTER_SYSTEM_PROMPT = """你是一位角色设计师。请根据小说设定，生成完整的角色系统。

输出 JSON 格式：
{
  "characters": [
    {
      "name": "角色名",
      "role": "主角/反派/配角/路人",
      "personality": {"勇敢": 7, "善良": 5, "冲动": 8, "智慧": 6, "忠诚": 9},
      "speaking_style": "说话方式描述",
      "core_desire": "核心欲望",
      "core_fear": "核心恐惧",
      "background": "背景故事",
      "appearance": "外貌描述",
      "arc_summary": "角色弧线概述",
      "relationships": {"其他角色名": {"状态": "友好/敌对/暗恋/...", "强度": 5, "描述": "关系详情"}}
    }
  ],
  "world_building": {
    "timeline": "时间线",
    "geography": "地理",
    "power_system": "力量体系",
    "factions": ["势力1", "势力2"],
    "notes": "其他设定"
  }
}"""

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()
        self.plots: dict[int, ChapterPlot] = {}  # {章号: ChapterPlot}
        self.world = WorldSetting()

    def design_chapter_plot(
        self,
        chapter_num: int,
        outline_item: dict,
        prev_chapter_summary: str = "",
        existing_foreshadowing: list[str] | None = None,
        model_tier: str = "flash",
    ) -> ChapterPlot:
        """设计单章详细剧情。

        Args:
            chapter_num: 章号
            outline_item: {title, expected_content}
            prev_chapter_summary: 上一章内容摘要
            existing_foreshadowing: 当前开放的伏笔列表
            model_tier: 模型档位（A16：以前这里硬编码 flash，--tier pro 被静默忽略）

        Returns:
            ChapterPlot
        """
        prompt = (
            f"章号: {chapter_num}\n"
            f"章节标题: {outline_item.get('title', '')}\n"
            f"预期内容: {outline_item.get('expected_content', '')}\n"
        )
        if prev_chapter_summary:
            prompt += f"\n上一章摘要: {prev_chapter_summary[:500]}\n"
        if existing_foreshadowing:
            prompt += f"当前开放伏笔: {'; '.join(existing_foreshadowing)}\n"

        try:
            response = self.llm.chat(
                [
                    {"role": "system", "content": self.PLOT_DESIGN_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                model_tier=model_tier,
                temperature=0.5,
            )
            return self._parse_plot(response, chapter_num, outline_item.get("title", ""))
        except Exception as e:
            logger.warning(f"剧情设计失败: {e}")
            return ChapterPlot(chapter_num, outline_item.get("title", ""))

    def _parse_plot(self, response: str, chapter_num: int, title: str) -> ChapterPlot:
        from src.utils.json_utils import safe_json_parse

        data = safe_json_parse(response)
        if not data:
            return ChapterPlot(chapter_num, title)

        plot = ChapterPlot(chapter_num, title)
        plot.opening_hook = data.get("opening_hook", "")
        plot.climax = data.get("climax", "")
        plot.ending_hook = data.get("ending_hook", "")
        plot.foreshadowing_planted = data.get("foreshadowing_planted", [])
        plot.foreshadowing_resolved = data.get("foreshadowing_resolved", [])
        plot.character_appearances = data.get("character_appearances", {})
        plot.emotional_arc = data.get("emotional_arc", "")

        for s in data.get("scenes", []):
            plot.scenes.append(
                Scene(
                    order=s.get("order", len(plot.scenes) + 1),
                    location=s.get("location", ""),
                    characters=s.get("characters", []),
                    summary=s.get("summary", ""),
                    purpose=s.get("purpose", ""),
                )
            )

        self.plots[chapter_num] = plot
        return plot

    def design_characters(
        self,
        novel_title: str,
        genre: str,
        description: str,
        outline_text: str,
        model_tier: str = "flash",
    ) -> tuple[list[dict], WorldSetting]:
        """生成完整的角色系统。

        Args:
            model_tier: 模型档位（A16：以前这里硬编码 flash，--tier pro 被静默忽略）

        Returns:
            (字符列表, 世界观设定)
        """
        prompt = (
            f"小说: 《{novel_title}》\n类型: {genre}\n简介: {description}\n"
            f"\n大纲:\n{outline_text[:2000]}\n\n请设计完整的角色系统。"
        )

        try:
            response = self.llm.chat(
                [
                    {"role": "system", "content": self.CHARACTER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                model_tier=model_tier,
                temperature=0.5,
            )
        except Exception as e:
            logger.warning(f"角色系统生成失败: {e}")
            return [], self.world

        from src.utils.json_utils import safe_json_parse

        data = safe_json_parse(response)
        if not data:
            return [], self.world

        # 类型守卫：LLM 可能返回字符串而非预期的对象/列表
        wb = data.get("world_building", {})
        if isinstance(wb, str):
            logger.warning("world_building 是字符串而非对象，使用空设定")
            wb = {}
        self.world.timeline = wb.get("timeline", "")
        self.world.geography = wb.get("geography", "")
        self.world.power_system = wb.get("power_system", "")
        self.world.factions = wb.get("factions", [])
        self.world.notes = wb.get("notes", "")

        chars = data.get("characters", [])
        if not isinstance(chars, list):
            logger.warning("characters 字段类型异常，使用空列表")
            chars = []

        # 规范化 relationships: 字符串值 -> dict
        for c in chars:
            rels = c.get("relationships", {})
            if isinstance(rels, dict):
                for k, v in list(rels.items()):
                    if isinstance(v, str):
                        rels[k] = {"状态": v, "强度": 5, "起始章": 0}
            # 也规范化 description 字段
            desc = c.get("description")
            if isinstance(desc, dict):
                c["description"] = str(desc)

        return chars, self.world

    def to_dict(self) -> dict:
        return {
            "plots": {str(k): v.to_dict() for k, v in self.plots.items()},
            "world": self.world.to_dict(),
        }

    def save(self, path: str):
        atomic_write_json(path, self.to_dict())

    def load(self, path: str):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.plots = {}
        for k, v in data.get("plots", {}).items():
            plot = ChapterPlot(int(k), v.get("title", ""))
            plot.opening_hook = v.get("opening_hook", "")
            plot.climax = v.get("climax", "")
            plot.ending_hook = v.get("ending_hook", "")
            plot.foreshadowing_planted = v.get("foreshadowing_planted", [])
            plot.foreshadowing_resolved = v.get("foreshadowing_resolved", [])
            plot.character_appearances = v.get("character_appearances", {})
            plot.emotional_arc = v.get("emotional_arc", "")
            plot.user_notes = v.get("user_notes", "")
            for s in v.get("scenes", []):
                plot.scenes.append(
                    Scene(
                        order=s.get("order", 0),
                        location=s.get("location", ""),
                        characters=s.get("characters", []),
                        summary=s.get("summary", ""),
                        purpose=s.get("purpose", ""),
                    )
                )
            self.plots[int(k)] = plot
        wb = data.get("world", {})
        self.world.timeline = wb.get("timeline", "")
        self.world.geography = wb.get("geography", "")
        self.world.power_system = wb.get("power_system", "")
        self.world.factions = wb.get("factions", [])
        self.world.notes = wb.get("notes", "")
