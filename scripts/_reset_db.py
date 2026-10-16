"""显式确认后重置预处理数据库及 checkpoint。"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from src.utils.file_utils import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "knowledge" / "writing_expert.db"
DEFAULT_CHECKPOINT = ROOT / "data" / "preprocess_checkpoint.json"
DEFAULT_EMBEDDINGS = ROOT / "data" / "embeddings"


def reset(
    db_path: Path = DEFAULT_DB,
    checkpoint_path: Path = DEFAULT_CHECKPOINT,
    embeddings_path: Path = DEFAULT_EMBEDDINGS,
    *,
    confirmed: bool = False,
) -> int:
    """重置派生数据；数据库未成功删除时绝不清空 checkpoint。"""
    if not confirmed:
        print("这是破坏性操作。请加 --yes 后重试。")
        return 2

    if db_path.exists():
        try:
            size = db_path.stat().st_size
            db_path.unlink()
            print(f"已删除数据库（{size / 1024 / 1024:.1f} MB）")
        except OSError as exc:
            print(f"无法删除数据库，checkpoint 保持不变：{exc}")
            return 1

    atomic_write_json(checkpoint_path, {"completed": [], "count": 0})
    print("checkpoint 已重置")

    if embeddings_path.exists():
        shutil.rmtree(embeddings_path)
        print("embedding 数据已清理")

    print("清理完成。可重新运行预处理。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="重置预处理数据库与进度")
    parser.add_argument("--yes", action="store_true", help="确认删除派生数据")
    args = parser.parse_args(argv)
    return reset(confirmed=args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
