"""
根据 config/crawled/board.json 中的版面信息，请求对应版面页面并解析帖子列表，
只保留当日发帖，保存到 data/讨论区名称/版面名称/年月日.json（时间仅含年月日）。

北邮人论坛需登录后才能看到版面帖子列表，默认使用 Playwright 登录后获取页面。
debug 模式（环境变量 DEBUG=1 或参数 debug=True）时打开浏览器窗口，否则无头不弹窗。
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# 将工程根目录加入 path，便于引用 utils 和 config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.path_tool import get_abs_path

# 请求头，模拟浏览器（用于 use_selenium=False 时）
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 版面配置与 base URL
BOARD_JSON_PATH = get_abs_path("config/crawled/board.json")
BBS_BASE = "https://bbs.byr.cn"


def _load_board_config() -> dict:
    """加载 config/crawled/board.json。"""
    with open(BOARD_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_board_info_by_name(board_name: str) -> tuple[str | None, str | None]:
    """
    根据版面名称（name）在 board.json 中查找对应版面的 URL 及其所属讨论区名称。
    只匹配 url 中含有 #!board/ 的版面（即真实版面，而非 section）。
    返回 (board_url, section_name)，未找到返回 (None, None)。
    """
    config = _load_board_config()
    name = (board_name or "").strip()
    if not name:
        return None, None

    for section in config.get("sections", []):
        section_name = (section.get("name") or "").strip()
        for board in section.get("boards", []):
            if (board.get("name") or "").strip() == name:
                url = (board.get("url") or "").strip()
                if "#!board/" in url or "/board/" in url:
                    return url, section_name
    return None, None


def _board_url_to_request_url(board_url: str) -> str:
    """
    将 board.json 中的版面 URL 转为实际可请求的列表页 URL。
    例如: https://bbs.byr.cn/#!board/IWhisper -> https://bbs.byr.cn/board/IWhisper
    """
    if not board_url:
        return ""
    # 提取 #!board/XXX 或 /board/XXX
    m = re.search(r"(?:#!)?/board/([^/#?\s]+)", board_url)
    if m:
        return f"{BBS_BASE.rstrip('/')}/board/{m.group(1)}"
    return board_url.replace("#!", "").replace("#!", "")


def _is_debug_mode() -> bool:
    """是否为 debug 模式：环境变量 DEBUG 为 1/true/yes 时视为 debug。"""
    v = (os.environ.get("DEBUG") or "").strip().lower()
    return v in ("1", "true", "yes")


def _fetch_board_html_playwright(
    request_url: str,
    wait_seconds: float = 2.0,
    debug: bool | None = None,
) -> str | None:
    """
    使用 Playwright 登录北邮人论坛后访问版面 URL，返回页面 HTML。
    debug 为 True 时打开浏览器窗口，否则无头模式不弹出窗口；未传时根据环境变量 DEBUG 判断。
    成功返回 HTML 字符串，失败返回 None。
    """
    try:
        from dotenv import load_dotenv
        from playwright.sync_api import sync_playwright

        from utils.config_handler import driver_conf, bbs_conf, load_crawled_config

        load_dotenv()
        BBS_Url = (bbs_conf.get("BBS_Url") or "").strip().rstrip("/")
        BBS_Name = os.environ.get("BBS_Name")
        BBS_Password = os.environ.get("BBS_Password")
        if not BBS_Url or not BBS_Name or not BBS_Password:
            return None

        config = load_crawled_config()
        login_url = (config.get("login_page_url") or BBS_Url).strip()
        username_id = (config.get("username_input_id") or "").strip()
        password_id = (config.get("password_input_id") or "").strip()
        login_btn_id = (config.get("login_button_id") or "").strip()
        if not username_id or not password_id or not login_btn_id:
            return None

        Chrome_Path = driver_conf.get("Chrome_Path")
        launch_options = {}
        if Chrome_Path:
            launch_options["executable_path"] = Chrome_Path
        headless = not (debug if debug is not None else _is_debug_mode())
        launch_options["headless"] = headless

        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_options)
            try:
                page = browser.new_page()
                page.goto(login_url, wait_until="domcontentloaded")
                page.wait_for_selector(f"#{username_id}", state="visible", timeout=10000)
                page.locator(f"#{username_id}").fill("")
                page.locator(f"#{username_id}").fill(BBS_Name)
                page.locator(f"#{password_id}").fill("")
                page.locator(f"#{password_id}").fill(BBS_Password)
                page.locator(f"#{login_btn_id}").click()
                page.wait_for_url(lambda u: "login" not in u.lower(), timeout=15000)
                time.sleep(max(0, wait_seconds - 1))
                page.goto(request_url, wait_until="domcontentloaded")
                time.sleep(wait_seconds)
                return page.content()
            finally:
                browser.close()
    except Exception:
        return None


def _parse_board_html(html: str, page_encoding: str = "utf-8") -> list[dict]:
    """
    解析版面文章列表页 HTML（与 test.html 结构一致）。
    从 table.board-list tbody tr 中提取：
    - 帖子名称（主题链接文字）
    - 发帖时间
    - 作者
    - 回复数量
    - 跳转地址（如 /article/IWhisper/8726362）
    返回字典列表，每个元素包含: title, time, author, reply_count, url。
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.board-list.tiz tbody tr")
    result = []

    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        # 结构: [状态, 主题, 发帖时间, 作者, 回复, 最新回复时间, 最新回复作者]
        # 索引:  0      1       2        3     4        5              6
        title_td = tds[1]   # title_9
        time_td = tds[2]    # 发帖时间
        author_td = tds[3]
        reply_td = tds[4]

        # 主题链接: 第一个 href 以 /article/ 开头的 a
        article_a = title_td.find("a", href=re.compile(r"^/article/[^/]+/\d+$"))
        if not article_a:
            # 可能带分页等，取第一个 /article/ 链接并规范化
            article_a = title_td.find("a", href=re.compile(r"^/article/"))
        if not article_a:
            continue

        href = (article_a.get("href") or "").strip()
        # 去掉 ?p=2 等查询参数，只保留路径
        if "?" in href:
            href = href.split("?")[0]
        title = (article_a.get_text(strip=True) or "").strip()

        post_time = (time_td.get_text(strip=True) or "").strip()
        author = ""
        author_a = author_td.find("a")
        if author_a:
            author = (author_a.get_text(strip=True) or "").strip()
        reply_count_str = (reply_td.get_text(strip=True) or "0").strip()
        try:
            reply_count = int(reply_count_str)
        except ValueError:
            reply_count = 0

        result.append({
            "title": title,
            "time": post_time,
            "author": author,
            "reply_count": reply_count,
            "url": href,
        })

    return result


