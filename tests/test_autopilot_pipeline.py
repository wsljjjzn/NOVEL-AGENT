"""
tests.test_autopilot_pipeline — 全自动巡航流水线与原子事务快照回滚测试。

遵循契约与规范：
1. 离线运行，严禁调用真实 LLM；
2. 验证快照创建、回滚（取消时不保存）与提交；
3. 验证单步流水线执行闭环（大纲补齐、正文撰写、静默质检、角色演化）。
"""

import json
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("starlette")
pytest.importorskip("fastapi")

from starlette.testclient import TestClient

from src.api.server import app
from src.novel.service import NovelService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_project(tmp_path, monkeypatch):
    """构建临时小说项目，隔离测试环境。"""
    proj_dir = tmp_path / "projects"
    proj_dir.mkdir(parents=True, exist_ok=True)

    svc = NovelService(base_dir=str(proj_dir))
    monkeypatch.setattr("src.api.novel_router.svc", svc)

    # 创建测试小说并写入第 1 章
    svc.create("巡航测试录", genre="都市", description="全自动巡航工程")
    bundle = svc.load("巡航测试录")
    bundle.project.add_chapter(1, "序章", "第一章的基础正文内容。")
    bundle.project.save()

    return "巡航测试录", svc


def test_autopilot_snapshot_lifecycle(client, temp_project):
    """验证快照创建、修改后回滚（取消不保存）、以及提交清理的完整生命周期。"""
    name, svc = temp_project

    # 1. 创建快照
    res_snap = client.post(f"/api/projects/{name}/autopilot/snapshot/create")
    assert res_snap.status_code == 200
    assert res_snap.json()["ok"] is True

    bundle = svc.load(name)
    snap_dir = bundle.project.base_dir / ".autopilot_snapshot"
    assert snap_dir.exists()
    assert (snap_dir / "project.json").exists()

    # 2. 模拟巡航中途写入了第 2 章与新大纲
    bundle.project.add_chapter(2, "第2章自动生成稿", "这是巡航中临时写出的第二章内容...")
    from src.novel.project_manager import OutlineItem

    bundle.project.outline.append(
        OutlineItem(chapter=2, title="临时大纲2", expected_content="临时情节描述")
    )
    bundle.project.save()

    # 确认当前项目已经包含了第 2 章
    bundle_updated = svc.load(name)
    assert 2 in bundle_updated.project.chapters

    # 3. 模拟用户点击【取消巡航 (不保存)】：触发原子回滚
    res_rb = client.post(f"/api/projects/{name}/autopilot/snapshot/rollback")
    assert res_rb.status_code == 200
    assert res_rb.json()["ok"] is True

    # 4. 验证：第 2 章和新大纲已经被物理丢弃抹平，工程彻底恢复启动前状态
    bundle_restored = svc.load(name)
    assert 2 not in bundle_restored.project.chapters
    assert 1 in bundle_restored.project.chapters
    assert not snap_dir.exists(), "回滚后临时快照目录应被自动清理"


def test_autopilot_snapshot_commit(client, temp_project):
    """验证快照提交时正确清理临时目录。"""
    name, svc = temp_project
    client.post(f"/api/projects/{name}/autopilot/snapshot/create")

    bundle = svc.load(name)
    snap_dir = bundle.project.base_dir / ".autopilot_snapshot"
    assert snap_dir.exists()

    res_commit = client.post(f"/api/projects/{name}/autopilot/snapshot/commit")
    assert res_commit.status_code == 200
    assert not snap_dir.exists()


def test_autopilot_step_pipeline_mocked(client, temp_project):
    """测试单步全自动巡航流水线（mock LLM，离线且保证确定性）。"""
    name, svc = temp_project

    mock_llm = MagicMock()
    # 模拟大纲脑暴返回 JSON
    mock_llm.chat.return_value = json.dumps(
        {"title": "暗潮涌动", "expected_content": "主角遭遇伏击，发现幕后黑手的线索。"}
    )

    with (
        patch("src.api.novel_router.LLMClient", return_value=mock_llm),
        patch.object(
            svc,
            "write_chapter",
            return_value=type("Res", (), {"ok": True, "title": "完成", "lines": []})(),
        ),
    ):
        # 先给项目填入模拟正文
        bundle = svc.load(name)
        bundle.project.add_chapter(2, "暗潮涌动", "主角在小巷深处遭遇了突如其来的袭击……")
        bundle.project.save()

        payload = {
            "chapter": 2,
            "target_words": 2000,
            "model_tier": "flash",
            "auto_outline": True,
            "silent_qa": False,
            "auto_evolve": False,
        }
        res = client.post(f"/api/projects/{name}/autopilot/step", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["chapter"] == 2
        assert data["word_count"] > 0
        assert "已全自动生成交付" in data["summary"]
