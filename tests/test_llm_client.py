"""测试：LLMClient 动态模型配置更新。"""

from src.utils.llm_client import LLMClient


class TestLLMClientDynamicConfig:
    """测试 update_tier_config / get_tier_info 动态配置功能。"""

    def test_update_and_get_tier_config(self):
        client = LLMClient()
        # 更新 flash 档配置
        client.update_tier_config(
            "flash",
            api_key="test-key-flash",
            base_url="https://test.flash.com/v1",
            model="test-flash-model",
        )
        # 更新 pro 档配置
        client.update_tier_config(
            "pro",
            api_key="test-key-pro",
            base_url="https://test.pro.com/v1",
            model="test-pro-model",
            temperature=0.5,
            max_tokens=2048,
        )

        # 验证 get_tier_info 返回值
        info_flash = client.get_tier_info("flash")
        assert "test" in info_flash["api_key"]  # 脱敏后仍保留前4字符
        assert "..." in info_flash["api_key"]
        assert info_flash["base_url"] == "https://test.flash.com/v1"
        assert info_flash["model"] == "test-flash-model"
        assert info_flash["temperature"] == 0.7  # 默认值，未覆盖
        assert info_flash["max_tokens"] == 4096  # 默认值，未覆盖

        info_pro = client.get_tier_info("pro")
        assert "test" in info_pro["api_key"]
        assert "..." in info_pro["api_key"]
        assert info_pro["model"] == "test-pro-model"
        assert info_pro["temperature"] == 0.5  # 已覆盖
        assert info_pro["max_tokens"] == 2048  # 已覆盖

    def test_update_clears_client_cache(self):
        client = LLMClient()
        # 先触发一次访问，客户端被缓存
        _ = client.flash  # 此时 flash_cfg 可能为 None，返回 None
        # 设置配置后
        client.update_tier_config(
            "flash",
            api_key="test-key",
            base_url="https://test.com/v1",
            model="test-model",
        )
        # 缓存应已被清除，重新访问返回新配置的客户端
        new_client = client.flash
        assert new_client is not None

    def test_update_invalid_tier(self):
        client = LLMClient()
        result = client.update_tier_config("invalid_tier", api_key="x", base_url="x", model="x")
        assert result is False

    def test_get_tier_info_nonexistent(self):
        client = LLMClient()
        info = client.get_tier_info("nonexistent")
        assert info is None

    def test_api_key_masking(self):
        client = LLMClient()
        client.update_tier_config("flash", api_key="sk-1234567890abcdef", base_url="x", model="x")
        info = client.get_tier_info("flash")
        # 脱敏：显示前4和后4字符，中间用...
        assert "sk-1" in info["api_key"]
        assert "cdef" in info["api_key"]
        assert "..." in info["api_key"]

    def test_multiple_updates_same_tier(self):
        client = LLMClient()
        client.update_tier_config("pro", api_key="key1", base_url="url1", model="model1")
        client.update_tier_config("pro", api_key="key2", base_url="url2", model="model2")
        info = client.get_tier_info("pro")
        assert "key2" in info["api_key"]  # 脱敏后
        assert "..." in info["api_key"]
        assert info["base_url"] == "url2"
        assert info["model"] == "model2"


class TestMissingKeyHandling:
    """Key 未配置时的行为：不抛 401，而是明确说"没配"。"""

    def test_client_is_none_without_key(self, monkeypatch):
        import config.settings as settings
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setattr(settings, "_config", None)
        client = LLMClient()
        # 回归：以前会把字面量 "${DEEPSEEK_API_KEY}" 当 Key 发出去换回一个 401
        assert client.flash is None
        assert client.pro is None
        assert client.get_available_tiers() == []

    def test_chat_raises_clear_error_without_key(self, monkeypatch):
        import pytest
        import config.settings as settings
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setattr(settings, "_config", None)
        client = LLMClient()
        with pytest.raises(RuntimeError) as e:
            client.chat([{"role": "user", "content": "ping"}], model_tier="flash")
        assert "未配置" in str(e.value)

    def test_placeholder_key_is_not_treated_as_configured(self, monkeypatch):
        """哪怕配置里留着 ${VAR} 字面量也视为未配置（settings 层已解析成空串）。"""
        from config.settings import LLMConfig
        client = LLMClient()
        assert client._has_key(LLMConfig(api_key="")) is False
        assert client._has_key(LLMConfig(api_key="   ")) is False
        assert client._has_key(LLMConfig(api_key="\\${DEEPSEEK_API_KEY}")) is False
        assert client._has_key(LLMConfig(api_key="sk-real")) is True


