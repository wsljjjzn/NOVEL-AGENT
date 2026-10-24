"""
scripts/package_windows_release.py — 打包针对 Windows 用户的专属开箱即用发布包。
输出: dist/Novel-Studio-Windows-v0.1.0.zip
"""

import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
OUT_ZIP = DIST_DIR / "Novel-Studio-Windows-v0.1.0.zip"

EXCLUDE_DIRS = {
    ".git", ".venv", "venv", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "__pycache__", "course_materials", "dist",
    ".idea", ".vscode", "logs", ".agent-scratch"
}

EXCLUDE_EXTS = {
    ".pyc", ".pyo", ".pyd", ".tmp", ".bak", ".log", ".DS_Store"
}

def should_exclude(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS or part.startswith(".git"):
            return True
        if part.startswith("project.json.bak-"):
            return True
    if path.suffix in EXCLUDE_EXTS:
        return True
    if path.name.startswith("."):
        return True
    return False

def write_to_zip(zf: zipfile.ZipFile, file_path: Path, arcname: str):
    # Windows 专属包：强制确保批处理与文本以 CRLF 换行存储，杜绝 cmd.exe 偏移漂移
    if file_path.suffix.lower() in {".bat", ".cmd", ".txt"}:
        raw = file_path.read_bytes()
        raw = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        zf.writestr(arcname, raw)
    else:
        zf.write(file_path, arcname)

def build_zip():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_ZIP.exists():
        OUT_ZIP.unlink()

    print(f"正在打包 Windows 专属开箱即用压缩包 -> {OUT_ZIP.name} ...")
    archive_root = "Novel-Studio-Windows-v0.1.0"
    count = 0

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # 1. 顶层核心引导文件
        top_files = [
            "一键启动.bat",
            "停止服务.bat",
            "使用说明.txt",
            "pyproject.toml",
            "uv.lock",
            "main.py",
            "tui.py",
            "README.md"
        ]
        for tf in top_files:
            p = ROOT / tf
            if p.exists():
                arcname = f"{archive_root}/{tf}"
                write_to_zip(zf, p, arcname)
                count += 1
                print(f"  + {arcname}")

        # 2. 独立 HTML 客户端
        html_src = ROOT / "web_prototype" / "index.html"
        if html_src.exists():
            arcname = f"{archive_root}/Novel-Studio-Web.html"
            write_to_zip(zf, html_src, arcname)
            count += 1
            print(f"  + {arcname}")

        # 3. 递归添加核心目录：src, web_prototype, config, data
        target_dirs = ["src", "web_prototype", "config", "data"]
        for td in target_dirs:
            base_dir = ROOT / td
            if not base_dir.exists():
                continue
            for root, dirs, files in os.walk(base_dir):
                # 过滤目录
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
                for f in files:
                    file_path = Path(root) / f
                    if should_exclude(file_path):
                        continue
                    # 避免打入超大语料库（保留知识库索引和示例项目即可）
                    if "user_uploads" in file_path.parts or "doc" in file_path.parts:
                        continue
                    rel = file_path.relative_to(ROOT)
                    arcname = f"{archive_root}/{rel.as_posix()}"
                    write_to_zip(zf, file_path, arcname)
                    count += 1

    size_mb = OUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"\n[OK] 打包完成！共包含 {count} 个文件，压缩包大小: {size_mb:.2f} MB")
    print(f"输出路径: {OUT_ZIP}")

if __name__ == "__main__":
    build_zip()
