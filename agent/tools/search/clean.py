# -*- coding: utf-8 -*-
"""
搜索工具 - 数据清理封装：对指定版面（或 分类/版面）下的帖子 JSON 做 content 分块清理并写回。
调用 knowledge.processing.clean，不实例化任何浏览器。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from pathlib import Path

from knowledge.processing.clean import clean_board as _clean_board
from knowledge.processing.clean import clean_json_files as _clean_json_files
from knowledge.processing.clean import get_board_json_paths
from utils.path_tool import get_abs_path


def clean_post_files(file_paths: list[str] | list[Path]) -> int:
    """
    仅对给定的帖子 JSON 文件做 content 分块清理并写回，不处理版面下其他旧文件。
    :param file_paths: 本次新保存的 JSON 文件路径列表（str 或 Path）
    :return: 成功处理并写回的文件数量
    """
    return _clean_json_files(file_paths)


def get_board_data_paths(
    board: str,
    data_root: str | Path | None = None,
) -> list[Path]:
    """
    获取指定版面下所有帖子 JSON 的文件路径。
    :param board: 版面名（如「创意生活」）或「分类/版面」（如「生活时尚/创意生活」）
    :param data_root: 动态数据根目录，None 时使用项目下的 data/dynamic
    :return: 该版面下所有 .json 的 Path 列表
    """
    if data_root is None:
        data_root = get_abs_path("data/dynamic")
    return get_board_json_paths(Path(data_root), board)


def clean_board_posts(
    board: str,
    data_root: str | Path | None = None,
) -> int:
    """
    清理指定版面下所有帖子的 content：按发信人、信区、标题、发信站、正文、来源分块并写回原文件。
    :param board: 版面名（如「悄悄话」）或「分类/版面」（如「生活时尚/悄悄话」）
    :param data_root: 动态数据根目录，None 时使用项目下的 data/dynamic
    :return: 处理并写回的 JSON 文件数量
    """
    if data_root is None:
        data_root = get_abs_path("data/dynamic")
    return _clean_board(board=board, data_root=data_root)
