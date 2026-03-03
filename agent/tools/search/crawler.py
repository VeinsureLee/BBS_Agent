# -*- coding: utf-8 -*-
"""
搜索工具 - 版面爬取封装：根据 forum/board/二级 board 调用 forum_updater 爬取并保存帖子 JSON。
不实例化浏览器，仅提供函数，由调用方传入 browser。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import asyncio
from typing import Any

from knowledge.ingestion.forum_updater import (
    load_forum_structure,
    get_board_by_section_subsection_and_name,
    update_board_posts,
)
from utils.path_tool import get_abs_path


def get_board_info(
    forum: str,
    board: str,
    sub_board: str | None = None,
    structure_path: str | None = None,
) -> dict | None:
    """
    根据讨论区、版面及可选的二级目录名称，从结构文件中解析出版面信息。
    :param forum: 讨论区名称（如「北邮校园」「生活时尚」）
    :param board: 版面名称（如「北邮图书馆」「悄悄话」）
    :param sub_board: 二级目录名称（可选，如「院系校区」「社团组织」）
    :param structure_path: 论坛结构 JSON 路径，None 时使用默认 data/web_structure/forum_structure.json
    :return: 版面 dict（含 id, name, url 等），未找到返回 None
    """
    structure = load_forum_structure(structure_path=structure_path)
    return get_board_by_section_subsection_and_name(
        structure,
        section_name=forum,
        board_name=board,
        sub_section_name=sub_board,
    )


async def crawl_board_and_save(
    browser: Any,
    base_url: str,
    forum: str,
    board: str,
    sub_board: str | None = None,
    max_pages: int = 2,
    concurrency: int = 32,
    output_root: str | None = None,
    structure_path: str | None = None,
) -> list[str]:
    """
    爬取指定版面多页帖子并保存为 JSON。不创建浏览器，由调用方传入 browser。
    :param browser: GlobalBrowser 实例（已 start，可选已登录）
    :param base_url: BBS 根 URL（如 https://bbs.byr.cn）
    :param forum: 讨论区名称
    :param board: 版面名称
    :param sub_board: 二级目录名称（可选）
    :param max_pages: 爬取页数（1=仅首页）
    :param concurrency: 并发线程数
    :param output_root: 输出根目录，None 时使用 data/dynamic
    :param structure_path: 论坛结构 JSON 路径，None 时使用默认
    :return: 已保存的文件路径列表
    """
    board_info = get_board_info(
        forum=forum,
        board=board,
        sub_board=sub_board,
        structure_path=structure_path,
    )
    if not board_info:
        return []

    if output_root is None:
        output_root = get_abs_path("data/dynamic")

    return await update_board_posts(
        browser=browser,
        base_url=base_url,
        section_name=forum,
        board=board_info,
        output_root=output_root,
        max_pages=max_pages,
        concurrency=concurrency,
    )


def run_crawl_board_and_save(
    browser: Any,
    base_url: str,
    forum: str,
    board: str,
    sub_board: str | None = None,
    max_pages: int = 2,
    concurrency: int = 32,
    output_root: str | None = None,
    structure_path: str | None = None,
) -> list[str]:
    """
    同步包装：在已有事件循环或新事件循环中执行 crawl_board_and_save。
    :param browser: GlobalBrowser 实例
    :param base_url: BBS 根 URL
    :param forum: 讨论区名称
    :param board: 版面名称
    :param sub_board: 二级目录名称（可选）
    :param max_pages: 爬取页数
    :param concurrency: 并发数
    :param output_root: 输出根目录
    :param structure_path: 论坛结构路径
    :return: 已保存的文件路径列表
    """
    return asyncio.run(
        crawl_board_and_save(
            browser=browser,
            base_url=base_url,
            forum=forum,
            board=board,
            sub_board=sub_board,
            max_pages=max_pages,
            concurrency=concurrency,
            output_root=output_root,
            structure_path=structure_path,
        )
    )
