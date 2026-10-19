"""
api.server — FastAPI Web 服务。
"""

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.writing_engine import WritingOrchestrator
from src.review_engine import ReviewOrchestrator
from src.api.novel_router import router as novel_router

app = FastAPI(title="Novel Studio & 写作专家系统 API", version="0.2.0")

# 允许跨域请求（支持桌面端与独立页面调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(novel_router)

# 挂载 Web 原型页面
PROTOTYPE_DIR = Path(__file__).resolve().parents[2] / "web_prototype"
if PROTOTYPE_DIR.exists():
    @app.get("/")
    def index():
        return FileResponse(PROTOTYPE_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(PROTOTYPE_DIR)), name="static")

orchestrator = WritingOrchestrator()
reviewer = ReviewOrchestrator()


class WriteRequest(BaseModel):
    user_input: str
    style_template: str = ""
    reference_materials: list[str] = []


class WriteResponse(BaseModel):
    title: str
    outline: dict
    full_text: str
    total_words: int


class ReviewRequest(BaseModel):
    article_text: str
    profile: str = "article"          # article / novel
    context: str = ""                 # 作品状态（小说向一致性核对用）


class ReviewResponse(BaseModel):
    level1_auto_fixes: list[dict]
    level2_suggestions: list[dict]
    level3_guidance: list[dict]
    reports: list[dict]
    overall_score: float = 0.0
    failed_dimensions: list[str] = []


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/write", response_model=WriteResponse)
def write(req: WriteRequest):
    """端到端写作入口。"""
    try:
        _, outline, article = orchestrator.write(
            user_input=req.user_input,
        )
        return WriteResponse(
            title=article.title,
            outline=outline.model_dump() if hasattr(outline, 'model_dump') else outline.dict(),
            full_text=article.full_text,
            total_words=article.total_words,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/review", response_model=ReviewResponse)
def review(req: ReviewRequest):
    """审稿入口。"""
    try:
        result = reviewer.review(
            article_text=req.article_text, profile=req.profile, context=req.context,
        )
        return ReviewResponse(
            level1_auto_fixes=[i.model_dump() if hasattr(i, 'model_dump') else i.dict() for i in result.level1_changes],
            level2_suggestions=[i.model_dump() if hasattr(i, 'model_dump') else i.dict() for i in result.level2_changes],
            level3_guidance=[i.model_dump() if hasattr(i, 'model_dump') else i.dict() for i in result.level3_guidance],
            reports=[r.model_dump() if hasattr(r, 'model_dump') else r.dict() for r in result.reports],
            overall_score=result.overall_score,
            failed_dimensions=[r.agent for r in result.failed_reports],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
