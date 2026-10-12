"""tests.test_pydantic_models — 领域模型 pydantic 化的契约（P1-2）。

这一层换来的是**边界校验**，而不是改磁盘格式：

- `to_dict` / `from_dict` 仍是落盘契约（`tests/test_roundtrip_baseline.py` 锁住
  了它的四类行为），pydantic 负责"数据进来时"把类型归一化；
- `extra="allow"`：档案里不认识的键必须原样带走。pydantic 默认的 `"ignore"`
  会**静默丢字段** —— 与 CODE_REVIEW A15 点名的那个陷阱是同一件事，
  所以这里专门写一条守卫测试，防止有人把配置改回默认。

历史 bug 背景：LLM 直接给出的 dict 以前**绕过**所有归一化进入档案
（只有 `from_dict` 才做归一），于是 `chapter="3"`、`key_actions="一个动作"`、
`relationships={"乙": "描述文本"}` 会被原样存下去。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.novel.character_engine import ChapterEvent, CharacterProfile, PersonalityShift  # noqa: E402
from src.novel.project_manager import NovelProject, OutlineItem  # noqa: E402


# ========== 直接构造（LLM 输出路径）也要归一化 ==========

def test_plain_construction_normalizes_like_from_dict():
    """以前只有 from_dict 做归一；LLM 直接构造的 dict 会带着脏类型落盘。"""
    profile = CharacterProfile(name="甲", relationships={"乙": "父亲，又敬又怕"})

    assert profile.relationships["乙"]["状态"] == "父亲，又敬又怕"
    assert isinstance(profile.relationships["乙"]["强度"], int)


def test_relationships_keep_unknown_keys_on_plain_construction():
    """关系表里的遗留键（描述）在直接构造时也不能丢。"""
    profile = CharacterProfile(
        name="甲",
        relationships={"乙": {"状态": "挚友", "强度": 8, "描述": "从小一起长大"}},
    )

    assert profile.relationships["乙"]["描述"] == "从小一起长大"
    assert profile.to_dict()["relationships"]["乙"]["描述"] == "从小一起长大"


def test_chapter_event_coerces_messy_llm_output():
    event = ChapterEvent(chapter="3", key_actions="只有一个动作", summary=None)

    assert event.chapter == 3
    assert event.key_actions == ["只有一个动作"]
    assert event.summary == ""
    assert event.to_dict()["chapter"] == 3


def test_personality_shift_coerces_nulls_and_ranges():
    shift = PersonalityShift(trait=None, old_value=None, new_value=99, reason=None)

    assert shift.trait == ""
    assert shift.old_value == 5, "null 兜底为默认值 5（A9）"
    assert shift.new_value == 10, "越界夹到 10（A9）"
    assert shift.reason == ""


def test_personality_values_stay_loose_for_legacy_saves():
    """存量档案里有 {"善良": null} 这类值：构造不能报错，读取时兜底。"""
    profile = CharacterProfile(name="甲", personality={"善良": None, "勇敢": 99})

    assert profile.personality == {"善良": None, "勇敢": 99}
    assert profile.personality_summary() == "勇敢10/10, 善良5/10"   # 按特质名排序


def test_relationship_changes_stay_plain_dicts():
    """必须是纯 dict 列表：换成嵌套模型会让落盘时 isinstance(rc, dict) 为假而丢数据。"""
    event = ChapterEvent(chapter=1, relationship_changes=[
        {"target": "乙", "new": "敌视"},
        None,                     # 脏数据要被滤掉，而不是让构造失败
        "不是 dict",
    ])

    assert event.relationship_changes == [{"target": "乙", "new": "敌视"}]
    assert event.to_dict()["relationship_changes"] == [{"target": "乙", "new": "敌视"}]


# ========== extra="allow"：不认识的键不能丢 ==========

def test_unknown_keys_survive_roundtrip():
    """手工编辑或更新版本写出的未知字段必须原样带走（不是默认的静默丢弃）。"""
    raw = {"name": "甲", "未来字段": {"a": 1}, "另一个遗留键": "保留我"}

    profile = CharacterProfile.from_dict(raw)
    back = profile.to_dict()

    assert back["未来字段"] == {"a": 1}
    assert back["另一个遗留键"] == "保留我"


def test_extra_policy_is_allow_not_ignore():
    """守卫：pydantic 默认 extra='ignore' 会静默丢字段（A15 的坑），必须显式 allow。"""
    for model in (CharacterProfile, ChapterEvent, PersonalityShift):
        assert model.model_config.get("extra") == "allow", model.__name__
    assert OutlineItem.model_config.get("extra") == "allow"


def test_assignment_validation_stays_off():
    """引擎会在原地改字段与容器，开了赋值校验这些既有路径会直接报错。"""
    profile = CharacterProfile(name="甲")
    profile.personality["勇敢"] = 7          # 原地改 dict
    profile.chapter_events.append(ChapterEvent(chapter=1))   # 原地改 list
    profile.role = "主角"                     # 已声明字段直接赋值
    assert profile.personality == {"勇敢": 7}
    assert profile.role == "主角"


# ========== OutlineItem：章号归一化（CODE_REVIEW 建议 6） ==========

def test_outline_item_coerces_chapter_and_tolerates_nulls():
    item = OutlineItem(chapter="3", title=None, expected_content=None, key_foreshadowing=None)

    assert item.chapter == 3
    assert (item.title, item.expected_content, item.key_foreshadowing) == ("", "", [])


def test_project_with_string_chapter_numbers_loads_and_lists(tmp_path):
    """模型把章号写成 "3" 时，list_chapters 不再抛 TypeError（建议 6）。"""
    d = tmp_path / "脏项目"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({
        "name": "脏项目", "title": "脏项目",
        "chapters": {"1": "正文"},
        "chapter_titles": {},
        "outline": [{"chapter": "2", "title": "第二章", "expected_content": None}],
        "metadata": {}, "foreshadowing": [],
    }, ensure_ascii=False), encoding="utf-8")

    project = NovelProject.load(str(tmp_path), "脏项目")
    numbers = [c.number for c in project.list_chapters()]

    assert numbers == [1, 2]
    assert all(isinstance(n, int) for n in numbers)
