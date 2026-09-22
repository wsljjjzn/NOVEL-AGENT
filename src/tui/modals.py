"""
tui.modals — 交互式界面的输入/确认弹窗。

设计：写作动作都要花钱或覆盖文件，所以**每个有副作用的动作都先过一道弹窗**，
把参数和风险摆在同一屏里，而不是让用户按一个键就开跑。
"""
from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea


class FormModal(ModalScreen[Optional[dict]]):
    """通用表单弹窗：若干字段 → 返回 {字段名: 值} 或 None（取消）。

    fields: [(key, label, default, hint), ...]
    多行字段用 multiline_keys 指定（用 TextArea 而不是 Input）。
    """

    BINDINGS = [Binding("escape", "cancel", "取消")]

    def __init__(self, title: str, fields: list[tuple], notice: str = "",
                 submit_label: str = "确定", multiline_keys: tuple[str, ...] = (),
                 danger: bool = False):
        super().__init__()
        self._title = title
        self._fields = fields
        self._notice = notice
        self._submit_label = submit_label
        self._multiline = set(multiline_keys)
        self._danger = danger

    def compose(self) -> ComposeResult:
        with Vertical(id="form-box", classes="danger" if self._danger else ""):
            yield Label(self._title, id="form-title")
            if self._notice:
                yield Static(self._notice, id="form-notice")
            with VerticalScroll(id="form-fields"):
                for key, label, default, hint in self._fields:
                    yield Label(f"{label}", classes="field-label")
                    if hint:
                        yield Static(hint, classes="field-hint")
                    if key in self._multiline:
                        yield TextArea(default or "", id=f"f-{key}")
                    else:
                        yield Input(value=str(default or ""), id=f"f-{key}")
            with Horizontal(id="form-buttons"):
                yield Button(self._submit_label, variant="error" if self._danger else "primary",
                             id="ok")
                yield Button("取消", id="cancel")
            yield Static("Enter 确定　·　Tab 切换字段　·　Esc 取消",
                         id="form-hint")

    def on_mount(self) -> None:
        # 焦点给第一个可输入字段：只有多行字段的表单（如剧情笔记）原先拿不到焦点，
        # 用户得先按 Tab 才能开始打字
        for widget in self.query("Input, TextArea"):
            if widget.can_focus:
                widget.focus()
                return

    @on(Input.Submitted)
    def _on_input_submitted(self, _event: Input.Submitted) -> None:
        """在输入框里按 Enter 就提交 —— 这是用户的第一直觉。

        回归：Input 按下 Enter 只会发出 Input.Submitted 消息，没人处理的话
        界面毫无反应，用户会觉得"填完了却确定不了"。
        多行字段（TextArea）里 Enter 仍是换行，用 Tab 到按钮或点确定。
        """
        self.submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        self.submit()

    def submit(self) -> None:
        """收集各字段当前值并关闭弹窗（返回给回调）。"""
        data = {}
        for key, *_ in self._fields:
            area = self.query(f"#f-{key}")
            if not area:
                data[key] = ""
                continue
            widget = area.first()
            data[key] = widget.text if isinstance(widget, TextArea) else widget.value
        self.dismiss(data)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
    """二次确认弹窗（危险操作用，默认焦点在"取消"上）。"""

    BINDINGS = [Binding("escape", "no", "取消"), Binding("y", "yes", "确认")]

    def __init__(self, title: str, body: str, yes_label: str = "确认执行",
                 danger: bool = True):
        super().__init__()
        self._title = title
        self._body = body
        self._yes_label = yes_label
        self._danger = danger

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box", classes="danger" if self._danger else ""):
            yield Label(self._title, id="confirm-title")
            yield Static(self._body, id="confirm-body")
            with Horizontal(id="confirm-buttons"):
                yield Button(self._yes_label, variant="error" if self._danger else "primary", id="yes")
                yield Button("取消", variant="default", id="no")

    def on_mount(self) -> None:
        # 默认焦点给"取消"：危险操作不该靠回车就能过
        self.query_one("#no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)
