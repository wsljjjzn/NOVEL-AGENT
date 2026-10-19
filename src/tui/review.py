"""
tui.review — 审稿浮层。

流程（"勾选哪条就改哪条"）：
    参数 → 后台六维审稿 → 列出**可机械替换**的条目（Level 1 默认勾选、Level 2 默认不勾）
    → 用户勾选 → 「应用勾选并保存」→ 覆盖前备份 project.json。
Level 3 与缺 before/after 的条目只作人工指引，不参与勾选。

为什么单独一个模块
------------------
审稿是 TUI 里最贵的单个动作（默认 6 次模型调用），需要把
「参数 / 风险 / 进度 / 结果」放在同一屏里。工作台与正文阅读器都通过
`push_screen(ReviewModal(...))` 复用它，避免两处各写一遍编排。

界面层护栏：
- 审稿进行中禁止关闭浮层（否则 worker 被取消，钱已花、结果丢）
- 一个浮层只允许点一次「开始」、一次「应用」（防连点重复计费/重复改写）
- 应用是**显式动作**：没有任何"审完就自动改正文"的静默写入
"""
from __future__ import annotations

from typing import Optional

from rich.markdown import Markdown as RichMarkdown
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, SelectionList, Static

from src.models import ReviewIssue
from src.novel.service import NovelService, Result


_MAX_LABEL_DESC = 56
_MAX_LABEL_SUGGESTION = 30
_MAX_GUIDANCE_LINES = 12


class _ReviewLog(Message):
    """worker 线程 → 界面线程：进度文本。"""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class _ReviewDone(Message):
    def __init__(self, result: Result) -> None:
        self.result = result
        super().__init__()


class _ApplyDone(Message):
    def __init__(self, result: Result) -> None:
        self.result = result
        super().__init__()


