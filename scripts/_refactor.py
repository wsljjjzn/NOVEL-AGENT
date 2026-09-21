"""Replace file_index/GROUP BY with CSV index."""

_CSV_PATH = 'data/knowledge/index.csv'

CODE = f'''
_CSV_PATH = Path("{_CSV_PATH}")

def _rebuild_csv():
    """从 DB 全量重建 CSV 索引。"""
    rows = bridge.conn.execute(
        "SELECT source_file, source_type, COUNT(*) as cc, SUM(char_count) as tc "
        "FROM chunks GROUP BY source_file ORDER BY source_type, source_file"
    ).fetchall()
    _CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CSV_PATH, "w", encoding="utf-8") as f:
        f.write("source_file,type,chunks,chars\\n")
        for sf, st, cc, tc in rows:
            f.write(f"{{sf}},{{st}},{{cc}},{{tc or 0}}\\n")

def _read_csv():
    """读取 CSV 索引，返回 [(source_file, type, chunks, chars), ...]"""
    if not _CSV_PATH.exists():
        _rebuild_csv()
    rows = []
    with open(_CSV_PATH, "r", encoding="utf-8") as f:
        next(f)  # skip header
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",", 3)
            if len(parts) == 4:
                rows.append((parts[0], parts[1], int(parts[2]), int(parts[3])))
    return rows

def _add_to_csv(source_file, source_type, chunks, chars):
    rows = _read_csv()
    # 替换或追加
    for i, (sf, st, cc, ch) in enumerate(rows):
        if sf == source_file:
            rows[i] = (source_file, source_type, chunks, chars)
            break
    else:
        rows.append((source_file, source_type, chunks, chars))
    rows.sort(key=lambda r: (r[1], r[0]))
    with open(_CSV_PATH, "w", encoding="utf-8") as f:
        f.write("source_file,type,chunks,chars\\n")
        for sf, st, cc, ch in rows:
            f.write(f"{{sf}},{{st}},{{cc}},{{ch}}\\n")

def _remove_from_csv(source_file):
    rows = [r for r in _read_csv() if r[0] != source_file]
    with open(_CSV_PATH, "w", encoding="utf-8") as f:
        f.write("source_file,type,chunks,chars\\n")
        for sf, st, cc, ch in rows:
            f.write(f"{{sf}},{{st}},{{cc}},{{ch}}\\n")
'''

