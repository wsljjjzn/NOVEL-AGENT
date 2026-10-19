"""测试：审稿引擎的失败语义 / fixer 正确性 / 小说向预设与状态注入。"""

from src.models import ReviewIssue, ReviewReport, AggregatedReview
from src.review_engine import (
    ArticleFixer,
    ReviewOrchestrator,
    build_novel_context,
    ARTICLE_AGENTS,
    NOVEL_AGENTS,
    PROFILES,
)
from src.review_engine.base_agent import BaseReviewAgent, _safe_int_level


# ========== A. 诚实失败语义与容错 ==========

class TestFailureSemantics:
    def test_level_labels_are_recognized(self):
        assert _safe_int_level("Level 1") == 1
        assert _safe_int_level("level 3") == 3
        assert _safe_int_level("L2") == 2
        assert _safe_int_level("级别2") == 2
        assert _safe_int_level("第1级") == 1
        assert _safe_int_level("严重") == 1
        assert _safe_int_level("建议") == 3
        assert _safe_int_level("无法判断") == 2  # 兜底

    def test_zero_score_is_preserved(self):
        agent = BaseReviewAgent(name="语言审稿", system_prompt="t")
        report = agent._parse_response('{"score": 0, "issues": []}', "a")
        assert report.status == "ok"
        assert report.score == 0.0

    def test_out_of_range_score_is_clamped_not_crashing(self):
        agent = BaseReviewAgent(name="语言审稿", system_prompt="t")
        report = agent._parse_response('{"score": 85, "issues": []}', "a")
        assert report.status == "ok"
        assert report.score == 10.0

    def test_level_label_keeps_auto_fixable(self):
        agent = BaseReviewAgent(name="校对", system_prompt="t")
        response = (
            '{"score": 8, "issues": [{"level": "Level 1", "description": "错别字",'
            ' "before_text": "的地得", "after_text": "得"}]}'
        )
        report = agent._parse_response(response, "a")
        assert report.issues[0].level == 1
        assert report.issues[0].auto_fixable is True

    def test_failed_statistics_exclude_failed_dimensions(self):
        ok = ReviewReport(agent="语言审稿", status="ok", score=8.0)
        failed = ReviewReport(agent="校对", status="failed", error="API 不可用", score=0.0)
        aggregated = AggregatedReview(reports=[ok, failed])
        assert aggregated.overall_score == 8.0
        assert aggregated.coverage == "1/2"
        assert [r.agent for r in aggregated.failed_reports] == ["校对"]


# ========== B. fixer 正确性 ==========

class TestFixerCorrectness:
    def _issue(self, before, after, description="测试"):
        return ReviewIssue(agent="校对", level=1, description=description,
                           before_text=before, after_text=after)

    def test_whitespace_normalized_anchor_maps_to_original_offsets(self):
        """归一化匹配必须映射回原文下标，不能把修复插到文章开头。"""
        text = "开头段落。\n\n我觉的\n\n这里有问题。\n\n结尾段落。"
        before = "我觉的 这里有问题"  # 与原文空白不同，只能走归一化匹配
        outcome = ArticleFixer.apply_auto_fixes_detailed(text, [self._issue(before, "我觉得这里有问题")])
        assert outcome.applied == 1
        assert "我觉得这里有问题" in outcome.text
        assert outcome.text.startswith("开头段落。")
        assert outcome.text.endswith("结尾段落。")
        assert "开头段落。我觉得" not in outcome.text

    def test_degenerate_single_char_anchor_is_skipped(self):
        text = "的的的的"
        outcome = ArticleFixer.apply_auto_fixes_detailed(text, [self._issue("的", "得")])
        assert outcome.skipped == 1
        assert outcome.applied == 0
        assert outcome.text == text

    def test_unique_single_char_anchor_is_applied(self):
        text = "独一无二的错字"
        outcome = ArticleFixer.apply_auto_fixes_detailed(text, [self._issue("字", "词")])
        assert outcome.applied == 1
        assert outcome.text == "独一无二的错词"

    def test_detailed_outcome_counts_hits_and_misses(self):
        text = "我觉的写得很好。"
        outcome = ArticleFixer.apply_auto_fixes_detailed(text, [
            self._issue("觉的", "觉得", "命中"),
            self._issue("根本不存在的片段", "x", "未命中"),
        ])
        assert outcome.applied == 1
        assert outcome.missed == 1
        assert "觉得" in outcome.text

    def test_legacy_str_signature_still_works(self):
        text = "我觉的写得很好。"
        result = ArticleFixer.apply_auto_fixes(text, [self._issue("觉的", "觉得")])
        assert isinstance(result, str)
        assert "觉得" in result

    def test_apply_fixes_records_accounting(self):
        orchestrator = ReviewOrchestrator()
        aggregated = AggregatedReview(level1_changes=[
            self._issue("觉的", "觉得", "命中"),
            self._issue("不存在片段", "x", "未命中"),
        ])
        result = orchestrator.apply_fixes("我觉的写得很好。", aggregated)
        assert "觉得" in result
        assert aggregated.applied_fixes == 1
        assert aggregated.missed_fixes == 1
        assert any("未命中" in w for w in aggregated.warnings)


