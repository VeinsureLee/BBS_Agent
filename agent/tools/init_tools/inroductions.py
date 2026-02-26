"""
inroductions tools：爬取版面首页面的置顶内容并保存；可点开帖子爬取详情（时间、人物、内容、赞踩等）。
供 init_tools 在同一浏览器实例（已登录）中调用，不单独启动浏览器。
"""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from agent.tools.init_tools.board_tools import _board_url_to_request_url, _get_bbs_base
from utils.config_handler import get_web_structure_introductions_root
from utils.timer import timer

# 帖子详情页：发信站时间格式
_RE_POST_TIME = re.compile(r"发信站:\s*[^(]+\(([^)]+)\)")
# 赞/踩、楼主好评/差评 数字
_RE_LIKE = re.compile(r"赞\((\d+)\)|楼主好评\s*\(\+?(\d+)\)")
_RE_CAI = re.compile(r"踩\((\d+)\)|楼主差评\s*\(\+?(\d+)\)")


def _sanitize_dir_name(name: str) -> str:
    """用于文件系统目录名的安全名称（去除非法字符）。"""
    if not name or not str(name).strip():
        return "未命名"
    s = re.sub(r'[<>:"/\\|?*]', "_", str(name).strip())
    return s or "未命名"


def _get_introductions_root() -> Path:
    """从 save.json 读取 introductions 根目录（其下为 讨论区名称/版面名称/介绍[index].json）。"""
    return get_web_structure_introductions_root()


