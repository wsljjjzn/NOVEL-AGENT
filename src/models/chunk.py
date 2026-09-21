"""
models.chunk — 段落块模型。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    """源文件元数据（可选，用于引用溯源）。"""
    author: str = ""
    year: int = 0
    work: str = ""
    genre: str = ""  # 叙事类/议论类/抒情类/实用类


class Chunk(BaseModel):
    """段落块 — 文献的基本处理单元。"""
    chunk_id: str = Field(description="唯一 ID，格式: source_file_序号")
    source_file: str = Field(description="来源文件名")
    source_metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)
    chapter_path: str = Field(default="", description="章节路径")
    paragraph_index: int = Field(default=0, description="在源文件中的段落序号")
    text: str = Field(description="段落文本")
    char_count: int = Field(default=0, description="字符数")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def __init__(self, **data):
        super().__init__(**data)
        if self.char_count == 0 and self.text:
            self.char_count = len(self.text)
