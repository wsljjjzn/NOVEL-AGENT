"""tests.test_cli_novel — CLI 小说命令的行为回归（不联网、不花钱）。

重点是"只往后写"：cmd_auto（一键生成整本）曾经用 range(1, N+1)，
对已有正文的项目会从第 1 章开始整本重写、把写好的章节覆盖掉。
现在它与 service.batch_write 的语义一致：从第一个未写章节开始。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cli import novel_commands  # noqa: E402
from src.novel.project_manager import NovelProject, OutlineItem  # noqa: E402


class FakeWriter:
    def __init__(self):
        self.written: list[int] = []

    def write_chapter(self, chapter_num, instructions="", target_words=2500, model_tier="pro"):
        self.written.append(chapter_num)
        return f"第{chapter_num}章正文" * 20


class FakePlot:
    def __init__(self):
        self.plots = {}
        self.designed: list[int] = []

    def design_chapter_plot(self, chapter_num, *args, **kwargs):
        self.designed.append(chapter_num)
        return None      # 没有剧情设计也允许直接写作

    def save(self, path):
        pass


class FakeEngine:
    def all_characters(self):
        return [object()]    # 非空 → cmd_auto 跳过"生成角色系统"

    def save(self, path):
        pass


class Args:
    """模拟 argparse 解析结果。"""

    def __init__(self, chapters: int, name: str = "测试项目"):
        self.name = name
        self.chapters = chapters
        self.words = 500
        self.prompt = ""
        self.genre = ""
        self.desc = ""
        self.tier = "flash"


def _make_bundle(tmp_path, chapters_written: int, outline_total: int):
    project = NovelProject("测试项目", base_dir=str(tmp_path))
    project.set_outline([
        OutlineItem(chapter=i, title=f"第{i}章", expected_content="")
        for i in range(1, outline_total + 1)
    ])
    for i in range(1, chapters_written + 1):
        project.add_chapter(i, f"第{i}章", f"正文{i}" * 10)
    writer, plot = FakeWriter(), FakePlot()
    bundle = (project, FakeEngine(), plot, writer)
    return bundle, writer, plot


def test_cmd_auto_skips_existing_chapters(tmp_path, monkeypatch):
    bundle, writer, plot = _make_bundle(tmp_path, chapters_written=2, outline_total=4)
    monkeypatch.setattr(novel_commands, "load_bundle",
                        lambda name, base_dir="data/projects": bundle)

    code = novel_commands.cmd_auto(Args(chapters=4))

    assert code == 0
    assert writer.written == [3, 4]     # 已有第 1-2 章，不重写
    assert plot.designed == [3, 4]      # 也不会为已写章节重新设计剧情


def test_cmd_auto_does_nothing_when_target_reached(tmp_path, monkeypatch):
    bundle, writer, plot = _make_bundle(tmp_path, chapters_written=3, outline_total=3)
    monkeypatch.setattr(novel_commands, "load_bundle",
                        lambda name, base_dir="data/projects": bundle)

    code = novel_commands.cmd_auto(Args(chapters=3))

    assert code == 0
    assert writer.written == []
    assert plot.designed == []


def test_cmd_auto_writes_from_scratch_for_new_project(tmp_path, monkeypatch):
    bundle, writer, plot = _make_bundle(tmp_path, chapters_written=0, outline_total=2)
    monkeypatch.setattr(novel_commands, "load_bundle",
                        lambda name, base_dir="data/projects": bundle)

    code = novel_commands.cmd_auto(Args(chapters=2))

    assert code == 0
    assert writer.written == [1, 2]     # 全新项目仍从第 1 章开始
