"""tests.test_novel_service — 服务层编排测试（用假 LLM，不联网、不花钱）。

覆盖的是**编排**而非模型能力：JSON 解析、落盘、护栏、失败上报。
假 LLM 直接把预置字符串当响应返回，因此 LLM 出错/返回垃圾的分支也能被测到。
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.novel.project_manager import NovelProject  # noqa: E402
from src.novel.service import NovelService  # noqa: E402


OUTLINE_JSON = json.dumps({
    "outline": [
        {"chapter": 1, "title": "开端", "expected_content": "主角登场",
         "key_foreshadowing": ["神秘的信号"]},
        {"chapter": 2, "title": "转折", "expected_content": "冲突爆发",
         "key_foreshadowing": []},
    ]
}, ensure_ascii=False)

CHARACTERS_JSON = json.dumps({
    "characters": [
        {"name": "林辰", "role": "主角", "personality": {"勇敢": 7},
         "speaking_style": "简短", "core_desire": "找到妹妹", "core_fear": "失去记忆"},
    ],
    "world": {"timeline": "公元 2157 年", "factions": ["氧气集团"]},
}, ensure_ascii=False)

PLOT_JSON = json.dumps({
    "opening_hook": "白炽灯闪烁",
    "climax": "数据被窃",
    "ending_hook": "警报响起",
    "scenes": [{"order": 1, "location": "实验室", "characters": ["林辰"],
                "summary": "潜入", "purpose": "建立悬念"}],
    "foreshadowing_planted": ["第七十四号信号"],
    "foreshadowing_resolved": ["神秘的信号"],
    "character_appearances": {"林辰": "潜入服务器机房"},
    "emotional_arc": "紧张→决绝",
}, ensure_ascii=False)


class RoutingFakeLLM:
    """按系统提示词路由的假 LLM：区分"大纲/剧情/角色分析/写正文"四类调用。

    真实写作一章会触发 **三次** 调用：剧情设计 + 正文 + 写后角色分析
    （见下面 test_write_chapter_costs_three_calls_per_chapter 的断言）。
    按位置塞响应的假 LLM 会因为漏算这一点而写出错误用例，所以这里按意图路由。
    """

    def __init__(self, outline: str = OUTLINE_JSON, plot: str = PLOT_JSON,
                 characters: str = CHARACTERS_JSON, chapters: Optional[list] = None,
                 analysis: str = '{"characters": []}'):
        self.outline, self.plot, self.characters = outline, plot, characters
        self.analysis = analysis
        self.chapter_responses = list(chapters if chapters is not None else ["默认正文" * 40])
        self.calls: list[str] = []

    def kind(self, messages) -> str:
        system = messages[0]["content"] if messages else ""
        user = messages[-1]["content"] if messages else ""
        if "策划师" in system:
            return "outline"
        if "角色分析师" in system:
            return "character_analysis"
        if "剧情" in system and "opening_hook" in system:
            return "plot"
        if "角色" in system and "world" in system:
            return "characters"
        _ = user
        return "chapter"

    def chat(self, messages, model_tier: str = "flash", **kwargs) -> str:
        kind = self.kind(messages)
        self.calls.append(kind)
        if kind == "outline":
            return self.outline
        if kind == "plot":
            return self.plot
        if kind == "characters":
            return self.characters
        if kind == "character_analysis":
            return self.analysis
        return self.chapter_responses.pop(0) if self.chapter_responses else ""

    def count(self, kind: str) -> int:
        return sum(1 for c in self.calls if c == kind)


class StubService(NovelService):
    """把假 LLM 注入到引擎里的服务（load() 是唯一的注入点）。"""

    def __init__(self, base_dir: str, llm: RoutingFakeLLM):
        super().__init__(base_dir)
        self.llm = llm

    def load(self, name: str):
        bundle = super().load(name)
        bundle.writer.llm = self.llm
        bundle.engine.llm = self.llm
        bundle.plot.llm = self.llm
        return bundle


class _Fixture:
    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.svc = NovelService(str(self.tmp))
        self.svc.create("测试书本", genre="科幻", description="一句话简介")
        return self.tmp

    def __exit__(self, *exc):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def data(self) -> dict:
        return json.loads((self.tmp / "测试书本" / "project.json").read_text("utf-8"))


# ========== 大纲 ==========

def test_generate_outline_writes_outline():
    with _Fixture() as tmp:
        svc = StubService(str(tmp), RoutingFakeLLM())
        r = svc.generate_outline("测试书本", 2, "主角寻妹")
        assert r.ok, r.title
        data = json.loads((tmp / "测试书本" / "project.json").read_text("utf-8"))
        assert [o["chapter"] for o in data["outline"]] == [1, 2]
        assert data["outline"][0]["title"] == "开端"
        assert data["outline"][0]["key_foreshadowing"] == ["神秘的信号"]


def test_generate_outline_reports_unparseable_output():
    """模型返回非 JSON 时必须报失败，而不是"看起来成功但大纲是空的"。"""
    with _Fixture() as tmp:
        svc = StubService(str(tmp), RoutingFakeLLM(outline="抱歉，我无法完成这个请求。"))
        r = svc.generate_outline("测试书本", 3, "随便")
        assert r.ok is False
        assert "JSON" in r.title


def test_generate_outline_reports_llm_error():
    class Boom(RoutingFakeLLM):
        def chat(self, *a, **k):
            raise RuntimeError("401 unauthorized")

    with _Fixture() as tmp:
        svc = StubService(str(tmp), Boom())
        r = svc.generate_outline("测试书本", 3, "随便")
        assert r.ok is False and "401" in r.title


# ========== 角色：覆盖前必须备份 ==========

def test_generate_characters_backs_up_before_overwrite():
    with _Fixture() as tmp:
        char_file = tmp / "测试书本" / "characters.json"
        original = {"旧角色": {"name": "旧角色", "role": "配角"}}
        char_file.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

        svc = StubService(str(tmp), RoutingFakeLLM())
        r = svc.generate_characters("测试书本")
        assert r.ok, r.title

        backups = list((tmp / "测试书本").glob("characters.json.bak-*"))
        assert backups, "覆盖 characters.json 前必须留下备份"
        assert json.loads(backups[0].read_text("utf-8")) == original, "备份内容应是覆盖前的原文件"

        saved = json.loads(char_file.read_text("utf-8"))
        assert "林辰" in saved


def test_generate_characters_keeps_existing_chapter_events():
    """重新生成角色不能丢掉逐章事件（那是长篇连续性的核心数据）。"""
    with _Fixture() as tmp:
        char_file = tmp / "测试书本" / "characters.json"
        char_file.write_text(json.dumps({
            "林辰": {"name": "林辰", "role": "主角", "personality": {"勇敢": 7},
                     "chapter_events": [{"chapter": 1, "mood": "紧张", "summary": "开场",
                                         "key_actions": ["送咖啡"], "personality_shifts": [],
                                         "relationship_changes": [], "skills_gained": [],
                                         "belief_changes": []}],
                     "relationships": {}, "arc_summary": ""}
        }, ensure_ascii=False), encoding="utf-8")

        svc = StubService(str(tmp), RoutingFakeLLM())
        assert svc.generate_characters("测试书本").ok
        saved = json.loads(char_file.read_text("utf-8"))
        assert saved["林辰"]["chapter_events"], "同名角色的 chapter_events 必须保留"
        assert saved["林辰"]["chapter_events"][0]["summary"] == "开场"


def test_generate_characters_failure_keeps_original_file():
    with _Fixture() as tmp:
        char_file = tmp / "测试书本" / "characters.json"
        original = {"旧角色": {"name": "旧角色"}}
        char_file.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
        svc = StubService(str(tmp), RoutingFakeLLM(characters="模型抽风了，这不是 JSON"))
        r = svc.generate_characters("测试书本")
        assert r.ok is False
        assert json.loads(char_file.read_text("utf-8")) == original, "失败时不能破坏原文件"


# ========== 剧情与写作 ==========

def test_design_plot_then_write_chapter_end_to_end():
    with _Fixture() as tmp:
        svc = StubService(str(tmp), RoutingFakeLLM(chapters=["第1章正文。" * 50]))
        assert svc.generate_outline("测试书本", 2, "主角寻妹").ok

        r = svc.design_plot("测试书本", 1)
        assert r.ok, r.title
        plot = json.loads((tmp / "测试书本" / "plots.json").read_text("utf-8"))
        assert plot["plots"]["1"]["opening_hook"] == "白炽灯闪烁"

        r = svc.write_chapter("测试书本", 1, target_words=250)
        assert r.ok, r.title
        data = json.loads((tmp / "测试书本" / "project.json").read_text("utf-8"))
        assert "1" in data["chapters"]
        # 剧情里"埋下的伏笔"要进项目伏笔表，"回收的"要移除
        assert "第七十四号信号" in data["foreshadowing"]
        assert "神秘的信号" not in data["foreshadowing"]


def test_write_chapter_reports_empty_output():
    with _Fixture() as tmp:
        svc = StubService(str(tmp), RoutingFakeLLM(chapters=["   "]))
        r = svc.write_chapter("测试书本", 1, target_words=100)
        assert r.ok is False and "空文本" in r.title


def test_write_chapter_flags_word_count_drift():
    with _Fixture() as tmp:
        svc = StubService(str(tmp), RoutingFakeLLM(chapters=["短" * 20]))
        r = svc.write_chapter("测试书本", 1, target_words=2500)
        assert r.ok
        assert any("偏差" in line for line in r.lines), "字数严重不达标应给出提示"


def test_design_plot_without_outline_item_is_rejected():
    with _Fixture() as tmp:
        svc = StubService(str(tmp), RoutingFakeLLM())
        r = svc.design_plot("测试书本", 7)
        assert r.ok is False and "大纲" in r.title


# ========== 批量续写：只往后写 ==========

def test_batch_write_continues_after_last_chapter():
    with _Fixture() as tmp:
        svc = StubService(str(tmp), RoutingFakeLLM(chapters=["正文" * 60, "正文" * 60, "正文" * 60]))
        svc.generate_outline("测试书本", 3, "简介")
        # 先写完第 1 章
        assert svc.write_chapter("测试书本", 1, target_words=100).ok
        # 批量续写 2 章 → 应从第 2 章开始
        r = svc.batch_write("测试书本", count=2, target_words=100)
        assert r.ok, r.title
        data = json.loads((tmp / "测试书本" / "project.json").read_text("utf-8"))
        assert sorted(int(k) for k in data["chapters"]) == [1, 2, 3]


def test_batch_write_refuses_existing_chapter():
    with _Fixture() as tmp:
        svc = StubService(str(tmp), RoutingFakeLLM(chapters=["正文" * 60]))
        svc.write_chapter("测试书本", 1, target_words=100)
        r = svc.batch_write("测试书本", count=1, start=1)
        assert r.ok is False and "已有正文" in r.title


def test_batch_write_stops_on_first_failure():
    """失败即停：避免连续烧钱。"""
    with _Fixture() as tmp:
        # 第 2 章写作返回空 → 立即停，不会继续第 3 章
        svc = StubService(str(tmp), RoutingFakeLLM(chapters=["正文" * 60, ""]))
        svc.generate_outline("测试书本", 3, "简介")
        r = svc.batch_write("测试书本", count=3, target_words=100, start=1)
        data = json.loads((tmp / "测试书本" / "project.json").read_text("utf-8"))
        assert sorted(int(k) for k in data["chapters"]) == [1]
        assert any("第2章" in line for line in r.lines)


# ========== 本地编辑与状态 ==========

def test_update_outline_item_creates_and_saves():
    with _Fixture() as tmp:
        svc = NovelService(str(tmp))
        r = svc.update_outline_item("测试书本", 5, "新标题", "新的预期内容", ["伏笔甲"])
        assert r.ok
        data = json.loads((tmp / "测试书本" / "project.json").read_text("utf-8"))
        item = next(o for o in data["outline"] if o["chapter"] == 5)
        assert item["title"] == "新标题" and item["key_foreshadowing"] == ["伏笔甲"]
        assert data["chapter_titles"]["5"] == "新标题"


def test_save_plot_notes_round_trip():
    with _Fixture() as tmp:
        svc = NovelService(str(tmp))
        assert svc.save_plot_notes("测试书本", 1, "这里我要写一场雨戏").ok
        plot = json.loads((tmp / "测试书本" / "plots.json").read_text("utf-8"))
        assert plot["plots"]["1"]["user_notes"] == "这里我要写一场雨戏"


def test_export_writes_file():
    with _Fixture() as tmp:
        svc = StubService(str(tmp), RoutingFakeLLM(chapters=["正文" * 30]))
        svc.write_chapter("测试书本", 1, target_words=100)
        r = svc.export("测试书本")
        assert r.ok
        out = (tmp / "测试书本" / "export.txt").read_text("utf-8")
        assert out.startswith("# 测试书本")


def test_create_rejects_duplicate():
    with _Fixture() as tmp:
        svc = NovelService(str(tmp))
        assert svc.create("测试书本").ok is False


def test_llm_status_without_key_is_not_configured():
    """未配置 Key 时 must be 明确报未配置（界面据此拦下花钱动作）。"""
    import os
    import config.settings as settings
    old = os.environ.pop("DEEPSEEK_API_KEY", None)
    settings._config = None
    try:
        status = NovelService().llm_status()
        assert status["configured"] is False
        assert {t["tier"] for t in status["tiers"]} == {"flash", "pro"}
        assert all(t["key_ok"] is False for t in status["tiers"])
    finally:
        if old is not None:
            os.environ["DEEPSEEK_API_KEY"] = old
        settings._config = None


def test_resolve_env_turns_unset_variable_into_empty():
    """回归：未设置的 ${VAR} 必须解析为空串，而不是被当字面量发出去。"""
    import os
    from config.settings import resolve_env
    os.environ.pop("SOME_UNSET_VAR_XYZ", None)
    assert resolve_env(r"\${SOME_UNSET_VAR_XYZ}") == ""
    assert resolve_env("${SOME_UNSET_VAR_XYZ}") == ""
    assert resolve_env("plain-key") == "plain-key"


def test_write_chapter_call_profile_without_outline():
    """没有大纲时写一章 = 2 次调用：正文 + 写后角色分析。"""
    with _Fixture() as tmp:
        llm = RoutingFakeLLM(chapters=["正文" * 60])
        svc = StubService(str(tmp), llm)
        assert svc.write_chapter("测试书本", 1, target_words=100).ok
        assert llm.count("chapter") == 1
        assert llm.count("character_analysis") == 1
        assert llm.count("plot") == 0


def test_write_chapter_call_profile_with_outline_is_three():
    """有大纲但没剧情设计时写一章 = 3 次调用：剧情 + 正文 + 角色分析。

    这是做费用估算的关键事实（比"一章一次调用"贵三倍），
    也是界面必须显示实时费用的原因。
    """
    with _Fixture() as tmp:
        llm = RoutingFakeLLM(chapters=["正文" * 60])
        svc = StubService(str(tmp), llm)
        svc.update_outline_item("测试书本", 1, "开端", "主角登场")
        assert svc.write_chapter("测试书本", 1, target_words=100).ok
        assert llm.count("plot") == 1, "缺剧情设计时应自动补一次"
        assert llm.count("chapter") == 1
        assert llm.count("character_analysis") == 1


# ========== 契约：tier 必须真的传到模型（A16 回归） ==========

class TierRecordingLLM(RoutingFakeLLM):
    """记录每次调用用的档位 —— 用来证明 tier 没有被中间层吞掉。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tiers: list[tuple[str, str]] = []

    def chat(self, messages, model_tier: str = "flash", **kwargs) -> str:
        self.tiers.append((self.kind(messages), model_tier))
        return super().chat(messages, model_tier=model_tier, **kwargs)

    def tier_of(self, kind: str):
        return next((tier for k, tier in self.tiers if k == kind), None)


