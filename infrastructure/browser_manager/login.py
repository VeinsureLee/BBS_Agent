"""
BBS 登录逻辑：仅使用 utils 中的配置与路径等，不依赖 utils 之外模块。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.config_handler import load_config, load_json_config


def login(browser, username: str, password: str) -> bool:
    """
    使用全局浏览器实例打开登录页，填写账号密码并点击登录。
    :param browser: GlobalBrowser 实例（需已 start）
    :param username: 用户名
    :param password: 密码
    :return: 是否执行了登录操作（未填账号时跳过点击）
    """
    conf = load_json_config(default_path="config/data/login_structure.json")
    bbs_cfg = load_config()
    bbs_url = (bbs_cfg.get("BBS_Url") or "").strip().rstrip("/")
    login_url = (conf.get("login_page_url") or "").strip() or bbs_url
    username_id = (conf.get("username_input_id") or "id").strip()
    password_id = (conf.get("password_input_id") or "pwd").strip()
    button_id = (conf.get("login_button_id") or "b_login").strip()

    page = browser.new_page(login_url)
    try:
        if username_id:
            page.locator(f"#{username_id}").fill(username)
        if password_id:
            page.locator(f"#{password_id}").fill(password)
        if username and password and button_id:
            # 等待登录后跳转（BBS 为 AJAX 登录后 location 跳转）
            with page.expect_navigation(wait_until="networkidle", timeout=15000):
                page.locator(f"#{button_id}").click()
            return True
        return False
    finally:
        page.close()
