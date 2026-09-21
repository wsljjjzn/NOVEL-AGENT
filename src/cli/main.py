
"""cli.main — 终端界面主入口（Rich + argparse 命令式）。

命令结构：
  novel   list | create | show | outline | characters | plot | write | auto | export | delete
  article write | review | e2e
  kb      learn | files | query | stats | delete

设计：每个叶子命令绑定 args.func(args) -> int；命令结束后统一打印
本进程产生的 LLM 开销（对齐 Gradio 的常驻费用面板）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.panel import Panel

from .common import console, ensure_utf8, print_llm_summary


def build_parser():
    from argparse import ArgumentParser, RawDescriptionHelpFormatter
    from . import novel_commands, article_commands, kb_commands

    parser = ArgumentParser(
        prog="novel-tui",
        description="写作专家系统 · 终端界面（板块一学习 / 板块二写作 / 板块三审稿）",
        formatter_class=RawDescriptionHelpFormatter,
        epilog="""
示例：
  python tui.py novel list
  python tui.py novel show 项目名 --chars --plots
  python tui.py novel outline 项目名 --chapters 10 --prompt 简介
  python tui.py novel write 项目名 --chapter 1 --words 2500
  python tui.py kb files --filter user
  python tui.py article review 稿子.txt --out 稿子_fixed.txt
Web 界面已暂停；如需旧版可运行：python main.py --mode gradio""",
    )
    parser.add_argument("--log-level", default="INFO", help="日志级别 (DEBUG/INFO/WARNING/ERROR)")
    sub = parser.add_subparsers(dest="group", required=True)
    novel_commands.register(sub)
    article_commands.register(sub)
    kb_commands.register(sub)
    return parser


def main(argv=None) -> int:
    ensure_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        from src.utils.logger import setup_logger
        # TUI 下控制台保持安静（WARNING 以上才显示），完整日志仍写入 logs/ 文件
        setup_logger(level=args.log_level, console_level="WARNING")
    except Exception:
        pass

    code = 0
    try:
        code = int(args.func(args) or 0)
    except KeyboardInterrupt:
        console.print("\n[yellow]已中断[/yellow]")
        code = 130
    except Exception as e:
        console.print(Panel(f"{type(e).__name__}: {e}", title="命令执行失败", border_style="red"))
        code = 1
    finally:
        print_llm_summary()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
