
"""cli.common — TUI 共享工具：项目加载、CSV 索引、通用渲染。

设计说明：命令式 CLI 每个进程只跑一条命令，因此不维护跨命令的内存态；
需要"当前项目"的命令都通过 load_bundle() 从磁盘恢复完整状态
（项目 + 角色引擎 + 剧情引擎 + 写作器），与 Gradio 版 novel_load 对齐。
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
CSV_PATH = ROOT / "data" / "knowledge" / "index.csv"


def ensure_utf8() -> None:
    """Windows 控制台缺省可能是 GBK，强制 UTF-8 输出。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ========== 项目加载 ==========

def load_bundle(name: str, base_dir: str = "data/projects"):
    """加载项目及其角色引擎、剧情引擎、写作器（不调用任何 LLM）。

    实现统一放在 NovelService.load()：命令行与交互界面共用一套编排，
    避免两处逻辑各自漂移（本函数只做旧的四元组返回格式兼容）。
    """
    from src.novel.service import NovelService

    bundle = NovelService(base_dir).load(name)
    return bundle.project, bundle.engine, bundle.plot, bundle.writer


def create_project(name: str, genre: str = "", desc: str = "") -> tuple:
    """新建项目（对齐 gradio novel_create）。编排同样复用服务层。"""
    from src.novel.service import NovelService

    service = NovelService()
    result = service.create(name, genre, desc)
    if not result.ok:
        raise RuntimeError(result.title)
    bundle = service.load(name)
    return bundle.project, bundle.engine, bundle.plot, bundle.writer


def project_summary(name: str, base_dir: str = "data/projects") -> dict:
    """轻量读取 project.json 做列表展示（不整章加载）。"""
    path = Path(base_dir) / name / "project.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except Exception:
        return {}
    md = data.get("metadata", {})
    return {
        "name": name,
        "title": data.get("title", name),
        "genre": data.get("genre", ""),
        "description": data.get("description", ""),
        "chapters": len(data.get("chapters", {})),
        "words": md.get("total_words", 0),
    }


# ========== 知识库文件索引（与 gradio 的 CSV 索引同格式） ==========

def read_index() -> list:
    """读取 index.csv（制表符分隔）。返回 [(source_file, type, chunks, chars), ...]。"""
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return []
    rows = []
    try:
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            header = f.readline()
            if not header.startswith("source_file"):
                return []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 4:
                    try:
                        rows.append((parts[0], parts[1], int(parts[2]), int(parts[3])))
                    except ValueError:
                        continue
    except Exception:
        return []
    return rows


def write_index(rows: list) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", encoding="utf-8") as f:
        f.write("source_file\ttype\tchunks\tchars\n")
        for sf, st, cc, ch in rows:
            f.write(f"{sf}\t{st}\t{cc}\t{ch}\n")


def add_to_index(source_file: str, source_type: str, chunks: int, chars: int) -> None:
    rows = read_index()
    for i, (sf, st, cc, ch) in enumerate(rows):
        if sf == source_file:
            rows[i] = (source_file, source_type, chunks, chars)
            break
    else:
        rows.append((source_file, source_type, chunks, chars))
    rows.sort(key=lambda r: (r[1], r[0]))
    write_index(rows)


def remove_from_index(source_file: str) -> None:
    write_index([r for r in read_index() if r[0] != source_file])


# ========== 知识库连接 ==========

def open_kb_conn():
    """打开 SQLite 知识库连接（懒加载配置）。"""
    from src.knowledge_base import init_db
    from config.settings import get_config
    path = get_config().database.get("path", "data/knowledge/writing_expert_new.db")
    return init_db(path)


# ========== 展示辅助 ==========

def render_project_table(sums: list[dict]) -> None:
    table = Table(title="项目列表", header_style="bold cyan")
    for col in ["名称", "题材", "简介", "章节", "总字数"]:
        table.add_column(col)
    for s in sums:
        table.add_row(
            s["name"],
            s.get("genre") or "-",
            (s.get("description") or "-")[:24],
            str(s.get("chapters", 0)),
            f"{s.get('words', 0):,}",
        )
    console.print(table)


def print_llm_summary() -> None:
    """命令结束后打印本进程产生的 LLM 开销。"""
    try:
        from src.utils.cost_tracker import get_tracker
        t = get_tracker()
        if t.total_calls > 0:
            console.print(Panel(t.markdown_summary(), title="LLM 调用统计", border_style="cyan"))
    except Exception:
        pass


def estimate_tokens(char_count: int, file_size_bytes: int = 0) -> dict:
    """估算学习一个文件所需的 token（与 Gradio 版一致）。"""
    flash_in = int(min(2000, char_count) / 1.5)
    flash_out = 300
    flash_total = flash_in + flash_out
    deep_chars = min(10000, char_count)
    deep_in_per = int(deep_chars / 1.5)
    deep_out_per = 500
    deep_total = (deep_in_per + deep_out_per) * 4 + (deep_in_per * 2 + 800)
    return {
        "flash_in": flash_in, "flash_out": flash_out, "flash_total": flash_total,
        "deep_in_per_layer": deep_in_per, "deep_out_per_layer": deep_out_per,
        "deep_total": deep_total, "total_estimated": flash_total + deep_total,
        "char_count": char_count, "file_size_bytes": file_size_bytes,
    }


def first_lines(text: str, n: int = 6) -> str:
    return "\n".join(text.strip().splitlines()[:n])
