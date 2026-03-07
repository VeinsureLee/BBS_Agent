# -*- coding: utf-8 -*-
"""
查询工具：基于 knowledge.retrieval 分模块读取用户数据、历史帖子数据、网站信息数据。

- 用户数据：入参 query，回参对应的用户数据文件。
- 历史爬取帖子：入参 query、版面（section/board 或 board_path），回参该版面下与 query 相关的帖子信息文件。
- 网站信息：入参 query，回参对应的版面列表（hierarchy_path、board_name 等）。
"""
from .user_data import (
    query_user_data,
    query_user_data_files,
)
from .post_data import (
    query_post_data,
    query_post_data_files,
)
from .structure_data import (
    query_structure_boards,
    query_structure_boards_simple,
    query_structure_documents,
)

__all__ = [
    "query_user_data",
    "query_user_data_files",
    "query_post_data",
    "query_post_data_files",
    "query_structure_boards",
    "query_structure_boards_simple",
    "query_structure_documents",
]
