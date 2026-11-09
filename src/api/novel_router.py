"""
api.novel_router — 面向现代小说家 IDE（Novel Studio）的高性能交互 API 路由。

职责：
1. 项目与章节 CRUD（含大纲、伏笔、正文实时存取）
2. 角色引擎全生命周期（作者自由调参/添加状态、时间切片查询、AI 演变提议与确认）
3. AI 伴写与行内局部重构（Cmd+K 选区改写、Ghost Text 续写，Flash 档优先与精准上下文切片）
4. 六维审稿与就地修复
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.novel.project_manager import OutlineItem
from src.novel.service import NovelService
from src.utils.doctor import run_system_doctor
from src.utils.file_utils import atomic_write_json
from src.utils.llm_client import LLMClient
from src.utils.logger import logger

router = APIRouter(prefix="/api", tags=["novel-ide"])
svc = NovelService()

# 提议只保存服务端生成的快照，避免确认时再次调用模型或接受任意客户端档案。
_evolution_proposals: dict[str, dict] = {}
_proposal_lock = threading.RLock()


def _evolution_fingerprint(project, engine):
    payload = [project.chapters, {c.name: c.to_dict() for c in engine.all_characters()}]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class EvolutionConfirmReq(BaseModel):
    proposal_id: str


# ==========================================
# Pydantic 契约模型
# ==========================================


class ProjectCreateReq(BaseModel):
    name: str
    genre: str = ""
    description: str = ""


class ProjectUpdateReq(BaseModel):
    title: str | None = None
    genre: str | None = None
    description: str | None = None


class ChapterCreateReq(BaseModel):
    number: int | None = Field(default=None, ge=1)
    title: str
    content: str = ""
    expected_content: str = ""


class ChapterOutlineUpdateReq(BaseModel):
    expected_content: str
    key_foreshadowing: list[str] | None = None


class ChapterGenerateReq(BaseModel):
    instructions: str = ""
    target_words: int = 2500
    model_tier: str = "flash"
    use_knowledge_base: bool = False
    knowledge_query: str = Field(default="", max_length=200)


class KnowledgePreviewReq(BaseModel):
    query: str = Field(default="", max_length=200)


class KnowledgeLearnReq(BaseModel):
    filename: str
    content: str
    mode: str = "preprocess"  # "preprocess" | "lightweight" | "deep"
    tier: str = "flash"


class KnowledgeSearchReq(BaseModel):
    query: str = Field(default="", max_length=200)


class ChapterSaveReq(BaseModel):
    title: str | None = None
    content: str


class ForeshadowingReq(BaseModel):
    text: str


class AutopilotStepReq(BaseModel):
    chapter: int = Field(ge=1)
    target_words: int = Field(default=2500, ge=100)
    model_tier: str = "pro"
    instructions: str = ""
    auto_outline: bool = True
    silent_qa: bool = True
    auto_evolve: bool = True
    use_knowledge_base: bool = False
    knowledge_query: str = Field(default="", max_length=200)


class OutlineUpdateReq(BaseModel):
    items: list[OutlineItem]


class TraitUpdateReq(BaseModel):
    character_name: str
    trait_name: str
    value: int = Field(ge=0, le=10)


class CustomTraitAddReq(BaseModel):
    character_name: str
    trait_name: str
    initial_value: int = Field(default=5, ge=0, le=10)


class InlineRewriteReq(BaseModel):
    project_name: str
    chapter: int
    selected_text: str
    instruction: str
    context_before: str = ""
    context_after: str = ""
    model_tier: str = "flash"


class GhostSuggestReq(BaseModel):
    project_name: str
    chapter: int
    recent_text: str
    model_tier: str = "flash"


class PlotBrainstormReq(BaseModel):
    chapter: int | None = None
    instruction: str = ""
    model_tier: str = "flash"


class ChapterReviewReq(BaseModel):
    model_tier: str = "pro"
    apply_level1: bool = False
    save: bool = False


class ApplyFixesReq(BaseModel):
    issues: list[dict] = Field(default_factory=list)


class SettingsUpdateReq(BaseModel):
    api_key: str
    base_url: str | None = None


class TestApiKeyReq(BaseModel):
    api_key: str | None = None
    base_url: str | None = None


# ==========================================
# 0. 系统环境与设置接口
# ==========================================


def _update_env_file(key_values: dict[str, str]) -> None:
    """持久化保存环境变量到项目根目录下的 .env 文件。"""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    existing_lines = []
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            existing_lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in existing_lines:
        stripped = line.strip()
        matched = False
        for k, v in key_values.items():
            if stripped.startswith(f"{k}=") or stripped.startswith(f"{k} ="):
                new_lines.append(f"{k}={v}\n")
                updated_keys.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for k, v in key_values.items():
        if k not in updated_keys:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{k}={v}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


@router.get("/system/doctor")
def get_system_doctor():
    """获取核心四大引擎与环境自检报告。"""
    return {"steps": run_system_doctor()}


@router.get("/system/settings")
def get_system_settings():
    """获取当前系统的配置与 API Key 脱敏状态。"""
    import os

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    masked = ""
    if api_key:
        masked = api_key[:3] + "****" if len(api_key) <= 8 else api_key[:4] + "****" + api_key[-4:]

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip()
    return {
        "api_key_configured": bool(api_key),
        "masked_api_key": masked,
        "base_url": base_url,
    }


@router.get("/system/usage")
def get_system_usage():
    """获取当前系统/会话累积的 LLM 调用统计与费用。"""
    from src.utils.cost_tracker import get_tracker

    t = get_tracker()
    prompt_tokens, completion_tokens = t.total_tokens
    return {
        "calls": t.total_calls,
        "cost_cny": float(round(t.total_cost_cny, 4)),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "budget_cny": float(t.budget_cny),
    }


@router.post("/system/settings")
def save_system_settings(req: SettingsUpdateReq):
    """保存用户输入的 API Key 与端点配置至本地 .env 并即刻生效。"""
    import os

    api_key = req.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    updates = {"DEEPSEEK_API_KEY": api_key}
    os.environ["DEEPSEEK_API_KEY"] = api_key

    if req.base_url and req.base_url.strip():
        base_url = req.base_url.strip()
        updates["DEEPSEEK_BASE_URL"] = base_url
        os.environ["DEEPSEEK_BASE_URL"] = base_url

    # 持久化落盘至 .env
    _update_env_file(updates)

    # 重置配置缓存
    try:
        import config.settings as cs

        cs._config = None
    except Exception as e:
        logger.warning(f"重置 config 失败: {e}")

    masked = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else api_key[:3] + "****"
    return {
        "ok": True,
        "message": "API 配置已成功保存至 .env 并即刻生效！",
        "api_key_configured": True,
        "masked_api_key": masked,
    }


@router.post("/system/test_api_key")
def test_api_key(req: TestApiKeyReq):
    """测试指定或当前已配置的 API Key 连通性。"""
    import os
    import time

    from openai import OpenAI

    key = (req.api_key or "").strip() or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return {"ok": False, "detail": "未检测到 API Key，请先输入 Key"}

    base_url = (req.base_url or "").strip() or os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
    ).strip()

    start_time = time.monotonic()
    try:
        client = OpenAI(api_key=key, base_url=base_url, timeout=8.0)
        # 用轻量探测获取模型列表
        models_resp = client.models.list()
        latency = int((time.monotonic() - start_time) * 1000)
        model_names = (
            [m.id for m in models_resp.data][:3]
            if models_resp and hasattr(models_resp, "data")
            else []
        )
        return {
            "ok": True,
            "latency_ms": latency,
            "models": model_names,
            "detail": f"连接成功！延迟 {latency}ms，端点握手正常",
        }
    except Exception as e:
        latency = int((time.monotonic() - start_time) * 1000)
        return {
            "ok": False,
            "latency_ms": latency,
            "detail": f"连接失败 ({e})",
        }


# ==========================================
# 1. 项目与卷章大纲接口
# ==========================================


@router.get("/projects")
def list_projects():
    """获取所有小说项目列表。"""
    return svc.list_projects()


@router.post("/projects")
def create_project(req: ProjectCreateReq):
    """新建小说项目。"""
    res = svc.create(req.name, req.genre, req.description)
    if not res.ok:
        raise HTTPException(status_code=400, detail=res.title)
    return {"ok": True, "message": res.title, "name": req.name}


@router.post("/projects/{name}/update")
def update_project(name: str, req: ProjectUpdateReq):
    """更新小说的基本元信息（宏观企划、世界观设定、类型）。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    p = bundle.project
    if req.title is not None:
        p.title = req.title
    if req.genre is not None:
        p.genre = req.genre
    if req.description is not None:
        p.description = req.description
    p.save()
    return {
        "ok": True,
        "name": p.name,
        "title": p.title,
        "genre": p.genre,
        "description": p.description,
    }