def test_generate_characters_passes_tier_to_llm():
    """A16：服务层以前只把 tier 写进日志，design_characters 里硬编码 flash。"""
    with _Fixture() as tmp:
        llm = TierRecordingLLM()
        svc = StubService(str(tmp), llm)
        assert svc.generate_characters("测试书本", tier="pro").ok
        assert llm.tier_of("characters") == "pro"


def test_design_plot_passes_tier_to_llm():
    with _Fixture() as tmp:
        llm = TierRecordingLLM()
        svc = StubService(str(tmp), llm)
        svc.update_outline_item("测试书本", 1, "开端", "主角登场")
        assert svc.design_plot("测试书本", 1, tier="pro").ok
        assert llm.tier_of("plot") == "pro"


def test_auto_plot_inside_write_chapter_passes_tier():
    """写正文时"自动补剧情设计"那条路径也必须带 tier（以前漏传）。"""
    with _Fixture() as tmp:
        llm = TierRecordingLLM(chapters=["正文" * 60])
        svc = StubService(str(tmp), llm)
        svc.update_outline_item("测试书本", 1, "开端", "主角登场")
        assert svc.write_chapter("测试书本", 1, target_words=100, tier="pro").ok
        assert llm.tier_of("plot") == "pro"
        assert llm.tier_of("chapter") == "pro"


