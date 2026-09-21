"""
writing_engine.knowledge_bridge — 板块一 → 板块二的知识桥接。

从知识库中检索与写作需求相关的知识单元和范文段落，
自动注入到写作引擎的 prompt 中。
"""

from typing import Optional
from pathlib import Path
import random

from src.utils.logger import logger
from src.models import StyleTemplate, KnowledgeUnit
from config.settings import get_config


class KnowledgeBridge:
    """知识桥接器 — 将板块一的知识库连接到板块二的写作流程。"""

    def __init__(self):
        self._conn = None

    @property
    def conn(self):
        if self._conn is None:
            from src.knowledge_base import init_db
            cfg = get_config()
            path = cfg.database.get("path", "data/knowledge/writing_expert_new.db")
            self._conn = init_db(path)
        return self._conn

    def query_units(self, type_name: str, limit: int = 3) -> list[dict]:
        """按类型查询知识单元。"""
        rows = self.conn.execute(
            "SELECT description, tags, category FROM knowledge_units "
            "WHERE type=? AND description != '' AND length(description) > 50 "
            "ORDER BY length(description) DESC LIMIT ?",
            (type_name, limit),
        ).fetchall()
        return [
            {"description": r[0], "tags": r[1], "category": r[2]}
            for r in rows
        ]

    def build_style_template(self, style_name: str = "") -> Optional[StyleTemplate]:
        """从知识库中构建风格模板。

        从语言层知识单元中提取风格特征，组装为 StyleTemplate。
        """
        units = self.query_units("language", limit=5)
        if not units:
            return None

        # 提取写作规则
        rules = []
        for u in units:
            desc = u.get("description", "")
            if desc:
                # 提取关键规则
                if "句" in desc[:50]:
                    rules.append(f"句法特征: {desc[:100]}")
                elif "修辞" in desc[:50]:
                    rules.append(f"修辞运用: {desc[:100]}")
                else:
                    rules.append(desc[:100])

        # 提取禁止模式
        forbidden = []
        for u in units:
            tags = u.get("tags", "")
            if "病句" in tags or "语病" in tags:
                forbidden.append(u.get("description", "")[:60])

        template = StyleTemplate(
            template_id="kb_auto_" + style_name[:10] if style_name else "kb_auto",
            template_name=style_name or "知识库推断风格",
            writing_rules=rules[:5],
            forbidden_patterns=forbidden[:3],
        )
        return template

    def query_chunks_by_file(self, file_keyword: str, limit: int = 3) -> list[dict]:
        """按文件名关键词查询段落块。"""
        rows = self.conn.execute(
            "SELECT chunk_id, text, char_count FROM chunks "
            "WHERE source_file LIKE ? AND char_count > 100 "
            "ORDER BY char_count DESC LIMIT ?",
            (f"%{file_keyword}%", limit),
        ).fetchall()
        return [
            {"chunk_id": r[0], "text": r[1][:500], "char_count": r[2]}
            for r in rows
        ]

    def get_reference_chunks(self, topic: str, limit: int = 3) -> list[dict]:
        """根据主题关键词检索相关范文段落。

        从 chunks 表中找包含主题关键词的段落。
        """
        rows = self.conn.execute(
            "SELECT chunk_id, source_file, text FROM chunks "
            "WHERE text LIKE ? AND char_count > 200 "
            "LIMIT ?",
            (f"%{topic[:10]}%", limit),
        ).fetchall()
        return [
            {"chunk_id": r[0], "source_file": r[1], "text": r[2][:500]}
            for r in rows
        ]

    def get_writing_guidance(self, topic: str) -> str:
        """根据主题生成写作指引（从知识单元中匹配）。"""
        # 从思想层取相关命题
        idea_units = self.conn.execute(
            "SELECT description FROM knowledge_units WHERE type='idea' "
            "AND (description LIKE ? OR description LIKE ?) "
            "LIMIT 3",
            (f"%{topic[:6]}%", f"%写作%"),
        ).fetchall()

        # 从叙事层取技法
        tech_units = self.conn.execute(
            "SELECT description FROM knowledge_units WHERE type='technique' "
            "AND description != '' AND length(description) > 50 "
            "ORDER BY length(description) DESC LIMIT 3"
        ).fetchall()

        parts = []
        if idea_units:
            parts.append("### 思想参考")
            for u in idea_units:
                parts.append(f"- {u[0][:200]}")
        if tech_units:
            parts.append("\n### 叙事技法参考")
            for u in tech_units:
                parts.append(f"- {u[0][:200]}")

        return "\n".join(parts)
