"""用量追踪的持久化与并发测试。"""

import sqlite3
import threading

from src.utils.cost_tracker import CostTracker, UsageRecord


def test_usage_persistence_works_across_worker_threads(tmp_path):
    db_path = tmp_path / "usage.db"
    tracker = CostTracker(usage_db_path=str(db_path))
    barrier = threading.Barrier(6)

    def record_usage(index: int) -> None:
        barrier.wait()
        tracker.add_record(UsageRecord("flash", prompt_tokens=index + 1))

    workers = [threading.Thread(target=record_usage, args=(index,)) for index in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    with sqlite3.connect(db_path) as conn:
        persisted = conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0]
    assert persisted == 6
