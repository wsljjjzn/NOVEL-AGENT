
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
from src.novel.service import NovelService


def _ensure_tier(tier: str) -> str:
    if tier not in ("flash", "pro"):
        raise SystemExit(f"无效模型层级: {tier}（可选 flash/pro）")
    return tier


# 项目根目录（测试可 patch 本模块的 BASE_DIR 指向临时目录）
BASE_DIR = "data/projects"


def _service() -> NovelService:
    """构造服务层：CLI 与 TUI 共用同一条编排（P0-1）。

    以前这四条命令各自内联了一遍"大纲→角色→剧情→写作"，于是
    "覆盖前备份 / 空输出报失败 / 只往后写"三类护栏只留在服务层里，CLI 全都丢了。
    现在 CLI 只做三件事：收集参数、展示结果、把结果映射成退出码。
    """
    return NovelService(BASE_DIR, log=lambda m: console.print(f"[cyan]{m}[/cyan]"))


def _report(result) -> int:
    """统一把服务层结果映射成输出与退出码（契约：失败必须非 0 退出）。"""
    style = "green" if result.ok else "red"
    console.print(f"[{style}]{result.title}[/{style}]")
    for line in result.lines:
        console.print(f"  {line}")
    return 0 if result.ok else 1


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


def cmd_characters(args) -> int:
    """生成角色系统 —— 编排在 NovelService（P0-1），CLI 只收集参数与展示结果。"""
    tier = _ensure_tier(args.tier)
    svc = _service()
    if not svc.exists(args.name):
        console.print(f"[red]项目不存在：{args.name}[/red]")
        return 1
    if not svc.load(args.name).project.outline:
        console.print("[yellow]当前没有大纲，角色生成缺少上下文。建议先: novel outline[/yellow]")
    console.print(f"[cyan]正在用 {tier} 生成角色系统…[/cyan]")
    r = svc.generate_characters(args.name, tier=tier)
    code = _report(r)
    if r.ok:
        _character_table(svc.load(args.name).engine)
    return code


def cmd_plot(args) -> int:
    """设计/导入单章剧情 —— 编排在 NovelService（P0-1）。"""
    tier = _ensure_tier(args.tier)
    svc = _service()
    if not svc.exists(args.name):
        console.print(f"[red]项目不存在：{args.name}[/red]")
        return 1
    if args.import_file:
        p = Path(args.import_file)
        if not p.exists():
            console.print(f"[red]文件不存在: {p}[/red]")
            return 1
        notes = p.read_text("utf-8")
        code = _report(svc.save_plot_notes(args.name, args.chapter, notes))
        console.print(Panel(notes, title=f"第{args.chapter}章 剧情笔记（已导入）", border_style="green"))
        return code

    console.print(f"[cyan]正在用 {tier} 设计第{args.chapter}章剧情…[/cyan]")
    r = svc.design_plot(args.name, args.chapter, tier=tier)
    code = _report(r)
    if r.ok:
        text = "\n".join(r.lines)
        console.print(Panel(text, title=f"第{args.chapter}章 剧情设计", border_style="blue"))
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            console.print(f"[green]已写入: {args.out}[/green]")
    return code


def cmd_write(args) -> int:
    """撰写单章 —— 编排在 NovelService（P0-1）。

    旧版无论模型返回什么，都打印绿色"写作完成（N 字）并已保存"并 exit 0；
    现在空文本由服务层判为 ok=False → 非 0 退出（契约：不许假成功）。
    """
    tier = _ensure_tier(args.tier)
    svc = _service()
    if not svc.exists(args.name):
        console.print(f"[red]项目不存在：{args.name}[/red]")
        return 1
    console.print(f"[cyan]正在用 {tier} 撰写第{args.chapter}章（目标 {args.words} 字）…[/cyan]")
    r = svc.write_chapter(
        args.name, args.chapter, target_words=args.words, tier=tier,
        instructions=args.instructions or "",
        use_plot=args.plot != "none",
        auto_plot=args.plot in ("auto", "if_missing"),
    )
    code = _report(r)
    if r.ok:
        text = svc.load(args.name).project.chapters.get(args.chapter, "")
        console.print(Panel(first_lines(text, 8), title="开头预览", border_style="green"))
    return code


def cmd_auto(args) -> int:
    """一键生成：大纲→角色→逐章 —— 全部委托 NovelService（P0-1）。

    旧版把三段编排又抄了一遍，于是把服务层的三类护栏全丢了：覆盖 characters.json
    前不备份、空输出照报成功、批量续写从第 1 章重写。现在 CLI 只做分阶段提示与退出码。
    """
    tier = _ensure_tier(args.tier)
    svc = _service()

    if not svc.exists(args.name):
        if not args.name.strip():
            console.print("[red]项目名不能为空[/red]")
            return 1
        r = svc.create(args.name, args.genre, args.desc)
        if _report(r):
            return 1
        console.print(f"[green]已自动创建项目「{args.name}」[/green]")

    console.print("[cyan][1/3] 生成大纲…[/cyan]")
    if not svc.load(args.name).project.outline:
        prompt = args.prompt or svc.load(args.name).project.description or "自动生成故事"
        code = _report(svc.generate_outline(args.name, args.chapters, prompt, tier=tier))
        if code:
            return code
    else:
        console.print("[yellow]大纲已存在，跳过[/yellow]")

    console.print("[cyan][2/3] 生成角色系统…[/cyan]")
    if not svc.load(args.name).engine.all_characters():
        code = _report(svc.generate_characters(args.name, tier=tier))
        if code:
            return code
    else:
        console.print("[yellow]角色已存在，跳过[/yellow]")

    console.print("[cyan][3/3] 逐章：剧情设计+写作…[/cyan]")
    # "只往后写"与"拒绝重写已有章"都由 service.batch_write 负责（护栏只有一处）
    project = svc.load(args.name).project
    written_to = max(project.chapters) if project.chapters else 0
    if written_to:
        console.print(f"[yellow]已有正文写到第 {written_to} 章，只往后写、不重写已有章节[/yellow]")
    if written_to >= args.chapters:
        console.print(f"[green]目标 {args.chapters} 章已完成，无需续写[/green]")
        return 0
    code = _report(svc.batch_write(
        args.name, count=args.chapters - written_to,
        target_words=args.words, tier=tier,
    ))
    if code == 0:
        console.print(f"[green]全部完成。导出全文可运行: python tui.py novel export {args.name}[/green]")
    return code


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
