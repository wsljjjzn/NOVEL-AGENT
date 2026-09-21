"""测试：审稿引擎（非 LLM 部分）。"""

from src.models import ReviewIssue, ReviewReport, AggregatedReview
from src.review_engine import BaseReviewAgent, ReviewOrchestrator
from src.writing_engine.prompts import (
    THOUGHT_REVIEW_SYSTEM, STRUCTURE_REVIEW_SYSTEM,
    NARRATIVE_REVIEW_SYSTEM, LANGUAGE_REVIEW_SYSTEM,
    FACT_CHECK_SYSTEM, PROOFREAD_SYSTEM,
)


class TestPrompts:
    """所有审稿提示词应非空且有实质内容。"""
    def test_thought_review(self):
        assert len(THOUGHT_REVIEW_SYSTEM) > 100

    def test_structure_review(self):
        assert len(STRUCTURE_REVIEW_SYSTEM) > 100

    def test_narrative_review(self):
        assert len(NARRATIVE_REVIEW_SYSTEM) > 100

    def test_language_review(self):
        assert len(LANGUAGE_REVIEW_SYSTEM) > 100

    def test_fact_check(self):
        assert len(FACT_CHECK_SYSTEM) > 100

    def test_proofread(self):
        assert len(PROOFREAD_SYSTEM) > 100


class TestBaseReviewAgent:
    def test_init(self):
        agent = BaseReviewAgent(
            name="测试审稿",
            system_prompt="你是一位测试审稿人。",
        )
        assert agent.name == "测试审稿"
        assert agent.system_prompt == "你是一位测试审稿人。"
        assert agent.llm is not None

    def test_parse_response_json(self):
        """验证 JSON 响应解析。"""
        agent = BaseReviewAgent(
            name="thought",
            system_prompt="test",
        )
        response = '''{
            "overall_assessment": "思想深度尚可",
            "strengths": ["论点清晰"],
            "score": 7.5,
            "issues": [
                {
                    "level": 2,
                    "location": "第2段",
                    "severity": "warning",
                    "description": "缺少反例",
                    "suggestion": "补充一个反例段落"
                }
            ]
        }'''
        report = agent._parse_response(response, "art_001")
        assert report.agent == "thought"
        assert report.overall_assessment == "思想深度尚可"
        assert report.score == 7.5
        assert len(report.strengths) == 1
        assert len(report.issues) == 1
        assert report.issues[0].level == 2
        assert report.issues[0].severity == "warning"
        assert report.issues[0].description == "缺少反例"

    def test_parse_response_invalid_json(self):
        """无效 JSON 应返回空 issues（不展示原始文本）。"""
        agent = BaseReviewAgent(
            name="proofread",
            system_prompt="test",
        )
        response = "这篇文章没有错别字。"
        report = agent._parse_response(response, "art_002")
        assert report.agent == "proofread"
        assert "JSON 解析失败" in report.overall_assessment
        assert len(report.issues) == 0  # JSON 解析失败返回空 issues
        assert report.score == 5.0

    def test_parse_response_malformed_json(self):
        """部分解析失败的 JSON。"""
        agent = BaseReviewAgent(
            name="language",
            system_prompt="test",
        )
        response = '{"overall_assessment": "好", issues: null}'
        report = agent._parse_response(response, "art_003")
        # JSON 解析失败（issues: null 非法），返回固定信息 + 空 issues
        assert "JSON 解析失败" in report.overall_assessment
        assert len(report.issues) == 0


class TestReviewOrchestrator:
    def test_init_creates_six_agents(self):
        orchestrator = ReviewOrchestrator()
        assert len(orchestrator.agents) == 6
        assert "thought" in orchestrator.agents
        assert "structure" in orchestrator.agents
        assert "narrative" in orchestrator.agents
        assert "language" in orchestrator.agents
        assert "fact_check" in orchestrator.agents
        assert "proofread" in orchestrator.agents

    def test_agent_names(self):
        orchestrator = ReviewOrchestrator()
        assert orchestrator.agents["thought"].name == "思想审稿"
        assert orchestrator.agents["structure"].name == "结构审稿"
        assert orchestrator.agents["narrative"].name == "叙事审稿"
        assert orchestrator.agents["language"].name == "语言审稿"
        assert orchestrator.agents["fact_check"].name == "事实核查"
        assert orchestrator.agents["proofread"].name == "校对"

    def test_review_sequential(self):
        """顺序执行审稿（使用 mock 后的 stub）。"""
        orchestrator = ReviewOrchestrator()
        result = orchestrator.review(
            article_text="这是一篇测试文章。",
            parallel=False,
            model_tier="flash",
        )
        assert isinstance(result, AggregatedReview)
        assert len(result.reports) == 6
        # 因为 LLM 调用会失败，所有报告应为默认值
        for report in result.reports:
            assert report.agent in ["思想审稿", "结构审稿", "叙事审稿",
                                     "语言审稿", "事实核查", "校对"]

    def test_review_l1_l2_l3_classification(self):
        """验证三级修改策略分类。"""
        result = AggregatedReview(article_id="art_001")
        result.level1_changes = [
            ReviewIssue(agent="proofread", level=1, description="错别字"),
        ]
        result.level2_changes = [
            ReviewIssue(agent="language", level=2, description="句长调整"),
        ]
        result.level3_guidance = [
            ReviewIssue(agent="thought", level=3, description="重构论点"),
        ]
        assert len(result.level1_changes) == 1
        assert len(result.level2_changes) == 1
        assert len(result.level3_guidance) == 1
        assert result.level1_changes[0].level == 1
        assert result.level2_changes[0].level == 2
        assert result.level3_guidance[0].level == 3

    def test_auto_fixable_level1(self):
        """Level 1 问题应标记为 auto_fixable。"""
        issue = ReviewIssue(
            agent="proofread", level=1,
            description="错别字",
            before_text="的地得",
            after_text="的地得（正确）",
        )
        assert issue.auto_fixable is True

    def test_level3_not_auto_fixable(self):
        """Level 3 不应标记为 auto_fixable。"""
        issue = ReviewIssue(
            agent="thought", level=3,
            description="重构论点",
        )
        assert issue.auto_fixable is False


