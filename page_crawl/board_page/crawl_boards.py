"""
爬取北邮人论坛「全部讨论区」下的讨论区与版面：讨论区对应 section/0..9，跳转后页面为表格，
版面信息在 tr > td.title_1 > a[href*="/board/"] 中（版面名称、地址）。结果保存到 config/crawled/board.json。
使用 Playwright 实现。
"""
import json
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from pathlib import Path
from urllib.parse import urljoin

from utils.config_handler import driver_conf, bbs_conf, load_crawled_config
from utils.path_tool import get_abs_path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

Chrome_Path = driver_conf.get("Chrome_Path")
BBS_Url = (bbs_conf.get("BBS_Url") or "").strip().rstrip("/")
BBS_Name = os.environ.get("BBS_Name")
BBS_Password = os.environ.get("BBS_Password")

# 讨论区数量：section/0 .. section/9
SECTION_COUNT = 10


def create_browser(playwright):
    """创建并返回 Chromium 浏览器实例。"""
    launch_options = {}
    if Chrome_Path:
        launch_options["executable_path"] = Chrome_Path
    return playwright.chromium.launch(**launch_options)


def do_login(page, login_url, username_id, password_id, login_btn_id):
    """在给定 page 上执行登录。"""
    page.goto(login_url, wait_until="domcontentloaded")
    page.wait_for_selector(f"#{username_id}", state="visible", timeout=10000)
    page.locator(f"#{username_id}").fill("")
    page.locator(f"#{username_id}").fill(BBS_Name)
    page.locator(f"#{password_id}").fill("")
    page.locator(f"#{password_id}").fill(BBS_Password)
    page.locator(f"#{login_btn_id}").click()
    page.wait_for_url(lambda u: "login" not in u.lower(), timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)


def crawl_sections_and_boards(require_login: bool = True) -> list:
    """
    爬取全部讨论区及其版面，返回层级列表。
    每项格式: { "name": "讨论区名", "url": "https://bbs.byr.cn/#!section/0", "boards": [ { "name": "版面名", "url": "https://bbs.byr.cn/#!board/Advice" }, ... ] }
    """
    if not BBS_Url:
        raise ValueError("未配置 BBS_Url，请在 config/local/bbs.json 或 .env 中设置")

    config = load_crawled_config()
    login_url = (config.get("login_page_url") or BBS_Url).strip()
    username_id = (config.get("username_input_id") or "").strip()
    password_id = (config.get("password_input_id") or "").strip()
    login_btn_id = (config.get("login_button_id") or "").strip()

    if require_login and (not BBS_Name or not BBS_Password):
        raise ValueError("爬取版面需登录，请在 .env 中设置 BBS_Name 和 BBS_Password")
    if require_login and (not username_id or not password_id or not login_btn_id):
        raise ValueError("请先运行 login_page/crawl_login_page.py 获取登录页元素 id")

    sections_out = []

    with sync_playwright() as p:
        browser = create_browser(p)
        try:
            page = browser.new_page()
            if require_login:
                do_login(page, login_url, username_id, password_id, login_btn_id)

            for i in range(SECTION_COUNT):
                section_path = f"/section/{i}"
                url = urljoin(BBS_Url + "/", section_path)
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=10000)

                # 讨论区名称：页面上 a[href="/section/{i}"] 的链接文本
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

                section_url = f"{BBS_Url.rstrip('/')}/#!section/{i}"

                # 按 tr 遍历：每行 td.title_1 内第一个链接的名称与地址
                boards = []
                base_url = BBS_Url.rstrip("/")
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

                sections_out.append({
                    "name": section_name,
                    "url": section_url,
                    "boards": boards,
                })
                print(f"  讨论区 {i}: {section_name}, 行数: {len(boards)}")
        finally:
            browser.close()

    return sections_out


def get_board_json_path() -> Path:
    """board.json 路径：config/crawled/board.json"""
    return Path(get_abs_path("config/crawled/board.json"))


def save_boards_to_json(sections: list, path: Path = None, encoding: str = "utf-8") -> None:
    """将讨论区与版面层级写入 board.json，不写入 config.json。"""
    path = path or get_board_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=encoding) as f:
        json.dump({"sections": sections}, f, ensure_ascii=False, indent=2)
    print(f"版面配置已保存到: {path}")


def main():
    print("开始爬取讨论区与版面…")
    try:
        sections = crawl_sections_and_boards(require_login=True)
        save_boards_to_json(sections)
        total_boards = sum(len(s["boards"]) for s in sections)
        print(f"完成。共 {len(sections)} 个讨论区、{total_boards} 个版面，已写入 config/crawled/board.json")
    except Exception as e:
        print(f"错误: {e}")
        raise


if __name__ == "__main__":
    main()
