# -*- coding: utf-8 -*-
"""
搜索工具：按 forum/board/二级 board 爬取版面、清理帖子 JSON、向量化存储。
仅提供函数，不实例化浏览器；调用方在 search.py 的 main 中实例浏览器并测试。
"""
from .crawler import (
    get_board_info,
    crawl_board_and_save,
    run_crawl_board_and_save,
)
from .clean import (
    get_board_data_paths,
    clean_board_posts,
    clean_post_files,
)
from .search import (
    crawl_clean_and_vectorize,
    run_crawl_clean_and_vectorize,
)

__all__ = [
    "get_board_info",
    "crawl_board_and_save",
    "run_crawl_board_and_save",
    "get_board_data_paths",
    "clean_board_posts",
    "clean_post_files",
    "crawl_clean_and_vectorize",
    "run_crawl_clean_and_vectorize",
]