# ========== C. 小说向预设与状态注入 ==========

class TestNovelProfile:
    def test_profiles_contain_both_presets(self):
        assert set(PROFILES) == {"article", "novel"}
        assert set(ARTICLE_AGENTS) == {
            "thought", "structure", "narrative", "language", "fact_check", "proofread",
        }
        assert set(NOVEL_AGENTS) == {
            "character", "continuity", "foreshadow", "pacing", "language", "proofread",
        }

    def test_novel_profile_builds_six_agents(self):
        orchestrator = ReviewOrchestrator(profile="novel")
        assert set(orchestrator.agents) == set(NOVEL_AGENTS)
        assert orchestrator.agents["character"].name == "人物一致性"

    def test_switching_profile_per_call_rebuilds_agents(self):
        orchestrator = ReviewOrchestrator()  # 默认 article
        assert "thought" in orchestrator.agents
        assert "character" in orchestrator._agents_for("novel")

    def test_context_injected_into_user_message(self):
        agent = BaseReviewAgent(name="人物一致性", system_prompt="t", key="character")
        content = agent._build_user_content("正文", context="林雪：谨慎8/10")
        assert "【作品状态" in content
        assert "林雪" in content
        assert "请审阅以下正文" in content

    def test_review_passes_context_to_agent_messages(self):
        captured = {}

        class FakeLLM:
            def chat(self, messages, model_tier="flash", temperature=None,
                     max_tokens=None, timeout=None, thinking=None, json_mode=False):
                captured["messages"] = messages
                captured["thinking"] = thinking
                captured["json_mode"] = json_mode
                return '{"score": 7, "issues": []}'

        orchestrator = ReviewOrchestrator(llm_client=FakeLLM(), profile="novel")
        result = orchestrator.review("正文内容", parallel=False, context="作品状态X")
        assert result.reports
        assert all(r.status == "ok" for r in result.reports)
        user_message = captured["messages"][1]["content"]
        assert "作品状态X" in user_message
        assert "正文内容" in user_message
        assert result.profile == "novel"

    def test_build_novel_context_includes_domain_state(self):
        class FakeChar:
            name = "林雪"
            role = "主角"
            core_desire = "复仇"
            core_fear = "失去"
            speaking_style = "冷淡"
            relationships = {"陈默": {"强度": 7, "状态": "信任"}}

            def personality_summary(self):
                return "谨慎8/10"

            def sorted_events(self):
                return []

        class FakeEngine:
            def all_characters(self):
                return [FakeChar()]

        class FakeWorld:
            timeline = "架空古代"
            geography = "北境"
            power_system = "灵气"
            factions = ["宗门"]
            custom_rules = []

        class FakePlot:
            world = FakeWorld()

        class FakeProject:
            title = "雪山"
            name = "雪山"
            genre = "玄幻"
            description = "一个复仇故事"
            outline = []
            foreshadowing = ["血玉的秘密"]

            def get_recap(self, chapter_num):
                return "上一章他活着。"

        context = build_novel_context(
            project=FakeProject(), engine=FakeEngine(), plot=FakePlot(), chapter_num=3,
        )
        assert "林雪" in context
        assert "血玉的秘密" in context
        assert "一个复仇故事" in context
        assert "北境" in context

    def test_build_novel_context_tolerates_missing_state(self):
        assert build_novel_context() == ""


# ========== D. 聚合增强 ==========

