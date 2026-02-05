"""
爬取登录页面，自动检测账号、密码输入框和登录按钮的 id，并保存到 config/crawled 的 JSON 配置。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_handler import driver_conf, bbs_conf, load_crawled_config, save_crawled_config

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

load_dotenv()

# 从 config/local/*.json 读取
Chrome_Path = driver_conf.get("Chrome_Path")
Chrome_Driver_Path = driver_conf.get("Chrome_Driver_Path")
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

    options = Options()
    if Chrome_Path:
        options.binary_location = Chrome_Path
    service = Service(Chrome_Driver_Path) if Chrome_Driver_Path else None

    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.get(url)
        # 等待页面加载
        driver.implicitly_wait(5)

        # 1. 密码框：唯一性高，用 type=password
        password_input = None
        try:
            password_input = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
        except Exception:
            pass

        # 2. 账号框：同一表单内的文本输入，或常见的 id/name
        username_input = None
        try:
            # 先尝试同表单内、在密码框之前的 input[type="text"]
            if password_input:
                form = password_input.find_element(By.XPATH, "./ancestor::form[1]")
                inputs = form.find_elements(By.CSS_SELECTOR, 'input[type="text"], input:not([type])')
                for inp in inputs:
                    if inp != password_input and inp.is_displayed():
                        username_input = inp
                        break
            if username_input is None:
                username_input = driver.find_element(By.CSS_SELECTOR, 'input[type="text"]')
        except Exception:
            try:
                username_input = driver.find_element(By.ID, "id")
            except Exception:
                pass

        # 3. 登录按钮：同表单内的 submit 或包含“登录”的按钮
        login_button = None
        try:
            if password_input:
                form = password_input.find_element(By.XPATH, "./ancestor::form[1]")
                for sel in ['input[type="submit"]', 'button[type="submit"]', 'button', 'input[type="button"]']:
                    try:
                        buttons = form.find_elements(By.CSS_SELECTOR, sel)
                        for btn in buttons:
                            if "登录" in (btn.text or "") or "login" in (btn.get_attribute("value") or "").lower():
                                login_button = btn
                                break
                            if sel == 'input[type="submit"]' and buttons:
                                login_button = buttons[0]
                                break
                        if login_button:
                            break
                    except Exception:
                        continue
            if login_button is None:
                login_button = driver.find_element(By.CSS_SELECTOR, 'input[type="submit"]')
        except Exception:
            try:
                login_button = driver.find_element(By.ID, "b_login")
            except Exception:
                pass

        return {
            "login_page_url": url.strip(),
            "username_input_id": get_or_fallback_id(username_input),
            "password_input_id": get_or_fallback_id(password_input),
            "login_button_id": get_or_fallback_id(login_button),
        }
    finally:
        driver.quit()


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
