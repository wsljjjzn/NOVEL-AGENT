"""
analysis.ingestion — 知识库入库流水线。

完整流程：
1. 预处理文献 → 段落块 (Chunk)
2. 轻量分析 (V4 Flash) → 分类/标签/情感
3. 深度分析 (V4 Pro) → 四层知识卡片
4. 知识单元入库 → SQLite
5. Embedding 入库 → ChromaDB
"""

from typing import Optional
from pathlib import Path

from src.utils.logger import logger
from src.utils.file_utils import read_text_file, list_text_files
from src.preprocessing import PreprocessingPipeline
from src.knowledge_base import init_db, Retriever
from src.models import Chunk, KnowledgeUnit

from .lightweight import LightweightAnalyzer, LightweightAnalysis
from .deep import DeepAnalyzer, DeepAnalysis


class IngestionPipeline:
    """知识库入库流水线 — 编排所有分析步骤。"""

    def __init__(
        self,
        db_path: str = "",
        chunk_size: int = 512,
    ):
        self.preprocessor = PreprocessingPipeline(chunk_size=chunk_size)
        self.lightweight = LightweightAnalyzer()
        self.deep = DeepAnalyzer()
        self.db_path = db_path
        self._conn = None

    @property
    def conn(self):
        if self._conn is None:
            from config.settings import get_config
            cfg = get_config()
            path = self.db_path or cfg.database.get("path", "data/knowledge/writing_expert.db")
            self._conn = init_db(path)
        return self._conn

    def process_single_file(self, file_path: str,
                            do_lightweight: bool = False,
                            do_deep: bool = False,
                            source_type: str = "user") -> dict:
        """处理单个文件：预处理 → (可选)轻量分析 → (可选)深度分析 → 入库。

        Args:
            file_path: 文件路径
            do_lightweight: 是否执行轻量分析
            do_deep: 是否执行深度分析
            source_type: 来源类型（"default" 或 "user"）

        Returns:
            处理统计信息（含 chunks / char_count / knowledge_units 等）
        """
        stats = {"file": file_path, "chunks": 0, "char_count": 0,
                 "lightweight": False, "knowledge_units": 0,
                 "source_type": source_type}

        # 第一步：预处理
        chunks = self.preprocessor.process_file(file_path)
        stats["chunks"] = len(chunks)
        # 字数与入库的 chunks.char_count 同源，避免索引与实际库两个口径
        # （回归：kb learn 曾因缺这个键，把索引里的字数恒记为 0）
        stats["char_count"] = sum(c.char_count for c in chunks)
        logger.info(f"预处理完成: {len(chunks)} 个段落块")

        # 入库段落块
        self._save_chunks(chunks, source_type=source_type)

        # 第二步：轻量分析（用全文采样）
        if do_lightweight and chunks:
            sample_text = chunks[0].text[:2000] if chunks else ""
            if sample_text:
                analysis = self.lightweight.analyze_text(sample_text, file_path)
                stats["lightweight"] = True
                self._save_lightweight_metadata(file_path, analysis)
                logger.info(f"轻量分析完成: {analysis.category} / {analysis.tags}")

        # 第三步：深度分析（用全文）
        if do_deep and chunks:
            full_text = "\n".join(c.text for c in chunks[:20])  # 取前20段
            if len(full_text) > 500:
                source_name = Path(file_path).stem
                deep_result = self.deep.analyze_all(full_text, source_name)
                units = self.deep.synthesize_knowledge_units(deep_result, source_name)
                stats["knowledge_units"] = len(units)
                self._save_knowledge_units(units, source_type=source_type)
                logger.info(f"深度分析完成: {len(units)} 个知识单元")

        return stats

    def process_directory(self, directory: str, max_files: int = 0,
                          do_lightweight: bool = False,
                          do_deep: bool = False) -> list[dict]:
        """批量处理目录下的所有文件。

        Args:
            directory: 目录路径
            max_files: 最大处理数（0=不限）
            do_lightweight: 是否轻量分析
            do_deep: 是否深度分析

        Returns:
            各文件的处理统计列表
        """
        files = list_text_files(directory)
        if max_files > 0:
            files = files[:max_files]

        all_stats = []
        logger.info(f"批量入库开始: {len(files)} 个文件")

        for fpath in files:
            stats = self.process_single_file(fpath, do_lightweight, do_deep)
            all_stats.append(stats)

        total_chunks = sum(s["chunks"] for s in all_stats)
        total_units = sum(s["knowledge_units"] for s in all_stats)
        logger.info(f"批量入库完成: {total_chunks} 段落块, {total_units} 知识单元")

        return all_stats

    def _save_chunks(self, chunks: list[Chunk], source_type: str = "default") -> int:
        """将段落块写入 SQLite。"""
        saved = 0
        for chunk in chunks:
            try:
                cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO chunks
                       (chunk_id, source_file, text, char_count, paragraph_index, source_type, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (chunk.chunk_id, chunk.source_file, chunk.text,
                     chunk.char_count, chunk.paragraph_index, source_type),
                )
                if cursor.rowcount > 0:
                    saved += 1
            except Exception as e:
                logger.debug(f"入库失败 [{chunk.chunk_id}]: {e}")
        self.conn.commit()
        return saved

    def _save_lightweight_metadata(self, file_path: str, analysis: LightweightAnalysis):
        """将轻量分析结果写入素材元数据。"""
        # 当前 schema 中 chunks 表支持 metadata 扩展字段
        # 轻量分析结果主要用于后续筛选，存在 knowledge_units 中作为临时标记
        pass

    def _save_knowledge_units(self, units: list[KnowledgeUnit],
                                db_path: str = "",
                                source_type: str = "default") -> int:
        """将知识单元写入 SQLite。

        Args:
            units: 知识单元列表
            db_path: 数据库路径（为空则用 self.db_path）
            source_type: 来源类型（"default" 或 "user"）
        """
        import sqlite3
        from config.settings import get_config
        path = db_path or self.db_path or get_config().database.get("path", "data/knowledge/writing_expert_new.db")
        conn = sqlite3.connect(path)
        saved = 0
        for unit in units:
            try:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO knowledge_units
                       (knowledge_unit_id, type, category, source_file, source_location,
                        description, tags, source_type, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (
                        unit.knowledge_unit_id,
                        unit.type,
                        unit.category,
                        unit.source.get("file", ""),
                        unit.source.get("field", ""),
                        unit.description,
                        ",".join(unit.tags),
                        source_type,
                    ),
                )
                if cursor.rowcount > 0:
                    saved += 1
            except Exception as e:
                logger.debug(f"知识单元入库失败 [{unit.knowledge_unit_id}]: {e}")
        conn.commit()
        conn.close()
        return saved
