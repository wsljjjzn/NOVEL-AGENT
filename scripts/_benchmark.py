import sqlite3, time
conn = sqlite3.connect('data/knowledge/writing_expert_new.db', timeout=60)

# 测试 1: chunks 行数
t0 = time.time()
total = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
print('chunks: %d 行 (%.2fs)' % (total, time.time() - t0))

# 测试 2: 文件去重数
t0 = time.time()
files = conn.execute('SELECT COUNT(DISTINCT source_file) FROM chunks').fetchone()[0]
print('去重文件数: %d (%.2fs)' % (files, time.time() - t0))

# 测试 3: GROUP BY 耗时
t0 = time.time()
try:
    rows = conn.execute(
        'SELECT source_file, source_type, COUNT(*) as cc, SUM(char_count) as tc '
        'FROM chunks GROUP BY source_file, source_type'
    ).fetchall()
    print('GROUP BY 查询: %d 条 (%.2fs)' % (len(rows), time.time() - t0))
except Exception as e:
    print('GROUP BY 失败:', e)

# 测试 4: 只查 user 类型
t0 = time.time()
rows2 = conn.execute(
    'SELECT source_file, source_type, COUNT(*) as cc, SUM(char_count) as tc '
    "FROM chunks WHERE source_type = 'user' GROUP BY source_file"
).fetchall()
t2 = time.time()
print('GROUP BY(user): %d 条 (%.2fs)' % (len(rows2), t2 - t0))

# 测试 5: 写入 file_index
t0 = time.time()
conn.execute('DELETE FROM file_index')
conn.execute("""
    INSERT INTO file_index (source_file, source_type, chunk_count, total_chars)
    SELECT source_file, source_type, COUNT(*), SUM(char_count)
    FROM chunks GROUP BY source_file, source_type
""")
conn.commit()
t1 = time.time()
print('写入 file_index: (%.2fs)' % (t1 - t0))

# 测试 6: file_index 查询
t0 = time.time()
all_rows = conn.execute('SELECT * FROM file_index').fetchall()
print('file_index 查询全部: %d 条 (%.2fs)' % (len(all_rows), time.time() - t0))

t0 = time.time()
user_rows = conn.execute("SELECT * FROM file_index WHERE source_type = 'user'").fetchall()
print('file_index 查询用户: %d 条 (%.3fs)' % (len(user_rows), time.time() - t0))

conn.close()
