"""
novel.service — 长篇小说操作的应用服务层（CLI 与 TUI 共用同一条编排）。

为什么要有这一层
----------------
原先"大纲→角色→剧情→写作"的编排逻辑写死在 `src/cli/novel_commands.py` 里，
界面换一次就要抄一遍。这里把**编排**收敛成一处，界面只负责收集参数和展示结果：

    src/novel/*.py     领域原语（项目/角色/剧情/写作）—— 不认识界面
    src/novel/service.py  编排 + 护栏 + 结果对象        —— 不认识界面
    src/cli/*.py            命令行界面
    src/tui/*.py            交互式终端界面

对有副作用的操作，本层加了 CLI 缺失的护栏：
- 覆盖 characters.json 前自动备份
- 批量续写从"第一个未写章节"开始（而不是从第 1 章重写）
- 引擎内部会把 LLM 失败吞成空结果，本层把它还原成 ok=False，避免"假成功"
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from src.novel.chapter_writer import ChapterWriter
from src.novel.character_engine import CharacterEngine, CharacterProfile
from src.novel.plot_engine import ChapterPlot, PlotEngine
from src.novel.project_manager import NovelProject, OutlineItem

LogFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


@dataclass
class Bundle:
    """一个项目的完整内存态（项目 + 角色引擎 + 剧情引擎 + 写作器）。"""
    project: NovelProject
    engine: CharacterEngine
    plot: PlotEngine
    writer: ChapterWriter


@dataclass
class Result:
    """服务层统一的返回：界面据此显示成功/失败，而不是靠猜。"""
    ok: bool
    title: str
    lines: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        return "\n".join([self.title, *self.lines])


class NovelService:
    """长篇小说业务服务。所有方法都不会抛 LLM 异常（失败转成 Result.ok=False）。"""

    def __init__(self, base_dir: str = "data/projects", log: LogFn = _noop):
        self.base_dir = base_dir
        self.log = log

    # ========== 项目 ==========

    def list_projects(self) -> list[dict]:
        rows = []
        root = Path(self.base_dir)
        if not root.exists():
            return rows
        for d in sorted(root.iterdir()):
            if not (d / "project.json").exists():
                continue
            try:
                data = json.loads((d / "project.json").read_text("utf-8"))
            except Exception:
                continue
            md = data.get("metadata", {})
            chapters = data.get("chapters", {}) or {}
            rows.append({
                "name": d.name,
                "title": data.get("title", d.name),
                "genre": data.get("genre", ""),
                "description": data.get("description", ""),
                "chapters": len(chapters),
                "outline": len(data.get("outline", []) or []),
                "foreshadowing": len(data.get("foreshadowing", []) or []),
                "words": md.get("total_words") or sum(len(v) for v in chapters.values()),
            })
        return rows

    def exists(self, name: str) -> bool:
        return (Path(self.base_dir) / name / "project.json").exists()

    def load(self, name: str) -> Bundle:
        """从磁盘恢复完整状态（不调用任何 LLM）。"""
        project = NovelProject.load(self.base_dir, name)
        engine = CharacterEngine()
        plot = PlotEngine()
        char_file = project.base_dir / "characters.json"
        plot_file = project.base_dir / "plots.json"
        if char_file.exists():
            engine.load(str(char_file))
        if plot_file.exists():
            plot.load(str(plot_file))
        return Bundle(project, engine, plot, ChapterWriter(project, engine))

    def create(self, name: str, genre: str = "", description: str = "") -> Result:
        if not name.strip():
            return Result(False, "项目名不能为空")
        if self.exists(name):
            return Result(False, f"项目已存在：{name}")
        project = NovelProject(name, self.base_dir)
        project.genre = genre
        project.description = description
        project.save()
        return Result(True, f"项目「{name}」已创建", [str(project.base_dir)])

    def delete(self, name: str) -> Result:
        if not self.exists(name):
            return Result(False, f"项目不存在：{name}")
        shutil.rmtree(Path(self.base_dir) / name)
        return Result(True, f"项目「{name}」已删除（不可恢复）")

    def export(self, name: str, out: Optional[str] = None) -> Result:
        bundle = self.load(name)
        if not bundle.project.chapters:
            return Result(False, "项目还没有任何章节")
        text = bundle.project.export_novel()
        path = Path(out) if out else bundle.project.base_dir / "export.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return Result(True, f"已导出 {len(text):,} 字", [str(path)])

    # ========== 大纲 ==========

    def generate_outline(self, name: str, chapters: int, prompt: str,
                         tier: str = "flash") -> Result:
        bundle = self.load(name)
        self.log(f"[大纲] 用 {tier} 生成 {chapters} 章…")
        try:
            items = bundle.writer.generate_outline(chapters, prompt, model_tier=tier)
        except Exception as e:
            return Result(False, f"大纲生成失败：{type(e).__name__}: {e}")
        if not items:
            return Result(False, "大纲为空：模型未返回可解析的 JSON（本次调用仍会计费）")
        return Result(True, f"大纲已生成 {len(items)} 章", self.outline_lines(bundle.project))

    def outline_lines(self, project: NovelProject) -> list[str]:
        lines = []
        for item in project.outline:
            lines.append(f"第{item.chapter}章「{item.title}」: {item.expected_content}")
            if item.key_foreshadowing:
                lines.append(f"  伏笔: {'; '.join(item.key_foreshadowing)}")
        return lines

    def update_outline_item(self, name: str, chapter: int, title: str,
                            expected_content: str, foreshadowing: Optional[list[str]] = None) -> Result:
        """手工修改单章大纲（TUI 编辑落盘用）。"""
        bundle = self.load(name)
        project = bundle.project
        target = next((o for o in project.outline if o.chapter == chapter), None)
        if target is None:
            target = OutlineItem(chapter=chapter, title=title, expected_content=expected_content)
            project.outline.append(target)
            project.outline.sort(key=lambda o: o.chapter)
        else:
            target.title = title
            target.expected_content = expected_content
        if foreshadowing is not None:
            target.key_foreshadowing = foreshadowing
        project.chapter_titles[chapter] = title
        project.save()
        return Result(True, f"第{chapter}章大纲已更新", [f"标题：{title}", f"预期内容：{expected_content}"])

    # ========== 角色 ==========

    def generate_characters(self, name: str, tier: str = "flash", backup: bool = True) -> Result:
        bundle = self.load(name)
        project, engine, plot = bundle.project, bundle.engine, bundle.plot
        char_file = project.base_dir / "characters.json"

        # 保留已有角色的 chapter_events（避免重新生成时丢掉逐章纪要）
        existing_events = {c.name: c.chapter_events
                           for c in engine.all_characters() if c.chapter_events}

        # 护栏：覆盖前自动备份 —— CLI 版本没有这一步
        backup_path = None
        if backup and char_file.exists():
            backup_path = char_file.with_name(
                f"characters.json.bak-{time.strftime('%Y%m%d-%H%M%S')}")
            shutil.copy2(char_file, backup_path)

        self.log(f"[角色] 用 {tier} 生成角色系统…")
        try:
            chars, _world = plot.design_characters(
                project.title, project.genre, project.description,
                project.get_outline_context(),
                model_tier=tier,          # A16：以前这里没传，日志说 pro、实际走 flash
            )
        except Exception as e:
            return Result(False, f"角色生成失败：{type(e).__name__}: {e}")
        if not chars:
            return Result(False, "模型未返回可解析的角色 JSON（本次调用仍会计费）")

        added = 0
        for cd in chars:
            if not isinstance(cd, dict) or not cd.get("name"):
                continue
            engine.add_character(CharacterProfile(
                name=cd["name"], role=cd.get("role", ""),
                personality=cd.get("personality", {}),
                speaking_style=cd.get("speaking_style", ""),
                core_desire=cd.get("core_desire", ""), core_fear=cd.get("core_fear", ""),
                background=cd.get("background", ""), appearance=cd.get("appearance", ""),
                relationships=cd.get("relationships", {}),
                arc_summary=cd.get("arc_summary", ""),
            ))
            added += 1

        for cname, events in existing_events.items():
            profile = engine.get_character(cname)
            if profile is not None and not profile.chapter_events:
                profile.chapter_events = events

        engine.save(str(char_file))
        plot.save(str(project.base_dir / "plots.json"))
        lines = [f"共 {added} 个角色（去重后 {len(engine.all_characters())} 个）"]
        if backup_path:
            lines.append(f"原文件已备份 → {backup_path.name}")
        return Result(True, "角色系统已生成", lines)

    # ========== 剧情 ==========

    def design_plot(self, name: str, chapter: int, tier: str = "flash") -> Result:
        bundle = self.load(name)
        project, plot = bundle.project, bundle.plot
        item = next((o for o in project.outline if o.chapter == chapter), None)
        if item is None:
            return Result(False, f"大纲里没有第{chapter}章（先生成大纲，或手工补一条）")
        self.log(f"[剧情] 用 {tier} 设计第{chapter}章…")
        plot_obj = plot.design_chapter_plot(
            chapter, {"title": item.title, "expected_content": item.expected_content},
            project.get_recap(chapter), project.foreshadowing,
            model_tier=tier,              # A16：以前这里没传
        )
        empty = not (plot_obj.opening_hook or plot_obj.scenes or plot_obj.climax)
        plot.save(str(project.base_dir / "plots.json"))
        if empty:
            return Result(False, f"第{chapter}章剧情设计为空：模型输出无法解析（本次调用仍会计费）")
        return Result(True, f"第{chapter}章剧情已设计", plot_obj.to_prompt_text().splitlines())

    def save_plot_notes(self, name: str, chapter: int, notes: str) -> Result:
        bundle = self.load(name)
        plot = bundle.plot
        plot_obj = plot.plots.get(chapter) or ChapterPlot(chapter)
        plot_obj.user_notes = notes
        plot.plots[chapter] = plot_obj
        plot.save(str(bundle.project.base_dir / "plots.json"))
        return Result(True, f"第{chapter}章剧情笔记已保存（{len(notes)} 字）")

    # ========== 写作 ==========

    def write_chapter(self, name: str, chapter: int, target_words: int = 2500,
                      tier: str = "pro", instructions: str = "",
                      use_plot: bool = True, auto_plot: bool = True) -> Result:
        bundle = self.load(name)
        project, plot, writer = bundle.project, bundle.plot, bundle.writer

        plot_obj = plot.plots.get(chapter)
        if plot_obj is None and use_plot and auto_plot:
            item = next((o for o in project.outline if o.chapter == chapter), None)
            if item is not None:
                self.log(f"[写作] 第{chapter}章缺剧情设计，先自动生成…")
                plot_obj = plot.design_chapter_plot(
                    chapter, {"title": item.title, "expected_content": item.expected_content},
                    project.get_recap(chapter), project.foreshadowing,
                    model_tier=tier,      # A16：以前这里没传
                )
                plot.save(str(project.base_dir / "plots.json"))

        prompt_instructions = instructions
        if plot_obj is not None and use_plot:
            prompt_instructions += "\n\n## 本章剧情设计（请严格遵循）\n" + plot_obj.to_prompt_text()
            for fp in plot_obj.foreshadowing_planted:
                project.add_foreshadowing(fp)
            for fr in plot_obj.foreshadowing_resolved:
                project.resolve_foreshadowing(fr)

        self.log(f"[写作] 第{chapter}章 用 {tier} 写 {target_words} 字…")
        try:
            text = writer.write_chapter(chapter, prompt_instructions, target_words,
                                        model_tier=tier)
        except Exception as e:
            return Result(False, f"第{chapter}章写作失败：{type(e).__name__}: {e}")
        if not text.strip():
            return Result(False, f"第{chapter}章返回空文本（本次调用仍会计费）")

        wc = len(project.chapters.get(chapter, ""))
        detail = [f"目标 {target_words} 字 → 实际 {wc:,} 字"]
        if target_words and abs(wc - target_words) / target_words > 0.3:
            detail.append("⚠ 与目标字数偏差超过 30%，可考虑重写或续写补足")
        return Result(True, f"第{chapter}章已完成", detail)

    def batch_write(self, name: str, count: int, target_words: int = 2500,
                    tier: str = "pro", instructions: str = "",
                    start: Optional[int] = None) -> Result:
        """批量续写。

        默认从**第一个未写章节**开始 —— 这是与 CLI `novel auto` 的关键区别：
        后者用 range(1, N+1)，对已有正文的项目会从第 1 章开始覆盖。
        """
        bundle = self.load(name)
        project = bundle.project
        first_unwritten = (max(project.chapters) + 1) if project.chapters else 1
        begin = start if start is not None else first_unwritten
        if begin <= (max(project.chapters) if project.chapters else 0):
            return Result(False,
                          f"起始章 {begin} 已有正文（现写到第 {max(project.chapters)} 章）。"
                          f"批量续写只会往后写；若要覆盖某一章请用单章撰写。")
        done, failed = [], []
        for i in range(begin, begin + count):
            r = self.write_chapter(name, i, target_words, tier, instructions)
            if r.ok:
                done.append(i)
            else:
                failed.append(f"第{i}章：{r.title}")
                break  # 失败即停，避免连续烧钱
        title = f"批量续写完成：第 {begin}-{begin + len(done) - 1} 章" if done else "批量续写未产生章节"
        lines = [f"成功 {len(done)} 章"] + failed
        return Result(bool(done), title, lines)

    # ========== 运行时状态 ==========

    def llm_status(self) -> dict:
        """LLM 配置状态（供界面显示，不泄露 Key）。"""
        from config.settings import get_config
        out = {"tiers": [], "configured": False, "budget_cny": 0.0}
        try:
            cfg = get_config()
        except Exception as e:
            out["error"] = f"配置加载失败：{e}"
            return out
        for tier in ("flash", "pro"):
            # config.yaml 里的键是完整模型名（deepseek_v4_flash），不是档位名，
            # 与 llm_client.py 的取法保持一致，并兼容只写 flash/pro 的配置。
            c = (cfg.llm.get(f"deepseek_v4_{tier}") or cfg.llm.get(tier)
                 or next((v for k, v in cfg.llm.items() if k.endswith(f"_{tier}")), None))
            if c is None:
                continue
            key = c.api_key or ""
            looks_placeholder = "${" in key or not key.strip()
            out["tiers"].append({
                "tier": tier, "model": c.model, "base_url": c.base_url,
                "key_ok": not looks_placeholder,
            })
            if not looks_placeholder:
                out["configured"] = True
        try:
            out["budget_cny"] = float(getattr(cfg.budget, "max_cny_per_session", 0) or 0)
        except Exception:
            pass
        return out

    def reload_config(self) -> tuple[bool, str]:
        """清掉配置单例缓存后重新读取 config.yaml + .env（界面里改完 Key 用）。"""
        try:
            import config.settings as settings
            settings._config = None
            settings.get_config()
            return True, "已重新读取配置"
        except Exception as e:
            return False, f"重载失败：{type(e).__name__}: {e}"

    def usage_summary(self) -> dict:
        """本进程累计用量/费用。"""
        try:
            from src.utils.cost_tracker import get_tracker
            t = get_tracker()
            return {"calls": t.total_calls, "cost": t.total_cost_cny,
                    "budget": t.budget_cny, "markdown": t.markdown_summary()}
        except Exception:
            return {"calls": 0, "cost": 0.0, "budget": 0.0, "markdown": ""}
