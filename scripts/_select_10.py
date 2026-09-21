"""Quickly pick 10 files for analysis."""
import os
from pathlib import Path

doc = "doc"
# Only scan part05 and part06 which have larger files
parts = ["doc/【按首字拼音分类】.part05", "doc/【按首字拼音分类】.part06"]

files = []
for part in parts:
    for entry in os.listdir(part):
        d = os.path.join(part, entry)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".txt"):
                continue
            fp = os.path.join(d, f)
            sz = os.path.getsize(fp)
            if 200000 < sz < 3000000:
                files.append((fp, sz))

# Pick one per directory, up to 10
seen_dirs = set()
selected = []
files.sort(key=lambda x: x[1])
for fp, sz in files:
    parent = os.path.dirname(fp)
    if parent not in seen_dirs or len(selected) < 6:
        seen_dirs.add(parent)
        selected.append((fp, sz))
    if len(selected) >= 10:
        break

import json
paths = [fp for fp, sz in selected]
with open("data/samples/learning_10_files.json", "w", encoding="utf-8") as f:
    json.dump(paths, f, ensure_ascii=False, indent=2)

for fp, sz in selected:
    rel = os.path.relpath(fp, doc)
    print(f"  {rel} ({sz/1024:.0f}KB)")
print(f"\nTotal: {len(selected)} files, saved to data/samples/learning_10_files.json")
