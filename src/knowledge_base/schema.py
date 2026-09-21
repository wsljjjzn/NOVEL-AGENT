"""
knowledge_base.schema — SQLite 数据库表结构。
"""

import sqlite3
from pathlib import Path
from typing import Optional

SCHEMA_SQL = """
-- 段落块表
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    source_author TEXT DEFAULT '',
    source_year INTEGER DEFAULT 0,
    source_work TEXT DEFAULT '',
    source_genre TEXT DEFAULT '',
    chapter_path TEXT DEFAULT '',
    paragraph_index INTEGER DEFAULT 0,
    text TEXT NOT NULL,
    char_count INTEGER DEFAULT 0,
    source_type TEXT DEFAULT 'default',
    created_at TEXT DEFAULT (datetime('now'))
);

-- 知识单元表
CREATE TABLE IF NOT EXISTS knowledge_units (
    knowledge_unit_id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK(type IN ('idea', 'structure', 'technique', 'language')),
    category TEXT DEFAULT '',
    source_file TEXT DEFAULT '',
    source_location TEXT DEFAULT '',
    description TEXT DEFAULT '',
    mechanism TEXT DEFAULT '',
    effect TEXT DEFAULT '',
    applicable_scenarios TEXT DEFAULT '[]',
    related_units TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    source_type TEXT DEFAULT 'default',
    embedding BLOB,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 风格模板表
CREATE TABLE IF NOT EXISTS style_templates (
    template_id TEXT PRIMARY KEY,
    template_name TEXT NOT NULL,
    quantitative_profile TEXT DEFAULT '{}',
    qualitative_profile TEXT DEFAULT '{}',
    writing_rules TEXT DEFAULT '[]',
    forbidden_patterns TEXT DEFAULT '[]',
    strengths TEXT DEFAULT '[]',
    weaknesses TEXT DEFAULT '[]',
    best_for TEXT DEFAULT '',
    avoid_for TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

-- 写作请求日志
CREATE TABLE IF NOT EXISTS writing_requests (
    request_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    style TEXT DEFAULT '',
    word_count INTEGER DEFAULT 2000,
    audience TEXT DEFAULT '',
    tone_override TEXT DEFAULT '',
    raw_input TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

-- 大纲表
CREATE TABLE IF NOT EXISTS outlines (
    outline_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    title TEXT DEFAULT '',
    outline_json TEXT NOT NULL,
    confirmed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (request_id) REFERENCES writing_requests(request_id)
);

-- 文章表
CREATE TABLE IF NOT EXISTS articles (
    article_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    outline_id TEXT DEFAULT '',
    title TEXT DEFAULT '',
    full_text TEXT DEFAULT '',
    total_words INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (request_id) REFERENCES writing_requests(request_id)
);

-- 审稿报告表
CREATE TABLE IF NOT EXISTS review_reports (
    report_id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    article_id TEXT NOT NULL,
    overall_assessment TEXT DEFAULT '',
    score REAL DEFAULT 0.0,
    report_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (article_id) REFERENCES articles(article_id)
);

-- 角色表
CREATE TABLE IF NOT EXISTS characters (
    character_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    aliases TEXT DEFAULT '[]',
    source_file TEXT DEFAULT '',
    base_profile TEXT DEFAULT '{}',
    personality TEXT DEFAULT '{}',
    dialogue_style TEXT DEFAULT '{}',
    arc_summary TEXT DEFAULT '',
    chapter_states TEXT DEFAULT '[]',
    relationship_map TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);

-- 文件统计索引表（避免 GROUP BY 全表扫描）
CREATE TABLE IF NOT EXISTS file_index (
    source_file TEXT PRIMARY KEY,
    source_type TEXT DEFAULT 'default',
    chunk_count INTEGER DEFAULT 0,
    total_chars INTEGER DEFAULT 0
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_file);
CREATE INDEX IF NOT EXISTS idx_chunks_source_type ON chunks(source_type);
CREATE INDEX IF NOT EXISTS idx_chunks_group ON chunks(source_type, source_file, char_count);
CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge_units(type);
CREATE INDEX IF NOT EXISTS idx_articles_request ON articles(request_id);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """初始化数据库，创建所有表。

    Args:
        db_path: 数据库文件路径

    Returns:
        sqlite3.Connection
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)

    # 兼容迁移：为已有表添加 source_type 列（如已存在则静默忽略）
    for table, col in [("chunks", "source_type"), ("knowledge_units", "source_type")]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT DEFAULT 'default'")
        except Exception:
            pass  # 列已存在

    conn.commit()
    return conn
