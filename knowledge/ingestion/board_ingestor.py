"""
版面（board）与二级目录异步爬取：从侧栏（点击 forum 后）解析版面/二级目录；从版面页解析置顶；从帖子页解析详情并保存为介绍[index].json。
"""
import re
from bs4 import BeautifulSoup

# 帖子详情页解析用（与 agent/tools/init_tools/inroductions 一致）
_RE_POST_TIME = re.compile(r"发信站:\s*[^(]+\(([^)]+)\)")
_RE_LIKE = re.compile(r"赞\((\d+)\)|楼主好评\s*\(\+?(\d+)\)")
_RE_CAI = re.compile(r"踩\((\d+)\)|楼主差评\s*\(\+?(\d+)\)")


def parse_section_table_tr(tr_html: str) -> dict | None:
    """
    解析单行 tr：版面（/board/XXX）或二级目录（/section/XXX + [二级目录]）。
    支持传入 tr 的 inner_html（仅 td 片段，无 tr 标签）或完整 tr 的 outer_html。
    :return: None 表示跳过；否则 {"type": "board"|"sub_section", "name": str, "id": str, "url": str, "is_secondary": bool}
    """
    soup = BeautifulSoup(tr_html, "html.parser")
    tr = soup.find("tr")
    if tr:
        td1 = tr.select_one("td.title_1")
    else:
        # 浏览器返回的是 inner_html，只有 td 没有 tr
        td1 = soup.find("td", class_=lambda c: c and "title_1" in (c if isinstance(c, str) else " ".join(c)))
    if not td1:
        return None
    a = td1.find("a", href=True)
    if not a:
        return None
    href = (a.get("href") or "").strip()
    if not href or "javascript:" in href:
        return None
    name = (a.get_text(strip=True) or "").strip()
    if "\n" in name:
        name = name.split("\n")[0].strip() or name
    if not name:
        name = href.rstrip("/").split("/")[-1].split("?")[0] or ""

    # 判断是否为二级目录：td.title_2 含 [二级目录]
    root = tr if tr else soup
    td2 = root.select_one("td.title_2")
    is_secondary = False
    if td2 and "[二级目录]" in (td2.get_text() or ""):
        is_secondary = True

    m_board = re.search(r"/board/([^/#?\s]+)", href)
    m_section = re.search(r"/section/([^/#?\s]+)", href)
    if m_board:
        bid = m_board.group(1)
        return {
            "type": "board",
            "name": name,
            "id": bid,
            "href": href,
            "is_secondary": False,
        }
    if m_section:
        sid = m_section.group(1)
        return {
            "type": "sub_section",
            "name": name,
            "id": sid,
            "href": href,
            "is_secondary": is_secondary,
        }
    return None


def parse_section_table(tr_items: list) -> tuple[list, list]:
    """
    从 tr 列表解析出版面列表与二级目录列表。
    :param tr_items: [{"text": str, "html": str}, ...] 每个为 tr 的 text/html
    :return: (boards, sub_sections)，均为 [{"type", "name", "id", "href", ...}, ...]
    """
    boards = []
    sub_sections = []
    for item in tr_items:
        row = parse_section_table_tr(item.get("html") or "")
        if not row:
            continue
        if row["type"] == "board":
            boards.append(row)
        else:
            sub_sections.append(row)
    return boards, sub_sections


def parse_sidebar_ul(ul_html: str) -> tuple[list, list]:
    """
    解析「点击 forum 后」侧栏中的 ul：li.leaf 为版面，li.folder-close 为二级目录。
    :return: (boards, sub_sections)，boards/sub_sections 每项含 id, name, href；调用方补 url。
    """
    soup = BeautifulSoup(ul_html, "html.parser")
    boards = []
    sub_sections = []
    for li in soup.find_all("li", class_=lambda c: c and ("leaf" in c or "folder-close" in c)):
        a = li.select_one("span.text a[href], span.active a[href]") or li.find("a", href=True)
        if not a:
            continue
        href = (a.get("href") or "").strip()
        if not href or "javascript:" in href:
            continue
        name = (a.get("title") or a.get_text(strip=True) or "").strip()
        if not name:
            name = href.rstrip("/").split("/")[-1].split("?")[0] or ""
        m_board = re.search(r"/board/([^/#?\s]+)", href)
        m_section = re.search(r"/section/([^/#?\s]+)", href)
        if m_board:
            boards.append({"id": m_board.group(1), "name": name, "href": href})
        elif m_section:
            sub_sections.append({"id": m_section.group(1), "name": name, "href": href, "boards": []})
    return boards, sub_sections


