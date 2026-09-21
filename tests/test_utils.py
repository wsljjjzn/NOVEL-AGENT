"""测试：工具模块。"""

import os
import tempfile
from pathlib import Path

from src.utils.file_utils import detect_encoding, read_text_file, list_text_files, ensure_dir
from src.utils.logger import setup_logger


class TestFileUtils:
    def test_detect_encoding_utf8(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         encoding="utf-8", delete=False) as f:
            f.write("测试文本")
            f_path = f.name
        try:
            enc = detect_encoding(f_path)
            # chardet 可能返回 'utf-8' 或 'UTF-8-SIG'
            assert enc.lower().replace("-sig", "") == "utf-8"
        finally:
            os.unlink(f_path)

    def test_detect_encoding_gbk(self):
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            f.write("测试".encode("gbk"))
            f_path = f.name
        try:
            enc = detect_encoding(f_path)
            assert "gb" in enc.lower()
        finally:
            os.unlink(f_path)

    def test_read_text_file_utf8(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         encoding="utf-8", delete=False) as f:
            f.write("Hello 世界")
            f_path = f.name
        try:
            text = read_text_file(f_path)
            assert text == "Hello 世界"
        finally:
            os.unlink(f_path)

    def test_list_text_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建临时文件
            Path(tmpdir, "a.txt").write_text("hello", encoding="utf-8")
            Path(tmpdir, "b.md").write_text("world", encoding="utf-8")
            Path(tmpdir, "c.py").write_text("print(1)", encoding="utf-8")
            os.makedirs(os.path.join(tmpdir, "sub"))
            Path(tmpdir, "sub", "d.txt").write_text("nested", encoding="utf-8")

            files = list_text_files(tmpdir, {".txt", ".md"})
            # 应该找到 a.txt, b.md, sub/d.txt
            assert len(files) == 3
            assert any(f.endswith("a.txt") for f in files)
            assert any(f.endswith("b.md") for f in files)
            assert any(f.endswith("d.txt") for f in files)

    def test_ensure_dir_creates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "a", "b", "c")
            p = ensure_dir(new_dir)
            assert os.path.isdir(new_dir)
            assert str(p) == new_dir

    def test_ensure_dir_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = ensure_dir(tmpdir)
            assert os.path.isdir(tmpdir)


class TestLogger:
    def test_setup_logger_no_error(self):
        from loguru import logger as loguru_logger
        tmpdir = tempfile.mkdtemp()
        try:
            log_dir = os.path.join(tmpdir, "logs")
            setup_logger(log_dir=log_dir, level="ERROR")
            assert Path(log_dir).is_dir()
            # 清理 logger 句柄以释放文件锁
            loguru_logger.remove()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
