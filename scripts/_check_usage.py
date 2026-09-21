"""检查知识库使用情况"""
import sqlite3

conn = sqlite3.connect('data/knowledge/writing_expert_new.db', timeout=30)

# 用户知识单元
rows = conn.execute(
    "SELECT type, source_file, description FROM knowledge_units WHERE source_type = 'user'"
).fetchall()
print(f"用户知识单元: {len(rows)} 条")
for r in rows:
    print(f"  [{r[0]}] {r[1]}: {r[2][:80]}")

# 默认知识单元数量
cnt = conn.execute("SELECT COUNT(*) FROM knowledge_units WHERE source_type = 'default'").fetchone()[0]
print(f"\n默认知识单元: {cnt:,} 条")

# 用户 chunks
cnt2 = conn.execute("SELECT COUNT(*) FROM chunks WHERE source_type = 'user'").fetchone()[0]
print(f"用户 chunks: {cnt2:,} 条")

# 默认识别用户文件的 system prompt
print("\n--- 检索测试 ---")
topic = "重生醒来，校花变同桌"
idea_units = conn.execute(
    "SELECT description, source_type FROM knowledge_units WHERE type = 'idea' "
    "AND (description LIKE ? OR description LIKE ?) LIMIT 5",
    (f"%{topic[:6]}%", "%写作%")
).fetchall()
print(f"主题'{topic[:6]}'匹配到 {len(idea_units)} 条 idea")
for u in idea_units:
    print(f"  [{'用户' if u[1]=='user' else '默认'}] {u[0][:80]}")

conn.close()
