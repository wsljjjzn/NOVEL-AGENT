"""
utils.json_utils — JSON 解析工具。

核心问题：LLM 经常在 JSON 外面包 markdown 代码块（```json ... ```），
导致 json.loads() 失败。这些工具函数负责去掉包裹再解析。
"""

import re
import json
from typing import Any, Optional


def extract_json(text: str) -> str:
    """去掉 markdown 代码块包裹后返回纯 JSON 字符串。

    支持：
    - ```json { ... } ```
    - ``` { ... } ```
    - 纯 { ... }（无变化）
    - 前后有解释文字时也尝试提取
    """
    text = text.strip()

    # 去掉 ```json ... ``` 包裹
    text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n?\s*```$', '', text)

    # 如果去掉包裹后还有多余文字（在 JSON 之前或之后），尝试提取 {} 部分
    text = text.strip()

    return text


def safe_json_parse(text: str, default: Any = None) -> Optional[Any]:
    """extract_json + json.loads，失败返回 default。

    Args:
        text: 可能带 markdown 包裹的 JSON 文本
        default: 解析失败时返回的默认值

    Returns:
        解析后的 Python 对象，或 default
    """
    try:
        return json.loads(extract_json(text))
    except (json.JSONDecodeError, ValueError):
        return default


def find_json_in_text(text: str) -> Optional[dict]:
    """在任意文本中寻找第一个 JSON 对象 {} 并解析。

    用于 LLM 返回了自然语言 + JSON 混合的情况。
    优先匹配 markdown 代码块内的 JSON。
    """
    # 先尝试提取 markdown 代码块内的 JSON
    md_match = re.search(r'```(?:json)?\s*\n?(.+?)\n?\s*```', text, re.DOTALL | re.IGNORECASE)
    if md_match:
        try:
            result = json.loads(md_match.group(1))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # 找第一个 { 到匹配的 }
    brace_depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if start == -1:
                start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and start != -1:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = -1

    # 最后尝试：找最后一个 { 到文本末尾（处理截断情况）
    if start != -1:
        # 括号未闭合，从 start 截取到末尾尝试解析
        partial = text[start:]
        try:
            return json.loads(partial)
        except json.JSONDecodeError:
            pass
        # 再尝试补全一个 }
        try:
            return json.loads(partial + '}')
        except json.JSONDecodeError:
            pass

    return None
