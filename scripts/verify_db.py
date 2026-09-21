"""快速验证脚本。"""
import sys
sys.path.insert(0, ".")

from src.knowledge_base import init_db
from config.settings import get_config

cfg = get_config()
db_path = cfg.database.get("path", "data/knowledge/writing_expert.db")
conn = init_db(db_path)
tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()
print("Tables:", [t[0] for t in tables])
conn.close()
print("=== DB OK ===")
