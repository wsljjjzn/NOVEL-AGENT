"""tests.test_cli_novel — CLI 命令与 NovelService 的契约（P0-1 / P0-2 / P0-3）。

为什么重写这一版
----------------
`novel auto` / `characters` / `plot` / `write` 以前各自内联了一遍编排，于是：

- 覆盖 `characters.json` 前**不备份**（服务层有，CLI 版没有）；
- 模型返回空文本照样打印"写作完成（0 字）并已保存"并 **exit 0**（假成功）；
- `--tier pro` 对角色/剧情**完全无效**（`plot_engine` 里硬编码 flash，A16）。

现在四条命令都只调 `NovelService`，所以本文件从"验命令自己的实现"改成
"验 CLI 与服务层的契约"：

1. **不绕过服务层** —— tier 必须落到每一次 LLM 调用；护栏（备份）必须生效
2. **不许假成功** —— 空输出必须非 0 退出
3. **只往后写** —— `cmd_auto` 不得重写已有章节，目标已达时一次 LLM 都不该调

用假 LLM（`RoutingFakeLLM` / `StubService`）驱动，不联网、不花钱。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cli import novel_commands  # noqa: E402
from tests.test_novel_service import RoutingFakeLLM, StubService  # noqa: E402


class TierRecordingLLM(RoutingFakeLLM):
    """在路由假 LLM 之上记录每次调用用的档位（A16 契约测试用）。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tiers: list[tuple[str, str]] = []

    def chat(self, messages, model_tier: str = "flash", **kwargs) -> str:
        self.tiers.append((self.kind(messages), model_tier))
        return super().chat(messages, model_tier=model_tier, **kwargs)

    def tier_of(self, kind: str):
        return next((tier for k, tier in self.tiers if k == kind), None)


class Args:
    """模拟 argparse 解析结果（四条命令的参数并集）。"""

    def __init__(self, chapters: int = 2, tier: str = "flash", name: str = "测试书本",
                 chapter: int = 1, words: int = 500, plot: str = "if_missing"):
        self.name = name
        self.chapters = chapters
        self.chapter = chapter
        self.words = words
        self.tier = tier
        self.plot = plot
        self.instructions = ""
        self.prompt = ""
        self.genre = ""
        self.desc = ""
        self.out = ""
        self.import_file = ""


def _make_project(base: Path, *, name: str = "测试书本", written: int = 0,
                  outline: int = 2, characters: bool = True) -> None:
    """在临时目录里造一个真实项目（走 NovelProject.load 的读取路径）。"""
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(json.dumps({
        "name": name, "title": name, "genre": "科幻", "description": "一句话简介",
        "chapters": {str(i): f"第{i}章正文内容。" * 20 for i in range(1, written + 1)},
        "chapter_titles": {str(i): f"第{i}章标题" for i in range(1, written + 1)},
        "outline": [{"chapter": i, "title": f"第{i}章标题",
                     "expected_content": f"第{i}章要发生的事", "key_foreshadowing": []}
                    for i in range(1, outline + 1)],
        "metadata": {"total_words": 0, "chapter_count": written},
        "foreshadowing": ["未解的线索A"],
    }, ensure_ascii=False), encoding="utf-8")
    (d / "plots.json").write_text(json.dumps({"plots": {}, "world": {}}, ensure_ascii=False),
                                  encoding="utf-8")
    if characters:
        (d / "characters.json").write_text(json.dumps({
            "主角": {"name": "主角", "role": "主角", "personality": {"勇敢": 7},
                     "chapter_events": [], "relationships": {}, "arc_summary": ""},
        }, ensure_ascii=False), encoding="utf-8")


def _install(monkeypatch, base: Path, llm) -> StubService:
    """把 CLI 构造服务的入口换成注入了假 LLM 的 StubService。"""
    svc = StubService(str(base), llm)
    monkeypatch.setattr(novel_commands, "_service", lambda: svc)
    return svc


def _chapters(base: Path, name: str = "测试书本") -> dict:
    return json.loads((base / name / "project.json").read_text("utf-8"))["chapters"]


# ========== 契约 3：cmd_auto 只往后写 ==========

def test_cmd_auto_only_appends_and_never_rewrites(tmp_path, monkeypatch):
    """已有第 1-2 章时，只写 3-4 章；已有正文一个字节都不能变。"""
    _make_project(tmp_path, written=2, outline=4)
    llm = RoutingFakeLLM(chapters=["新写的正文" * 30, "新写的正文" * 30])
    _install(monkeypatch, tmp_path, llm)

    code = novel_commands.cmd_auto(Args(chapters=4, tier="pro"))

    assert code == 0
    data = _chapters(tmp_path)
    assert sorted(int(k) for k in data) == [1, 2, 3, 4]
    assert data["1"] == "第1章正文内容。" * 20, "第 1 章被重写了"
    assert data["2"] == "第2章正文内容。" * 20, "第 2 章被重写了"
    plots = json.loads((tmp_path / "测试书本" / "plots.json").read_text("utf-8"))["plots"]
    assert sorted(int(k) for k in plots) == [3, 4], "不该为已写章节重新设计剧情"


