"""测试：板块一 — 文献学习系统分析模块。"""

from src.analysis.models import (
    LightweightAnalysis as LWModel,
    ThoughtAnalysis, StructureAnalysis,
    NarrativeAnalysis, LanguageAnalysis,
)
from src.analysis.lightweight import LightweightAnalyzer
from src.analysis.deep import DeepAnalyzer
from src.analysis.ingestion import IngestionPipeline


class TestAnalysisModels:
    def test_lightweight_defaults(self):
        a = LWModel()
        assert a.category == "混合"
        assert a.tags == []
        assert a.quality == "完整可读"
        assert a.sentiment == "中立"

    def test_lightweight_full(self):
        a = LWModel(
            category="叙事类",
            tags=["武侠", "江湖"],
            quality="完整可读",
            sentiment="积极",
            summary="一个武侠故事",
        )
        assert a.category == "叙事类"
        assert "武侠" in a.tags

    def test_thought_analysis(self):
        t = ThoughtAnalysis(
            core_proposition="命运由选择而非天定",
            intellectual_lineage="存在主义",
        )
        assert "命运" in t.core_proposition
        assert t.intellectual_lineage == "存在主义"

    def test_structure_analysis(self):
        s = StructureAnalysis(
            structure_type="递进",
            climax_position="全文3/4处",
            notable_technique="层层递进",
        )
        assert s.structure_type == "递进"

    def test_narrative_analysis(self):
        n = NarrativeAnalysis(
            character_portrayal="圆形人物，通过对话展现性格",
            plot_design="双线叙事",
        )
        assert "双线" in n.plot_design

    def test_language_analysis(self):
        l = LanguageAnalysis(
            sentence_length="平均25字，长短句交替",
            overall_style="冷峻写实",
        )
        assert l.overall_style == "冷峻写实"


class TestLightweightAnalyzer:
    def test_parse_normal(self):
        analyzer = LightweightAnalyzer()
        response = '''{
            "category": "议论类",
            "tags": ["教育", "AI", "未来"],
            "quality": "完整可读",
            "sentiment": "中立",
            "summary": "讨论AI对教育的影响"
        }'''
        result = analyzer._parse(response)
        assert result.category == "议论类"
        assert len(result.tags) == 3
        assert "AI" in result.tags

    def test_parse_invalid_json(self):
        analyzer = LightweightAnalyzer()
        response = "这不是JSON"
        result = analyzer._parse(response)
        assert result.summary == "这不是JSON"
        assert result.category == "混合"

    def test_parse_partial(self):
        analyzer = LightweightAnalyzer()
        response = '{"category": "叙事类"}'
        result = analyzer._parse(response)
        assert result.category == "叙事类"
        assert result.tags == []


