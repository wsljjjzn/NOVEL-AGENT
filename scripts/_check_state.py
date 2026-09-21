"""Check state of preprocessing and selected files."""
import os, json

print("=== 状态检查 ===")

db = "data/knowledge/writing_expert_new.db"
if os.path.exists(db):
    sz = os.path.getsize(db)
    print(f"新数据库: {sz/1024/1024:.0f} MB")
else:
    print("新数据库: 不存在")

sel = "data/samples/selected_5000.json"
if os.path.exists(sel):
    files = json.load(open(sel, "r", encoding="utf-8"))
    print(f"精选列表: {len(files)} 篇")
    if files:
        print(f"第一篇存在: {os.path.exists(files[0])}")
else:
    print("精选列表: 不存在")

cp = "data/preprocess_checkpoint.json"
if os.path.exists(cp):
    d = json.load(open(cp, "r", encoding="utf-8"))
    n = d.get("count", 0)
    print(f"Checkpoint: {n} 文件完成")
else:
    print("Checkpoint: 不存在")

print("=== 完毕 ===")
