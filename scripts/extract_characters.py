"""
scripts/extract_characters.py — 从 analysis_results.json 提取角色。

用法：python scripts/extract_characters.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.analysis.character_analyzer import CharacterAnalyzer
from src.utils.logger import setup_logger

setup_logger(level="INFO")


def main():
    json_path = ROOT / "data" / "samples" / "analysis_results.json"

    if not json_path.exists():
        print(f"文件不存在: {json_path}")
        return

    analyzer = CharacterAnalyzer()
    characters = analyzer.extract_from_analysis_json(str(json_path))

    print(f"\n从分析结果中提取了 {len(characters)} 个角色：\n")
    for c in characters:
        print(f"  [{c.character_id}]")
        print(f"    名称：{c.name}")
        if c.aliases:
            print(f"    别名：{', '.join(c.aliases)}")
        if c.base_profile:
            bp = c.base_profile
            for k, v in list(bp.items())[:3]:
                print(f"    {k}：{v}")
        if c.relationship_map:
            print(f"    关系：")
            for t, d in c.relationship_map.items():
                print(f"      - {t}: {d[:40]}")
        if c.arc_summary:
            print(f"    弧线：{c.arc_summary[:60]}")
        print()

    # 保存到 JSON 供检查
    import json
    output_path = ROOT / "data" / "samples" / "characters_extracted.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            [c.model_dump() for c in characters],
            f, ensure_ascii=False, indent=2,
        )
    print(f"已保存到: {output_path}")


if __name__ == "__main__":
    main()
