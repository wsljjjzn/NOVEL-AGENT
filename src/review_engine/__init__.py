"""
review_engine — 审稿引擎（板块三）。

六维并行审稿 + 三级修改；支持 article / novel 两套维度预设。
详见 docs/modules/review_engine.md。
"""

from .base_agent import BaseReviewAgent
from .orchestrator import (
    ReviewOrchestrator,
    ARTICLE_AGENTS,
    NOVEL_AGENTS,
    PROFILES,
)
from .fixer import ArticleFixer, FixOutcome
from .context import build_novel_context

__all__ = [
    "BaseReviewAgent",
    "ReviewOrchestrator",
    "ARTICLE_AGENTS",
    "NOVEL_AGENTS",
    "PROFILES",
    "ArticleFixer",
    "FixOutcome",
    "build_novel_context",
]
