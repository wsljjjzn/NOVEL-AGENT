"""
models.writing_request — 写作请求与输出模型。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RequiredElement(BaseModel):
    """用户要求的文章要素。"""
    description: str = Field(description="要素描述")
    verified: bool = Field(default=False, description="是否在最终文章中验证通过")


class WritingRequest(BaseModel):
    """用户写作需求（标准化后）。"""
    request_id: str = Field(default="", description="请求 ID")
    topic: str = Field(description="主题")
    style: str = Field(default="", description="风格名称或'模仿xxx素材的风格'")
    word_count: int = Field(default=2000, description="目标字数")
    required_elements: list[RequiredElement] = Field(default_factory=list)
    audience: str = Field(default="", description="目标读者")
    tone_override: str = Field(default="", description="语气覆盖")
    forbidden: list[str] = Field(default_factory=list)
    reference_materials: list[str] = Field(default_factory=list)
    raw_input: str = Field(default="", description="原始用户输入")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SectionOutline(BaseModel):
    """章节大纲。"""
    section_id: int = Field(description="章节序号")
    title: str = Field(description="章节标题")
    core_argument: str = Field(default="", description="核心论点")
    estimated_words: int = Field(default=0, description="预估字数")
    retrieval_queries: list[str] = Field(default_factory=list, description="检索方向/关键词")
    notes: list[str] = Field(default_factory=list, description="注意事项")


class Outline(BaseModel):
    """完整大纲。"""
    outline_id: str = Field(default="", description="大纲 ID")
    request_id: str = Field(default="")
    title: str = Field(default="", description="文章标题")
    sections: list[SectionOutline] = Field(default_factory=list)
    overall_notes: list[str] = Field(default_factory=list)
    confirmed: bool = Field(default=False, description="用户是否确认")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class WrittenSection(BaseModel):
    """已完成的章节。"""
    section_id: int = Field(description="章节序号")
    title: str = ""
    text: str = ""
    word_count: int = 0
    citations: list[dict] = Field(default_factory=list, description="引用标注 [{chunk_id, claim}]")


class WrittenArticle(BaseModel):
    """已完成文章。"""
    article_id: str = Field(default="")
    request_id: str = ""
    outline_id: str = ""
    title: str = ""
    sections: list[WrittenSection] = Field(default_factory=list)
    full_text: str = ""
    total_words: int = 0
    elements_checklist: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
