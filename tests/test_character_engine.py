"""tests.test_character_engine — 角色分析与角色库更新（用假 LLM，不联网、不花钱）。

覆盖三处"静默失败"的回归：JSON 解析失败、模型不返回角色、首次写作角色库为空——
三者过去都表现为日志里的"0 个角色更新"，排查方向完全不同，现在必须有可区分的信号；
另外首次写作时 prompt 必须显式引导模型按"新角色"输出。
"""
import json
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.novel.character_engine import CharacterEngine  # noqa: E402


NEW_CHARACTER_JSON = json.dumps({
    "characters": [
        {"name": "林晚", "is_new": True, "role": "主角",
         "personality": {"勇敢": 7, "敏感": 6},
         "speaking_style": "简短",
         "mood": "戒备",
         "key_actions": ["推开仓库的门"],
         "summary": "初次登场"},
    ]
}, ensure_ascii=False)


class FakeLLM:
    """把预置字符串当响应返回，并记录发给模型的 prompt。"""

    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def chat(self, messages, model_tier: str = "flash", **kwargs) -> str:
        self.prompts.append(messages[-1]["content"])
        return self.response


@contextmanager
def capture_logs(level: str = "WARNING"):
    """捕获 loguru 日志（项目用 loguru，不走标准 logging，caplog 抓不到）。"""
    from loguru import logger as loguru_logger
    messages: list[str] = []
    sink_id = loguru_logger.add(lambda m: messages.append(m.record["message"]), level=level)
    try:
        yield messages
    finally:
        loguru_logger.remove(sink_id)


class TestParseAnalysis:
    def test_invalid_json_returns_empty_and_warns(self):
        engine = CharacterEngine(llm_client=FakeLLM("这不是 JSON"))
        with capture_logs("WARNING") as logs:
            updated = engine._parse_analysis("这不是 JSON", 1)
        assert updated == []
        assert any("无法解析" in m for m in logs)

    def test_empty_characters_list_is_logged(self):
        engine = CharacterEngine(llm_client=FakeLLM('{"characters": []}'))
        with capture_logs("INFO") as logs:
            updated = engine._parse_analysis('{"characters": []}', 2)
        assert updated == []
        assert any("未返回任何角色" in m for m in logs)

    def test_characters_not_a_list_is_ignored(self):
        engine = CharacterEngine(llm_client=FakeLLM('{"characters": {"a": 1}}'))
        with capture_logs("WARNING") as logs:
            updated = engine._parse_analysis('{"characters": {"a": 1}}', 3)
        assert updated == []
        assert any("不是数组" in m for m in logs)

    def test_new_character_is_created(self):
        engine = CharacterEngine(llm_client=FakeLLM(NEW_CHARACTER_JSON))
        updated = engine._parse_analysis(NEW_CHARACTER_JSON, 1)
        assert [c.name for c in updated] == ["林晚"]
        profile = engine.get_character("林晚")
        assert profile is not None
        assert profile.personality.get("勇敢") == 7
        assert profile.current_chapter == 1


class TestAnalyzeChapterPrompt:
    def test_empty_library_asks_for_new_characters(self):
        llm = FakeLLM(NEW_CHARACTER_JSON)
        engine = CharacterEngine(llm_client=llm)
        engine.analyze_chapter(1, "第一章正文", existing_names=[])
        assert "新角色" in llm.prompts[0]

    def test_existing_library_lists_names_without_new_hint(self):
        llm = FakeLLM(NEW_CHARACTER_JSON)
        engine = CharacterEngine(llm_client=llm)
        engine.analyze_chapter(2, "第二章正文", existing_names=["林晚"])
        assert "林晚" in llm.prompts[0]
        assert "新角色" not in llm.prompts[0]
