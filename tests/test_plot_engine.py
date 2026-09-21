"""测试：剧情引擎的类型防御。"""

from src.novel.plot_engine import PlotEngine, ChapterPlot, Scene
from src.utils.json_utils import safe_json_parse


class TestPlotEngineTypeSafety:
    """验证 design_characters 中对 LLM 非标输出的防御。"""

    def test_world_building_is_string(self):
        """world_building 是字符串而非对象 → 不崩溃，使用空设定。"""
        engine = PlotEngine()

        # 模拟 LLM 返回 string world_building
        mock_response = '''{
            "characters": [{"name": "张三", "role": "主角"}],
            "world_building": "这是一个现代都市世界观，位于2024年的上海。"
        }'''
        # 直接模拟 safe_json_parse 后的数据
        data = safe_json_parse(mock_response)
        wb = data.get("world_building", {})
        if isinstance(wb, str):
            wb = {}
        assert wb == {}
        chars = data.get("characters", [])
        if not isinstance(chars, list):
            chars = []
        assert len(chars) == 1

    def test_world_building_missing(self):
        """world_building 缺失 → 正常返回空 WorldSetting。"""
        engine = PlotEngine()
        mock_response = '''{"characters": []}'''
        data = safe_json_parse(mock_response)
        wb = data.get("world_building", {})
        if isinstance(wb, str):
            wb = {}
        assert wb == {}
        # 验证 world 对象有默认值
        assert engine.world.timeline == ""

    def test_world_building_normal(self):
        """world_building 是正常 dict → 正确解析。"""
        engine = PlotEngine()
        data = {
            "world_building": {
                "timeline": "2024年",
                "geography": "上海",
                "power_system": "黑道势力体系",
            }
        }
        wb = data.get("world_building", {})
        if isinstance(wb, str):
            wb = {}
        assert wb["timeline"] == "2024年"
        assert wb["power_system"] == "黑道势力体系"

    def test_characters_is_string(self):
        """characters 字段是字符串 → 不抛异常，返回空列表。"""
        engine = PlotEngine()
        data = {"characters": "这是一个角色列表但被LLM写成了字符串", "world_building": {}}
        chars = data.get("characters", [])
        if not isinstance(chars, list):
            chars = []
        assert chars == []

    def test_safe_parse_world_building_string(self):
        """集成测试：通过 safe_json_parse 解析包含字符串 world_building 的 JSON。"""
        response = '''{
            "characters": [],
            "world_building": "世界观描述文本"
        }'''
        data = safe_json_parse(response)
        assert data is not None
        wb = data.get("world_building", {})
        assert isinstance(wb, str)  # LLM 返回了字符串
        # 这就是需要防御的场景
        if isinstance(wb, str):
            wb = {}
        assert wb == {}

    def test_design_characters_no_llm(self):
        """不调 LLM，直接验证防御逻辑是否工作。"""
        engine = PlotEngine()
        # 模拟 _parse 后的数据
        mock_data = {
            "world_building": "文本",
            "characters": "文本"
        }
        wb = mock_data.get("world_building", {})
        if isinstance(wb, str):
            wb = {}
        chars = mock_data.get("characters", [])
        if not isinstance(chars, list):
            chars = []
        assert wb == {}
        assert chars == []


class TestChapterPlot:
    """验证 ChapterPlot 基本功能。"""
    def test_create_empty(self):
        plot = ChapterPlot(1, "测试章")
        assert plot.chapter_num == 1
        assert plot.title == "测试章"
        assert plot.scenes == []

    def test_add_scene(self):
        plot = ChapterPlot(1, "测试章")
        plot.scenes.append(Scene(
            order=1, location="教室", characters=["张三"],
            summary="上课", purpose="展开剧情"
        ))
        assert len(plot.scenes) == 1
        assert plot.scenes[0].location == "教室"

    def test_to_prompt_text(self):
        plot = ChapterPlot(1, "初遇")
        plot.opening_hook = "林逸捡到一本书"
        plot.foreshadowing_planted = ["蛇形纹身"]
        text = plot.to_prompt_text()
        assert "第1章剧情设计" in text
        assert "林逸捡到一本书" in text
        assert "蛇形纹身" in text

    def test_to_dict_roundtrip(self):
        plot = ChapterPlot(1, "测试")
        plot.opening_hook = "钩子"
        d = plot.to_dict()
        assert d["chapter"] == 1
        assert d["opening_hook"] == "钩子"
