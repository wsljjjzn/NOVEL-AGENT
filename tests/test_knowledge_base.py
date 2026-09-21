"""测试：知识库（数据库 + 检索器）。"""

import pytest

from src.knowledge_base import Retriever, RetrievalResult, init_db


class TestDatabaseSchema:
    def test_init_db_creates_tables(self):
        conn = init_db(":memory:")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t[0] for t in tables]
        assert "chunks" in names
        assert "knowledge_units" in names
        assert "style_templates" in names
        assert "writing_requests" in names
        assert "outlines" in names
        assert "articles" in names
        assert "review_reports" in names
        assert "characters" in names  # 新增角色表
        conn.close()

    def test_init_db_wal_mode(self):
        """使用文件数据库验证 WAL 模式（内存数据库不支持 WAL）。"""
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = init_db(db_path)
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert journal_mode == "wal"
            conn.close()
        finally:
            os.unlink(db_path)


class TestRetrieverBase:
    def test_vector_search_default(self):
        r = Retriever({"skip_model": True})
        results = r.vector_search("test")
        assert results == []

    def test_bm25_search_default(self):
        r = Retriever({"skip_model": True})
        results = r.bm25_search("test")
        assert results == []

    def test_rerank_default(self):
        r = Retriever({"skip_model": True})
        results = r.rerank("test", [])
        assert results == []

    def test_hybrid_search_default(self):
        r = Retriever({"skip_model": True})
        results = r.hybrid_search("test", top_k=5)
        assert results == []


class TestRetrievalResult:
    def test_creation(self):
        result = RetrievalResult(
            content={"text": "测试"},
            score=0.95,
            source="vector",
            chunk_id="chunk_001",
        )
        assert result.score == 0.95
        assert result.source == "vector"
        assert result.chunk_id == "chunk_001"
        assert result.content["text"] == "测试"