def test_cmd_auto_does_nothing_when_target_reached(tmp_path, monkeypatch):
    """目标章数已达 → 一次 LLM 调用都不该发生（不烧钱）。"""
    _make_project(tmp_path, written=3, outline=3)
    llm = RoutingFakeLLM()
    _install(monkeypatch, tmp_path, llm)

    code = novel_commands.cmd_auto(Args(chapters=3))

    assert code == 0
    assert llm.calls == [], f"目标已达却调用了 LLM: {llm.calls}"


def test_cmd_auto_writes_from_scratch_for_new_project(tmp_path, monkeypatch):
    _make_project(tmp_path, written=0, outline=0, characters=False)
    llm = RoutingFakeLLM(chapters=["第一章正文" * 30, "第二章正文" * 30])
    _install(monkeypatch, tmp_path, llm)

    code = novel_commands.cmd_auto(Args(chapters=2, tier="pro"))

    assert code == 0
    assert sorted(int(k) for k in _chapters(tmp_path)) == [1, 2]


# ========== 契约 1：tier 必须真的传下去（A16） ==========

def test_cmd_auto_passes_tier_to_every_stage(tmp_path, monkeypatch):
    """--tier pro 必须落到大纲/角色/剧情/正文每一处，不再被静默忽略。"""
    _make_project(tmp_path, written=0, outline=0, characters=False)
    llm = TierRecordingLLM()
    _install(monkeypatch, tmp_path, llm)

    code = novel_commands.cmd_auto(Args(chapters=1, tier="pro"))

    assert code == 0
    assert llm.tier_of("outline") == "pro"
    assert llm.tier_of("characters") == "pro"
    assert llm.tier_of("plot") == "pro"
    assert llm.tier_of("chapter") == "pro"


def test_cmd_characters_passes_tier_and_creates_backup(tmp_path, monkeypatch):
    """CLI 版角色生成必须带上 tier，并享受服务层的"覆盖前备份"护栏。"""
    _make_project(tmp_path, written=0, outline=2, characters=True)
    llm = TierRecordingLLM()
    _install(monkeypatch, tmp_path, llm)

    code = novel_commands.cmd_characters(Args(tier="pro"))

    assert code == 0
    assert llm.tier_of("characters") == "pro"
    backups = list((tmp_path / "测试书本").glob("characters.json.bak-*"))
    assert backups, "覆盖 characters.json 前必须备份（CLI 旧版没有这一步）"


def test_cmd_plot_passes_tier(tmp_path, monkeypatch):
    _make_project(tmp_path, written=0, outline=2)
    llm = TierRecordingLLM()
    _install(monkeypatch, tmp_path, llm)

    code = novel_commands.cmd_plot(Args(chapter=2, tier="pro"))

    assert code == 0
    assert llm.tier_of("plot") == "pro"


# ========== 契约 2：空输出必须非 0 退出（不许假成功） ==========

def test_cmd_write_empty_output_exits_nonzero(tmp_path, monkeypatch, capsys):
    """模型返回空文本时：exit ≠ 0，且不能出现"已完成/已保存"字样。"""
    _make_project(tmp_path, written=0, outline=2)
    llm = RoutingFakeLLM(chapters=[""])
    _install(monkeypatch, tmp_path, llm)

    code = novel_commands.cmd_write(Args(chapter=1, tier="pro", plot="none"))

    assert code == 1, "空输出必须非 0 退出"
    out = capsys.readouterr().out
    assert "已保存" not in out and "写作完成" not in out
    assert "1" not in _chapters(tmp_path), "空文本不该被写进项目"


def test_cmd_write_success_returns_zero(tmp_path, monkeypatch):
    _make_project(tmp_path, written=0, outline=2)
    llm = RoutingFakeLLM(chapters=["一段足够长的正文。" * 30])
    _install(monkeypatch, tmp_path, llm)

    code = novel_commands.cmd_write(Args(chapter=1, tier="pro", plot="none"))

    assert code == 0
    assert "1" in _chapters(tmp_path)


def test_cmd_missing_project_exits_nonzero(tmp_path, monkeypatch):
    """项目不存在 → 非 0 退出，且不抛异常。"""
    _make_project(tmp_path, written=0, outline=2)
    _install(monkeypatch, tmp_path, RoutingFakeLLM())

    assert novel_commands.cmd_characters(Args(name="不存在的项目")) == 1
    assert novel_commands.cmd_plot(Args(name="不存在的项目", chapter=1)) == 1
    assert novel_commands.cmd_write(Args(name="不存在的项目", chapter=1)) == 1
