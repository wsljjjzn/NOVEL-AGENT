"""
tui.app — 交互式终端界面（Textual）。

三屏结构：
    ProjectsScreen   项目列表 + 详情预览（进入/新建/删除）
    WorkbenchScreen  单个项目的工作台：大纲/章节/角色/剧情/伏笔 五个页签 + 底部实时日志
    ReaderScreen     章节正文阅读（n/p 翻章）

两条设计原则：
1. 凡是有副作用或花钱的动作，先弹窗收集参数、再二次确认，参数与风险同屏。
2. LLM 动作全部丢进后台 worker 线程，日志实时回传，界面不卡；同一时刻只允许一个
   动作在跑（exclusive worker），避免连点烧钱。
"""
from __future__ import annotations

from typing import Callable, Optional

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button, DataTable, Footer, Header, Label, RichLog, Static, TabbedContent, TabPane,
)

from src.novel.service import NovelService, Result
from src.tui.modals import ConfirmModal, FormModal

TIERS = ("flash", "pro")


def _clip(text: str, width: int) -> str:
    """按显示宽度截断（中文按 1 个字符算，配合 Textual 自动排版够用）。"""
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= width else text[: width - 1] + "…"


# ========== 消息：worker 线程 → 界面线程 ==========

class LogLine(Message):
    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class ActionDone(Message):
    def __init__(self, label: str, ok: bool, detail: str) -> None:
        self.label, self.ok, self.detail = label, ok, detail
        super().__init__()


# ========== 屏 1：项目列表 ==========