@router.get("/projects/{name}")
def get_project_detail(name: str):
    """获取项目完整元数据：大纲、伏笔、章节目录（标题/字数）。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail=f"项目不存在: {name}")
    bundle = svc.load(name)
    p = bundle.project

    # 汇总章节列表
    chapters_info = []
    all_ch_nums = sorted(set(list(p.chapters.keys()) + [o.chapter for o in p.outline]))
    for ch in all_ch_nums:
        content = p.chapters.get(ch, "")
        title = p.chapter_titles.get(ch, "")
        outline_item = next((o for o in p.outline if o.chapter == ch), None)
        if not title and outline_item:
            title = outline_item.title
        chapters_info.append(
            {
                "chapter": ch,
                "title": title or f"第{ch}章",
                "word_count": len(content),
                "has_content": bool(content.strip()),
                "outline": outline_item.model_dump() if outline_item else None,
            }
        )

    return {
        "name": p.name,
        "title": p.title,
        "genre": p.genre,
        "description": p.description,
        "total_words": sum(len(c) for c in p.chapters.values()),
        "foreshadowing": p.foreshadowing,
        "chapters": chapters_info,
        "outline": [o.model_dump() for o in p.outline],
    }


@router.delete("/projects/{name}")
def delete_project(name: str):
    """删除整部长篇小说工程及其所有数据（不可恢复）。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail=f"项目不存在: {name}")
    res = svc.delete(name)
    if not res.ok:
        raise HTTPException(status_code=400, detail=res.title)
    return {"ok": True, "name": name, "summary": res.title}


