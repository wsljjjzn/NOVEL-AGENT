"""tests.test_tui — 交互式界面（Textual）的无头测试。

用 Textual 的 run_test() 在**没有真实终端**的环境里驱动界面：挂载、按键、断言屏幕内容。
这样界面逻辑就能进 CI，而不是只能靠人工在终端里点。

跑法（无需 pytest-asyncio，测试内部自己 asyncio.run）：
    python -m pytest tests/test_tui.py
    python -c "import tests.test_tui as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]"

注意：测试里**不会**触发任何真实 LLM 调用（本机没配 Key，动作会被拦下），
所以这些用例不会花钱。
"""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.novel.service import NovelService  # noqa: E402
from src.tui.app import (  # noqa: E402
    HelpModal, NovelWorkbench, ProjectsScreen, ReaderScreen, SettingsModal, WorkbenchScreen,
)
from src.tui.modals import ConfirmModal, FormModal  # noqa: E402


def _make_project(base: Path, name: str = "测试项目", chapters: int = 3) -> None:
    """造一个最小可用项目：project.json + characters.json + plots.json。"""
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(json.dumps({
        "name": name, "title": name, "genre": "科幻", "description": "一句话简介",
        "chapters": {str(i): f"这是第{i}章的正文内容。" * 20 for i in range(1, chapters + 1)},
        "chapter_titles": {str(i): f"第{i}章标题" for i in range(1, chapters + 1)},
        "outline": [{"chapter": i, "title": f"第{i}章标题",
                     "expected_content": f"第{i}章要发生的事", "key_foreshadowing": []}
                    for i in range(1, chapters + 2)],
        "metadata": {"total_words": 0, "chapter_count": chapters},
        "foreshadowing": ["未解的线索A", "未解的线索B"],
    }, ensure_ascii=False), encoding="utf-8")
    (d / "characters.json").write_text(json.dumps({
        "主角": {"name": "主角", "role": "主角", "personality": {"勇敢": 7},
                 "chapter_events": [{"chapter": 1, "mood": "紧张", "key_actions": [],
                                     "summary": "开场"}],
                 "relationships": {}, "arc_summary": ""},
    }, ensure_ascii=False), encoding="utf-8")
    (d / "plots.json").write_text(json.dumps({
        "plots": {"1": {"chapter": 1, "title": "第1章标题", "scenes": [],
                        "opening_hook": "钩子", "climax": "高潮", "ending_hook": "尾钩",
                        "foreshadowing_planted": [], "foreshadowing_resolved": [],
                        "character_appearances": {}, "emotional_arc": "", "user_notes": ""}},
        "world": {},
    }, ensure_ascii=False), encoding="utf-8")


class _Fixture:
    """临时项目目录（测试互不污染，也不碰仓库里的真实数据）。"""

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp())
        _make_project(self.tmp)
        return self.tmp

    def __exit__(self, *exc):
        shutil.rmtree(self.tmp, ignore_errors=True)


def _log_text(app: NovelWorkbench) -> str:
    """把工作台日志面板的文本抓出来，用于断言（比看通知更稳）。"""
    from textual.widgets import RichLog
    try:
        widget = app.screen.query_one(RichLog)
    except Exception:
        return ""
    parts = []
    for strip in widget.lines:
        parts.append(getattr(strip, "text", str(strip)))
    return "\n".join(parts)


# ========== 项目列表屏 ==========

def test_projects_screen_lists_projects():
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                from textual.widgets import DataTable
                table = app.screen.query_one("#project-table", DataTable)
                assert table.row_count == 1, f"应列出 1 个项目，实际 {table.row_count}"
                hint = app.screen.query_one("#projects-hint")
                assert "1 个项目" in str(hint.content)
            app.exit()

    asyncio.run(main())


def test_projects_screen_shows_key_status_warning():
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                hint = str(app.screen.query_one("#projects-hint").content)
                # 本机没配 Key —— 界面必须明确告知，而不是等用户点了才报错
                assert "未配置 Key" in hint or "已配置 Key" in hint
            app.exit()

    asyncio.run(main())


def test_new_project_modal_opens_and_cancels():
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("n")
                await pilot.pause()
                assert isinstance(app.screen, FormModal), "按 n 应弹出新建表单"
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(app.screen, ProjectsScreen), "Esc 应关闭表单"
                # 取消后不应产生新项目
                assert len(NovelService(str(tmp)).list_projects()) == 1
            app.exit()

    asyncio.run(main())