def _parse_sticky_posts_from_board_html(html: str) -> list:
    """
    从版面列表页 HTML 中解析置顶内容。置顶行由 <tr class="top"> 标记。
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.board-list.tiz tbody tr.top")
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


def _parse_article_detail_html(html: str) -> list:
    """
    从帖子详情页 HTML（div.b-content .a-wrap）解析每一层楼：时间、人物、帖子内容、点赞、踩等。
    返回列表，每项为一层楼：floor_name, author, author_id, nickname, time, content, like_count, dislike_count, level, article_count, score, constellation。
    """
    soup = BeautifulSoup(html, "html.parser")
    wraps = soup.select("div.a-wrap.corner")
    result = []
    for wrap in wraps:
        table = wrap.find("table", class_="article")
        if not table:
            continue
        tbody = table.find("tbody")
        if not tbody:
            continue
        rows = {tr.get("class", [None])[0]: tr for tr in tbody.find_all("tr") if tr.get("class")}
        head = rows.get("a-head")
        body = rows.get("a-body")
        bottom = rows.get("a-bottom")
        # 作者与楼层
        floor_name = ""
        author = ""
        author_id = ""
        if head:
            name_a = head.select_one(".a-u-name a")
            if name_a:
                author = (name_a.get_text(strip=True) or "").strip()
                href = (name_a.get("href") or "").strip()
                if "/user/query/" in href:
                    author_id = href.split("/user/query/")[-1].split("?")[0].strip() or author
                else:
                    author_id = author
            pos_span = head.select_one(".a-pos")
            if pos_span:
                floor_name = (pos_span.get_text(strip=True) or "").strip()
        # 赞/踩：head 或 bottom 的 .a-func-support/.a-func-like 与 .a-func-oppose/.a-func-cai
        like_count = 0
        dislike_count = 0
        for container in [head, bottom]:
            if not container:
                continue
            for a in container.select("a.a-func-support, a.a-func-like"):
                t = (a.get_text(strip=True) or "")
                m = _RE_LIKE.search(t)
                if m:
                    like_count = int((m.group(1) or m.group(2) or "0"))
                    break
            else:
                continue
            break
        for container in [head, bottom]:
            if not container:
                continue
            for a in container.select("a.a-func-oppose, a.a-func-cai"):
                t = (a.get_text(strip=True) or "")
                m = _RE_CAI.search(t)
                if m:
                    dislike_count = int((m.group(1) or m.group(2) or "0"))
                    break
            else:
                continue
            break
        # 昵称、等级/文章/积分/星座、正文
        nickname = ""
        level = ""
        article_count = ""
        score = ""
        constellation = ""
        content = ""
        post_time = ""
        if body:
            uid_div = body.select_one(".a-u-uid")
            if uid_div:
                nickname = (uid_div.get_text(strip=True) or "").strip()
            info = body.select_one("dl.a-u-info")
            if info:
                dts = info.find_all("dt")
                dds = info.find_all("dd")
                for dt, dd in zip(dts, dds):
                    key = (dt.get_text(strip=True) or "").strip()
                    val = (dd.get_text(strip=True) or "").strip()
                    if key == "等级":
                        level = val
                    elif key == "文章":
                        article_count = val
                    elif key == "积分":
                        score = val
                    elif key == "星座":
                        constellation = val
            wrap_div = body.select_one(".a-content-wrap")
            if wrap_div:
                content = (wrap_div.get_text(separator="\n", strip=True) or "").strip()
                mt = _RE_POST_TIME.search(wrap_div.get_text() or "")
                if mt:
                    post_time = (mt.group(1) or "").strip()
        result.append({
            "floor_name": floor_name,
            "author": author,
            "author_id": author_id,
            "nickname": nickname,
            "time": post_time,
            "content": content,
            "like_count": like_count,
            "dislike_count": dislike_count,
            "level": level,
            "article_count": article_count,
            "score": score,
            "constellation": constellation,
        })
    return result


def crawl_article_detail(page, article_url: str, base_url: str, debug: bool = False) -> list:
    """
    使用已登录的 page 打开帖子详情页，解析每层楼的时间、人物、内容、赞踩等并返回。
    :param page: Playwright 的 Page 对象（已登录）
    :param article_url: 帖子 URL（可为相对路径如 /article/Clothing/154）
    :param base_url: BBS 根 URL
    :param debug: 为 True 时打印一行
    :return: 每层楼的列表，见 _parse_article_detail_html
    """
    base_url = base_url.rstrip("/")
    url = article_url if article_url.startswith("http") else (base_url + article_url)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    html = page.content()
    floors = _parse_article_detail_html(html)
    if debug:
        print("    [DEBUG] 帖子详情", article_url, "->", len(floors), "层")
    return floors


def crawl_board_introductions(
    page,
    request_url: str,
    section_name: str,
    board_name: str,
    debug: bool = False,
) -> list:
    """
    使用已登录的 page 访问版面列表页，解析置顶内容并返回。
    :param page: Playwright 的 Page 对象（已登录）
    :param request_url: 版面列表页请求 URL
    :param section_name: 讨论区名称
    :param board_name: 版面名称
    :param debug: 为 True 时打印一行
    :return: 置顶帖子列表 [{ title, time, author, reply_count, url }, ...]
    """
    page.goto(request_url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    html = page.content()
    posts = _parse_sticky_posts_from_board_html(html)
    if debug:
        print("  [DEBUG] 置顶爬取", section_name, "/", board_name, "->", len(posts), "条")
    return posts


def crawl_one_section_introductions(
    page,
    section: dict,
    base_url: str,
    debug: bool = False,
    fetch_article_detail: bool = True,
) -> dict:
    """
    爬取单个讨论区下所有版面的置顶内容（含可选帖子详情），每个版面计时。
    :param page: Playwright 的 Page 对象（已登录）
    :param section: 单个 section 字典，含 name, url, boards（无 introductions）
    :param base_url: BBS 根 URL
    :param debug: 为 True 时每版打印一行
    :param fetch_article_detail: 为 True 时对每个置顶帖打开详情页并解析楼层
    :return: 同一 section，boards 中每项多出 introductions 字段
    """
    base_url = base_url.rstrip("/")
    sec_copy = {"name": section.get("name", ""), "url": section.get("url", ""), "boards": []}
    for board in section.get("boards", []):
        board_copy = {"name": board.get("name", ""), "url": board.get("url", "")}
        request_url = _board_url_to_request_url(board_copy["url"], base_url)
        if not request_url:
            board_copy["introductions"] = []
            sec_copy["boards"].append(board_copy)
            continue
        with timer(f"版面 {board_copy['name']}"):
            introductions = crawl_board_introductions(
                page,
                request_url,
                sec_copy["name"],
                board_copy["name"],
                debug=debug,
            )
            if fetch_article_detail and introductions:
                for item in introductions:
                    url = (item.get("url") or "").strip()
                    if url:
                        try:
                            item["floors"] = crawl_article_detail(
                                page, url, base_url, debug=debug
                            )
                        except Exception:
                            item["floors"] = []
                    else:
                        item["floors"] = []
            board_copy["introductions"] = introductions
            sec_copy["boards"].append(board_copy)
    return sec_copy


def crawl_all_introductions(
    page,
    sections: list,
    base_url: str = None,
    debug: bool = False,
    fetch_article_detail: bool = True,
) -> list:
    """
    遍历 sections 中每个讨论区、每个版面爬取置顶内容（含计时）；若 fetch_article_detail 为 True，则点开每个帖子爬取详情。
    introduction tools 负责：置顶信息爬取并保存，讨论区级与版面级计时。
    :param page: Playwright 的 Page 对象（已登录）
    :param sections: 由 crawl_sections_and_boards 返回的讨论区列表
    :param base_url: BBS 根 URL，不传则从 config 读取
    :param debug: 为 True 时每版打印一行
    :param fetch_article_detail: 为 True 时对每个置顶帖打开详情页并解析楼层信息
    :return: 与 sections 结构相同，每个 board 多出 introductions 字段；若 fetch_article_detail，每条含 floors 列表
    """
    base_url = (base_url or _get_bbs_base()).rstrip("/")
    out = []
    for sec in sections:
        with timer(f"置顶-讨论区 {sec.get('name', '')}"):
            sec_with_intros = crawl_one_section_introductions(
                page, sec, base_url, debug=debug, fetch_article_detail=fetch_article_detail
            )
            out.append(sec_with_intros)
    return out


def save_introductions(
    sections_with_intros: list,
    root: Path = None,
    only_last_section: bool = False,
) -> Path:
    """
    将带 introductions 的 sections 按 根目录/讨论区名称/版面名称/介绍[index].json 保存。
    :param sections_with_intros: 含 introductions 的 sections 列表
    :param root: 介绍根目录，不传则使用 save.json 的 introductions_root
    :param only_last_section: 为 True 时只写入列表中最后一个讨论区（用于每区保存时只写新区）
    :return: 介绍根目录路径
    """
    root = (root or _get_introductions_root()).resolve()
    to_save = sections_with_intros[-1:] if (only_last_section and sections_with_intros) else sections_with_intros
    for sec in to_save:
        section_name = _sanitize_dir_name(sec.get("name", ""))
        for board in sec.get("boards", []):
            board_name = _sanitize_dir_name(board.get("name", ""))
            dir_path = root / section_name / board_name
            dir_path.mkdir(parents=True, exist_ok=True)
            for i, intro in enumerate(board.get("introductions", [])):
                json_path = dir_path / f"介绍{i}.json"
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(intro, f, ensure_ascii=False, indent=2)
    return root