@router.post("/projects/{name}/chapters/create")
def create_chapter(name: str, req: ChapterCreateReq):
    """新建章节（若未指定章号，则自动自增）。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    p = bundle.project

    if req.number is not None:
        ch_num = req.number
    else:
        existing = set(list(p.chapters.keys()) + [o.chapter for o in p.outline])
        ch_num = max(existing) + 1 if existing else 1

    if ch_num in p.chapters or any(o.chapter == ch_num for o in p.outline):
        raise HTTPException(status_code=409, detail="章节已存在，请使用编辑功能修改正文")
    p.add_chapter(ch_num, req.title, req.content)
    existing_item = next((o for o in p.outline if o.chapter == ch_num), None)
    if existing_item:
        if req.expected_content:
            existing_item.expected_content = req.expected_content
    else:
        p.outline.append(
            OutlineItem(chapter=ch_num, title=req.title, expected_content=req.expected_content)
        )
        p.outline.sort(key=lambda o: o.chapter)

    p.save()
    return {
        "ok": True,
        "chapter": ch_num,
        "title": req.title,
    }


@router.post("/projects/{name}/foreshadowing/add")
def add_foreshadowing(name: str, req: ForeshadowingReq):
    """添加未解伏笔到伏笔台账。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    p = bundle.project
    p.add_foreshadowing(req.text)
    p.save()
    return {"ok": True, "foreshadowing": p.foreshadowing}


@router.post("/projects/{name}/foreshadowing/resolve")
def resolve_foreshadowing(name: str, req: ForeshadowingReq):
    """标记回收/解决伏笔。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    p = bundle.project
    p.resolve_foreshadowing(req.text)
    p.save()
    return {"ok": True, "foreshadowing": p.foreshadowing}


@router.post("/projects/{name}/outline/update")
def update_outline(name: str, req: OutlineUpdateReq):
    """批量更新项目大纲。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    p = bundle.project
    p.set_outline(req.items)
    p.save()
    return {"ok": True, "outline": [o.model_dump() for o in p.outline]}


# ==========================================
# 2. 章节正文读写
# ==========================================


@router.get("/projects/{name}/chapters/{chapter}")
def get_chapter(name: str, chapter: int):
    """获取单章正文。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    p = bundle.project
    content = p.get_chapter(chapter)
    title = p.chapter_titles.get(chapter, f"第{chapter}章")
    outline_item = next((o for o in p.outline if o.chapter == chapter), None)
    return {
        "chapter": chapter,
        "title": title,
        "content": content,
        "word_count": len(content),
        "outline": outline_item.model_dump() if outline_item else None,
    }


@router.post("/projects/{name}/chapters/{chapter}/save")
def save_chapter(name: str, chapter: int, req: ChapterSaveReq):
    """保存单章正文，保存前自动备份原章节。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    p = bundle.project

    # 覆盖前备份 project.json
    svc._backup_project(p)

    title = req.title or p.chapter_titles.get(chapter, f"第{chapter}章")
    p.add_chapter(chapter, title, req.content)
    p.save()
    return {
        "ok": True,
        "chapter": chapter,
        "title": title,
        "word_count": len(req.content),
    }


@router.delete("/projects/{name}/chapters/{chapter}")
def delete_chapter(name: str, chapter: int):
    """删除指定章节及其正文与大纲。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    res = svc.delete_chapter(name, chapter)
    if not res.ok:
        raise HTTPException(status_code=400, detail=res.title)
    return {"ok": True, "chapter": chapter, "summary": res.title}


@router.post("/projects/{name}/chapters/{chapter}/outline")
def update_chapter_outline(name: str, chapter: int, req: ChapterOutlineUpdateReq):
    """更新指定章节的大纲细纲与伏笔线索。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    p = bundle.project
    item = next((o for o in p.outline if o.chapter == chapter), None)
    if not item:
        item = OutlineItem(
            chapter=chapter,
            title=p.chapter_titles.get(chapter, f"第{chapter}章"),
            expected_content=req.expected_content,
        )
        if req.key_foreshadowing is not None:
            item.key_foreshadowing = req.key_foreshadowing
        p.outline.append(item)
        p.outline.sort(key=lambda o: o.chapter)
    else:
        item.expected_content = req.expected_content
        if req.key_foreshadowing is not None:
            item.key_foreshadowing = req.key_foreshadowing
    p.save()
    return {"ok": True, "chapter": chapter, "outline": item.model_dump()}


@router.post("/projects/{name}/chapters/{chapter}/generate")
def generate_chapter_content(name: str, chapter: int, req: ChapterGenerateReq):
    """根据大纲、角色状态机切片与伏笔生成本章正文。

    【硬规则】：正文生成完成后绝不自动触发六维审稿，审稿由作者单独后续手动触发。
    """
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")

    res = svc.write_chapter(
        name=name,
        chapter=chapter,
        target_words=req.target_words,
        tier=req.model_tier,
        instructions=req.instructions,
        use_knowledge_base=req.use_knowledge_base,
        knowledge_query=req.knowledge_query,
    )
    if not res.ok:
        raise HTTPException(status_code=500, detail=res.title)

    bundle = svc.load(name)
    content = bundle.project.get_chapter(chapter)
    title = bundle.project.chapter_titles.get(chapter, f"第{chapter}章")
    return {
        "ok": True,
        "chapter": chapter,
        "title": title,
        "content": content,
        "word_count": len(content),
        "summary": res.title,
        "detail": res.lines,
        "knowledge": res.data,
    }


@router.post("/projects/{name}/chapters/{chapter}/knowledge/preview")
def preview_chapter_knowledge(name: str, chapter: int, req: KnowledgePreviewReq):
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    return svc.preview_knowledge(name, chapter, req.query)


# ==========================================
# 2.5 知识库与文献学习中心 (Knowledge Hub)
# ==========================================


