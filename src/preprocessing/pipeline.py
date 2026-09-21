"""
preprocessing.pipeline — 文献预处理管线。

三层分级的第一层：全量预处理（纯 Python，零 LLM 调用）。
"""

import os
import re
import hashlib
from pathlib import Path
from typing import Optional
from tqdm import tqdm

from src.utils.file_utils import detect_encoding, read_text_file, list_text_files
from src.utils.logger import logger
from src.models import Chunk, ChunkMetadata


class PreprocessingPipeline:
    """预处理管线：编码检测 → 清洗 → 段落切分 → 基础统计。"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # 噪音模式
        self.noise_patterns = [
            re.compile(r'^\s*\d+\s*$'),                          # 纯页码
            re.compile(r'^[-—=]{3,}$'),                           # 分割线
            re.compile(r'^第[一二三四五六七八九十百千\d]+[章节卷部集]'),  # 章节标题（保留）
            re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]'),          # 控制字符
        ]

    def clean_text(self, text: str) -> str:
        """清洗文本噪音。"""
        # 移除控制字符
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        # 统一换行
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # 合并多余空行（保留段落分隔）
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def split_paragraphs(self, text: str) -> list[str]:
        """按空行分割段落。"""
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]

    def is_noise(self, text: str) -> bool:
        """判断是否噪音行。"""
        if len(text) < 10:
            return True
        return False

    def create_chunk(self, text: str, source_file: str,
                     para_index: int, chapter: str = "") -> Chunk:
        """创建段落块。"""
        chunk_id = f"{Path(source_file).stem}_{para_index:05d}"
        return Chunk(
            chunk_id=chunk_id,
            source_file=source_file,
            text=text,
            char_count=len(text),
            paragraph_index=para_index,
            chapter_path=chapter,
        )

    def process_file(self, file_path: str) -> list[Chunk]:
        """处理单个文件，返回段落块列表。"""
        try:
            text = read_text_file(file_path)
        except Exception as e:
            logger.warning(f"读取失败: {file_path} — {e}")
            return []

        text = self.clean_text(text)
        paragraphs = self.split_paragraphs(text)
        chunks = []

        for i, para in enumerate(paragraphs):
            if self.is_noise(para):
                continue
            chunk = self.create_chunk(para, file_path, i)
            chunks.append(chunk)

        logger.info(f"处理完成: {file_path} → {len(chunks)} 个段落块")
        return chunks

    def process_directory(self, directory: str, extensions: Optional[set] = None,
                          max_files: int = 0) -> list[Chunk]:
        """批量处理目录下的所有文件。

        Args:
            directory: 目录路径
            extensions: 文件扩展名
            max_files: 最大处理文件数（0=不限制）

        Returns:
            所有段落块列表
        """
        files = list_text_files(directory, extensions)
        if max_files > 0:
            files = files[:max_files]

        all_chunks = []
        logger.info(f"开始批量处理: {directory} ({len(files)} 个文件)")

        for fpath in tqdm(files, desc="预处理进度"):
            chunks = self.process_file(fpath)
            all_chunks.extend(chunks)

        logger.info(f"批量处理完成: 共 {len(all_chunks)} 个段落块")
        return all_chunks