async def crawl_section_boards_via_sidebar(page, base_url: str, section_index: int, section_name: str) -> dict:
    """
    在同一页面上：点击指定讨论区以展开侧栏，解析版面与二级目录；对每个二级目录依次点击展开，解析其下版面。
    不同二级目录需依次点开，不能同时显示。
    :param page: Playwright Page 对象（已打开 BBS 且已登录）
    :param base_url: BBS 根 URL
    :param section_index: 讨论区下标 0-based
    :param section_name: 讨论区名称（仅用于日志）
    :return: {"boards": [...], "sub_sections": [{"id","name","url","boards": [...]}]}，每项含 url
    """
    base_url = (base_url or "").rstrip("/")
    # 点击该讨论区链接，使侧栏显示该区下的 ul（含 li.leaf 版面 / li.folder-close 二级目录）
    section_loc = page.locator(f'a[href="/section/{section_index}"]').first
    await section_loc.click(timeout=5000)
    await page.wait_for_timeout(400)
    # 等待当前讨论区展开（folder-open），其下出现版面或二级目录
    await page.wait_for_selector(
        f"li.folder-open a[href='/section/{section_index}']",
        timeout=6000,
    )
    await page.wait_for_timeout(200)
    # 只取「当前讨论区」节点下的直接子 ul（避免取到「全部讨论区」的顶级 ul，把 forum 当 board）
    ul_html = await page.evaluate(
        """(sectionIndex) => {
        const sectionLink = document.querySelector(
            `li.folder-open a[href="/section/${sectionIndex}"]`
        );
        if (!sectionLink) return '';
        const li = sectionLink.closest('li');
        const ul = li ? li.querySelector(':scope > ul') : null;
        return ul ? ul.outerHTML : '';
    }""",
        section_index,
    )
    boards, sub_sections = parse_sidebar_ul(ul_html)
    for b in boards:
        b["url"] = f"{base_url}/#!board/{b['id']}"
    for s in sub_sections:
        s["url"] = f"{base_url}/#!section/{s['id']}"

    # 依次点击每个二级目录，解析其下版面（同一时间只能展开一个）
    for sub in sub_sections:
        sub_id = sub["id"]
        folder_loc = page.locator(f'li.folder-close a[href="/section/{sub_id}"], li.folder-close-last a[href="/section/{sub_id}"]').first
        if await folder_loc.count() == 0:
            continue
        await folder_loc.click(timeout=3000)
        await page.wait_for_timeout(500)
        # 展开后变为 li.folder-open，其下 ul 内有 li.leaf
        try:
            nested_ul = page.locator(f'li.folder-open:has(a[href="/section/{sub_id}"])').locator("ul").first
            if await nested_ul.count() > 0:
                nested_ul_html = await nested_ul.inner_html()
                sub_boards, _ = parse_sidebar_ul(nested_ul_html)
                for b in sub_boards:
                    b["url"] = f"{base_url}/#!board/{b['id']}"
                sub["boards"] = sub_boards
        except Exception:
            pass

    return {"boards": boards, "sub_sections": sub_sections}


def parse_pinned_from_tr(tr_html: str) -> dict | None:
    """
    从置顶行 tr.top 解析：标题、链接、日期、作者。
    兼容多列布局：td.title_9 为标题链接，title_10 为日期，title_12 为作者；或按列序 tds[1] 标题等。
    """
    soup = BeautifulSoup(tr_html, "html.parser")
    tr = soup.find("tr", class_=lambda c: c and "top" in c)
    if not tr:
        return None
    tds = tr.find_all("td")
    if len(tds) < 4:
        return None
    title_a = tr.select_one("td.title_9 a[href^='/article/']")
    if not title_a:
        title_a = tr.select_one("a[href^='/article/']")
    if not title_a:
        return None
    href = (title_a.get("href") or "").strip()
    if "?" in href:
        href = href.split("?")[0]
    title = (title_a.get_text(strip=True) or "").strip()
    date_cell = tr.select_one("td.title_10")
    if not date_cell:
        date_cell = tds[2] if len(tds) > 2 else None
    post_time = (date_cell.get_text(strip=True) or "").strip() if date_cell else ""
    author_cell = tr.select_one("td.title_12 a")
    if not author_cell:
        for td in tds:
            a = td.find("a", href=re.compile(r"/user/query/"))
            if a:
                author_cell = a
                break
    author = (author_cell.get_text(strip=True) or "").strip() if author_cell else ""
    return {"title": title, "url": href, "time": post_time, "author": author}