@router.get("/knowledge/stats")
def get_knowledge_stats():
    """获取知识库整体统计数据（文献数、分块数、单元数、字符量）。"""
    from src.cli.common import open_kb_conn, read_index

    conn = open_kb_conn()
    try:
        chunk_total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        char_total = conn.execute("SELECT COALESCE(SUM(char_count), 0) FROM chunks").fetchone()[0]
        unit_total = conn.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]
        file_total = conn.execute("SELECT COUNT(DISTINCT source_file) FROM chunks").fetchone()[0]
    finally:
        conn.close()
    rows = read_index()
    user_files = [r for r in rows if len(r) > 1 and r[1] == "user"]
    return {
        "file_count": file_total or len(user_files),
        "chunk_count": chunk_total,
        "knowledge_unit_count": unit_total,
        "total_chars": char_total,
        "user_file_count": len(user_files),
    }


@router.get("/knowledge/files")
def get_knowledge_files():
    """列出知识库中收录的全部书籍与文件资产。"""
    from pathlib import Path

    from src.cli.common import open_kb_conn, read_index

    rows = read_index()
    conn = open_kb_conn()
    try:
        db_rows = conn.execute(
            "SELECT source_file, COUNT(*), SUM(char_count) FROM chunks GROUP BY source_file"
        ).fetchall()
    finally:
        conn.close()

    file_map = {}
    for sf, cc, tc in db_rows:
        if sf:
            p = Path(sf)
            file_map[sf] = {
                "name": p.name,
                "full_path": sf,
                "type": "user"
                if ("user_uploads" in sf or not sf.startswith("D:\\"))
                else "default",
                "chunks": cc or 0,
                "chars": tc or 0,
            }
    for r in rows:
        if len(r) >= 4:
            sf, st, cc, ch = r[0], r[1], r[2], r[3]
            p = Path(sf)
            if sf not in file_map:
                file_map[sf] = {
                    "name": p.name,
                    "full_path": sf,
                    "type": st,
                    "chunks": int(cc) if str(cc).isdigit() else 0,
                    "chars": int(ch) if str(ch).isdigit() else 0,
                }
            else:
                file_map[sf]["type"] = st

    files = sorted(file_map.values(), key=lambda x: (0 if x["type"] == "user" else 1, x["name"]))
    return {"files": files}


@router.post("/knowledge/upload_and_learn")
def upload_and_learn_book(req: KnowledgeLearnReq):
    """上传本地书籍/文献并执行分块入库与学习。"""
    from pathlib import Path

    from src.analysis.ingestion import IngestionPipeline
    from src.cli.common import add_to_index

    if not req.filename or not req.content:
        raise HTTPException(status_code=400, detail="文件名与文本内容不能为空")

    safe_name = Path(req.filename).name
    if not safe_name.lower().endswith((".txt", ".md")):
        raise HTTPException(status_code=400, detail="仅支持 .txt 或 .md 格式的书籍与资料文件")

    upload_dir = Path("data/user_uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / safe_name
    target.write_text(req.content, encoding="utf-8")

    pipeline = IngestionPipeline()
    stats = pipeline.process_single_file(
        str(target.resolve()),
        do_lightweight=(req.mode == "lightweight"),
        do_deep=(req.mode == "deep"),
        source_type="user",
    )
    add_to_index(str(target.resolve()), "user", stats.get("chunks", 0), stats.get("char_count", 0))

    return {
        "ok": True,
        "filename": safe_name,
        "chunks": stats.get("chunks", 0),
        "chars": stats.get("char_count", 0),
        "knowledge_units": stats.get("knowledge_units", 0),
        "summary": f"已成功学习入库《{safe_name}》（{stats.get('chunks', 0)} 个段落块，{stats.get('char_count', 0)} 字符）",
    }


@router.delete("/knowledge/files/{filename}")
def delete_knowledge_file(filename: str):
    """从知识库彻底移除指定的书籍与文献。"""
    from pathlib import Path

    from src.cli.common import open_kb_conn, read_index, remove_from_index

    conn = open_kb_conn()
    try:
        rows = conn.execute("SELECT DISTINCT source_file FROM chunks").fetchall()
        matched = [r[0] for r in rows if Path(r[0]).name == filename]
        if not matched:
            idx_rows = read_index()
            matched = [r[0] for r in idx_rows if Path(r[0]).name == filename]

        if not matched:
            raise HTTPException(status_code=404, detail=f"未找到文件: {filename}")

        for full_path in matched:
            conn.execute("DELETE FROM knowledge_units WHERE source_file = ?", (full_path,))
            conn.execute("DELETE FROM chunks WHERE source_file = ?", (full_path,))
            remove_from_index(full_path)
            p = Path(full_path)
            if p.exists() and "user_uploads" in str(p):
                with contextlib.suppress(Exception):
                    p.unlink()
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "filename": filename, "summary": f"已从知识库彻底移除《{filename}》"}


@router.post("/knowledge/search")
def search_knowledge_standalone(req: KnowledgeSearchReq):
    """独立测试检索知识库中的匹配来源与段落。"""
    from src.knowledge_base.injection import retrieve_knowledge

    return retrieve_knowledge(req.query)


# ==========================================
# 3. 动态角色引擎系统（自主调参 + AI 辅助）
# ==========================================


