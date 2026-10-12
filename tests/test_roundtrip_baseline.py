"""tests.test_roundtrip_baseline — P1-1 读写往返基线（落盘契约锁）。

为什么需要这个文件
------------------
`plan/00-phases.md` 的 P1 要把领域模型改成 pydantic，并且明确要求 P1-1
"读写往返基线（**必须先做**）"。原因：`characters.json` / `project.json` 是
**允许手工编辑的长期存档**，任何模型层替换如果改变了落盘形状，老项目就会
打不开或悄悄丢字段。没有这条基线，迁移是否安全无法判断。

实测结论（2026-10-12，用真实存档 `data/projects/`，45 个角色）
-------------------------------------------------------------
load → dump 后 **39/45（87%）** 与磁盘不一致，差异收敛为四类：

| # | 差异 | 性质 | 本文件中的断言 |
|---|------|------|----------------|
| 1 | 关系表遗留键 `描述` 被丢弃（真实存档 8 条） | 🔴 **数据丢失** | ✅ **已修**（`_normalize_relationship` 改为原样保留未知键），直接断言 |
| 2 | 字符串关系 `"乙": "父亲，又敬又怕"` 被改写成 dict | 🟠 格式漂移 | 期望保持原样 → strict xfail |
| 3 | 同章重复的 `chapter_events` 被去重（保留后者） | ✅ **修复性**（A8） | 直接断言，当前通过 |
| 4 | 空 `relationship_changes` 键被补写到每个事件 | 🟠 格式漂移 | 期望保持磁盘原样 → strict xfail |

差异 4 已确认为**有意行为**（`to_dict` 无条件写出该键，是 A4 序列化对称的一部分，且无测试
要求空键存在），故不改，只留基线记录。

`strict=True` 的含义：一旦 1/2/4 被修好，这些用例会 **XPASS 并报失败**，
强制修的人回来更新这份基线，而不是让"已知漂移"悄悄变成"规范"。

样本一律内联，**不读 `data/projects/`** —— 用户会删项目，测试不能依赖用户数据。
"""

import pytest

from src.novel.character_engine import CharacterProfile


def roundtrip(raw: dict) -> dict:
    """按项目现有的读取/写回路径做一次 load → dump。"""
    name = raw.get("name", "测试角色")
    return CharacterProfile.from_dict(raw, fallback_name=name).to_dict()


# ========== 差异 1：遗留键 描述 被保留（曾丢失，已修） ==========

def test_legacy_relationship_description_key_survives_roundtrip():
    """遗留键 `描述` 必须原样带走 —— 它以前会在 load→save 时被静默丢掉。"""
    raw = {
        "name": "甲",
        "relationships": {"乙": {"状态": "信赖的挚友", "强度": 8, "描述": "隐约察觉他有秘密但从不追问"}},
    }

    out = roundtrip(raw)

    assert out["relationships"]["乙"]["描述"] == "隐约察觉他有秘密但从不追问"
    # 规范化后的已知键仍在，且被正确归一化
    assert out["relationships"]["乙"]["状态"] == "信赖的挚友"
    assert out["relationships"]["乙"]["强度"] == 8


# ========== 差异 2：字符串关系被规范化成 dict（格式漂移） ==========

@pytest.mark.xfail(strict=True, reason="已知漂移：字符串关系被 _normalize_relationship 改写成 dict 落盘")
def test_string_relationship_keeps_its_on_disk_shape():
    raw = {"name": "甲", "relationships": {"乙": "父亲，又敬又怕，临终前和解"}}

    out = roundtrip(raw)

    assert out["relationships"]["乙"] == "父亲，又敬又怕，临终前和解"


# ========== 差异 3：同章重复事件被去重（这是修复，直接锁住） ==========

def test_duplicate_chapter_events_dedupe_keeps_the_later_one():
    """A8 的修复行为：同一章写两次不再留下两条事件。

    去重保留**后写入**的那条（真实存档里它信息更全：7 个 key_actions vs 4 个）。
    这条是有意行为，因此不用 xfail，直接断言，防止将来退化成"两条都留"。
    """
    raw = {
        "name": "甲",
        "chapter_events": [
            {"chapter": 2, "mood": "坚定但紧张", "key_actions": ["送早餐"]},
            {"chapter": 2, "mood": "好奇且担忧", "key_actions": ["接近", "图书馆对话", "被警告"]},
        ],
    }

    out = roundtrip(raw)

    assert len(out["chapter_events"]) == 1
    assert out["chapter_events"][0]["mood"] == "好奇且担忧"
    assert out["chapter_events"][0]["key_actions"] == ["接近", "图书馆对话", "被警告"]


# ========== 差异 4：空 relationship_changes 键被补写（格式漂移） ==========

@pytest.mark.xfail(strict=True, reason="已知漂移：事件写回时无条件补出 relationship_changes 空键")
def test_event_without_relationship_changes_stays_without_it():
    raw = {"name": "甲", "chapter_events": [{"chapter": 1, "mood": "平静"}]}

    out = roundtrip(raw)

    assert "relationship_changes" not in out["chapter_events"][0]


# ========== 正向基线：手工编辑过的存档不能让项目打不开（A4，已修，必须保持） ==========

@pytest.mark.parametrize(
    "broken,label",
    [
        ({"name": "甲"}, "只有名字，其余全缺"),
        ({"name": "甲", "aliases": None, "personality": None}, "手改成 null"),
        ({"name": "甲", "chapter_events": [{"chapter": "3", "mood": "平静"}]}, '章号是字符串 "3"'),
        ({"name": "甲", "relationships": {"乙": None}}, "关系值是 null"),
        ({"name": "甲", "personality": {"勇敢": "很强"}}, "人格值是非数字"),
    ],
)
def test_hand_edited_save_still_loads(broken, label):
    """无论如何手改，load 都必须成功（不能抛异常）—— 这是 A4 修复的核心承诺。"""
    out = roundtrip(broken)

    assert out["name"] == "甲"
    assert isinstance(out["chapter_events"], list)
