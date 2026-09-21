"""
analysis.deep — 第三层：深度分析（V4 Pro）。
对精选文献做四层分析：思想层、结构层、叙事层、语言层。
"""

import json
from typing import Optional
from src.utils.llm_client import LLMClient
from src.utils.logger import logger
from src.utils.json_utils import safe_json_parse
from src.models import Chunk, KnowledgeUnit
from .models import (
    ThoughtAnalysis, StructureAnalysis,
    NarrativeAnalysis, LanguageAnalysis, DeepAnalysis,
)
from .prompts import (
    THOUGHT_ANALYSIS_SYSTEM, STRUCTURE_ANALYSIS_SYSTEM,
    NARRATIVE_ANALYSIS_SYSTEM, LANGUAGE_ANALYSIS_SYSTEM,
    KNOWLEDGE_UNIT_SYNTHESIS_SYSTEM,
)


class DeepAnalyzer:
    """深度分析器 — 对精选素材做四层分析（每次调用聚焦单一维度）。"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self._system_prompts = {
            "thought": THOUGHT_ANALYSIS_SYSTEM,
            "structure": STRUCTURE_ANALYSIS_SYSTEM,
            "narrative": NARRATIVE_ANALYSIS_SYSTEM,
            "language": LANGUAGE_ANALYSIS_SYSTEM,
        }

    def analyze_all(self, text: str, source_id: str = "",
                    model_tier: str = "pro") -> DeepAnalysis:
        """对素材做全部四层分析（四次独立调用）。

        Args:
            text: 素材文本（建议 2000-8000 tokens）
            source_id: 素材 ID（日志用）
            model_tier: 模型层级 "flash" 或 "pro"（默认 pro）

        Returns:
            DeepAnalysis 聚合结果
        """
        result = DeepAnalysis()

        for layer, system_prompt in self._system_prompts.items():
            logger.info(f"深度分析 - {layer}层 [{source_id}] ({model_tier})")
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请分析以下文本：\n\n{text[:4000]}"},
                ]
                response = self.llm.chat(messages, model_tier=model_tier, temperature=0.4)
                parsed = self._parse_layer(layer, response)
                setattr(result, layer, parsed)
            except Exception as e:
                logger.warning(f"{layer}层分析失败 [{source_id}]: {e}")

        return result

    def analyze_layer(self, layer: str, text: str,
                      source_id: str = "",
                      model_tier: str = "pro") -> Optional[object]:
        """只分析单一维度（按素材类型分配权重时用）。

        Args:
            layer: thought / structure / narrative / language
            text: 素材文本
            source_id: 素材 ID
            model_tier: 模型层级 "flash" 或 "pro"
        """
        system_prompt = self._system_prompts.get(layer)
        if not system_prompt:
            raise ValueError(f"未知分析层: {layer}")

        logger.info(f"深度分析(单层) - {layer}层 [{source_id}] ({model_tier})")
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析以下文本：\n\n{text[:4000]}"},
            ]
            response = self.llm.chat(messages, model_tier=model_tier, temperature=0.4)
            return self._parse_layer(layer, response)
        except Exception as e:
            logger.warning(f"{layer}层分析失败 [{source_id}]: {e}")
            return None

    def _coerce_types(self, layer: str, data) -> dict:
        """容错：将 Flash 的非标输出转为 Pydantic 期望的类型。"""
        # 情况1：safe_json_parse 返回了 list
        if isinstance(data, list):
            data = data[0] if data else {}
        # 情况2：不是 dict 就没法修
        if not isinstance(data, dict):
            return {}

        import json as _json

        # === 所有可能为 list -> str 的字段 ===
        list_to_str_fields = [
            "core_proposition", "subverted_beliefs",
            "notable_technique", "rhetorical_devices",
        ]
        for f in list_to_str_fields:
            if isinstance(data.get(f), list):
                data[f] = "；".join(str(v) for v in data[f])

        # === 所有可能为 dict -> str 的字段 ===
        dict_to_str_fields = [
            "character_portrayal", "plot_design", "emotional_rhythm",
            "pov_and_distance", "sentence_length", "sentence_diversity",
            "modifier_density", "tone_and_distance", "overall_style",
            "value_premise", "intellectual_lineage", "applicability_boundary",
            "structure_type", "info_release_rhythm", "climax_position",
        ]
        for f in dict_to_str_fields:
            if isinstance(data.get(f), dict):
                data[f] = _json.dumps(data[f], ensure_ascii=False)

        # === section_functions 特殊处理 ===
        sf = data.get("section_functions")
        if sf is not None and not isinstance(sf, list):
            if isinstance(sf, dict):
                data["section_functions"] = [{"role": f"{k}: {v}"} for k, v in sf.items()]
            else:
                data["section_functions"] = [{"role": str(sf)}]
        elif isinstance(sf, list):
            data["section_functions"] = [
                {"role": v} if isinstance(v, str) else v for v in sf
            ]

        # === subverted_beliefs: str -> list ===
        if isinstance(data.get("subverted_beliefs"), str):
            data["subverted_beliefs"] = [data["subverted_beliefs"]]

        # === rhetorical_devices: dict/str -> list（language 层） ===
        if layer == "language":
            rd = data.get("rhetorical_devices")
            if isinstance(rd, dict):
                data["rhetorical_devices"] = [f"{k}: {v}" for k, v in rd.items()]
            elif isinstance(rd, str):
                data["rhetorical_devices"] = [rd]

        return data

    def _parse_layer(self, layer: str, response: str) -> object:
        """解析单层分析 JSON 为对应的模型。"""
        data = safe_json_parse(response)
        if data is None:
            logger.warning(f"{layer} 解析失败，使用默认值")
            model_map = {
                "thought": ThoughtAnalysis,
                "structure": StructureAnalysis,
                "narrative": NarrativeAnalysis,
                "language": LanguageAnalysis,
            }
            return model_map.get(layer, dict)()

        # 类型容错：Flash 输出的字段类型可能不符合 Pydantic schema
        data = self._coerce_types(layer, data)

        try:
            model_map = {
                "thought": ThoughtAnalysis,
                "structure": StructureAnalysis,
                "narrative": NarrativeAnalysis,
                "language": LanguageAnalysis,
            }
            model_class = model_map.get(layer)
            if model_class:
                return model_class(**data)
            return data
        except Exception as e:
            logger.warning(f"{layer} 字段解析失败: {e}")
            model_map = {
                "thought": ThoughtAnalysis,
                "structure": StructureAnalysis,
                "narrative": NarrativeAnalysis,
                "language": LanguageAnalysis,
            }
            return model_map.get(layer, dict)()

    def synthesize_knowledge_units(
        self, deep_analysis: DeepAnalysis, source_file: str = ""
    ) -> list[KnowledgeUnit]:
        """从深度分析结果中合成可复用的知识单元。

        Args:
            deep_analysis: 四层分析结果
            source_file: 来源文件名

        Returns:
            KnowledgeUnit 列表（每层产出 1-3 个）
        """
        units = []

        # 将各层分析转为结构化知识单元
        layer_map = [
            ("idea", "thought", deep_analysis.thought,
             ["思想", "核心命题", "价值观"]),
            ("structure", "structure", deep_analysis.structure,
             ["结构", "信息组织", "节奏"]),
            ("technique", "narrative", deep_analysis.narrative,
             ["叙事", "人物", "情感", "悬念"]),
            ("language", "language", deep_analysis.language,
             ["语言", "风格", "修辞"]),
        ]

        for unit_type, layer_name, analysis_obj, default_tags in layer_map:
            analysis_dict = analysis_obj.model_dump() if hasattr(analysis_obj, 'model_dump') else {}
            # 只提取有内容的字段作为知识单元
            for key, value in analysis_dict.items():
                if isinstance(value, str) and len(value) > 10:
                    unit = KnowledgeUnit(
                        knowledge_unit_id=f"{source_file}_{layer_name}_{key}",
                        type=unit_type,
                        category=key,
                        source={"file": source_file, "field": key},
                        description=value[:500],
                        tags=default_tags + [key],
                    )
                    units.append(unit)
                    break  # 每层只取最有价值的一个

        return units
