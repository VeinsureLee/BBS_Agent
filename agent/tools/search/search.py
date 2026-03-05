# -*- coding: utf-8 -*-
"""
搜索工具 - 主流程：爬取版面 -> 数据清理 -> 向量化存储。
支持单版面与异步批量多版面爬取。在 main 中实例化浏览器并调用本流程进行测试，入参全部具体写出。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import asyncio

from typing import Any, TypedDict

from knowledge.ingestion.utils_tools import sanitize_dir
from knowledge.stores.dynamic_store import init_dynamic_store
from utils.path_tool import get_abs_path

from agent.tools.search.crawler import crawl_board_and_save
from agent.tools.search.clean import clean_post_files


class BoardSpec(TypedDict):
    """单个版面配置：讨论区、版面名、可选二级目录。"""
    forum: str
    board: str
    sub_board: str | None


async def crawl_boards_batch(
    browser: Any,
    base_url: str,
    board_specs: list[BoardSpec],
    max_pages: int = 2,
    concurrency: int = 32,
    output_root: str | None = None,
    structure_path: str | None = None,
) -> list[str]:
    """
    异步批量爬取多个版面，并发执行多个 crawl_board_and_save，合并返回所有已保存文件路径。
    :param browser: GlobalBrowser 实例
    :param base_url: BBS 根 URL
    :param board_specs: 版面配置列表，每项含 forum、board、可选 sub_board
    :param max_pages: 每个版面爬取页数
    :param concurrency: 每个版面内部并发数
    :param output_root: 爬取输出根目录
    :param structure_path: 论坛结构 JSON 路径
    :return: 所有版面已保存的文件路径列表（合并）
    """
    if not board_specs:
        return []
    tasks = [
        crawl_board_and_save(
            browser=browser,
            base_url=base_url,
            forum=spec["forum"],
            board=spec["board"],
            sub_board=spec.get("sub_board"),
            max_pages=max_pages,
            concurrency=concurrency,
            output_root=output_root,
            structure_path=structure_path,
        )
        for spec in board_specs
    ]
    results = await asyncio.gather(*tasks)
    saved_paths: list[str] = []
    for paths in results:
        saved_paths.extend(paths)
    return saved_paths


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


async def crawl_clean_and_vectorize_batch(
    browser: Any,
    base_url: str,
    board_specs: list[BoardSpec],
    max_pages: int = 2,
    concurrency: int = 32,
    output_root: str | None = None,
    structure_path: str | None = None,
    data_root: str | None = None,
    vector_store_workers: int = 4,
) -> dict:
    """
    异步批量：多版面爬取 -> 合并清理 -> 各版面目录分别向量化。
    :param browser: GlobalBrowser 实例
    :param base_url: BBS 根 URL
    :param board_specs: 版面配置列表
    :param max_pages: 每个版面爬取页数
    :param concurrency: 每个版面内部并发数
    :param output_root: 爬取输出根目录
    :param structure_path: 论坛结构 JSON 路径
    :param data_root: 清理与向量化数据根目录
    :param vector_store_workers: 各版面向量化加载线程数
    :return: {"saved_paths": list[str], "cleaned_count": int, "vector_store_results": list[dict]}
             vector_store_results 每项为 {"forum": str, "board": str, "ok": bool}
    """
    if output_root is None:
        output_root = get_abs_path("data/dynamic")
    if data_root is None:
        data_root = output_root

    saved_paths = await crawl_boards_batch(
        browser=browser,
        base_url=base_url,
        board_specs=board_specs,
        max_pages=max_pages,
        concurrency=concurrency,
        output_root=output_root,
        structure_path=structure_path,
    )
    cleaned_count = clean_post_files(saved_paths)

    vector_store_results: list[dict] = []
    for spec in board_specs:
        folder = os.path.join(
            data_root,
            sanitize_dir(spec["forum"]),
            sanitize_dir(spec["board"]),
        )
        ok = init_dynamic_store(
            folder_path=folder,
            max_workers=vector_store_workers,
        )
        vector_store_results.append({
            "forum": spec["forum"],
            "board": spec["board"],
            "ok": ok,
        })

    return {
        "saved_paths": saved_paths,
        "cleaned_count": cleaned_count,
        "vector_store_results": vector_store_results,
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


def run_crawl_clean_and_vectorize_batch(
    browser: Any,
    base_url: str,
    board_specs: list[BoardSpec],
    max_pages: int = 2,
    concurrency: int = 32,
    output_root: str | None = None,
    structure_path: str | None = None,
    data_root: str | None = None,
    vector_store_workers: int = 4,
) -> dict:
    """同步包装：执行 crawl_clean_and_vectorize_batch（异步批量多版面爬取+清理+向量化）。"""
    return asyncio.run(
        crawl_clean_and_vectorize_batch(
            browser=browser,
            base_url=base_url,
            board_specs=board_specs,
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
    max_pages = 2
    concurrency = 16
    output_root = get_abs_path("data/dynamic")
    structure_path = get_abs_path("data/web_structure/forum_structure.json")
    data_root = get_abs_path("data/dynamic")
    vector_store_workers = 16

    # 批量爬取：多版面异步并发；设为 False 则只爬取单个版面
    use_batch = True
    board_specs: list[BoardSpec] = [
        {"forum": "生活时尚", "board": "悄悄话", "sub_board": None},
        {"forum": "生活时尚", "board": "创意生活", "sub_board": None},
    ]

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

            if use_batch:
                result = await crawl_clean_and_vectorize_batch(
                    browser=browser,
                    base_url=base_url,
                    board_specs=board_specs,
                    max_pages=max_pages,
                    concurrency=concurrency,
                    output_root=output_root,
                    structure_path=structure_path,
                    data_root=data_root,
                    vector_store_workers=vector_store_workers,
                )
                print(
                    "批量爬取保存 %d 个文件 | 清理 %d 个文件"
                    % (len(result["saved_paths"]), result["cleaned_count"])
                )
                for r in result["vector_store_results"]:
                    print("  向量库 %s/%s: %s" % (r["forum"], r["board"], "成功" if r["ok"] else "失败"))
            else:
                forum, board, sub_board = (
                    board_specs[0]["forum"], board_specs[0]["board"], board_specs[0].get("sub_board")
                )
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