class TestThinkingSwitch:
    """V4 默认开思考，思考**先于**正文吃 max_tokens；思考开着时模型还可能改写成散文。

    根因记录（2026-10-13）：审稿在 flash 档 6 个维度里 4 个失败，实测
    completion 打满 4096 而 content 是空串（全被思考吃掉）。
    处置：**保留思考**，档位 max_tokens 提到 16384，并给结构化调用加
    response_format=json_object（json_mode）——两者都只是"约束/上限"，不牺牲思考。
    """

    def test_thinking_payload_is_an_object_not_a_bool(self):
        from src.utils.llm_client import _thinking_payload
        assert _thinking_payload(False) == {"thinking": {"type": "disabled"}}
        assert _thinking_payload(True) == {"thinking": {"type": "enabled"}}
        # 传布尔 false 会被服务端 422 拒绝（expected struct），形状必须锁死
        assert isinstance(_thinking_payload(False)["thinking"], dict)

    def test_chat_resolves_thinking_from_config_then_override(self, monkeypatch):
        client = LLMClient()
        client.update_tier_config("flash", api_key="sk-test", base_url="https://x/v1",
                                  model="m", thinking=True, rpm_limit=0)
        seen = []

        def spy(self, client_, cfg, model, tier, messages, temperature,
                max_tokens, timeout, thinking=True, json_mode=False):
            seen.append(thinking)
            return "ok"

        monkeypatch.setattr(type(client), "_request", spy)
        client.chat([{"role": "user", "content": "x"}], model_tier="flash")
        client.chat([{"role": "user", "content": "x"}], model_tier="flash", thinking=False)
        assert seen == [True, False], "chat 必须把配置默认值与按次覆盖分别传下去"

    def test_request_payload_shape(self):
        from src.utils.llm_client import _request_payload
        base = dict(model="m", messages=[{"role": "user", "content": "x"}],
                    temperature=0.3, max_tokens=16384, timeout=60)

        plain = _request_payload(**base, thinking=True, json_mode=False)
        assert plain["extra_body"] == {"thinking": {"type": "enabled"}}
        assert "response_format" not in plain, "不需要 JSON 时不要强加约束"

        jsoned = _request_payload(**base, thinking=True, json_mode=True)
        assert jsoned["response_format"] == {"type": "json_object"}
        # 关键：JSON 模式与思考**可以共存**，不要为了 JSON 去关思考
        assert jsoned["extra_body"] == {"thinking": {"type": "enabled"}}

    def test_chat_forwards_json_mode(self, monkeypatch):
        client = LLMClient()
        client.update_tier_config("flash", api_key="sk-test", base_url="https://x/v1",
                                  model="m", rpm_limit=0)
        seen = {}

        def spy(self, client_, cfg, model, tier, messages, temperature,
                max_tokens, timeout, thinking=True, json_mode=False):
            seen["json_mode"] = json_mode
            return "ok"

        monkeypatch.setattr(type(client), "_request", spy)
        client.chat([{"role": "user", "content": "x"}], model_tier="flash", json_mode=True)
        assert seen["json_mode"] is True

    def test_tier_info_exposes_thinking(self):
        from config.settings import LLMConfig
        client = LLMClient()
        client.update_tier_config("flash", api_key="sk-test", base_url="https://x/v1",
                                  model="m", thinking=False)
        assert client.get_tier_info("flash")["thinking"] is False
        assert LLMConfig().thinking is True   # 缺省保持现状（开），不悄悄改行为
