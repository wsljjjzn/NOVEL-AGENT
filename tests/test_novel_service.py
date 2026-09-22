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
