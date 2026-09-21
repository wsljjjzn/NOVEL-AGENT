
"""cli.novel_commands — 长篇小说相关子命令。

行为对齐 Gradio 版工作台（novel_create / novel_load / 四阶段 / 导出），
但改为"每条命令 = 一个进程"的命令式形态；涉及 LLM 的步骤均带 --tier 选项。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.panel import Panel
from rich.table import Table

from .common import console, load_bundle, create_project, project_summary, render_project_table, first_lines


def _ensure_tier(tier: str) -> str:
    if tier not in ("flash", "pro"):
        raise SystemExit(f"无效模型层级: {tier}（可选 flash/pro）")
    return tier


# ========== 工具 ==========

def _outline_lines(project) -> list[str]:
    lines = []
    for item in project.outline:
        lines.append(f"第{item.chapter}章「{item.title}」: {item.expected_content}")
        if item.key_foreshadowing:
            lines.append(f"  伏笔: {'; '.join(item.key_foreshadowing)}")
    return lines


def parse_outline_text(text: str) -> list:
    """把可编辑大纲文本解析回 OutlineItem（对齐 gradio novel_save_outline，并支持伏笔行）。"""
    from src.novel.project_manager import OutlineItem
    items = []
    cur = None
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"第(\d+)章[「【]\s*(.+?)\s*[」】]\s*[：:]\s*(.+)", line)
        if m:
            cur = OutlineItem(
                chapter=int(m.group(1)),
                title=m.group(2),
                expected_content=m.group(3),
                key_foreshadowing=[],
            )
            items.append(cur)
            continue
        fm = re.match(r"伏笔[:：]\s*(.+)", line)
        if fm and cur is not None:
            cur.key_foreshadowing = [x.strip() for x in fm.group(1).split(";") if x.strip()]
    return items


def _chapter_table(project) -> None:
    chs = project.list_chapters()
    table = Table(title=f"章节一览（{project.title}）", header_style="bold cyan")
    for col in ["章号", "标题", "状态", "字数"]:
        table.add_column(col)
    for c in chs:
        table.add_row(str(c.number), c.title or "-", c.status, f"{c.word_count:,}")
    console.print(table)


def _character_table(engine) -> None:
    chars = engine.all_characters()
    if not chars:
        console.print("[yellow]暂无角色（先运行 novel characters）[/yellow]")
        return
    table = Table(title="角色系统", header_style="bold cyan")
    for col in ["姓名", "定位", "情绪", "人格"]:
        table.add_column(col)
    for c in chars:
        table.add_row(c.name, c.role or "-", c.current_mood, c.personality_summary())
    console.print(table)


# ========== 命令实现 ==========

def cmd_list(args) -> int:
    from src.novel import NovelProject
    names = NovelProject.list_projects()
    if not names:
        console.print("[yellow]暂无项目[/yellow]")
        return 0
    render_project_table([project_summary(n) for n in names])
    return 0


def cmd_create(args) -> int:
    try:
        project, engine, plot, writer = create_project(args.name, args.genre, args.desc)
        console.print(f"[green]项目「{project.name}」已创建[/green]")
        return 0
    except Exception as e:
        console.print(f"[red]创建失败: {e}[/red]")
        return 1


def cmd_show(args) -> int:
    try:
        project, engine, plot, writer = load_bundle(args.name)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    except Exception as e:
        console.print(f"[red]加载失败: {e}[/red]")
        return 1

    if args.chapter is not None:
        text = project.get_chapter(args.chapter)
        if not text:
            console.print(f"[red]第{args.chapter}章暂未撰写[/red]")
            return 1
        title = project.chapter_titles.get(args.chapter, f"第{args.chapter}章")
        console.print(Panel(text, title=f"第{args.chapter}章 {title}", border_style="green"))
        return 0

    if args.recap is not None:
        console.print(Panel(project.get_recap(args.recap), title=f"第{args.recap}章 前情提要", border_style="blue"))
        return 0

    meta = project_summary(args.name)
    console.print(Panel(
        f"标题: {meta['title']}\n题材: {meta['genre'] or '-'}\n简介: {meta['description'] or '-'}\n"
        f"已写章节: {meta['chapters']} | 总字数: {meta['words']:,}",
        title="项目信息", border_style="cyan",
    ))
    _chapter_table(project)
    if project.foreshadowing:
        console.print(f"[yellow]开放伏笔: {'; '.join(project.foreshadowing[:8])}[/yellow]")
    if args.chars:
        _character_table(engine)
    if args.plots:
        if not plot.plots:
            console.print("[yellow]暂无剧情设计[/yellow]")
        else:
            table = Table(title="剧情设计一览", header_style="bold cyan")
            for col in ["章", "开篇钩子", "高潮", "结尾钩子"]:
                table.add_column(col)
            for num in sorted(plot.plots):
                p = plot.plots[num]
                table.add_row(str(num), (p.opening_hook or "-")[:40], (p.climax or "-")[:40], (p.ending_hook or "-")[:40])
            console.print(table)
    return 0


def cmd_outline(args) -> int:
    if args.import_file and args.chapters is not None:
        console.print("[red]--import-file 与 --chapters 不能同时使用[/red]")
        return 1
    try:
        project, engine, plot, writer = load_bundle(args.name)
    except Exception as e:
        console.print(f"[red]加载失败: {e}[/red]")
        return 1

    if args.import_file:
        p = Path(args.import_file)
        if not p.exists():
            console.print(f"[red]文件不存在: {p}[/red]")
            return 1
        items = parse_outline_text(p.read_text("utf-8"))
        if not items:
            console.print("[red]未识别到大纲行（格式：第N章「标题」: 内容，可选伏笔行）[/red]")
            return 1
        project.set_outline(items)
        project.save()
        console.print(f"[green]已从 {p.name} 导入大纲 {len(items)} 章[/green]")
        for l in _outline_lines(project):
            console.print(l)
        return 0

    if not args.prompt:
        console.print("[red]缺少故事简介：--prompt 一句话简介[/red]")
        return 1
    console.print(f"[cyan]正在用 {_ensure_tier(args.tier)} 生成 {args.chapters} 章大纲…[/cyan]")
    try:
        items = writer.generate_outline(args.chapters, args.prompt, model_tier=args.tier)
    except Exception as e:
        console.print(f"[red]大纲生成失败: {e}[/red]")
        return 1
    if not items:
        console.print("[red]大纲为空（模型未返回有效 JSON）[/red]")
        return 1
    for l in _outline_lines(project):
        console.print(l)
    console.print(f"[green]大纲已生成并保存 {len(items)} 章[/green]")
    if args.out:
        Path(args.out).write_text("\n".join(_outline_lines(project)), encoding="utf-8")
        console.print(f"[green]已写入: {args.out}[/green]")
    return 0


def _fill_characters(project, engine, plot, keep_existing: bool = True) -> int:
    """生成角色系统并入库（对齐 gradio novel_stage2_characters）。"""
    existing_events = {}
    if keep_existing:
        for c in engine.all_characters():
            if c.chapter_events:
                existing_events[c.name] = c.chapter_events

    chars, world = plot.design_characters(
        project.title, project.genre,
        project.description, project.get_outline_context(),
    )
    from src.novel.character_engine import CharacterProfile
    for cd in chars:
        if not isinstance(cd, dict) or not cd.get("name"):
            continue
        profile = CharacterProfile(
            name=cd["name"], role=cd.get("role", ""),
            personality=cd.get("personality", {}),
            speaking_style=cd.get("speaking_style", ""),
            core_desire=cd.get("core_desire", ""), core_fear=cd.get("core_fear", ""),
            background=cd.get("background", ""), appearance=cd.get("appearance", ""),
            relationships=cd.get("relationships", {}),
            arc_summary=cd.get("arc_summary", ""),
        )
        engine.add_character(profile)
    for name, events in existing_events.items():
        if name in engine._characters and not engine._characters[name].chapter_events:
            engine._characters[name].chapter_events = events

    engine.save(str(project.base_dir / "characters.json"))
    plot.save(str(project.base_dir / "plots.json"))
    return len(engine.all_characters())


def cmd_characters(args) -> int:
    try:
        project, engine, plot, writer = load_bundle(args.name)
    except Exception as e:
        console.print(f"[red]加载失败: {e}[/red]")
        return 1
    if not project.outline:
        console.print("[yellow]当前没有大纲，角色生成缺少上下文。建议先: novel outline[/yellow]")
    console.print(f"[cyan]正在用 {_ensure_tier(args.tier)} 生成角色系统…[/cyan]")
    try:
        n = _fill_characters(project, engine, plot)
    except Exception as e:
        console.print(f"[red]角色生成失败: {e}[/red]")
        return 1
    _character_table(engine)
    console.print(f"[green]角色已保存 characters.json（{n} 个）[/green]")
    return 0


def cmd_plot(args) -> int:
    try:
        project, engine, plot, writer = load_bundle(args.name)
    except Exception as e:
        console.print(f"[red]加载失败: {e}[/red]")
        return 1
    item = next((o for o in project.outline if o.chapter == args.chapter), None)
    if item is None:
        console.print(f"[red]大纲中没有第{args.chapter}章（请先 novel outline）[/red]")
        return 1
    if args.import_file:
        p = Path(args.import_file)
        if not p.exists():
            console.print(f"[red]文件不存在: {p}[/red]")
            return 1
        from src.novel.plot_engine import ChapterPlot
        plot_obj = plot.plots.get(args.chapter) or ChapterPlot(args.chapter)
        plot_obj.user_notes = p.read_text("utf-8")
        plot.plots[args.chapter] = plot_obj
        plot.save(str(project.base_dir / "plots.json"))
        console.print(Panel(plot_obj.user_notes, title=f"第{args.chapter}章 剧情笔记（已导入）", border_style="green"))
        return 0

    console.print(f"[cyan]正在用 {_ensure_tier(args.tier)} 设计第{args.chapter}章剧情…[/cyan]")
    try:
        plot_obj = plot.design_chapter_plot(
            args.chapter,
            {"title": item.title, "expected_content": item.expected_content},
            project.get_recap(args.chapter),
            project.foreshadowing,
        )
        plot.save(str(project.base_dir / "plots.json"))
    except Exception as e:
        console.print(f"[red]剧情设计失败: {e}[/red]")
        return 1
    console.print(Panel(plot_obj.to_prompt_text(), title=f"第{args.chapter}章 剧情设计", border_style="blue"))
    if args.out:
        Path(args.out).write_text(plot_obj.to_prompt_text(), encoding="utf-8")
        console.print(f"[green]已写入: {args.out}[/green]")
    return 0


def cmd_write(args) -> int:
    _ensure_tier(args.tier)
    try:
        project, engine, plot, writer = load_bundle(args.name)
    except Exception as e:
        console.print(f"[red]加载失败: {e}[/red]")
        return 1

    instructions = args.instructions or ""
    plot_obj = plot.plots.get(args.chapter)
    if plot_obj is None and args.plot in ("auto", "if_missing"):
        item = next((o for o in project.outline if o.chapter == args.chapter), None)
        if item is not None:
            console.print(f"[cyan]第{args.chapter}章尚无剧情设计，先自动生成…[/cyan]")
            try:
                plot_obj = plot.design_chapter_plot(
                    args.chapter,
                    {"title": item.title, "expected_content": item.expected_content},
                    project.get_recap(args.chapter),
                    project.foreshadowing,
                )
                plot.save(str(project.base_dir / "plots.json"))
            except Exception as e:
                console.print(f"[red]剧情自动设计失败: {e}[/red]")
                return 1
    if plot_obj is not None and args.plot != "none":
        instructions += "\n\n## 本章剧情设计（请严格遵循）\n" + plot_obj.to_prompt_text()
        for fp in plot_obj.foreshadowing_planted:
            project.add_foreshadowing(fp)
        for fr in plot_obj.foreshadowing_resolved:
            project.resolve_foreshadowing(fr)

    console.print(f"[cyan]正在用 {args.tier} 撰写第{args.chapter}章（目标 {args.words} 字）…[/cyan]")
    try:
        text = writer.write_chapter(args.chapter, instructions, args.words, model_tier=args.tier)
    except Exception as e:
        console.print(f"[red]写作失败: {e}[/red]")
        return 1
    wc = len(project.chapters.get(args.chapter, ""))
    console.print(f"[green]第{args.chapter}章写作完成（{wc:,} 字）并已保存[/green]")
    console.print(Panel(first_lines(text, 8), title="开头预览", border_style="green"))
    return 0


def cmd_auto(args) -> int:
    """一键生成：大纲→角色→逐章（剧情设计+写作）。需要较多 API 调用。"""
    _ensure_tier(args.tier)
    try:
        project, engine, plot, writer = load_bundle(args.name)
    except FileNotFoundError:
        project, engine, plot, writer = create_project(args.name, args.genre, args.desc)
        console.print(f"[green]已自动创建项目「{args.name}」[/green]")
    except Exception as e:
        console.print(f"[red]加载失败: {e}[/red]")
        return 1

    console.print("[cyan][1/3] 生成大纲…[/cyan]")
    if not project.outline:
        writer.generate_outline(args.chapters, args.prompt or project.description or "自动生成故事", model_tier=args.tier)
        console.print(f"[green]大纲 {len(project.outline)} 章已生成[/green]")
    else:
        console.print("[yellow]大纲已存在，跳过[/yellow]")

    console.print("[cyan][2/3] 生成角色系统…[/cyan]")
    if not engine.all_characters():
        n = _fill_characters(project, engine, plot)
        console.print(f"[green]角色 {n} 个已生成[/green]")
    else:
        console.print("[yellow]角色已存在，跳过[/yellow]")

    console.print("[cyan][3/3] 逐章：剧情设计+写作…[/cyan]")
    for ch in range(1, args.chapters + 1):
        item = next((o for o in project.outline if o.chapter == ch), None)
        plot_obj = plot.plots.get(ch)
        if plot_obj is None and item is not None:
            plot_obj = plot.design_chapter_plot(
                ch, {"title": item.title, "expected_content": item.expected_content},
                project.get_recap(ch), project.foreshadowing,
            )
            plot.save(str(project.base_dir / "plots.json"))
        instructions = ""
        if plot_obj is not None:
            instructions = "\n\n## 本章剧情设计（请严格遵循）\n" + plot_obj.to_prompt_text()
            for fp in plot_obj.foreshadowing_planted:
                project.add_foreshadowing(fp)
            for fr in plot_obj.foreshadowing_resolved:
                project.resolve_foreshadowing(fr)
        try:
            writer.write_chapter(ch, instructions, args.words, model_tier=args.tier)
        except Exception as e:
            console.print(f"[red]第{ch}章写作失败: {e}（已停止）[/red]")
            break
        wc = len(project.chapters.get(ch, ""))
        console.print(f"[green]第{ch}章完成（{wc:,} 字）[/green]")

    project.save()
    engine.save(str(project.base_dir / "characters.json"))
    plot.save(str(project.base_dir / "plots.json"))
    console.print(f"[green]全部完成。导出全文可运行: python tui.py novel export {args.name}[/green]")
    return 0


def cmd_export(args) -> int:
    try:
        project, engine, plot, writer = load_bundle(args.name)
    except Exception as e:
        console.print(f"[red]加载失败: {e}[/red]")
        return 1
    if not project.chapters:
        console.print("[yellow]项目还没有任何章节[/yellow]")
        return 1
    text = project.export_novel()
    if args.stdout:
        console.print(text)
        return 0
    path = Path(args.out) if args.out else project.base_dir / "export.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    console.print(f"[green]已导出 {len(text):,} 字 → {path}[/green]")
    return 0


def cmd_delete(args) -> int:
    if not args.yes:
        console.print("[red]危险操作，请加 --yes 确认删除[/red]")
        return 1
    from src.novel import NovelProject
    try:
        ok = NovelProject.delete("data/projects", args.name)
    except Exception as e:
        console.print(f"[red]删除失败: {e}[/red]")
        return 1
    console.print("[green]已删除[/green]" if ok else "[yellow]项目不存在[/yellow]")
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("novel", help="长篇小说：项目管理与写作")
    sp = p.add_subparsers(dest="action", required=True)

    def add(name, fn, help_text):
        q = sp.add_parser(name, help=help_text)
        q.set_defaults(func=fn)
        return q

    q = add("list", cmd_list, "列出所有项目")
    q = add("create", cmd_create, "新建项目")
    q.add_argument("name", help="项目名称")
    q.add_argument("--genre", default="", help="题材，如 都市/玄幻")
    q.add_argument("--desc", default="", help="一句话简介")

    q = add("show", cmd_show, "查看项目状态 / 章节正文 / 前情提要")
    q.add_argument("name")
    q.add_argument("--chapter", type=int, default=None, help="打印指定章节正文")
    q.add_argument("--recap", type=int, default=None, help="打印指定章节的前情提要")
    q.add_argument("--chars", action="store_true", help="同时展示角色系统")
    q.add_argument("--plots", action="store_true", help="同时展示剧情设计一览")

    q = add("outline", cmd_outline, "生成/导入大纲")
    q.add_argument("name")
    q.add_argument("--chapters", type=int, default=None, help="总章节数")
    q.add_argument("--prompt", default="", help="故事简介")
    q.add_argument("--tier", default="flash")
    q.add_argument("--out", default="", help="大纲另存到文本文件")
    q.add_argument("--import-file", default="", help="从可编辑大纲文件导入")

    q = add("characters", cmd_characters, "生成角色系统")
    q.add_argument("name")
    q.add_argument("--tier", default="flash")

    q = add("plot", cmd_plot, "设计/导入单章剧情")
    q.add_argument("name")
    q.add_argument("--chapter", type=int, required=True)
    q.add_argument("--tier", default="flash")
    q.add_argument("--out", default="", help="设计文本另存文件")
    q.add_argument("--import-file", default="", help="把已编辑剧情文本存为本章剧情笔记")

    q = add("write", cmd_write, "撰写单章（写完自动分析角色变化）")
    q.add_argument("name")
    q.add_argument("--chapter", type=int, required=True)
    q.add_argument("--words", type=int, default=2500)
    q.add_argument("--instructions", default="")
    q.add_argument("--tier", default="pro")
    q.add_argument("--plot", choices=["auto", "if_missing", "none"], default="if_missing",
                  help="是否附带本章剧情设计上下文（auto=缺省就先生成）")

    q = add("auto", cmd_auto, "一键生成整本（大纲→角色→逐章，耗 API）")
    q.add_argument("name")
    q.add_argument("--chapters", type=int, required=True)
    q.add_argument("--words", type=int, default=2000)
    q.add_argument("--prompt", default="")
    q.add_argument("--genre", default="")
    q.add_argument("--desc", default="")
    q.add_argument("--tier", default="flash", help="大纲/角色/剧情用层级（正文固定为 pro 更稳妥，本命令内统一用此值）")

    q = add("export", cmd_export, "导出整本小说文本")
    q.add_argument("name")
    q.add_argument("--out", default="", help="输出路径（默认 data/projects/<name>/export.txt）")
    q.add_argument("--stdout", action="store_true", help="直接打印全文")

    q = add("delete", cmd_delete, "删除项目（不可恢复）")
    q.add_argument("name")
    q.add_argument("--yes", action="store_true")