def test_generate_outline_passes_tier_to_llm():
    with _Fixture() as tmp:
        llm = TierRecordingLLM()
        svc = StubService(str(tmp), llm)
        assert svc.generate_outline("测试书本", 2, "主角寻妹", tier="pro").ok
        assert llm.tier_of("outline") == "pro"


def test_plot_engine_signature_accepts_tier():
    """直接锁住引擎签名：以后有人把 model_tier 删掉，这里会先红。"""
    import inspect
    from src.novel.plot_engine import PlotEngine
    for fn in (PlotEngine.design_characters, PlotEngine.design_chapter_plot):
        assert "model_tier" in inspect.signature(fn).parameters, fn.__name__


# ========== 审稿（服务层护栏） ==========

REVIEW_LEVEL1_JSON = json.dumps({
    "overall_assessment": "尚可",
    "score": 8,
    "issues": [{
        "level": "Level 1", "description": "措辞",
        "before_text": "这是第1章的", "after_text": "这里是第1章的",
    }],
}, ensure_ascii=False)

REVIEW_CLEAN_JSON = json.dumps(
    {"overall_assessment": "没问题", "score": 9, "issues": []}, ensure_ascii=False)

# 混合档：可勾选的 Level 1 / Level 2 + 只能人工的 Level 3
REVIEW_MIXED_JSON = json.dumps({
    "overall_assessment": "尚可",
    "score": 8,
    "issues": [
        {"level": 1, "description": "L1 措辞", "before_text": "这是第1章的",
         "after_text": "这里是第1章的"},
        {"level": 2, "description": "L2 精简", "before_text": "正文内容",
         "after_text": "正文"},
        {"level": 3, "description": "L3 结构建议"},
    ],
}, ensure_ascii=False)