with open('src/api/gradio_app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Step 1: Replace kb_list_files to read from CSV
old1 = '''def kb_list_files(source_filter: str = "all", page: int = 1):
    """列出知识库文件（分页，每页 50 条，带编号）。返回 (表格, 当前页码)。"""
    try:
        conn = bridge.conn
        where = ""
        if source_filter == "default":
            where = "WHERE source_type = 'default'"
        elif source_filter == "user":
            where = "WHERE source_type = 'user'"
        rows = conn.execute(
            f"SELECT source_file, source_type, COUNT(*) as cc, SUM(char_count) as tc "
            f"FROM chunks {where} GROUP BY source_file ORDER BY source_type, source_file"
        ).fetchall()
        if not rows:
            return "暂无已导入的文件", page
        per_page = 50
        total = len(rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        page_rows = rows[start:start + per_page]
        lines = [
            f"**共 {total} 个文件 | 第 {page}/{total_pages} 页**",
            "",
            "| 编号 | 文件名 | 类型 | 段落块 | 字符数 |",
            "|------|--------|------|--------|--------|",
        ]
        for i, (fname, stype, cc, tc) in enumerate(page_rows, start + 1):
            label = "\\U0001f4d6" if stype == "default" else "\\U0001f464"
            name = Path(fname).name
            cs = f"{tc:,}" if tc else "-"
            lines.append(f"| **{i}** | `{name}` | {label} | {cc:,} | {cs} |")
        return "\\n".join(lines), page
    except Exception as e:
        return f"查询失败: {e}", page'''

new1 = '''def kb_list_files(source_filter: str = "all", page: int = 1):
    """列出知识库文件（分页，每页 50 条，带编号）。从 CSV 索引读取。"""
    try:
        all_rows = _read_csv()
        if source_filter == "user":
            all_rows = [r for r in all_rows if r[1] == "user"]
        elif source_filter == "default":
            all_rows = [r for r in all_rows if r[1] == "default"]
        if not all_rows:
            return "暂无已导入的文件", page
        per_page = 50
        total = len(all_rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        page_rows = all_rows[start:start + per_page]
        lines = [
            f"**共 {total} 个文件 | 第 {page}/{total_pages} 页**",
            "",
            "| 编号 | 文件名 | 类型 | 段落块 | 字符数 |",
            "|------|--------|------|--------|--------|",
        ]
        for i, (fname, stype, cc, tc) in enumerate(page_rows, start + 1):
            label = "\\U0001f4d6" if stype == "default" else "\\U0001f464"
            name = Path(fname).name
            lines.append(f"| **{i}** | `{name}` | {label} | {cc:,} | {tc:,} |")
        return "\\n".join(lines), page
    except Exception as e:
        return f"查询失败: {e}", page'''

if old1 in content:
    content = content.replace(old1, new1, 1)
    print("Step 1 OK")
else:
    print("Step 1 FAIL")

# Step 2: Remove old _update_file_index / _get_file_rows, insert CSV functions
old2 = '''# 文件统计索引（替代 GROUP BY 全表扫描）
def _update_file_index(source_file: str = None):
    """增量更新 file_index。指定文件则只更新该文件，否则从 chunks 全量重建。"""
    conn = bridge.conn
    if source_file:
        row = conn.execute(
            "SELECT source_type, COUNT(*), SUM(char_count) FROM chunks WHERE source_file = ? GROUP BY source_file",
            (source_file,)
        ).fetchone()
        if row:
            stype, cc, tc = row
            conn.execute(
                "INSERT OR REPLACE INTO file_index (source_file, source_type, chunk_count, total_chars) VALUES (?, ?, ?, ?)",
                (source_file, stype, cc, tc or 0),
            )
        else:
            conn.execute("DELETE FROM file_index WHERE source_file = ?", (source_file,))
        conn.commit()
    else:
        conn.execute("DELETE FROM file_index")
        conn.execute("""
            INSERT INTO file_index (source_file, source_type, chunk_count, total_chars)
            SELECT source_file, source_type, COUNT(*), SUM(char_count)
            FROM chunks GROUP BY source_file, source_type
        """)
        conn.commit()


def _get_file_rows(source_filter="all"):
    """从 file_index 查询文件列表（无需 GROUP BY）。"""
    conn = bridge.conn
    where = ""
    if source_filter == "default":
        where = "WHERE source_type = 'default'"
    elif source_filter == "user":
        where = "WHERE source_type = 'user'"
    count = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
    if count == 0:
        _update_file_index()
    rows = conn.execute(
        f"SELECT source_file, source_type, chunk_count, total_chars "
        f"FROM file_index {where} ORDER BY source_type, source_file"
    ).fetchall()
    return rows'''

new2 = CODE

if old2 in content:
    content = content.replace(old2, new2, 1)
    print("Step 2 OK")
else:
    print("Step 2 FAIL")

# Step 3: Replace _get_file_rows usage in kb_delete_file
old3 = '''        rows = _get_file_rows(source_filter)'''
new3 = '''        rows = _read_csv()
        if source_filter == "user":
            rows = [r for r in rows if r[1] == "user"]
        elif source_filter == "default":
            rows = [r for r in rows if r[1] == "default"]'''

if old3 in content:
    content = content.replace(old3, new3, 1)
    print("Step 3 OK")
else:
    print("Step 3 FAIL")

# Step 4: Replace remaining _get_file_rows usage
old4 = '''        remaining = _get_file_rows(source_filter)'''
new4 = '''        remaining = _read_csv()
        if source_filter == "user":
            remaining = [r for r in remaining if r[1] == "user"]
        elif source_filter == "default":
            remaining = [r for r in remaining if r[1] == "default"]'''

if old4 in content:
    content = content.replace(old4, new4, 1)
    print("Step 4 OK")
else:
    print("Step 4 FAIL")

# Step 5: Replace _update_file_index call in handle_learn_file with _add_to_csv
old5 = '''        # 增量更新 file_index
        try:
            if 'target' in dir() and target:
                _update_file_index(str(target))
        except Exception:
            pass'''

new5 = '''        # 增量更新 CSV 索引
        try:
            if 'target' in dir() and target:
                stats = locals().get('stats', {})
                _add_to_csv(str(target), "user", stats.get('chunks', 0), stats.get('char_count', 0))
        except Exception:
            pass'''

if old5 in content:
    content = content.replace(old5, new5, 1)
    print("Step 5 OK")
else:
    print("Step 5 FAIL")

# Step 6: Replace DELETE chunks + DELETE file_index with _remove_from_csv
old6 = '''                    conn = bridge.conn
                    conn.execute("DELETE FROM knowledge_units WHERE source_file = ?", (fname,))
                    conn.execute("DELETE FROM chunks WHERE source_file = ?", (fname,))
                    conn.execute("DELETE FROM file_index WHERE source_file = ?", (fname,))
                    conn.commit()
                    deleted.append(Path(fname).name)'''
new6 = '''                    conn = bridge.conn
                    conn.execute("DELETE FROM knowledge_units WHERE source_file = ?", (fname,))
                    conn.execute("DELETE FROM chunks WHERE source_file = ?", (fname,))
                    conn.commit()
                    _remove_from_csv(fname)
                    deleted.append(Path(fname).name)'''

if old6 in content:
    content = content.replace(old6, new6, 1)
    print("Step 6 OK")
else:
    print("Step 6 FAIL")

with open('src/api/gradio_app.py', 'w', encoding='utf-8') as f:
    f.write(content)

import ast
try:
    ast.parse(content)
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax error at line {e.lineno}: {e.msg}")
    lines = content.split('\\n')
    for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+3)):
        prefix = '>>>' if i == e.lineno-1 else '   '
        clean = ''.join(c if ord(c) < 128 else '?' for c in lines[i])
        print(f'{prefix} {i+1}: {clean[:120]}')
