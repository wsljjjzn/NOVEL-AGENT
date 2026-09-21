"""
scripts/learn_articles.py — 对10篇文章进行深度分析并输出学习结论。

流程：
1. 读文件列表
2. 对每篇做：预处理分块 → 四层深度分析 (V4 Pro)
3. 知识单元入库
4. 输出学习结论 JSON
"""

import sys, json, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.logger import setup_logger
from src.analysis.ingestion import IngestionPipeline
from src.analysis.deep import DeepAnalyzer

setup_logger(level="INFO")


def main():
    # 读文件列表
    list_path = ROOT / "data" / "samples" / "learning_10_files.json"
    if not list_path.exists():
        print(f"文件列表不存在: {list_path}")
        return

    with open(list_path, "r", encoding="utf-8") as f:
        file_paths = json.load(f)

    print(f"将分析 {len(file_paths)} 篇文章\n")

    pipeline = IngestionPipeline()
    deep = DeepAnalyzer()
    results = []
    t_start = time.time()

    for i, fpath in enumerate(file_paths):
        if not Path(fpath).exists():
            print(f"[{i+1}/{len(file_paths)}] 文件不存在: {fpath}")
            continue

        source_name = Path(fpath).stem
        t0 = time.time()

        print(f"\n[{i+1}/{len(file_paths)}] {source_name}")
        print(f"  预处理...", end="", flush=True)

        # 1. 预处理
        chunks = pipeline.preprocessor.process_file(fpath)
        print(f" {len(chunks)} 个段落块", flush=True)

        # 2. 取前20段做分析样本
        if not chunks:
            print("  跳过（无段落块）")
            continue

        full_text = "\n".join(c.text for c in chunks[:20])
        if len(full_text) < 200:
            print("  跳过（文本太短）")
            continue

        # 3. 四层深度分析
        print(f"  深度分析（4 次 Pro 调用）...", end="", flush=True)
        deep_result = deep.analyze_all(full_text, source_name)
        print(f" 完成", flush=True)

        # 4. 入库知识单元
        units = deep.synthesize_knowledge_units(deep_result, fpath)
        pipeline._save_knowledge_units(units)
        print(f"  入库 {len(units)} 个知识单元", flush=True)

        # 5. 收集结果
        try:
            result_dict = {
                "title": source_name,
                "file": fpath,
                "analysis": deep_result.model_dump() if hasattr(deep_result, 'model_dump') else str(deep_result),
            }
        except Exception:
            result_dict = {"title": source_name, "file": fpath, "analysis": "serialization_error"}

        results.append(result_dict)
        elapsed = time.time() - t0
        print(f"  耗时: {elapsed:.0f}s", flush=True)

    # 保存结论
    output_path = ROOT / "data" / "samples" / "learning_conclusion.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total_elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"分析完成: {len(results)} 篇文章")
    print(f"总耗时: {total_elapsed/60:.1f} 分钟")
    print(f"结论已保存: {output_path}")


if __name__ == "__main__":
    main()
