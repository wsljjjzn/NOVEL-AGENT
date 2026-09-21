"""
novel — 长篇小说写作系统。

模块：
- character_engine: 角色人格引擎（跨章节追踪）
- project_manager: 项目管理（章节/I/O/导出）
- chapter_writer: 逐章写作管线
"""

from .character_engine import CharacterEngine, CharacterProfile, ChapterEvent, PersonalityShift
from .project_manager import NovelProject, ChapterSummary, OutlineItem
from .chapter_writer import ChapterWriter
from .plot_engine import PlotEngine, ChapterPlot, Scene, WorldSetting

__all__ = [
    "CharacterEngine", "CharacterProfile", "ChapterEvent", "PersonalityShift",
    "NovelProject", "ChapterSummary", "OutlineItem",
    "ChapterWriter",
    "PlotEngine", "ChapterPlot", "Scene", "WorldSetting",
]
