"""
scripts/batch_preprocess.py — 流式分批并行预处理，带总进度。
先快速扫路径（零内存压力），再按资源上限分批并行处理。
"""

import gc
import json
import logging as _logging
import os
import sqlite3
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_logging.getLogger().setLevel(_logging.ERROR)
_logging.getLogger("src").setLevel(_logging.ERROR)

from src.knowledge_base import init_db  # noqa: E402
from src.preprocessing import PreprocessingPipeline  # noqa: E402
from src.utils.file_utils import atomic_write_json  # noqa: E402

# 预处理主要受磁盘与 SQLite 写入限制；过多线程会耗尽句柄并加重锁竞争。
WORKERS = min(32, max(1, (os.cpu_count() or 1) * 2))
CHECKPOINT_FILE = ROOT / "data" / "preprocess_checkpoint.json"


def scan_paths(directory: str) -> list[str]:
    """快速收集所有 .txt 路径（只读文件名，不读内容）。"""
    paths = []
    for root, _dirs, filenames in os.walk(directory):
        for f in filenames:
            if f.endswith(".txt"):
                paths.append(os.path.join(root, f))
    return paths


def load_cp():
    if CHECKPOINT_FILE.exists():
        try:
            return set(json.loads(Path(CHECKPOINT_FILE).read_text("utf-8")).get("completed", []))
        except (OSError, TypeError, json.JSONDecodeError):
            return set()
    return set()


def save_cp(completed):
    atomic_write_json(CHECKPOINT_FILE, {"completed": sorted(completed), "count": len(completed)})


def apply_batch_results(
    completed: set[str], results: Iterable[tuple[str, bool, str]]
) -> list[tuple[str, str]]:
    """只记录成功文件；失败文件保留给下一次重试。"""
    failed = []
    for fpath, ok, detail in results:
        if ok:
            completed.add(fpath)
        else:
            failed.append((fpath, detail))
    return failed


def main() -> int:
    from config.settings import get_config

    doc_dir = str(ROOT / "doc")
    if not os.path.isdir(doc_dir):
        print("doc 目录不存在")
        return 1

    print("扫描文件路径...")
    all_paths = scan_paths(doc_dir)
    total = len(all_paths)
    print(f"共 {total} 个文件\n")

    completed = load_cp()
    pending_all = [p for p in all_paths if p not in completed]
    print(f"已完成 {len(completed)}, 待处理 {len(pending_all)}\n")

    if not pending_all:
        print("全部已完成。")
        return 0

    cfg = get_config()
    db_path = cfg.database.get("path", "data/knowledge/writing_expert.db")
    conn = init_db(db_path)
    db_path_real = conn.execute("PRAGMA database_list").fetchone()[2]
    pipeline = PreprocessingPipeline()

    t0 = time.time()
    done = len(completed)
    failures: list[tuple[str, str]] = []

    def do_one(fpath):
        lconn = None
        try:
            chunks = pipeline.process_file(fpath)
            lconn = sqlite3.connect(db_path_real)
            for c in chunks:
                lconn.execute(
                    "INSERT OR IGNORE INTO chunks (chunk_id,source_file,text,char_count,paragraph_index,created_at) VALUES (?,?,?,?,?,datetime('now'))",
                    (c.chunk_id, c.source_file, c.text, c.char_count, c.paragraph_index),
                )
            lconn.commit()
            return fpath, True, ""
        except Exception as exc:
            return fpath, False, f"{type(exc).__name__}: {exc}"
        finally:
            if lconn is not None:
                lconn.close()

    try:
        idx = 0
        while idx < len(pending_all):
            batch = pending_all[idx : idx + WORKERS]
            idx += WORKERS

            print(
                f"[{done}/{total}  {done * 100 // total}%] 处理 {len(batch)} 个...",
                end="",
                flush=True,
            )

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                futs = {pool.submit(do_one, p): p for p in batch}
                results = []
                for fut in as_completed(futs):
                    try:
                        results.append(fut.result())
                    except Exception as exc:
                        results.append((futs[fut], False, f"{type(exc).__name__}: {exc}"))
                failed = apply_batch_results(completed, results)
                failures.extend(failed)
                done = len(completed)

            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            print(
                f"\r[{done}/{total}  {done * 100 // total}%]  {rate:.0f} 文件/s  剩余 ~{eta / 60:.0f}min"
            )
            if failed:
                print(f"本批 {len(failed)} 个文件失败，未写入 checkpoint，将在下次运行时重试")
            save_cp(completed)
            gc.collect()

    except KeyboardInterrupt:
        print(f"\n中断。已完成 {done}/{total}。下次自动续。")
        save_cp(completed)
        return 130
    finally:
        conn.close()

    elapsed = time.time() - t0
    print(f"\n完成: {done}/{total} | 耗时 {elapsed / 60:.1f} min")
    if failures:
        print(f"失败 {len(failures)} 个文件；它们没有被标记完成。")
        for fpath, detail in failures[:5]:
            print(f"  - {fpath}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    main()
