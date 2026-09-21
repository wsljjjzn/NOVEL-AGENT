"""
writing_engine.requirement_agent — 需求解析 Agent。
"""

import json
from typing import Optional

import json
from src.utils.llm_client import LLMClient
from src.utils.logger import logger
from src.utils.json_utils import safe_json_parse, extract_json
from src.models import WritingRequest, RequiredElement
from .prompts import REQUIREMENT_PARSER_SYSTEM


def _ensure_list(val):
    """确保值是列表。"""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return [val] if val.strip() else []
    return []


def _int_or_default(val, default=2000):
    """将值转为 int，失败返回默认值。"""
    if val is None:
        return default
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        try:
            return int(val)
        except (ValueError, TypeError):
            # 从字符串中提取数字，如 "约800字" -> 800
            import re
            nums = re.findall(r'\d+', val)
            return int(nums[0]) if nums else default
    return default


class RequirementAgent:
    """将用户口语化需求解析为结构化 WritingRequest。"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.system_prompt = REQUIREMENT_PARSER_SYSTEM

    def parse(self, user_input: str, model_tier: str = "flash") -> WritingRequest:
        """解析用户需求。

        Args:
            user_input: 用户原始输入
            model_tier: 使用的模型层级

        Returns:
            结构化的 WritingRequest
        """
        logger.info(f"解析需求: {user_input[:100]}...")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"请分析以下写作需求：\n\n{user_input}"},
        ]

        response = self.llm.chat(messages, model_tier=model_tier, temperature=0.3)
        parsed = self._parse_response(response, user_input)
        return parsed

    def _parse_response(self, response: str, raw_input: str) -> WritingRequest:
        """解析 LLM 返回的 JSON。"""
        try:
            data = safe_json_parse(response)
            if data is None:
                raise json.JSONDecodeError("无法解析", response, 0)
            elements = [
                RequiredElement(description=e) if isinstance(e, str) else RequiredElement(**e)
                for e in data.get("required_elements", [])
            ]
            return WritingRequest(
                topic=data.get("topic") or "",
                style=data.get("style") or "",
                word_count=_int_or_default(data.get("word_count"), 2000),
                required_elements=elements,
                audience=data.get("audience") or "",
                tone_override=data.get("tone_override") or "",
                forbidden=_ensure_list(data.get("forbidden")),
                reference_materials=_ensure_list(data.get("reference_materials")),
                raw_input=raw_input,
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"JSON 解析失败 ({e})，使用默认值")
            return WritingRequest(
                topic=raw_input[:100],
                raw_input=raw_input,
            )
