"""
BBS Web search 工具：基于提供的URL，爬取BBS网站上的信息，并将其存储到本地。

- crawl_board_pages：在浏览器中打开版面列表页，爬取帖子列表（支持翻页），保存到 data/bbs_sections。
- open_post_detail_and_save：打开帖子详情页，解析内容并保存到 data/post_details。
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bs4 import BeautifulSoup
from langchain_core.tools import tool

from utils.path_tool import get_abs_path
from utils.config_handler import load_web_structure_board_config, load_web_structure_login_config, bbs_conf
from utils.logger_handler import logger
from agent.tools.init_tools.browser_tools import get_page, start_browser, close_browser
from agent.tools.init_tools.login_tools import do_login
from agent.tools.init_tools.board_tools import (
    find_board_info_by_name,
    board_url_to_request_url,
)
from agent.tools.init_tools.inroductions import crawl_article_detail


def _get_bbs_sections_root() -> str:
    """返回 data/bbs_sections 的绝对路径。"""
    return get_abs_path("data/bbs_sections")


def _get_post_details_root() -> str:
    """返回 data/post_details 的绝对路径。"""
    return get_abs_path("data/post_details")


def _get_bbs_base() -> str:
    base = (bbs_conf.get("BBS_Url") or "").strip().rstrip("/")
    if not base:
        raise ValueError("未配置 BBS_Url，请在 config/local/bbs.json 中设置")
    return base


def _ensure_browser_and_login():
    """若浏览器未启动则启动并登录；返回 page，失败则返回 None。"""
    page = get_page()
    if page is not None:
        return page
    try:
        start_browser(debug=False)
        page = get_page()
        if page is None:
            return None
        login_cfg = load_web_structure_login_config()
        if not login_cfg.get("login_page_url"):
            logger.warning("[search_tools] 未找到登录配置，请先执行 BBS 初始化（run_bbs_init）。")
            return None
        BBS_Url = _get_bbs_base()
        do_login(
            page,
            login_cfg["login_page_url"],
            login_cfg.get("username_input_id", "id"),
            login_cfg.get("password_input_id", "pwd"),
            login_cfg.get("login_button_id", "b_login"),
            debug=False,
        )
        return page
    except Exception as e:
        logger.exception("[search_tools] 启动浏览器或登录失败: %s", e)
        return None


def _get_next_board_page_url(page, current_url: str, base_url: str) -> str:
    """
    从当前版面列表页解析「下一页」链接。
    常见：a 文本为「下一页」或 href 带 page 参数。
    """
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    base_url = base_url.rstrip("/")
    # 1) 文本为「下一页」的链接
    for a in soup.find_all("a", href=True):
        text = (a.get_text(strip=True) or "").strip()
        if "下一页" in text or "下页" in text or "next" in text.lower():
            href = (a.get("href") or "").strip()
            if href and "javascript:" not in href:
                return href if href.startswith("http") else urljoin(base_url + "/", href)
    # 2) 分页区带 page 参数的链接（当前页+1）
    parsed = urlparse(current_url)
    qs = parse_qs(parsed.query)
    page_num = 1
    if "page" in qs:
        try:
            page_num = int(qs["page"][0]) + 1
        except (ValueError, IndexError):
            page_num = 2
    else:
        page_num = 2
    path = parsed.path or "/"
    prefix = current_url.split("?")[0]
    new_url = f"{prefix}?page={page_num}" if "?" not in current_url else f"{prefix}&page={page_num}"
    return new_url


def _crawl_one_board_page(page, request_url: str, base_url: str) -> tuple:
    """
    爬取当前版面列表页的帖子列表（不含置顶 tr.top）。
    返回 (posts 列表, 下一页 URL 或空字符串)。
    """
    page.goto(request_url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    html = page.content()
    # 与 board_tools 一致：table.board-list.tiz tbody tr，但排除 tr.top 置顶
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.board-list.tiz tbody tr")
    result = []
    for tr in rows:
        if "top" in (tr.get("class") or []):
            continue
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        title_td, time_td, author_td, reply_td = tds[1], tds[2], tds[3], tds[4]
        article_a = title_td.find("a", href=re.compile(r"^/article/[^/]+/\d+$"))
        if not article_a:
            article_a = title_td.find("a", href=re.compile(r"^/article/"))
        if not article_a:
            continue
        href = (article_a.get("href") or "").strip()
        if "?" in href:
            href = href.split("?")[0]
        title = (article_a.get_text(strip=True) or "").strip()
        post_time = (time_td.get_text(strip=True) or "").strip()
        author = ""
        author_a = author_td.find("a")
        if author_a:
            author = (author_a.get_text(strip=True) or "").strip()
        try:
            reply_count = int((reply_td.get_text(strip=True) or "0").strip())
        except ValueError:
            reply_count = 0
        result.append({"title": title, "time": post_time, "author": author, "reply_count": reply_count, "url": href})
    next_url = _get_next_board_page_url(page, request_url, base_url)
    return result, next_url


# ---------------------------------------------------------------------------
# 1. 爬取版面列表（含翻页）
# ---------------------------------------------------------------------------


@tool(
    description="在浏览器中打开指定版面的列表页，爬取帖子列表（支持翻页），并保存到 data/bbs_sections。"
    " 需先执行过 BBS 初始化（run_bbs_init）。若未打开浏览器则自动启动并登录后再爬取。"
    " 参数：board_name 版面名称（与版面结构一致）；max_pages 最多爬取几页（默认 1，传 0 表示不限制页数，建议不超过 10）。"
)
def crawl_board_pages(board_name: str, max_pages: int = 1) -> str:
    """
    爬取指定版面的帖子列表，支持多页，结果保存到 data/bbs_sections/讨论区/版面/日期.json。
    """
    board_name = (board_name or "").strip()
    if not board_name:
        return "请提供版面名称（board_name）。"

    try:
        board_cfg = load_web_structure_board_config()
    except Exception as e:
        logger.warning("[search_tools] 读取版面结构失败: %s", e)
        return "当前无法读取版面结构，请先执行 BBS 初始化（run_bbs_init）。"

    sections = board_cfg.get("sections") or []
    board_url, section_name = find_board_info_by_name(sections, board_name)
    if not board_url or not section_name:
        return f"未找到版面「{board_name}」，请先执行 BBS 初始化或确认版面名称正确。"

    page = _ensure_browser_and_login()
    if page is None:
        return "无法启动浏览器或登录失败，请先执行 run_bbs_init 完成初始化后再试。"

    base_url = _get_bbs_base()
    request_url = board_url_to_request_url(board_url, base_url)
    if not request_url:
        return "无法解析版面请求 URL。"

    max_pages = max(0, int(max_pages)) if max_pages is not None else 1
    if max_pages == 0:
        max_pages = 99

    all_posts = []
    seen_urls = set()
    current_url = request_url
    pages_done = 0

    while pages_done < max_pages:
        try:
            posts, next_url = _crawl_one_board_page(page, current_url, base_url)
        except Exception as e:
            logger.exception("[search_tools] 爬取版面页失败: %s", e)
            break
        for p in posts:
            u = (p.get("url") or "").strip()
            if u and u not in seen_urls:
                seen_urls.add(u)
                all_posts.append(p)
        pages_done += 1
        if not posts:
            break
        if not next_url or next_url == current_url:
            break
        current_url = next_url

    if not all_posts:
        return f"版面「{board_name}」当前页未解析到帖子，或该版面暂无帖子。"

    today_str = datetime.now().strftime("%Y-%m-%d")
    safe_section = re.sub(r'[<>:"/\\|?*]', "_", (section_name or "未分类").strip()) or "未分类"
    safe_board = re.sub(r'[<>:"/\\|?*]', "_", board_name.strip()) or "board"
    root = _get_bbs_sections_root()
    dir_path = Path(root) / safe_section / safe_board
    dir_path.mkdir(parents=True, exist_ok=True)
    json_path = dir_path / f"{today_str}.json"
    out = {
        "section_name": section_name,
        "board_name": board_name,
        "date": today_str,
        "crawl_time": datetime.now().isoformat(),
        "request_url": request_url,
        "pages_crawled": pages_done,
        "posts": all_posts,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return f"已爬取版面「{board_name}」共 {pages_done} 页、{len(all_posts)} 条帖子，已保存到：{json_path}"


# ---------------------------------------------------------------------------
# 2. 打开帖子详情并保存到 data
# ---------------------------------------------------------------------------


def _article_url_to_slug(article_url: str) -> str:
    """从 /article/Clothing/154 或 完整 URL 得到 slug 如 Clothing_154。"""
    if not article_url:
        return "unknown"
    path = urlparse(article_url).path or article_url
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "article":
        return "_".join(parts[1:])
    return re.sub(r"[^\w\-]", "_", path) or "unknown"


@tool(
    description="在浏览器中打开帖子详情页，解析帖子内容（各楼层作者、时间、正文、赞踩等）并保存到 data/post_details。"
    " 参数：post_url 帖子的链接，可为相对路径如 /article/Clothing/154 或完整 URL。"
    " 若未打开浏览器则会自动启动并登录后再打开详情。"
)
def open_post_detail_and_save(post_url: str) -> str:
    """
    打开帖子详情，解析楼层内容，保存到 data/post_details/<slug>.json。
    """
    post_url = (post_url or "").strip()
    if not post_url:
        return "请提供帖子链接（post_url）。"

    page = _ensure_browser_and_login()
    if page is None:
        return "无法启动浏览器或登录失败，请先执行 run_bbs_init 完成初始化后再试。"

    base_url = _get_bbs_base()
    try:
        floors = crawl_article_detail(page, post_url, base_url, debug=False)
    except Exception as e:
        logger.exception("[search_tools] 爬取帖子详情失败: %s", e)
        return f"打开帖子详情失败：{e}"

    if not floors:
        return "该帖子未解析到楼层内容，或页面结构不符。"

    slug = _article_url_to_slug(post_url)
    full_url = post_url if post_url.startswith("http") else (base_url.rstrip("/") + post_url)
    out = {
        "url": full_url,
        "post_url": post_url,
        "crawl_time": datetime.now().isoformat(),
        "floor_count": len(floors),
        "floors": floors,
    }
    root = _get_post_details_root()
    Path(root).mkdir(parents=True, exist_ok=True)
    json_path = Path(root) / f"{slug}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return f"已打开帖子详情并保存 {len(floors)} 层楼到：{json_path}"
