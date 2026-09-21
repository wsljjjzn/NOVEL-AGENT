"""tui — 写作专家系统 终端界面（TUI）入口。

用法示例：
  python tui.py novel list
  python tui.py novel show 怀里的女孩是黑帮千金
  python tui.py kb files --filter all
运行 python tui.py -h 查看全部命令。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from src.cli.main import main as cli_main
    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