def _filter_posts_today(posts: list[dict]) -> list[dict]:
    """
    只保留发帖日期为当日的帖子。
    页面中发帖时间格式：仅时间如 "15:07:58" 表示当日；完整日期如 "2026-02-04" 需判断是否等于今天。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    result = []
    date_re = re.compile(r"^(\d{4}-\d{2}-\d{2})$")
    for p in posts:
        t = (p.get("time") or "").strip()
        if not t:
            continue
        m = date_re.match(t)
        if m:
            if m.group(1) == today:
                result.append(p)
        else:
            # 仅时间（如 15:07:58），页面惯例表示当日
            result.append(p)
    return result


def crawl_board_posts(
    board_name: str,
    *,
    use_selenium: bool = True,
    debug: bool | None = None,
    headers: dict | None = None,
    timeout: int = 15,
    save_dir: str | None = None,
) -> tuple[list[dict], str | None]:
    """
    根据版面名称（name）从 board.json 解析出对应 URL，请求该版面文章列表页，
    只保留当日发帖，保存到 data/讨论区名称/版面名称/年月日.json。

    debug 为 True 或环境变量 DEBUG=1 时 Playwright 会打开浏览器窗口，否则无头不弹窗。

    :param board_name: 版面名称，与 board.json 中 boards[].name 一致（如 "悄悄话"）
    :param use_selenium: 是否用 Playwright 登录后获取页面（默认 True）
    :param debug: 是否 debug 模式（打开浏览器）；None 时根据环境变量 DEBUG 判断
    :param headers: 可选请求头，use_selenium=False 时生效
    :param timeout: 请求超时秒数，use_selenium=False 时生效
    :param save_dir: 可选，覆盖保存根目录，默认使用工程下 data
    :return: (当日帖子列表, 保存的 JSON 文件路径)；未找到版面或请求失败时列表为空，路径为 None
    """
    board_url, section_name = _find_board_info_by_name(board_name)
    if not board_url:
        return [], None

    request_url = _board_url_to_request_url(board_url)
    if not request_url:
        return [], None

    html = None
    if use_selenium:
        html = _fetch_board_html_playwright(request_url, debug=debug)
    else:
        req_headers = {**DEFAULT_HEADERS, **(headers or {})}
        try:
            resp = requests.get(request_url, headers=req_headers, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            html = resp.text
        except Exception:
            pass

    if not html:
        return [], None

    all_posts = _parse_board_html(html)
    posts = _filter_posts_today(all_posts)

    # 保存路径: data/讨论区名称/版面名称/年月日.json
    root = save_dir if save_dir is not None else get_abs_path("data")
    today_str = datetime.now().strftime("%Y-%m-%d")
    safe_section = re.sub(r'[<>:"/\\|?*]', "_", (section_name or "未分类").strip()) or "未分类"
    safe_board = re.sub(r'[<>:"/\\|?*]', "_", board_name.strip()) or "board"
    dir_path = Path(root) / safe_section / safe_board
    dir_path.mkdir(parents=True, exist_ok=True)
    json_path = dir_path / f"{today_str}.json"

    out = {
        "section_name": section_name or "",
        "board_name": board_name,
        "date": today_str,
        "crawl_time": datetime.now().isoformat(),
        "request_url": request_url,
        "posts": posts,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return posts, str(json_path)


if __name__ == "__main__":
    print("test")
    start_time = time.time()
    # 示例：爬取「悄悄话」版面；设置 DEBUG=1 或 debug=True 可弹出浏览器
    name = "悄悄话"
    posts, path = crawl_board_posts(name)  # debug=True 可打开浏览器
    print(f"版面: {name}, 当日帖子数: {len(posts)}, 保存: {path}")
    if posts:
        print("首条:", json.dumps(posts[0], ensure_ascii=False))
    print(f"time: {time.time() - start_time}")