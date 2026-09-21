"""
scripts/generate_conclusion.py — 从学习结论生成可读的 Markdown 报告。
"""

import sys, json
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.llm_client import LLMClient


def fmt(val, max_len=200):
    """格式化 Any 字段为字符串。"""
    if val is None:
        return ""
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)[:max_len]
    if isinstance(val, list):
        return ", ".join(str(v)[:60] for v in val)[:max_len]
    return str(val)[:max_len]


def main():
    json_path = ROOT / "data" / "samples" / "learning_conclusion.json"
    if not json_path.exists():
        print(f"文件不存在: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    lines = ["# 10 篇文章学习结论报告", f"", f"**分析时间**: 2026-07-25", f"**文章数**: {len(results)}", f"", "---", ""]

    # 逐篇摘要
    lines.append("## 一、逐篇分析摘要")
    lines.append("")

    for i, r in enumerate(results):
        title = r.get("title", f"文章{i+1}")
        filepath = r.get("file", "")
        analysis = r.get("analysis", {})

        thought = analysis.get("thought", {})
        structure = analysis.get("structure", {})
        narrative = analysis.get("narrative", {})
        language = analysis.get("language", {})

        lines.append(f"### {i+1}. {title}")
        lines.append(f"路径: `{filepath}`")
        lines.append("")

        # 思想层
        core = thought.get("core_proposition", "")
        if core:
            lines.append(f"- **核心命题**: {fmt(core, 300)}")
        beliefs = thought.get("subverted_beliefs", [])
        if beliefs:
            bs = ", ".join(fmt(b, 80) for b in beliefs[:3])
            lines.append(f"- **反常识点**: {bs}")
        value = thought.get("value_premise", "")
        if value:
            lines.append(f"- **价值观**: {fmt(value, 200)}")

        # 结构层
        st = structure.get("structure_type", "")
        if st:
            lines.append(f"- **结构类型**: {fmt(st, 100)}")
        tech_s = structure.get("notable_technique", "")
        if tech_s:
            lines.append(f"- **结构技法**: {fmt(tech_s, 200)}")

        # 叙事层
        cp = narrative.get("character_portrayal", "")
        if cp:
            lines.append(f"- **人物塑造**: {fmt(cp, 200)}")
        nt = narrative.get("notable_technique", "")
        if nt:
            lines.append(f"- **叙事技法**: {fmt(nt, 200)}")

        # 语言层
        style = language.get("overall_style", "")
        if style:
            lines.append(f"- **语言风格**: {fmt(style, 100)}")

        lines.append("")

    # 跨文章分析
    lines.append("---")
    lines.append("## 二、跨文章共性发现")
    lines.append("")

    # 用 LLM 做一次聚合分析
    try:
        llm = LLMClient()
        summaries = []
        for r in results:
            title = r.get("title", "")
            t = r.get("analysis", {}).get("thought", {})
            s = r.get("analysis", {}).get("structure", {})
            summaries.append(f"《{title}》: 核心命题={fmt(t.get('core_proposition',''), 150)}, 结构={fmt(s.get('structure_type',''), 80)}")

        prompt = "以下是对10篇网络小说的四维分析摘要。请提炼共性写作特征，输出JSON：\n\n"
        prompt += "\n".join(summaries)
        prompt += "\n\n请按以下格式输出:\n{\"思想层共性\": \"...\", \"结构层共性\": \"...\", \"叙事层共性\": \"...\", \"语言层共性\": \"...\", \"通用写作建议\": [\"...\"]}"

        response = llm.chat([{"role": "user", "content": prompt}], model_tier="pro", temperature=0.4)
        lines.append("### 用 LLM 聚合分析的结果")
        lines.append("")
        lines.append(response)
        lines.append("")
    except Exception as e:
        lines.append(f"LLM 聚合分析失败: {e}")
        lines.append("")

    # 知识单元统计
    lines.append("---")
    lines.append("## 三、知识单元清单")
    lines.append("")

    from config.settings import get_config
    from src.knowledge_base import init_db
    cfg = get_config()
    db_path = cfg.database.get("path", "data/knowledge/writing_expert.db")
    conn = init_db(db_path)
    rows = conn.execute("SELECT type, category, description, tags FROM knowledge_units ORDER BY type").fetchall()
    conn.close()

    by_type = {}
    for row in rows:
        t = row[0]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(row)

    for t, items in by_type.items():
        lines.append(f"### {t} ({len(items)} 个)")
        for item in items[:5]:  # 每类只显示前5个
            desc = item[2][:200] if item[2] else "(空)"
            tags = item[3] if item[3] else ""
            lines.append(f"- {desc}")
            if tags:
                lines.append(f"  tags: {tags}")
        if len(items) > 5:
            lines.append(f"  ...还有 {len(items)-5} 个")
        lines.append("")

    # 保存报告
    report_path = ROOT / "data" / "samples" / "LEARNING_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    # 输出到控制台
    print("\n".join(lines[:200]))  # 只输出前200行
    print(f"...")
    print(f"\n完整报告已保存: {report_path}")


if __name__ == "__main__":
    main()