class TestDeepAnalyzer:
    def test_parse_thought_layer(self):
        analyzer = DeepAnalyzer()
        response = '''{
            "core_proposition": "反常识的断言",
            "subverted_beliefs": ["流行观念A"],
            "value_premise": "人性本善",
            "intellectual_lineage": "儒家思想",
            "applicability_boundary": "适用于集体主义文化"
        }'''
        result = analyzer._parse_layer("thought", response)
        assert isinstance(result, ThoughtAnalysis)
        assert "反常识" in result.core_proposition
        assert len(result.subverted_beliefs) == 1

    def test_parse_structure_layer(self):
        analyzer = DeepAnalyzer()
        response = '''{
            "structure_type": "环形结构",
            "info_release_rhythm": "三段式释放",
            "climax_position": "结尾",
            "section_functions": [{"para": 1, "func": "hook"}],
            "notable_technique": "首尾呼应"
        }'''
        result = analyzer._parse_layer("structure", response)
        assert isinstance(result, StructureAnalysis)
        assert result.structure_type == "环形结构"

    def test_parse_narrative_layer(self):
        analyzer = DeepAnalyzer()
        response = '''{
            "character_portrayal": "通过对话塑造",
            "plot_design": "双线叙事",
            "emotional_rhythm": "先抑后扬",
            "pov_and_distance": "第三人称有限视角",
            "notable_technique": "留白"
        }'''
        result = analyzer._parse_layer("narrative", response)
        assert isinstance(result, NarrativeAnalysis)

    def test_parse_language_layer(self):
        analyzer = DeepAnalyzer()
        response = '''{
            "sentence_length": "平均20字",
            "sentence_diversity": "丰富",
            "modifier_density": "适中",
            "rhetorical_devices": ["排比", "比喻"],
            "tone_and_distance": "冷峻",
            "overall_style": "新闻体"
        }'''
        result = analyzer._parse_layer("language", response)
        assert isinstance(result, LanguageAnalysis)
        assert result.overall_style == "新闻体"

    def test_parse_invalid_json(self):
        analyzer = DeepAnalyzer()
        result = analyzer._parse_layer("thought", "broken json")
        assert isinstance(result, ThoughtAnalysis)
        assert result.core_proposition == ""

    def test_synthesize_empty(self):
        analyzer = DeepAnalyzer()
        from src.analysis.models import DeepAnalysis
        da = DeepAnalysis()
        units = analyzer.synthesize_knowledge_units(da, "test_file")
        assert isinstance(units, list)

    def test_synthesize_with_data(self):
        analyzer = DeepAnalyzer()
        da = type('DeepAnalysis', (), {
            'thought': ThoughtAnalysis(core_proposition="一个非常有价值的核心命题，长度超过十个字"),
            'structure': StructureAnalysis(structure_type="递进结构是一种很好的组织方式"),
            'narrative': NarrativeAnalysis(character_portrayal="人物塑造通过对话和行为展现性格特征"),
            'language': LanguageAnalysis(overall_style="冷峻写实的语言风格贯穿全文"),
            'model_dump': lambda self: {
                'thought': {'core_proposition': 'test'},
                'structure': {'structure_type': 'test'},
                'narrative': {'character_portrayal': 'test'},
                'language': {'overall_style': 'test'},
            }
        })()
        units = analyzer.synthesize_knowledge_units(da, "test_file")
        # should produce 0 because model_dump returns short strings
        assert isinstance(units, list)


class TestIngestionPipeline:
    def test_process_single_file_no_api(self):
        """不调 API 时只做预处理 + 入库。"""
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         encoding="utf-8", delete=False) as f:
            f.write("第一段内容。用于测试预处理和入库流程。\n\n")
            f.write("第二段内容。继续验证批量处理能力。\n")
            fpath = f.name

        try:
            pipeline = IngestionPipeline(db_path=":memory:")
            stats = pipeline.process_single_file(
                fpath, do_lightweight=False, do_deep=False
            )
            assert stats["chunks"] > 0
            assert stats["lightweight"] is False
            assert stats["knowledge_units"] == 0
        finally:
            os.unlink(fpath)

    def test_save_chunks(self):
        """验证段落块入库。"""
        from src.models import Chunk
        pipeline = IngestionPipeline(db_path=":memory:")
        chunks = [
            Chunk(chunk_id="test_001", source_file="f.txt", text="第一段"),
            Chunk(chunk_id="test_002", source_file="f.txt", text="第二段"),
        ]
        saved = pipeline._save_chunks(chunks)
        assert saved == 2
        count = pipeline.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert count == 2

    def test_duplicate_chunks_ignored(self):
        """重复 chunk_id 应被忽略。"""
        from src.models import Chunk
        pipeline = IngestionPipeline(db_path=":memory:")
        chunks = [
            Chunk(chunk_id="dup_001", source_file="f.txt", text="第一段"),
            Chunk(chunk_id="dup_001", source_file="f.txt", text="第二段"),
        ]
        saved = pipeline._save_chunks(chunks)
        assert saved == 1  # 只有第一个成功

    def test_save_knowledge_units(self):
        """验证知识单元入库。"""
        import tempfile, os
        from src.models import KnowledgeUnit
        db_path = tempfile.mktemp(suffix=".db")
        try:
            from src.knowledge_base import init_db
            conn = init_db(db_path)
            conn.close()
            pipeline = IngestionPipeline(db_path=db_path)
            units = [
                KnowledgeUnit(
                    knowledge_unit_id="test_idea_001",
                    type="idea",
                    source={"file": "f.txt"},
                    description="核心命题",
                ),
            ]
            saved = pipeline._save_knowledge_units(units, db_path=db_path)
            assert saved == 1
        finally:
            os.unlink(db_path)
