"""测试：JSON 解析工具。"""

from src.utils.json_utils import extract_json, safe_json_parse, find_json_in_text


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == '{"a": 1}'

    def test_with_code_block(self):
        result = extract_json('```json\n{"a": 1}\n```')
        assert result == '{"a": 1}'

    def test_with_code_block_no_lang(self):
        result = extract_json('```\n{"a": 1}\n```')
        assert result == '{"a": 1}'

    def test_with_extra_whitespace(self):
        result = extract_json('  ```json\n{"a": 1}\n```  ')
        assert result == '{"a": 1}'

    def test_empty_text(self):
        assert extract_json('') == ''

    def test_multiline_json(self):
        text = '''```json
{
  "name": "test",
  "value": 42
}
```'''
        result = extract_json(text)
        assert '"name"' in result
        assert '"value"' in result


class TestSafeJsonParse:
    def test_parse_plain(self):
        result = safe_json_parse('{"a": 1}')
        assert result == {"a": 1}

    def test_parse_wrapped(self):
        result = safe_json_parse('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_parse_invalid(self):
        result = safe_json_parse('not json', default={})
        assert result == {}

    def test_parse_none(self):
        result = safe_json_parse('```\nnull\n```')
        assert result is None

    def test_parse_with_surrounding_text(self):
        text = "Here is the result:\n```json\n{\"key\": \"value\"}\n```\nEnd."
        result = safe_json_parse(text)
        assert result is None  # 不会解析，因为前后有文字
        # 但用 find_json_in_text 可以
        result2 = find_json_in_text(text)
        assert result2 == {"key": "value"}


class TestFindJsonInText:
    def test_text_before_json(self):
        result = find_json_in_text('结果是：{"a": 1}，完毕。')
        assert result == {"a": 1}

    def test_multiple_braces(self):
        text = '{"outer": {"inner": 1}}'
        result = find_json_in_text(text)
        assert result == {"outer": {"inner": 1}}

    def test_no_json(self):
        result = find_json_in_text('纯文本，没有 JSON')
        assert result is None

    def test_wrapped_in_text(self):
        text = """好的，以下是分析结果：
```json
{"score": 8, "summary": "不错"}
```
请查收。"""
        result = find_json_in_text(text)
        assert result is not None
        assert result["score"] == 8
