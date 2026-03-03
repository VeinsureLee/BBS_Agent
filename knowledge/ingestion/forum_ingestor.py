"""
讨论区（forum/section）异步爬取模块：从 BBS 获取讨论区列表。

功能说明：
    - 从「全部讨论区」下拉的 ul.x-child HTML 中解析讨论区列表；
    - 异步爬取讨论区列表：优先点击「全部讨论区」解析 ul.x-child，失败则按 section 下标
      依次打开 #!section/i 取名称。

主要接口入参/出参：
    - parse_section_list_from_html(html: str)
        入参：html — 包含 ul.x-child 的 HTML 或完整页面。
        出参：list[dict]，每项 {"id", "name", "href"}，url 需调用方用 base_url 拼接。
    - crawl_section_list(browser, base_url: str, section_count: int = SECTION_COUNT)
        入参：browser — GlobalBrowser 实例；base_url — BBS 根 URL；section_count — 讨论区个数。
        出参：list[dict]，每项 {"id", "name", "href", "url"}。
"""
import re
from bs4 import BeautifulSoup

# 讨论区数量（与 agent/tools/init_tools/board_tools 一致）
SECTION_COUNT = 10


def parse_section_list_from_html(html: str) -> list:
    """
    从「全部讨论区」下拉的 ul.x-child HTML 中解析讨论区列表。
    :param html: 包含 ul.x-child 的 HTML 或完整页面
    :return: [{"id": str, "name": str, "href": str, "url": str}, ...]，url 需调用方用 base_url 拼接
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for li in soup.select("ul.x-child > li"):
        a = li.select_one('span.text a[href^="/section/"]')
        if not a:
            continue
        href = (a.get("href") or "").strip()
        name = (a.get_text(strip=True) or "").strip()
        if not href:
            continue
        # href 如 /section/0, /section/9
        sec_id = href.rstrip("/").split("/")[-1].split("?")[0]
        items.append({
            "id": sec_id,
            "name": name or f"讨论区{sec_id}",
            "href": href,
        })
    return items


async def crawl_section_list(browser, base_url: str, section_count: int = SECTION_COUNT) -> list:
    """
    异步爬取讨论区列表：先尝试从首页点击「全部讨论区」解析 ul.x-child；
    若失败则按 section 下标 0..section_count-1 依次打开 #!section/i 取名称。
    :param browser: GlobalBrowser 实例
    :param base_url: BBS 根 URL（已 rstrip("/")）
    :param section_count: 讨论区个数
    :return: [{"id": str, "name": str, "href": str, "url": str}, ...]
    """
    base_url = (base_url or "").rstrip("/")
    page = await browser.new_page(base_url)
    try:
        # 使用 domcontentloaded 避免 networkidle 在 SPA/长连接场景下超时；再等待关键元素出现
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        await page.wait_for_selector('a:has-text("全部讨论区")', state="attached", timeout=10000)
        await page.wait_for_timeout(500)
        # 尝试点击「全部讨论区」展开下拉（内容由 AJAX 加载，需等待真实链接出现）
        try:
            link = page.locator('a:has-text("全部讨论区")').first
            await link.click(timeout=3000)
            # 等待 AJAX 加载完成：ul.x-child 内出现 section 链接（而非占位 {url:...}）
            await page.wait_for_selector(
                "ul.x-child li span.text a[href^='/section/']",
                state="attached",
                timeout=8000,
            )
            await page.wait_for_timeout(300)
            ul = page.locator("ul.x-child").first
            html = await ul.inner_html()
            full_html = f"<ul class=\"x-child\">{html}</ul>"
            parsed = parse_section_list_from_html(full_html)
            if parsed:
                for item in parsed:
                    item["url"] = f"{base_url}/#!section/{item['id']}"
                return parsed
        except Exception:
            pass
        # 回退：按下标打开每个 section 页取名称
        sections = []
        for i in range(section_count):
            url = f"{base_url}/#!section/{i}"
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(800)
            section_name = f"讨论区{i}"
            try:
                loc = page.locator(f'a[href="/section/{i}"]').first
                if await loc.count() > 0:
                    t = (await loc.inner_text() or "").strip()
                    if t and not t.startswith("http"):
                        section_name = t
            except Exception:
                pass
            sections.append({
                "id": str(i),
                "name": section_name,
                "href": f"/section/{i}",
                "url": url,
            })
        return sections
    finally:
        await page.close()