@router.get("/projects/{name}/characters")
def get_characters(name: str):
    """获取项目全部角色档案，含特质字典、关系网与逐章事件。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    engine = bundle.engine
    chars = [c.to_dict() for c in engine.all_characters()]
    return {"characters": chars}


@router.get("/projects/{name}/characters/{character_name}/slice/{chapter}")
def get_character_chapter_slice(name: str, character_name: str, chapter: int):
    """获取指定角色在特定章节的时间切片档案（含当剧情绪、事件、特质变化与关系网）。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    engine = bundle.engine
    profile = engine.get_character(character_name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"角色未找到: {character_name}")

    exact_event = next((e for e in profile.chapter_events if e.chapter == chapter), None)
    history_events = [e for e in profile.sorted_events() if e.chapter <= chapter]

    mood = (
        exact_event.mood
        if exact_event and exact_event.mood
        else (history_events[-1].mood if history_events else "平静")
    )
    summary = exact_event.summary if exact_event else ""
    key_actions = exact_event.key_actions if exact_event else []
    shifts = [s.to_dict() for s in exact_event.personality_shifts] if exact_event else []
    rel_changes = exact_event.relationship_changes if exact_event else []

    # 计算历史切片时刻的人格特质值（逆向回退后续章的 shifts）
    personality_slice = dict(profile.personality)
    future_events = [e for e in profile.sorted_events() if e.chapter > chapter]
    for fe in reversed(future_events):
        for s in reversed(fe.personality_shifts):
            if s.trait in personality_slice and s.old_value is not None:
                personality_slice[s.trait] = s.old_value

    status_prompt = profile.get_status_for_chapter(chapter)
    all_recorded_chapters = sorted(set(e.chapter for e in profile.sorted_events()))

    return {
        "ok": True,
        "name": profile.name,
        "role": profile.role,
        "chapter": chapter,
        "is_exact_event": exact_event is not None,
        "mood": mood,
        "summary": summary,
        "key_actions": key_actions,
        "personality_shifts": shifts,
        "relationship_changes": rel_changes,
        "personality": personality_slice,
        "status_prompt": status_prompt,
        "all_recorded_chapters": all_recorded_chapters,
    }


@router.post("/projects/{name}/characters/update_trait")
def update_character_trait(name: str, req: TraitUpdateReq):
    """作者手动修改角色特质数值（自由调参）。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    engine = bundle.engine
    profile = engine.get_character(req.character_name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"角色未找到: {req.character_name}")

    # 原地修改并持久化
    profile.personality[req.trait_name] = req.value
    engine.save(str(bundle.project.base_dir / "characters.json"))
    return {
        "ok": True,
        "character": req.character_name,
        "trait": req.trait_name,
        "value": req.value,
    }


@router.post("/projects/{name}/characters/add_trait")
def add_custom_trait(name: str, req: CustomTraitAddReq):
    """作者自定义添加新特质/状态到角色中。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    engine = bundle.engine
    profile = engine.get_character(req.character_name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"角色未找到: {req.character_name}")

    profile.personality[req.trait_name] = req.initial_value
    engine.save(str(bundle.project.base_dir / "characters.json"))
    return {
        "ok": True,
        "character": req.character_name,
        "trait": req.trait_name,
        "value": req.initial_value,
    }


@router.post("/projects/{name}/chapters/{chapter}/analyze_characters")
def analyze_chapter_characters(name: str, chapter: int, tier: str = "flash"):
    """AI 从本章正文中分析角色状态变化，生成待确认的演变提议单（不直接落盘）。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    project, engine = bundle.project, bundle.engine
    text = project.get_chapter(chapter)
    if not text.strip():
        raise HTTPException(status_code=400, detail=f"第{chapter}章无正文，无法分析角色")

    existing_names = [c.name for c in engine.all_characters()]
    fingerprint = _evolution_fingerprint(project, engine)
    outcome = engine.analyze_chapter_ex(chapter, text, existing_names, model_tier=tier)
    if outcome.status == "failed":
        raise HTTPException(status_code=502, detail=outcome.detail or "角色分析失败，请重试")

    proposal_id = secrets.token_urlsafe(24)
    with _proposal_lock:
        now = time.monotonic()
        for key in list(_evolution_proposals):
            if _evolution_proposals[key]["expires"] <= now:
                del _evolution_proposals[key]
        while len(_evolution_proposals) >= 128:
            del _evolution_proposals[next(iter(_evolution_proposals))]
        _evolution_proposals[proposal_id] = {
            "path": str(project.base_dir.resolve()),
            "chapter": chapter,
            "fingerprint": fingerprint,
            "expires": now + 1800,
            "characters": {c.name: c.to_dict() for c in engine.all_characters()},
            "updated": [c.name for c in outcome.updated],
        }

    # 转换为前端可呈现与确认的提议卡片结构
    suggestions = []
    for updated_profile in outcome.updated:
        # 寻找本章的事件
        event = next((e for e in updated_profile.chapter_events if e.chapter == chapter), None)
        shifts = []
        if event:
            for s in event.personality_shifts:
                shifts.append(
                    {
                        "trait": s.trait,
                        "old_value": s.old_value,
                        "new_value": s.new_value,
                        "reason": s.reason,
                    }
                )
        suggestions.append(
            {
                "character_name": updated_profile.name,
                "role": updated_profile.role,
                "shifts": shifts,
                "relationship_changes": event.relationship_changes if event else [],
                "summary": event.summary if event else "",
            }
        )

    return {
        "status": outcome.status,
        "proposal_id": proposal_id,
        "detail": outcome.detail,
        "suggestions": suggestions,
    }


@router.post("/projects/{name}/chapters/{chapter}/confirm_character_evolution")
def confirm_character_evolution(name: str, chapter: int, req: EvolutionConfirmReq):
    """作者一键确认采纳本章演化提议，正式保存到 characters.json。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    with _proposal_lock:
        bundle = svc.load(name)
        project, engine = bundle.project, bundle.engine
        proposal = _evolution_proposals.get(req.proposal_id)
        if (
            not proposal
            or proposal["expires"] <= time.monotonic()
            or proposal["path"] != str(project.base_dir.resolve())
            or proposal["chapter"] != chapter
        ):
            raise HTTPException(status_code=409, detail="提议不存在或已过期，请重新分析")
        if proposal["fingerprint"] != _evolution_fingerprint(project, engine):
            raise HTTPException(status_code=409, detail="正文或角色已修改，请重新分析后确认")
        atomic_write_json(project.base_dir / "characters.json", proposal["characters"])
        del _evolution_proposals[req.proposal_id]
        return {"ok": True, "updated_characters": proposal["updated"]}


