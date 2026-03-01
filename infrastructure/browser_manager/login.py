"""
BBS 登录逻辑：仅使用 utils 中的配置与路径等，不依赖 utils 之外模块。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.config_handler import load_config, load_json_config


async def login(browser, username: str, password: str) -> bool:
    """
    使用全局浏览器实例打开登录页，填写账号密码并点击登录。
    :param browser: GlobalBrowser 实例（需已 await start()）
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

    page = await browser.new_page(
        login_url, wait_until="domcontentloaded", timeout=60000
    )
    try:
        if username_id:
            await page.locator(f"#{username_id}").fill(username)
        if password_id:
            await page.locator(f"#{password_id}").fill(password)
        if username and password and button_id:
            # BBS 可能为 AJAX 登录，不一定会触发 networkidle，先尝试等待导航
            try:
                async with page.expect_navigation(wait_until="load", timeout=15000):
                    await page.locator(f"#{button_id}").click()
            except Exception:
                # 超时或未发生导航时，等待短暂时间让 AJAX 完成后再关闭
                await page.wait_for_timeout(2000)
            return True
        return False
    finally:
        await page.close()
