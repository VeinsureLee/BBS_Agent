"""
爬取登录页面，自动检测账号、密码输入框和登录按钮的 id，并保存到 config/crawled 的 JSON 配置。
使用 Playwright 实现。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from utils.config_handler import driver_conf, bbs_conf, load_crawled_config, save_crawled_config
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

# 从 config/local/*.json 读取
Chrome_Path = driver_conf.get("Chrome_Path")
BBS_Url = bbs_conf.get("BBS_Url")


def get_or_fallback_id(element) -> str:
    """获取元素的 id，若无 id 则返回空字符串。"""
    if element is None:
        return ""
    return element.get_attribute("id") or ""


def crawl_login_page(url: str) -> dict:
    """
    打开登录页，检测账号输入框、密码输入框、登录按钮的 id。
    返回包含 url 与三个 id 的字典。
    """
    if not url or not url.strip():
        raise ValueError("BBS_Url 未设置或为空，请在 .env 中配置 BBS_Url")

    launch_options = {}
    if Chrome_Path:
        launch_options["executable_path"] = Chrome_Path

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_options)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=10000)

            # 1. 密码框：唯一性高，用 type=password
            password_input = page.query_selector('input[type="password"]')

            # 2. 账号框：同一表单内的文本输入，或常见的 id/name
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

            # 3. 登录按钮：同表单内的 submit 或包含“登录”的按钮
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
                "username_input_id": get_or_fallback_id(username_input),
                "password_input_id": get_or_fallback_id(password_input),
                "login_button_id": get_or_fallback_id(login_button),
            }
        finally:
            browser.close()


def main():
    url = (BBS_Url or "").strip()
    if not url:
        print("错误: 请在 .env 中设置 BBS_Url")
        return

    print(f"正在打开登录页: {url}")
    result = crawl_login_page(url)
    print("检测结果:", result)
    save_crawled_config(result)
    print("完成。")


if __name__ == "__main__":
    main()
