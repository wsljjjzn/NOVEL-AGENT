"""
writing_engine.outline_agent — 大纲生成 Agent。
"""

import json
from typing import Optional

from src.utils.llm_client import LLMClient
from src.utils.logger import logger
from src.utils.json_utils import safe_json_parse, extract_json
from src.models import WritingRequest, Outline, SectionOutline
from .prompts import OUTLINE_GENERATOR_SYSTEM, THOUGHT_STRUCTURE_SYSTEM


def _ensure_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return [val] if val.strip() else []
    return []


def _extract_json(text: str) -> str:
    """从文本中提取 JSON（去掉 markdown 代码块等包裹）。"""
    import re
    # 去掉 ```json ... ``` 包裹
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text)
    return text


class OutlineAgent:
    """生成结构化文章大纲。"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def generate(self, request: WritingRequest, model_tier: str = "flash") -> Outline:
        """生成大纲。

        Args:
            request: 已解析的写作需求
            model_tier: 使用的模型层级

        Returns:
            Outline 对象
        """
        logger.info(f"生成大纲: topic={request.topic}")

        # 先做思想定位和结构推荐
        thought_prompt = self._build_thought_prompt(request)
        thought_response = self.llm.chat(
            [{"role": "system", "content": THOUGHT_STRUCTURE_SYSTEM},
             {"role": "user", "content": thought_prompt}],
            model_tier=model_tier,
            temperature=0.5,
        )
        logger.debug(f"思想定位结果: {thought_response[:200]}...")

        # 生成大纲
        outline_prompt = self._build_outline_prompt(request, thought_response)
        response = self.llm.chat(
            [{"role": "system", "content": OUTLINE_GENERATOR_SYSTEM},
             {"role": "user", "content": outline_prompt}],
            model_tier=model_tier,
            temperature=0.5,
        )

        outline = self._parse_response(response, request)
        return outline

    def _build_thought_prompt(self, request: WritingRequest) -> str:
        return (
            f"主题：{request.topic}\n"
            f"风格：{request.style}\n"
            f"目标读者：{request.audience}\n"
            f"请分析可能的思想立场和推荐结构模式。"
        )

    def _build_outline_prompt(self, request: WritingRequest, thought: str) -> str:
        return (
            f"写作需求：\n"
            f"- 主题：{request.topic}\n"
            f"- 风格：{request.style}\n"
            f"- 字数：{request.word_count}\n"
            f"- 要素：{[e.description for e in request.required_elements]}\n"
            f"- 目标读者：{request.audience}\n"
            f"- 禁止项：{request.forbidden}\n\n"
            f"思想定位与结构参考：\n{thought}\n\n"
            f"请生成结构化大纲（JSON 格式）。"
        )

    def _parse_response(self, response: str, request: WritingRequest) -> Outline:
        try:
            data = safe_json_parse(response)
            if data is None:
                raise json.JSONDecodeError("parse failed", response, 0)
            # 兼容两种命名方式
            sections_raw = _ensure_list(data.get("sections") or data.get("chapters") or [])
            sections = [
                SectionOutline(
                    section_id=i + 1,
                    title=s.get("title") or "",
                    core_argument=(s.get("core_argument") or s.get("coreThesis") or s.get("core_argument_cn") or ""),
                    estimated_words=s.get("estimated_words") or s.get("estimatedWords") or 0,
                    retrieval_queries=_ensure_list(s.get("retrieval_queries") or s.get("keywords") or s.get("searchDirections") or []),
                    notes=_ensure_list(s.get("notes") or s.get("cautions") or []),
                )
                for i, s in enumerate(sections_raw)
            ]
            return Outline(
                title=data.get("title") or data.get("total_title") or request.topic,
                sections=sections,
                overall_notes=_ensure_list(data.get("overall_notes") or []),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"大纲 JSON 解析失败 ({e})")
            return Outline(
                title=request.topic,
                sections=[
                    SectionOutline(section_id=1, title=request.topic, core_argument="")
                ],
            )
