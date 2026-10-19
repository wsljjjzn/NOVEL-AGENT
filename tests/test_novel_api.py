"""
tests.test_novel_api — Novel Studio Web / IDE API 路由测试。
离线测试：使用 Fake LLM / 模拟数据，不花钱、不联网。
"""
import pytest
from starlette.testclient import TestClient

from src.api.server import app
from src.novel.service import NovelService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_project(tmp_path, monkeypatch):
    """构建临时小说项目目录，避免污染真实 data/projects/。"""
    proj_dir = tmp_path / "projects"
    proj_dir.mkdir(parents=True, exist_ok=True)

    # 替换服务层的 base_dir
    svc = NovelService(base_dir=str(proj_dir))
    monkeypatch.setattr("src.api.novel_router.svc", svc)

    # 创建测试小说
    svc.create("测试修仙传", genre="修仙", description="穿越修仙界")
    bundle = svc.load("测试修仙传")
    bundle.project.add_chapter(1, "初入宗门", "林凡站在山门前，深吸一口气。")
    bundle.project.save()

    # 初始化一个角色
    char_file = bundle.project.base_dir / "characters.json"
    bundle.engine.save(str(char_file))

    return "测试修仙传", svc


def test_list_projects(client, temp_project):
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(p["name"] == "测试修仙传" for p in data)


