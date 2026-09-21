
"""cli.kb_commands — 板块一：文献学习 / 知识库查询 子命令。

行为对齐 Gradio：handle_learn_file（学习入库+CSV 索引）、kb_list_files（分页）、
handle_query_units（按类型查知识单元）、handle_stats。
"""
from __future__ import annotations

import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.panel import Panel
from rich.table import Table

from .common import (
    console, open_kb_conn, read_index, add_to_index, remove_from_index, estimate_tokens,
)

UPLOAD_DIR = ROOT / "data" / "user_uploads"


# ========== 学习 ==========

def cmd_learn(args) -> int:
    src = Path(args.file)
    if not src.exists():
        console.print(f"[red]文件不存在: {src}[/red]")
        return 1
    allowed = {".txt", ".md"}
    if src.suffix.lower() not in allowed:
        console.print(f"[red]仅支持 {allowed} 文件[/red]")
        return 1

    try:
        text = src.read_text("utf-8")
    except UnicodeDecodeError:
        from src.utils.file_utils import read_text_file
        text = read_text_file(str(src))
    est = estimate_tokens(len(text), src.stat().st_size)

    target = UPLOAD_DIR / src.name
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(target))

    lines = [
        "| 项目 | 预估 tokens |",
        "|------|-----------|",
        f"| Flash（轻量） | {est['flash_total']:,} |",
        f"| Pro（深度 x5） | {est['deep_total']:,} |",
        f"| 合计 | {est['total_estimated']:,} |",
    ]
    console.print(Panel("\n".join(lines), title=f"Token 预估（{src.name}，{est['file_size_bytes']/1024:.1f}KB）", border_style="cyan"))
    if not (args.lightweight or args.deep):
        console.print("[yellow]未选 --lightweight/--deep：仅做预处理入库，不调用 LLM[/yellow]")

    from src.analysis.ingestion import IngestionPipeline
    pipeline = IngestionPipeline()
    console.print("[cyan]预处理 + 入库中…[/cyan]")
    try:
        stats = pipeline.process_single_file(
            str(target),
            do_lightweight=args.lightweight,
            do_deep=args.deep,
            source_type="user",
        )
    except Exception as e:
        console.print(f"[red]学习失败: {e}[/red]")
        return 1

    console.print("[green]学习完成[/green]")
    console.print(f"- 文件: {src.name}")
    console.print(f"- 段落块: {stats['chunks']:,} 个（预处理入库，零 LLM）")
    if stats.get("lightweight"):
        console.print("- 轻量分析（Flash）: 完成")
    if stats.get("knowledge_units", 0):
        console.print(f"- 深度分析知识单元: {stats['knowledge_units']} 个")
    if not (args.lightweight or args.deep):
        console.print("[yellow]提示：纯预处理入库不生成知识单元，可加 --lightweight / --deep 补分析[/yellow]")

    try:
        add_to_index(str(target), "user", stats.get("chunks", 0), stats.get("char_count", 0))
    except Exception:
        pass
    return 0


# ========== 文件列表 ==========

def _filter_rows(rows, source_filter: str):
    if source_filter == "user":
        return [r for r in rows if r[1] == "user"]
    if source_filter == "default":
        return [r for r in rows if r[1] == "default"]
    return rows


def cmd_files(args) -> int:
    rows = _filter_rows(read_index(), args.filter)
    if args.search:
        rows = [r for r in rows if args.search in Path(r[0]).name]
    if not rows:
        console.print("[yellow]暂无匹配文件（可先运行 kb learn，或 python scripts/build_index_csv.py 重建索引）[/yellow]")
        return 0

    total = len(rows)
    per_page = args.page_size
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(args.page, total_pages))
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]

    table = Table(title=f"知识库文件（共 {total} | 第 {page}/{total_pages} 页）", header_style="bold cyan")
    for col in ["编号", "文件名", "类型", "段落块", "字符数"]:
        table.add_column(col)
    for i, (fname, stype, cc, tc) in enumerate(page_rows, start + 1):
        label = "默认" if stype == "default" else "用户"
        table.add_row(str(i), Path(fname).name, label, f"{cc:,}", f"{tc:,}")
    console.print(table)
    if args.raw:
        for fname, *_ in page_rows:
            console.print(fname)
    return 0


# ========== 查询知识单元 ==========

