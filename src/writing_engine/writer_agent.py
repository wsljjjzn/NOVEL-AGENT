"""
writing_engine.writer_agent — 逐节写作 Agent。
"""

from typing import Optional

from src.utils.llm_client import LLMClient
from src.utils.logger import logger
from src.models import (
    WritingRequest, Outline, SectionOutline,
    WrittenSection, WrittenArticle, StyleTemplate,
)
from .prompts import SECTION_WRITER_SYSTEM, ARTICLE_ASSEMBLER_SYSTEM


class SectionWriter:
    """逐节写作者 — 每次只写一个章节。"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def write_section(
        self,
        request: WritingRequest,
        outline: Outline,
        section: SectionOutline,
        style_template: Optional[StyleTemplate] = None,
        reference_chunks: list[dict] = None,
        model_tier: str = "pro",
    ) -> WrittenSection:
        """写一个章节。

        Args:
            request: 写作需求
            outline: 完整大纲
            section: 当前章节大纲
            style_template: 风格模板
            reference_chunks: 参考素材列表
            model_tier: 使用的模型层级（正文用 pro）

        Returns:
            完成的章节
        """
        logger.info(f"写作章节 {section.section_id}: {section.title}")

        prompt = self._build_section_prompt(
            request, outline, section, style_template, reference_chunks
        )

        response = self.llm.chat(
            [{"role": "system", "content": SECTION_WRITER_SYSTEM},
             {"role": "user", "content": prompt}],
            model_tier=model_tier,
            temperature=0.7,
        )

        return WrittenSection(
            section_id=section.section_id,
            title=section.title,
            text=response,
            word_count=len(response),
        )

    def _build_section_prompt(
        self,
        request: WritingRequest,
        outline: Outline,
        section: SectionOutline,
        style_template: Optional[StyleTemplate] = None,
        reference_chunks: list[dict] = None,
    ) -> str:
        parts = [
            f"## 文章总标题\n{outline.title}",
            f"\n## 当前章节\n{section.section_id}. {section.title}",
            f"\n核心论点：{section.core_argument}",
            f"\n预估字数：{section.estimated_words}",
        ]

        if style_template:
            parts.append(f"\n## 风格指令\n{style_template.template_name}")
            if style_template.writing_rules:
                parts.append("写作规则：\n" + "\n".join(f"- {r}" for r in style_template.writing_rules))
            if style_template.forbidden_patterns:
                parts.append("禁止：\n" + "\n".join(f"- {p}" for p in style_template.forbidden_patterns))
            if style_template.representative_samples:
                parts.append("风格参考示例：")
                for s in style_template.representative_samples[:2]:
                    parts.append(f"> {s.text_snippet[:200]}...")

        if request.forbidden:
            parts.append("\n## 禁止项\n" + "\n".join(f"- {f}" for f in request.forbidden))

        if reference_chunks:
            parts.append("\n## 参考素材\n")
            for i, chunk in enumerate(reference_chunks[:5]):
                text = chunk.get("text", "")[:300]
                parts.append(f"[素材 {i+1} | {chunk.get('chunk_id', '')}]\n{text}\n")

        if section.retrieval_queries:
            parts.append(f"\n检索方向参考：{', '.join(section.retrieval_queries)}")

        parts.append("\n请写出这一章的完整正文。每个事实性陈述标注 [来源: chunk_id]（如有参考素材）。")
        parts.append("素材找不到支持的标注[需补充证据]。")

        return "\n".join(parts)


class ArticleAssembler:
    """全文组装器 — 合并章节、检查一致性。"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def assemble(
        self,
        request: WritingRequest,
        outline: Outline,
        sections: list[WrittenSection],
        model_tier: str = "pro",
    ) -> WrittenArticle:
        """组装全文并验证。

        Args:
            request: 写作需求
            outline: 大纲
            sections: 各章节
            model_tier: 使用的模型层级

        Returns:
            完成文章
        """
        # 简单合并（暂不做 LLM 后处理）
        full_text = "\n\n".join(
            f"## {s.title}\n\n{s.text}" for s in sections
        )

        total_words = sum(s.word_count for s in sections)

        # 要素验证
        elements_checklist = []
        for elem in request.required_elements:
            found = elem.description[:10] in full_text
            elements_checklist.append({
                "element": elem.description,
                "verified": found,
            })

        return WrittenArticle(
            title=outline.title,
            sections=sections,
            full_text=full_text,
            total_words=total_words,
            elements_checklist=elements_checklist,
        )
