"""测试：写作引擎（非 LLM 部分）。"""

import json

from src.models import WritingRequest, RequiredElement, SectionOutline, Outline
from src.writing_engine.prompts import (
    REQUIREMENT_PARSER_SYSTEM,
    THOUGHT_STRUCTURE_SYSTEM,
    OUTLINE_GENERATOR_SYSTEM,
    SECTION_WRITER_SYSTEM,
    ARTICLE_ASSEMBLER_SYSTEM,
)


class TestPrompts:
    """所有系统提示词应非空且有实质内容。"""
    def test_requirement_parser_prompt(self):
        assert len(REQUIREMENT_PARSER_SYSTEM) > 100

    def test_thought_structure_prompt(self):
        assert len(THOUGHT_STRUCTURE_SYSTEM) > 100

    def test_outline_generator_prompt(self):
        assert len(OUTLINE_GENERATOR_SYSTEM) > 100

    def test_section_writer_prompt(self):
        assert len(SECTION_WRITER_SYSTEM) > 100

    def test_article_assembler_prompt(self):
        assert len(ARTICLE_ASSEMBLER_SYSTEM) > 100


class TestWritingRequestParsing:
    def test_required_element_defaults(self):
        elem = RequiredElement(description="测试要素")
        assert elem.verified is False

    def test_required_element_verified(self):
        elem = RequiredElement(description="已测试", verified=True)
        assert elem.verified is True


class TestOutlineCreation:
    def test_section_outline_defaults(self):
        section = SectionOutline(section_id=1, title="引言")
        assert section.core_argument == ""
        assert section.estimated_words == 0
        assert section.retrieval_queries == []

    def test_outline_not_confirmed(self):
        outline = Outline(title="测试")
        assert outline.confirmed is False

    def test_outline_confirm(self):
        outline = Outline(title="测试")
        outline.confirmed = True
        assert outline.confirmed is True


class TestSectionWriterNonLLM:
    def test_build_section_prompt_basic(self):
        """验证 prompt 构建不抛异常。"""
        from src.writing_engine.writer_agent import SectionWriter
        writer = SectionWriter()
        request = WritingRequest(topic="AI与教育")
        outline = Outline(
            title="AI与教育",
            sections=[SectionOutline(section_id=1, title="引言", core_argument="AI正在改变教育")],
        )
        section = outline.sections[0]
        prompt = writer._build_section_prompt(request, outline, section)
        assert "AI与教育" in prompt
        assert "引言" in prompt
        assert "AI正在改变教育" in prompt

    def test_build_section_prompt_with_style(self):
        """带风格模板的 prompt 构建。"""
        from src.writing_engine.writer_agent import SectionWriter
        from src.models import StyleTemplate
        writer = SectionWriter()
        request = WritingRequest(topic="测试")
        outline = Outline(title="测试", sections=[SectionOutline(section_id=1, title="章1")])
        style = StyleTemplate(
            template_id="test",
            template_name="测试风格",
            writing_rules=["规则1"],
        )
        prompt = writer._build_section_prompt(request, outline, outline.sections[0], style)
        assert "测试风格" in prompt
        assert "规则1" in prompt

    def test_build_section_prompt_with_forbidden(self):
        """带禁止项的 prompt 构建。"""
        from src.writing_engine.writer_agent import SectionWriter
        writer = SectionWriter()
        request = WritingRequest(topic="测试", forbidden=["禁止使用'赋能'"])
        outline = Outline(title="测试", sections=[SectionOutline(section_id=1, title="章1")])
        prompt = writer._build_section_prompt(request, outline, outline.sections[0])
        assert "禁止" in prompt
        assert "赋能" in prompt


class TestArticleAssembler:
    def test_assemble_empty(self):
        """空章节列表的组装。"""
        from src.writing_engine.writer_agent import ArticleAssembler
        from src.models import WritingRequest, Outline
        assembler = ArticleAssembler()
        request = WritingRequest(topic="测试")
        outline = Outline(title="测试")
        article = assembler.assemble(request, outline, [])
        assert article.title == "测试"
        assert article.total_words == 0
        assert article.full_text == ""

    def test_assemble_with_sections(self):
        """多章节组装。"""
        from src.writing_engine.writer_agent import ArticleAssembler
        from src.models import WritingRequest, Outline, WrittenSection
        assembler = ArticleAssembler()
        request = WritingRequest(topic="测试")
        outline = Outline(title="测试文章")
        sections = [
            WrittenSection(section_id=1, title="第一章", text="内容一", word_count=3),
            WrittenSection(section_id=2, title="第二章", text="内容二", word_count=3),
        ]
        article = assembler.assemble(request, outline, sections)
        assert article.total_words == 6
        assert "第一章" in article.full_text
        assert "第二章" in article.full_text

    def test_assemble_elements_checklist(self):
        """要素验证清单。"""
        from src.writing_engine.writer_agent import ArticleAssembler
        from src.models import WritingRequest, RequiredElement, Outline, WrittenSection
        assembler = ArticleAssembler()
        request = WritingRequest(
            topic="测试",
            required_elements=[
                RequiredElement(description="内容一"),
                RequiredElement(description="不存在的内容"),
            ],
        )
        outline = Outline(title="测试")
        sections = [
            WrittenSection(section_id=1, title="章1", text="内容一在这里", word_count=7),
        ]
        article = assembler.assemble(request, outline, sections)
        assert article.elements_checklist[0]["verified"] is True   # "内容一" 存在
        assert article.elements_checklist[1]["verified"] is False   # "不存在的内容" 不存在
