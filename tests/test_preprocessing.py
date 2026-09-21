"""测试：文献预处理管线。"""

import tempfile
from pathlib import Path

from src.preprocessing import PreprocessingPipeline


class TestPreprocessing:
    def setup_method(self):
        self.pipeline = PreprocessingPipeline()

    def test_clean_text_removes_control_chars(self):
        dirty = "Hello\x00World\x1fTest\n"
        clean = self.pipeline.clean_text(dirty)
        assert "\x00" not in clean
        assert "\x1f" not in clean

    def test_clean_text_collapses_excess_newlines(self):
        text = "Line1\n\n\n\n\nLine2\n\nLine3"
        clean = self.pipeline.clean_text(text)
        # 最多保留两个连续换行
        assert "\n\n\n" not in clean

    def test_clean_text_strips_whitespace(self):
        text = "  \n\n内容\n\n  "
        clean = self.pipeline.clean_text(text)
        assert clean == "内容"

    def test_split_paragraphs(self):
        text = "第一段内容。\n\n第二段内容。\n\n\n第三段内容。"
        paras = self.pipeline.split_paragraphs(text)
        assert len(paras) == 3

    def test_split_paragraphs_no_double_newline(self):
        text = "只有一段"
        paras = self.pipeline.split_paragraphs(text)
        assert len(paras) == 1

    def test_is_noise_short_lines(self):
        assert self.pipeline.is_noise("短") is True       # < 10 chars
        assert self.pipeline.is_noise("") is True          # empty
        assert self.pipeline.is_noise("这是一句超过十个字的测试文本") is False

    def test_create_chunk(self):
        chunk = self.pipeline.create_chunk(
            text="测试内容",
            source_file="test.txt",
            para_index=0,
            chapter="第一章",
        )
        assert chunk.source_file == "test.txt"
        assert chunk.paragraph_index == 0
        assert chunk.chapter_path == "第一章"
        assert chunk.char_count == 4

    def test_process_file(self):
        """用小样本文档验证完整管线。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write("这是第一段。它包含一些用来测试预处理管线的文本内容。\n\n")
            f.write("这是第二段。同样需要一定的字数来确保超过最小长度限制。\n\n")
            f.write("这是第三段。预处理管线应该能正确识别并处理它。\n")
            f_path = f.name

        try:
            chunks = self.pipeline.process_file(f_path)
            assert len(chunks) == 3
            assert Path(chunks[0].source_file).name == Path(f_path).name
            assert chunks[0].char_count > 0
            assert chunks[0].paragraph_index == 0
            assert chunks[1].paragraph_index == 1
            assert chunks[2].paragraph_index == 2
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_process_file_empty(self):
        """空文件应返回空列表。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write("")
            f_path = f.name

        try:
            chunks = self.pipeline.process_file(f_path)
            assert len(chunks) == 0
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_process_directory_max_files(self):
        """测试目录处理，限制文件数。"""
        import os
        chunks = self.pipeline.process_directory(
            "data/samples", max_files=1
        )
        assert isinstance(chunks, list)
