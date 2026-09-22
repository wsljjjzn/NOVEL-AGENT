"""tui — 项目入口。

用法：
  python tui.py                      交互式终端界面（推荐）
  python tui.py novel list           一次性命令行（脚本/管道用）
  python tui.py novel show 项目名
  python tui.py kb files --filter all
命令行完整列表见 python tui.py -h；交互界面快捷键见界面内 ? 。

没装依赖？直接跑这个文件会告诉你怎么装（三种方式，见 _print_install_hint）。
本文件是"冷启动"入口，因此只 import 标准库 —— 任何第三方 import 都放在函数内部。
"""
import importlib.util
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 首参数命中这些（或不带参数）时进入交互界面，其余照旧走命令行
_INTERACTIVE = ("", "tui", "ui", "workbench")

# 核心功能所需（缺一个就跑不起来）—— 与 requirements-core.txt 对应
_CORE = {
    "yaml": "pyyaml", "dotenv": "python-dotenv", "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings", "rich": "rich", "loguru": "loguru",
    "openai": "openai", "chardet": "chardet",
}
# 只有交互界面需要
_UI = {"textual": "textual"}


def _missing(modules: dict) -> list:
    return [pkg for mod, pkg in modules.items() if importlib.util.find_spec(mod) is None]


def _print_install_hint(missing: list) -> None:
    """给出可直接复制的三种装法；有 uv 就把 uv 排在最前。"""
    py = sys.executable or "python3"
    has_uv = shutil.which("uv") is not None
    print("缺少依赖：" + "、".join(missing))
    print()
    print("任选一种方式（不需要预先创建虚拟环境也能跑）：")
    step = 1
    if has_uv:
        print(f"  {step}) uv（已检测到，最省事：自动建环境并装依赖）")
        print("       uv run tui.py")
        step += 1
    print(f"  {step}) 装到当前 Python 的用户目录（不动系统环境）")
    print(f"       {py} -m pip install --user -r requirements-core.txt")
    print(f"       {py} tui.py")
    step += 1
    print(f"  {step}) 用虚拟环境（隔离最干净，推荐长期使用）")
    print("       python3 -m venv .venv")
    print("       .venv/bin/python -m pip install -r requirements-core.txt")
    print("       .venv/bin/python tui.py")
    print()
    print("  · requirements-core.txt = 只跑命令行与界面所需（小，几十 MB）")
    print("  · requirements.txt      = 另含板块一的重型依赖（torch/chromadb 等，数 GB）")


def main() -> int:
    argv = sys.argv[1:]
    interactive = (not argv) or argv[0] in _INTERACTIVE

    # 先查依赖，给出可操作的提示，而不是抛一个 ModuleNotFoundError
    needed = dict(_CORE)
    if interactive:
        needed.update(_UI)
    missing = _missing(needed)
    if missing:
        _print_install_hint(missing)
        return 1

    if interactive:
        from src.tui.app import run
        return run()

    from src.cli.main import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
