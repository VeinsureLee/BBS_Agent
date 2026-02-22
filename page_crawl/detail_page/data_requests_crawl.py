"""
使用 Playwright 模拟登录北邮人论坛，并访问登录后页面（如 JobInfo 版面）。
可从 config/crawled/config.json 读取登录页配置，从 .env 读取账号密码。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from utils.config_handler import driver_conf, load_crawled_config

load_dotenv()

config = load_crawled_config()
if not config:
    config = {
        "login_page_url": "https://bbs.byr.cn",
        "username_input_id": "id",
        "password_input_id": "pwd",
        "login_button_id": "b_login",
    }

username = os.environ.get("BBS_Name", "Buendia")
password = os.environ.get("BBS_Password", "LiWenXuan0113")

Chrome_Path = driver_conf.get("Chrome_Path")
launch_options = {}
if Chrome_Path:
    launch_options["executable_path"] = Chrome_Path

with sync_playwright() as p:
    browser = p.chromium.launch(**launch_options)
    try:
        page = browser.new_page()
        login_url = (config.get("login_page_url") or "").strip()
        page.goto(login_url, wait_until="domcontentloaded")
        print("GET login page: ok")

        page.wait_for_selector(f"#{config['username_input_id']}", state="visible", timeout=10000)
        page.locator(f"#{config['username_input_id']}").fill(username)
        page.locator(f"#{config['password_input_id']}").fill(password)
        page.locator(f"#{config['login_button_id']}").click()

        page.wait_for_url(lambda u: "login" not in u.lower(), timeout=15000)
        print("Login: ok")

        protected_url = "https://bbs.byr.cn/board/JobInfo"
        page.goto(protected_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)
        print("Protected page content (first 2000 chars):")
        print(page.content()[:2000])
    finally:
        browser.close()
