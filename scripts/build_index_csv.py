"""
知识库文件索引 CSV 构建工具
运行一次，建立 data/knowledge/index.csv
之后应用启动直接读 CSV，不再查数据库。
"""
import sqlite3, os, time

db_path = "data/knowledge/writing_expert_new.db"
csv_path = "data/knowledge/index.csv"

if not os.path.exists(db_path):
    print(f"❌ 数据库不存在: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path, timeout=120)

t0 = time.time()
total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
print(f"chunks 表总行数: {total:,}")

# 用 LIMIT + OFFSET 分批 GROUP BY，避免一次加载全部结果
os.makedirs(os.path.dirname(csv_path), exist_ok=True)
t0 = time.time()
batch = 500
offset = 0
written = 0

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("source_file\ttype\tchunks\tchars\n")
    while True:
        rows = conn.execute(
            "SELECT source_file, source_type, COUNT(*) as cc, SUM(char_count) as tc "
            "FROM chunks GROUP BY source_file, source_type "
            "ORDER BY source_type, source_file LIMIT ? OFFSET ?",
            (batch, offset)
        ).fetchall()
        if not rows:
            break
        for sf, st, cc, tc in rows:
            f.write(f"{sf}\t{st}\t{cc}\t{tc or 0}\n")
        written += len(rows)
        offset += batch
        if offset % 2000 == 0:
            print(f"  进度: {offset} 个文件 ({time.time()-t0:.1f}s)")

print(f"✅ CSV 已生成: {csv_path}")
print(f"   文件数: {written}")
print(f"   大小: {os.path.getsize(csv_path)/1024:.1f} KB")
print(f"   耗时: {time.time()-t0:.1f}s")

# 验证
check = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
if check > 0:
    print(f"\n📌 file_index 表有 {check:,} 条记录，可以删除重建，也可以留着")
print(f"📌 现在启动应用，文件列表将直接从 CSV 读取")
conn.close()
