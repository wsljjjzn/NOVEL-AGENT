#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tui_snapshot — 无终端环境下给交互界面拍"文本快照"，用来验证排版。

为什么需要它：Textual 界面通常只能靠人肉在终端里看，无法进 CI。这个脚本用
App.run_test() 在无 TTY 环境里把界面渲染成文本打印出来，于是：
- 改完样式能立刻看出中文是否错位、面板是否被挤爆
- 可以在没有图形终端的机器上（比如 CI 容器）核对界面

用法：
    python3 scripts/tui_snapshot.py                 # 拍全部屏（真实项目数据）
    python3 scripts/tui_snapshot.py --screen projects --size 160x46
    python3 scripts/tui_snapshot.py --base-dir /tmp/fake-projects
    python3 scripts/tui_snapshot.py --out /tmp/snap.txt
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.tui.app import NovelWorkbench, ReaderScreen, SettingsModal  # noqa: E402


def snapshot(app, height: int) -> str:
    """把当前屏渲染成纯文本（保留边框与对齐）。"""
    strips = app.screen._compositor.render_strips()
    return "\n".join(s.text.rstrip() for s in strips[:height])


async def shoot(screen: str, base_dir: str, width: int, height: int) -> dict[str, str]:
    shots: dict[str, str] = {}
    app = NovelWorkbench(base_dir=base_dir)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        if screen in ("all", "projects"):
            shots["项目列表"] = snapshot(app, height)

        if screen in ("all", "workbench", "reader"):
            await pilot.press("enter")          # 打开第一个项目
            await pilot.pause()
            if screen in ("all", "workbench"):
                shots["工作台·章节"] = snapshot(app, height)
                # 切到角色/大纲页签各拍一张
                for key, name in (("right", "工作台·大纲"), ("right", "工作台·角色")):
                    await pilot.press(key)
                    await pilot.pause()
                    shots[name] = snapshot(app, height)
            if screen in ("all", "reader"):
                # 章节表行回车 → 阅读器
                await pilot.press("left", "left")   # 回到章节页签
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                if isinstance(app.screen, ReaderScreen):
                    shots["正文阅读器"] = snapshot(app, height)
                await pilot.press("escape")
                await pilot.pause()

        if screen in ("all", "settings"):
            await pilot.press("escape")          # 回项目列表
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            if isinstance(app.screen, SettingsModal):
                shots["设置/费用"] = snapshot(app, height)
    return shots


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="给交互式 TUI 拍无头文本快照")
    ap.add_argument("--screen", default="all",
                    choices=["all", "projects", "workbench", "reader", "settings"])
    ap.add_argument("--base-dir", default=str(ROOT / "data" / "projects"))
    ap.add_argument("--size", default="150x46", help="终端尺寸 WxH（默认 150x46）")
    ap.add_argument("--out", default="", help="把快照写入文件（默认打印）")
    args = ap.parse_args(argv)

    width, height = (int(x) for x in args.size.lower().split("x"))
    shots = asyncio.run(shoot(args.screen, args.base_dir, width, height))

    chunks = [f"{'=' * 20} {name} {'=' * 20}\n{body}" for name, body in shots.items()]
    text = "\n\n".join(chunks)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写入 {args.out}（{len(shots)} 张）")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
