"""tests.test_rebuild_outline — 大纲重建脚本的回归测试。

只依赖标准库（脚本本身不 import 项目模块），因此本机缺 yaml/loguru/openai 时也能跑：

    python -m pytest tests/test_rebuild_outline.py       # 有 pytest 时
    python -c "import tests.test_rebuild_outline as t; \
        [getattr(t, n)() for n in dir(t) if n.startswith('test_')]"   # 无 pytest 时
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rebuild_outline as R  # noqa: E402


# ========== 标题：切点顺序与清洗 ==========

def test_title_cut_uses_earliest_boundary():
    """「，」在位置 5，「并」在位置 10 —— 必须取更靠前的那个切点。

    回归：早期实现按 TITLE_CUTS 列表顺序匹配，导致标题变成「触按弧形门，导致门融化」。
    """
    assert R.title_from_actions(["触按弧形门，导致门融化并进入幻境"], set(), 21) == "触按弧形门"


def test_title_strips_quotes():
    """回归：动作里的装饰性引号会让标题残缺（「开口说出‘她不在了」）。"""
    assert R.title_from_actions(["开口说出‘她不在了’"], set(), 48) == "开口说出她不在了"


def test_title_rejects_overlong_action():
    """超过 12 字的动作不是合格标题，应继续找下一个动作。"""
    assert R.title_from_actions(["将钝针翻转向掌心裂缝注入蓝光"], set(), 48) is None
    assert R.title_from_actions(
        ["将钝针翻转向掌心裂缝注入蓝光", "按在矩阵中央说出值得"], set(), 48
    ) == "按在矩阵中央说出值得"


def test_title_dedup():
    used = {"潜入服务器机房"}
    assert R.title_from_actions(["潜入服务器机房"], used, 3) is None


def test_title_from_text_prefers_nominal_phrase():
    text = "培养舱的蓝光亮起。培养舱里没有声音。培养舱依旧沉默。他走进通道。"
    title = R.title_from_text(text, set())
    assert title and title.endswith(("舱", "道"))


# ========== 摘要：来源筛选与截断 ==========

def test_absent_summary_detection():
    assert R.is_absent("本章未直接出场，但通过林辰的回忆可知她一直在等待。")
    assert R.is_absent("作为林辰的推荐人，其背景成为怀疑链条的一环。") is False
    assert R.is_absent("林辰潜入机房，发现数据包异常。") is False


def test_absent_events_are_skipped_when_picking_primary():
    events = [
        ("林辰", {"summary": "本章未出场，无变化。", "key_actions": []}),
        ("卡尔", {"summary": "卡尔锁定维修员罗德。", "key_actions": ["调取管道维修记录"]}),
    ]
    picked = R.pick_primary(events, protagonist="林辰")
    assert picked is not None and picked[0] == "卡尔"


def test_extractive_summary_truncates_at_boundary():
    """回归：截断不能停在半句（早期出现「关键行动：使」这类尾巴）。"""
    text = ("他沿着通道一直向前走，直到某个看不清的深处，"
            "那里有某种东西在等他，而他还不知道那究竟是什么。")
    summary = R.extractive_summary(text, max_sentences=1, max_chars=20)
    assert len(summary) <= 21
    assert summary.endswith("…")


def test_cut_clean_keeps_short_text_intact():
    assert R._cut_clean("短句。", 50) == "短句。"


# ========== 开放伏笔：精度 ==========

def test_open_foreshadowing_skips_movement_sentences():
    chapters = {49: "他在等。有人在更深处等你。林辰攥紧针，转身向更深处走去。"}
    items = R.open_foreshadowing(chapters, last_n=1, max_items=5)
    assert len(items) == 1
    assert "有人在更深处等你" in items[0]
    assert "转身向更深处走去" not in items[0]


def test_open_foreshadowing_carries_chapter_number():
    chapters = {50: "他握紧了针。她在更深处吗？"}
    items = R.open_foreshadowing(chapters, last_n=1, max_items=5)
    assert items and items[0].startswith("（第50章）")


def test_open_foreshadowing_ignores_plain_narration():
    chapters = {50: "他走进竖井深处。地面很凉。墙壁上有刻痕。"}
    assert R.open_foreshadowing(chapters, last_n=1, max_items=5) == []


# ========== 导出格式 ==========

def test_build_export_matches_novel_project_format():
    project = {
        "title": "测试书名", "genre": "科幻", "description": "一句话简介",
        "chapters": {"1": "正文一", "2": "正文二"},
        "chapter_titles": {"1": "开端", "2": "转折"},
    }
    out = R.build_export(project)
    assert out.startswith("# 测试书名\n\n*科幻* — 一句话简介\n\n---\n\n")
    assert "## 第1章 开端\n\n正文一\n" in out
    assert "## 第2章 转折\n\n正文二\n" in out
    assert out.endswith("正文二\n")


# ========== 安全护栏 ==========

def test_existing_outline_is_not_overwritten():
    tmp = Path(tempfile.mkdtemp())
    try:
        base = tmp / "proj"
        base.mkdir()
        original = {"name": "proj", "title": "proj", "chapters": {"1": "正文"},
                    "chapter_titles": {"1": "第1章"}, "outline": [{"chapter": 1, "title": "已有"}],
                    "foreshadowing": ["已有伏笔"], "metadata": {}, "description": "", "genre": ""}
        (base / "project.json").write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

        old = R.PROJECTS_DIR
        R.PROJECTS_DIR = tmp
        try:
            args = SimpleNamespace(project="proj", apply=True, force=False, open_chapters=8,
                                   max_open=8, max_content=200, rebuild_export=False)
            assert R.rebuild("proj", args) == 0
        finally:
            R.PROJECTS_DIR = old

        after = json.loads((base / "project.json").read_text(encoding="utf-8"))
        assert after == original, "已有大纲的项目不该被改动"
        assert not list(base.glob("project.json.bak-*")), "未写入就不该产生备份"
    finally:
        shutil.rmtree(tmp)