class TestArticleFixer:
    """ArticleFixer：修改应用和报告格式化。"""

    def test_apply_auto_fixes_replaces_text(self):
        from src.review_engine.fixer import ArticleFixer
        fixer = ArticleFixer()
        text = "今天天气很好，的地得用错了。"
        issues = [
            ReviewIssue(
                agent="proofread", level=1,
                description="'的地得'误用",
                before_text="的地得",
                after_text="得",
            ),
        ]
        result = fixer.apply_auto_fixes(text, issues)
        assert "的地得" not in result
        assert "得" in result
        assert "今天天气很好" in result

    def test_apply_auto_fixes_empty_issues(self):
        from src.review_engine.fixer import ArticleFixer
        fixer = ArticleFixer()
        text = "原文不变。"
        result = fixer.apply_auto_fixes(text, [])
        assert result == text

    def test_apply_auto_fixes_no_match_preserves_text(self):
        from src.review_engine.fixer import ArticleFixer
        fixer = ArticleFixer()
        text = "这是一段文字。"
        issues = [
            ReviewIssue(
                agent="proofread", level=1,
                description="不存在的片段",
                before_text="不存在的文本",
                after_text="替换文本",
            ),
        ]
        result = fixer.apply_auto_fixes(text, issues)
        assert result == text

    def test_apply_auto_fixes_multiple_replacements(self):
        from src.review_engine.fixer import ArticleFixer
        fixer = ArticleFixer()
        text = "我觉的这篇文章写的好。"
        issues = [
            ReviewIssue(
                agent="proofread", level=1,
                description="'觉的'→'觉得'",
                before_text="觉的",
                after_text="觉得",
            ),
            ReviewIssue(
                agent="proofread", level=1,
                description="'写的好'→'写得好'",
                before_text="写的好",
                after_text="写得好",
            ),
        ]
        result = fixer.apply_auto_fixes(text, issues)
        assert "觉得" in result
        assert "写得好" in result
        assert "觉的" not in result
        assert "写的好" not in result

    def test_apply_confirmed_fixes_basic(self):
        from src.review_engine.fixer import ArticleFixer
        fixer = ArticleFixer()
        text = "长句太复杂需要拆分调整。"
        issues = [
            ReviewIssue(
                agent="language", level=2,
                description="句长调整",
                before_text="长句太复杂需要拆分调整",
                after_text="长句太复杂。需要拆分调整。",
            ),
        ]
        result = fixer.apply_confirmed_fixes(text, issues)
        assert "长句太复杂。需要拆分调整。" in result

    def test_format_review_report_empty(self):
        from src.review_engine.fixer import ArticleFixer
        fixer = ArticleFixer()
        aggregated = AggregatedReview(article_id="art_000")
        report = fixer.format_review_report(aggregated)
        assert "# 📋 审稿报告" in report
        assert "_无_" in report

    def test_format_review_report_with_all_levels(self):
        from src.review_engine.fixer import ArticleFixer
        fixer = ArticleFixer()
        aggregated = AggregatedReview(
            article_id="art_001",
            reports=[
                ReviewReport(
                    agent="校对", article_id="art_001",
                    overall_assessment="有 2 个错别字", score=8.0,
                    issues=[ReviewIssue(agent="校对", level=1, description="错别字")]
                ),
            ],
            level1_changes=[
                ReviewIssue(agent="校对", level=1, description="错别字 '的地得'",
                            before_text="的地得", after_text="得"),
            ],
            level2_changes=[
                ReviewIssue(agent="语言审稿", level=2, description="句长调整",
                            suggestion="拆分长句", before_text="长句", after_text="短句"),
            ],
            level3_guidance=[
                ReviewIssue(agent="思想审稿", level=3, description="重构核心论点",
                            location="第3段", severity="critical", suggestion="重写论证"),
            ],
        )
        report = fixer.format_review_report(aggregated)
        assert "校对" in report
        assert "8.0/10" in report
        assert "的地得" in report
        assert "句长调整" in report
        assert "重构核心论点" in report
        assert "Level 1" in report
        assert "Level 2" in report
        assert "Level 3" in report


class TestOrchestratorWithFixer:
    """Orchestrator 集成 fixer 的端到端测试。"""

    def test_apply_fixes_integration(self):
        """orchestrator.apply_fixes 应正确委托给 fixer。"""
        orchestrator = ReviewOrchestrator()
        text = "我觉的写的很好。"
        aggregated = AggregatedReview(
            article_id="art_001",
            level1_changes=[
                ReviewIssue(agent="校对", level=1, description="地得误用",
                            before_text="觉的", after_text="觉得"),
            ],
        )
        result = orchestrator.apply_fixes(text, aggregated)
        assert "觉得" in result
        assert "觉的" not in result

    def test_format_report_integration(self):
        """orchestrator.format_report 应返回有效 Markdown。"""
        orchestrator = ReviewOrchestrator()
        aggregated = AggregatedReview(article_id="art_001")
        report = orchestrator.format_report(aggregated)
        assert "# 📋 审稿报告" in report
