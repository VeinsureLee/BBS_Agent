"""
knowledge.ingestion 命令行入口：BBS 讨论区与版面结构爬取及置顶帖介绍归档。

功能说明：
    - 创建全局浏览器实例并登录 BBS；
    - 爬取「全部讨论区」或各 section 页获取讨论区列表；
    - 对每个讨论区打开 #!section/id 页面，从主表格或侧栏解析版面与二级目录；
    - 递归收集所有版面，爬取各版面置顶帖列表；
    - 对每个置顶帖打开详情页，解析楼层内容并保存为 介绍[index].json；
    - 讨论区与版面结构保存到 data/web_structure/forum_structure.json。

入参：
    - 无命令行参数；依赖环境与配置：
      - .env：BBS_Name、BBS_Password（可选，用于登录）；
      - config/*.json：BBS_Url 等 BBS 配置。

出参：
    - 无返回值；副作用：
      - data/web_structure/forum_structure.json：讨论区与版面结构；
      - data/web_structure/<讨论区>/<版面>/介绍0.json、介绍1.json ...：各版面置顶帖介绍 JSON。
"""
import asyncio
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.config_handler import load_config
from utils.env_handler import load_env, get_bbs_credentials
from utils.path_tool import get_abs_path

from infrastructure.browser_manager.browser_manager import GlobalBrowser
from infrastructure.browser_manager.login import login

from knowledge.ingestion.forum_ingestor import crawl_section_list
from knowledge.ingestion.board_ingestor import (
    crawl_section_boards_tree,
    crawl_board_pinned,
    crawl_article_detail,
    build_intro_dict,
)
from knowledge.ingestion.utils_tools import sanitize_dir, collect_all_boards


async def async_main():
    load_env()
    bbs_cfg = load_config()
    home_url = (bbs_cfg.get("BBS_Url") or "").strip().rstrip("/")
    if not home_url:
        print("未配置 BBS_Url，退出")
        return

    browser = GlobalBrowser(headless=True)
    await browser.start()
    try:
        username, password = get_bbs_credentials()
        if username and password:
            await login(browser, username, password)
        else:
            print("未设置 BBS_Name/BBS_Password（可在项目根目录 .env 中配置），跳过登录")

        base_url = home_url
        browser.logger.info("开始爬取讨论区列表")
        sections_raw = await crawl_section_list(browser, base_url)
        browser.logger.info("讨论区列表爬取完成: %s 个", len(sections_raw))

        # 对每个 forum 打开 base_url/#!section/id 页面，从主表格 tbody tr 解析版面与二级目录；二级目录再打开其页面解析 sub boards
        sections_out = []
        for sec in sections_raw:
            try:
                tree = await crawl_section_boards_tree(browser, base_url, sec["id"])
                sections_out.append({
                    "id": sec["id"],
                    "name": sec["name"],
                    "url": sec["url"],
                    "boards": tree["boards"],
                    "sub_sections": tree["sub_sections"],
                })
                browser.logger.info("讨论区 %s: %s 个直接版面, %s 个二级目录",
                                    sec.get("name"), len(tree["boards"]), len(tree["sub_sections"]))
            except Exception as e:
                browser.logger.warning("讨论区 %s 版面爬取失败: %s", sec.get("name"), e)
                sections_out.append({
                    "id": sec["id"],
                    "name": sec["name"],
                    "url": sec["url"],
                    "boards": [],
                    "sub_sections": [],
                })

        # 保存讨论区与版面结构
        out_root = get_abs_path("data/web_structure")
        os.makedirs(out_root, exist_ok=True)
        structure_path = os.path.join(out_root, "forum_structure.json")
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump({"sections": sections_out}, f, ensure_ascii=False, indent=2)
        browser.logger.info("已保存讨论区与版面结构: %s", structure_path)

        # 收集所有版面并爬取置顶，再对每个置顶打开帖子详情保存为 介绍[index].json
        all_boards_flat = []
        for sec in sections_out:
            sec_name = sec.get("name") or ""
            for item in collect_all_boards(sec, sec_name, []):
                all_boards_flat.append(item)

        sem = asyncio.Semaphore(32)

        async def fetch_pinned(sec_name: str, path_parts: list, board: dict):
            async with sem:
                try:
                    pinned = await crawl_board_pinned(browser, base_url, board["id"])
                    return sec_name, path_parts, board, pinned
                except Exception as e:
                    browser.logger.warning("置顶爬取失败 %s/%s: %s", sec_name, board.get("name"), e)
                    return sec_name, path_parts, board, []

        browser.logger.info("开始爬取各版面置顶，共 %s 个版面", len(all_boards_flat))
        pinned_results = await asyncio.gather(
            *[fetch_pinned(sec_name, path_parts, board) for sec_name, path_parts, board in all_boards_flat],
            return_exceptions=True,
        )

        # 收集所有待抓取详情的置顶帖：(dir_path, index, pinned_item)
        article_tasks = []
        for r in pinned_results:
            if isinstance(r, BaseException):
                browser.logger.warning("置顶任务异常: %s", r)
                continue
            sec_name, path_parts, board, pinned = r
            parts = [sanitize_dir(p) for p in path_parts] + [sanitize_dir(board.get("name") or board["id"])]
            dir_path = os.path.join(out_root, *parts)
            os.makedirs(dir_path, exist_ok=True)

            path_display = " / ".join(parts) or sec_name
            browser.logger.info("%s：%d 个置顶帖子爬取完毕", path_display, len(pinned))

            for index, pinned_item in enumerate(pinned):
                article_tasks.append((dir_path, index, pinned_item))

        # 多个置顶帖并行打开并保存详情（Semaphore 限制同时打开的帖子数）
        article_sem = asyncio.Semaphore(64)

        async def fetch_and_save_article(dir_path: str, index: int, pinned_item: dict):
            async with article_sem:
                try:
                    floors = await crawl_article_detail(browser, base_url, pinned_item.get("url") or "")
                    intro = build_intro_dict(pinned_item, floors)
                    intro_path = os.path.join(dir_path, f"介绍{index}.json")
                    with open(intro_path, "w", encoding="utf-8") as f:
                        json.dump(intro, f, ensure_ascii=False, indent=2)
                    browser.logger.info("已保存 %s", intro_path)
                except Exception as e:
                    browser.logger.warning("帖子详情爬取失败 %s 介绍%d: %s", dir_path, index, e)

        if article_tasks:
            browser.logger.info("开始并行爬取帖子详情，共 %s 篇，并发数 5", len(article_tasks))
            await asyncio.gather(
                *[fetch_and_save_article(d, i, p) for d, i, p in article_tasks],
                return_exceptions=True,
            )
    finally:
        await browser.close()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
