"""console_scripts 入口：`na` / `na-tui` / `na-tools-preprocess`。

为什么要有这一层，而不是让 `[project.scripts]` 直接指向 `src.cli.main:main`
--------------------------------------------------------------------------
**把工作目录切到仓库根。** 数据（`data/projects`）、日志（`logs/`）、语料（`doc/`）
在 AGENTS.md 里都是**相对仓库根**的路径；`python tui.py` 只有站在仓库根运行才正确。
而安装出来的命令可以从任何目录被调用 —— 不切目录就会看到"项目列表是空的"
这种假故障（实测：从 `/tmp` 执行 `na novel list` 会打印"暂无项目"）。

顺便保证 `sys.path` 上有仓库根，`scripts.*` 这类顶层模块可导入。

⚠️ 切目录之后，命令行里**相对路径**的参数（如 `--out backup.txt`）以仓库根为基准；
绝对路径不受影响。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # src/cli/entrypoints.py → 仓库根


def _enter_repo_root() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)


def na() -> int:
    """`uv run na <novel|article|kb> ...`，等价于在仓库根跑 `python tui.py <子命令>`。"""
    _enter_repo_root()
    from src.cli.main import main

    return main(sys.argv[1:])


def na_tui() -> int:
    """`uv run na-tui` —— 交互式终端界面（Textual）。"""
    _enter_repo_root()
    from src.tui.app import run

    return run()


def na_tools_preprocess() -> int:
    """`uv run na-tools-preprocess` —— 批量语料预处理。"""
    _enter_repo_root()
    from scripts.batch_preprocess import main

    return main() or 0