class ReportModal(ModalScreen[None]):
    """完整审稿报告（Markdown）浮层。"""

    BINDINGS = [Binding("escape", "close", "关闭")]

    def __init__(self, title: str, markdown: str) -> None:
        super().__init__()
        self._title = title
        self._markdown = markdown

    def compose(self) -> ComposeResult:
        with Vertical(id="report-box"):
            yield Label(self._title, id="report-title")
            with VerticalScroll(id="report-scroll"):
                yield Static(RichMarkdown(self._markdown), id="report-body")
            with Horizontal(id="report-buttons"):
                yield Button("关闭", id="report-close")

    @on(Button.Pressed, "#report-close")
    def _pressed_close(self) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class ReviewModal(ModalScreen[Optional[Result]]):
    """单章审稿浮层：审完让用户勾选要应用的条目。

    dismiss 的返回值：应用过则返回应用结果；只审过则返回审稿结果；
    直接关闭返回 None。
    """

    BINDINGS = [Binding("escape", "close", "关闭")]

    def __init__(self, project_name: str, chapter: int, tier: str = "pro") -> None:
        super().__init__()
        self.project_name = project_name
        self.chapter = int(chapter)
        self._tier = tier if tier in ("flash", "pro") else "pro"
        self._busy = False
        self._started = False
        self._applied = False
        self._result: Optional[Result] = None
        self._applied_result: Optional[Result] = None
        self._issues: list[ReviewIssue] = []
        self._service: Optional[NovelService] = None

    # ---- 布局 ----

    def compose(self) -> ComposeResult:
        with Vertical(id="review-box"):
            yield Label(f"审稿 · 第{self.chapter}章", id="review-title")
            yield Static("", id="review-notice")
            with Horizontal(id="review-params"):
                yield Select(
                    [("pro（更稳，贵）", "pro"), ("flash（便宜）", "flash")],
                    value=self._tier, allow_blank=False, id="review-tier",
                )
                yield Static("", id="review-counts")
            yield SelectionList(id="review-issues")
            with VerticalScroll(id="review-guidance-scroll"):
                yield Static("", id="review-guidance")
            with Horizontal(id="review-buttons"):
                yield Button("开始六维审稿", variant="primary", id="review-start")
                yield Button("应用勾选并保存", variant="success", id="review-apply")
                yield Button("全选", id="review-all")
                yield Button("全不选", id="review-none")
                yield Button("完整报告", id="review-report-btn")
                yield Button("关闭", id="review-close")
            yield Static(
                "↑↓ 移动　空格 勾选/取消　Enter 也可切换　·　"
                "Level 1 默认勾选、Level 2 需你确认；写回前自动备份 project.json",
                id="review-hint",
            )

    def on_mount(self) -> None:
        self._set_notice(self._idle_notice())
        self._set_review_controls(visible=False)

    def _idle_notice(self) -> str:
        return (
            "将对照【作品状态】审阅本章：人物一致性 / 设定连续性 / 伏笔回收 / 节奏 / 语言 / 校对。\n"
            "审完会列出可机械替换的修改点，你勾选哪条就只改哪条；"
            "情节类问题只作指引，不会自动改写。"
        )

    def _set_notice(self, text: str) -> None:
        self.query_one("#review-notice", Static).update(text)

    def _set_review_controls(self, visible: bool) -> None:
        """审稿前只露「开始」；审稿后换成勾选/应用相关按钮。"""
        self.query_one("#review-start", Button).display = not visible
        for widget_id in ("#review-apply", "#review-all", "#review-none", "#review-report-btn"):
            self.query_one(widget_id, Button).display = visible
        self.query_one("#review-issues", SelectionList).display = visible
        self.query_one("#review-apply", Button).disabled = False

    # ---- 事件 ----

    @on(Button.Pressed, "#review-start")
    def _pressed_start(self) -> None:
        self._begin()

    @on(Button.Pressed, "#review-close")
    def _pressed_close(self) -> None:
        self.action_close()

    @on(Button.Pressed, "#review-all")
    def _pressed_all(self) -> None:
        if self._result is not None:
            self.query_one("#review-issues", SelectionList).select_all()

    @on(Button.Pressed, "#review-none")
    def _pressed_none(self) -> None:
        if self._result is not None:
            self.query_one("#review-issues", SelectionList).deselect_all()

    @on(Button.Pressed, "#review-report-btn")
    def _pressed_report(self) -> None:
        if self._result is not None and self._result.report.strip():
            self.app.push_screen(
                ReportModal(f"审稿报告 · 第{self.chapter}章", self._result.report)
            )

    @on(Button.Pressed, "#review-apply")
    def _pressed_apply(self) -> None:
        self._apply_selected()

    @on(_ReviewLog)
    def _on_log(self, message: _ReviewLog) -> None:
        self._set_notice(message.text)

    @on(_ReviewDone)
    def _on_review_done(self, message: _ReviewDone) -> None:
        self._busy = False
        self._result = message.result
        self.query_one("#review-tier", Select).disabled = True
        self._set_review_controls(visible=True)
        self._populate_issues(message.result)
        self._set_notice(self._render_summary(message.result))

    @on(_ApplyDone)
    def _on_apply_done(self, message: _ApplyDone) -> None:
        self._busy = False
        self._applied_result = message.result
        if message.result.ok:
            self._applied = True
            self.query_one("#review-apply", Button).disabled = True
            self.query_one("#review-issues", SelectionList).disabled = True
        else:
            # 没改成就允许重试（例如用户想换一批条目）
            self.query_one("#review-apply", Button).disabled = False
        self._set_notice(self._render_summary(message.result))
        self.notify(message.result.title,
                    severity="information" if message.result.ok else "error", timeout=8)

    # ---- 后台：审稿 ----

    def _begin(self) -> None:
        if self._busy or self._started:
            return
        self._started = True
        self._busy = True
        tier = str(self.query_one("#review-tier", Select).value or "pro")
        self.query_one("#review-start", Button).disabled = True
        self._set_notice(f"[yellow]六维审稿中（{tier}）… 六个维度并行，通常需要 1 分钟左右[/yellow]")
        self._service = self.app.make_service(  # type: ignore[attr-defined]
            lambda s: self.post_message(_ReviewLog(s))
        )
        self._work(tier)

    @work(thread=True, exclusive=True, group="review")
    def _work(self, tier: str) -> None:
        try:
            # apply_level1=False：不在服务层自动改，等用户勾选
            result = self._service.review_chapter(
                self.project_name, self.chapter, tier=tier,
                apply_level1=False, save=False,
            )
        except Exception as e:  # 服务层已兜住大部分，这里兜底
            result = Result(False, f"审稿失败：{type(e).__name__}: {e}")
        self.post_message(_ReviewDone(result))

    # ---- 后台：应用勾选 ----

    def _apply_selected(self) -> None:
        if self._busy or self._applied or self._result is None:
            return
        selector = self.query_one("#review-issues", SelectionList)
        chosen = [self._issues[i] for i in selector.selected
                  if isinstance(i, int) and 0 <= i < len(self._issues)]
        if not chosen:
            self.notify("没有勾选任何修改", severity="warning")
            return
        self._busy = True
        self.query_one("#review-apply", Button).disabled = True
        self._set_notice(f"[yellow]正在应用 {len(chosen)} 处修改…[/yellow]")
        self._apply_work(chosen)

    @work(thread=True, exclusive=True, group="review")
    def _apply_work(self, issues: list) -> None:
        try:
            result = self._service.apply_review_fixes(
                self.project_name, self.chapter, issues,
            )
        except Exception as e:
            result = Result(False, f"应用失败：{type(e).__name__}: {e}")
        self.post_message(_ApplyDone(result))

    # ---- 渲染 ----

    def _populate_issues(self, result: Result) -> None:
        aggregated = result.data
        issues = list(getattr(aggregated, "applicable_issues", []) or [])
        guidance = list(getattr(aggregated, "guidance_issues", []) or [])
        self._issues = issues

        selector = self.query_one("#review-issues", SelectionList)
        selector.clear_options()
        if issues:
            selector.add_options([
                (self._issue_label(issue), index, issue.level == 1)
                for index, issue in enumerate(issues)
            ])
        else:
            self.query_one("#review-apply", Button).disabled = True
        self.query_one("#review-counts", Static).update(
            f"可勾选 {len(issues)} 项 · 仅指引 {len(guidance)} 项"
        )

        guidance_text = self._guidance_text(guidance)
        self.query_one("#review-guidance-scroll", VerticalScroll).display = bool(guidance_text)
        self.query_one("#review-guidance", Static).update(guidance_text)

    @staticmethod
    def _issue_label(issue: ReviewIssue) -> str:
        """列表项标签。刻意不用方括号，避免被当成 Rich 标记解析。"""
        desc = " ".join((issue.description or "").split())
        if len(desc) > _MAX_LABEL_DESC:
            desc = desc[:_MAX_LABEL_DESC - 1] + "…"
        suggestion = " ".join((issue.suggestion or "").split())
        if len(suggestion) > _MAX_LABEL_SUGGESTION:
            suggestion = suggestion[:_MAX_LABEL_SUGGESTION - 1] + "…"
        head = f"L{issue.level} · {issue.agent} · {desc}"
        if issue.duplicated_by:
            head += f"（{'、'.join(issue.duplicated_by)} 也报出）"
        return f"{head}　→ {suggestion}" if suggestion else head

    @staticmethod
    def _guidance_text(issues: list) -> str:
        if not issues:
            return ""
        lines = ["仅人工处理（没有可直接替换的原文片段）："]
        for issue in issues[:_MAX_GUIDANCE_LINES]:
            desc = " ".join((issue.description or "").split())
            lines.append(f"· L{issue.level} · {issue.agent} · {desc[:60]}")
        if len(issues) > _MAX_GUIDANCE_LINES:
            lines.append(f"…另有 {len(issues) - _MAX_GUIDANCE_LINES} 条，见完整报告")
        return "\n".join(lines)

    @staticmethod
    def _render_summary(result: Result) -> str:
        if result.ok:
            head = f"[green]✓ {result.title}[/green]"
        else:
            head = f"[red]✗ {result.title}[/red]"
        body = "\n".join(f"· {line}" for line in result.lines)
        return f"{head}\n{body}" if body else head

    # ---- 关闭 ----

    def action_close(self) -> None:
        if self._busy:
            self.notify("任务进行中，请等它跑完（此时关闭会丢掉已付费的结果）",
                        severity="warning", timeout=8)
            return
        self.dismiss(self._applied_result or self._result)
