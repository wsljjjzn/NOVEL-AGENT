"""
utils.logger — 日志配置（基于 loguru）。
"""

import sys
from pathlib import Path
from typing import Optional
from loguru import logger


def setup_logger(log_dir: str = "logs", level: str = "INFO",
                 console_level: Optional[str] = None) -> None:
    """配置全局日志器。

    Args:
        log_dir: 日志文件目录
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        console_level: 控制台级别；为 None 时与 level 一致。
            TUI 等界面场景可传 "WARNING"/"ERROR" 避免刷屏，
            同时日志文件仍按 level 记录完整信息。
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 移除默认 handler
    logger.remove()

    console_lv = (console_level or level).upper()

    # 控制台输出
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=console_lv,
        colorize=True,
    )

    # 文件输出（按天轮转，保留 30 天）
    logger.add(
        log_path / "writing_expert_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {name}:{function}:{line} - {message}",
        level=level.upper(),
        rotation="1 day",
        retention="30 days",
        encoding="utf-8",
    )

    logger.info(f"日志系统初始化完成，级别={level.upper()}（控制台 {console_lv}）")