class ReviewFakeLLM:
    """只服务审稿 Agent 的假 LLM：把预置 JSON 原样返回，并记账调用次数。"""

    def __init__(self, response: str):
        self.response = response
        self.calls = 0
        self.last_messages: list = []

    def chat(self, messages, model_tier: str = "flash", **kwargs) -> str:
        self.calls += 1
        self.last_messages = messages
        return self.response


def _project_with_chapter(tmp, text: str = "这是第1章的正文内容。" * 20) -> NovelProject:
    """在 fixture 项目里补一章正文（review_chapter 需要非空章节）。"""
    project = NovelProject.load(str(tmp), "测试书本")
    project.add_chapter(1, "第1章", text)
    project.save()
    return project


def test_review_chapter_rejects_empty_chapter():
    """没有正文的章节不该送审：不花钱，也不能把「审稿成功」挂在空章节上。"""
    with _Fixture() as tmp:
        called: list[int] = []

        class NeverReviewer:
            def review(self, *args, **kwargs):
                called.append(1)
                raise AssertionError("空章不该调用审稿引擎")

        svc = NovelService(str(tmp), reviewer=NeverReviewer())
        r = svc.review_chapter("测试书本", 2)
        assert r.ok is False
        assert "还没有正文" in r.title
        assert called == []