def test_delete_requires_confirmation():
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("d")
                await pilot.pause()
                assert isinstance(app.screen, ConfirmModal), "删除必须二次确认"
                await pilot.press("escape")  # 取消
                await pilot.pause()
                assert (tmp / "测试项目" / "project.json").exists(), "取消后项目必须还在"
            app.exit()

    asyncio.run(main())


# ========== 工作台 ==========

def test_enter_opens_workbench_with_data():
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(app.screen, WorkbenchScreen)
                from textual.widgets import DataTable
                chapters = app.screen.query_one("#chapter-table", DataTable)
                outline = app.screen.query_one("#outline-table", DataTable)
                chars = app.screen.query_one("#character-table", DataTable)
                plots = app.screen.query_one("#plot-table", DataTable)
                # 章节表展示的是「已有正文 ∪ 大纲章号」的并集：
                # fixture 正文 3 章 + 大纲规划到第 4 章 → 4 行（第 4 章状态为待写）
                assert chapters.row_count == 4
                assert outline.row_count == 4
                assert chars.row_count == 1
                assert plots.row_count == 1
                title = str(app.screen.query_one("#workbench-title").content)
                assert "测试项目" in title
                status = str(app.screen.query_one("#status-bar").content)
                assert "本会话调用" in status
            app.exit()

    asyncio.run(main())


def test_escape_returns_to_projects():
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(app.screen, ProjectsScreen)
            app.exit()

    asyncio.run(main())


def test_reader_opens_chapter_and_flips():
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("enter")      # 进工作台
                await pilot.pause()
                await pilot.press("enter")      # 章节表首行 → 阅读器
                await pilot.pause()
                assert isinstance(app.screen, ReaderScreen), "章节行回车应打开阅读器"
                assert app.screen.chapter == 1
                body = str(app.screen.query_one("#reader-body").content)
                assert "第1章的正文内容" in body
                await pilot.press("n")
                await pilot.pause()
                assert app.screen.chapter == 2, "n 应翻到下一章"
                await pilot.press("p", "p")
                await pilot.pause()
                assert app.screen.chapter in (1, 2), "p 不应越界到负数章"
                assert app.screen.chapter == 1
            app.exit()

    asyncio.run(main())


# ========== 花钱动作的护栏（关键） ==========

def test_llm_action_blocked_without_key():
    """没配 Key 时按 w 必须被拦下：不启动 worker、不产生调用、不写章节。

    这里注入一个"永远报告未配置"的服务替身，用例结果与本机是否配了 Key 无关。
    """
    async def main():
        with _Fixture() as tmp:
            class Unconfigured(NovelService):
                def llm_status(self):
                    return {"tiers": [], "configured": False, "budget_cny": 0.0}

            app = NovelWorkbench(
                base_dir=str(tmp),
                service_factory=lambda log: Unconfigured(str(tmp), log=log),
            )
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("enter")          # 进工作台
                await pilot.pause()
                await pilot.press("w")              # 撰写本章 → 先弹参数表单
                await pilot.pause()
                assert isinstance(app.screen, FormModal)
                # 直接在章号输入框回车提交（也就是用户的操作路径）
                await pilot.press("enter")
                await pilot.pause()

                data = json.loads((tmp / "测试项目" / "project.json").read_text("utf-8"))
                assert "4" not in data["chapters"], "未配置 Key 时不应写章节"
                assert len(data["chapters"]) == 3, "项目数据必须原样不动"
                # 日志里要留下"为什么没执行"的痕迹，而不是静默失败
                assert "未配置" in _log_text(app), "日志应说明被拦下的原因"
            app.exit()

    asyncio.run(main())


def test_batch_write_refuses_to_rewrite_existing_chapters(monkeypatch):
    """批量续写的起点必须"往后写"；填已有章号要被拒绝（这是 CLI auto 的坑）。

    P0-4：断言之前**必须先把 writer 换掉**。旧写法直接拿真 NovelService 断言，
    于是"护栏"本身成了这个测试的前提 —— 一旦护栏回归，它会真的发起 LLM 调用
    （花钱 + 依赖网络），而不是干脆地失败。
    """
    written: list[int] = []

    class RefusingWriter:
        """替身：一旦被调用就记账，供下面断言"根本不该被调到"。"""

        def __init__(self, *args, **kwargs):
            pass

        def write_chapter(self, chapter_num, *args, **kwargs) -> str:
            written.append(chapter_num)
            return "这个替身不该被调用" * 20

    monkeypatch.setattr("src.novel.service.ChapterWriter", RefusingWriter)

    async def main():
        with _Fixture() as tmp:
            svc = NovelService(str(tmp))
            r = svc.batch_write("测试项目", count=1, start=2)
            assert r.ok is False and "已有正文" in r.title
            # 项目数据未被改动
            data = json.loads((tmp / "测试项目" / "project.json").read_text("utf-8"))
            assert sorted(data["chapters"]) == ["1", "2", "3"]
            return r

    r = asyncio.run(main())
    assert r is not None
    assert written == [], f"护栏失效：批量续写真的去写第 {written} 章了"


