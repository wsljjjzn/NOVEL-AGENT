"""
scripts/generate_conclusion_final.py — 从知识库生成学习结论报告。

对 1960 篇已分析文章做分层聚合统计，输出可读 Markdown 报告。
"""

import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_base import init_db
from src.utils.llm_client import LLMClient
from config.settings import get_config

cfg = get_config()
db_path = cfg.database.get("path", "data/knowledge/writing_expert_new.db")
conn = init_db(db_path)


def get_type_stats():
    rows = conn.execute("SELECT type, COUNT(*) FROM knowledge_units GROUP BY type").fetchall()
    return dict(rows)


def get_top_tags(limit=20):
    """获取出现最频繁的标签。"""
    rows = conn.execute(
        "SELECT tags FROM knowledge_units WHERE tags != '' AND tags IS NOT NULL"
    ).fetchall()
    tag_counts = {}
    for r in rows:
        for t in r[0].split(","):
            t = t.strip()
            if t:
                tag_counts[t] = tag_counts.get(t, 0) + 1
    return sorted(tag_counts.items(), key=lambda x: -x[1])[:limit]


def get_samples(type_name, limit=5):
    rows = conn.execute(
        "SELECT description, tags FROM knowledge_units WHERE type=? AND description != '' "
        "ORDER BY length(description) DESC LIMIT ?",
        (type_name, limit),
    )
    return rows.fetchall()


def get_representative_quotes(type_name, limit=8):
    """取该类型中最有代表性的条目（内容最长的）。"""
    rows = conn.execute(
        "SELECT description FROM knowledge_units WHERE type=? AND length(description) > 50 "
        "ORDER BY length(description) DESC LIMIT ?",
        (type_name, limit),
    )
    return [r[0][:300] for r in rows.fetchall() if r[0]]


def main():
    t0 = time.time()

    lines = []
    lines.append("# 板块一：学习结论报告")
    lines.append("")
    lines.append(f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**分析文章**: 1,960 篇")
    lines.append(f"**知识单元总数**: {sum(get_type_stats().values())}")
    lines.append("")

    # === 章节 1：总体统计 ===
    lines.append("---")
    lines.append("## 一、知识单元总体统计")
    lines.append("")
    lines.append("| 类型 | 数量 | 占比 |")
    lines.append("|------|------|------|")
    stats = get_type_stats()
    total = sum(stats.values())
    for t in ["idea", "structure", "technique", "language"]:
        cnt = stats.get(t, 0)
        pct = cnt / total * 100 if total > 0 else 0
        labels = {"idea": "思想", "structure": "结构", "technique": "叙事技法", "language": "语言"}
        lines.append(f"| {labels.get(t, t)} | {cnt} | {pct:.1f}% |")
    lines.append("")

    # === 章节 2：高频标签 ===
    lines.append("---")
    lines.append("## 二、高频主题标签")
    lines.append("")
    tags = get_top_tags(30)
    lines.append("| 标签 | 出现次数 |")
    lines.append("|------|---------|")
    for tag, cnt in tags:
        lines.append(f"| {tag} | {cnt} |")
    lines.append("")

    # === 章节 3：逐类型深度分析 ===
    type_names = {
        "idea": ("思想层", "核心命题与价值观分析"),
        "structure": ("结构层", "叙事结构与信息组织"),
        "technique": ("叙事技法层", "人物塑造与情节设计"),
        "language": ("语言层", "文体风格与表达特征"),
    }

    lines.append("---")
    lines.append("## 三、四层分析深度摘要")
    lines.append("")

    for type_key, (cn_name, subtitle) in type_names.items():
        lines.append(f"### {cn_name}：{subtitle}")
        lines.append("")
        quotes = get_representative_quotes(type_key, 6)
        for q in quotes:
            lines.append(f"- {q}")
        lines.append("")

    # === 章节 4：LLM 聚合分析（用聚类采样） ===
    lines.append("---")
    lines.append("## 四、跨文章共性发现（LLM 聚合）")
    lines.append("")

    try:
        llm = LLMClient()
        # 每类取 3 条最有代表的，拼成 prompt
        prompt_parts = ["以下是1,960篇网络小说中提取的写作知识单元采样，请提炼共性写作特征：\n"]
        for type_key, (cn_name, _) in type_names.items():
            quotes = get_representative_quotes(type_key, 3)
            prompt_parts.append(f"\n## {cn_name}")
            for q in quotes:
                prompt_parts.append(f"- {q[:200]}")

        prompt_parts.append(
            '\n\n请输出JSON格式:\n'
            '{\n'
            '  "思想层共性": "...",\n'
            '  "结构层共性": "...",\n'
            '  "叙事层共性": "...",\n'
            '  "语言层共性": "...",\n'
            '  "通用写作建议": ["..."]\n'
            '}'
        )

        response = llm.chat(
            [{"role": "user", "content": "\n".join(prompt_parts)}],
            model_tier="flash",
            temperature=0.4,
        )
        lines.append(response)
        lines.append("")
    except Exception as e:
        lines.append(f"LLM 聚合分析不可用: {e}")
        lines.append("")

    # === 章节 5：写作建议 ===
    lines.append("---")
    lines.append("## 五、知识单元分类清单")
    lines.append("")

    for type_key, (cn_name, _) in type_names.items():
        cnt = stats.get(type_key, 0)
        lines.append(f"### {cn_name}（共 {cnt} 条）")
        samples = get_samples(type_key, 4)
        for desc, tags in samples:
            lines.append(f"- {desc[:150]}...")
            if tags:
                lines.append(f"  标签: {tags[:80]}")
        lines.append("")

    # 保存
    report_path = Path("data/samples/LEARNING_REPORT_FINAL.md")
    report_path.write_text("\n".join(lines), encoding="utf-8")

    elapsed = time.time() - t0
    print(f"报告已生成: {report_path}")
    print(f"耗时: {elapsed:.1f}s")
    print(f"长度: {len(lines)} 行")

    # 显示报告前 40 行
    for line in lines[:40]:
        print(line)

    conn.close()


if __name__ == "__main__":
    main()