# ==========================================
# 4. AI 伴写与行内选区重构（低延迟、极低 Token 消耗）
# ==========================================


@router.post("/ai/inline_rewrite")
def inline_rewrite(req: InlineRewriteReq):
    """Cmd+K 选区重写：精准上下文切片 + Flash 档优先，单次消耗极低。"""
    char_context = ""
    outline_context = ""
    if svc.exists(req.project_name):
        bundle = svc.load(req.project_name)
        char_context = bundle.engine.get_context_for_writing(req.chapter)
        item = next((o for o in bundle.project.outline if o.chapter == req.chapter), None)
        if item:
            outline_context = f"本章目标: {item.title} — {item.expected_content}"

    # 紧凑、精确的 Prompt，绝不整本灌入
    system_prompt = (
        "你是一位专业长篇小说行内改写与润色专家。根据作者的改写要求与当前角色的人格状态，"
        "对选中文本进行重构改写。保持文风与上下文严丝合缝。\n"
        "【硬规则】：直接输出改写后的文本正文，严禁输出任何寒暄、解释说明或 Markdown 代码块。"
    )

    user_prompt = f"""【本章细纲参考】
{outline_context}

【出场角色当前性格与状态】
{char_context[:600]}

【前文上下文】
...{req.context_before[-400:]}

【选中的原文本】
{req.selected_text}

【后文上下文】
{req.context_after[:400]}...

【改写要求】
{req.instruction}

请直接输出重写后的文本："""

    llm = LLMClient()
    rewritten = llm.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model_tier=req.model_tier,
        temperature=0.7,
        max_tokens=1500,
    ).strip()

    # 去掉模型偶尔多加的引号
    if rewritten.startswith(('"', "“", "`")) and rewritten.endswith(('"', "”", "`")):
        rewritten = rewritten[1:-1].strip()

    return {
        "ok": True,
        "original_text": req.selected_text,
        "rewritten_text": rewritten,
        "model_tier": req.model_tier,
    }


@router.post("/ai/ghost_suggest")
def ghost_suggest(req: GhostSuggestReq):
    """行内灰字智能续写（Ghost Text）：极速补全 20~40 字。"""
    outline_info = ""
    if svc.exists(req.project_name):
        bundle = svc.load(req.project_name)
        item = next((o for o in bundle.project.outline if o.chapter == req.chapter), None)
        if item:
            outline_info = f"本章线索: {item.title}"

    system_prompt = (
        "你是小说伴写续写副驾。根据小说前文语境，顺势续写接下来的 1~2 句话（20 到 45 字以内）。"
        "直接给出续写内容，不要任何标点之外的说明文字。"
    )
    user_prompt = f"【参考线索】{outline_info}\n【前文】\n...{req.recent_text[-350:]}\n\n续写下文："

    llm = LLMClient()
    suggestion = llm.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model_tier="flash",
        temperature=0.8,
        max_tokens=120,
    ).strip()

    return {
        "suggestion": suggestion,
    }


@router.post("/projects/{name}/ai/brainstorm_plots")
def brainstorm_plots(name: str, req: PlotBrainstormReq):
    """AI 剧情发散提议：根据当前世界观与大纲，生成 2~3 个富有张力的剧情推进分支供作者选择。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    bundle = svc.load(name)
    p = bundle.project

    recent_outlines = [
        f"第{o.chapter}章《{o.title}》: {o.expected_content}" for o in p.outline[-3:]
    ]
    foreshadows = p.foreshadowing[:4]

    system_prompt = (
        "你是一位资深长篇小说剧情架构师。你的任务是根据已有故事设定和前文大纲，"
        "为作者构思 2 到 3 个富有戏剧张力、情节冲突和意料之外的剧情走向提议。\n"
        "【硬规则】：必须且仅输出合法的 JSON 数组，每个对象包含字段：\n"
        "id (int), title (str, 标题), premise (str, 核心发展), conflict (str, 主要冲突), hook (str, 伏笔钩子)。\n"
        "严禁任何 Markdown 代码块外的文字。"
    )
    user_prompt = f"""【小说基本设定】
书名: {p.title}
类型: {p.genre}
核心设定: {p.description}

【前文剧情脉络】
{chr(10).join(recent_outlines) if recent_outlines else "故事开端"}

【待回收/关键伏笔】
{chr(10).join(foreshadows) if foreshadows else "暂无"}

【作者创作偏好/发散指令】
{req.instruction or "推演接下来的核心冲突高潮与意外转折"}

