"""检查数据库中的文件数量和 CSV 中的文件数量对比"""
import sqlite3, time, os

# 检查 CSV
csv_path = 'data/knowledge/index.csv'
if os.path.exists(csv_path):
    with open(csv_path, 'r', encoding='utf-8') as f:
        csv_lines = [l for l in f if l.strip() and not l.startswith('source_file')]
    print(f"CSV 文件数: {len(csv_lines)}")
    if csv_lines:
        print(f"CSV 首个: {csv_lines[0].strip()}")
        print(f"CSV 末个: {csv_lines[-1].strip()}")
else:
    print("CSV 不存在")

# 检查数据库
conn = sqlite3.connect('data/knowledge/writing_expert_new.db', timeout=30)

t0 = time.time()
cnt = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
print(f"\nchunks 总行数: {cnt:,}")

t0 = time.time()
user_files = conn.execute(
    "SELECT COUNT(DISTINCT source_file) FROM chunks WHERE source_type = 'user'"
).fetchone()[0]
print(f"用户文件数: {user_files:,}")

t0 = time.time()
default_files = conn.execute(
    "SELECT COUNT(DISTINCT source_file) FROM chunks WHERE source_type = 'default'"
).fetchone()[0]
print(f"默认文件数: {default_files:,}")

# 用户文件列表
t0 = time.time()
user_rows = conn.execute(
    "SELECT source_file, source_type, COUNT(*) FROM chunks "
    "WHERE source_type = 'user' GROUP BY source_file"
).fetchall()
print(f"\n用户文件明细 ({len(user_rows)} 个):")
for sf, st, cc in user_rows:
    name = sf.split('\\')[-1].split('/')[-1]
    print(f"  {name}: {cc} 段")

conn.close()
