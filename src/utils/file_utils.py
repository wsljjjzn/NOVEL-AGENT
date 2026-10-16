"""
utils.file_utils — 文件操作工具函数。
"""

import contextlib
import json
import os
import tempfile
from pathlib import Path

import chardet


def atomic_write_json(path: str | Path, data: object) -> None:
    """原子写入 JSON，避免进程中断留下半截存档。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), prefix=f"{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def detect_encoding(file_path: str) -> str:
    """检测文件编码。

    Args:
        file_path: 文件路径

    Returns:
        编码名称，如 'utf-8', 'gbk', 'gb2312'
    """
    with open(file_path, "rb") as f:
        raw = f.read(min(1024 * 1024, os.path.getsize(file_path)))  # 最多读 1MB
    result = chardet.detect(raw)
    encoding = result.get("encoding")
    return encoding if isinstance(encoding, str) else "utf-8"


def read_text_file(file_path: str, encoding: str | None = None) -> str:
    """读取文本文件，自动检测编码。

    Args:
        file_path: 文件路径
        encoding: 指定编码（不指定则自动检测）

    Returns:
        文件文本内容
    """
    if encoding is None:
        encoding = detect_encoding(file_path)

    try:
        with open(file_path, encoding=encoding) as f:
            return f.read()
    except UnicodeDecodeError as initial_error:
        # 尝试常见编码
        last_error = initial_error
        for enc in ["utf-8", "gbk", "gb2312", "utf-16", "latin-1"]:
            try:
                with open(file_path, encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError as error:
                last_error = error
                continue
        raise ValueError(f"无法解码文件: {file_path}") from last_error


def list_text_files(directory: str, extensions: set[str] | None = None) -> list[str]:
    """递归列出目录下所有文本文件。

    Args:
        directory: 目录路径
        extensions: 文件扩展名集合，默认 {'.txt', '.md'}

    Returns:
        文件路径列表
    """
    if extensions is None:
        extensions = {".txt", ".md"}

    files = []
    for root, _, filenames in os.walk(directory):
        for fn in filenames:
            if any(fn.endswith(ext) for ext in extensions):
                files.append(os.path.join(root, fn))
    return sorted(files)


def ensure_dir(dir_path: str) -> Path:
    """确保目录存在，不存在则创建。

    Args:
        dir_path: 目录路径

    Returns:
        Path 对象
    """
    p = Path(dir_path)
    p.mkdir(parents=True, exist_ok=True)
    return p