async def crawl_section_boards(browser, base_url: str, section_id_or_slug: str) -> tuple[list, list]:
    """
    异步爬取某讨论区页的版面列表与二级目录列表（从页面主表格 tbody tr 解析）。
    :param browser: GlobalBrowser 实例
    :param base_url: BBS 根 URL
    :param section_id_or_slug: 讨论区 id（如 "0","9"）或二级目录 slug（如 "BBSLOG"）
    :return: (boards, sub_sections)，每个 board/sub_section 含 type, name, id, href；调用方拼 url
    """
    base_url = (base_url or "").rstrip("/")
    url = f"{base_url}/#!section/{section_id_or_slug}"
    # 版面列表在 forum 页的主表格 tbody 中，每行 tr 为版面或二级目录（td.title_1 为第一列）
    rows = await browser.crawl_selector(
        url,
        selector="table tbody tr:has(td.title_1)",
        wait_until_selector="table tbody tr td.title_1",
        wait_until="domcontentloaded",
        timeout=15000,
    )
    boards, sub_sections = parse_section_table(rows)
    # 为每项补全 url
    for b in boards:
        b["url"] = f"{base_url}/#!board/{b['id']}"
    for s in sub_sections:
        s["url"] = f"{base_url}/#!section/{s['id']}"
    return boards, sub_sections


async def crawl_section_boards_tree(browser, base_url: str, section_id_or_slug: str) -> dict:
    """
    异步爬取某讨论区及其二级目录的完整版面树。
    从 section 页表格解析 boards 与 sub_sections；对每个 sub_section 再打开其页面解析其下 boards。
    :return: {"boards": [...], "sub_sections": [{"id","name","href","url","boards": [...], "sub_sections": []}]}
    """
    boards, sub_sections = await crawl_section_boards(browser, base_url, section_id_or_slug)
    for sub in sub_sections:
        sub["boards"] = []
        sub["sub_sections"] = []
        try:
            sub_boards, sub_sub_sections = await crawl_section_boards(browser, base_url, sub["id"])
            sub["boards"] = sub_boards
            # 二级目录下一般不再嵌套，若有可在此递归
            for s2 in sub_sub_sections:
                s2["url"] = f"{(base_url or '').rstrip('/')}/#!section/{s2['id']}"
                s2["boards"] = []
                sub["sub_sections"].append(s2)
        except Exception:
            pass
    return {"boards": boards, "sub_sections": sub_sections}


async def crawl_board_pinned(browser, base_url: str, board_id: str) -> list:
    """
    异步爬取某版面的置顶帖子列表（仅结构信息：标题、链接、日期、作者）。
    :param browser: GlobalBrowser 实例
    :param base_url: BBS 根 URL
    :param board_id: 版面 id（如 BBShelp, Advice）
    :return: [{"title", "url", "time", "author"}, ...]
    """
    base_url = (base_url or "").rstrip("/")
    url = f"{base_url}/#!board/{board_id}"
    rows = await browser.crawl_selector(
        url,
        selector="tr.top",
        wait_until_selector="table",
        wait_until="load",
        timeout=10000,
    )
    result = []
    for item in rows:
        parsed = parse_pinned_from_tr(item.get("html") or "")
        if parsed:
            result.append(parsed)
    return result


def parse_article_detail_html(html: str) -> list:
    """
    从帖子详情页 HTML（div.b-content .a-wrap）解析每一层楼。
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


async def crawl_article_detail(browser, base_url: str, article_url: str) -> list:
    """
    异步打开帖子详情页，解析每层楼并返回（与 介绍[index].json 中 floors 格式一致）。
    :param article_url: 相对路径如 /article/BM_Market/2034
    :return: floors 列表
    """
    base_url = (base_url or "").rstrip("/")
    url = article_url if article_url.startswith("http") else (base_url + article_url)
    html = await browser.crawl_page_content(url, wait_until="domcontentloaded")
    return parse_article_detail_html(html)


def build_intro_dict(pinned_item: dict, floors: list) -> dict:
    """根据置顶项与楼层列表组装为 data/web_structure 下的 介绍 格式。"""
    reply_count = max(0, len(floors) - 1) if floors else 0
    first = floors[0] if floors else {}
    return {
        "title": pinned_item.get("title") or "",
        "time": pinned_item.get("time") or first.get("time") or "",
        "author": pinned_item.get("author") or first.get("author") or "",
        "reply_count": reply_count,
        "url": pinned_item.get("url") or "",
        "floors": floors,
    }
