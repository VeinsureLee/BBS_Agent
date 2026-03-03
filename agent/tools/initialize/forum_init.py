"""
论坛初始化：爬取讨论区列表与各讨论区版面树，保存为 data/web_structure/forum_structure.json。
参考 knowledge/ingestion 的流程，仅做结构爬取（不爬置顶与帖子详情）。
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.config_handler import load_config
from utils.env_handler import load_env, get_bbs_credentials
from utils.path_tool import get_abs_path
from utils.logger_handler import logger

from infrastructure.browser_manager.browser_manager import GlobalBrowser
from infrastructure.browser_manager.login import login

from knowledge.ingestion.forum_ingestor import crawl_section_list
from knowledge.ingestion.board_ingestor import crawl_section_boards_tree

INIT_JSON_PATH = "config/init.json"
CRAWL_CONCURRENCY_KEY = "crawl_concurrency"


def _load_init_json() -> dict:
    """读取 config/init.json，缺失或解析失败返回默认 dict。"""
    path = get_abs_path(INIT_JSON_PATH)
    default = {
        "usr_vector_store_status": False,
        "static_vector_store_status": False,
        "tag_init_status": False,
        CRAWL_CONCURRENCY_KEY: 4,
        "tag_max_workers": 8,
    }
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except (json.JSONDecodeError, IOError):
        return default


def _crawl_concurrency() -> int:
    """从 config/init.json 读取爬取并发数（crawl_concurrency），默认 4。"""
    data = _load_init_json()
    try:
        return max(1, int(data.get(CRAWL_CONCURRENCY_KEY, 4)))
    except (TypeError, ValueError):
        return 4


async def run_forum_init() -> bool:
    """
    爬取讨论区列表与各讨论区版面树，保存为 data/web_structure/forum_structure.json。
    :return: True 表示成功，False 表示未配置 BBS_Url 等异常。
    """
    load_env()
    bbs_cfg = load_config()
    home_url = (bbs_cfg.get("BBS_Url") or "").strip().rstrip("/")
    if not home_url:
        logger.warning("未配置 BBS_Url，退出论坛初始化")
        return False

    browser = GlobalBrowser(headless=True)
    await browser.start()
    try:
        username, password = get_bbs_credentials()
        if username and password:
            await login(browser, username, password)
        else:
            logger.info("未设置 BBS_Name/BBS_Password（可在项目根目录 .env 中配置），跳过登录")

        base_url = home_url
        browser.logger.info("开始爬取讨论区列表")
        sections_raw = await crawl_section_list(browser, base_url)
        browser.logger.info("讨论区列表爬取完成: %s 个", len(sections_raw))

        concurrency = _crawl_concurrency()
        browser.logger.info("爬取讨论区版面树，异步并发数: %s", concurrency)
        sem = asyncio.Semaphore(concurrency)

        async def crawl_one_section(sec: dict) -> dict:
            async with sem:
                try:
                    tree = await crawl_section_boards_tree(browser, base_url, sec["id"])
                    browser.logger.info(
                        "讨论区 %s: %s 个直接版面, %s 个二级目录",
                        sec.get("name"), len(tree["boards"]), len(tree["sub_sections"]),
                    )
                    return {
                        "id": sec["id"],
                        "name": sec["name"],
                        "url": sec["url"],
                        "boards": tree["boards"],
                        "sub_sections": tree["sub_sections"],
                    }
                except Exception as e:
                    browser.logger.warning("讨论区 %s 版面爬取失败: %s", sec.get("name"), e)
                    return {
                        "id": sec["id"],
                        "name": sec["name"],
                        "url": sec["url"],
                        "boards": [],
                        "sub_sections": [],
                    }

        results = await asyncio.gather(*[crawl_one_section(sec) for sec in sections_raw])
        sections_out = list(results)

        out_root = get_abs_path("data/web_structure")
        os.makedirs(out_root, exist_ok=True)
        structure_path = os.path.join(out_root, "forum_structure.json")
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump({"sections": sections_out}, f, ensure_ascii=False, indent=2)
        browser.logger.info("已保存讨论区与版面结构: %s", structure_path)
        return True
    finally:
        await browser.close()
