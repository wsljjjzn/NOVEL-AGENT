"""Get checkpoint data."""
import json
d = json.load(open("data/preprocess_checkpoint.json", "r", encoding="utf-8"))
print(f"已完成: {d.get('count', 0)} 个文件")
