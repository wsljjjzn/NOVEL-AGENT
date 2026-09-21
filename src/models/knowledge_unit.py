"""
models.knowledge_unit — 知识单元模型。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class KnowledgeUnit(BaseModel):
    """知识单元 — 从文献中提取的最小可复用知识片段。

    支持四类知识：
    - idea: 思想层（核心命题、价值观、思想来源）
    - structure: 结构层（结构类型、信息释放节奏、段落功能）
    - technique: 叙事技法层（悬念、人物塑造、情感表达）
    - language: 语言层（文体风格、句式特征、修辞手法）
    """
    knowledge_unit_id: str = Field(description="唯一 ID")
    type: str = Field(description="知识类型: idea/structure/technique/language")
    category: str = Field(default="", description="子类别，如'悬念设置'、'递进结构'")
    source: dict = Field(default_factory=dict, description="来源引用 {file, location}")
    description: str = Field(default="", description="知识描述")
    mechanism: str = Field(default="", description="机制说明（为什么有效）")
    applicable_scenarios: list[str] = Field(default_factory=list)
    effect: str = Field(default="", description="效果描述")
    related_units: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = Field(default=None, description="向量嵌入")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
