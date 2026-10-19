"""工作台保存与确认契约：仅使用临时项目和假分析器。"""
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_novel_api import client, temp_project  # noqa: F401
from src.novel.character_engine import CharacterEngine, CharacterProfile
from src.novel.project_manager import OutlineItem


def test_create_rejects_existing_chapter_and_outline(client, temp_project):
    name, svc = temp_project
    original = svc.load(name).project.get_chapter(1)
    bundle = svc.load(name)
    bundle.project.outline.append(OutlineItem(chapter=2, title="规划"))
    bundle.project.save()
    for chapter in (1, 2):
        res = client.post(f"/api/projects/{name}/chapters/create", json={"number": chapter, "title": "重复"})
        assert res.status_code == 409
    assert svc.load(name).project.get_chapter(1) == original
    assert client.post(f"/api/projects/{name}/chapters/create", json={"number": 0, "title": "非法"}).status_code == 422


def test_confirmation_saves_preview_once_without_llm(client, temp_project):
    name, svc = temp_project
    def analyze(engine, *args, **kwargs):
        char = CharacterProfile(name="预览角色", personality={"勇气": 7})
        engine.add_character(char)
        return SimpleNamespace(status="ok", detail="", updated=[char])
    url = f"/api/projects/{name}/chapters/1"
    with patch.object(CharacterEngine, "analyze_chapter_ex", analyze):
        preview = client.post(url + "/analyze_characters").json()
    assert svc.load(name).engine.get_character("预览角色") is None
    with patch.object(CharacterEngine, "analyze_chapter_ex", side_effect=AssertionError("确认不得调用模型")):
        payload = {"proposal_id": preview["proposal_id"]}
        assert client.post(url + "/confirm_character_evolution", json=payload).status_code == 200
        assert client.post(url + "/confirm_character_evolution", json=payload).status_code == 409
    assert svc.load(name).engine.get_character("预览角色").personality["勇气"] == 7


def test_stale_and_failed_proposals_cannot_confirm(client, temp_project):
    name, svc = temp_project
    url = f"/api/projects/{name}/chapters/1"
    with patch.object(CharacterEngine, "analyze_chapter_ex", return_value=SimpleNamespace(status="ok", detail="", updated=[])):
        preview = client.post(url + "/analyze_characters").json()
    bundle = svc.load(name)
    bundle.project.add_chapter(1, "改动", "正文已改变")
    bundle.project.save()
    assert client.post(url + "/confirm_character_evolution", json={"proposal_id": preview["proposal_id"]}).status_code == 409
    with patch.object(CharacterEngine, "analyze_chapter_ex", return_value=SimpleNamespace(status="failed", detail="模拟失败", updated=[])):
        assert client.post(url + "/analyze_characters").status_code == 502
    assert client.post(url + "/confirm_character_evolution", json={"proposal_id": "missing"}).status_code == 409
