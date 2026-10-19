"""
review_engine.orchestrator — 审稿编排器。

并行运行六个维度并聚合结果，支持两套预设：
- `article`：非虚构文章（思想/结构/叙事/语言/事实核查/校对）
- `novel`：长篇小说（人物/设定/伏笔/节奏/语言/校对），可通过 `context` 注入作品状态

不变量见 docs/modules/review_engine.md：reports 长度恒等于维度数、失败维度显式占位、
score 只统计有效维度、预算耗尽不再穿透。
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.utils.llm_client import LLMClient
from src.utils.logger import logger
from src.utils.cost_tracker import (
    BudgetExceeded, get_tracker, PRICING, USD_TO_CNY,
)
from src.models import ReviewReport, ReviewIssue, AggregatedReview
from .base_agent import BaseReviewAgent
from .fixer import ArticleFixer
from .context import build_novel_context  # noqa: F401  （对外复用入口）
from ..writing_engine.prompts import (
    THOUGHT_REVIEW_SYSTEM,
    STRUCTURE_REVIEW_SYSTEM,
    NARRATIVE_REVIEW_SYSTEM,
    LANGUAGE_REVIEW_SYSTEM,
    FACT_CHECK_SYSTEM,
    PROOFREAD_SYSTEM,
    CHARACTER_REVIEW_SYSTEM,
    CONTINUITY_REVIEW_SYSTEM,
    FORESHADOW_REVIEW_SYSTEM,
    PACING_REVIEW_SYSTEM,
)


ARTICLE_AGENTS = {
    "thought": {"name": "思想审稿", "prompt": THOUGHT_REVIEW_SYSTEM},
    "structure": {"name": "结构审稿", "prompt": STRUCTURE_REVIEW_SYSTEM},
    "narrative": {"name": "叙事审稿", "prompt": NARRATIVE_REVIEW_SYSTEM},
    "language": {"name": "语言审稿", "prompt": LANGUAGE_REVIEW_SYSTEM},
    "fact_check": {"name": "事实核查", "prompt": FACT_CHECK_SYSTEM},
    "proofread": {"name": "校对", "prompt": PROOFREAD_SYSTEM},
}

NOVEL_AGENTS = {
    "character": {"name": "人物一致性", "prompt": CHARACTER_REVIEW_SYSTEM},
    "continuity": {"name": "设定连续性", "prompt": CONTINUITY_REVIEW_SYSTEM},
    "foreshadow": {"name": "伏笔回收", "prompt": FORESHADOW_REVIEW_SYSTEM},
    "pacing": {"name": "节奏", "prompt": PACING_REVIEW_SYSTEM},
    "language": {"name": "语言文风", "prompt": LANGUAGE_REVIEW_SYSTEM},
    "proofread": {"name": "校对", "prompt": PROOFREAD_SYSTEM},
}

PROFILES = {"article": ARTICLE_AGENTS, "novel": NOVEL_AGENTS}

# 中文约 1.5 字 / token；系统提示词与作品状态的粗略余量
_CHARS_PER_TOKEN = 1.5
_PROMPT_OVERHEAD_CHARS = 1200
# 仅在读不到 config.yaml 时使用（正常路径读档位配置，避免预算漂移）
_FALLBACK_MAX_TOKENS = {"flash": 16384, "pro": 16384}


def _dedupe_key(issue: ReviewIssue) -> str:
    """跨维度去重键：优先用锚点原文（同锚点=同位置），否则用规范化描述。"""
    before = re.sub(r'\s+', '', issue.before_text or "")
    if before:
        return "b:" + before
    desc = re.sub(r'[\s，。；、,.!?！？:：]', '', issue.description or "")
    return ("d:" + desc[:24]) if desc else ""


def _dedupe_issues(issues: list[ReviewIssue]) -> list[ReviewIssue]:
    """合并同一问题的多个维度报告：保留首个，其余记入 duplicated_by。"""
    seen: dict[str, ReviewIssue] = {}
    result: list[ReviewIssue] = []
    for issue in issues:
        key = _dedupe_key(issue)
        if key and key in seen:
            representative = seen[key]
            if issue.agent and issue.agent != representative.agent \
                    and issue.agent not in representative.duplicated_by:
                representative.duplicated_by.append(issue.agent)
            continue
        if key:
            seen[key] = issue
        result.append(issue)
    return result


class ReviewOrchestrator:
    """审稿编排器 — 六维并行审稿 + 三级修改策略。"""

    # 向后兼容：早期的类属性名
    AGENTS_CONFIG = ARTICLE_AGENTS

    def __init__(self, llm_client: Optional[LLMClient] = None, profile: str = "article"):
        self.llm = llm_client or LLMClient()
        self.profile = profile if profile in PROFILES else "article"
        self._agent_cache: dict[str, dict[str, BaseReviewAgent]] = {}
        self.agents = self._agents_for(self.profile)

    # ---- Agent 构建 ----

    def _build_agents(self, profile: str) -> dict[str, BaseReviewAgent]:
        config = PROFILES.get(profile) or ARTICLE_AGENTS
        return {
            key: BaseReviewAgent(
                name=cfg["name"],
                system_prompt=cfg["prompt"],
                llm_client=self.llm,
                key=key,
            )
            for key, cfg in config.items()
        }

    def _agents_for(self, profile: str) -> dict[str, BaseReviewAgent]:
        if profile not in self._agent_cache:
            self._agent_cache[profile] = self._build_agents(profile)
        return self._agent_cache[profile]

    # ---- 审稿 ----

    def review(self, article_text: str, article_id: str = "",
               parallel: Optional[bool] = None, model_tier: str = "pro",
               context: str = "", profile: Optional[str] = None) -> AggregatedReview:
        """执行完整审稿流程。

        Args:
            article_text: 正文
            article_id: 文章/章节 ID
            parallel: 是否并行（None 时读 config.review.parallel_agents）
            model_tier: 使用的模型层级
            context: 作品状态（小说向一致性核对用），见 build_novel_context
            profile: 维度预设（article/novel），默认用实例 profile

        Returns:
            聚合审稿结果（失败维度以 status="failed" 占位）
        """
        profile = profile if profile in PROFILES else self.profile
        agents = self._agents_for(profile)
        if parallel is None:
            parallel = bool(getattr(self._review_config(), "parallel_agents", True))

        logger.info(
            f"开始审稿: article_id={article_id}, profile={profile}, "
            f"parallel={parallel}, model_tier={model_tier}"
        )

        if parallel:
            reports = self._review_parallel(
                agents, article_text, article_id, model_tier, context,
            )
        else:
            reports = self._review_sequential(
                agents, article_text, article_id, model_tier, context,
            )
        return self._aggregate(reports, article_id, profile)

    @staticmethod
    def _review_config():
        try:
            from config.settings import get_config
            return getattr(get_config(), "review", None)
        except Exception:
            return None

    def _review_sequential(self, agents, article_text, article_id,
                           model_tier, context) -> list[ReviewReport]:
        reports: list[ReviewReport] = []
        budget_hit = False
        for agent in agents.values():
            if budget_hit:
                # 预算耗尽后不再发起新调用，但维度仍显式占位（不静默少 agent）
                reports.append(agent._failed_report(article_id, "预算耗尽，未执行"))
                continue
            try:
                reports.append(agent.review(
                    article_text, article_id, model_tier, context=context,
                ))
            except BudgetExceeded as e:
                logger.error(f"{agent.name} 因预算耗尽未执行: {e}")
                reports.append(agent._failed_report(article_id, f"预算耗尽：{e}"))
                budget_hit = True
            except Exception as e:
                logger.error(f"{agent.name} 审稿失败: {type(e).__name__}: {e}")
                reports.append(agent._failed_report(article_id, f"{type(e).__name__}: {e}"))
        return reports

    def _review_parallel(self, agents, article_text, article_id,
                         model_tier, context) -> list[ReviewReport]:
        # 预算前置检查：6 个 Pro 并发可一起越过逐调用预算闸（见文档 §4.8）
        self._assert_budget_for(self._estimate_cost(article_text, len(agents), model_tier))

        collected: dict[str, ReviewReport] = {}
        budget_error: Optional[BudgetExceeded] = None
        executor = ThreadPoolExecutor(max_workers=max(1, len(agents)))
        futures = {
            executor.submit(agent.review, article_text, article_id, model_tier, context=context): key
            for key, agent in agents.items()
        }
        try:
            for future in as_completed(futures):
                key = futures[future]
                try:
                    collected[key] = future.result()
                except BudgetExceeded as e:
                    budget_error = e
                    collected[key] = agents[key]._failed_report(article_id, f"预算耗尽：{e}")
                    break  # 不再等待，去取消还没启动的调用
                except Exception as e:
                    logger.error(f"{agents[key].name} 审稿失败: {type(e).__name__}: {e}")
                    collected[key] = agents[key]._failed_report(
                        article_id, f"{type(e).__name__}: {e}",
                    )
        finally:
            if budget_error is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            else:
                executor.shutdown(wait=True)

        # 保险：任何没有结果的维度都补失败占位，保证不静默少 agent
        for key, agent in agents.items():
            if key not in collected:
                collected[key] = agent._failed_report(article_id, "预算耗尽/已取消，未执行")
        return [collected[key] for key in agents]

    # ---- 预算 ----

    @staticmethod
    def _tier_max_tokens(model_tier: str) -> int:
        """读该档配置的 max_tokens；读不到才退回兜底值（避免与 config.yaml 漂移）。"""
        try:
            from config.settings import get_config
            cfg = get_config()
            tier_cfg = (
                cfg.llm.get(f"deepseek_v4_{model_tier}")
                or cfg.llm.get(model_tier)
                or next((v for k, v in cfg.llm.items() if k.endswith(f"_{model_tier}")), None)
            )
            if tier_cfg is not None:
                value = int(getattr(tier_cfg, "max_tokens", 0) or 0)
                if value > 0:
                    return value
        except Exception:
            pass
        return _FALLBACK_MAX_TOKENS.get(model_tier, 16384)

    @classmethod
    def _estimate_cost(cls, article_text: str, dimension_count: int, model_tier: str) -> float:
        """按最坏情况（输出吃满 max_tokens）粗估本次审稿费用（CNY）。

        思考也算在 max_tokens 里，所以这个上界不是"虚高"，是真实可能发生的用量。
        """
        price = PRICING.get(model_tier, PRICING["flash"])
        max_tokens = cls._tier_max_tokens(model_tier)
        prompt_tokens = (len(article_text or "") + _PROMPT_OVERHEAD_CHARS) / _CHARS_PER_TOKEN
        usd = dimension_count * (
            prompt_tokens * price["input"] + max_tokens * price["output"]
        ) / 1_000_000
        return usd * USD_TO_CNY

    @staticmethod
    def _assert_budget_for(estimated_cny: float) -> None:
        tracker = get_tracker()
        budget = getattr(tracker, "budget_cny", 0.0) or 0.0
        if budget <= 0:
            return
        remaining = budget - tracker.total_cost_cny
        if remaining < estimated_cny:
            raise BudgetExceeded(
                f"预计本次审稿最坏约 ¥{estimated_cny:.4f}，剩余预算仅 ¥{remaining:.4f}；"
                "为避免并发调用穿透预算闸，已提前中止。"
                "可调大 config.yaml budget.max_cny_per_session 或改用 flash 档。"
            )

    # ---- 聚合 ----

    def _aggregate(self, reports: list[ReviewReport], article_id: str,
                   profile: str) -> AggregatedReview:
        level1: list[ReviewIssue] = []
        level2: list[ReviewIssue] = []
        level3: list[ReviewIssue] = []
        for report in reports:
            for issue in report.issues:
                if issue.level == 1:
                    level1.append(issue)
                elif issue.level == 2:
                    level2.append(issue)
                else:
                    level3.append(issue)

        level1 = _dedupe_issues(level1)
        level2 = _dedupe_issues(level2)
        level3 = _dedupe_issues(level3)

        failed = [r for r in reports if r.status == "failed"]
        warnings: list[str] = []
        if failed:
            warnings.append(
                f"{len(failed)}/{len(reports)} 个维度失败（"
                + "、".join(r.agent for r in failed)
                + "），结论不代表全文已合格"
            )

        aggregated = AggregatedReview(
            article_id=article_id,
            profile=profile,
            reports=reports,
            level1_changes=level1,
            level2_changes=level2,
            level3_guidance=level3,
            warnings=warnings,
        )
        logger.info(
            f"审稿完成: {len(level1)} 个自动修改, {len(level2)} 个待确认, "
            f"{len(level3)} 个手动指引, 有效维度 {aggregated.coverage}"
        )
        return aggregated

    # ---- 修改应用 / 报告 ----

    def apply_fixes(self, article_text: str, aggregated: AggregatedReview,
                    apply_level2: bool = False) -> str:
        """应用审稿修改到文章，并把命中统计写回 aggregated。"""
        fixer = ArticleFixer()
        outcome = fixer.apply_auto_fixes_detailed(article_text, aggregated.level1_changes)
        aggregated.applied_fixes = outcome.applied
        aggregated.missed_fixes = outcome.missed
        aggregated.skipped_fixes = outcome.skipped
        if outcome.missed:
            aggregated.warnings.append(
                f"{outcome.missed} 处 Level 1 修改未命中锚点（原文可能已改动），未应用"
            )
        text = outcome.text
        if apply_level2:
            text = fixer.apply_confirmed_fixes(text, aggregated.level2_changes)
        return text

    def format_report(self, aggregated: AggregatedReview) -> str:
        """生成 Markdown 审稿报告。"""
        return ArticleFixer.format_review_report(aggregated)
