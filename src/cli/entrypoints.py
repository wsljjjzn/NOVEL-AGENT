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


def _enable_windows_kill_on_close() -> None:
    """在 Windows 上利用 Job Object 强制绑定进程生命周期到控制台。

    一旦控制台关闭（点击 [X] 或被关闭），Windows 内核级保证子进程与工作进程立刻被终止，
    杜绝孤儿进程留在后台占用 8000 端口和文件句柄。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h_job = kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryLimit", ctypes.c_size_t),
                ("PeakJobMemoryLimit", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JobObjectExtendedLimitInformation = 9

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        if kernel32.SetInformationJobObject(
            h_job,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            kernel32.AssignProcessToJobObject(h_job, kernel32.GetCurrentProcess())
    except Exception:
        pass


def na_studio() -> int:
    """`uv run na-studio` —— 启动 Novel Studio 现代写作 IDE 服务并打开浏览器。"""
    _enter_repo_root()
    _enable_windows_kill_on_close()

    import threading
    import time
    import webbrowser
    import uvicorn
    from src.utils.doctor import print_terminal_doctor

    # 1. 终端引擎自检输出
    print_terminal_doctor()

    def _open_browser():
        time.sleep(1.0)
        webbrowser.open("http://127.0.0.1:8000")

    threading.Thread(target=_open_browser, daemon=True).start()

    # 生产/分发模式默认单进程运行（reload=False），杜绝多进程监听导致“关掉控制台终端后子进程仍在后台残留”
    # 开发调试时可设置 NA_RELOAD=1 开启自动重载
    dev_reload = os.getenv("NA_RELOAD", "0").lower() in ("1", "true")

    uvicorn.run(
        "src.api.server:app",
        host="127.0.0.1",
        port=8000,
        reload=dev_reload,
        reload_dirs=[str(ROOT / "src"), str(ROOT / "web_prototype")] if dev_reload else None,
        log_level="warning",
    )
    return 0
