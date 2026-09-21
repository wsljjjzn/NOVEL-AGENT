"""Fast DB stats query."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_base import init_db

conn = init_db("data/knowledge/writing_expert.db")

# Fast metadata
pc = conn.execute("PRAGMA page_count").fetchone()[0]
ps = conn.execute("PRAGMA page_size").fetchone()[0]
db_size = pc * ps

# File count (index scan)
files = conn.execute("SELECT COUNT(DISTINCT source_file) FROM chunks").fetchone()[0]
units = conn.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]

print(f"数据库大小: {db_size/1024/1024/1024:.0f} GB")
print(f"去重源文件: {files}")
print(f"已有知识单元: {units}")

conn.close()
