"""
models.review — 审稿报告模型。

失败语义（见 docs/specs/contracts.md §4）：
- `ReviewReport.status="ok"`：维度产出有效报告（没有问题也是有效结论）。
- `ReviewReport.status="failed"`：LLM 调用失败或结构化输出解析失败——
  必须能被上层识别，不能与「审得很好没问题」混淆。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ReviewStatus = Literal["ok", "failed"]


def _coerce_level(value, default: int = 2) -> int:
    """把任意 level 写法夹到 1/2/3（模型可能返回 "Level 1" 之类）。"""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        try:
            return max(1, min(3, int(value)))
        except (TypeError, ValueError):
            return default
    if isinstance(value, str):
        text = value.strip()
        try:
            return max(1, min(3, int(text)))
        except ValueError:
            return default
    return default


def _clamp_score(value) -> float:
    """把 score 夹到 [0, 10]；非法值退回 0.0，绝不因越界抛 ValidationError。"""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score != score:  # NaN
        return 0.0
    return max(0.0, min(10.0, score))


class ReviewIssue(BaseModel):
    """审稿发现的具体问题。"""
    issue_id: str = Field(default="")
    agent: str = Field(description="审稿 Agent 名称")
    dimension: str = Field(default="", description="维度 key（thought/character/...）")
    level: int = Field(description="修改级别: 1(自动) / 2(半自动) / 3(手动)")
    location: str = Field(default="", description="问题位置（章节/段落）")
    severity: str = Field(default="warning", description="严重程度: critical/warning/info")
    description: str = Field(description="问题描述")
    suggestion: str = Field(default="", description="修改建议")
    before_text: str = Field(default="", description="修改前文本（Level 1/2 用）")
    after_text: str = Field(default="", description="修改后文本（Level 1/2 用）")
    auto_fixable: bool = Field(default=False)
    duplicated_by: list[str] = Field(
        default_factory=list,
        description="同样报出该问题的其他维度名称（聚合去重时填入）",
    )

    @field_validator("level", mode="before")
    @classmethod
    def _level_in_range(cls, value):
        return _coerce_level(value)

    @model_validator(mode="after")
    def _set_auto_fixable(self):
        if self.level == 1:
            self.auto_fixable = True
        return self


class ReviewReport(BaseModel):
    """审稿报告（单个维度的完整输出）。"""
    report_id: str = Field(default="")
    agent: str = Field(description="审稿维度名称，如 思想审稿 / 人物一致性")
    dimension: str = Field(default="", description="维度 key，如 thought / character")
    article_id: str = ""
    status: ReviewStatus = Field(default="ok", description="ok=有效报告 / failed=调用或解析失败")
    error: str = Field(default="", description="status=failed 时的失败原因")
    overall_assessment: str = Field(default="", description="总体评价")
    strengths: list[str] = Field(default_factory=list)
    issues: list[ReviewIssue] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=10.0)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    @field_validator("score", mode="before")
    @classmethod
    def _score_in_range(cls, value):
        return _clamp_score(value)

    @property
    def ok(self) -> bool:
        """维度是否产出了有效报告（失败维度不计分）。"""
        return self.status == "ok"


class AggregatedReview(BaseModel):
    """聚合审稿结果（六个维度合并）。"""
    article_id: str = ""
    profile: str = Field(default="article", description="维度预设: article / novel")
    reports: list[ReviewReport] = Field(default_factory=list)
    level1_changes: list[ReviewIssue] = Field(default_factory=list, description="自动修改的变更")
    level2_changes: list[ReviewIssue] = Field(default_factory=list, description="待用户确认的变更")
    level3_guidance: list[ReviewIssue] = Field(default_factory=list, description="手动修改指引")
    applied_fixes: int = Field(default=0, description="Level 1 实际命中的修改数")
    missed_fixes: int = Field(default=0, description="Level 1 锚点未命中的数量")
    skipped_fixes: int = Field(default=0, description="因锚点过短/退化被跳过的数量")
    warnings: list[str] = Field(default_factory=list, description="成功但有隐患的提示")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    @property
    def ok_reports(self) -> list[ReviewReport]:
        return [r for r in self.reports if r.status == "ok"]

    @property
    def failed_reports(self) -> list[ReviewReport]:
        return [r for r in self.reports if r.status == "failed"]

    @property
    def overall_score(self) -> float:
        """有效维度的平均分；全部失败时为 0.0（不伪装成 5.0）。"""
        scores = [r.score for r in self.ok_reports]
        return round(sum(scores) / len(scores), 2) if scores else 0.0

    @property
    def coverage(self) -> str:
        """有效维度 / 总维度，如 "5/6"。"""
        return f"{len(self.ok_reports)}/{len(self.reports)}"

    @property
    def applicable_issues(self) -> list[ReviewIssue]:
        """带 before/after、可机械替换的条目（Level 1 在前，Level 2 在后）。

        审稿浮层据此生成「勾选哪条改哪条」的清单：Level 1 与 Level 2 都可能带
        可替换片段，Level 3 只有指引、无法机械应用。
        """
        items = [*self.level1_changes, *self.level2_changes]
        return [i for i in items if i.before_text and i.after_text]

    @property
    def guidance_issues(self) -> list[ReviewIssue]:
        """只能人工处理的条目：Level 3 + 缺 before/after 的 Level 1/2。"""
        items = [*self.level1_changes, *self.level2_changes]
        return [i for i in items if not (i.before_text and i.after_text)] \
            + list(self.level3_guidance)

    @property
    def issues(self) -> list[ReviewIssue]:
        """全部审稿问题条目（Level 1 自动 + Level 2 待确认 + Level 3 手动指引）。"""
        return [*self.level1_changes, *self.level2_changes, *self.level3_guidance]

    @property
    def blocking_issues(self) -> list[ReviewIssue]:
        """阻断性硬伤：Level 1（可机械自动替换的字词错别字/标点错误）或标注为 critical 的致命问题。"""
        return [i for i in self.issues if i.level == 1 or i.severity == "critical"]

    @property
    def advisory_issues(self) -> list[ReviewIssue]:
        """建议性修辞与风格灵感：Level 2 / 3 且非 critical 的建议，供作者选读，不作为阻断项。"""
        return [i for i in self.issues if i.level != 1 and i.severity != "critical"]

    @property
    def passed(self) -> bool:
        """本章是否达标放行：无 Level 1/critical 阻断性硬伤，且（综合评分 >= 7.5 或总硬伤数为 0）。"""
        return len(self.blocking_issues) == 0 and (self.overall_score >= 7.5 or len(self.issues) == 0)
