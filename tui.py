"""tui — 项目入口。

用法：
  python tui.py                      交互式终端界面（推荐）
  python tui.py novel list           一次性命令行（脚本/管道用）
  python tui.py novel show 项目名
  python tui.py kb files --filter all
命令行完整列表见 python tui.py -h；交互界面快捷键见界面内 ? 。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 首参数命中这些（或不带参数）时进入交互界面，其余照旧走命令行
_INTERACTIVE = ("", "tui", "ui", "workbench")


def main() -> int:
    argv = sys.argv[1:]

    if not argv or argv[0] in _INTERACTIVE:
        try:
            from src.tui.app import run
        except ImportError as e:
            print(f"交互式界面需要 textual（{e}）。\n"
                  f"  安装：python -m pip install textual\n"
                  f"  不想装也能用命令行：python tui.py novel list")
            return 1
        return run()

    from src.cli.main import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
