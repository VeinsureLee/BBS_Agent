"""
爬取北邮人论坛「全部讨论区」下的讨论区与版面：讨论区对应 section/0..9，跳转后页面为表格，
版面信息在 tr > td.title_1 > a[href*="/board/"] 中（版面名称、地址）。结果保存到 config/crawled/board.json。
"""
import json
import os
import re
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from urllib.parse import urljoin

from utils.config_handler import driver_conf, bbs_conf, load_crawled_config
from utils.path_tool import get_abs_path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

load_dotenv()

Chrome_Path = driver_conf.get("Chrome_Path")
Chrome_Driver_Path = driver_conf.get("Chrome_Driver_Path")
BBS_Url = (bbs_conf.get("BBS_Url") or "").strip().rstrip("/")
BBS_Name = os.environ.get("BBS_Name")
BBS_Password = os.environ.get("BBS_Password")

# 讨论区数量：section/0 .. section/9
SECTION_COUNT = 10


def create_driver():
    """创建并返回 Chrome WebDriver。"""
    options = Options()
    if Chrome_Path:
        options.binary_location = Chrome_Path
    service = Service(Chrome_Driver_Path) if Chrome_Driver_Path else None
    return webdriver.Chrome(service=service, options=options)


def do_login(driver, login_url, username_id, password_id, login_btn_id):
    """在给定 driver 上执行登录。"""
    driver.get(login_url)
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.ID, username_id)))
    driver.find_element(By.ID, username_id).clear()
    driver.find_element(By.ID, username_id).send_keys(BBS_Name)
    driver.find_element(By.ID, password_id).clear()
    driver.find_element(By.ID, password_id).send_keys(BBS_Password)
    driver.find_element(By.ID, login_btn_id).click()
    time.sleep(3)
    try:
        WebDriverWait(driver, 15).until(
            lambda d: "login" not in (d.current_url or "").lower()
        )
    except Exception:
        pass
    time.sleep(2)


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

    driver = create_driver()
    sections_out = []

    try:
        if require_login:
            do_login(driver, login_url, username_id, password_id, login_btn_id)

        for i in range(SECTION_COUNT):
            # 访问 section 页面（无 hash 的路径也可打开，站点会渲染对应内容）
            section_path = f"/section/{i}"
            url = urljoin(BBS_Url + "/", section_path)
            driver.get(url)
            driver.implicitly_wait(5)
            time.sleep(1.5)

            # 讨论区名称：页面上 a[href="/section/{i}"] 的链接文本，如「北邮校园」
            section_name = ""
            try:
                section_links = driver.find_elements(
                    By.CSS_SELECTOR, f'a[href="/section/{i}"]'
                )
                for a in section_links:
                    t = (a.text or "").strip()
                    if t and not t.startswith("http"):
                        section_name = t
                        break
            except Exception:
                pass
            if not section_name:
                section_name = f"讨论区{i}"

            section_url = f"{BBS_Url.rstrip('/')}/#!section/{i}"

            # 按 <tr> 遍历：每行 td.title_1 内第一个链接的名称与地址（兼容 /board/ 与 /section/ 等）
            # 例：<tr><td class="title_1"><a href="/board/Advice">意见与建议</a><br>Advice</td>...
            # 例：<tr><td class="title_1"><a href="/section/BBSLOG">论坛数据统计及日志</a><br>BBSLOG</td>...
            boards = []
            base_url = BBS_Url.rstrip("/")
            try:
                rows = driver.find_elements(By.CSS_SELECTOR, "tr")
                for tr in rows:
                    try:
                        td = tr.find_element(By.CSS_SELECTOR, "td.title_1")
                        link = td.find_element(By.CSS_SELECTOR, "a[href]")
                    except Exception:
                        continue
                    href = (link.get_attribute("href") or "").strip()
                    if not href or "javascript:" in href:
                        continue
                    # 名称：链接文本，若有换行取首行
                    name = (link.text or "").strip()
                    if "\n" in name:
                        name = name.split("\n")[0].strip() or name
                    if not name:
                        name = href.split("/")[-1].split("?")[0] or ""

                    # 地址：统一为站内 #! 形式
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
                pass

            sections_out.append({
                "name": section_name,
                "url": section_url,
                "boards": boards,
            })
            print(f"  讨论区 {i}: {section_name}, 行数: {len(boards)}")

    finally:
        driver.quit()

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
