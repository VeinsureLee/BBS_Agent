"""
版面初始化：在已有 forum_structure.json 的前提下，爬取各版面置顶帖并保存介绍 JSON。
参考 knowledge/ingestion/board_ingestor 与 __main__.py 的方法，不调用 __main__ 中任何函数。
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

from knowledge.ingestion.board_ingestor import (
    crawl_board_pinned,
    crawl_article_detail,
    build_intro_dict,
)
from knowledge.ingestion.utils_tools import sanitize_dir, collect_all_boards

STRUCTURE_PATH = "data/web_structure/forum_structure.json"
INIT_JSON_PATH = "config/init.json"
BOARD_PINNED_CONCURRENCY_KEY = "board_pinned_concurrency"
BOARD_ARTICLE_CONCURRENCY_KEY = "board_article_concurrency"
DEFAULT_PINNED_CONCURRENCY = 32
DEFAULT_ARTICLE_CONCURRENCY = 64


def _load_init_json() -> dict:
    """读取 config/init.json，缺失或解析失败返回默认 dict。"""
    path = get_abs_path(INIT_JSON_PATH)
    default = {
        "crawl_concurrency": 4,
        BOARD_PINNED_CONCURRENCY_KEY: DEFAULT_PINNED_CONCURRENCY,
        BOARD_ARTICLE_CONCURRENCY_KEY: DEFAULT_ARTICLE_CONCURRENCY,
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


def _board_pinned_concurrency() -> int:
    """从 config/init.json 读取版面置顶爬取并发数，默认 32。"""
    data = _load_init_json()
    try:
        return max(1, int(data.get(BOARD_PINNED_CONCURRENCY_KEY, DEFAULT_PINNED_CONCURRENCY)))
    except (TypeError, ValueError):
        return DEFAULT_PINNED_CONCURRENCY


def _board_article_concurrency() -> int:
    """从 config/init.json 读取帖子详情爬取并发数，默认 64。"""
    data = _load_init_json()
    try:
        return max(1, int(data.get(BOARD_ARTICLE_CONCURRENCY_KEY, DEFAULT_ARTICLE_CONCURRENCY)))
    except (TypeError, ValueError):
        return DEFAULT_ARTICLE_CONCURRENCY


def _load_forum_structure() -> list | None:
    """加载 forum_structure.json，返回 sections 列表；不存在或解析失败返回 None。"""
    path = get_abs_path(STRUCTURE_PATH)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("sections") if isinstance(data, dict) else None
    except (json.JSONDecodeError, IOError):
        return None


async def run_board_init() -> bool:
    """
    根据 data/web_structure/forum_structure.json 收集所有版面，
    爬取各版面置顶帖列表，对每个置顶打开详情并保存为 介绍[index].json。
    :return: True 表示成功，False 表示无结构文件或未配置 BBS_Url。
    """
    sections_out = _load_forum_structure()
    if not sections_out:
        logger.warning("未找到 forum_structure.json 或内容为空，跳过版面初始化")
        return False

    load_env()
    bbs_cfg = load_config()
    home_url = (bbs_cfg.get("BBS_Url") or "").strip().rstrip("/")
    if not home_url:
        logger.warning("未配置 BBS_Url，退出版面初始化")
        return False

    out_root = get_abs_path("data/web_structure")
    all_boards_flat = []
    for sec in sections_out:
        sec_name = sec.get("name") or ""
        for item in collect_all_boards(sec, sec_name, []):
            all_boards_flat.append(item)

    browser = GlobalBrowser(headless=True)
    await browser.start()
    try:
        username, password = get_bbs_credentials()
        if username and password:
            await login(browser, username, password)
        else:
            logger.info("未设置 BBS_Name/BBS_Password，跳过登录")

        base_url = home_url
        pinned_sem = asyncio.Semaphore(_board_pinned_concurrency())
        article_sem = asyncio.Semaphore(_board_article_concurrency())

        async def fetch_pinned(sec_name: str, path_parts: list, board: dict):
            async with pinned_sem:
                try:
                    pinned = await crawl_board_pinned(browser, base_url, board["id"])
                    return sec_name, path_parts, board, pinned
                except Exception as e:
                    browser.logger.warning("置顶爬取失败 %s/%s: %s", sec_name, board.get("name"), e)
                    return sec_name, path_parts, board, []

        logger.info(
            "开始爬取各版面置顶，共 %s 个版面（置顶并发: %s，帖子详情并发: %s，config/init.json）",
            len(all_boards_flat), _board_pinned_concurrency(), _board_article_concurrency(),
        )
        pinned_results = await asyncio.gather(
            *[fetch_pinned(sec_name, path_parts, board) for sec_name, path_parts, board in all_boards_flat],
            return_exceptions=True,
        )

        article_tasks = []
        for r in pinned_results:
            if isinstance(r, BaseException):
                logger.warning("置顶任务异常: %s", r)
                continue
            sec_name, path_parts, board, pinned = r
            parts = [sanitize_dir(p) for p in path_parts] + [sanitize_dir(board.get("name") or board["id"])]
            dir_path = os.path.join(out_root, *parts)
            os.makedirs(dir_path, exist_ok=True)
            path_display = " / ".join(parts) or sec_name
            logger.info("%s：%d 个置顶帖子爬取完毕", path_display, len(pinned))
            for index, pinned_item in enumerate(pinned):
                article_tasks.append((dir_path, index, pinned_item))

        async def fetch_and_save_article(dir_path: str, index: int, pinned_item: dict):
            async with article_sem:
                try:
                    floors = await crawl_article_detail(browser, base_url, pinned_item.get("url") or "")
                    intro = build_intro_dict(pinned_item, floors)
                    intro_path = os.path.join(dir_path, f"介绍{index}.json")
                    with open(intro_path, "w", encoding="utf-8") as f:
                        json.dump(intro, f, ensure_ascii=False, indent=2)
                    logger.info("已保存 %s", intro_path)
                except Exception as e:
                    logger.warning("帖子详情爬取失败 %s 介绍%d: %s", dir_path, index, e)

        if article_tasks:
            logger.info("开始并行爬取帖子详情，共 %s 篇", len(article_tasks))
            await asyncio.gather(
                *[fetch_and_save_article(d, i, p) for d, i, p in article_tasks],
                return_exceptions=True,
            )
        return True
    finally:
        await browser.close()
