"""测试：配置系统。"""

import os
import tempfile
import yaml

from config.settings import AppConfig


class TestAppConfig:
    def test_load_defaults(self):
        """从默认路径加载配置。"""
        cfg = AppConfig.load()
        assert cfg.project_root.endswith("novel")
        assert "deepseek_v4_flash" in cfg.llm
        assert "deepseek_v4_pro" in cfg.llm
        assert cfg.writing.outline_model == "flash"
        assert cfg.writing.writing_model == "pro"

    def test_load_with_custom_path(self):
        """从自定义路径加载配置。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml",
                                         delete=False, encoding="utf-8") as f:
            yaml.dump({
                "llm": {
                    "deepseek_v4_flash": {
                        "model": "test-flash",
                        "max_tokens": 2048,
                    }
                },
                "writing": {
                    "outline_model": "pro",
                },
            }, f)
            f_path = f.name

        try:
            cfg = AppConfig.load(f_path)
            assert cfg.llm["deepseek_v4_flash"].model == "test-flash"
            assert cfg.llm["deepseek_v4_flash"].max_tokens == 2048
            assert cfg.writing.outline_model == "pro"
        finally:
            os.unlink(f_path)


class TestLLMConfig:
    def test_flash_vs_pro_defaults(self):
        """Flash 和 Pro 的默认参数差异。"""
        cfg = AppConfig.load()
        flash = cfg.llm["deepseek_v4_flash"]
        pro = cfg.llm["deepseek_v4_pro"]
        assert flash.max_tokens <= pro.max_tokens  # Pro 应有更大的上下文
        assert flash.rpm_limit >= pro.rpm_limit    # Flash 应有更高 RPM