def test_settings_modal_renders_status():
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("s")
                await pilot.pause()
                assert isinstance(app.screen, SettingsModal)
                body = str(app.screen.query_one("#settings-body").content)
                assert "flash" in body and "pro" in body
                assert "本会话用量" in body
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(app.screen, ProjectsScreen)
            app.exit()

    asyncio.run(main())


def test_help_modal_opens():
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("question_mark")
                await pilot.pause()
                assert isinstance(app.screen, HelpModal)
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(app.screen, ProjectsScreen)
            app.exit()

    asyncio.run(main())


# ========== 中文排版 ==========

def test_cjk_renders_without_breaking_borders():
    """中文按全角宽度排版：面板内每一行的显示宽度必须一致，否则边框会错位。

    这是比"看起来对不对"更硬的检查 —— 若中文宽度算错，含中文的行会比其他行
    多占或少占列，rstrip 后的显示宽度就不相等。
    """
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(120, 30)) as pilot:
                await pilot.pause()
                from rich.cells import cell_len
                lines = [s.text for s in app.screen._compositor.render_strips()]
                # 只看"以左边框开头、以右边框结尾"的内容行
                content_rows = [ln.rstrip() for ln in lines
                                if ln.startswith("│") and ln.rstrip().endswith("│")]
                assert content_rows, "应当渲染出面板内容行"
                widths = {cell_len(ln) for ln in content_rows}
                assert len(widths) == 1, f"面板行宽度不一致（中文宽度算错？）：{sorted(widths)}"
                # 且不能超出终端宽度
                assert max(widths) <= 120
            app.exit()

    asyncio.run(main())


def test_detail_panel_shows_no_key_warning():
    """详情栏与提示栏都要能显示内容（中文长文本不崩、不空）。"""
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(120, 30)) as pilot:
                await pilot.pause()
                detail = str(app.screen.query_one("#project-detail").content)
                assert "测试项目" in detail
                assert "角色" in detail and "伏笔" in detail
            app.exit()

    asyncio.run(main())


# ========== 入口分发：不带参数才进交互界面 ==========

def test_entrypoint_launches_tui_without_args(monkeypatch):
    """python tui.py（无参数）→ 交互界面；老命令行用法必须保持可用。"""
    import tui as entry

    calls = {}

    def fake_run(base_dir="data/projects"):
        calls["tui"] = base_dir
        return 0

    import src.tui.app as app_module
    monkeypatch.setattr(app_module, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["tui.py"])
    assert entry.main() == 0
    assert calls.get("tui") == "data/projects", "无参数应启动交互界面"


def test_entrypoint_keeps_cli_subcommands(monkeypatch):
    """python tui.py novel list 仍走命令行（脚本/管道场景不能破坏）。"""
    import tui as entry

    seen = {}

    def fake_cli(argv):
        seen["argv"] = argv
        return 7

    import src.cli.main as cli_module
    monkeypatch.setattr(cli_module, "main", fake_cli)
    monkeypatch.setattr(sys, "argv", ["tui.py", "novel", "list"])
    assert entry.main() == 7
    assert seen["argv"] == ["novel", "list"]


def test_entrypoint_accepts_explicit_tui_keyword(monkeypatch):
    import tui as entry

    def fake_run(base_dir="data/projects"):
        return 0

    import src.tui.app as app_module
    monkeypatch.setattr(app_module, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["tui.py", "tui"])
    assert entry.main() == 0


# ========== 表单可用性：键盘必须能把表单走完 ==========

def test_new_project_enter_in_input_creates_project():
    """回归：在输入框里按 Enter 必须提交 —— 否则用户"填完了却确定不了"。

    症状（用户报告）：新建项目填了书名，按 Enter 毫无反应，弹窗关不掉。
    原因：Input 按 Enter 只发出 Input.Submitted 消息，当时没有任何人处理它。
    """
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("n")
                await pilot.pause()
                assert isinstance(app.screen, FormModal)
                for ch in "我的新书":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause()

                assert not isinstance(app.screen, FormModal), "Enter 应当关闭表单并提交"
                assert (tmp / "我的新书" / "project.json").exists(), "项目应当被创建"
                from textual.widgets import DataTable
                table = app.screen.query_one("#project-table", DataTable)
                assert table.row_count == 2, "列表应刷新出新项目"
            app.exit()

    asyncio.run(main())


