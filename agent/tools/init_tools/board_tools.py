"""
版面相关工具：爬取讨论区与版面信息。
供 init_tools 在同一浏览器实例（已登录）中调用，不单独启动浏览器。
"""
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from utils.config_handler import load_bbs_config
from utils.timer import timer

# 讨论区数量
SECTION_COUNT = 10


def _get_bbs_base() -> str:
    """从 config/local/bbs.json 读取 BBS_Url。"""
    base = (load_bbs_config().get("BBS_Url") or "").strip().rstrip("/")
    if not base:
        raise ValueError("未配置 BBS_Url，请在 config/local/bbs.json 中设置")
    return base


def _board_url_to_request_url(board_url: str, base: str = None) -> str:
    base = (base or _get_bbs_base()).rstrip("/")
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


def find_board_info_by_name(sections: list, board_name: str) -> tuple:
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


def crawl_section_and_boards(
    page, base_url: str, section_index: int, debug: bool = False
) -> dict:
    """
    爬取单个讨论区及其版面列表。
    :param page: Playwright 的 Page 对象（已登录）
    :param base_url: BBS 根 URL
    :param section_index: 讨论区下标（0-based）
    :param debug: 为 True 时 print 一行
    :return: 单个 section 字典，含 name, url, boards
    """
    base_url = base_url.rstrip("/")
    i = section_index
    section_name = f"讨论区{i}"
    section_path = f"/section/{i}"
    url = urljoin(base_url + "/", section_path)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)

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

    if debug:
        names = [b.get("name") for b in boards[:5]]
        tail = " ..." if len(boards) > 5 else ""
        print("  ", i + 1, section_name, "->", len(boards), "个版面:", names, tail)
    return {"name": section_name, "url": section_url, "boards": boards}


def crawl_sections_and_boards(
    page, base_url: str, section_count: int = SECTION_COUNT, debug: bool = False
) -> list:
    """
    使用已登录的 page 按讨论区依次爬取，每个讨论区计时。
    :return: sections 列表，每项含 name, url, boards
    """
    sections_out = []
    base_url = base_url.rstrip("/")
    for i in range(section_count):
        with timer(f"讨论区{i}"):
            section = crawl_section_and_boards(page, base_url, i, debug=debug)
            sections_out.append(section)
    return sections_out


def crawl_board_posts(
    page,
    request_url: str,
    section_name: str,
    board_name: str,
    posts_root: str,
    debug: bool = False,
) -> tuple:
    """
    用已登录的 page 访问版面列表页，解析第一页并保存到 posts_root。
    :param debug: 为 True 时保存后 print 一行
    :return: (posts 列表, 保存的 json 文件路径)
    """
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
    if debug:
        print("  [DEBUG] 已爬取版面", board_name, "->", json_path)
    return posts, str(json_path)


def board_url_to_request_url(board_url: str, base: str = None) -> str:
    """将版面 hash URL 转为实际请求 URL。供 init_tools 等调用。"""
    return _board_url_to_request_url(board_url, base)