def test_review_chapter_reports_total_failure():
    """六个维度全失败 → ok=False，并把原因带出来（不伪装成「没问题」）。"""
    with _Fixture() as tmp:
        _project_with_chapter(tmp)

        class AllFailedReviewer:
            def review(self, *args, **kwargs):
                from src.models import AggregatedReview, ReviewReport
                reports = [ReviewReport(agent=f"维度{i}", status="failed",
                                        error="超时", score=0.0) for i in range(6)]
                return AggregatedReview(article_id="x", reports=reports)

            def format_report(self, aggregated):
                return "# 报告（全部失败）"

        svc = NovelService(str(tmp), reviewer=AllFailedReviewer())
        r = svc.review_chapter("测试书本", 1)
        assert r.ok is False
        assert "全部失败" in r.title
        assert "超时" in r.lines[0]
        assert r.report == "# 报告（全部失败）"


def test_review_chapter_applies_level1_and_backs_up():
    """Level 1 命中会写回正文，且覆盖前必须留下 project.json 备份。"""
    with _Fixture() as tmp:
        from src.review_engine import ReviewOrchestrator
        _project_with_chapter(tmp)
        llm = ReviewFakeLLM(REVIEW_LEVEL1_JSON)
        svc = NovelService(str(tmp), reviewer=ReviewOrchestrator(llm_client=llm))

        r = svc.review_chapter("测试书本", 1, tier="flash")
        assert r.ok, r.as_text()
        assert llm.calls == 6, "六维应各调用一次"
        assert "作品状态" in llm.last_messages[1]["content"], "小说向审稿必须注入作品状态"

        data = json.loads((tmp / "测试书本" / "project.json").read_text("utf-8"))
        assert data["chapters"]["1"].startswith("这里是第1章的")
        assert list((tmp / "测试书本").glob("project.json.bak-*")), "覆盖前必须备份"
        assert "已写回第1章" in "\n".join(r.lines)
        assert r.report and "审稿报告" in r.report