def test_form_tab_reaches_submit_and_cancel_buttons():
    """只用键盘也要能走到按钮（不能只有鼠标点得到）。"""
    async def main():
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("n")
                await pilot.pause()
                chain = [getattr(w, "id", None) for w in app.screen.focus_chain]
                assert "ok" in chain and "cancel" in chain, f"按钮不在焦点链里：{chain}"
                # Tab 一路走到"创建"按钮并回车提交
                for _ in range(len(chain)):
                    if getattr(app.focused, "id", None) == "ok":
                        break
                    await pilot.press("tab")
                    await pilot.pause()
                assert getattr(app.focused, "id", None) == "ok", "Tab 应当能到达提交按钮"
                await pilot.press("enter")
                await pilot.pause()
                assert not isinstance(app.screen, FormModal)
            app.exit()

    asyncio.run(main())


def test_multiline_field_enter_does_not_submit():
    """多行字段里 Enter 必须是换行，不能被当成提交（否则正文备注会被截断）。"""
    async def main():
        from textual.widgets import TextArea
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("enter")   # 进工作台
                await pilot.pause()
                await pilot.press("t")       # 改剧情笔记（只有多行字段）
                await pilot.pause()
                assert isinstance(app.screen, FormModal)
                area = app.screen.query_one("TextArea", TextArea)
                # 只有多行字段的表单，焦点应默认落在它身上（回归：原先没人拿焦点）
                assert app.focused is area, "多行字段应默认获得焦点"
                await pilot.pause()
                await pilot.press("a", "b", "enter", "c")
                await pilot.pause()
                assert isinstance(app.screen, FormModal), "多行字段里 Enter 不应提交表单"
                assert "\n" in area.text, "Enter 应当插入换行"
            app.exit()

    asyncio.run(main())


def test_plot_notes_form_saves_via_button():
    """多行表单通过按钮提交后，笔记要真的落盘。"""
    async def main():
        from textual.widgets import Button, TextArea
        with _Fixture() as tmp:
            app = NovelWorkbench(base_dir=str(tmp))
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                await pilot.press("t")
                await pilot.pause()
                area = app.screen.query_one("TextArea", TextArea)
                area.text = "这里我要加一场雨戏"
                await pilot.click("#ok")
                await pilot.pause()
                data = json.loads((tmp / "测试项目" / "plots.json").read_text("utf-8"))
                notes = [p.get("user_notes") for p in data.get("plots", {}).values()]
                assert "这里我要加一场雨戏" in notes, f"笔记没落盘：{data.get('plots')}"
            app.exit()

    asyncio.run(main())


def test_local_actions_work_without_api_key():
    """回归：导出与存剧情笔记是纯本地操作，没配 Key 也必须能用。

    原先它们走了 _run（会先查 Key），于是没 Key 的用户连笔记都存不了。
    """
    async def main():
        from textual.widgets import TextArea
        with _Fixture() as tmp:
            class Unconfigured(NovelService):
                def llm_status(self):
                    return {"tiers": [], "configured": False, "budget_cny": 0.0}

            app = NovelWorkbench(
                base_dir=str(tmp),
                service_factory=lambda log: Unconfigured(str(tmp), log=log),
            )
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.pause()
                await pilot.press("enter")      # 进工作台
                await pilot.pause()

                # 1) 存剧情笔记
                await pilot.press("t")
                await pilot.pause()
                area = app.screen.query_one("TextArea", TextArea)
                area.text = "没配 Key 也要能存"
                await pilot.press("tab", "tab")   # 走到提交按钮
                await pilot.pause()
                from textual.widgets import Button
                app.screen.query_one("#ok", Button).press()
                await pilot.pause()
                notes = [p.get("user_notes")
                         for p in json.loads((tmp / "测试项目" / "plots.json")
                                             .read_text("utf-8"))["plots"].values()]
                assert "没配 Key 也要能存" in notes, f"本地笔记未落盘：{notes}"

                # 2) 导出全文
                await pilot.press("e")
                await pilot.pause()
                assert (tmp / "测试项目" / "export.txt").exists(), "本地导出应可用"
                assert "第1章的正文内容" in (tmp / "测试项目" / "export.txt").read_text("utf-8")
            app.exit()

    asyncio.run(main())
