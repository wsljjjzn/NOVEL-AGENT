"""
writing_engine — 写作引擎（板块二）。
"""

from .requirement_agent import RequirementAgent
from .outline_agent import OutlineAgent
from .writer_agent import SectionWriter, ArticleAssembler
from .orchestrator import WritingOrchestrator
from .knowledge_bridge import KnowledgeBridge
from .prompts import (
    REQUIREMENT_PARSER_SYSTEM,
    THOUGHT_STRUCTURE_SYSTEM,
    OUTLINE_GENERATOR_SYSTEM,
    SECTION_WRITER_SYSTEM,
    ARTICLE_ASSEMBLER_SYSTEM,
)

__all__ = [
    "RequirementAgent",
    "OutlineAgent",
    "SectionWriter",
    "ArticleAssembler",
    "WritingOrchestrator",
    "KnowledgeBridge",
]