class ProjectsScreen(Screen):
    BINDINGS = [
        Binding("enter", "open_project", "打开"),
        Binding("n", "new_project", "新建"),
        Binding("d", "delete_project", "删除"),
        Binding("r", "reload", "刷新"),
        Binding("s", "settings", "设置/费用"),
        Binding("question_mark", "help", "帮助"),
        Binding("q", "quit_app", "退出"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="projects-hint")
        with Horizontal(id="projects-layout"):
            yield DataTable(id="project-table")
            yield Static("", id="project-detail")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("项目", "题材", "章节", "大纲", "伏笔", "总字数")
        self.reload()

    # ---- 数据 ----

    def reload(self) -> None:
        svc = self.app.make_service()
        table = self.query_one("#project-table", DataTable)
        keep = table.cursor_row
        table.clear()
        rows = svc.list_projects()
        for p in rows:
            table.add_row(
                Text(p["name"], no_wrap=True, overflow="ellipsis"),
                p["genre"] or "-",
                str(p["chapters"]),
                str(p["outline"]),
                str(p["foreshadowing"]),
                f"{p['words']:,}",
                key=p["name"],
            )
        if rows:
            table.move_cursor(row=min(keep, len(rows) - 1))
        self._show_detail()
        status = svc.llm_status()
        key_note = ("LLM: 已配置 Key" if status.get("configured")
                    else "LLM: 未配置 Key（只能浏览，写作动作会被拦下）")
        self.query_one("#projects-hint", Static).update(
            f"共 {len(rows)} 个项目　|　{key_note}　|　↑↓ 选择，Enter 打开，n 新建，d 删除，s 设置"
        )

    def _selected(self) -> Optional[str]:
        table = self.query_one("#project-table", DataTable)
        if table.row_count == 0:
            return None
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        except Exception:
            return None
        return row_key.value if row_key and row_key.value else None

    def _show_detail(self) -> None:
        name = self._selected()
        detail = self.query_one("#project-detail", Static)
        if not name:
            detail.update("（还没有项目，按 n 新建）")
            return
        rows = {p["name"]: p for p in self.app.make_service().list_projects()}
        p = rows.get(name)
        if not p:
            detail.update("")
            return
        try:
            bundle = self.app.make_service().load(name)
            chars = len(bundle.engine.all_characters())
            plots = len(bundle.plot.plots)
            written = len(bundle.project.chapters)
            total = max(len(bundle.project.outline), written)
            open_fs = len(bundle.project.foreshadowing)
        except Exception as e:
            detail.update(f"[red]加载失败：{e}[/red]")
            return
        detail.update(
            f"[bold]{p['name']}[/bold]\n\n"
            f"题材　{p['genre'] or '-'}\n"
            f"简介　{p['description'] or '-'}\n\n"
            f"章节　{written} 已写 / {total} 章规划\n"
            f"字数　{p['words']:,}\n"
            f"角色　{chars} 个\n"
            f"剧情　{plots} 章已设计\n"
            f"伏笔　{open_fs} 条未解\n\n"
            "[dim]Enter 进入工作台[/dim]"
        )

    @on(DataTable.RowHighlighted, "#project-table")
    def _on_highlight(self) -> None:
        self._show_detail()

    @on(DataTable.RowSelected, "#project-table")
    def _on_selected(self) -> None:
        self.action_open_project()

    # ---- 动作 ----

    def action_open_project(self) -> None:
        name = self._selected()
        if not name:
            self.notify("还没有项目", severity="warning")
            return
        self.app.push_screen(WorkbenchScreen(name))

    def action_reload(self) -> None:
        self.reload()
        self.notify("已刷新")

    def action_new_project(self) -> None:
        def done(data: Optional[dict]) -> None:
            if not data:
                return
            result = self.app.make_service().create(
                data["name"].strip(), data.get("genre", "").strip(),
                data.get("description", "").strip(),
            )
            self._report(result)
            if result.ok:
                self.reload()

        self.app.push_screen(FormModal(
            "新建项目",
            [
                ("name", "项目名（也是目录名，建议用书名）", "", ""),
                ("genre", "题材", "", "如：都市/校园/恋爱/黑帮"),
                ("description", "一句话简介", "", ""),
            ],
            notice="只会创建一个空项目目录，不会调用 LLM、不花钱。",
            submit_label="创建",
        ), done)

    def action_delete_project(self) -> None:
        name = self._selected()
        if not name:
            return
        rows = {p["name"]: p for p in self.app.make_service().list_projects()}
        p = rows.get(name, {})
        body = (f"将永久删除项目「{name}」的整个目录：\n"
                f"{p.get('chapters', 0)} 章正文、{p.get('words', 0):,} 字、"
                f"角色与剧情数据全部一起删除，无法恢复。")

        def done(yes: Optional[bool]) -> None:
            if not yes:
                return
            self._report(self.app.make_service().delete(name))
            self.reload()

        self.app.push_screen(ConfirmModal(f"删除项目：{name}", body, yes_label="永久删除"), done)

    def action_settings(self) -> None:
        self.app.push_screen(SettingsModal())

    def action_help(self) -> None:
        self.app.push_screen(HelpModal())

    def action_quit_app(self) -> None:
        self.app.exit()

    def _report(self, result: Result) -> None:
        if result.ok:
            self.notify(result.title, severity="information")
        else:
            self.notify(result.title, severity="error", timeout=8)


# ========== 屏 2：项目工作台 ==========

class WorkbenchScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "返回项目列表"),
        Binding("g", "gen_outline", "生成大纲"),
        Binding("c", "gen_characters", "生成角色"),
        Binding("p", "design_plot", "设计剧情"),
        Binding("w", "write_chapter", "撰写本章"),
        Binding("b", "batch_write", "批量续写"),
        Binding("o", "edit_outline", "改大纲"),
        Binding("t", "edit_plot_notes", "改剧情笔记"),
        Binding("e", "export", "导出"),
        Binding("l", "toggle_log", "日志面板"),
        Binding("s", "settings", "设置/费用"),
        Binding("question_mark", "help", "帮助"),
        Binding("r", "reload", "刷新"),
        Binding("q", "quit_app", "退出"),
    ]

    def __init__(self, project_name: str) -> None:
        super().__init__()
        self.project_name = project_name
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="workbench-title")
        with Vertical(id="workbench-body"):
            with TabbedContent(id="tabs"):
                with TabPane("章节", id="tab-chapters"):
                    yield DataTable(id="chapter-table")
                with TabPane("大纲", id="tab-outline"):
                    yield DataTable(id="outline-table")
                with TabPane("角色", id="tab-characters"):
                    yield DataTable(id="character-table")
                with TabPane("剧情", id="tab-plots"):
                    yield DataTable(id="plot-table")
                with TabPane("伏笔", id="tab-foreshadow"):
                    yield Static("", id="foreshadow-panel")
            # 默认收起：不跑动作时把高度让给章节表；一旦有动作日志就自动展开
            yield RichLog(id="log-panel", classes="hidden", highlight=False, markup=True, wrap=True)
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        for tid, cols in (
            ("#chapter-table", ("章号", "标题", "状态", "字数")),
            ("#outline-table", ("章号", "标题", "预期内容")),
            ("#character-table", ("姓名", "定位", "情绪", "人格")),
            ("#plot-table", ("章", "开篇钩子", "高潮", "结尾钩子")),
        ):
            table = self.query_one(tid, DataTable)
            table.cursor_type = "row"
            table.add_columns(*cols)
        self.log_line("[dim]提示：g 生成大纲 / c 生成角色 / p 设计剧情 / w 撰写本章 / b 批量续写[/dim]")
        self.reload()
        # 焦点默认给章节表：否则回车被页签栏吃掉、方向键也用不了
        self.query_one("#chapter-table", DataTable).focus()

    @on(TabbedContent.TabActivated)
    def _focus_tab_table(self, event: TabbedContent.TabActivated) -> None:
        """切页签时把焦点交给该页签的表格，方向键/回车立刻可用。"""
        pane_id = getattr(getattr(event, "pane", None), "id", None)
        target = {
            "tab-chapters": "#chapter-table",
            "tab-outline": "#outline-table",
            "tab-characters": "#character-table",
            "tab-plots": "#plot-table",
        }.get(pane_id)
        if target:
            try:
                self.query_one(target, DataTable).focus()
            except Exception:
                pass

    # ---- 数据装载 ----

    def reload(self) -> None:
        svc = self._svc()
        try:
            bundle = svc.load(self.project_name)
        except Exception as e:
            self.notify(f"加载失败：{e}", severity="error")
            return
        project, engine, plot = bundle.project, bundle.engine, bundle.plot

        title = project.title or self.project_name
        self.query_one("#workbench-title", Static).update(
            f"[bold]{title}[/bold]　[dim]{project.genre or '-'}[/dim]　"
            f"已写 {len(project.chapters)} 章 / {sum(len(v) for v in project.chapters.values()):,} 字"
        )

        # 章节
        t = self.query_one("#chapter-table", DataTable)
        t.clear()
        for c in project.list_chapters():
            t.add_row(str(c.number), c.title or "-", c.status, f"{c.word_count:,}", key=str(c.number))

        # 大纲
        t = self.query_one("#outline-table", DataTable)
        t.clear()
        for item in project.outline:
            t.add_row(str(item.chapter), item.title,
                      _clip(item.expected_content, 70), key=str(item.chapter))

        # 角色
        t = self.query_one("#character-table", DataTable)
        t.clear()
        for c in engine.all_characters():
            t.add_row(c.name, c.role or "-", _clip(c.current_mood, 22),
                      _clip(c.personality_summary(), 34), key=c.name)

        # 剧情
        t = self.query_one("#plot-table", DataTable)
        t.clear()
        for num in sorted(plot.plots):
            p = plot.plots[num]
            t.add_row(str(num), _clip(p.opening_hook, 26), _clip(p.climax, 26),
                      _clip(p.ending_hook, 26), key=str(num))

        # 伏笔
        fs = self.query_one("#foreshadow-panel", Static)
        if project.foreshadowing:
            fs.update("[bold]未解伏笔[/bold]\n" + "\n".join(
                f"· {f}" for f in project.foreshadowing))
        else:
            fs.update("[dim]暂无未解伏笔（生成剧情/写作时会自动记录）[/dim]")

        self._update_status()

    def _update_status(self) -> None:
        usage = self._svc().usage_summary()
        status = self._svc().llm_status()
        key_note = "Key 已配置" if status.get("configured") else "Key 未配置"
        budget = usage.get("budget") or 0
        budget_note = f" / 上限 ¥{budget:.0f}" if budget else ""
        self.query_one("#status-bar", Static).update(
            f"{self.project_name}　|　LLM {key_note}　|　"
            f"本会话调用 {usage['calls']} 次　费用 ¥{usage['cost']:.4f}{budget_note}"
            f"　|　[dim]? 帮助　l 日志[/dim]"
        )

    # ---- 日志与结果 ----

    def log_line(self, text: str) -> None:
        panel = self.query_one("#log-panel", RichLog)
        if panel.has_class("hidden"):
            panel.remove_class("hidden")   # 有日志就自动露出来
        panel.write(text)

    @on(LogLine)
    def _on_log(self, message: LogLine) -> None:
        self.log_line(message.text)

    @on(ActionDone)
    def _on_done(self, message: ActionDone) -> None:
        self._busy = False
        self._finish(message.label, Result(message.ok, message.detail))

    def _finish(self, label: str, result: Result) -> None:
        """所有动作的统一收尾：写日志、弹通知、刷新数据。"""
        style = "green" if result.ok else "red"
        first = result.title.splitlines()[0] if result.title else ""
        self.log_line(f"[{style}]■ {label}：{first}[/{style}]")
        for line in result.lines:
            self.log_line(f"  {line}")
        self.notify(first or label, severity="information" if result.ok else "error", timeout=8)
        self.reload()

    # ---- worker：所有会调 LLM 的动作都走这里 ----

    def _run(self, label: str, fn: Callable[[], Result]) -> None:
        """会调 LLM 的动作：查 Key、防重入、丢后台线程。"""
        if self._busy:
            self.notify("已有任务在执行，等它跑完（避免重复花钱）", severity="warning")
            return
        status = self._svc().llm_status()
        if not status.get("configured"):
            self.notify("未配置 API Key：写作类动作已拦下。按 s 查看怎么配置。",
                        severity="error", timeout=10)
            self.log_line("[red]✗ 未配置 API Key，动作未执行（未产生任何调用）[/red]")
            return
        self._busy = True
        self.log_line(f"[cyan]▶ {label}[/cyan]")
        self._work(label, fn)

    def _run_local(self, label: str, fn: Callable[[], Result]) -> None:
        """纯本地操作（导出、存剧情笔记）：同步执行。

        这些动作不调 LLM、不花钱，**所以不需要 API Key**，也不该占用 worker
        （回归：它们曾经走 _run，于是没配 Key 的人连"存剧情笔记"和"导出"都用不了）。
        """
        self.log_line(f"[cyan]▶ {label}[/cyan]")
        try:
            result = fn()
        except Exception as e:
            result = Result(False, f"{type(e).__name__}: {e}")
        self._finish(label, result)

    @work(thread=True, exclusive=True, group="llm")
    def _work(self, label: str, fn: Callable[[], Result]) -> None:
        try:
            result = fn()
        except Exception as e:  # service 层已兜住大部分，这里兜底
            self.post_message(ActionDone(label, False, f"{type(e).__name__}: {e}"))
            return
        self.post_message(ActionDone(label, result.ok, result.as_text()))

    def _svc(self) -> NovelService:
        """带日志回传的服务实例（经 App.make_service，便于测试替换）。"""
        return self.app.make_service(lambda s: self.post_message(LogLine(s)))

    def _ask(self, modal: ModalScreen, label: str,
             call: Callable[[dict], Result]) -> None:
        def done(data: Optional[dict]) -> None:
            if not data:
                return
            self._run(label, lambda: call(data))

        self.app.push_screen(modal, done)

    # ---- 各动作 ----

    def action_gen_outline(self) -> None:
        self._ask(FormModal(
            "生成分章大纲",
            [
                ("chapters", "总章节数", "10", ""),
                ("prompt", "故事简介 / 要求", "", "会作为大纲的故事梗概，越具体越好"),
                ("tier", "模型档位（flash 便宜 / pro 贵）", "flash", ""),
            ],
            notice="会覆盖现有大纲（正文与角色不受影响）。flash 档约几分钱。",
            submit_label="生成大纲",
        ), "生成大纲", lambda d: self._svc().generate_outline(
            self.project_name, int(d["chapters"] or 10), d.get("prompt", ""),
            (d.get("tier") or "flash").strip()))

    def action_gen_characters(self) -> None:
        def go(_d: dict) -> Result:
            return self._svc().generate_characters(self.project_name)

        def confirmed(yes: Optional[bool]) -> None:
            if yes:
                self._run("生成角色系统", lambda: go({}))

        self.app.push_screen(ConfirmModal(
            "重新生成角色系统",
            "会用 LLM 重新生成角色档案并**覆盖 characters.json**。\n\n"
            "已有角色的逐章事件（chapter_events）会尽量保留；\n"
            "覆盖前会自动备份为 characters.json.bak-<时间戳>。\n\n"
            "注意：这份文件是长篇连续性的核心数据，建议确认备份成功再继续。",
            yes_label="生成并覆盖（先备份）",
        ), confirmed)

    def action_design_plot(self) -> None:
        default_ch = self._next_chapter()
        self._ask(FormModal(
            "设计本章剧情",
            [
                ("chapter", "章号", str(default_ch), f"大纲里需已有该章（当前建议第 {default_ch} 章）"),
                ("tier", "模型档位", "flash", ""),
            ],
            notice="产出：开篇钩子 / 场景列表 / 高潮 / 结尾钩子 / 本章伏笔。flash 档即可。",
            submit_label="设计剧情",
        ), "设计剧情", lambda d: self._svc().design_plot(
            self.project_name, int(d["chapter"] or default_ch), (d.get("tier") or "flash").strip()))

    def action_write_chapter(self) -> None:
        default_ch = self._next_chapter()
        self._ask(FormModal(
            "撰写章节",
            [
                ("chapter", "章号", str(default_ch), ""),
                ("words", "目标字数", "2500", ""),
                ("tier", "模型档位（pro 更稳，贵）", "pro", ""),
                ("instructions", "额外写作要求（可空）", "", "例如：多一点环境描写，减少对话"),
            ],
            notice=("正文写作默认走 pro，费用明显高于 flash。\n"
                    "缺剧情设计时会先自动设计一章（多一次调用）。"),
            submit_label="开始写作",
            multiline_keys=("instructions",),
        ), "撰写章节", lambda d: self._svc().write_chapter(
            self.project_name, int(d["chapter"] or default_ch),
            int(d["words"] or 2500), (d.get("tier") or "pro").strip(),
            d.get("instructions", "")))

    def action_batch_write(self) -> None:
        default_ch = self._next_chapter()
        self._ask(FormModal(
            "批量续写",
            [
                ("start", "起始章", str(default_ch), "只会往后写；填已有章节号会被拒绝"),
                ("count", "连写几章", "3", ""),
                ("words", "每章目标字数", "2500", ""),
                ("tier", "模型档位", "pro", ""),
            ],
            notice=("逐章顺序执行，**失败即停**（避免连续烧钱）。\n"
                    "以 3 章 × 2500 字估算：几百次调用量级的费用由此产生，请先估算再跑。"),
            submit_label="开始批量续写",
            danger=True,
        ), "批量续写", lambda d: self._svc().batch_write(
            self.project_name, int(d["count"] or 1), int(d["words"] or 2500),
            (d.get("tier") or "pro").strip(), start=int(d["start"] or default_ch)))

    def action_edit_outline(self) -> None:
        chapter = self._selected_chapter("#outline-table") or self._next_chapter()
        bundle = self._svc().load(self.project_name)
        item = next((o for o in bundle.project.outline if o.chapter == chapter), None)
        if item is None:
            self.notify(f"大纲里没有第{chapter}章（可先按 g 生成，或在此新建）", severity="warning")

        def done(data: Optional[dict]) -> None:
            if not data:
                return
            fs = [x.strip() for x in (data.get("foreshadowing") or "").replace("；", ";").split(";") if x.strip()]
            result = self._svc().update_outline_item(
                self.project_name, int(data["chapter"]), data["title"].strip(),
                data["expected_content"].strip(), fs)
            if result.ok:
                self.notify(result.title)
                self.reload()
            else:
                self.notify(result.title, severity="error")

        self.app.push_screen(FormModal(
            f"编辑第{chapter}章大纲",
            [
                ("chapter", "章号", str(chapter), ""),
                ("title", "章节标题", item.title if item else "", ""),
                ("expected_content", "预期内容", item.expected_content if item else "",
                 "写成「本章要发生什么」，续写时会被注入模型"),
                ("foreshadowing", "本章伏笔（多个用 ; 分隔）",
                 "; ".join(item.key_foreshadowing) if item else "", ""),
            ],
            notice="纯本地编辑，不调用 LLM、不花钱。保存后立即生效。",
            submit_label="保存",
            multiline_keys=("expected_content",),
        ), done)

    def action_edit_plot_notes(self) -> None:
        chapter = self._selected_chapter("#plot-table") or self._next_chapter()
        bundle = self._svc().load(self.project_name)
        plot_obj = bundle.plot.plots.get(chapter)

        def done(data: Optional[dict]) -> None:
            if not data:
                return
            self._run_local(f"保存第{chapter}章剧情笔记",
                            lambda: self._svc().save_plot_notes(
                                self.project_name, chapter, data.get("notes", "")))

        self.app.push_screen(FormModal(
            f"第{chapter}章 剧情笔记",
            [("notes", "你手写的剧情安排（优先于 LLM 设计）",
              plot_obj.user_notes if plot_obj else "",
              "写入 plots.json 的 user_notes，写作时会被注入 prompt")],
            notice="纯本地保存，不调用 LLM。",
            submit_label="保存笔记",
            multiline_keys=("notes",),
        ), done)

    def action_export(self) -> None:
        self._run_local("导出全文", lambda: self._svc().export(self.project_name))

    def action_toggle_log(self) -> None:
        panel = self.query_one("#log-panel", RichLog)
        panel.toggle_class("hidden")

    def action_settings(self) -> None:
        self.app.push_screen(SettingsModal())

    def action_help(self) -> None:
        self.app.push_screen(HelpModal())

    def action_reload(self) -> None:
        self.reload()
        self.notify("已刷新")

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit_app(self) -> None:
        self.app.exit()

    # ---- 交互辅助 ----

    def _next_chapter(self) -> int:
        try:
            bundle = self._svc().load(self.project_name)
            return (max(bundle.project.chapters) + 1) if bundle.project.chapters else 1
        except Exception:
            return 1

    def _selected_chapter(self, table_id: str) -> Optional[int]:
        table = self.query_one(table_id, DataTable)
        if table.row_count == 0:
            return None
        try:
            key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        except Exception:
            return None
        try:
            return int(key.value) if key and key.value else None
        except (TypeError, ValueError):
            return None

    @on(DataTable.RowSelected, "#chapter-table")
    def _open_reader(self) -> None:
        chapter = self._selected_chapter("#chapter-table")
        if chapter:
            self.app.push_screen(ReaderScreen(self.project_name, chapter))

    @on(DataTable.RowSelected, "#outline-table")
    def _edit_outline_row(self) -> None:
        self.action_edit_outline()

    @on(DataTable.RowSelected, "#plot-table")
    def _edit_plot_row(self) -> None:
        self.action_edit_plot_notes()


