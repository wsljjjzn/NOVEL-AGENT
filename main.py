
"""
main — 写作专家系统入口（默认走终端 TUI；Web 界面已暂停，可用 --mode gradio 显式开启）。
"""

import argparse
import sys
from pathlib import Path

# 将项目根目录加入 sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# TUI 顶层命令组：命中即委托给终端界面
_CLI_GROUPS = ("novel", "article", "kb", "tui")


def main():
    argv = sys.argv[1:]

    # ---- 终端界面（默认）----
    if argv and argv[0] in _CLI_GROUPS:
        from src.cli.main import main as cli_main
        raise SystemExit(cli_main(argv))

    # ---- 旧版 Web / 批处理模式（显式 --mode 才启动）----
    parser = argparse.ArgumentParser(description="写作专家系统（旧版入口，请优先使用 python tui.py）")
    parser.add_argument("--mode", choices=["api", "gradio", "preprocess", "test"], default=None,
                        help="运行模式（不传则输出使用指引，不启动任何服务）")
    parser.add_argument("--host", default="127.0.0.1", help="服务主机")
    parser.add_argument("--port", type=int, default=7860, help="服务端口")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    parser.add_argument("--config", default=None, help="配置文件路径")
    args = parser.parse_args(argv)

    if args.mode is None:
        print(
            "写作专家系统：Web 前端观测已暂停。\n"
            "请使用终端界面：\n"
            "  python tui.py -h            # 全部命令\n"
            "  python tui.py novel list    # 示例\n"
            "如需旧版 Web 界面：python main.py --mode gradio --port 7860"
        )
        return 0

    from src.utils.logger import setup_logger, logger
    setup_logger(level=args.log_level)
    cfg = get_config_safe()
    logger.info(f"配置加载完成: project_root={cfg.project_root}")

    if args.mode == "api":
        import uvicorn
        from src.api import app
        uvicorn.run(app, host=args.host, port=args.port)
    elif args.mode == "gradio":
        import gradio as gr
        from src.api.gradio_app import create_app
        app = create_app()
        app.launch(server_name=args.host, server_port=args.port, theme=gr.themes.Soft())
    elif args.mode == "preprocess":
        from scripts.batch_preprocess import main
        main()
    elif args.mode == "test":
        logger.info("测试模式启动")
        from src.models import (
            Chunk, KnowledgeUnit, StyleTemplate,
            WritingRequest, Outline, WrittenArticle,
            ReviewReport, AggregatedReview,
        )
        logger.info("所有模型导入成功")
    return 0


def get_config_safe():
    """加载配置；失败时返回带 project_root 的最小对象，避免报错。"""
    try:
        from config.settings import get_config
        return get_config()
    except Exception:
        from types import SimpleNamespace
        return SimpleNamespace(project_root=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
