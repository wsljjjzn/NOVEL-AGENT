"""
scripts/select_top_articles.py — 从 doc/ 精选高质量文章。

筛选标准：
- 文件大小 100KB ~ 3MB
- 中文字符占比 >60%
- 按首字母目录分层配额（保持多样性）
- 目标：5000 篇
"""

import os, json, re, sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "data" / "samples" / "selected_5000.json"

# 扫描 doc 下所有子目录
DOC_DIRS = [
    ROOT / "doc" / "【按首字拼音分类】.part01",
    ROOT / "doc" / "【按首字拼音分类】.part05",
    ROOT / "doc" / "【按首字拼音分类】.part06",
]


def chinese_ratio(text: str) -> float:
    """计算文本中中文字符占比。"""
    if not text:
        return 0
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return cjk / max(len(text), 1)


def main():
    all_candidates = []       # (dir_key, filepath, size_kb, chinese_pct)

    for base_dir in DOC_DIRS:
        if not base_dir.exists():
            continue
        for subdir in sorted(os.listdir(base_dir)):
            subpath = base_dir / subdir
            if not subpath.is_dir():
                continue
            for f in os.listdir(subpath):
                if not f.endswith(".txt"):
                    continue
                fp = subpath / f
                sz = fp.stat().st_size
                if sz < 100 * 1024 or sz > 3 * 1024 * 1024:
                    continue
                # 读前 4KB 判断中文占比
                try:
                    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                        head = fh.read(4096)
                    ratio = chinese_ratio(head)
                    if ratio < 0.6:
                        continue
                except Exception:
                    continue

                dir_key = subdir  # 如 【A】、【B】等
                all_candidates.append((dir_key, str(fp), sz / 1024, round(ratio, 3)))

    print(f"候选文章: {len(all_candidates)} 篇")

    if not all_candidates:
        print("没有找到符合条件的文章")
        return

    # 按目录配额分配
    dir_groups = defaultdict(list)
    for item in all_candidates:
        dir_groups[item[0]].append(item)

    # 每个目录至少 5 篇，其余按比例分配
    num_dirs = len(dir_groups)
    base_per_dir = 5
    remaining = 5000 - base_per_dir * num_dirs
    if remaining < 0:
        remaining = 0

    # 按候选数比例分配剩余名额
    total_candidates = len(all_candidates)
    selected = []

    for dir_key, items in sorted(dir_groups.items()):
        items.sort(key=lambda x: -x[2])  # 大文件优先（内容更丰富）
        # 先取 base
        take = min(base_per_dir, len(items))
        selected.extend(items[:take])
        items = items[take:]

        # 比例分配
        if remaining > 0 and total_candidates > 0:
            extra = max(1, int(remaining * len(items) / total_candidates))
            extra = min(extra, len(items))
            selected.extend(items[:extra])

    # 如果还不到 5000，从所有剩余候选中补
    if len(selected) < 5000:
        selected_set = set(s[1] for s in selected)
        more = [c for c in all_candidates if c[1] not in selected_set]
        more.sort(key=lambda x: -x[2])
        need = 5000 - len(selected)
        selected.extend(more[:need])

    # 截断到 5000
    selected = selected[:5000]

    # 输出结果
    paths = [s[1] for s in selected]
    summary = []
    for dir_key in sorted(dir_groups.keys()):
        count = sum(1 for s in selected if s[0] == dir_key)
        summary.append(f"  {dir_key}: {count} 篇")

    print(f"\n精选 {len(selected)} 篇文章:")
    print("\n".join(summary))
    print(f"\n平均大小: {sum(s[2] for s in selected) / len(selected):.0f} KB")
    print(f"平均中文占比: {sum(s[3] for s in selected) / len(selected) * 100:.0f}%")

    # 保存
    OUTPUT.write_text(json.dumps(paths, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已保存: {OUTPUT}")


if __name__ == "__main__":
    main()
