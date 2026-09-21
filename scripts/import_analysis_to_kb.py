"""
scripts/import_analysis_to_kb.py — 将 analysis_results.json 的 5 篇分析入库。

用法：python scripts/import_analysis_to_kb.py
"""

import sys, json, os
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.knowledge_base import init_db
from src.models import KnowledgeUnit
from src.utils.logger import setup_logger, logger

setup_logger(level="INFO")


def main():
    json_path = ROOT / "data" / "samples" / "analysis_results.json"
    if not json_path.exists():
        print(f"文件不存在: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from config.settings import get_config
    cfg = get_config()
    db_path = cfg.database.get("path", "data/knowledge/writing_expert.db")
    conn = init_db(db_path)

    samples = data.get("samples", [])
    total_units = 0

    for sample in samples:
        sid = sample.get("id", "unknown")
        title = sample.get("title", "")
        source_file = sample.get("file", "")
        analysis = sample.get("analysis", {})
        file_stem = Path(source_file).stem if source_file else sid

        for layer_name, layer_data in analysis.items():
            if not isinstance(layer_data, dict):
                continue

            # 将每层分析转为知识单元
            for key, value in layer_data.items():
                if isinstance(value, str) and len(value) > 20:
                    unit = KnowledgeUnit(
                        knowledge_unit_id=f"{file_stem}_{layer_name}_{key}",
                        type=_layer_to_type(layer_name),
                        category=f"{layer_name}/{key}",
                        source={"file": source_file, "layer": layer_name},
                        description=value[:1000],
                        tags=[layer_name, key],
                    )
                    _save_unit(conn, unit)
                    total_units += 1
                elif isinstance(value, list) and len(value) > 0:
                    combined = "; ".join(str(v)[:200] for v in value)
                    unit = KnowledgeUnit(
                        knowledge_unit_id=f"{file_stem}_{layer_name}_{key}",
                        type=_layer_to_type(layer_name),
                        category=f"{layer_name}/{key}",
                        source={"file": source_file, "layer": layer_name},
                        description=combined[:1000],
                        tags=[layer_name, key],
                    )
                    _save_unit(conn, unit)
                    total_units += 1

    conn.close()
    print(f"\n入库完成！共写入 {total_units} 个知识单元（来自 {len(samples)} 篇分析）")


def _layer_to_type(layer: str) -> str:
    """中文分析层名 → 知识单元类型。"""
    mapping = {
        "思想层": "idea",
        "结构层": "structure",
        "叙事层": "technique",
        "语言层": "language",
    }
    return mapping.get(layer, "technique")


def _save_unit(conn, unit: KnowledgeUnit):
    """写入一个知识单元到 SQLite。"""
    try:
        conn.execute(
            """INSERT OR IGNORE INTO knowledge_units
               (knowledge_unit_id, type, category, source_file, source_location,
                description, tags, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                unit.knowledge_unit_id,
                unit.type,
                unit.category,
                unit.source.get("file", ""),
                unit.source.get("layer", ""),
                unit.description,
                ",".join(unit.tags),
            ),
        )
        conn.commit()
    except Exception as e:
        print(f"  入库失败 [{unit.knowledge_unit_id}]: {e}")


if __name__ == "__main__":
    main()
