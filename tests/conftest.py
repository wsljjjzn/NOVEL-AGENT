"""pytest 配置：sys.path + 两条测试环境的硬保证。

1. **测试绝不产生真实 API 调用**：本机可能配了真实 Key（项目根 .env），
   跑一次测试不该花钱。真正的 HTTP 调用都经过 LLMClient._request，这里直接拦掉；
   需要 LLM 的测试应当注入替身（见 tests/test_novel_service.py 的 RoutingFakeLLM）。
2. **测试不受开发者本地 .env 影响**：settings.AppConfig.load() 会 load_dotenv(项目根/.env)，
   于是"没配 Key"的用例会因本地 .env 而意外变成"已配置"。这里把 load_dotenv 变成空操作，
   让用例结果与开发者本机配置无关。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolate_llm_environment(monkeypatch):
    """每个用例都在"无本地 .env、无真实网络调用"的环境里跑。"""
    # 2) 屏蔽真实 .env（密钥仍可通过 shell 环境变量显式提供）
    try:
        import dotenv
        monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    except ImportError:
        pass

    # 1) 兜底拦掉真实调用：_request 是唯一出口
    from src.utils import llm_client

    def _blocked(self, *args, **kwargs):
        raise RuntimeError(
            "测试环境禁止真实 LLM 调用。需要模型输出的用例请注入假 LLM"
            "（参考 tests/test_novel_service.py 的 RoutingFakeLLM）。"
        )

    monkeypatch.setattr(llm_client.LLMClient, "_request", _blocked, raising=False)

    # 配置单例清零，避免上一个用例的缓存串味
    import config.settings as settings
    monkeypatch.setattr(settings, "_config", None)
    yield
    settings._config = None
