"""
api.gradio_app — 三板块一体化界面（含开销追踪 + 导入导出）。
"""

import gradio as gr
import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from src.writing_engine import WritingOrchestrator, KnowledgeBridge
from src.review_engine import ReviewOrchestrator
from src.utils.logger import logger
from src.utils.cost_tracker import get_tracker
from src.utils.llm_client import LLMClient
from src.novel import CharacterEngine, NovelProject, ChapterWriter
from src.novel.plot_engine import PlotEngine
from src.novel.project_manager import OutlineItem
from src.novel.character_engine import CharacterProfile
from src.analysis.ingestion import IngestionPipeline
from src.knowledge_base import init_db
from config.settings import get_config
from src.models import ReviewIssue
from src.review_engine.orchestrator import AggregatedReview

orchestrator = WritingOrchestrator()
reviewer = ReviewOrchestrator()
bridge = KnowledgeBridge()


# ========== 导入导出 ==========

def export_text(content: str, filename: str, fmt: str) -> str:
    """导出为文件（返回路径）。"""
    ext = ".md" if fmt == "md" else ".txt"
    path = Path(f"data/exports/{filename}{ext}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def import_file(filepath: str) -> str:
    """导入文件。"""
    path = Path(filepath)
    if not path.exists():
        return "文件不存在"
    return path.read_text("utf-8")


# ========== 开销面板 ==========

def cost_panel():
    t = get_tracker()
    return t.markdown_summary() if t.total_calls > 0 else "暂无 LLM 调用记录"


# ========== 板块一：文献学习 ==========

def handle_query_units(type_name: str, limit: int):
    rows = bridge.conn.execute(
        "SELECT description, tags FROM knowledge_units "
        "WHERE type=? AND description != '' ORDER BY length(description) DESC LIMIT ?",
        (type_name, limit),
    ).fetchall()
    if not rows:
        return "无匹配结果"
    lines = []
    for r in rows:
        lines.append(f"- {str(r[0])[:300]}")
        if r[1]:
            lines.append(f"  tags: {r[1][:100]}")
    return "\n".join(lines)


def handle_stats():
    rows = bridge.conn.execute("SELECT type, COUNT(*) FROM knowledge_units GROUP BY type").fetchall()
    lines = ["| 类型 | 数量 |", "|------|------|"]
    for t, c in rows:
        lines.append(f"| {t} | {c} |")
    total = sum(r[1] for r in rows)
    lines.append(f"| **合计** | **{total}** |")
    return "\n".join(lines)



def estimate_tokens(file_size_bytes: int, char_count: int) -> dict:
    """根据文件大小和字符数估算 Token 消耗。"""
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


def handle_learn_file(file, do_lightweight: bool, do_deep: bool):
    """上传文件并学习入库。"""
    if file is None:
        return "请先选择文件", "等待选择文件...", cost_panel()
    fp = Path(file.name if hasattr(file, 'name') else str(file))
    allowed = {".txt", ".md"}
    if fp.suffix.lower() not in allowed:
        return f"不支持的文件格式 {fp.suffix}", "", cost_panel()
    try:
        text = fp.read_text("utf-8")
        est = estimate_tokens(fp.stat().st_size, len(text))
        upload_dir = Path("data/user_uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / fp.name
        import shutil
        shutil.copy2(str(fp), str(target))
        pipeline = IngestionPipeline()
        stats = pipeline.process_single_file(str(target), do_lightweight, do_deep, source_type="user")
        result = f"### 学习完成\n**文件**: {target.name}\n**段落块**: {stats['chunks']} 个"
        if stats.get("lightweight"):
            result += "\n**轻量分析**: 完成"
        if stats.get("knowledge_units", 0):
            result += f"\n**知识单元**: {stats['knowledge_units']} 个"
        est_md = (
            f"**Token 预估**\n\n"
            f"| 类型 | Input | Output | 合计 |\n"
            f"|------|-------|--------|------|\n"
            f"| Flash | {est['flash_in']:,} | {est['flash_out']:,} | {est['flash_total']:,} |\n"
            f"| Pro | {est['deep_in_per_layer']:,}x5 | {est['deep_out_per_layer']:,}x4+800 | {est['deep_total']:,} |\n"
            f"| **总计** | | | **{est['total_estimated']:,}** |\n\n"
            f"文件: {est['file_size_bytes']/1024:.1f}KB | 字符: {est['char_count']:,}"
        )
        return result, est_md, cost_panel()
    except Exception as e:
        return f"学习失败: {e}", "", cost_panel()
    finally:
        # 增量更新 CSV 索引
        try:
            if 'target' in dir() and target:
                stats = locals().get('stats', {})
                _add_to_csv(str(target), "user", stats.get('chunks', 0), stats.get('char_count', 0))
        except Exception:
            pass

_CSV_PATH = Path("data/knowledge/index.csv")

def _rebuild_csv():
    """从 DB 全量重建 CSV 索引（制表符分隔）。
    若 DB 不可用或 chunks 表为空，创建空索引文件。
    若 chunks 表行数过多（>10万），跳过重建并提示用户手动运行 build_index_csv.py。"""
    _CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        # 先检查 chunks 行数，避免长时间 GROUP BY
        count = bridge.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        if count > 100000:
            # 数据库太大，跳过重建，写一个提示文件
            with open(_CSV_PATH, "w", encoding="utf-8") as f:
                f.write("source_file\ttype\tchunks\tchars\n")
            logger.warning(
                f"chunks 表有 {count:,} 行，跳过自动重建 CSV。"
                f"请手动运行: python scripts/build_index_csv.py"
            )
            return
        rows = bridge.conn.execute(
            "SELECT source_file, source_type, COUNT(*) as cc, SUM(char_count) as tc "
            "FROM chunks GROUP BY source_file ORDER BY source_type, source_file"
        ).fetchall()
    except Exception as e:
        logger.warning(f"重建 CSV 索引时查询失败（数据库可能为空）: {e}")
        rows = []
    with open(_CSV_PATH, "w", encoding="utf-8") as f:
        f.write("source_file\ttype\tchunks\tchars\n")
        for sf, st, cc, tc in rows:
            f.write(f"{sf}\t{st}\t{cc}\t{tc or 0}\n")

def _read_csv():
    """读取 CSV 索引（制表符分隔）。返回 [(source_file, type, chunks, chars), ...]
    若 CSV 不存在或损坏，自动重建。"""
    if not _CSV_PATH.exists() or _CSV_PATH.stat().st_size == 0:
        _rebuild_csv()
    rows = []
    try:
        with open(_CSV_PATH, "r", encoding="utf-8") as f:
            header = f.readline()
            if not header.startswith("source_file"):
                _rebuild_csv()
                return _read_csv()
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
    except Exception as e:
        logger.warning(f"读取 CSV 失败，将重建: {e}")
        _rebuild_csv()
        return _read_csv()
    return rows

def _add_to_csv(source_file, source_type, chunks, chars):
    rows = _read_csv()
    for i, (sf, st, cc, ch) in enumerate(rows):
        if sf == source_file:
            rows[i] = (source_file, source_type, chunks, chars)
            break
    else:
        rows.append((source_file, source_type, chunks, chars))
    rows.sort(key=lambda r: (r[1], r[0]))
    with open(_CSV_PATH, "w", encoding="utf-8") as f:
        f.write("source_file\ttype\tchunks\tchars\n")
        for sf, st, cc, ch in rows:
            f.write(f"{sf}\t{st}\t{cc}\t{ch}\n")

def _remove_from_csv(source_file):
    rows = [r for r in _read_csv() if r[0] != source_file]
    with open(_CSV_PATH, "w", encoding="utf-8") as f:
        f.write("source_file\ttype\tchunks\tchars\n")
        for sf, st, cc, ch in rows:
            f.write(f"{sf}\t{st}\t{cc}\t{ch}\n")

def kb_list_files(source_filter: str = "all", page: int = 1):
    """列出知识库文件（分页，每页 50 条，带编号）。从 CSV 索引读取。"""
    try:
        all_rows = _read_csv()
        if source_filter == "user":
            all_rows = [r for r in all_rows if r[1] == "user"]
        elif source_filter == "default":
            all_rows = [r for r in all_rows if r[1] == "default"]
        if not all_rows:
            # CSV 可能为空（尚未运行 build_index_csv.py）
            if _CSV_PATH.exists() and _CSV_PATH.stat().st_size < 200:
                return "⚠️ CSV 索引为空。请运行 `python scripts/build_index_csv.py` 生成文件索引", page
            return "暂无已导入的文件", page
        per_page = 50
        total = len(all_rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        page_rows = all_rows[start:start + per_page]
        lines = [
            f"**共 {total} 个文件 | 第 {page}/{total_pages} 页**",
            "",
            "| 编号 | 文件名 | 类型 | 段落块 | 字符数 |",
            "|------|--------|------|--------|--------|",
        ]
        for i, (fname, stype, cc, tc) in enumerate(page_rows, start + 1):
            label = "📖" if stype == "default" else "👤"
            name = Path(fname).name
            lines.append(f"| **{i}** | `{name}` | {label} | {cc:,} | {tc:,} |")
        return "\n".join(lines), page
    except Exception as e:
        msg = str(e) or "未知错误（请确认 data/knowledge/index.csv 可正常读写）"
        return f"查询失败: {msg}", page


def kb_delete_file(indices_text: str, source_filter: str, page: int):
    """按编号删除文件。支持 1,3,5 / 1-10 / all。仅用户文件可删。"""
    logger.info(f"删除请求: indices={indices_text!r}, filter={source_filter!r}, page={page}")
    if not indices_text or not indices_text.strip():
        return "请输入编号", page
    try:
        rows = _read_csv()
        if source_filter == "user":
            rows = [r for r in rows if r[1] == "user"]
        elif source_filter == "default":
            rows = [r for r in rows if r[1] == "default"]
        if not rows:
            return "暂无文件", page
        total = len(rows)
        indices = set()
        if indices_text.strip().lower() == "all":
            indices = set(range(1, total + 1))
        else:
            for part in indices_text.split(","):
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    try:
                        a, b = part.split("-", 1)
                        indices.update(range(int(a.strip()), int(b.strip()) + 1))
                    except ValueError:
                        continue
                else:
                    try:
                        idx = int(part)
                        if 1 <= idx <= total:
                            indices.add(idx)
                    except ValueError:
                        continue
        if not indices:
            return "未匹配到有效编号", page
        logger.info(f"解析得到 {len(indices)} 个索引: {sorted(indices)}")
        deleted = []
        skipped = []
        for idx in sorted(indices):
            if 1 <= idx <= total:
                fname = rows[idx - 1][0]
                stype = rows[idx - 1][1]
                name = Path(fname).name
                if stype == "default":
                    logger.warning(f"跳过默认文件 [{idx}]: {name}")
                    skipped.append(name)
                else:
                    logger.info(f"删除用户文件 [{idx}]: {name}")
                    conn = bridge.conn
                    conn.execute("DELETE FROM knowledge_units WHERE source_file = ?", (fname,))
                    conn.execute("DELETE FROM chunks WHERE source_file = ?", (fname,))
                    conn.commit()
                    _remove_from_csv(fname)
                    deleted.append(name)
        logger.info(f"删除完成: deleted={len(deleted)}, skipped={len(skipped)}")
        parts = []
        if deleted:
            parts.append(f"已删除 {len(deleted)} 个: {'、'.join(deleted)}")
        if skipped:
            parts.append(f"跳过 {len(skipped)} 个默认文件: {'、'.join(skipped[:5])}{'...' if len(skipped)>5 else ''}")
        remaining = _read_csv()
        if source_filter == "user":
            remaining = [r for r in remaining if r[1] == "user"]
        elif source_filter == "default":
            remaining = [r for r in remaining if r[1] == "default"]
        total_pages = max(1, (len(remaining) + 49) // 50)
        if page > total_pages:
            page = total_pages
        return "；".join(parts) if parts else "无匹配项", page
    except Exception as e:
        logger.error(f"删除失败: {e}")
        return f"删除失败: {e}", page


# ========== 板块二：AI 写作 ==========

def handle_write(user_input, use_kb, model_tier):
    if not user_input.strip():
        return "请输入", "", cost_panel()
    try:
        req, outline, article = orchestrator.write(
            user_input.strip(), use_knowledge_base=use_kb,
        )
        article_text = f"# {article.title}\n\n{article.full_text}"
        outline_text = "\n".join(
            f"## {s.section_id}. {s.title}\n{s.core_argument}"
            for s in outline.sections
        ) if outline.sections else "(空)"
        kb_note = "✅ 知识库" if use_kb else "ℹ️ 纯 LLM"
        meta = (
            f"**字数**: {article.total_words}  |  **模型**: {model_tier}  |  {kb_note}\n\n"
            f"### 大纲\n{outline_text}"
        )
        return article_text, meta, cost_panel(), article_text
    except Exception as e:
        return f"**错误**: {str(e)}", "", cost_panel(), ""


# ========== 板块三：审稿 ==========

def handle_review(article_text):
    if not article_text.strip():
        return "无", "无", "无", "无", "", cost_panel()
    try:
        result = reviewer.review(article_text)
        fixed = reviewer.apply_fixes(article_text, result)
        l1 = "\n".join(f"- {i.description}" for i in result.level1_changes) or "无"
        l2 = "\n".join(f"- {i.description}\n  建议: {i.suggestion}" for i in result.level2_changes) or "无"
        l3 = "\n".join(f"- [{i.agent}] {i.description}\n  指引: {i.suggestion}" for i in result.level3_guidance) or "无"
        rpt = reviewer.format_report(result)
        return l1, l2, l3, rpt, fixed, cost_panel()
    except Exception as e:
        return f"错误: {e}", "", "", "", "", cost_panel()


def _get_chapter_for_review(chapter_num: int) -> tuple:
    """从长篇小说项目中提取指定章节内容用于审稿。"""
    global _novel_project
    if not _novel_project:
        return "请先加载项目", "", 0
    ch = int(chapter_num)
    if ch not in _novel_project.chapters:
        return f"第{ch}章暂未撰写", "", ch
    title = _novel_project.chapter_titles.get(ch, f"第{ch}章")
    text = _novel_project.chapters[ch]
    ftext = f"# {title}\n\n{text}"
    return ftext, title, ch


def handle_e2e(user_input):
    if not user_input.strip():
        return "请输入", "", cost_panel()
    try:
        _, _, article = orchestrator.write(user_input.strip(), use_knowledge_base=True)
        result = reviewer.review(article.full_text, article_id=article.article_id)
        fixed = reviewer.apply_fixes(article.full_text, result)
        report = reviewer.format_report(result)
        return fixed, report, cost_panel()
    except Exception as e:
        return f"错误: {e}", "", cost_panel()


# ========== 长篇小说工作台 ==========

_novel_project: NovelProject = None
_novel_engine: CharacterEngine = None
_novel_writer: ChapterWriter = None
_novel_plot: PlotEngine = None

def _build_chars_markdown() -> str:
    """构建角色状态的 Markdown 文本。"""
    if not _novel_engine:
        return ""
    lines = []
    for c in _novel_engine.all_characters():
        lines.append(f"**{c.name}** ({c.role}) 情绪={c.current_mood}")
        lines.append(f"人格: {c.personality_summary()}")
        if c.relationships:
            rels = []
            for k, v in c.relationships.items():
                if isinstance(v, dict):
                    rels.append(f"{k}({v.get('状态','')})")
                else:
                    rels.append(f"{k}({v})")
            lines.append(f"关系: {', '.join(rels)}")
        lines.append("")
    return "\n".join(lines) if lines else "暂无角色"


def novel_load(name: str):
    global _novel_project, _novel_engine, _novel_writer, _novel_plot
    try:
        _novel_project = NovelProject.load("data/projects", name)
        _novel_engine = CharacterEngine()
        _novel_plot = PlotEngine()
        char_file = _novel_project.base_dir / "characters.json"
        plot_file = _novel_project.base_dir / "plots.json"
        if char_file.exists():
            _novel_engine.load(str(char_file))
        if plot_file.exists():
            _novel_plot.load(str(plot_file))
        _novel_writer = ChapterWriter(_novel_project, _novel_engine)
        chs = _novel_project.list_chapters()
        lines = ["| 章节 | 标题 | 状态 | 字数 |", "|------|------|------|------|"]
        for c in chs:
            lines.append(f"| {c.number} | {c.title} | {c.status} | {c.word_count} |")
        full_novel = _novel_project.export_novel() if _novel_project.chapters else "尚未撰写任何章节"
        chars_md = _build_chars_markdown()
        chars_json = json.dumps(
            {c.name: c.to_dict() for c in _novel_engine.all_characters()},
            ensure_ascii=False, indent=2,
        ) if _novel_engine.all_characters() else "{}"
        return "\n".join(lines), chars_md, chars_json, full_novel
    except Exception as e:
        return f"加载失败: {e}", "", "{}", ""

def novel_create(name: str, genre: str, desc: str):
    global _novel_project, _novel_engine, _novel_writer, _novel_plot
    try:
        _novel_project = NovelProject(name)
        _novel_project.genre = genre
        _novel_project.description = desc
        _novel_engine = CharacterEngine()
        _novel_plot = PlotEngine()
        _novel_writer = ChapterWriter(_novel_project, _novel_engine)
        _novel_project.save()
        choices = NovelProject.list_projects()
        return f"项目「{name}」已创建", gr.Dropdown(choices=choices, value=name)
    except Exception as e:
        return f"创建失败: {e}", gr.Dropdown()

def novel_refresh_projects():
    choices = NovelProject.list_projects()
    return gr.Dropdown(choices=choices)

def novel_delete(selected: str):
    if not selected:
        return "请先选择要删除的项目", gr.update()
    try:
        ok = NovelProject.delete("data/projects", selected)
        if ok:
            names = NovelProject.list_projects()
            return f"项目「{selected}」已删除", gr.update(choices=names, value=None)
        return "删除失败：项目不存在", gr.update()
    except Exception as e:
        return f"删除失败: {e}", gr.update()

def novel_list():
    try:
        names = NovelProject.list_projects()
        return "\n".join(f"- {n}" for n in names) if names else "暂无项目"
    except:
        return "暂无项目"

# ---- 阶段 1：大纲生成 ----

def novel_stage1_outline(total_chapters: int, instructions: str):
    if not _novel_writer:
        return "请先创建/加载项目", ""
    try:
        get_tracker().snapshot()
        items = _novel_writer.generate_outline(total_chapters, instructions)
        lines = []
        for item in items:
            lines.append(f"第{item.chapter}章「{item.title}」: {item.expected_content}")
            if item.key_foreshadowing:
                lines.append(f"  伏笔: {'; '.join(item.key_foreshadowing)}")
        outline_text = "\n".join(lines)
        return outline_text, get_tracker().delta_summary()
    except Exception as e:
        return f"大纲生成失败: {e}", ""

def novel_save_outline(outline_text: str):
    if not _novel_project:
        return "请先创建/加载项目", gr.update()
    try:
        import re
        items = []
        for line in outline_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r'第(\d+)章[「【]\s*(.+?)\s*[」】]\s*[：:]\s*(.+)', line)
            if m:
                from src.novel.project_manager import OutlineItem
                items.append(OutlineItem(
                    chapter=int(m.group(1)),
                    title=m.group(2),
                    expected_content=m.group(3),
                    key_foreshadowing=[],
                ))
        if items:
            _novel_project.set_outline(items)
            _novel_project.save()
            return f"大纲已保存（{len(items)} 章）", outline_text
        return "解析失败：未识别到有效大纲行", gr.update()
    except Exception as e:
        return f"保存失败: {e}", gr.update()


# ---- 剧情保存 ----

def novel_save_plot(plot_text: str, chapter_num: int):
    if not _novel_project:
        return "请先创建/加载项目"
    try:
        from src.novel.plot_engine import ChapterPlot
        plot = _novel_plot.plots.get(chapter_num)
        if not plot:
            plot = ChapterPlot(chapter_num)
        plot.user_notes = plot_text
        _novel_plot.plots[chapter_num] = plot
        _novel_plot.save(str(_novel_project.base_dir / "plots.json"))
        return f"第{chapter_num}章剧情已保存 ✅"
    except Exception as e:
        return f"保存失败: {e}"


# ---- 角色保存 ----

def novel_save_characters():
    if not _novel_engine or not _novel_project:
        return "请先加载项目"
    _novel_engine.save(str(_novel_project.base_dir / "characters.json"))
    return "角色系统已保存 ✅"


# ---- 全局保存 ----

def novel_save_all():
    if not _novel_project:
        return "请先创建/加载项目"
    try:
        _novel_project.save()
        if _novel_engine:
            _novel_engine.save(str(_novel_project.base_dir / "characters.json"))
        if _novel_plot:
            _novel_plot.save(str(_novel_project.base_dir / "plots.json"))
        return "全部已保存 ✅"
    except Exception as e:
        return f"保存失败: {e}"

# ---- 阶段 2：角色系统生成 ----

def novel_stage2_characters():
    if not _novel_project:
        return "请先创建项目并生成大纲", "{}", ""
    try:
        get_tracker().snapshot()
        # 保存已有角色的逐章事件
        existing_events = {}
        for c in _novel_engine.all_characters():
            if c.chapter_events:
                existing_events[c.name] = c.chapter_events

        chars, world = _novel_plot.design_characters(
            _novel_project.title, _novel_project.genre,
            _novel_project.description, _novel_project.get_outline_context()
        )
        # 填充到引擎
        for cd in chars:
            if not isinstance(cd, dict):
                continue
            from src.novel.character_engine import CharacterProfile
            profile = CharacterProfile(
                name=cd["name"], role=cd.get("role", ""),
                personality=cd.get("personality", {}),
                speaking_style=cd.get("speaking_style", ""),
                core_desire=cd.get("core_desire", ""), core_fear=cd.get("core_fear", ""),
                background=cd.get("background", ""), appearance=cd.get("appearance", ""),
                relationships=cd.get("relationships", {}),
                arc_summary=cd.get("arc_summary", ""),
            )
            _novel_engine.add_character(profile)

        # 恢复已有角色的逐章事件（不覆盖）
        for name, events in existing_events.items():
            if name in _novel_engine._characters and not _novel_engine._characters[name].chapter_events:
                _novel_engine._characters[name].chapter_events = events

        _novel_engine.save(str(_novel_project.base_dir / "characters.json"))
        _novel_plot.save(str(_novel_project.base_dir / "plots.json"))

        lines = ["### 角色列表", ""]
        for c in _novel_engine.all_characters():
            lines.append(f"**{c.name}** ({c.role})")
            lines.append(f"- 人格: {c.personality_summary()}")
            if c.speaking_style:
                lines.append(f"- 说话风格: {c.speaking_style}")
            if c.core_desire:
                lines.append(f"- 核心欲望: {c.core_desire}")
            if c.core_fear:
                lines.append(f"- 核心恐惧: {c.core_fear}")
            if c.relationships:
                rels = []
                for k, v in c.relationships.items():
                    if isinstance(v, dict):
                        status = v.get("状态", "")
                        rels.append(f"{k}({status})")
                    else:
                        rels.append(f"{k}({v})")
                lines.append(f"- 关系: {', '.join(rels)}")
            lines.append("")

        lines.append("### 世界观设定")
        lines.append(f"- 时间线: {_novel_plot.world.timeline}")
        lines.append(f"- 地理: {_novel_plot.world.geography}")
        lines.append(f"- 力量体系: {_novel_plot.world.power_system}")
        lines.append(f"- 势力: {', '.join(_novel_plot.world.factions)}")

        # 角色 JSON 用于编辑
        chars_json = json.dumps(
            {c.name: c.to_dict() for c in _novel_engine.all_characters()},
            ensure_ascii=False, indent=2,
        )
        return "\n".join(lines), chars_json, get_tracker().delta_summary()
    except Exception as e:
        return f"角色生成失败: {e}", "{}", ""

# ---- 阶段 3：剧情设计 ----

def novel_stage3_plot(chapter_num: int):
    if not _novel_project:
        return "请先创建项目并生成大纲"
    try:
        get_tracker().snapshot()
        outline = _novel_project.outline
        item = None
        for o in outline:
            if o.chapter == chapter_num:
                item = o
                break
        if not item:
            return f"大纲中没有第{chapter_num}章", ""

        prev_summary = _novel_project.get_recap(chapter_num)
        plot = _novel_plot.design_chapter_plot(
            chapter_num,
            {"title": item.title, "expected_content": item.expected_content},
            prev_summary,
            _novel_project.foreshadowing,
        )
        _novel_plot.save(str(_novel_project.base_dir / "plots.json"))
        return plot.to_prompt_text(), get_tracker().delta_summary()
    except Exception as e:
        return f"剧情设计失败: {e}", ""

# ---- 一键自动生成 ----

def novel_auto_generate(total_chapters: int, target_words: int, progress=gr.Progress()):
    """一键生成完整项目：大纲->角色->逐章剧情+写作。"""
    if not _novel_project:
        yield "请先创建或加载项目", "", ""
        return

    total_steps = 2 + total_chapters * 2
    step = 0
    status_lines = ["## 一键自动生成", "", ""]

    # 阶段 1：大纲
    step += 1
    progress(step / total_steps, desc=f"生成大纲 ({total_chapters}章)")
    outline_text, _ = novel_stage1_outline(total_chapters, _novel_project.description or "自动生成故事")
    status_lines.append(f"[阶段1] 大纲已生成 ({total_chapters}章)")
    yield "\n".join(status_lines), outline_text, ""

    # 阶段 2：角色
    step += 1
    progress(step / total_steps, desc="生成角色系统")
    chars_md, chars_json, _ = novel_stage2_characters()
    status_lines.append("[阶段2] 角色系统已生成")
    yield "\n".join(status_lines), outline_text, ""

    # 逐章
    for ch in range(1, total_chapters + 1):
        # 剧情设计
        step += 1
        progress(step / total_steps, desc=f"设计第{ch}章剧情")
        plot_text, _ = novel_stage3_plot(ch)
        status_lines.append(f"[第{ch}章] 剧情已设计")
        yield "\n".join(status_lines), outline_text, ""

        # 写作
        step += 1
        progress(step / total_steps, desc=f"撰写第{ch}章 ({target_words}字)")
        chars_status, cost, write_status, full_novel, _ = novel_stage4_write(ch, "", target_words)
        status_lines.append(f"[第{ch}章] 写作完成")
        yield "\n".join(status_lines), outline_text, full_novel

    # 最终保存
    novel_save_all()
    status_lines.append("")
    status_lines.append("---")
    status_lines.append("全部完成！")
    full_novel = _novel_project.export_novel() if _novel_project else ""
    yield "\n".join(status_lines), outline_text, full_novel

def novel_stage4_write(chapter_num: int, instructions: str, target_words: int):
    if not _novel_writer:
        return "请先完成前置步骤", cost_panel(), "", "", ""
    try:
        get_tracker().snapshot()
        plot = _novel_plot.plots.get(chapter_num)
        plot_text = ""
        if plot:
            plot_text = "\n\n## 本章剧情设计（请严格遵循）\n" + plot.to_prompt_text()
            for fp in plot.foreshadowing_planted:
                _novel_project.add_foreshadowing(fp)
            for fr in plot.foreshadowing_resolved:
                _novel_project.resolve_foreshadowing(fr)

        _novel_writer.write_chapter(chapter_num, instructions + plot_text, target_words)
        full_novel = _novel_project.export_novel()
        chars_status = _build_chars_markdown()
        wc = len(_novel_project.chapters.get(chapter_num, ""))
        status = f"第{chapter_num}章写作完成（{wc}字）"
        cost_delta = get_tracker().delta_summary()
        return chars_status, cost_panel(), status, full_novel, cost_delta
    except Exception as e:
        return f"写作失败: {e}", cost_panel(), f"写作失败: {e}", "", ""

def _novel_chars_summary() -> str:
    if not _novel_engine:
        return ""
    lines = []
    for c in _novel_engine.all_characters():
        lines.append(f"**{c.name}** 情绪={c.current_mood} 人格={c.personality_summary()}")
    return "\n".join(lines) if lines else "暂无角色"

def _novel_chapter_list() -> str:
    """章节超链接列表。"""
    if not _novel_project:
        return ""
    lines = []
    for num in sorted(_novel_project.chapters.keys()):
        title = _novel_project.chapter_titles.get(num, "")
        wc = len(_novel_project.chapters[num])
        lines.append(f"第{num}章「{title}」({wc}字)")
    return "\n".join(lines)

def novel_export():
    if not _novel_project:
        return ""
    path = _novel_project.base_dir / "export.txt"
    path.write_text(_novel_project.export_novel(), encoding="utf-8")
    return str(path)

# 角色编辑
def novel_update_chars(chars_json: str):
    global _novel_engine
    if not chars_json.strip():
        return "JSON 为空"
    try:
        data = json.loads(chars_json)
        from src.novel.character_engine import CharacterProfile
        for name, cd in data.items():
            profile = CharacterProfile(
                name=cd["name"], role=cd.get("role", ""),
                personality=cd.get("personality", {}),
                speaking_style=cd.get("speaking_style", ""),
                core_desire=cd.get("core_desire", ""), core_fear=cd.get("core_fear", ""),
                background=cd.get("background", ""), appearance=cd.get("appearance", ""),
                relationships=cd.get("relationships", {}),
                arc_summary=cd.get("arc_summary", ""),
            )
            _novel_engine.add_character(profile)
        _novel_engine.save(str(_novel_project.base_dir / "characters.json"))
        return "角色已更新 ✅"
    except Exception as e:
        return f"解析失败: {e}"


# ========== App ==========

def create_app():
    with gr.Blocks(title="小说写作专家系统") as app:
        gr.Markdown("# ✍️ 小说写作专家系统")
        gr.Markdown("知识驱动型 AI 写作辅助工具 — 学习 / 写作 / 审稿 一体")

        # 全局状态：开销面板 + 文章状态
        cost_md = gr.Markdown(value=cost_panel())
        article_state = gr.State(value="")  # 跨 Tab 共享文章内容

        with gr.Tabs():

            # ===== 板块一 =====
            with gr.Tab("📖 板块一 · 文献学习"):
                # 知识库管理
                gr.Markdown("### 知识库管理")
                with gr.Accordion("上传学习", open=True):
                    learn_file = gr.File(label="选择文件", file_types=[".txt", ".md"])
                    with gr.Row():
                        learn_lw = gr.Checkbox(label="轻量分析 (Flash)", value=True)
                        learn_dp = gr.Checkbox(label="深度分析 (Pro)", value=True)
                    learn_btn = gr.Button("开始学习", variant="primary")
                    learn_token_est = gr.Markdown(value="等待选择文件...")
                    learn_result = gr.Markdown()

                    def _on_file_select(f):
                        if f is None:
                            return "等待选择文件..."
                        fp = Path(f.name if hasattr(f, 'name') else str(f))
                        if fp.suffix.lower() not in {".txt", ".md"}:
                            return "仅支持 .txt / .md 文件"
                        try:
                            text = fp.read_text("utf-8")
                            est = estimate_tokens(fp.stat().st_size, len(text))
                            return (
                                f"**Token 预估**\n\n"
                                f"| 类型 | Input | Output | 合计 |\n"
                                f"|------|-------|--------|------|\n"
                                f"| Flash | {est['flash_in']:,} | {est['flash_out']:,} | {est['flash_total']:,} |\n"
                                f"| Pro | {est['deep_in_per_layer']:,}x5 | {est['deep_out_per_layer']:,}x4+800 | {est['deep_total']:,} |\n"
                                f"| **总计** | | | **{est['total_estimated']:,}** |\n\n"
                                f"文件: {est['file_size_bytes']/1024:.1f}KB | 字符: {est['char_count']:,}"
                            )
                        except Exception:
                            return "无法读取文件"

                    learn_file.change(fn=_on_file_select, inputs=[learn_file], outputs=[learn_token_est])
                    learn_btn.click(fn=handle_learn_file, inputs=[learn_file, learn_lw, learn_dp], outputs=[learn_result, learn_token_est, cost_md])

                with gr.Accordion("知识库文件列表", open=False):
                    kb_page = gr.State(value=1)
                    with gr.Row():
                        kb_filter = gr.Radio(["全部", "用户", "默认"], value="全部", label="筛选")
                        kb_show_btn = gr.Button("显示文件列表", variant="primary")
                    kb_file_list = gr.Markdown(value="点击「显示文件列表」查看")
                    with gr.Row():
                        kb_prev_btn = gr.Button("◀ 上一页", scale=1)
                        kb_page_info = gr.Markdown("第 1 页", scale=1)
                        kb_next_btn = gr.Button("▶ 下一页", scale=1)
                    with gr.Row():
                        kb_delete_indices = gr.Textbox(label="输入编号删除（如 1,3,5 或 1-10 或 all）", placeholder="例: 1,3,5", scale=3)
                        kb_delete_btn = gr.Button("删除", variant="stop", scale=1)
                    kb_del_result = gr.Markdown()

                    _filter_map = {"全部": "all", "用户": "user", "默认": "default"}

                    def _show_list(f, p):
                        t, np = kb_list_files(_filter_map[f], p)
                        return t, np, f"第 {np} 页"

                    def _prev_page(f, p):
                        return _show_list(f, max(1, p - 1))

                    def _next_page(f, p):
                        return _show_list(f, p + 1)

                    def _do_delete(idx, f, p):
                        msg, np = kb_delete_file(idx, _filter_map[f], p)
                        # 刷新列表
                        t, np2 = kb_list_files(_filter_map[f], np)
                        return msg, t, np2, f"第 {np2} 页"

                    kb_show_btn.click(fn=_show_list, inputs=[kb_filter, kb_page], outputs=[kb_file_list, kb_page, kb_page_info])
                    kb_prev_btn.click(fn=_prev_page, inputs=[kb_filter, kb_page], outputs=[kb_file_list, kb_page, kb_page_info])
                    kb_next_btn.click(fn=_next_page, inputs=[kb_filter, kb_page], outputs=[kb_file_list, kb_page, kb_page_info])
                    kb_delete_btn.click(fn=_do_delete, inputs=[kb_delete_indices, kb_filter, kb_page], outputs=[kb_del_result, kb_file_list, kb_page, kb_page_info])

                gr.Markdown("---")
                gr.Markdown("### 知识库检索")
                with gr.Row():
                    type_sel = gr.Radio(choices=["idea", "structure", "technique", "language"], label="类型", value="idea")
                    limit_slider = gr.Slider(3, 20, 5, step=1, label="条数")
                query_btn = gr.Button("查询")
                query_out = gr.Markdown()
                query_btn.click(fn=handle_query_units, inputs=[type_sel, limit_slider], outputs=[query_out])

                stats_btn = gr.Button("刷新统计")
                stats_out = gr.Markdown()
                stats_btn.click(fn=handle_stats, inputs=[], outputs=[stats_out])

            # ===== 写作工作台 =====
            with gr.Tab("✏️ 写作工作台"):
                with gr.Accordion("📝 短篇写作", open=False):
                    gr.Markdown("### 知识增强写作")
                    with gr.Row():
                        with gr.Column(scale=1):
                            w_input = gr.Textbox(label="写作需求", lines=5,
                                placeholder="例: 写一篇800字短评，关于AI对写作的影响，冷峻评论体")
                            with gr.Row():
                                use_kb = gr.Checkbox(label="注入知识库", value=True)
                                model_sel = gr.Radio(["V4 Flash", "V4 Pro"], value="V4 Flash", label="模型")
                        with gr.Column(scale=2):
                            w_out = gr.Markdown(label="生成文章")
                            w_meta = gr.Markdown(label="元信息")

                    write_btn = gr.Button("开始写作", variant="primary")
                    write_btn.click(fn=handle_write, inputs=[w_input, use_kb, model_sel], outputs=[w_out, w_meta, cost_md, article_state])



            # ===== 长篇小说工作台 =====
                with gr.Accordion("📖 长篇小说工作台", open=False):
                    gr.Markdown("### 项目管理")
                    with gr.Row():
                        novel_name = gr.Textbox(label="项目名称", placeholder="输入新项目名...", scale=2)
                        novel_genre = gr.Textbox(label="类型", placeholder="玄幻/都市/科幻...", scale=1)
                        novel_desc = gr.Textbox(label="简介", placeholder="一句话简介", scale=2)
                    with gr.Row():
                        create_btn = gr.Button("新建项目", variant="primary")
                        project_dropdown = gr.Dropdown(label="选择已有项目", choices=[], interactive=True)
                        refresh_btn = gr.Button("刷新列表")
                        delete_btn = gr.Button("删除选中项目", variant="stop")
                        load_btn = gr.Button("加载选中项目")
                        save_all_btn = gr.Button("保存全部", variant="secondary")
                    novel_status = gr.Markdown()

                    create_btn.click(fn=novel_create, inputs=[novel_name, novel_genre, novel_desc], outputs=[novel_status, project_dropdown])
                    refresh_btn.click(fn=novel_refresh_projects, inputs=[], outputs=[project_dropdown])
                    delete_btn.click(fn=novel_delete, inputs=[project_dropdown], outputs=[novel_status, project_dropdown])
                    save_all_btn.click(fn=novel_save_all, inputs=[], outputs=[novel_status])

                    gr.Markdown("---")
                    gr.Markdown("### 一键自动生成")
                    with gr.Row():
                        auto_chs = gr.Number(label="总章节数", value=10, precision=0)
                        auto_words = gr.Slider(label="每章字数", value=2000, minimum=500, maximum=5000, step=500)
                        auto_btn = gr.Button("开始自动生成", variant="primary")
                    auto_progress = gr.Markdown(label="生成进度")
                    auto_outline_preview = gr.Textbox(label="大纲预览", lines=4, visible=False)
                    auto_full_out = gr.Textbox(label="完整小说全文", lines=8)
                    auto_btn.click(fn=novel_auto_generate, inputs=[auto_chs, auto_words],
                        outputs=[auto_progress, auto_outline_preview, auto_full_out])

                    gr.Markdown("---")
                    gr.Markdown("### 阶段 1/4：生成大纲")
                    with gr.Row():
                        outline_chs = gr.Number(label="总章节数", value=10, precision=0)
                        outline_inst = gr.Textbox(label="故事简介", lines=2, placeholder="介绍你的故事...", scale=3)
                    s1_btn = gr.Button("1. 生成大纲", variant="primary")
                    s1_out = gr.Textbox(label="大纲（可编辑）", lines=8, placeholder="生成后可手动修改")
                    s1_cost = gr.Markdown()
                    s1_btn.click(fn=novel_stage1_outline, inputs=[outline_chs, outline_inst], outputs=[s1_out, s1_cost])
                    save_outline_btn = gr.Button("保存大纲修改")
                    s1_save_status = gr.Markdown()
                    save_outline_btn.click(fn=novel_save_outline, inputs=[s1_out], outputs=[s1_save_status, s1_out])

                    gr.Markdown("---")
                    gr.Markdown("### 阶段 2/4：角色系统")
                    s2_btn = gr.Button("2. 生成角色系统", variant="primary")
                    with gr.Row():
                        s2_out = gr.Markdown(label="角色列表")
                        s2_json = gr.Textbox(label="角色 JSON（可编辑）", lines=12, placeholder="修改后点保存")
                    s2_save_btn = gr.Button("保存角色修改")
                    s2_save_status = gr.Markdown()
                    s2_cost = gr.Markdown()
                    s2_btn.click(fn=novel_stage2_characters, inputs=[], outputs=[s2_out, s2_json, s2_cost])
                    s2_save_btn.click(fn=novel_update_chars, inputs=[s2_json], outputs=[s2_save_status])

                    gr.Markdown("---")
                    gr.Markdown("### 阶段 3/4：剧情设计")
                    shared_chapter = gr.Number(label="选择章节", value=1, precision=0)
                    with gr.Row():
                        s3_btn = gr.Button("3. 设计本章剧情")
                        s3_save_btn = gr.Button("保存剧情修改")
                    s3_out = gr.Textbox(label="剧情设计（可编辑）", lines=8)
                    s3_cost = gr.Markdown()
                    s3_status = gr.Markdown()
                    s3_btn.click(fn=novel_stage3_plot, inputs=[shared_chapter], outputs=[s3_out, s3_cost])
                    s3_save_btn.click(fn=novel_save_plot, inputs=[s3_out, shared_chapter], outputs=[s3_status])

                    gr.Markdown("---")
                    gr.Markdown("### 阶段 4/4：生成文章")
                    with gr.Row():
                        s4_inst = gr.Textbox(label="额外要求", lines=1, scale=2, placeholder="写作要求（剧情设计已自动注入）")
                        s4_words = gr.Slider(label="目标字数", value=2500, minimum=500, maximum=8000, step=500)
                        s4_btn = gr.Button("4. 撰写本章", variant="primary")
                        s4_save_chars_btn = gr.Button("保存角色状态")
                    with gr.Row():
                        s4_chars = gr.Markdown(label="角色当前状态", scale=1)
                        cost_md_novel = gr.Markdown(label="开销", scale=1)
                    s4_write_status = gr.Markdown()
                    s4_save_chars_status = gr.Markdown()
                    s4_cost = gr.Markdown()

                    gr.Markdown("---")
                    gr.Markdown("### 完整小说全文")
                    novel_full_btn = gr.Button("刷新全文")
                    novel_full_out = gr.Textbox(label="完整小说全文", lines=16)
                    novel_full_btn.click(
                        fn=lambda: _novel_project.export_novel() if _novel_project else "请先加载项目",
                        inputs=[], outputs=[novel_full_out],
                    )
                    send_chapter_btn = gr.Button("📨 发送本章到审稿", variant="secondary")
                    send_chapter_btn.click(
                        fn=lambda ch: (lambda t, tl, n: t if t and "暂未撰写" not in t else "")(*_get_chapter_for_review(ch)),
                        inputs=[shared_chapter],
                        outputs=[article_state],
                    )
                    # 后置绑定
                    load_btn.click(fn=novel_load, inputs=[project_dropdown],
                        outputs=[novel_status, s2_out, s2_json, novel_full_out])
                    s4_btn.click(fn=novel_stage4_write, inputs=[shared_chapter, s4_inst, s4_words],
                        outputs=[s4_chars, cost_md_novel, s4_write_status, novel_full_out, s4_cost])
                    s4_save_chars_btn.click(fn=novel_save_characters, inputs=[], outputs=[s4_save_chars_status])

                    export_btn = gr.Button("导出到文件")
                    export_out = gr.Textbox(label="导出路径")
                    export_btn.click(fn=novel_export, inputs=[], outputs=[export_out])

            # ===== 板块三 =====
            with gr.Tab("🔍 板块三 · 文章审稿"):
                gr.Markdown("### 六维审稿")
                with gr.Row():
                    with gr.Column(scale=1):
                        load_btn = gr.Button("📥 加载写作区文章", variant="secondary")
                        r_input = gr.Textbox(label="文章内容", lines=10)
                        r_btn = gr.Button("开始审稿", variant="primary")
                    with gr.Column(scale=2):
                        r1 = gr.Markdown(label="Level 1 · 自动修改")
                        r2 = gr.Markdown(label="Level 2 · 待确认")
                        r3 = gr.Markdown(label="Level 3 · 手动指引")
                        rpt = gr.Markdown(label="完整审稿报告")
                        fixed_out = gr.Markdown(label="修改后文章")

                load_btn.click(fn=lambda s: s, inputs=[article_state], outputs=[r_input])
                r_btn.click(fn=handle_review, inputs=[r_input], outputs=[r1, r2, r3, rpt, fixed_out, cost_md])

                gr.Markdown("---")
                gr.Markdown("### 端到端：写作 → 审稿")
                with gr.Row():
                    e2e_in = gr.Textbox(label="写作需求", lines=3, scale=3,
                        placeholder="例: 写一篇关于人工智能对教育影响的文章...")
                    e2e_btn = gr.Button("写作 + 审稿", variant="primary", scale=1)
                e2e_fixed = gr.Markdown(label="修复后文章")
                e2e_report = gr.Markdown(label="审稿报告")
                e2e_btn.click(fn=handle_e2e, inputs=[e2e_in], outputs=[e2e_fixed, e2e_report, cost_md])

                # 发送到审稿按钮
                send_short_btn = gr.Button("📨 从写作区加载到审稿")
                send_short_btn.click(fn=lambda s: (s, s), inputs=[article_state], outputs=[article_state, r_input])

            # 初始加载时显示一次
            app.load(fn=cost_panel, inputs=[], outputs=[cost_md])

    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(server_name="127.0.0.1", server_port=7860)