# ========== 屏 3：正文阅读器 ==========

class ReaderScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "返回"),
        Binding("n", "next_chapter", "下一章"),
        Binding("p", "prev_chapter", "上一章"),
        Binding("question_mark", "help", "帮助"),
        Binding("q", "quit_app", "退出"),
    ]

    def __init__(self, project_name: str, chapter: int) -> None:
        super().__init__()
        self.project_name = project_name
        self.chapter = chapter
        self._chapters: list[int] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="reader-title")
        with VerticalScroll(id="reader-scroll"):
            yield Static("", id="reader-body")
        yield Footer()

    def on_mount(self) -> None:
        self.load_chapter(self.chapter)

    def load_chapter(self, chapter: int) -> None:
        try:
            bundle = self.app.make_service().load(self.project_name)
        except Exception as e:
            self.notify(f"加载失败：{e}", severity="error")
            return
        project = bundle.project
        self._chapters = sorted(project.chapters)
        self.chapter = chapter
        text = project.get_chapter(chapter)
        title = project.chapter_titles.get(chapter, f"第{chapter}章")
        if not text:
            outline = next((o for o in project.outline if o.chapter == chapter), None)
            hint = f"（该章还没写。大纲预期：{outline.expected_content}）" if outline else "（该章还没写，大纲里也没有这一章）"
            body = f"[yellow]{hint}[/yellow]\n\n[dim]按 w 回工作台撰写本章[/dim]"
            self.query_one("#reader-title", Static).update(f"第{chapter}章 {title}　[dim]未写[/dim]")
        else:
            body = text
            idx = self._chapters.index(chapter) + 1 if chapter in self._chapters else 0
            self.query_one("#reader-title", Static).update(
                f"第{chapter}章 {title}　[dim]{len(text):,} 字　"
                f"（{idx}/{len(self._chapters)}）　n 下一章 / p 上一章 / esc 返回[/dim]"
            )
        self.query_one("#reader-body", Static).update(body)
        self.query_one("#reader-scroll", VerticalScroll).scroll_home(animate=False)

    def action_next_chapter(self) -> None:
        nxt = next((c for c in self._chapters if c > self.chapter), None)
        if nxt is None:
            self.notify("已是最后一章", severity="warning")
            return
        self.load_chapter(nxt)

    def action_prev_chapter(self) -> None:
        prv = next((c for c in reversed(self._chapters) if c < self.chapter), None)
        if prv is None:
            self.notify("已是第一章", severity="warning")
            return
        self.load_chapter(prv)

    def action_help(self) -> None:
        self.app.push_screen(HelpModal())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit_app(self) -> None:
        self.app.exit()


