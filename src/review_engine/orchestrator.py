"""
review_engine.orchestrator — 审稿编排器，并行运行六 Agent 并聚合结果。
"""

from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils.llm_client import LLMClient
from src.utils.logger import logger
from src.utils.cost_tracker import BudgetExceeded
from src.models import ReviewReport, AggregatedReview
from .base_agent import BaseReviewAgent
from .fixer import ArticleFixer
from ..writing_engine.prompts import (
    THOUGHT_REVIEW_SYSTEM,
    STRUCTURE_REVIEW_SYSTEM,
    NARRATIVE_REVIEW_SYSTEM,
    LANGUAGE_REVIEW_SYSTEM,
    FACT_CHECK_SYSTEM,
    PROOFREAD_SYSTEM,
)


class ReviewOrchestrator:
    """审稿编排器 — 六 Agent 并行审稿 + 三级修改策略。"""

    AGENTS_CONFIG = {
        "thought": {"name": "思想审稿", "prompt": THOUGHT_REVIEW_SYSTEM},
        "structure": {"name": "结构审稿", "prompt": STRUCTURE_REVIEW_SYSTEM},
        "narrative": {"name": "叙事审稿", "prompt": NARRATIVE_REVIEW_SYSTEM},
        "language": {"name": "语言审稿", "prompt": LANGUAGE_REVIEW_SYSTEM},
        "fact_check": {"name": "事实核查", "prompt": FACT_CHECK_SYSTEM},
        "proofread": {"name": "校对", "prompt": PROOFREAD_SYSTEM},
    }

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.agents = {
            key: BaseReviewAgent(
                name=cfg["name"],
                system_prompt=cfg["prompt"],
                llm_client=self.llm,
            )
            for key, cfg in self.AGENTS_CONFIG.items()
        }

    def review(self, article_text: str, article_id: str = "",
               parallel: bool = True, model_tier: str = "pro") -> AggregatedReview:
        """执行完整审稿流程。

        Args:
            article_text: 文章全文
            article_id: 文章 ID
            parallel: 是否并行执行
            model_tier: 使用的模型层级

        Returns:
            聚合审稿结果
        """
        logger.info(f"开始审稿: article_id={article_id}, parallel={parallel}, model_tier={model_tier}")

        if parallel:
            reports = self._review_parallel(article_text, article_id, model_tier)
        else:
            reports = self._review_sequential(article_text, article_id, model_tier)

        # 按级别分类
        level1 = []
        level2 = []
        level3 = []

        for report in reports:
            for issue in report.issues:
                if issue.level == 1:
                    level1.append(issue)
                elif issue.level == 2:
                    level2.append(issue)
                else:
                    level3.append(issue)

        aggregated = AggregatedReview(
            article_id=article_id,
            reports=reports,
            level1_changes=level1,
            level2_changes=level2,
            level3_guidance=level3,
        )

        logger.info(f"审稿完成: {len(level1)} 个自动修改, "
                    f"{len(level2)} 个待确认, {len(level3)} 个手动指引")
        return aggregated

    def apply_fixes(self, article_text: str, aggregated: AggregatedReview,
                    apply_level2: bool = False) -> str:
        """应用审稿修改到文章。

        Args:
            article_text: 原始文章文本
            aggregated: 聚合审稿结果
            apply_level2: 是否同时应用 Level 2（默认仅 Level 1）

        Returns:
            修改后的文章文本
        """
        fixer = ArticleFixer()
        text = fixer.apply_auto_fixes(article_text, aggregated.level1_changes)
        if apply_level2:
            text = fixer.apply_confirmed_fixes(text, aggregated.level2_changes)
        return text

    def format_report(self, aggregated: AggregatedReview) -> str:
        """生成 Markdown 审稿报告。"""
        return ArticleFixer.format_review_report(aggregated)

    def _review_sequential(self, article_text: str, article_id: str,
                           model_tier: str) -> list[ReviewReport]:
        """顺序执行审稿。"""
        return [
            agent.review(article_text, article_id, model_tier)
            for agent in self.agents.values()
        ]

    def _review_parallel(self, article_text: str, article_id: str,
                         model_tier: str) -> list[ReviewReport]:
        """并行执行审稿。"""
        reports = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(agent.review, article_text, article_id, model_tier): name
                for name, agent in self.agents.items()
            }
            for future in as_completed(futures):
                try:
                    reports.append(future.result())
                except BudgetExceeded as e:
                    # 预算耗尽：中断整个审稿，不允许静默丢 Agent
                    raise e
                except Exception as e:
                    name = futures[future]
                    logger.error(f"{name} 审稿失败: {e}")
        return reports
