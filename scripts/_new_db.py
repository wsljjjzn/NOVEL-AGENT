"""Create new empty database and update config."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_base import init_db

# Create new empty DB
conn = init_db("data/knowledge/writing_expert_new.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("新数据库已创建, 表:", [t[0] for t in tables])
conn.close()

# Update config
import yaml
with open("config/config.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
cfg["database"]["path"] = "data/knowledge/writing_expert_new.db"
with open("config/config.yaml", "w", encoding="utf-8") as f:
    yaml.dump(cfg, f, allow_unicode=True)
print("config.yaml 已更新为新数据库路径")
