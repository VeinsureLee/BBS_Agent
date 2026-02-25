"""
初始化工具:将 BBS 登录页、版面、帖子第一页爬取并保存到 config/web_structure。
1. 初始化读取BBS登录页面信息：读取BBS登录页面信息，并将其存储到本地。
2. 初始化BBS版面信息：初始化BBS版面以及其子版面名称信息，并将其存储到本地。
3. 初始化BBS子版面信息：初始化BBS子版面名称信息，版面描述，并将其存储到本地。
4. 初始化BBS帖子信息：初始化BBS帖子信息，仅读取第一页帖子信息，并将其存储到本地。

保存路径由 config/web_structure/save.json 定义；初始化成功后更新 init.json。
全程复用同一 Playwright 浏览器实例，不重复启动。
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

# 工程根目录加入 path
_AGENT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROJECT_ROOT = os.path.dirname(_AGENT_ROOT)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from utils.config_handler import driver_conf, bbs_conf
from utils.path_tool import get_abs_path

load_dotenv()

# 讨论区数量
SECTION_COUNT = 10
BBS_BASE_DEFAULT = "https://bbs.byr.cn"

# ---------------------------------------------------------------------------
# 保存路径（来自 save.json）
# ---------------------------------------------------------------------------

def _load_save_config() -> dict:
    """加载 config/web_structure/save.json，得到各保存路径。"""
    path = get_abs_path("config/web_structure/save.json")
    if not os.path.exists(path):
        return {
            "login_config": "config/web_structure/config.json",
            "board": "config/web_structure/board/board.json",
            "posts_root": "config/web_structure/posts",
            "init_status_file": "config/web_structure/init.json",
        }
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "login_config": data.get("login_config", "config/web_structure/config.json"),
        "board": data.get("board", "config/web_structure/board/board.json"),
        "posts_root": data.get("posts_root", "config/web_structure/posts"),
        "init_status_file": data.get("init_status_file", "config/web_structure/init.json"),
    }


def _get_login_config_path() -> Path:
    return Path(get_abs_path(_load_save_config()["login_config"]))


def _get_board_path() -> Path:
    return Path(get_abs_path(_load_save_config()["board"]))


def _get_posts_root() -> str:
    return get_abs_path(_load_save_config()["posts_root"])


def _get_init_status_path() -> Path:
    return Path(get_abs_path(_load_save_config()["init_status_file"]))


def _set_init_status(success: bool) -> None:
    """初始化成功后更新 init.json。"""
    path = _get_init_status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"init_status": success}, f, ensure_ascii=False, indent=2)


def is_initialized() -> bool:
    """检查 config/web_structure/init.json 中 init_status 是否为 True。"""
    path = _get_init_status_path()
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("init_status") is True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 登录页爬取（仅检测元素 id，不登录）
# ---------------------------------------------------------------------------

def _get_or_fallback_id(element) -> str:
    if element is None:
        return ""
    return element.get_attribute("id") or ""


def _crawl_login_page_with_page(page, url: str) -> dict:
    """使用已有 page 打开登录页并检测账号、密码、登录按钮 id。"""
    if not url or not url.strip():
        raise ValueError("BBS_Url 未设置或为空")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)

    password_input = page.query_selector('input[type="password"]')
    username_input = None
    if password_input:
        form_handle = password_input.evaluate_handle("el => el.closest('form')")
        form = form_handle.as_element() if form_handle else None
        if form:
            inputs = form.query_selector_all('input[type="text"], input:not([type])')
            for inp in inputs:
                if inp != password_input and inp.is_visible():
                    username_input = inp
                    break
    if username_input is None:
        username_input = page.query_selector('input[type="text"]')
    if username_input is None:
        username_input = page.query_selector("#id")

    login_button = None
    if password_input:
        form_handle = password_input.evaluate_handle("el => el.closest('form')")
        form = form_handle.as_element() if form_handle else None
        if form:
            for sel in ['input[type="submit"]', 'button[type="submit"]', 'button', 'input[type="button"]']:
                buttons = form.query_selector_all(sel)
                for btn in buttons:
                    text = btn.inner_text() if btn else ""
                    value = btn.get_attribute("value") or ""
                    if "登录" in text or "login" in value.lower():
                        login_button = btn
                        break
                    if sel == 'input[type="submit"]' and buttons:
                        login_button = buttons[0]
                        break
                if login_button:
                    break
    if login_button is None:
        login_button = page.query_selector('input[type="submit"]')
    if login_button is None:
        login_button = page.query_selector("#b_login")

    return {
        "login_page_url": url.strip(),
        "username_input_id": _get_or_fallback_id(username_input),
        "password_input_id": _get_or_fallback_id(password_input),
        "login_button_id": _get_or_fallback_id(login_button),
    }


# ---------------------------------------------------------------------------
# 登录（在已有 page 上填表并点击）
# ---------------------------------------------------------------------------

def _do_login(page, login_url: str, username_id: str, password_id: str, login_btn_id: str) -> None:
    BBS_Name = os.environ.get("BBS_Name")
    BBS_Password = os.environ.get("BBS_Password")
    if not BBS_Name or not BBS_Password:
        raise ValueError("请在 .env 中设置 BBS_Name 和 BBS_Password")
    page.goto(login_url, wait_until="domcontentloaded")
    page.wait_for_selector(f"#{username_id}", state="visible", timeout=10000)
    page.locator(f"#{username_id}").fill("")
    page.locator(f"#{username_id}").fill(BBS_Name)
    page.locator(f"#{password_id}").fill("")
    page.locator(f"#{password_id}").fill(BBS_Password)
    page.locator(f"#{login_btn_id}").click()
    page.wait_for_url(lambda u: "login" not in u.lower(), timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)


# ---------------------------------------------------------------------------
# 讨论区与版面爬取（已登录的 page）
# ---------------------------------------------------------------------------

def _crawl_sections_and_boards_with_page(page, base_url: str) -> list:
    sections_out = []
    base_url = base_url.rstrip("/")
    for i in range(SECTION_COUNT):
        section_path = f"/section/{i}"
        url = urljoin(base_url + "/", section_path)
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)

        section_name = f"讨论区{i}"
        try:
            section_links = page.locator(f'a[href="/section/{i}"]').all()
            for a in section_links:
                t = (a.inner_text() or "").strip()
                if t and not t.startswith("http"):
                    section_name = t
                    break
        except Exception:
            pass

        section_url = f"{base_url}/#!section/{i}"
        boards = []
        try:
            rows = page.locator("tr").all()
            for tr in rows:
                try:
                    if tr.locator("td.title_1").count() == 0:
                        continue
                    link = tr.locator("td.title_1").first.locator("a[href]")
                    if link.count() == 0:
                        continue
                    href = (link.first.get_attribute("href") or "").strip()
                    if not href or "javascript:" in href:
                        continue
                    name = (link.first.inner_text() or "").strip()
                    if "\n" in name:
                        name = name.split("\n")[0].strip() or name
                    if not name:
                        name = href.split("/")[-1].split("?")[0] or ""

                    m_board = re.search(r"/board/([^/#?]+)", href)
                    m_section = re.search(r"/section/([^/#?]+)", href)
                    if m_board:
                        board_url = f"{base_url}/#!board/{m_board.group(1)}"
                    elif m_section:
                        board_url = f"{base_url}/#!section/{m_section.group(1)}"
                    else:
                        board_url = href
                    boards.append({"name": name, "url": board_url})
                except Exception:
                    continue
        except Exception:
            pass

        sections_out.append({"name": section_name, "url": section_url, "boards": boards})
    return sections_out


# ---------------------------------------------------------------------------
# 版面帖子第一页解析（HTML）
# ---------------------------------------------------------------------------

def _board_url_to_request_url(board_url: str, base: str = None) -> str:
    base = (base or BBS_BASE_DEFAULT).rstrip("/")
    if not board_url:
        return ""
    m = re.search(r"(?:#!)?/board/([^/#?\s]+)", board_url)
    if m:
        return f"{base}/board/{m.group(1)}"
    return board_url.replace("#!", "")


def _parse_board_html(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.board-list.tiz tbody tr")
    result = []
    for tr in rows:
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
    return result


def _filter_posts_today(posts: list) -> list:
    today = datetime.now().strftime("%Y-%m-%d")
    date_re = re.compile(r"^(\d{4}-\d{2}-\d{2})$")
    result = []
    for p in posts:
        t = (p.get("time") or "").strip()
        if not t:
            continue
        m = date_re.match(t)
        if m:
            if m.group(1) == today:
                result.append(p)
        else:
            result.append(p)
    return result


def _find_board_info_by_name(sections: list, board_name: str) -> tuple:
    """从 sections 中按版面名称查找 (board_url, section_name)。"""
    name = (board_name or "").strip()
    if not name:
        return None, None
    for section in sections:
        section_name = (section.get("name") or "").strip()
        for board in section.get("boards", []):
            if (board.get("name") or "").strip() == name:
                url = (board.get("url") or "").strip()
                if "#!board/" in url or "/board/" in url:
                    return url, section_name
    return None, None


def _crawl_board_posts_with_page(
    page, request_url: str, section_name: str, board_name: str, posts_root: str, base_url: str
) -> tuple:
    """用已登录的 page 访问版面列表页，解析第一页并保存到 posts_root。"""
    page.goto(request_url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    html = page.content()
    all_posts = _parse_board_html(html)
    posts = _filter_posts_today(all_posts)

    today_str = datetime.now().strftime("%Y-%m-%d")
    safe_section = re.sub(r'[<>:"/\\|?*]', "_", (section_name or "未分类").strip()) or "未分类"
    safe_board = re.sub(r'[<>:"/\\|?*]', "_", board_name.strip()) or "board"
    dir_path = Path(posts_root) / safe_section / safe_board
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


# ---------------------------------------------------------------------------
# 单次启动浏览器，顺序执行：登录页 -> 保存 -> 登录 -> 版面 -> 保存 -> 可选帖子
# ---------------------------------------------------------------------------

def run_full_init(
    boards_to_crawl_posts: list = None,
    headless: bool = True,
) -> dict:
    """
    启动一次 Playwright 浏览器，依次：爬取登录页并保存 -> 登录 -> 爬取讨论区与版面并保存 -> 可选爬取指定版面第一页帖子。
    全部保存到 config/web_structure（路径见 save.json），成功后更新 init.json 为 init_status: true。

    :param boards_to_crawl_posts: 可选，要爬取第一页帖子的版面名称列表（如 ["悄悄话"]）
    :param headless: 是否无头模式
    :return: 汇总结果，含 login_config_path, board_path, posts_paths, init_status_path 等
    """
    save_cfg = _load_save_config()
    BBS_Url = (bbs_conf.get("BBS_Url") or "").strip().rstrip("/")
    if not BBS_Url:
        raise ValueError("未配置 BBS_Url，请在 config/local/bbs.json 或 .env 中设置")

    login_config_path = Path(get_abs_path(save_cfg["login_config"]))
    board_path = Path(get_abs_path(save_cfg["board"]))
    posts_root = get_abs_path(save_cfg["posts_root"])
    init_path = Path(get_abs_path(save_cfg["init_status_file"]))

    Chrome_Path = driver_conf.get("Chrome_Path")
    launch_options = {"headless": headless}
    if Chrome_Path:
        launch_options["executable_path"] = Chrome_Path

    result_summary = {
        "login_config_path": str(login_config_path),
        "board_path": str(board_path),
        "posts_root": posts_root,
        "init_status_path": str(init_path),
        "posts_saved": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_options)
        try:
            page = browser.new_page()

            # 1. 登录页
            login_result = _crawl_login_page_with_page(page, BBS_Url)
            login_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(login_config_path, "w", encoding="utf-8") as f:
                json.dump(login_result, f, ensure_ascii=False, indent=2)

            # 2. 登录
            _do_login(
                page,
                login_result["login_page_url"],
                login_result["username_input_id"],
                login_result["password_input_id"],
                login_result["login_button_id"],
            )

            # 3. 讨论区与版面
            sections = _crawl_sections_and_boards_with_page(page, BBS_Url)
            board_path.parent.mkdir(parents=True, exist_ok=True)
            with open(board_path, "w", encoding="utf-8") as f:
                json.dump({"sections": sections}, f, ensure_ascii=False, indent=2)

            # 4. 可选：指定版面第一页帖子
            if boards_to_crawl_posts:
                for board_name in boards_to_crawl_posts:
                    board_name = (board_name or "").strip()
                    if not board_name:
                        continue
                    board_url, section_name = _find_board_info_by_name(sections, board_name)
                    if not board_url:
                        continue
                    request_url = _board_url_to_request_url(board_url, BBS_Url)
                    if not request_url:
                        continue
                    _, saved_path = _crawl_board_posts_with_page(
                        page, request_url, section_name, board_name, posts_root, BBS_Url
                    )
                    result_summary["posts_saved"].append(saved_path)

            _set_init_status(True)
        except Exception as e:
            _set_init_status(False)
            raise
        finally:
            browser.close()

    return result_summary


# ---------------------------------------------------------------------------
# Agent 可调用的 @tool
# ---------------------------------------------------------------------------

def _get_tool_run_full_init():
    from langchain_core.tools import tool

    @tool(
        description="执行 BBS 初始化：爬取登录页配置、讨论区与版面信息并保存到 config/web_structure，成功后更新 init.json。"
        " 可选传入要爬取第一页帖子的版面名称（逗号分隔），如「悄悄话,JobInfo」。全程只启动一次浏览器。"
    )
    def run_bbs_init(boards_to_crawl_posts: str = "") -> str:
        """
        执行完整 BBS 初始化（登录页 + 版面结构），可选同时爬取部分版面第一页帖子。
        boards_to_crawl_posts: 逗号分隔的版面名称，如 "悄悄话,JobInfo"，不传则只做登录页与版面。
        """
        board_list = [x.strip() for x in (boards_to_crawl_posts or "").split(",") if x.strip()]
        try:
            summary = run_full_init(boards_to_crawl_posts=board_list if board_list else None, headless=True)
            lines = [
                "BBS 初始化完成。",
                f"登录页配置: {summary['login_config_path']}",
                f"版面配置: {summary['board_path']}",
                f"帖子根目录: {summary['posts_root']}",
            ]
            if summary["posts_saved"]:
                lines.append("已爬取第一页帖子的版面: " + ", ".join(summary["posts_saved"]))
            lines.append("init.json 已更新为 init_status: true。")
            return "\n".join(lines)
        except Exception as e:
            return f"初始化失败: {e}"

    return run_bbs_init


# 供 react_agent 直接引用
run_bbs_init = _get_tool_run_full_init()