class TestAggregation:
    def test_dedupe_merges_same_anchor_across_dimensions(self):
        orchestrator = ReviewOrchestrator()
        a = ReviewIssue(agent="校对", level=1, description="的地得",
                        before_text="的地得", after_text="得")
        b = ReviewIssue(agent="语言文风", level=1, description="的地得误用",
                        before_text="的地得", after_text="得")
        report_a = ReviewReport(agent="校对", status="ok", score=8.0, issues=[a])
        report_b = ReviewReport(agent="语言文风", status="ok", score=6.0, issues=[b])
        aggregated = orchestrator._aggregate([report_a, report_b], "art_1", "novel")
        assert len(aggregated.level1_changes) == 1
        assert aggregated.level1_changes[0].duplicated_by == ["语言文风"]

    def test_failed_dimensions_produce_warning(self):
        orchestrator = ReviewOrchestrator()
        ok = ReviewReport(agent="校对", status="ok", score=9.0)
        failed = ReviewReport(agent="节奏", status="failed", error="超时", score=0.0)
        aggregated = orchestrator._aggregate([ok, failed], "art_1", "novel")
        assert aggregated.warnings
        assert "节奏" in aggregated.warnings[0]

    def test_parallel_review_always_returns_six_reports(self):
        """任一维度失败也要占位，绝不静默少 agent（测试环境无真实调用）。"""
        orchestrator = ReviewOrchestrator()
        result = orchestrator.review("这是一段测试正文。", parallel=True, model_tier="flash")
        assert len(result.reports) == 6
        assert len(result.failed_reports) == 6
        assert result.overall_score == 0.0
        assert result.warnings

    def test_report_marks_failed_dimension(self):
        ok = ReviewReport(agent="语言审稿", status="ok", score=8.0)
        failed = ReviewReport(agent="校对", status="failed", error="API 不可用", score=0.0)
        aggregated = AggregatedReview(reports=[ok, failed], article_id="a")
        report = ArticleFixer.format_review_report(aggregated)
        assert "❌ 审稿失败" in report
        assert "有效维度**: 1/2" in report


# ========== E. thinking 与输出预算（2026-10-13 线上事故回归） ==========

class TestThinkingAndOutputBudget:
    """V4 默认开思考，思考**先于**正文吃 max_tokens。

    事故形状：flash 档审稿 6 维里 4 维失败并报「JSON 解析失败」，
    实测 completion=4096、content=""。处置方式是**保留思考、把预算加够**，
    再给审稿加 json_object 输出模式（思考开着时模型可能改写成散文）。
    """

    def test_review_keeps_thinking_on_and_requests_json_mode(self):
        from src.review_engine.base_agent import REVIEW_JSON_MODE
        captured = {}

        class FakeLLM:
            def chat(self, messages, model_tier="flash", temperature=None,
                     max_tokens=None, timeout=None, thinking=None, json_mode=False):
                captured["thinking"] = thinking
                captured["json_mode"] = json_mode
                return '{"score": 7, "issues": []}'

        agent = BaseReviewAgent(name="校对", system_prompt="t", llm_client=FakeLLM())
        report = agent.review("正文", "a", model_tier="flash")
        assert report.status == "ok"
        assert REVIEW_JSON_MODE is True
        assert captured["json_mode"] is True, "审稿必须约束成 JSON 输出"
        assert captured["thinking"] is None, "思考保持档位默认（开），不按次关掉"

    def test_configured_budget_can_hold_thinking(self):
        """两档 max_tokens 必须容得下「思考 + 正文」——实测单维审稿需 6k~13k。"""
        from config.settings import get_config
        cfg = get_config()
        for tier in ("flash", "pro"):
            tier_cfg = cfg.llm.get(f"deepseek_v4_{tier}") or cfg.llm.get(tier)
            assert tier_cfg is not None, f"缺少档位配置：{tier}"
            assert tier_cfg.thinking is True, f"{tier} 的思考应保持开启"
            assert tier_cfg.max_tokens >= 12288, (
                f"{tier} 的 max_tokens={tier_cfg.max_tokens} 装不下思考 + 正文"
                "（实测单维审稿需 6k~13k tokens）"
            )

    def test_empty_response_is_reported_as_empty_not_json_error(self):
        class EmptyLLM:
            def chat(self, messages, model_tier="flash", **kwargs):
                return ""

        agent = BaseReviewAgent(name="校对", system_prompt="t", llm_client=EmptyLLM())
        report = agent.review("正文", "a")
        assert report.status == "failed"
        assert "未返回任何内容" in report.error
        assert "JSON 解析失败" not in report.error

    def test_truncated_json_repair_ignores_brackets_inside_strings(self):
        from src.review_engine.base_agent import _try_fix_truncated_json
        # 字符串里带 [ ]：旧的 count() 实现会多补一个 ]，补出非法 JSON
        truncated = '{"score": 8, "issues": [{"description": "看到 [信号] 时", "level": 1'
        data = _try_fix_truncated_json(truncated)
        assert data is not None, "字符串里的方括号不应破坏补全"
        assert data["score"] == 8
        assert data["issues"][0]["description"] == "看到 [信号] 时"

    def test_truncated_json_repair_closes_nested_containers(self):
        from src.review_engine.base_agent import _try_fix_truncated_json
        truncated = '{"score": 6, "issues": [{"level": 2, "description": "x"}'
        data = _try_fix_truncated_json(truncated)
        assert data is not None and data["score"] == 6
