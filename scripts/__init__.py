"""scripts — 开发与运维脚本（批量预处理、索引重建、数据检查等）。

有这个文件是为了让 hatchling 把 `scripts` 当成可安装的包：
`na-tools-preprocess` 这条 console script 需要 `scripts.batch_preprocess:main`
能从任意目录被导入（见 `src/cli/entrypoints.py`）。
"""
