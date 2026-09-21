"""Check DB and checkpoint status."""
import os, json

db = "data/knowledge/writing_expert.db"
size = os.path.getsize(db) if os.path.exists(db) else 0
print(f"DB size: {size/1024/1024:.0f} MB")

cp = "data/preprocess_checkpoint.json"
if os.path.exists(cp):
    d = json.load(open(cp, "r", encoding="utf-8"))
    print(f"Checkpoint done: {d.get('count',0)} files")

print("OK")
