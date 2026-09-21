"""
models.style_template — 风格模板模型。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class QuantitativeProfile(BaseModel):
    """定量特征画像。"""
    avg_sentence_length: float = 0.0
    adj_adv_ratio: float = 0.0
    punctuation_freq: dict[str, float] = Field(default_factory=dict)
    top_words: list[str] = Field(default_factory=list)


class QualitativeProfile(BaseModel):
    """定性特征画像。"""
    genre: str = ""          # 评论批判 / 温情叙事 / 冷峻写实 / ...
    tone: str = ""           # 冷峻克制 / 热情洋溢 / 讽刺辛辣 / 朴实平和
    narrative_distance: str = ""  # 与读者的距离：远/中/近


class RepresentativeSample(BaseModel):
    """代表性样本（few-shot 示例）。"""
    chunk_id: str = ""
    text_snippet: str = ""


class StyleTemplate(BaseModel):
    """风格模板 — 控制生成文本的风格。"""
    template_id: str = Field(description="模板 ID")
    template_name: str = Field(description="模板名称，如'冷峻评论体'")
    quantitative_profile: QuantitativeProfile = Field(default_factory=QuantitativeProfile)
    qualitative_profile: QualitativeProfile = Field(default_factory=QualitativeProfile)
    writing_rules: list[str] = Field(default_factory=list, description="写作规则，如'必须每段以短句收束'")
    forbidden_patterns: list[str] = Field(default_factory=list, description="禁止模式")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    best_for: str = ""
    avoid_for: str = ""
    representative_samples: list[RepresentativeSample] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
