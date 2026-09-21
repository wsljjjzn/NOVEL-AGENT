"""
analysis.lightweight — 第二层：轻量分析（V4 Flash）。
对全量文献做快速分类、标签、质量判断、情感基调。
"""

import json
from typing import Optional
from src.utils.llm_client import LLMClient
from src.utils.logger import logger
from src.utils.json_utils import safe_json_parse
from src.models import Chunk
from .models import LightweightAnalysis
from .prompts import LIGHTWEIGHT_ANALYSIS_SYSTEM


class LightweightAnalyzer:
    """轻量分析器 — 对每个素材做一次 Flash 调用。"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.system_prompt = LIGHTWEIGHT_ANALYSIS_SYSTEM

    def analyze_chunk(self, chunk: Chunk) -> LightweightAnalysis:
        """分析单个段落块（用于快速采样）。"""
        text = chunk.text[:2000]  # 限制输入长度
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"请分析以下文本：\n\n{text}"},
        ]
        try:
            response = self.llm.chat(messages, model_tier="flash", temperature=0.3)
            return self._parse(response)
        except Exception as e:
            logger.warning(f"轻量分析失败 [{chunk.chunk_id}]: {e}")
            return LightweightAnalysis(summary=f"分析失败: {e}")

    def analyze_text(self, text: str, sample_id: str = "") -> LightweightAnalysis:
        """分析任意文本片段。"""
        text = text[:2000]
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"请分析以下文本：\n\n{text}"},
        ]
        try:
            response = self.llm.chat(messages, model_tier="flash", temperature=0.3)
            return self._parse(response)
        except Exception as e:
            logger.warning(f"轻量分析失败 [{sample_id}]: {e}")
            return LightweightAnalysis(summary=f"分析失败: {e}")

    def _parse(self, response: str) -> LightweightAnalysis:
        """解析 JSON 响应。"""
        data = safe_json_parse(response)
        if data is None:
            logger.warning(f"JSON 解析失败，使用默认值")
            return LightweightAnalysis(summary=response[:200])

        try:
            return LightweightAnalysis(
                category=data.get("category", "混合"),
                tags=data.get("tags", []),
                quality=data.get("quality", "完整可读"),
                sentiment=data.get("sentiment", "中立"),
                summary=data.get("summary", ""),
            )
        except Exception as e:
            logger.warning(f"字段解析失败: {e}")
            return LightweightAnalysis(summary=response[:200])
