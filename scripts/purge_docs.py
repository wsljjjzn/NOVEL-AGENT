"""
scripts/purge_docs.py — 清理未选中的文章。

两种模式：
- --dry-run: 只显示将删除的文件数，不实际删除
- --execute: 实际执行删除

用法：
  python scripts/purge_docs.py --dry-run
  python scripts/purge_docs.py --execute
"""

import os, json, sys, argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不执行删除")
    parser.add_argument("--execute", action="store_true", help="实际执行删除")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("请指定 --dry-run 或 --execute")
        return

    # 读取精选列表
    sel_path = ROOT / "data" / "samples" / "selected_5000.json"
    if not sel_path.exists():
        print(f"精选列表不存在: {sel_path}")
        return

    keep = set(json.loads(sel_path.read_text("utf-8")))
    print(f"保留 {len(keep)} 篇文章\n")

    # 扫描 doc/ 下所有 .txt
    doc_dir = ROOT / "doc"
    to_delete = []
    kept = 0

    for root, dirs, files in os.walk(doc_dir):
        for f in files:
            if not f.endswith(".txt"):
                continue
            fp = os.path.join(root, f)
            if fp in keep:
                kept += 1
            else:
                to_delete.append(fp)

    print(f"doc 目录中共 {len(to_delete) + kept} 个 .txt 文件")
    print(f"保留: {kept}")
    print(f"待删除: {len(to_delete)}")

    if not to_delete:
        print("没有需要删除的文件")
        return

    # 统计待删除文件总大小
    total_size = sum(os.path.getsize(f) for f in to_delete)
    print(f"释放空间: {total_size / 1024 / 1024:.0f} MB")

    if args.dry_run:
        print("\n[模拟] 未执行删除。加上 --execute 以实际执行。")
        return

    # 执行删除
    print("\n正在删除...")
    for i, fp in enumerate(to_delete):
        if (i + 1) % 500 == 0:
            print(f"  已删除 {i+1}/{len(to_delete)}...")
        os.remove(fp)

    print(f"删除完成！共删除 {len(to_delete)} 个文件")
    print(f"释放空间: {total_size / 1024 / 1024:.0f} MB")


if __name__ == "__main__":
    main()
