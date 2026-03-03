"""
按讨论区/版面增量更新：爬取指定版面的帖子（含分页）并保存为 日期/帖子名称.json。

功能说明：
    - 从 data/web_structure/forum_structure.json 加载讨论区与版面结构；
    - 按讨论区名称与版面名称查找版面信息；
    - 爬取指定版面的多页帖子列表，拉取每帖详情并保存到 output_root/讨论区/版面/日期/帖子名称.json；
    - 发帖时间解析支持 YYYY-MM-DD、BBS 格式（如 Thu Oct 6 14:23:37 2022）等，用于目录名。

主要接口入参/出参：
    - load_forum_structure(structure_path: str | None) -> dict
        入参：structure_path — 结构 JSON 路径，None 时使用 data/web_structure/forum_structure.json。
        出参：含 "sections" 的 dict。
    - get_board_by_section_and_name(structure, section_name, board_name) -> dict | None
        入参：structure — 讨论区结构；section_name、board_name — 讨论区名与版面名。
        出参：版面 dict（id, name, url 等）或 None。
    - update_board_posts(browser, base_url, section_name, board, output_root, max_pages=2, concurrency=32) -> list[str]
        入参：browser — GlobalBrowser；base_url — BBS 根 URL；section_name — 讨论区名；board — 版面信息 dict；
              output_root — 输出根目录；max_pages — 爬取页数；concurrency — 并发数。
        出参：已保存的文件路径列表。
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.path_tool import get_abs_path
from knowledge.ingestion.utils_tools import sanitize_dir
from knowledge.ingestion.board_ingestor import (
    crawl_board_posts,
    crawl_article_detail,
    build_intro_dict,
)


def load_forum_structure(structure_path: str | None = None) -> dict:
    """加载讨论区与版面结构。默认使用 data/web_structure/forum_structure.json。"""
    if structure_path is None:
        structure_path = get_abs_path("data/web_structure/forum_structure.json")
    with open(structure_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_board_by_section_and_name(structure: dict, section_name: str, board_name: str) -> dict | None:
    """
    按讨论区名称与版面名称查找版面信息。
    :return: 版面 dict（含 id, name, url 等），未找到返回 None。
    """
    return get_board_by_section_subsection_and_name(
        structure, section_name, board_name, sub_section_name=None
    )


def get_board_by_section_subsection_and_name(
    structure: dict,
    section_name: str,
    board_name: str,
    sub_section_name: str | None = None,
) -> dict | None:
    """
    按讨论区、可选二级目录与版面名称查找版面信息。
    :param structure: 讨论区结构（含 sections）
    :param section_name: 讨论区名称（forum）
    :param board_name: 版面名称（board）
    :param sub_section_name: 二级目录名称（可选）；若指定则仅在该二级目录下查找版面
    :return: 版面 dict（含 id, name, url 等），未找到返回 None。
    """
    sections = structure.get("sections") or []
    section_name = (section_name or "").strip()
    board_name = (board_name or "").strip()
    sub_section_name = (sub_section_name or "").strip() or None

    for sec in sections:
        if (sec.get("name") or "").strip() != section_name:
            continue
        if sub_section_name:
            for sub in sec.get("sub_sections") or []:
                if (sub.get("name") or "").strip() != sub_section_name:
                    continue
                for b in sub.get("boards") or []:
                    if (b.get("name") or "").strip() == board_name:
                        return b
                return None
        else:
            for b in sec.get("boards") or []:
                if (b.get("name") or "").strip() == board_name:
                    return b
            for sub in sec.get("sub_sections") or []:
                for b in sub.get("boards") or []:
                    if (b.get("name") or "").strip() == board_name:
                        return b
    return None


# BBS 常见发帖时间格式（如 "Thu Oct  6 14:23:37 2022"）的 strptime 格式
_BBS_TIME_FMT = "%a %b %d %H:%M:%S %Y"

# 英文月份名到数字的映射，用于正则解析
_MONTH_NAMES = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def _date_folder_from_time(time_str: str) -> str:
    """
    从帖子发帖时间字符串解析出用于目录名的日期，格式 YYYY-MM-DD。
    仅使用发帖时间，无法解析时不使用爬取时间，返回「未知日期」。
    """
    if not (time_str and (time_str := time_str.strip())):
        return "未知日期"
    # 1. 匹配 YYYY-MM-DD 或 YYYY/MM/DD
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", time_str)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        return f"{y}-{mo}-{d}"
    # 2. BBS 格式：Thu Oct  6 14:23:37 2022
    try:
        dt = datetime.strptime(time_str, _BBS_TIME_FMT)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
    # 3. 正则兜底：Month DD ... YYYY
    m2 = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}).*?(\d{4})",
        time_str,
        re.IGNORECASE,
    )
    if m2:
        mo = _MONTH_NAMES.get(m2.group(1)[:3].capitalize())
        if mo:
            d = m2.group(2).zfill(2)
            y = m2.group(3)
            return f"{y}-{mo}-{d}"
    return "未知日期"


async def update_board_posts(
    browser,
    base_url: str,
    section_name: str,
    board: dict,
    output_root: str,
    max_pages: int = 2,
    concurrency: int = 32,
) -> list[str]:
    """
    爬取指定版面的多页帖子（异步），拉取每帖详情并保存到 output_root/讨论区/版面/日期/帖子名称.json。
    :param browser: GlobalBrowser 实例
    :param base_url: BBS 根 URL
    :param section_name: 讨论区名称（用于目录路径）
    :param board: 版面信息 dict，至少含 id, name
    :param output_root: 输出根目录（如 data/dynamic）
    :param max_pages: 爬取前几页（1=仅首页）
    :param concurrency: 并发数（同时打开的帖子数）
    :return: 已保存的文件路径列表
    """
    base_url = (base_url or "").rstrip("/")
    board_id = board.get("id") or ""
    board_display_name = board.get("name") or board_id
    board_dir = os.path.join(output_root, sanitize_dir(section_name), sanitize_dir(board_display_name))

    # 异步爬取多页帖子列表
    async def fetch_page(p: int):
        return await crawl_board_posts(browser, base_url, board_id, page=p)

    page_results = await asyncio.gather(
        *[fetch_page(p) for p in range(1, max_pages + 1)],
        return_exceptions=True,
    )

    posts = []
    for i, r in enumerate(page_results):
        if isinstance(r, BaseException):
            browser.logger.warning("版面 %s 第 %d 页爬取失败: %s", board_display_name, i + 1, r)
            continue
        posts.extend(r)

    # 按 url 去重（同一帖可能出现在多页）
    seen_urls = set()
    unique_posts = []
    for p in posts:
        u = (p.get("url") or "").strip()
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique_posts.append(p)

    sem = asyncio.Semaphore(concurrency)
    saved_paths = []

    async def fetch_and_save(post_item: dict):
        async with sem:
            try:
                floors = await crawl_article_detail(browser, base_url, post_item.get("url") or "")
                intro = build_intro_dict(post_item, floors)
                date_folder = _date_folder_from_time(intro.get("time") or "")
                dir_path = os.path.join(board_dir, date_folder)
                os.makedirs(dir_path, exist_ok=True)
                safe_title = sanitize_dir((post_item.get("title") or "未命名").strip()) or "未命名"
                # 若文件名过长则截断，避免路径过长
                if len(safe_title) > 120:
                    safe_title = safe_title[:120]
                fname = f"{safe_title}.json"
                out_path = os.path.join(dir_path, fname)
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(intro, f, ensure_ascii=False, indent=2)
                browser.logger.info("已保存 %s", out_path)
                return out_path
            except Exception as e:
                browser.logger.warning("帖子详情爬取失败 %s: %s", post_item.get("title"), e)
                return None

    results = await asyncio.gather(
        *[fetch_and_save(p) for p in unique_posts],
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, str):
            saved_paths.append(r)
        elif isinstance(r, BaseException):
            browser.logger.warning("任务异常: %s", r)
    return saved_paths


async def async_main():
    """调试入口：爬取「悄悄话」版面首页与第二页所有帖子，保存到 data/dynamic/生活时尚/悄悄话/日期/帖子名称.json。"""
    from utils.config_handler import load_config
    from utils.env_handler import load_env, get_bbs_credentials
    from infrastructure.browser_manager.browser_manager import GlobalBrowser
    from infrastructure.browser_manager.login import login

    load_env()
    bbs_cfg = load_config()
    home_url = (bbs_cfg.get("BBS_Url") or "").strip().rstrip("/")
    if not home_url:
        print("未配置 BBS_Url，退出")
        return

    structure = load_forum_structure()
    section_name = "北邮校园"
    board_name = "北邮图书馆"
    board = get_board_by_section_and_name(structure, section_name, board_name)
    if not board:
        print("未找到版面：%s / %s" % (section_name, board_name))
        return

    browser = GlobalBrowser(headless=True)
    await browser.start()
    try:
        username, password = get_bbs_credentials()
        if username and password:
            await login(browser, username, password)
        else:
            print("未设置 BBS_Name/BBS_Password，跳过登录")

        output_root = get_abs_path("data/dynamic")
        paths = await update_board_posts(
            browser,
            home_url,
            section_name,
            board,
            output_root,
            max_pages=4,
            concurrency=16,
        )
        print("共保存 %d 个帖子到 %s" % (len(paths), output_root))
    finally:
        await browser.close()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
