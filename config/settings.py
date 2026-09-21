"""
配置加载器 — 从 config.yaml 读取配置，支持环境变量覆盖。
"""

import os
from pathlib import Path
from typing import Literal, Optional
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings
import yaml


class LLMConfig(BaseSettings):
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.7
    rpm_limit: int = 50
    # P0-1：请求硬化参数
    timeout_seconds: int = 60
    max_retries: int = 3
    retry_base_delay: float = 1.0


class EmbeddingConfig(BaseSettings):
    model: str = "BGE-M3"
    device: str = "cuda"
    batch_size: int = 32
    max_seq_length: int = 8192


class VectorStoreConfig(BaseSettings):
    type: str = "chromadb"
    persist_directory: str = "data/embeddings"
    collection_name: str = "writing_knowledge"


class PreprocessingConfig(BaseSettings):
    chunk_size: int = 512
    chunk_overlap: int = 64
    min_chunk_chars: int = 50
    encoding: str = "utf-8"
    max_file_size_mb: int = 100


class WritingConfig(BaseSettings):
    max_sections: int = 10
    min_section_words: int = 200
    default_temperature: float = 0.7
    outline_model: Literal["flash", "pro"] = "flash"
    writing_model: Literal["flash", "pro"] = "pro"
    retrieval_top_k: int = 10
    rerank_top_k: int = 5


class ReviewConfig(BaseSettings):
    parallel_agents: bool = True
    auto_fix_level1: bool = True
    auto_fix_level2: bool = False
    agents: list[str] = ["thought", "structure", "narrative", "language", "fact_check", "proofread"]


class BudgetConfig(BaseSettings):
    """P0-1：成本护栏。max_cny_per_session<=0 表示不设硬闸。"""
    max_cny_per_session: float = 0.0
    usage_db: str = "data/knowledge/llm_usage.db"


class AppConfig(BaseSettings):
    """全局配置，从 config.yaml 加载，支持环境变量覆盖。"""

    llm: dict[str, LLMConfig] = {}
    embedding: EmbeddingConfig = EmbeddingConfig()
    vector_store: VectorStoreConfig = VectorStoreConfig()
    preprocessing: PreprocessingConfig = PreprocessingConfig()
    writing: WritingConfig = WritingConfig()
    review: ReviewConfig = ReviewConfig()
    budget: BudgetConfig = BudgetConfig()
    database: dict = {"path": "data/knowledge/writing_expert_new.db"}
    project_root: str = ""

    model_config = ConfigDict(extra="allow")

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "AppConfig":
        """从 YAML 文件加载配置，合并环境变量。"""
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "config", "config.yaml"
            )

        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        # 加载 .env 文件
        from dotenv import load_dotenv
        env_path = os.path.join(os.path.dirname(config_path), os.pardir, ".env")
        load_dotenv(os.path.abspath(env_path))

        # 解析 LLM 配置
        llm_configs = {}
        for name, cfg in raw.get("llm", {}).items():
            api_key = os.getenv("DEEPSEEK_API_KEY", cfg.get("api_key", ""))
            llm_configs[name] = LLMConfig(
                api_key=api_key,
                base_url=cfg.get("base_url", "https://api.deepseek.com/v1"),
                model=cfg.get("model", "deepseek-chat"),
                max_tokens=cfg.get("max_tokens", 4096),
                temperature=cfg.get("temperature", 0.7),
                rpm_limit=cfg.get("rpm_limit", 50),
                timeout_seconds=cfg.get("timeout_seconds", 60),
                max_retries=cfg.get("max_retries", 3),
                retry_base_delay=cfg.get("retry_base_delay", 1.0),
            )

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        return cls(
            llm=llm_configs,
            embedding=EmbeddingConfig(**raw.get("embedding", {})),
            vector_store=VectorStoreConfig(**raw.get("vector_store", {})),
            preprocessing=PreprocessingConfig(**raw.get("preprocessing", {})),
            writing=WritingConfig(**raw.get("writing", {})),
            review=ReviewConfig(**raw.get("review", {})),
            budget=BudgetConfig(**raw.get("budget", {})),
            database=raw.get("database", {"path": "data/knowledge/writing_expert_new.db"}),
            project_root=project_root,
        )


# 全局单例
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = AppConfig.load()
    return _config
