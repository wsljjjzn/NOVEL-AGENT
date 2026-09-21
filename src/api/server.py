"""
api.server — FastAPI Web 服务。
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.writing_engine import WritingOrchestrator
from src.review_engine import ReviewOrchestrator

app = FastAPI(title="写作专家系统 API", version="0.1.0")
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


class ReviewResponse(BaseModel):
    level1_auto_fixes: list[dict]
    level2_suggestions: list[dict]
    level3_guidance: list[dict]
    reports: list[dict]


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
        result = reviewer.review(article_text=req.article_text)
        return ReviewResponse(
            level1_auto_fixes=[i.model_dump() if hasattr(i, 'model_dump') else i.dict() for i in result.level1_changes],
            level2_suggestions=[i.model_dump() if hasattr(i, 'model_dump') else i.dict() for i in result.level2_changes],
            level3_guidance=[i.model_dump() if hasattr(i, 'model_dump') else i.dict() for i in result.level3_guidance],
            reports=[r.model_dump() if hasattr(r, 'model_dump') else r.dict() for r in result.reports],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
