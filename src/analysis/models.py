"""analysis.models — 分析专用的 Pydantic 模型。

注意：字段用 Any 类型，因为 LLM 可能返回 str/dict/list 等多种格式。
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


class LightweightAnalysis(BaseModel):
    """第二层轻量分析结果。"""
    category: str = Field(default="混合")
    tags: list[str] = Field(default_factory=list)
    quality: str = Field(default="完整可读")
    sentiment: str = Field(default="中立")
    summary: str = Field(default="")


class ThoughtAnalysis(BaseModel):
    """第三层 · 思想层分析。"""
    core_proposition: str = Field(default="")
    subverted_beliefs: Any = Field(default_factory=list)
    value_premise: Any = Field(default="")
    intellectual_lineage: Any = Field(default="")
    applicability_boundary: Any = Field(default="")


class StructureAnalysis(BaseModel):
    """第三层 · 结构层分析。"""
    structure_type: Any = Field(default="")
    info_release_rhythm: Any = Field(default="")
    climax_position: Any = Field(default="")
    section_functions: list[Any] = Field(default_factory=list)
    notable_technique: Any = Field(default="")


class NarrativeAnalysis(BaseModel):
    """第三层 · 叙事层分析。"""
    character_portrayal: Any = Field(default="")
    plot_design: Any = Field(default="")
    emotional_rhythm: Any = Field(default="")
    pov_and_distance: Any = Field(default="")
    notable_technique: Any = Field(default="")


class LanguageAnalysis(BaseModel):
    """第三层 · 语言层分析。"""
    sentence_length: Any = Field(default="")
    sentence_diversity: Any = Field(default="")
    modifier_density: Any = Field(default="")
    rhetorical_devices: Any = Field(default_factory=list)
    tone_and_distance: Any = Field(default="")
    overall_style: Any = Field(default="")


class DeepAnalysis(BaseModel):
    """第三层深度分析聚合。"""
    thought: ThoughtAnalysis = Field(default_factory=ThoughtAnalysis)
    structure: StructureAnalysis = Field(default_factory=StructureAnalysis)
    narrative: NarrativeAnalysis = Field(default_factory=NarrativeAnalysis)
    language: LanguageAnalysis = Field(default_factory=LanguageAnalysis)
