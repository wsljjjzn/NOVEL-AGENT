"""tests.test_character_engine — 角色引擎回归测试（不联网、不花钱）。

覆盖 CODE_REVIEW.md 里 A1-A13 的修复点：
- A1  写后分析的失败可区分（llm_failed / parse_failed / no_change）
- A2  is_new 不再清空已有档案
- A3  未登记的人格特质也会落地
- A4  序列化往返保住 relationship_changes；手工编辑过的存档不再让项目打不开；save 原子
- A5  别名与括号写法归并到同一角色
- A6  关系强度不再恒为 5，起始章不再被每章覆盖
- A7  写作卡片无条件带上核心欲望/恐惧/道德准则/背景/外貌/别名
- A8  同章重写替换而非追加
- A9  null/越界/字符串数值一律夹到 0-10
- A10 role 进分析模板，已有角色不被覆盖
- A11 乱序写章时逐章视图取正确
- A12 正文超限时截断并告警
- A13 上下文默认裁剪"最近未出场且非主角/反派"的角色

假 LLM 直接返回预置字符串（或抛异常），因此所有分支都能被测到，不需要真实 API。
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.novel.character_engine import (  # noqa: E402
    ANALYSIS_MAX_TOKENS,
    ANALYSIS_TEXT_LIMIT,
    STATUS_LLM_FAILED,
    STATUS_NO_CHANGE,
    STATUS_PARSE_FAILED,
    CharacterDataError,
    CharacterEngine,
    CharacterProfile,
    ChapterEvent,
    PersonalityShift,
)
from src.utils.logger import logger  # noqa: E402


class FakeLLM:
    """假 LLM：按顺序返回预置响应，或直接抛异常；同时记录收到的 prompt 与参数。"""

    def __init__(self, *responses, error=None):
        self.responses = list(responses)
        self.error = error
        self.prompts: list[str] = []
        self.kwargs: list[dict] = []

    def chat(self, messages, model_tier: str = "flash", **kwargs):
        self.prompts.append(messages[-1]["content"])
        self.kwargs.append({"model_tier": model_tier, **kwargs})
        if self.error is not None:
            raise self.error
        return self.responses.pop(0) if self.responses else ""


def make_engine(llm=None) -> CharacterEngine:
    """构造引擎但不触碰 LLMClient（测试不需要读配置、建客户端）。"""
    engine = CharacterEngine.__new__(CharacterEngine)
    engine._characters = {}
    engine.llm = llm if llm is not None else FakeLLM("{}")
    return engine


def analysis_json(*characters) -> str:
    return json.dumps({"characters": list(characters)}, ensure_ascii=False)


def capture_warnings():
    """挂一个 loguru sink，返回 (消息列表, 卸载函数)。"""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    return messages, lambda: logger.remove(handler_id)


# ========== 基础构造 ==========

def test_engine_constructs_with_real_config():
    """真实配置下能构造（配置缺失属环境问题，跳过而不是判失败）。"""
    try:
        engine = CharacterEngine()
    except Exception as exc:  # pragma: no cover - 取决于本机配置
        pytest.skip(f"无法构造 LLMClient: {exc}")
    assert engine.all_characters() == []


def test_analysis_prompt_keeps_legacy_marker():
    """旧测试的假 LLM 靠"角色分析师"字样路由角色分析调用，不能改掉。"""
    assert "角色分析师" in CharacterEngine.CHARACTER_ANALYSIS_SYSTEM


# ========== A1：失败可区分 ==========

def test_llm_failure_is_distinguishable_from_no_change():
    engine = make_engine(FakeLLM(error=RuntimeError("网络挂了")))
    outcome = engine.analyze_chapter_ex(1, "正文", [])

    assert outcome.status == STATUS_LLM_FAILED
    assert outcome.failed is True
    assert outcome.updated == []
    assert engine.all_characters() == []


def test_truncated_json_is_parse_failed():
    engine = make_engine(FakeLLM('{"characters": [{"name": "甲", "mood": "平静"'))  # 缺右括号
    outcome = engine.analyze_chapter_ex(1, "正文", [])

    assert outcome.status == STATUS_PARSE_FAILED
    assert outcome.failed is True
    assert engine.all_characters() == []


def test_empty_response_is_parse_failed():
    engine = make_engine(FakeLLM(""))
    assert engine.analyze_chapter_ex(1, "正文", []).status == STATUS_PARSE_FAILED


def test_empty_character_list_is_no_change_not_failure():
    engine = make_engine(FakeLLM('{"characters": []}'))
    outcome = engine.analyze_chapter_ex(1, "正文", [])

    assert outcome.status == STATUS_NO_CHANGE
    assert outcome.failed is False


def test_legacy_analyze_chapter_still_returns_a_list():
    """旧接口（5 处调用方在用）保持"返回角色列表"的语义。"""
    engine = make_engine(FakeLLM(analysis_json({"name": "甲", "mood": "平静"})))
    updated = engine.analyze_chapter(1, "正文", [])

    assert [profile.name for profile in updated] == ["甲"]


def test_failed_analysis_returns_empty_via_legacy_api():
    engine = make_engine(FakeLLM(error=RuntimeError("超时")))
    assert engine.analyze_chapter(1, "正文", []) == []


def test_analysis_call_gets_its_own_output_budget():
    """4 角色一多，flash 默认 4096 会被截断（A1 的生产事故）。"""
    fake = FakeLLM('{"characters": []}')
    make_engine(fake).analyze_chapter_ex(1, "正文", [])

    assert fake.kwargs[0]["max_tokens"] == ANALYSIS_MAX_TOKENS


# ========== A12：正文超限 ==========

def test_overlong_chapter_is_truncated_and_warned():
    messages, unmount = capture_warnings()
    try:
        fake = FakeLLM('{"characters": []}')
        engine = make_engine(fake)
        long_text = "字" * (ANALYSIS_TEXT_LIMIT + 500)
        outcome = engine.analyze_chapter_ex(7, long_text, [])
    finally:
        unmount()

    assert outcome.truncated is True
    assert "字" * ANALYSIS_TEXT_LIMIT in fake.prompts[0]
    assert "字" * (ANALYSIS_TEXT_LIMIT + 1) not in fake.prompts[0]
    assert any("第7章" in message and "截断" in message for message in messages)


# ========== A2：is_new 不清空档案 ==========

def test_is_new_does_not_rebuild_existing_profile():
    engine = make_engine()
    engine.add_character(CharacterProfile(
        name="乙", role="主角", core_desire="复仇", core_fear="失去妹妹",
        personality={"冷静": 9},
        relationships={"丙": {"状态": "盟友", "强度": 8, "起始章": 1}},
        chapter_events=[ChapterEvent(chapter=1, mood="愤怒", summary="第一章")],
    ))
    engine.llm = FakeLLM(analysis_json(
        {"name": "乙", "is_new": True, "mood": "平静", "summary": "第二章"}))

    outcome = engine.analyze_chapter_ex(2, "正文", ["乙"])
    profile = engine.get_character("乙")

    assert outcome.status == "ok"
    assert outcome.created == []                       # 没有新建
    assert profile.role == "主角"                       # 此前会被重置成"配角"
    assert profile.core_desire == "复仇"
    assert profile.personality == {"冷静": 9}
    assert profile.relationships["丙"]["强度"] == 8
    assert [event.chapter for event in profile.sorted_events()] == [1, 2]


def test_existing_profile_only_fills_empty_fields():
    engine = make_engine()
    engine.add_character(CharacterProfile(name="乙"))
    engine.llm = FakeLLM(analysis_json({
        "name": "乙", "mood": "平静", "core_desire": "复仇", "background": "孤儿"}))

    engine.analyze_chapter_ex(1, "正文", [])
    profile = engine.get_character("乙")

    assert profile.core_desire == "复仇"     # 空字段被补上
    assert profile.background == "孤儿"
    assert profile.role == "配角"            # 仍走默认


# ========== A3 / A9：人格演进与数值夹紧 ==========

def test_personality_shift_applies_to_unregistered_trait():
    engine = make_engine(FakeLLM(analysis_json({
        "name": "甲", "personality": {"善良": 7},
        "personality_shifts": [{"trait": "勇敢", "old": 3, "new": 9, "reason": "初次战斗"}],
    })))
    engine.analyze_chapter_ex(1, "正文", [])
    profile = engine.get_character("甲")

    assert profile.personality["勇敢"] == 9      # 此前只记录不落地
    assert profile.chapter_events[0].personality_shifts[0].trait == "勇敢"


def test_personality_shift_prefers_local_current_value_as_old():
    """分析 prompt 不含角色当前数值，模型给的 old 是猜的，应以本地状态为准。"""
    engine = make_engine(FakeLLM(analysis_json({
        "name": "甲", "personality": {"善良": 7},
        "personality_shifts": [{"trait": "善良", "old": 1, "new": 4, "reason": "心硬了"}],
    })))
    engine.analyze_chapter_ex(1, "正文", [])
    shift = engine.get_character("甲").chapter_events[0].personality_shifts[0]

    assert shift.old_value == 7
    assert shift.new_value == 4


def test_null_and_out_of_range_values_are_clamped():
    engine = make_engine(FakeLLM(analysis_json({
        "name": "甲",
        "personality": {"善良": None, "勇敢": 99, "谨慎": "3", "冲动": -4},
        "personality_shifts": [{"trait": "善良", "old": None, "new": None}],
    })))
    engine.analyze_chapter_ex(1, "正文", [])
    personality = engine.get_character("甲").personality

    assert personality["善良"] == 5      # 兜底默认值，不是 None
    assert personality["勇敢"] == 10     # 越界夹紧
    assert personality["谨慎"] == 3      # 字符串数字
    assert personality["冲动"] == 0


def test_legacy_none_personality_renders_without_none():
    profile = CharacterProfile(name="甲", personality={"善良": None})
    assert profile.personality_summary() == "善良5/10"


# ========== A6：关系强度与起始章 ==========

def test_relationship_intensity_is_kept():
    engine = make_engine(FakeLLM(analysis_json({
        "name": "甲", "mood": "平静",
        "relationship_changes": [
            {"target": "乙", "old": "陌生", "new": "敌视", "reason": "被背叛", "intensity": 9}],
    })))
    engine.analyze_chapter_ex(3, "正文", [])
    relation = engine.get_character("甲").relationships["乙"]

    assert relation["状态"] == "敌视"
    assert relation["强度"] == 9            # 此前恒为 5
    assert relation["起始章"] == 3
    assert relation["最近变化"]["chapter"] == 3
    assert relation["最近变化"]["from"] == "陌生"


def test_relationship_intensity_falls_back_and_start_chapter_is_stable():
    engine = make_engine(FakeLLM(analysis_json({
        "name": "甲", "mood": "平静",
        "relationship_changes": [{"target": "乙", "new": "敌视", "intensity": 8}]})))
    engine.analyze_chapter_ex(1, "正文", [])

    engine.llm = FakeLLM(analysis_json({
        "name": "甲", "mood": "平静",
        "relationship_changes": [{"target": "乙", "new": "和解"}]}))
    engine.analyze_chapter_ex(5, "正文", [])
    relation = engine.get_character("甲").relationships["乙"]

    assert relation["强度"] == 8            # 模型没给强度时保留原值
    assert relation["起始章"] == 1          # 起始章不再被每章覆盖
    assert relation["状态"] == "和解"


# ========== A8 / A11：逐章事件的写入与视图 ==========

def test_rewriting_same_chapter_replaces_the_event():
    engine = make_engine(FakeLLM(
        analysis_json({"name": "甲", "mood": "紧张", "summary": "第一版"}),
        analysis_json({"name": "甲", "mood": "愤怒", "summary": "第二版"}),
    ))
    engine.analyze_chapter_ex(3, "正文", [])
    engine.analyze_chapter_ex(3, "正文", [])
    profile = engine.get_character("甲")

    assert len(profile.chapter_events) == 1
    assert profile.chapter_events[0].summary == "第二版"


def test_chapter_events_are_always_ordered_by_chapter():
    profile = CharacterProfile(name="甲")
    for chapter in (5, 2, 9, 3):
        profile.upsert_event(ChapterEvent(chapter=chapter, mood=f"m{chapter}"))

    assert [event.chapter for event in profile.chapter_events] == [2, 3, 5, 9]


def test_views_are_correct_when_chapters_written_out_of_order():
    engine = make_engine()
    for chapter in (5, 2, 9, 3):
        engine.llm = FakeLLM(analysis_json({"name": "甲", "mood": f"m{chapter}"}))
        engine.analyze_chapter_ex(chapter, "正文", [])
    profile = engine.get_character("甲")

    assert profile.current_chapter == 9          # 此前是 3
    assert profile.current_mood == "m9"
    assert [event.chapter for event in profile.recent_events(6)] == [2, 3, 5]


# ========== A4：序列化往返、容错读取、原子写 ==========

def test_roundtrip_keeps_relationship_changes(tmp_path):
    engine = make_engine(FakeLLM(analysis_json({
        "name": "甲", "mood": "平静",
        "relationship_changes": [
            {"target": "乙", "old": "陌生", "new": "敌视", "reason": "被背叛"}],
    })))
    engine.analyze_chapter_ex(1, "正文", [])

    path = tmp_path / "characters.json"
    engine.save(str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["甲"]["chapter_events"][0]["relationship_changes"] == [
        {"target": "乙", "old": "陌生", "new": "敌视", "reason": "被背叛"}]

    reloaded = make_engine()
    reloaded.load(str(path))
    event = reloaded.get_character("甲").chapter_events[0]
    assert event.relationship_changes == [
        {"target": "乙", "old": "陌生", "new": "敌视", "reason": "被背叛"}]
    assert reloaded.get_character("甲").relationships["乙"]["状态"] == "敌视"


def test_roundtrip_keeps_personality_and_relationships(tmp_path):
    engine = make_engine()
    engine.add_character(CharacterProfile(
        name="甲", aliases=["小甲"], role="主角", personality={"勇敢": 7},
        speaking_style="寡言", core_desire="找到妹妹", core_fear="失忆",
        moral_compass={"诚实": 7}, background="边陲小镇", appearance="短发",
        relationships={"乙": {"状态": "盟友", "强度": 8, "起始章": 2}},
        chapter_events=[ChapterEvent(chapter=2, mood="紧张", key_actions=["翻墙"],
                                     skills_gained=["轻功"], belief_changes=["不再信任官府"],
                                     summary="夜探")],
        arc_summary="从怯懦到担当",
    ))
    path = tmp_path / "characters.json"
    engine.save(str(path))

    reloaded = make_engine()
    reloaded.load(str(path))
    profile = reloaded.get_character("甲")

    assert profile.to_dict() == engine.get_character("甲").to_dict()
    assert profile.aliases == ["小甲"]
    assert profile.relationships["乙"]["强度"] == 8


def test_load_deduplicates_and_orders_same_chapter_events(tmp_path):
    """存量档案里的重复章号（旧 bug 留下的）在加载时被规范化。"""
    path = tmp_path / "characters.json"
    path.write_text(json.dumps({"甲": {"name": "甲", "chapter_events": [
        {"chapter": 2, "mood": "第一版"},
        {"chapter": 2, "mood": "第二版"},
        {"chapter": 1, "mood": "更早"}]}}, ensure_ascii=False), encoding="utf-8")

    engine = make_engine()
    engine.load(str(path))
    events = engine.get_character("甲").chapter_events

    assert [event.chapter for event in events] == [1, 2]
    assert events[1].mood == "第二版"          # 同章保留最后一次写入


def test_load_tolerates_hand_edited_records(tmp_path):
    """旧实现用 ed["mood"] 硬索引，手工删一个字段就让整个项目打不开。"""
    path = tmp_path / "characters.json"
    path.write_text(json.dumps(
        {"甲": {"name": "甲", "chapter_events": [{"chapter": 1}]}}, ensure_ascii=False),
        encoding="utf-8")

    engine = make_engine()
    engine.load(str(path))
    profile = engine.get_character("甲")

    assert profile.chapter_events[0].chapter == 1
    assert profile.chapter_events[0].mood == ""
    assert profile.chapter_events[0].personality_shifts == []
    assert profile.personality == {}


def test_load_skips_non_object_records(tmp_path):
    path = tmp_path / "characters.json"
    path.write_text(json.dumps({"甲": {"name": "甲"}, "坏记录": "不是对象"},
                               ensure_ascii=False), encoding="utf-8")

    engine = make_engine()
    engine.load(str(path))
    assert [profile.name for profile in engine.all_characters()] == ["甲"]


def test_load_raises_readable_error_for_broken_json(tmp_path):
    path = tmp_path / "characters.json"
    path.write_text('{"甲": {"name": "甲"', encoding="utf-8")

    engine = make_engine()
    with pytest.raises(CharacterDataError) as excinfo:
        engine.load(str(path))
    assert str(path) in str(excinfo.value)
    assert "JSON" in str(excinfo.value)


def test_load_rejects_non_object_top_level(tmp_path):
    path = tmp_path / "characters.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(CharacterDataError):
        make_engine().load(str(path))


def test_load_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_engine().load(str(tmp_path / "不存在.json"))


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    engine = make_engine()
    engine.add_character(CharacterProfile(name="甲", personality={"勇敢": 7}))

    path = tmp_path / "characters.json"
    engine.save(str(path))

    assert [entry.name for entry in tmp_path.iterdir()] == ["characters.json"]
    assert json.loads(path.read_text(encoding="utf-8"))["甲"]["personality"] == {"勇敢": 7}


def test_save_creates_missing_directory(tmp_path):
    engine = make_engine()
    engine.add_character(CharacterProfile(name="甲"))

    path = tmp_path / "nested" / "characters.json"
    engine.save(str(path))
    assert path.exists()


def test_save_overwrites_previous_content_completely(tmp_path):
    path = tmp_path / "characters.json"
    engine = make_engine()
    engine.add_character(CharacterProfile(name="甲"))
    engine.add_character(CharacterProfile(name="乙"))
    engine.save(str(path))

    engine2 = make_engine()
    engine2.add_character(CharacterProfile(name="丙"))
    engine2.save(str(path))

    assert json.loads(path.read_text(encoding="utf-8")).keys() == {"丙"}


def test_loads_real_project_archives():
    """仓库里现有档案（含 2 字节的 "{}"）都必须能读进来。"""
    projects = ROOT / "data" / "projects"
    files = sorted(projects.glob("*/characters.json")) if projects.exists() else []
    if not files:  # pragma: no cover - 仓库里没有项目时跳过
        pytest.skip("仓库里没有可用的项目档案")

    for path in files:
        engine = make_engine()
        engine.load(str(path))          # 不抛异常即通过
        for profile in engine.all_characters():
            assert profile.name


# ========== A5：别名与括号写法归并 ==========

def test_alias_and_paren_variants_merge_into_one_profile():
    engine = make_engine()
    engine.add_character(CharacterProfile(name="林雪", aliases=["小雪"]))
    engine.llm = FakeLLM(analysis_json(
        {"name": "小雪", "mood": "紧张"},
        {"name": "林雪（林辰妹妹）", "mood": "平静"},
    ))

    outcome = engine.analyze_chapter_ex(1, "正文", ["林雪"])
    names = sorted(profile.name for profile in engine.all_characters())

    assert names == ["林雪"]                       # 此前会变成 3 个"角色"
    assert outcome.created == []
    assert len(outcome.updated) == 1
    assert ("林雪（林辰妹妹）", "林雪") in outcome.merged
    assert "林雪（林辰妹妹）" in engine.get_character("林雪").aliases
    assert [event.chapter for event in engine.get_character("林雪").chapter_events] == [1]


def test_full_width_and_half_width_parens_are_merged():
    engine = make_engine()
    engine.add_character(CharacterProfile(name="父亲（神秘人）"))
    engine.llm = FakeLLM(analysis_json({"name": "父亲(神秘人)", "mood": "安静"}))

    engine.analyze_chapter_ex(1, "正文", [])
    assert [profile.name for profile in engine.all_characters()] == ["父亲（神秘人）"]


def test_distinct_characters_are_not_merged():
    engine = make_engine()
    engine.llm = FakeLLM(analysis_json(
        {"name": "林雪", "mood": "紧张"},
        {"name": "林雨", "mood": "平静"},
    ))
    engine.analyze_chapter_ex(1, "正文", [])

    assert sorted(profile.name for profile in engine.all_characters()) == ["林雨", "林雪"]


# ========== A7：写作卡片的锚点 ==========

def test_card_keeps_anchor_fields_after_first_event():
    profile = CharacterProfile(
        name="甲", role="主角", aliases=["小甲"],
        personality={"冷静": 9}, speaking_style="寡言",
        core_desire="找到妹妹", core_fear="失去记忆",
        moral_compass={"诚实": 7}, background="来自边陲小镇", appearance="短发",
        chapter_events=[ChapterEvent(chapter=1, mood="愤怒", key_actions=["砸门"])],
    )
    card = profile.get_status_for_chapter(2)

    for expected in ("找到妹妹", "失去记忆", "诚实7/10", "来自边陲小镇",
                     "短发", "小甲", "砸门", "冷静9/10"):
        assert expected in card


def test_card_without_events_also_has_anchors():
    profile = CharacterProfile(name="乙", role="配角", core_desire="活下去")
    card = profile.get_status_for_chapter(1)

    assert "活下去" in card
    assert "未设定" in card          # 人格为空时的占位


def test_card_lists_relationship_changes_of_recent_events():
    engine = make_engine(FakeLLM(analysis_json({
        "name": "甲", "mood": "平静",
        "relationship_changes": [{"target": "乙", "old": "友好", "new": "怀疑"}]})))
    engine.analyze_chapter_ex(1, "正文", [])

    card = engine.get_character("甲").get_status_for_chapter(2)
    assert "关系变化: 乙 友好→怀疑" in card


# ========== A10：role ==========

def test_role_is_taken_from_analysis():
    assert '"role"' in CharacterEngine.CHARACTER_ANALYSIS_SYSTEM
    engine = make_engine(FakeLLM(analysis_json({"name": "甲", "role": "反派", "mood": "冷笑"})))
    engine.analyze_chapter_ex(1, "正文", [])
    assert engine.get_character("甲").role == "反派"


def test_role_defaults_to_supporting_when_model_omits_it():
    engine = make_engine(FakeLLM(analysis_json({"name": "甲", "mood": "平静"})))
    engine.analyze_chapter_ex(1, "正文", [])
    assert engine.get_character("甲").role == "配角"


# ========== A13：写作上下文裁剪 ==========

def _context_fixture():
    engine = make_engine()
    engine.add_character(CharacterProfile(name="主角甲", role="主角"))
    engine.add_character(CharacterProfile(name="反派乙", role="反派"))
    engine.add_character(CharacterProfile(name="近期丙", role="配角",
                                         chapter_events=[ChapterEvent(chapter=19, mood="紧张")]))
    engine.add_character(CharacterProfile(name="早年丁", role="配角",
                                         chapter_events=[ChapterEvent(chapter=1, mood="平静")]))
    engine.add_character(CharacterProfile(name="新人戊", role="配角"))
    return engine


def test_context_drops_characters_that_are_neither_recent_nor_leads():
    context = _context_fixture().get_context_for_writing(20)

    for expected in ("主角甲", "反派乙", "近期丙", "新人戊"):
        assert expected in context
    assert "早年丁" not in context          # 第 1 章出场过，之后 19 章没戏


def test_context_focus_forces_inclusion():
    context = _context_fixture().get_context_for_writing(20, focus=["早年丁"])
    assert "早年丁" in context


def test_context_include_all_restores_previous_behaviour():
    context = _context_fixture().get_context_for_writing(20, include_all=True)
    assert "早年丁" in context


def test_context_is_empty_without_characters():
    assert make_engine().get_context_for_writing(1) == ""


# ========== 解析健壮性（额外覆盖） ==========

def test_analysis_tolerates_garbage_field_types():
    engine = make_engine(FakeLLM(analysis_json({
        "name": "甲",
        "mood": {"情绪": "平静"},                 # 对象而不是字符串
        "key_actions": "砸门",                     # 标量而不是列表
        "personality": "不是字典",
        "relationship_changes": [{"target": "乙", "new": "怀疑"}],
        "personality_shifts": ["不是对象"],
        "summary": None,
    })))
    outcome = engine.analyze_chapter_ex(1, "正文", [])
    profile = engine.get_character("甲")

    assert outcome.status == "ok"
    assert profile.chapter_events[0].key_actions == ["砸门"]
    assert profile.personality == {}
    assert profile.relationships["乙"]["状态"] == "怀疑"


def test_characters_without_name_are_skipped():
    engine = make_engine(FakeLLM(analysis_json({"mood": "平静"}, {"name": "", "mood": "平静"})))
    outcome = engine.analyze_chapter_ex(1, "正文", [])

    assert engine.all_characters() == []
    assert outcome.status == STATUS_NO_CHANGE


def test_personality_shift_without_trait_is_skipped():
    engine = make_engine(FakeLLM(analysis_json({
        "name": "甲", "mood": "平静",
        "personality_shifts": [{"trait": "", "new": 9}, {"trait": "勇敢", "new": 9}]})))
    engine.analyze_chapter_ex(1, "正文", [])
    assert engine.get_character("甲").chapter_events[0].personality_shifts == [
        PersonalityShift(trait="勇敢", old_value=5, new_value=9, reason="")]


# ========== 首次写作：空角色库的显式引导 ==========

def test_empty_library_prompt_asks_for_new_characters():
    """角色库为空时必须在 prompt 里显式引导，否则模型容易返回空数组（首次写作 0 更新）。"""
    llm = FakeLLM(analysis_json({"name": "甲", "mood": "戒备"}))
    engine = make_engine(llm)

    engine.analyze_chapter_ex(1, "正文", [])

    assert "当前角色库为空" in llm.prompts[0]


def test_nonempty_library_prompt_has_no_empty_hint():
    llm = FakeLLM(analysis_json({"name": "甲", "mood": "平静"}))
    engine = make_engine(llm)

    engine.analyze_chapter_ex(1, "正文", ["甲"])

    assert "当前角色库为空" not in llm.prompts[0]
