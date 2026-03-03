# -*- coding: utf-8 -*-
"""
搜索工具 - 主流程：爬取版面 -> 数据清理 -> 向量化存储。
在 main 中实例化浏览器并调用本流程进行测试，入参全部具体写出。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import asyncio

from typing import Any

from knowledge.ingestion.utils_tools import sanitize_dir
from knowledge.stores.dynamic_store import init_dynamic_store
from utils.path_tool import get_abs_path

from agent.tools.search.crawler import crawl_board_and_save
from agent.tools.search.clean import clean_post_files


async def crawl_clean_and_vectorize(
    browser: Any,
    base_url: str,
    forum: str,
    board: str,
    sub_board: str | None = None,
    max_pages: int = 2,
    concurrency: int = 32,
    output_root: str | None = None,
    structure_path: str | None = None,
    data_root: str | None = None,
    vector_store_workers: int = 4,
) -> dict:
    """
    爬取指定版面 -> 清理帖子 JSON -> 将对应目录向量化写入动态库。
    不创建浏览器，由调用方传入 browser。
    :param browser: GlobalBrowser 实例
    :param base_url: BBS 根 URL
    :param forum: 讨论区名称
    :param board: 版面名称
    :param sub_board: 二级目录名称（可选）
    :param max_pages: 爬取页数
    :param concurrency: 爬取并发数
    :param output_root: 爬取输出根目录，None 时使用 data/dynamic
    :param structure_path: 论坛结构 JSON 路径
    :param data_root: 清理与向量化使用的数据根目录，None 时与 output_root 一致
    :param vector_store_workers: 向量化加载线程数
    :return: {"saved_paths": list[str], "cleaned_count": int, "vector_store_ok": bool}
    """
    if output_root is None:
        output_root = get_abs_path("data/dynamic")
    if data_root is None:
        data_root = output_root

    saved_paths = await crawl_board_and_save(
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

    # 仅清理本次新保存的文件，不处理版面下已有旧文件
    cleaned_count = clean_post_files(saved_paths)

    folder_for_vector = os.path.join(data_root, sanitize_dir(forum), sanitize_dir(board))
    vector_store_ok = init_dynamic_store(
        folder_path=folder_for_vector,
        max_workers=vector_store_workers,
    )

    return {
        "saved_paths": saved_paths,
        "cleaned_count": cleaned_count,
        "vector_store_ok": vector_store_ok,
    }


def run_crawl_clean_and_vectorize(
    browser: Any,
    base_url: str,
    forum: str,
    board: str,
    sub_board: str | None = None,
    max_pages: int = 2,
    concurrency: int = 32,
    output_root: str | None = None,
    structure_path: str | None = None,
    data_root: str | None = None,
    vector_store_workers: int = 4,
) -> dict:
    """
    同步包装：执行 crawl_clean_and_vectorize。
    """
    return asyncio.run(
        crawl_clean_and_vectorize(
            browser=browser,
            base_url=base_url,
            forum=forum,
            board=board,
            sub_board=sub_board,
            max_pages=max_pages,
            concurrency=concurrency,
            output_root=output_root,
            structure_path=structure_path,
            data_root=data_root,
            vector_store_workers=vector_store_workers,
        )
    )


def main() -> None:
    """测试入口：实例化浏览器，登录（如有配置），爬取指定版面并清理、向量化。入参全部具体写出。"""
    import os
    import asyncio

    from utils.config_handler import load_config
    from utils.env_handler import load_env, get_bbs_credentials
    from infrastructure.browser_manager.browser_manager import GlobalBrowser
    from infrastructure.browser_manager.login import login

    # 入参全部具体写出
    forum = "生活时尚"
    board = "悄悄话"
    sub_board = None  # 可选，如 "院系校区"
    max_pages = 2
    concurrency = 16
    output_root = get_abs_path("data/dynamic")
    structure_path = get_abs_path("data/web_structure/forum_structure.json")
    data_root = get_abs_path("data/dynamic")
    vector_store_workers = 16

    load_env()
    bbs_cfg = load_config()
    base_url = (bbs_cfg.get("BBS_Url") or "").strip().rstrip("/")
    if not base_url:
        print("未配置 BBS_Url，退出")
        return

    async def _async_main() -> None:
        browser = GlobalBrowser(headless=True)
        await browser.start()
        try:
            username, password = get_bbs_credentials()
            if username and password:
                await login(browser, username, password)
            else:
                print("未设置 BBS_Name/BBS_Password，跳过登录")

            result = await crawl_clean_and_vectorize(
                browser=browser,
                base_url=base_url,
                forum=forum,
                board=board,
                sub_board=sub_board,
                max_pages=max_pages,
                concurrency=concurrency,
                output_root=output_root,
                structure_path=structure_path,
                data_root=data_root,
                vector_store_workers=vector_store_workers,
            )
            print(
                "爬取保存 %d 个文件 | 清理 %d 个文件 | 向量库写入: %s"
                % (
                    len(result["saved_paths"]),
                    result["cleaned_count"],
                    "成功" if result["vector_store_ok"] else "失败",
                )
            )
        finally:
            await browser.close()

    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
