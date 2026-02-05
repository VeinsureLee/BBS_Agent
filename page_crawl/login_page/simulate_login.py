"""
根据 .env 中的账号密码和 config/crawled 中的登录页元素 id，模拟登录并将登录后的页面保存为 HTML 文件。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from pathlib import Path

from utils.config_handler import driver_conf, bbs_conf, load_crawled_config, get_crawled_config_path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


load_dotenv()

# 从 config/local/*.json 读取
Chrome_Path = driver_conf.get("Chrome_Path")
Chrome_Driver_Path = driver_conf.get("Chrome_Driver_Path")
BBS_Url = bbs_conf.get("BBS_Url")

# .env 读取账号密码
BBS_Name = os.environ.get("BBS_Name")
BBS_Password = os.environ.get("BBS_Password")

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_HTML_PATH = SCRIPT_DIR / "logged_in_page.html"


def create_driver():
    """创建并返回 Chrome WebDriver。"""
    options = Options()
    if Chrome_Path:
        options.binary_location = Chrome_Path
    service = Service(Chrome_Driver_Path) if Chrome_Driver_Path else None
    return webdriver.Chrome(service=service, options=options)


def simulate_login(*, html_path: str | Path | None = None) -> str:
    """
    使用 .env 中的账号密码登录，将登录后的页面保存为 HTML 文件。
    :param html_path: 保存的 HTML 文件路径，默认为 login_page/logged_in_page.html
    :return: 保存的 HTML 文件绝对路径
    """
    if not BBS_Name or not BBS_Password:
        raise ValueError("请在 .env 中设置 BBS_Name 和 BBS_Password")

    config = load_crawled_config()
    if not config:
        raise FileNotFoundError(f"未找到配置文件: {get_crawled_config_path()}，请先运行 crawl_login_page.py")
    url = config.get("login_page_url") or os.environ.get("BBS_Url") or ""
    if not url.strip():
        raise ValueError("未配置登录页地址，请在 config/crawled 配置文件或 .env 中设置 login_page_url / BBS_Url")

    username_id = (config.get("username_input_id") or "").strip()
    password_id = (config.get("password_input_id") or "").strip()
    login_btn_id = (config.get("login_button_id") or "").strip()
    if not username_id or not password_id or not login_btn_id:
        raise ValueError("config/crawled 配置中缺少 username_input_id / password_input_id / login_button_id，请先运行 crawl_login_page.py")

    save_path = Path(html_path) if html_path else DEFAULT_HTML_PATH
    save_path = save_path.resolve()

    driver = create_driver()
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 10)

        # 等待账号输入框出现并输入
        username_input = wait.until(EC.presence_of_element_located((By.ID, username_id)))
        username_input.clear()
        username_input.send_keys(BBS_Name)

        password_input = driver.find_element(By.ID, password_id)
        password_input.clear()
        password_input.send_keys(BBS_Password)

        login_btn = driver.find_element(By.ID, login_btn_id)
        login_btn.click()

        # 等待跳转：等待一段时间或等待 URL 变化
        time.sleep(3)
        try:
            WebDriverWait(driver, 15).until(lambda d: d.current_url != url or "login" not in d.current_url.lower())
        except Exception:
            pass

        # 再等少许时间确保页面渲染
        time.sleep(2)

        html_content = driver.page_source
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"登录后页面已保存到: {save_path}")
        return str(save_path)
    finally:
        driver.quit()


def main():
    try:
        simulate_login()
        print("完成。")
    except Exception as e:
        print(f"错误: {e}")
        raise


if __name__ == "__main__":
    main()