def test_review_chapter_clean_does_not_touch_project():
    """没有 Level 1 命中就不落盘、不备份（避免无意义改写与磁盘垃圾）。"""
    with _Fixture() as tmp:
        from src.review_engine import ReviewOrchestrator
        _project_with_chapter(tmp, text="正文" * 80)
        svc = NovelService(str(tmp),
                           reviewer=ReviewOrchestrator(llm_client=ReviewFakeLLM(REVIEW_CLEAN_JSON)))
        before = (tmp / "测试书本" / "project.json").read_text("utf-8")

        r = svc.review_chapter("测试书本", 1)
        assert r.ok, r.as_text()
        after = (tmp / "测试书本" / "project.json").read_text("utf-8")
        assert before == after, "没有 Level 1 修改时不该改写项目文件"
        assert not list((tmp / "测试书本").glob("project.json.bak-*"))


# ========== 审稿：勾选哪条改哪条 ==========

def _mixed_reviewer() -> "object":
    from src.review_engine import ReviewOrchestrator
    return ReviewOrchestrator(llm_client=ReviewFakeLLM(REVIEW_MIXED_JSON))


def test_review_only_mode_lists_issues_without_modifying():
    """apply_level1=False：只审不改，并把结构化结果带回给界面。"""
    with _Fixture() as tmp:
        _project_with_chapter(tmp)
        svc = NovelService(str(tmp), reviewer=_mixed_reviewer())
        before = (tmp / "测试书本" / "project.json").read_text("utf-8")

        r = svc.review_chapter("测试书本", 1, apply_level1=False, save=False)
        assert r.ok, r.as_text()
        # 关键：审稿本身绝不改正文
        assert (tmp / "测试书本" / "project.json").read_text("utf-8") == before
        assert not list((tmp / "测试书本").glob("project.json.bak-*"))

        aggregated = r.data
        assert aggregated is not None, "界面要靠 data 生成勾选清单"
        assert len(aggregated.applicable_issues) == 2, "L1 + L2 都可勾选"
        assert [i.level for i in aggregated.applicable_issues] == [1, 2]
        assert len(aggregated.guidance_issues) == 1, "L3 只能人工处理"
        assert "可勾选应用 2 项" in "\n".join(r.lines)


def test_apply_review_fixes_applies_only_selected():
    """只应用勾选的条目：没勾的 Level 2 必须原样保留。"""
    with _Fixture() as tmp:
        _project_with_chapter(tmp)
        svc = NovelService(str(tmp), reviewer=_mixed_reviewer())
        aggregated = svc.review_chapter("测试书本", 1, apply_level1=False).data

        level1 = [i for i in aggregated.applicable_issues if i.level == 1]
        r = svc.apply_review_fixes("测试书本", 1, level1)
        assert r.ok, r.as_text()

        text = NovelProject.load(str(tmp), "测试书本").get_chapter(1)
        assert text.startswith("这里是第1章的"), "勾选的 L1 应生效"
        assert "正文内容" in text, "没勾的 L2 不该被改"
        assert list((tmp / "测试书本").glob("project.json.bak-*")), "覆盖前必须备份"


def test_apply_review_fixes_rejects_empty_selection():
    with _Fixture() as tmp:
        _project_with_chapter(tmp)
        svc = NovelService(str(tmp))
        r = svc.apply_review_fixes("测试书本", 1, [])
        assert r.ok is False
        assert "没有勾选" in r.title


def test_apply_review_fixes_reports_missed_anchors():
    """锚点都没命中 → ok=False，且不落盘、不备份（不假装改成功）。"""
    with _Fixture() as tmp:
        from src.models import ReviewIssue
        _project_with_chapter(tmp)
        svc = NovelService(str(tmp))
        before = (tmp / "测试书本" / "project.json").read_text("utf-8")
        ghost = ReviewIssue(agent="校对", level=1, description="不存在",
                            before_text="这段原文根本不在正文里", after_text="x")

        r = svc.apply_review_fixes("测试书本", 1, [ghost])
        assert r.ok is False
        assert "没有实际改动" in r.title
        assert (tmp / "测试书本" / "project.json").read_text("utf-8") == before
        assert not list((tmp / "测试书本").glob("project.json.bak-*"))
