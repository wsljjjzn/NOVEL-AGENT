"""维护脚本的失败保护测试。"""

import json

from scripts._reset_db import reset
from scripts.batch_preprocess import apply_batch_results


def test_failed_preprocess_file_is_not_recorded_as_completed():
    completed = {"already-done.txt"}

    failed = apply_batch_results(
        completed,
        [("ok.txt", True, ""), ("broken.txt", False, "UnicodeDecodeError: bad input")],
    )

    assert completed == {"already-done.txt", "ok.txt"}
    assert failed == [("broken.txt", "UnicodeDecodeError: bad input")]


def test_reset_requires_confirmation_and_preserves_data(tmp_path):
    db_path = tmp_path / "writing_expert.db"
    checkpoint_path = tmp_path / "checkpoint.json"
    embeddings_path = tmp_path / "embeddings"
    db_path.write_bytes(b"database")
    checkpoint_path.write_text('{"completed": ["done.txt"]}', encoding="utf-8")
    embeddings_path.mkdir()

    assert reset(db_path, checkpoint_path, embeddings_path, confirmed=False) == 2
    assert db_path.exists()
    assert json.loads(checkpoint_path.read_text(encoding="utf-8"))["completed"] == ["done.txt"]
    assert embeddings_path.exists()


def test_reset_clears_derived_data_after_confirmation(tmp_path):
    db_path = tmp_path / "writing_expert.db"
    checkpoint_path = tmp_path / "checkpoint.json"
    embeddings_path = tmp_path / "embeddings"
    db_path.write_bytes(b"database")
    embeddings_path.mkdir()
    (embeddings_path / "index.bin").write_bytes(b"embedding")

    assert reset(db_path, checkpoint_path, embeddings_path, confirmed=True) == 0
    assert not db_path.exists()
    assert not embeddings_path.exists()
    assert json.loads(checkpoint_path.read_text(encoding="utf-8")) == {"completed": [], "count": 0}