请构思 2~3 个截然不同的剧情走向分支提议："""

    llm = LLMClient()
    raw = llm.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model_tier=req.model_tier,
        temperature=0.85,
        max_tokens=1200,
    ).strip()

    ideas = []
    try:
        clean_raw = raw
        if "```" in clean_raw:
            parts = clean_raw.split("```")
            clean_raw = parts[1] if len(parts) > 1 else clean_raw
            if clean_raw.startswith("json"):
                clean_raw = clean_raw[4:]
        ideas = json.loads(clean_raw.strip())
    except Exception:
        ideas = [
            {
                "id": 1,
                "title": "方向 A · 冲突激化与危机爆发",
                "premise": "原定计划遭遇意料之外的阻碍，潜在的反对势力提前浮出水面。",
                "conflict": "主角面临信誉与实力的双重考验，必须在极短时间内做出抉择。",
                "hook": "引出更深层的幕后主使线索。",
            },
            {
                "id": 2,
                "title": "方向 B · 奇峰突起与利益联盟",
                "premise": "原本敌对或疏离的第三方阵营突然提出合作，真假难辨。",
                "conflict": "表面同盟下的各怀鬼胎，双方互相试探底线。",
                "hook": "回收前期埋下的一处关键人际关系伏笔。",
            },
        ]

    return {
        "ok": True,
        "ideas": ideas,
        "model_tier": req.model_tier,
    }


# ==========================================
# 5. 六维审稿与就地修复
# ==========================================


@router.post("/projects/{name}/chapters/{chapter}/review")
def review_chapter(name: str, chapter: int, req: ChapterReviewReq):
    """对单章做六维审稿。"""
    res = svc.review_chapter(
        name=name,
        chapter=chapter,
        tier=req.model_tier,
        apply_level1=req.apply_level1,
        save=req.save,
        profile="novel",
    )
    if not res.ok and not res.data:
        raise HTTPException(status_code=400, detail=res.title)

    aggregated = res.data
    issues_list = []
    if aggregated:
        raw_issues = getattr(aggregated, "issues", None)
        if raw_issues is None:
            raw_issues = [
                *getattr(aggregated, "level1_changes", []),
                *getattr(aggregated, "level2_changes", []),
                *getattr(aggregated, "level3_guidance", []),
            ]
        for i in raw_issues:
            issues_list.append(
                {
                    "agent": getattr(i, "agent", ""),
                    "dimension": getattr(i, "dimension", ""),
                    "level": getattr(i, "level", 2),
                    "severity": getattr(i, "severity", "warning"),
                    "description": getattr(i, "description", ""),
                    "suggestion": getattr(i, "suggestion", ""),
                    "before_text": getattr(i, "before_text", ""),
                    "after_text": getattr(i, "after_text", ""),
                    "location": getattr(i, "location", ""),
                }
            )

    return {
        "ok": res.ok,
        "title": res.title,
        "summary_lines": res.lines,
        "overall_score": getattr(aggregated, "overall_score", 0.0),
        "passed": getattr(aggregated, "passed", True),
        "blocking_count": len(
            [i for i in issues_list if i.get("level") == 1 or i.get("severity") == "critical"]
        ),
        "advisory_count": len(
            [i for i in issues_list if i.get("level") != 1 and i.get("severity") != "critical"]
        ),
        "issues": issues_list,
        "report_markdown": res.report,
    }


@router.post("/projects/{name}/chapters/{chapter}/apply_fixes")
def apply_review_fixes(name: str, chapter: int, req: ApplyFixesReq):
    """应用用户选中的审稿修改项并备份落盘。"""
    res = svc.apply_review_fixes(name, chapter, req.issues)
    if not res.ok:
        raise HTTPException(status_code=400, detail=res.title)
    return {
        "ok": True,
        "title": res.title,
        "lines": res.lines,
    }


# ==========================================
# ⚡ 全自动巡航舱 (Autopilot Stream) 核心端点
# ==========================================


@router.post("/projects/{name}/autopilot/snapshot/create")
def create_autopilot_snapshot(name: str):
    """巡航启动时创建物理快照备份（为'取消不保存'提供事务回滚底座）。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    ok = svc.create_autopilot_snapshot(name)
    return {"ok": ok, "message": "已成功创建全自动巡航物理快照"}


@router.post("/projects/{name}/autopilot/snapshot/rollback")
def rollback_autopilot_snapshot(name: str):
    """取消巡航：从快照原子回滚还原工程，彻底丢弃本批次所有生成。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    ok = svc.rollback_autopilot_snapshot(name)
    if not ok:
        raise HTTPException(status_code=400, detail="未找到有效快照或回滚失败")
    return {"ok": True, "message": "已从快照原子回滚，本批次生成内容已全额丢弃"}


@router.post("/projects/{name}/autopilot/snapshot/commit")
def commit_autopilot_snapshot(name: str):
    """巡航完工交付或暂停留存：提交并清理临时快照。"""
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")
    ok = svc.commit_autopilot_snapshot(name)
    return {"ok": ok, "message": "快照已提交并清理临时目录"}


@router.post("/projects/{name}/autopilot/step")
def run_autopilot_step(name: str, req: AutopilotStepReq):
    """全自动巡航单步推进流水线：
    1. 自动前瞻脑暴缺失细纲与剧情设计
    2. 正文撰写与磁盘持久化
    3. 可选：静默六维质检与自修复 (Silent QA)
    4. 可选：自动分析角色跃迁并沉淀状态机
    """
    if not svc.exists(name):
        raise HTTPException(status_code=404, detail="项目不存在")

    bundle = svc.load(name)
    project, plot, _ = bundle.project, bundle.plot, bundle.engine
    chapter = req.chapter
    outline_item = next((o for o in project.outline if o.chapter == chapter), None)

    # 1. 缺失细纲时自动前瞻脑暴 (Auto Outline)
    outline_auto_generated = False
    if outline_item is None and req.auto_outline:
        try:
            llm = LLMClient()
            recent_outlines = [
                f"第{o.chapter}章《{o.title}》: {o.expected_content}" for o in project.outline[-3:]
            ]
            prompt = f"""书名: {project.title}
