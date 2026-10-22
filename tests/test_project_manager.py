"""项目存档与路径边界测试。"""

import json

import pytest

from src.novel.project_manager import NovelProject
from src.novel.service import NovelService


@pytest.mark.parametrize("name", ["", " ", ".", "..", "../outside", "nested/project"])
def test_project_name_cannot_escape_base_dir(tmp_path, name):
    with pytest.raises(ValueError):
        NovelProject(name, str(tmp_path))


def test_service_rejects_invalid_project_name(tmp_path):
    service = NovelService(str(tmp_path))
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("必须保留", encoding="utf-8")

    result = service.delete("../outside.txt")

    assert result.ok is False
    assert "不合法" in result.title
    assert outside.read_text(encoding="utf-8") == "必须保留"


def test_project_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    project = NovelProject("测试项目", str(tmp_path))
    project.add_chapter(1, "开端", "正文")
    project.save()

    target = tmp_path / "测试项目" / "project.json"
    assert json.loads(target.read_text(encoding="utf-8"))["chapters"] == {"1": "正文"}
    assert not list(target.parent.glob("project.json.*.tmp"))


def test_project_style_guide_lifecycle(tmp_path):
    project = NovelProject("风格测试", str(tmp_path))
    project.save()
    assert project.get_style_guide() is None
    assert project.get_style_context() == ""

    guide_data = {
        "style_name": "硬汉写实",
        "tone": "冷峻克制",
        "rules": ["多用短句，强化动词递进", "每段不超过三句话"],
        "forbidden_words": ["只见", "宛如"],
        "few_shot_examples": [
            {"type": "动作冲突", "text": "刀锋划破夜色，他没有迟疑，顺势侧滑一尺。"}
        ],
    }

    project.set_style_guide(guide_data)
    assert project.get_style_guide()["style_name"] == "硬汉写实"

    # 验证磁盘持久化
    style_file = tmp_path / "风格测试" / "style_guide.json"
    assert style_file.exists()
    assert json.loads(style_file.read_text("utf-8"))["tone"] == "冷峻克制"

    # 验证上下文 prompt 组装（零 LLM）
    context = project.get_style_context()
    assert "## 行文风格与范文指引" in context
    assert "- 参考风格: 硬汉写实" in context
    assert "- 语言基调: 冷峻克制" in context
    assert "多用短句，强化动词递进" in context
    assert "严禁出现以下词汇或套路：只见, 宛如" in context
    assert "【示例 1 · 动作冲突】" in context
    assert "刀锋划破夜色" in context

    # 重新加载项目
    loaded = NovelProject.load(str(tmp_path), "风格测试")
    assert loaded.get_style_guide()["style_name"] == "硬汉写实"
    assert "硬汉写实" in loaded.get_style_context()

    # 清空风格指南
    loaded.clear_style_guide()
    assert loaded.get_style_guide() is None
    assert not style_file.exists()
    assert loaded.get_style_context() == ""


def test_service_style_guide_management(tmp_path):
    service = NovelService(str(tmp_path))
    create_res = service.create("服务风格测试")
    assert create_res.ok is True

    # 初始状态未配置
    get_res = service.get_style_guide("服务风格测试")
    assert get_res.ok is True
    assert get_res.data is None

    # 配置风格
    guide = {
        "template_name": "华丽仙侠体",
        "writing_rules": ["四字成语对仗", "大量意象白描"],
        "forbidden_patterns": ["现代网络词汇"],
        "representative_samples": [
            {"type": "法宝祭出", "text_snippet": "金光自袖底暴涨，如龙蛇起陆。"}
        ],
    }
    set_res = service.set_style_guide("服务风格测试", guide)
    assert set_res.ok is True
    assert "华丽仙侠体" in set_res.title

    # 读取验证
    get_res2 = service.get_style_guide("服务风格测试")
    assert get_res2.ok is True
    assert get_res2.data["template_name"] == "华丽仙侠体"
    assert "规则数: 2" in get_res2.lines

    # 检查 chapter_writer 的 prompt 是否注入
    bundle = service.load("服务风格测试")
    prompt = bundle.writer._build_prompt(1, "初入仙门", 2000)
    assert "## 行文风格与范文指引" in prompt
    assert "- 参考风格: 华丽仙侠体" in prompt
    assert "四字成语对仗" in prompt
    assert "严禁出现以下词汇或套路：现代网络词汇" in prompt
    assert "金光自袖底暴涨" in prompt

    # 清空
    clear_res = service.clear_style_guide("服务风格测试")
    assert clear_res.ok is True
    bundle2 = service.load("服务风格测试")
    prompt2 = bundle2.writer._build_prompt(1, "初入仙门", 2000)
    assert "## 行文风格与范文指引" not in prompt2