# ========== 弹窗：设置/费用、帮助 ==========

class SettingsModal(ModalScreen):
    BINDINGS = [Binding("escape", "close", "关闭"), Binding("r", "reload_config", "重载配置")]

    def compose(self) -> ComposeResult:
        with Vertical(id="form-box"):
            yield Label("设置 / 费用", id="form-title")
            yield Static("", id="form-notice")
            with VerticalScroll(id="form-fields"):
                yield Static("", id="settings-body")
            with Horizontal(id="form-buttons"):
                yield Button("重新读取配置 (r)", id="reload")
                yield Button("关闭", id="close")

    def on_mount(self) -> None:
        self.refresh_body()

    def refresh_body(self) -> None:
        svc = self.app.make_service()
        status = svc.llm_status()
        usage = svc.usage_summary()
        lines = []
        if status.get("error"):
            lines.append(f"[red]{status['error']}[/red]")
        for t in status.get("tiers", []):
            mark = "[green]✓[/green]" if t["key_ok"] else "[red]✗[/red]"
            lines.append(f"{mark} [bold]{t['tier']}[/bold]　模型 {t['model']}　{t['base_url']}")
        if not status.get("configured"):
            lines.append("")
            lines.append("[yellow]Key 未配置 → 写作类动作会被拦下（浏览和本地编辑不受影响）。[/yellow]")
            lines.append("配置方式（二选一，改完在这里按 r 重新读取）：")
            lines.append("  1. 项目根目录建 .env：DEEPSEEK_API_KEY=sk-xxx")
            lines.append("  2. export DEEPSEEK_API_KEY=sk-xxx 后重启本界面")
            lines.append("  Key 配好后若报 Model Not Exist，改 config/config.yaml 的 model 字段。")
        lines.append("")
        lines.append(f"[bold]本会话用量[/bold]　调用 {usage['calls']} 次　"
                     f"费用 ¥{usage['cost']:.4f}"
                     + (f" / 上限 ¥{usage['budget']:.2f}" if usage.get("budget") else ""))
        try:
            from config.settings import get_config
            cfg = get_config()
            lines.append(f"[dim]用量落库：{cfg.budget.usage_db}（可用 sqlite3 对账）[/dim]")
            lines.append(f"[dim]项目根：{cfg.project_root}[/dim]")
        except Exception:
            pass
        lines.append("[dim]Key/模型来自 config/config.yaml + 项目根 .env；本界面不改这两个文件。[/dim]")
        self.query_one("#settings-body", Static).update("\n".join(lines))

    def action_reload_config(self) -> None:
        ok, msg = self.app.make_service().reload_config()
        self.notify(msg, severity="information" if ok else "warning")
        self.refresh_body()

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "reload":
            self.action_reload_config()
        else:
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class HelpModal(ModalScreen):
    BINDINGS = [Binding("escape", "close", "关闭"), Binding("question_mark", "close", "关闭")]

    HELP = """[bold]项目列表[/bold]
  ↑↓ 选择　Enter 打开项目　n 新建　d 删除（二次确认）　r 刷新　s 设置/费用　q 退出

[bold]工作台（单个项目）[/bold]
  Tab / Shift+Tab　切换 章节·大纲·角色·剧情·伏笔 页签
  Enter　　　　　　章节页签：打开正文阅读器；大纲/剧情页签：编辑该行
  g  生成大纲（覆盖现有大纲，不动正文）
  c  生成角色系统（覆盖 characters.json，覆盖前自动备份）
  p  设计本章剧情　　w  撰写本章　　b  批量续写（往后写，不会重写已有章节）
  o  改大纲　　t  改剧情笔记（均为本地编辑，免费）
  e  导出全文　l 折叠/展开日志面板　r 刷新　esc 返回

[bold]正文阅读器[/bold]
  n 下一章　p 上一章　esc 返回

[bold]关于花钱[/bold]
  · 只有 g / c / p / w / b 五个动作会调用 API，其余操作全免费。
  · 未配置 API Key 时这些动作会被直接拦下，不会产生任何调用。
  · 每个动作跑在后台线程，同一时刻只允许一个动作执行，防止连点重复计费。
  · 底部状态栏实时显示本会话调用次数与费用；硬上限见 config.yaml 的 budget。
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="form-box"):
            yield Label("帮助 / 快捷键", id="form-title")
            with VerticalScroll(id="form-fields"):
                yield Static(self.HELP)
            with Horizontal(id="form-buttons"):
                yield Button("关闭", id="close")

    @on(Button.Pressed)
    def _pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


# ========== App ==========

class NovelWorkbench(App):
    """长篇小说写作工作台（交互式 TUI）。"""

    CSS_PATH = "styles.tcss"
    TITLE = "小说写作工作台"
    SUB_TITLE = "Novel Agent"

    def __init__(self, base_dir: str = "data/projects",
                 service: Optional[NovelService] = None,
                 service_factory: Optional[Callable[[Callable[[str], None]], NovelService]] = None) -> None:
        """service: 只读用的服务实例；service_factory: 可注入的服务工厂（测试替身用）。"""
        super().__init__()
        self.service = service or NovelService(base_dir)
        self._service_factory = service_factory

    def make_service(self, log: Optional[Callable[[str], None]] = None) -> NovelService:
        """界面统一从这里取服务实例 —— 测试可以整个替换掉（注入假 LLM）。"""
        if self._service_factory is not None:
            return self._service_factory(log) if log else self._service_factory(lambda _s: None)
        return NovelService(self.service.base_dir, log=log or (lambda _s: None))

    def on_mount(self) -> None:
        self.push_screen(ProjectsScreen())


def run(base_dir: str = "data/projects") -> int:
    """命令行入口：python tui.py（无参数）会走到这里。"""
    from src.utils.logger import setup_logger
    setup_logger(level="INFO", console_level="ERROR")  # 日志写文件，别盖住界面
    NovelWorkbench(base_dir).run()
    return 0
