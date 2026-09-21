"""
scripts/learn_articles_economy.py — 经济型深度分析：Flash 粗筛 + Pro 精选 + Pro 聚合。

成本：~0.30元（vs 原方案 0.88元，节省 66%）

阶段 A: Flash 全量分析（10篇 × 4层 = 40次 Flash, ~0.03元）
阶段 B: 自动精选 3 篇 + Pro 验证（3篇 × 4层 = 12次 Pro, ~0.27元）
阶段 C: Pro 跨文章聚合（1次 Pro, ~0.02元）
"""

import sys, json, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.logger import setup_logger
from src.utils.llm_client import LLMClient
from src.analysis.ingestion import IngestionPipeline
from src.analysis.deep import DeepAnalyzer

setup_logger(level="WARNING")

COST_FLASH = 0.00075   # 每次 Flash 调用估算
COST_PRO = 0.022       # 每次 Pro 调用估算


def main():
    list_path = ROOT / "data" / "samples" / "learning_10_files.json"
    if not list_path.exists():
        print(f"文件列表不存在: {list_path}")
        return

    with open(list_path, "r", encoding="utf-8") as f:
        file_paths = json.load(f)

    print(f"经济型分析: {len(file_paths)} 篇文章\n")
    print(f"  阶段 A: Flash 全量粗筛 (40 次, ~{COST_FLASH*40:.3f}元)")
    print(f"  阶段 B: Pro 精选验证 (12 次, ~{COST_PRO*12:.3f}元)")
    print(f"  阶段 C: Pro 聚合提炼 (1 次, ~{COST_PRO:.3f}元)")
    print(f"  总计: ~{COST_FLASH*40 + COST_PRO*13:.3f}元\n")

    pipeline = IngestionPipeline()
    deep = DeepAnalyzer()
    t_start = time.time()

    # === 阶段 A: Flash 全量粗筛 ===
    print("【阶段 A】Flash 全量分析...\n")
    flash_results = []

    for i, fpath in enumerate(file_paths):
        if not Path(fpath).exists():
            continue
        source_name = Path(fpath).stem
        chunks = pipeline.preprocessor.process_file(fpath)
        if not chunks:
            continue
        full_text = "\n".join(c.text for c in chunks[:20])
        if len(full_text) < 200:
            continue

        print(f"  [{i+1}/{len(file_paths)}] {source_name[:30]}...", end="", flush=True)
        result = deep.analyze_all(full_text, source_name, model_tier="flash")
        flash_results.append({
            "title": source_name,
            "file": fpath,
            "analysis": _deep_to_dict(result),
        })
        print(" 完成")

    # === 阶段 B: 自动精选 + Pro 验证 ===
    print(f"\n【阶段 B】精选 3 篇 + Pro 验证...\n")

    # 选 score 最低的 3 篇（Flash 可能没抓准的）
    scored = []
    for r in flash_results:
        a = r["analysis"]
        core = a.get("thought", {}).get("core_proposition", "")
        tech = a.get("structure", {}).get("notable_technique", "")
        score = 0
        if core and len(str(core)) > 10:
            score += 1
        if tech and len(str(tech)) > 10:
            score += 1
        if a.get("narrative", {}).get("character_portrayal"):
            score += 1
        if a.get("language", {}).get("overall_style"):
            score += 1
        scored.append((score, r))

    scored.sort(key=lambda x: x[0])  # 低分优先重跑
    to_rerun = scored[:3]

    for score, r in to_rerun:
        title = r["title"]
        chunks = pipeline.preprocessor.process_file(r["file"])
        full_text = "\n".join(c.text for c in chunks[:20])
        print(f"  重跑: {title[:30]}... (Flash 质量分: {score}/4)", end="", flush=True)
        pro_result = deep.analyze_all(full_text, title, model_tier="pro")
        r["analysis"] = _deep_to_dict(pro_result)
        print(" → Pro 完成")

        # 入库知识单元
        units = deep.synthesize_knowledge_units(pro_result, r["file"])
        pipeline._save_knowledge_units(units)
        print(f"    入库 {len(units)} 个知识单元")

    # === 阶段 C: Pro 聚合 ===
    print(f"\n【阶段 C】Pro 聚合提炼...\n")

    summaries = []
    for r in flash_results:
        title = r["title"]
        a = r["analysis"]
        t = a.get("thought", {})
        s = a.get("structure", {})
        n = a.get("narrative", {})
        l = a.get("language", {})
        summaries.append(
            f"《{title}》: 核心={str(t.get('core_proposition',''))[:100]}, "
            f"结构={str(s.get('structure_type',''))[:50]}, "
            f"叙事技法={str(n.get('notable_technique',''))[:80]}, "
            f"语言风格={str(l.get('overall_style',''))[:50]}"
        )

    prompt = "以下是对10篇网络小说的四层分析摘要。请提炼共性写作特征，输出JSON：\n\n"
    prompt += "\n".join(summaries)
    prompt += (
        '\n\n请输出JSON:\n'
        '{\n'
        '  "思想层共性": "...",\n'
        '  "结构层共性": "...",\n'
        '  "叙事层共性": "...",\n'
        '  "语言层共性": "...",\n'
        '  "通用写作建议": ["..."]\n'
        '}'
    )

    llm = LLMClient()
    conclusion = llm.chat(
        [{"role": "user", "content": prompt}],
        model_tier="pro",
        temperature=0.4,
    )

    # === 生成报告 ===
    lines = ["# 10 篇文章学习结论报告（经济版）", ""]
    total_flash = len(flash_results) * 4
    total_pro = len(to_rerun) * 4 + 1  # 3篇×4层 + 1次聚合
    total_cost = total_flash * COST_FLASH + total_pro * COST_PRO

    lines.append("## 成本说明")
    lines.append(f"- Flash 调用: {total_flash} 次 (~{total_flash*COST_FLASH:.3f}元)")
    lines.append(f"- Pro 调用: {total_pro} 次 (~{total_pro*COST_PRO:.4f}元)")
    lines.append(f"- 总计: ~{total_cost:.3f}元（vs 全 Pro 方案 ~0.88元，节省 {1-total_cost/0.88:.0%}）")
    lines.append(f"- 验证样本: {len(to_rerun)}/10 篇经 Pro 交叉验证")
    lines.append("")

    lines.append("## 逐篇摘要")
    for r in flash_results:
        title = r["title"]
        a = r["analysis"]
        t = a.get("thought", {})
        s = a.get("structure", {})

        lines.append(f"### {title}")
        if t.get("core_proposition"):
            lines.append(f"- 核心命题: {str(t['core_proposition'])[:200]}")
        if s.get("structure_type"):
            lines.append(f"- 结构类型: {str(s['structure_type'])[:80]}")
        if a.get("language", {}).get("overall_style"):
            lines.append(f"- 语言风格: {str(a['language']['overall_style'])[:100]}")
        lines.append("")

    lines.append("## 跨文章共性发现")
    lines.append("")
    lines.append(conclusion)
    lines.append("")

    # 统计知识单元
    from src.knowledge_base import init_db
    from config.settings import get_config
    cfg = get_config()
    conn = init_db(cfg.database.get("path", "data/knowledge/writing_expert.db"))
    rows = conn.execute("SELECT type, COUNT(*) FROM knowledge_units GROUP BY type").fetchall()
    conn.close()

    lines.append("## 知识单元统计")
    for t, c in rows:
        lines.append(f"- {t}: {c} 个")

    report_path = ROOT / "data" / "samples" / "LEARNING_REPORT_ECONOMY.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已保存: {report_path}")

    total_time = time.time() - t_start
    print(f"总耗时: {total_time/60:.1f} 分钟")
    print(f"估算费用: ~{total_cost:.3f} 元")


def _deep_to_dict(d):
    if hasattr(d, 'model_dump'):
        return d.model_dump()
    return str(d)


if __name__ == "__main__":
    main()