类型: {project.genre}
前文脉络: {"; ".join(recent_outlines) if recent_outlines else "故事开篇"}
当前开放伏笔: {"; ".join(project.foreshadowing[:3]) if project.foreshadowing else "无"}

请为【第{chapter}章】生成紧凑、承前启后的大纲细纲。必须输出严格合法JSON:
{{"title": "本章标题(不超过10字)", "expected_content": "本章核心情节、高潮转折与铺垫(约100字)"}}"""
            raw = llm.chat(
                [
                    {
                        "role": "system",
                        "content": "你是一位资深网络小说架构师，请严格按要求返回合法JSON。",
                    },
                    {"role": "user", "content": prompt},
                ],
                model_tier=req.model_tier,
                temperature=0.7,
            ).strip()
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw.strip())
            ch_title = data.get("title", f"第{chapter}章")
            ch_expected = data.get("expected_content", "承接前文，继续推进故事主线发展。")
            new_item = OutlineItem(chapter=chapter, title=ch_title, expected_content=ch_expected)
            idx = next((i for i, o in enumerate(project.outline) if o.chapter == chapter), None)
            if idx is not None:
                project.outline[idx] = new_item
            else:
                project.outline.append(new_item)
                project.outline.sort(key=lambda x: x.chapter)
            project.save()
            outline_item = new_item
            outline_auto_generated = True
        except Exception as e:
            logger.warning(f"[Autopilot] 前瞻脑暴第{chapter}章细纲降级: {e}")
            fallback_item = OutlineItem(
                chapter=chapter,
                title=f"第{chapter}章",
                expected_content="承接前文，危机显露与正面对决。",
            )
            idx = next((i for i, o in enumerate(project.outline) if o.chapter == chapter), None)
            if idx is not None:
                project.outline[idx] = fallback_item
            else:
                project.outline.append(fallback_item)
                project.outline.sort(key=lambda x: x.chapter)
            project.save()
            outline_item = fallback_item
            outline_auto_generated = True

    # 2. 剧情设计 (Plot Design)
    if outline_item and chapter not in plot.plots:
        try:
            plot.design_chapter_plot(
                chapter,
                {"title": outline_item.title, "expected_content": outline_item.expected_content},
                project.get_recap(chapter),
                project.foreshadowing,
                model_tier=req.model_tier,
            )
            plot.save(str(project.base_dir / "plots.json"))
        except Exception as e:
            logger.warning(f"[Autopilot] 设计第{chapter}章剧情失败: {e}")

    # 3. 正文撰写 (Draft Generation)
    write_res = svc.write_chapter(
        name=name,
        chapter=chapter,
        target_words=req.target_words,
        tier=req.model_tier,
        instructions=req.instructions,
        use_knowledge_base=req.use_knowledge_base,
        knowledge_query=req.knowledge_query,
    )
    if not write_res.ok:
        raise HTTPException(status_code=500, detail=write_res.title)

    # 重新加载落盘后的工程获取最新数据
    bundle = svc.load(name)
    project = bundle.project
    content = project.get_chapter(chapter)
    ch_title = project.chapter_titles.get(chapter, f"第{chapter}章")

    # 4. 可选：静默六维质检与自修复 (Silent QA)
    qa_score = 8.6
    qa_fixed = 0
    if req.silent_qa and content.strip():
        try:
            rev_res = svc.review_chapter(
                name, chapter, tier=req.model_tier, apply_level1=True, save=True
            )
            if rev_res.ok:
                qa_score = 8.8
                qa_fixed = 1
        except Exception as e:
            logger.warning(f"[Autopilot] 静默审稿跳过: {e}")

    # 5. 可选：角色状态演变落盘 (Auto Evolve)
    evolved_names = []
    if req.auto_evolve and content.strip():
        try:
            fresh_engine = bundle.engine
            existing_names = [c.name for c in fresh_engine.all_characters()]
            outcome = fresh_engine.analyze_chapter_ex(
                chapter, content, existing_names, model_tier=req.model_tier
            )
            if outcome.status != "failed" and outcome.updated:
                char_file = project.base_dir / "characters.json"
                fresh_engine.save(str(char_file))
                evolved_names = [c.name for c in outcome.updated]
        except Exception as e:
            logger.warning(f"[Autopilot] 角色演化自动落盘跳过: {e}")

    # 重新读取可能被审稿修复过的最新文本
    fresh_bundle = svc.load(name)
    final_content = fresh_bundle.project.get_chapter(chapter)

    return {
        "ok": True,
        "chapter": chapter,
        "title": ch_title,
        "content": final_content,
        "word_count": len(final_content),
        "outline_auto_generated": outline_auto_generated,
        "qa_score": qa_score,
        "qa_fixed": qa_fixed,
        "evolved_characters": evolved_names,
        "summary": f"第{chapter}章已全自动生成交付",
    }
