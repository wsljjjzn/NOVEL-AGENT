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
