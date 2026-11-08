from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def test_knowledge_stats():
    res = client.get("/api/knowledge/stats")
    assert res.status_code == 200
    data = res.json()
    assert "file_count" in data
    assert "chunk_count" in data
    assert "knowledge_unit_count" in data
    assert "total_chars" in data


def test_knowledge_files():
    res = client.get("/api/knowledge/files")
    assert res.status_code == 200
    data = res.json()
    assert "files" in data
    assert isinstance(data["files"], list)


def test_knowledge_search():
    res = client.post("/api/knowledge/search", json={"query": "太空 飞船 跃迁", "top_k": 3})
    assert res.status_code == 200
    data = res.json()
    assert "sources" in data
    assert isinstance(data["sources"], list)


def test_knowledge_upload_and_delete():
    # 1. Upload and learn
    content = "# 测试书籍规约\n\n测试章节一：曲率折跃引擎的基础散热模型在恒星引力井范围内的热逸散。"
    res = client.post(
        "/api/knowledge/upload_and_learn",
        json={
            "filename": "hub_test_book.md",
            "content": content,
            "mode": "split_only",
            "chunk_size": 200,
            "overlap": 20,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["chunks"] >= 1

    # 2. Search for the newly learned term
    res_search = client.post(
        "/api/knowledge/search", json={"query": "曲率折跃引擎 散热模型", "top_k": 3}
    )
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert any("hub_test_book.md" in s.get("source", "") for s in search_data.get("sources", []))

    # 3. Delete
    res_del = client.delete("/api/knowledge/files/hub_test_book.md")
    assert res_del.status_code == 200
    del_data = res_del.json()
    assert del_data["ok"] is True
    assert "summary" in del_data