def cmd_query(args) -> int:
    conn = open_kb_conn()
    sql = "SELECT description, tags FROM knowledge_units WHERE type=? AND description != '' "
    params: list = [args.type]
    if args.contains:
        sql += "AND (description LIKE ? OR tags LIKE ? OR category LIKE ?) "
        kw = f"%{args.contains}%"
        params += [kw, kw, kw]
    sql += "ORDER BY length(description) DESC LIMIT ?"
    params.append(args.limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    if not rows:
        console.print("[yellow]无匹配结果[/yellow]")
        return 0
    if args.json:
        import json
        console.print(json.dumps(
            [{"description": r[0], "tags": (r[1] or "").split(",")} for r in rows],
            ensure_ascii=False, indent=2,
        ))
        return 0
    table = Table(title=f"知识单元（type={args.type}，前 {len(rows)} 条）", header_style="bold cyan")
    table.add_column("描述")
    table.add_column("标签")
    for r in rows:
        table.add_row(str(r[0])[:240], (r[1] or "")[:80])
    console.print(table)
    return 0


# ========== 统计 ==========

def cmd_stats(args) -> int:
    rows = read_index()
    console.print(f"[cyan]知识库文件索引（index.csv）: {len(rows)} 个文件[/cyan]")
    try:
        conn = open_kb_conn()
        units = conn.execute("SELECT type, COUNT(*) FROM knowledge_units GROUP BY type").fetchall()
        total_units = sum(c for _, c in units)
        chunk_total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        file_total = conn.execute("SELECT COUNT(DISTINCT source_file) FROM chunks").fetchone()[0]
        conn.close()
    except Exception as e:
        console.print(f"[red]知识库查询失败: {e}[/red]")
        return 1

    table = Table(title=f"知识单元（共 {total_units:,}）", header_style="bold cyan")
    table.add_column("类型")
    table.add_column("数量")
    for t, c in units:
        table.add_row(t, f"{c:,}")
    console.print(table)
    console.print(f"chunks 表总行数: {chunk_total:,} | 来源文件数: {file_total:,}")
    console.print("[yellow]说明：大量段落集中在 chunks 表；真正可检索的知识单元见上表。[/yellow]")
    return 0


# ========== 删除（仅用户文件） ==========

def cmd_delete(args) -> int:
    if not args.yes:
        console.print("[red]危险操作：会同时删除 DB 中该文件的段落与知识单元。请加 --yes[/red]")
        return 1
    if not args.name:
        console.print("[red]必须指定要删除的用户文件名（先运行 kb files --filter user 查看）[/red]")
        return 1
    rows = _filter_rows(read_index(), "user")
    matches = [r for r in rows if Path(r[0]).name == args.name]
    if not matches:
        console.print(f"[red]未找到用户文件: {args.name}[/red]")
        return 1

    conn = open_kb_conn()
    for fname, stype, cc, tc in matches:
        conn.execute("DELETE FROM knowledge_units WHERE source_file = ?", (fname,))
        conn.execute("DELETE FROM chunks WHERE source_file = ?", (fname,))
        remove_from_index(fname)
        console.print(f"[green]已删除: {Path(fname).name}（{cc:,} 块 / {tc:,} 字符）[/green]")
    conn.commit()
    conn.close()
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("kb", help="板块一：文献学习与知识库")
    sp = p.add_subparsers(dest="action", required=True)

    def add(name, fn, help_text):
        q = sp.add_parser(name, help=help_text)
        q.set_defaults(func=fn)
        return q

    q = add("learn", cmd_learn, "学习一个文件（预处理必需 + 可选轻量/深度分析）")
    q.add_argument("file")
    q.add_argument("--lightweight", action="store_true", help="轻量分析（Flash）")
    q.add_argument("--deep", action="store_true", help="深度分析（四层）")
    q.add_argument("--tier", default="pro", choices=["flash", "pro"], help="深度分析模型层级")

    q = add("files", cmd_files, "列出知识库文件（分页/筛选/搜索）")
    q.add_argument("--filter", default="all", choices=["all", "user", "default"])
    q.add_argument("--page", type=int, default=1)
    q.add_argument("--page-size", type=int, default=50)
    q.add_argument("--search", default="", help="按文件名关键字过滤")
    q.add_argument("--raw", action="store_true", help="同时输出完整路径")

    q = add("query", cmd_query, "查询知识单元（按类型，可按关键字过滤）")
    q.add_argument("--type", required=True, choices=["idea", "structure", "technique", "language"])
    q.add_argument("--limit", type=int, default=10)
    q.add_argument("--contains", default="", help="描述/标签/类别含该关键字")
    q.add_argument("--json", action="store_true")

    q = add("stats", cmd_stats, "知识库统计")

    q = add("delete", cmd_delete, "删除用户文件（默认/文献文件不可删）")
    q.add_argument("name", help="用户文件名（kb files --filter user 查看）")
    q.add_argument("--yes", action="store_true")
