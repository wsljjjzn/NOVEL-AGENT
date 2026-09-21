
"""cli.article_commands — 短篇写作 / 审稿 / 端到端 子命令。

行为对齐 Gradio：handle_write（短篇知识增强写作）、handle_review（六维审稿+三级修改）、handle_e2e。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.panel import Panel

from .common import console


def _read_source(args) -> str:
    """从位置参数文件或 --text 取文章内容。"""
    if getattr(args, "text", None):
        return args.text
    if getattr(args, "file", None):
        p = Path(args.file)
        if not p.exists():
            raise SystemExit(f"文件不存在: {p}")
        from src.utils.file_utils import read_text_file
        return read_text_file(str(p))
    raise SystemExit("需要提供 --text 正文 或 FILE 路径")


# ========== 短篇写作 ==========

def cmd_write(args) -> int:
    from src.writing_engine import WritingOrchestrator
    if not args.topic.strip():
        console.print("[red]需求不能为空[/red]")
        return 1
    orchestrator = WritingOrchestrator()
    console.print(f"[cyan]正在写作（正文模型={args.tier}，知识库={'开' if args.kb else '关'}）…[/cyan]")
    try:
        req, outline, article = orchestrator.write(
            args.topic.strip(),
            use_knowledge_base=args.kb,
            model_tier=args.tier,
        )
    except Exception as e:
        console.print(f"[red]写作失败: {e}[/red]")
        return 1

    outline_text = "\n".join(
        f"## {s.section_id}. {s.title}\n{s.core_argument}" for s in outline.sections
    ) if outline.sections else "(空)"
    console.print(Panel(
        f"标题: {article.title}\n字数: {article.total_words:,} | 章节数: {len(outline.sections)} | 模型: {args.tier}\n\n{outline_text}",
        title="元信息", border_style="blue",
    ))
    console.print(Panel(article.full_text, title=article.title, border_style="green"))

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {article.title}\n\n{article.full_text}", encoding="utf-8")
        console.print(f"[green]已写入: {path}[/green]")
    return 0


# ========== 审稿 ==========

def cmd_review(args) -> int:
    from src.review_engine import ReviewOrchestrator
    text = _read_source(args)
    if not text.strip():
        console.print("[red]文章为空[/red]")
        return 1
    reviewer = ReviewOrchestrator()
    console.print(f"[cyan]六维并行审稿中（{args.tier}）…[/cyan]")
    try:
        result = reviewer.review(text, model_tier=args.tier)
        fixed = reviewer.apply_fixes(text, result, apply_level2=args.level2)
    except Exception as e:
        console.print(f"[red]审稿失败: {e}[/red]")
        return 1

    table_rows = []
    for r in result.reports:
        table_rows.append(f"- {r.agent}: {r.score:.1f}/10，{len(r.issues)} 个问题")
    console.print(Panel("\n".join(table_rows) if table_rows else "(无报告)", title="各 Agent 评分", border_style="cyan"))

    console.print(Panel(reviewer.format_report(result), title="审稿报告", border_style="yellow"))

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fixed, encoding="utf-8")
        console.print(f"[green]修改后文章已写入: {path}[/green]")
        if args.report:
            rp = Path(args.report)
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(reviewer.format_report(result), encoding="utf-8")
            console.print(f"[green]审稿报告已写入: {rp}[/green]")
    elif args.show_fixed:
        console.print(Panel(fixed, title="修改后文章", border_style="green"))
    else:
        console.print(
            f"[green]Level1 自动修改 {len(result.level1_changes)} 项；"
            f"Level2 待确认 {len(result.level2_changes)} 项；"
            f"Level3 手动指引 {len(result.level3_guidance)} 项。"
            f"（加 --out 可保存修改后文章）[/green]"
        )
    return 0


# ========== 端到端 ==========

def cmd_e2e(args) -> int:
    from src.writing_engine import WritingOrchestrator
    from src.review_engine import ReviewOrchestrator
    if not args.topic.strip():
        console.print("[red]需求不能为空[/red]")
        return 1
    orchestrator = WritingOrchestrator()
    reviewer = ReviewOrchestrator()
    console.print(f"[cyan]写作（{args.tier}）→ 审稿…[/cyan]")
    try:
        _, _, article = orchestrator.write(args.topic.strip(), use_knowledge_base=True, model_tier=args.tier)
        result = reviewer.review(article.full_text, article_id=article.article_id, model_tier=args.tier)
        fixed = reviewer.apply_fixes(article.full_text, result, apply_level2=args.level2)
    except Exception as e:
        console.print(f"[red]端到端失败: {e}[/red]")
        return 1
    console.print(f"[green]文章《{article.title}》{article.total_words:,} 字 → Level1 {len(result.level1_changes)} 项修复已应用[/green]")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(fixed, encoding="utf-8")
        Path(args.out + ".report.md").write_text(reviewer.format_report(result), encoding="utf-8")
        console.print(f"[green]成品: {args.out} | 报告: {args.out}.report.md[/green]")
    else:
        console.print(Panel(reviewer.format_report(result), title="审稿报告", border_style="yellow"))
        console.print(Panel(fixed[:2000], title="修改后文章（开头）", border_style="green"))
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("article", help="短篇写作与审稿")
    sp = p.add_subparsers(dest="action", required=True)

    def add(name, fn, help_text):
        q = sp.add_parser(name, help=help_text)
        q.set_defaults(func=fn)
        return q

    q = add("write", cmd_write, "知识增强短篇写作")
    q.add_argument("topic", help="写作需求（可含风格/字数/要素）")
    q.add_argument("--tier", default="pro", choices=["flash", "pro"])
    q.add_argument("--kb", action="store_true", default=True, help="注入知识库（默认开）")
    q.add_argument("--no-kb", dest="kb", action="store_false", help="纯 LLM 不注入知识库")
    q.add_argument("--out", default="", help="保存到文件")

    q = add("review", cmd_review, "六维审稿 + 三级修改")
    q.add_argument("file", nargs="?", default=None, help="文章文件路径")
    q.add_argument("--text", default="", help="或直接给文章文本")
    q.add_argument("--tier", default="pro", choices=["flash", "pro"])
    q.add_argument("--level2", action="store_true", help="同时应用 Level2 修改")
    q.add_argument("--show-fixed", action="store_true", help="打印修改后全文")
    q.add_argument("--out", default="", help="修改后文章写入文件")
    q.add_argument("--report", default="", help="审稿报告写入文件")

    q = add("e2e", cmd_e2e, "端到端：写作 → 审稿 → 修复")
    q.add_argument("topic", help="写作需求")
    q.add_argument("--tier", default="pro", choices=["flash", "pro"])
    q.add_argument("--level2", action="store_true")
    q.add_argument("--out", default="", help="输出前缀（将生成 <out> 与 <out>.report.md）")
