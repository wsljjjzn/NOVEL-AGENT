"""
models.review — 审稿报告模型。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class ReviewIssue(BaseModel):
    """审稿发现的具体问题。"""
    issue_id: str = Field(default="")
    agent: str = Field(description="审稿 Agent 名称")
    level: int = Field(description="修改级别: 1(自动) / 2(半自动) / 3(手动)")
    location: str = Field(default="", description="问题位置（章节/段落）")
    severity: str = Field(default="warning", description="严重程度: critical/warning/info")
    description: str = Field(description="问题描述")
    suggestion: str = Field(default="", description="修改建议")
    before_text: str = Field(default="", description="修改前文本（Level 1/2 用）")
    after_text: str = Field(default="", description="修改后文本（Level 1/2 用）")
    auto_fixable: bool = Field(default=False)

    @model_validator(mode="after")
    def _set_auto_fixable(self):
        if self.level == 1:
            self.auto_fixable = True
        return self


class ReviewReport(BaseModel):
    """审稿报告（单个 Agent 的完整输出）。"""
    report_id: str = Field(default="")
    agent: str = Field(description="审稿 Agent: thought/structure/narrative/language/fact_check/proofread")
    article_id: str = ""
    overall_assessment: str = Field(default="", description="总体评价")
    strengths: list[str] = Field(default_factory=list)
    issues: list[ReviewIssue] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=10.0)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class AggregatedReview(BaseModel):
    """聚合审稿结果（六个 Agent 合并）。"""
    article_id: str = ""
    reports: list[ReviewReport] = Field(default_factory=list)
    level1_changes: list[ReviewIssue] = Field(default_factory=list, description="自动修改的变更")
    level2_changes: list[ReviewIssue] = Field(default_factory=list, description="待用户确认的变更")
    level3_guidance: list[ReviewIssue] = Field(default_factory=list, description="手动修改指引")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
