"""
scripts/batch_analyze_flash.py — Flash API 批量四层分析（稳定版）。

WORKERS=5, MAX_RETRIES=3, 断点续传, 失败文件另存。
"""

import sys, json, time, os, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.logger import setup_logger
from src.analysis.deep import DeepAnalyzer
from src.analysis.ingestion import IngestionPipeline
from src.utils.cost_tracker import BudgetExceeded
from src.utils.llm_client import LLMUnavailableError

setup_logger(level="WARNING")

WORKERS = 5
MAX_RETRIES = 3
RETRY_DELAY = 2.0
CHECKPOINT_EVERY = 5

SELECTED_FILE = ROOT / "data" / "samples" / "selected_5000.json"
PROGRESS_FILE = ROOT / "data" / "samples" / "analysis_progress.json"
FAILED_FILE = ROOT / "data" / "samples" / "analysis_failed.json"
_lock = threading.Lock()


def load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            pass
    return {}


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def process_one(filepath, pipeline, deep) -> tuple:
    for attempt in range(MAX_RETRIES):
        try:
            chunks = pipeline.preprocessor.process_file(filepath)
            if not chunks:
                return (filepath, False, "无段落块", [])
            full_text = "\n".join(c.text for c in chunks[:20])
            if len(full_text) < 200:
                return (filepath, False, "文本太短", [])
            source_name = Path(filepath).stem
            result = deep.analyze_all(full_text, source_name, model_tier="flash")
            units = deep.synthesize_knowledge_units(result, filepath)
            # 序列化后由主线程统一写入（避免多线程SQLite冲突）
            units_data = [{
                "knowledge_unit_id": u.knowledge_unit_id,
                "type": u.type,
                "category": u.category,
                "source": u.source,
                "description": u.description,
                "tags": u.tags,
            } for u in units]
            return (filepath, True, f"{len(units)} 单元", units_data)
        except (BudgetExceeded, LLMUnavailableError):
            raise  # 预算耗尽 / API 不可用：中止整轮而不是当失败文件续跑
        except Exception as e:
            err = str(e)[:100]
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                return (filepath, False, err, [])
    return (filepath, False, "未知错误", [])


def main():
    if not SELECTED_FILE.exists():
        print(f"文件不存在: {SELECTED_FILE}")
        return

    files = json.loads(SELECTED_FILE.read_text("utf-8"))
    total = len(files)

    progress = load_json(PROGRESS_FILE)
    failed = load_json(FAILED_FILE)
    completed_set = set(progress.get("completed", []))
    failed_set = set(failed.get("files", []))

    done = len(completed_set)
    total_failed = len(failed_set)
    pending_count = total - done - total_failed
    print(f"总数: {total} | 已完成: {done} | 失败: {total_failed} | 待处理: {pending_count}")

    if done >= total:
        print("全部完成。")
        return

    if not progress.get("started_at"):
        progress["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        progress["total"] = total

    pipeline = IngestionPipeline()
    deep = DeepAnalyzer()
    t0 = time.time()

    pending = [f for f in files if f not in completed_set and f not in failed_set]
    print(f"本轮处理: {len(pending)} 篇\n")

    pool = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        futs = {pool.submit(process_one, f, pipeline, deep): f for f in pending}
        session_done = 0

        for future in as_completed(futs):
            try:
                fpath, ok, info, units_data = future.result()
            except BudgetExceeded:
                raise  # 交给外层 except BudgetExceeded 优雅收尾
            except Exception:
                continue

            session_done += 1

            with _lock:
                if ok:
                    completed_set.add(fpath)
                    if units_data:
                        try:
                            from src.models import KnowledgeUnit
                            for ud in units_data:
                                pipeline._save_knowledge_units([KnowledgeUnit(**ud)])
                        except Exception:
                            pass
                else:
                    failed_set.add(fpath)

                done = len(completed_set)
                elapsed = time.time() - t0
                rate = session_done / elapsed if elapsed > 0 else 0
                remaining = total - done - len(failed_set)
                eta_min = remaining / rate / 60 if rate > 0 else 0

                marker = "OK" if ok else "FAIL"
                print(f"[{done}/{total} {done*100//total:2d}%] {marker} "
                      f"{Path(fpath).name[:45]:45s} {info[:30]} "
                      f"ETA {eta_min:.0f}min")

                if session_done % CHECKPOINT_EVERY == 0:
                    progress["completed"] = list(completed_set)
                    save_json(PROGRESS_FILE, progress)
                    if failed_set:
                        failed["files"] = list(failed_set)
                        save_json(FAILED_FILE, failed)

    except BudgetExceeded as e:
        print(f"\n[预算用尽] {e}（进度已保存，调大 config.yaml 预算后可续跑）")
    except KeyboardInterrupt:
        print("\n\n收到中断信号，保存进度后退出...")
        pool.shutdown(wait=False, cancel_futures=True)
    finally:
        progress["completed"] = list(completed_set)
        progress["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_json(PROGRESS_FILE, progress)
        if failed_set:
            failed["files"] = list(failed_set)
            save_json(FAILED_FILE, failed)

    total_elapsed = time.time() - t0
    print(f"\n{'='*50}")
    print(f"本次完成: {session_done} 篇")
    print(f"累计完成: {len(completed_set)}/{total}")
    print(f"失败: {len(failed_set)} 篇 -> {FAILED_FILE}")
    print(f"耗时: {total_elapsed/60:.1f} 分钟")
    print(f"预估总费用: ~${len(completed_set) * 4 * 0.0007:.2f}")


if __name__ == "__main__":
    main()