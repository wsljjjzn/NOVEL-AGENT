"""
analysis — 板块一：文献学习系统。

三层分析管线：
- 第一层：预处理 (src/preprocessing/)
- 第二层：轻量分析 (LightweightAnalyzer, V4 Flash)
- 第三层：深度分析 (DeepAnalyzer, V4 Pro)
- 入库流水线 (IngestionPipeline)
"""

from .lightweight import LightweightAnalyzer, LightweightAnalysis
from .deep import DeepAnalyzer, DeepAnalysis
from .ingestion import IngestionPipeline
from .models import (
    LightweightAnalysis as LWModel,
    ThoughtAnalysis, StructureAnalysis,
    NarrativeAnalysis, LanguageAnalysis, DeepAnalysis as DeepModel,
)

__all__ = [
    "LightweightAnalyzer", "LightweightAnalysis",
    "DeepAnalyzer", "DeepAnalysis",
    "IngestionPipeline",
    "LWModel",
    "ThoughtAnalysis", "StructureAnalysis",
    "NarrativeAnalysis", "LanguageAnalysis", "DeepModel",
]
