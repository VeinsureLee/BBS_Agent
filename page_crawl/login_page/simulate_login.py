"""
根据 .env 中的账号密码和 config/crawled 中的登录页元素 id，模拟登录并将登录后的页面保存为 HTML 文件。
使用 Playwright 实现。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pathlib import Path

from utils.config_handler import driver_conf, load_crawled_config, get_crawled_config_path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

# 从 config/local/*.json 读取
Chrome_Path = driver_conf.get("Chrome_Path")
BBS_Url = os.environ.get("BBS_Url")

# .env 读取账号密码
BBS_Name = os.environ.get("BBS_Name")
BBS_Password = os.environ.get("BBS_Password")

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_HTML_PATH = SCRIPT_DIR / "logged_in_page.html"


def create_browser(playwright):
    """创建并返回 Chromium 浏览器实例。"""
    launch_options = {}
    if Chrome_Path:
        launch_options["executable_path"] = Chrome_Path
    return playwright.chromium.launch(**launch_options)


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

    with sync_playwright() as p:
        browser = create_browser(p)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_selector(f"#{username_id}", state="visible", timeout=10000)

            page.locator(f"#{username_id}").fill("")
            page.locator(f"#{username_id}").fill(BBS_Name)
            page.locator(f"#{password_id}").fill("")
            page.locator(f"#{password_id}").fill(BBS_Password)
            page.locator(f"#{login_btn_id}").click()

            # 等待跳转
            page.wait_for_url(lambda u: "login" not in u.lower(), timeout=15000)
            page.wait_for_load_state("networkidle", timeout=10000)

            html_content = page.content()
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            print(f"登录后页面已保存到: {save_path}")
            return str(save_path)
        finally:
            browser.close()


def main():
    try:
        simulate_login()
        print("完成。")
    except Exception as e:
        print(f"错误: {e}")
        raise


if __name__ == "__main__":
    main()
