"""
scripts/batch_preprocess.py — 流式分批并行预处理，带总进度。
先快速扫路径（零内存压力），再180个一批并行处理。
"""

import os, gc, json, time, sys, threading, sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import logging as _logging
_logging.getLogger().setLevel(_logging.ERROR)
_logging.getLogger("src").setLevel(_logging.ERROR)

from src.preprocessing import PreprocessingPipeline
from src.knowledge_base import init_db

WORKERS = 180
CHECKPOINT_FILE = ROOT / "data" / "preprocess_checkpoint.json"

def scan_paths(directory: str) -> list[str]:
    """快速收集所有 .txt 路径（只读文件名，不读内容）。"""
    paths = []
    for root, dirs, filenames in os.walk(directory):
        for f in filenames:
            if f.endswith('.txt'):
                paths.append(os.path.join(root, f))
    return paths

def load_cp():
    if CHECKPOINT_FILE.exists():
        try: return set(json.loads(Path(CHECKPOINT_FILE).read_text("utf-8")).get("completed", []))
        except: pass
    return set()

def save_cp(completed):
    Path(CHECKPOINT_FILE).write_text(
        json.dumps({"completed": list(completed), "count": len(completed)}, ensure_ascii=False),
        encoding="utf-8")

def main():
    from config.settings import get_config

    doc_dir = str(ROOT / "doc")
    if not os.path.isdir(doc_dir):
        print("doc 目录不存在"); return

    print("扫描文件路径...")
    all_paths = scan_paths(doc_dir)
    total = len(all_paths)
    print(f"共 {total} 个文件\n")

    completed = load_cp()
    pending_all = [p for p in all_paths if p not in completed]
    print(f"已完成 {len(completed)}, 待处理 {len(pending_all)}\n")

    if not pending_all:
        print("全部已完成。"); return

    cfg = get_config()
    db_path = cfg.database.get("path", "data/knowledge/writing_expert.db")
    conn = init_db(db_path)
    db_path_real = conn.execute("PRAGMA database_list").fetchone()[2]
    pipeline = PreprocessingPipeline()

    t0 = time.time()
    done = len(completed)

    def do_one(fpath):
        try:
            chunks = pipeline.process_file(fpath)
            lconn = sqlite3.connect(db_path_real)
            for c in chunks:
                try: lconn.execute(
                    "INSERT OR IGNORE INTO chunks (chunk_id,source_file,text,char_count,paragraph_index,created_at) VALUES (?,?,?,?,?,datetime('now'))",
                    (c.chunk_id, c.source_file, c.text, c.char_count, c.paragraph_index))
                except: pass
            lconn.commit(); lconn.close()
            return (fpath, True)
        except Exception:
            return (fpath, False)

    try:
        idx = 0
        while idx < len(pending_all):
            batch = pending_all[idx:idx + WORKERS]
            idx += WORKERS

            print(f"[{done}/{total}  {done*100//total}%] 处理 {len(batch)} 个...", end="", flush=True)

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                futs = {pool.submit(do_one, p): p for p in batch}
                for fut in as_completed(futs):
                    fpath, ok = fut.result()
                    completed.add(fpath)
                    done += 1

            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            print(f"\r[{done}/{total}  {done*100//total}%]  {rate:.0f} 文件/s  剩余 ~{eta/60:.0f}min")
            save_cp(completed)
            gc.collect()

    except KeyboardInterrupt:
        print(f"\n中断。已完成 {done}/{total}。下次自动续。")
        save_cp(completed)

    elapsed = time.time() - t0
    print(f"\n完成: {done}/{total} | 耗时 {elapsed/60:.1f} min")
    conn.close()

if __name__ == "__main__":
    main()
