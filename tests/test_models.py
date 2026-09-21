"""测试：核心数据模型。"""

from src.models import (
    Chunk, ChunkMetadata, KnowledgeUnit, StyleTemplate,
    WritingRequest, RequiredElement, SectionOutline, Outline,
    WrittenSection, WrittenArticle, ReviewIssue, ReviewReport, AggregatedReview,
)


class TestChunk:
    def test_minimal(self):
        c = Chunk(chunk_id="test_0001", source_file="test.txt", text="Hello 世界")
        assert c.chunk_id == "test_0001"
        assert c.char_count == len("Hello 世界")

    def test_with_metadata(self):
        c = Chunk(
            chunk_id="素材A_0037",
            source_file="素材A.txt",
            source_metadata=ChunkMetadata(author="鲁迅", year=1923),
            chapter_path="自序",
            paragraph_index=12,
            text="这是一个测试段落。",
        )
        assert c.source_metadata.author == "鲁迅"
        assert c.chapter_path == "自序"
        assert c.paragraph_index == 12

    def test_char_count_auto(self):
        c = Chunk(chunk_id="test", source_file="f.txt", text="你好世界")
        assert c.char_count == 4


class TestKnowledgeUnit:
    def test_minimal(self):
        ku = KnowledgeUnit(
            knowledge_unit_id="素材A_叙事技法_悬念铺设",
            type="technique",
            category="悬念设置",
            description="作者通过看似随意的话埋下悬念",
        )
        assert ku.type == "technique"
        assert ku.category == "悬念设置"
        assert ku.tags == []

    def test_with_tags(self):
        ku = KnowledgeUnit(
            knowledge_unit_id="test_001",
            type="idea",
            tags=["悬念", "伏笔", "信息控制"],
        )
        assert len(ku.tags) == 3
        assert "悬念" in ku.tags


class TestStyleTemplate:
    def test_minimal(self):
        st = StyleTemplate(
            template_id="style_07",
            template_name="冷峻评论体",
            writing_rules=["每段4-6句以短句收束", "禁止使用感叹号"],
        )
        assert len(st.writing_rules) == 2
        assert st.best_for == ""

    def test_representative_samples(self):
        from src.models.style_template import RepresentativeSample
        st = StyleTemplate(
            template_id="style_01",
            template_name="温情叙事体",
            representative_samples=[
                RepresentativeSample(chunk_id="c1", text_snippet="一段温情文字。"),
            ],
        )
        assert len(st.representative_samples) == 1
        assert st.representative_samples[0].chunk_id == "c1"


class TestWritingRequest:
    def test_minimal(self):
        req = WritingRequest(topic="人工智能对教育的影响")
        assert req.topic == "人工智能对教育的影响"
        assert req.word_count == 2000

    def test_with_elements(self):
        req = WritingRequest(
            topic="AI与教育",
            style="冷峻评论体",
            word_count=2000,
            required_elements=[
                RequiredElement(description="至少2个案例"),
            ],
            audience="教育从业者",
            forbidden=["禁止使用'赋能'"],
        )
        assert req.style == "冷峻评论体"
        assert len(req.required_elements) == 1
        assert "赋能" in req.forbidden[0]


class TestOutline:
    def test_with_sections(self):
        outline = Outline(
            title="AI与教育",
            sections=[
                SectionOutline(section_id=1, title="引言", core_argument="AI正在改变教育"),
                SectionOutline(section_id=2, title="正反观点", core_argument="双面影响"),
            ],
        )
        assert len(outline.sections) == 2
        assert outline.sections[0].title == "引言"
        assert outline.sections[0].section_id == 1

    def test_not_confirmed_by_default(self):
        outline = Outline(title="测试")
        assert outline.confirmed is False


class TestWrittenArticle:
    def test_assembly(self):
        sections = [
            WrittenSection(section_id=1, title="第一章", text="第一章内容", word_count=4),
            WrittenSection(section_id=2, title="第二章", text="第二章内容", word_count=4),
        ]
        article = WrittenArticle(
            title="测试文章",
            sections=sections,
            full_text="第一章内容\n\n第二章内容",
            total_words=8,
        )
        assert len(article.sections) == 2
        assert article.total_words == 8


class TestReviewModels:
    def test_review_issue(self):
        issue = ReviewIssue(
            agent="thought",
            level=3,
            location="第3段",
            severity="warning",
            description="论点缺乏反例考量",
            suggestion="补充反例段落",
        )
        assert issue.agent == "thought"
        assert issue.level == 3

    def test_review_report(self):
        report = ReviewReport(
            agent="thought",
            article_id="art_001",
            overall_assessment="思想深度不足",
            score=6.5,
        )
        assert report.agent == "thought"
        assert report.score == 6.5

    def test_aggregated_review(self):
        review = AggregatedReview(article_id="art_001")
        assert review.article_id == "art_001"
        assert review.level1_changes == []
        assert review.level2_changes == []
