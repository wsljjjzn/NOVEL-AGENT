"""Reset database and checkpoint for new 5000-article preprocessing."""
import os, json, time

db = "data/knowledge/writing_expert.db"
cp = "data/preprocess_checkpoint.json"

# Try to delete DB (may be locked by lingering processes)
max_retries = 5
for i in range(max_retries):
    try:
        if os.path.exists(db):
            os.remove(db)
            sz = os.path.getsize(db)
            print(f"已删除数据库 ({sz/1024/1024/1024:.0f} GB)")
        break
    except PermissionError as e:
        if i < max_retries - 1:
            print(f"数据库被锁定，等待 5 秒重试 ({i+1}/{max_retries})...")
            time.sleep(5)
        else:
            print(f"无法删除数据库（被占用）: {e}")
            print("请手动关闭所有 Python 进程后重试")

# Reset checkpoint
with open(cp, "w", encoding="utf-8") as f:
    json.dump({"completed": [], "count": 0}, f)
print("checkpoint 已重置")

# Delete old embedding data
import shutil
emb_dir = "data/embeddings"
if os.path.exists(emb_dir):
    shutil.rmtree(emb_dir, ignore_errors=True)
    print("embedding 数据已清理")

print("\n清理完成。可重新运行预处理。")