def test_create_and_get_project_detail(client, temp_project):
    name, _ = temp_project
    resp = client.get(f"/api/projects/{name}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["name"] == name
    assert detail["title"] == name
    assert detail["genre"] == "修仙"
    assert len(detail["chapters"]) >= 1
    assert detail["chapters"][0]["chapter"] == 1


def test_chapter_read_and_save(client, temp_project):
    name, _ = temp_project
    # 读取第一章
    resp = client.get(f"/api/projects/{name}/chapters/1")
    assert resp.status_code == 200
    data = resp.json()
    assert "林凡站在山门前" in data["content"]

    # 保存第一章修改
    save_resp = client.post(
        f"/api/projects/{name}/chapters/1/save",
        json={"title": "宗门考核", "content": "林凡拔出木剑，迎向测灵石。"},
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["ok"] is True

    # 再次读取验证
    resp2 = client.get(f"/api/projects/{name}/chapters/1")
    assert resp2.json()["content"] == "林凡拔出木剑，迎向测灵石。"
    assert resp2.json()["title"] == "宗门考核"


def test_character_traits_manual_update(client, temp_project):
    name, svc = temp_project
    bundle = svc.load(name)

    # 先给角色引擎加个角色
    from src.novel.character_engine import CharacterProfile
    char = CharacterProfile(name="林凡", role="主角", personality={"果断": 5, "警惕": 4})
    bundle.engine.add_character(char)
    bundle.engine.save(str(bundle.project.base_dir / "characters.json"))

    # 读取角色
    resp = client.get(f"/api/projects/{name}/characters")
    assert resp.status_code == 200
    chars = resp.json()["characters"]
    assert any(c["name"] == "林凡" for c in chars)

    # 手动调参：把【警惕】改为 8
    update_resp = client.post(
        f"/api/projects/{name}/characters/update_trait",
        json={"character_name": "林凡", "trait_name": "警惕", "value": 8},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["value"] == 8

    # 自定义添加新特质：【心魔】= 6
    add_resp = client.post(
        f"/api/projects/{name}/characters/add_trait",
        json={"character_name": "林凡", "trait_name": "心魔", "initial_value": 6},
    )
    assert add_resp.status_code == 200
    assert add_resp.json()["value"] == 6

    # 再次读取验证持久化
    resp2 = client.get(f"/api/projects/{name}/characters")
    lin = next(c for c in resp2.json()["characters"] if c["name"] == "林凡")
    assert lin["personality"]["警惕"] == 8
    assert lin["personality"]["心魔"] == 6


def test_ai_inline_rewrite(client, monkeypatch):
    """测试 Cmd+K 选区重写（使用 Fake LLM）。"""
    class FakeLLM:
        def chat(self, messages, **kwargs):
            return "林凡目光如鹰隼般扫视四周，握剑的指节因用力而发白。"

    monkeypatch.setattr("src.api.novel_router.LLMClient", lambda: FakeLLM())

    resp = client.post(
        "/api/ai/inline_rewrite",
        json={
            "project_name": "不存在也可以测试纯改写",
            "chapter": 1,
            "selected_text": "林凡警惕地看着四周。",
            "instruction": "加强冷硬派细节与心理描写",
            "context_before": "周围一片漆黑。",
            "context_after": "风声越来越大。",
            "model_tier": "flash",
        },
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["ok"] is True
    assert "指节因用力而发白" in res["rewritten_text"]


def test_ai_ghost_suggest(client, monkeypatch):
    """测试行内灰字 Ghost Text 智能续写（使用 Fake LLM）。"""
    class FakeLLM:
        def chat(self, messages, **kwargs):
            return "山道两侧的古柏在狂风中疯狂摇曳。"

    monkeypatch.setattr("src.api.novel_router.LLMClient", lambda: FakeLLM())

    resp = client.post(
        "/api/ai/ghost_suggest",
        json={
            "project_name": "测试",
            "chapter": 1,
            "recent_text": "林凡拾阶而上，",
            "model_tier": "flash",
        },
    )
    assert resp.status_code == 200
    assert "古柏" in resp.json()["suggestion"]


def test_chapter_create_and_outline_and_foreshadowing(client, temp_project):
    """测试章节创建、大纲批量更新与伏笔生命周期管理。"""
    name, _ = temp_project

    # 1. 创建章节
    create_ch_resp = client.post(
        f"/api/projects/{name}/chapters/create",
        json={"title": "青铜大门开启", "content": "大门轰然开启……"},
    )
    assert create_ch_resp.status_code == 200
    assert create_ch_resp.json()["chapter"] == 2

    # 2. 伏笔添加与标记解决
    add_f_resp = client.post(
        f"/api/projects/{name}/foreshadowing/add",
        json={"text": "主角腰间的半截玉佩隐藏着身世之谜"},
    )
    assert add_f_resp.status_code == 200
    assert "身世之谜" in add_f_resp.json()["foreshadowing"][0]

    # 验证获取项目详情中包含伏笔
    detail = client.get(f"/api/projects/{name}").json()
    assert len(detail["foreshadowing"]) == 1

    # 标记解决
    res_f_resp = client.post(
        f"/api/projects/{name}/foreshadowing/resolve",
        json={"text": "主角腰间的半截玉佩隐藏着身世之谜"},
    )
    assert res_f_resp.status_code == 200
    assert len(res_f_resp.json()["foreshadowing"]) == 0

    # 3. 批量更新大纲
    outline_resp = client.post(
        f"/api/projects/{name}/outline/update",
        json={
            "items": [
                {
                    "chapter": 1,
                    "title": "青铜大门开启",
                    "expected_content": "探寻遗迹秘辛",
                    "key_foreshadowing": ["神秘符文"],
                },
                {
                    "chapter": 2,
                    "title": "深海古龙苏醒",
                    "expected_content": "恶战",
                    "key_foreshadowing": [],
                },
            ]
        },
    )
    assert outline_resp.status_code == 200
    assert len(outline_resp.json()["outline"]) == 2


def test_system_doctor(client):
    """测试系统与引擎自检报告输出。"""
    resp = client.get("/api/system/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert "steps" in data
    assert len(data["steps"]) >= 5
    assert any(s["name"] == "domain_engines" and s["ok"] for s in data["steps"])


def test_project_update(client, temp_project):
    """测试更新小说宏观企划与世界观设定。"""
    name, _ = temp_project
    resp = client.post(
        f"/api/projects/{name}/update",
        json={"title": "修仙界新纪元", "genre": "仙侠修真", "description": "天道崩塌后的重塑之路"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "修仙界新纪元"
    assert data["genre"] == "仙侠修真"
    assert data["description"] == "天道崩塌后的重塑之路"

    # 验证获取项目详情已更新
    detail = client.get(f"/api/projects/{name}").json()
    assert detail["title"] == "修仙界新纪元"
    assert detail["description"] == "天道崩塌后的重塑之路"


def test_ai_brainstorm_plots(client, temp_project, monkeypatch):
    """测试 AI 剧情脑暴发散提议。"""
    name, _ = temp_project
    class FakeLLM:
        def chat(self, messages, **kwargs):
            return '[{"id": 1, "title": "叛徒突现", "premise": "同门师兄暗中下毒", "conflict": "生死试炼", "hook": "解药线索"}]'

    monkeypatch.setattr("src.api.novel_router.LLMClient", lambda: FakeLLM())
    resp = client.post(
        f"/api/projects/{name}/ai/brainstorm_plots",
        json={"instruction": "推演生死危机", "model_tier": "flash"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["ideas"]) >= 1
    assert data["ideas"][0]["title"] == "叛徒突现"


def test_system_settings_crud(client, monkeypatch):
    """测试系统配置获取与保存。"""
    monkeypatch.setattr("src.api.novel_router._update_env_file", lambda updates: None)

    # 1. 获取当前状态
    resp = client.get("/api/system/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "api_key_configured" in data
    assert "base_url" in data

    # 2. 保存新 Key
    save_resp = client.post(
        "/api/system/settings",
        json={"api_key": "sk-test1234567890abcdef", "base_url": "https://api.deepseek.com/v1"},
    )
    assert save_resp.status_code == 200
    save_data = save_resp.json()
    assert save_data["ok"] is True
    assert save_data["api_key_configured"] is True
    assert "sk-t****cdef" in save_data["masked_api_key"]


def test_test_api_key_mock(client, monkeypatch):
    """测试 API Key 连通性探测（Mock 保证离线安全）。"""
    class FakeModel:
        def __init__(self, mid):
            self.id = mid

    class FakeModelsList:
        def __init__(self):
            self.data = [FakeModel("deepseek-chat"), FakeModel("deepseek-reasoner")]

    class FakeModelsResp:
        def list(self):
            return FakeModelsList()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.models = FakeModelsResp()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    resp = client.post(
        "/api/system/test_api_key",
        json={"api_key": "sk-fake-key", "base_url": "https://api.deepseek.com/v1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "deepseek-chat" in data["models"]
    assert data["latency_ms"] >= 0


def test_review_chapter_api(client, temp_project, monkeypatch):
    """测试章节审稿接口能够正确提取 AggregatedReview 的条目且不报 AttributeError。"""
    name, _ = temp_project
    from src.models.review import AggregatedReview, ReviewIssue, ReviewReport
    from src.novel.service import Result

    mock_issue = ReviewIssue(
        agent="校对",
        dimension="proofread",
        level=1,
        description="发现错别字",
        before_text="的地得",
        after_text="的",
    )
    mock_aggregated = AggregatedReview(
        article_id=f"{name}#1",
        level1_changes=[mock_issue],
        reports=[ReviewReport(agent="校对", dimension="proofread", score=9.0, issues=[mock_issue])],
    )

    monkeypatch.setattr(
        "src.novel.service.NovelService.review_chapter",
        lambda *args, **kwargs: Result(ok=True, data=mock_aggregated, title="审稿完成"),
    )

    resp = client.post(
        f"/api/projects/{name}/chapters/1/review",
        json={"model_tier": "flash"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["issues"]) == 1
    assert data["issues"][0]["description"] == "发现错别字"
    assert data["issues"][0]["level"] == 1


def test_apply_review_fixes_dict_success(client, temp_project):
    """测试通过字典格式向接口提交修改项并成功修改正文落盘。"""
    name, svc = temp_project
    # 初始正文为: "林凡站在山门前，深吸一口气。"
    issue_dict = {
        "agent": "校对",
        "dimension": "proofread",
        "level": 1,
        "description": "用词优化",
        "before_text": "林凡站在山门前",
        "after_text": "林凡傲然屹立于山门前",
    }
    resp = client.post(
        f"/api/projects/{name}/chapters/1/apply_fixes",
        json={"issues": [issue_dict]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "已应用 1 处修改" in data["title"]

    # 验证正文已更新
    chap_resp = client.get(f"/api/projects/{name}/chapters/1")
    assert chap_resp.status_code == 200
    assert "林凡傲然屹立于山门前，深吸一口气。" in chap_resp.json()["content"]


def test_apply_review_fixes_missed_anchor(client, temp_project):
    """测试当锚点不匹配时返回 400 且保留原正文。"""
    name, svc = temp_project
    issue_dict = {
        "agent": "校对",
        "dimension": "proofread",
        "level": 1,
        "description": "不存在的文字",
        "before_text": "完全不存在的原文段落",
        "after_text": "新的文本",
    }
    resp = client.post(
        f"/api/projects/{name}/chapters/1/apply_fixes",
        json={"issues": [issue_dict]},
    )
    assert resp.status_code == 400
    assert "没有实际改动" in resp.json()["detail"]


def test_update_chapter_outline(client, temp_project):
    """测试更新单章大纲细纲与伏笔线索。"""
    name, _ = temp_project
    resp = client.post(
        f"/api/projects/{name}/chapters/1/outline",
        json={
            "expected_content": "林凡在禁地获得神秘剑胎，引来同门嫉妒",
            "key_foreshadowing": ["剑胎深处的龙纹印记"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["outline"]["expected_content"] == "林凡在禁地获得神秘剑胎，引来同门嫉妒"
    assert "剑胎深处的龙纹印记" in data["outline"]["key_foreshadowing"]


def test_generate_chapter_content(client, temp_project, monkeypatch):
    """测试根据大纲和角色生成本章正文（测试用例离线注入 Fake LLM）。"""
    name, _ = temp_project

    class FakeWriterLLM:
        def chat(self, messages, **kwargs):
            return "林凡深吸一口气，周身灵气澎湃激荡。剑鸣声起，四方惊骇。"

    # 注入 fake LLMClient 到 chapter_writer, plot_engine 与 character_engine
    monkeypatch.setattr("src.novel.chapter_writer.LLMClient", lambda: FakeWriterLLM())
    monkeypatch.setattr("src.novel.plot_engine.LLMClient", lambda: FakeWriterLLM())
    monkeypatch.setattr("src.novel.character_engine.LLMClient", lambda: FakeWriterLLM())

    resp = client.post(
        f"/api/projects/{name}/chapters/1/generate",
        json={
            "instructions": "强化打斗张力与动作细节",
            "target_words": 2000,
            "model_tier": "flash",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["chapter"] == 1
    assert "林凡深吸一口气" in data["content"]
    assert data["word_count"] > 0

    # 验证获取章节正文确实已落盘
    chap_resp = client.get(f"/api/projects/{name}/chapters/1")
    assert chap_resp.status_code == 200
    assert "林凡深吸一口气" in chap_resp.json()["content"]


def test_delete_chapter(client, temp_project):
    """测试删除章节接口。"""
    name, _ = temp_project
    # 先创建第 2 章
    create_resp = client.post(
        f"/api/projects/{name}/chapters/create",
        json={"number": 2, "title": "第二章 险象环生", "content": "第二章正文"},
    )
    assert create_resp.status_code == 200

    # 删除第 2 章
    del_resp = client.delete(f"/api/projects/{name}/chapters/2")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    # 验证获取第 2 章已被移除
    proj_resp = client.get(f"/api/projects/{name}")
    assert not any(c["chapter"] == 2 for c in proj_resp.json()["chapters"])


def test_delete_project(client, temp_project):
    """测试删除整部小说项目接口。"""
    name, _ = temp_project
    resp = client.delete(f"/api/projects/{name}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 验证项目已不在列表中
    list_resp = client.get("/api/projects")
    assert not any(p["name"] == name for p in list_resp.json())


def test_character_chapter_slice(client, temp_project):
    """测试获取角色在指定章节的时间切片接口。"""
    name, svc = temp_project
    bundle = svc.load(name)
    from src.novel.character_engine import CharacterProfile, ChapterEvent, PersonalityShift
    profile = CharacterProfile(
        name="林凡",
        role="主角",
        personality={"警惕心": 8, "同理心": 5},
    )
    event1 = ChapterEvent(
        chapter=1,
        mood="坚定警惕",
        key_actions=["步入青云宗山门", "收敛气息"],
        personality_shifts=[
            PersonalityShift(trait="警惕心", old_value=6, new_value=8, reason="见识同门倾轧")
        ],
        summary="林凡初步在宗门立足",
    )
    profile.upsert_event(event1)
    bundle.engine.add_character(profile)
    bundle.engine.save(str(bundle.project.base_dir / "characters.json"))

    resp = client.get(f"/api/projects/{name}/characters/林凡/slice/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["name"] == "林凡"
    assert data["chapter"] == 1
    assert data["is_exact_event"] is True
    assert data["mood"] == "坚定警惕"
    assert "步入青云宗山门" in data["key_actions"]
    assert data["personality"]["警惕心"] == 8
    assert 1 in data["all_recorded_chapters"]

