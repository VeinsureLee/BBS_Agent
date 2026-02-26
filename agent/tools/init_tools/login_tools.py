"""
登录相关工具：爬取登录页登录框元素信息、执行登录。
供 init_tools 在同一浏览器实例中调用，不单独启动浏览器。
"""
import os


def _get_or_fallback_id(element) -> str:
    if element is None:
        return ""
    return element.get_attribute("id") or ""


def crawl_login_page(page, url: str, debug: bool = False) -> dict:
    """
    使用已有 page 打开登录页并检测账号、密码、登录按钮的 id。
    :param page: Playwright 的 Page 对象
    :param url: BBS 登录页 URL
    :param debug: 为 True 时爬取完成后 print 一行
    :return: 含 login_page_url, username_input_id, password_input_id, login_button_id 的字典
    """
    if not url or not url.strip():
        raise ValueError("BBS_Url 未设置或为空")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)

    password_input = page.query_selector('input[type="password"]')
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

    result = {
        "login_page_url": url.strip(),
        "username_input_id": _get_or_fallback_id(username_input),
        "password_input_id": _get_or_fallback_id(password_input),
        "login_button_id": _get_or_fallback_id(login_button),
    }
    if debug:
        print("  [DEBUG] 登录页爬取完成:", result["login_page_url"], "->", "username_input_id=%s" % result["username_input_id"], "password_input_id=%s" % result["password_input_id"], "login_button_id=%s" % result["login_button_id"])
    return result


def do_login(
    page,
    login_url: str,
    username_id: str,
    password_id: str,
    login_btn_id: str,
    debug: bool = False,
) -> None:
    """
    在已有 page 上填写账号密码并点击登录。
    :param page: Playwright 的 Page 对象
    :param login_url: 登录页 URL
    :param username_id: 用户名输入框 id（选择器用 #id）
    :param password_id: 密码输入框 id
    :param login_btn_id: 登录按钮 id
    :param debug: 为 True 时登录完成后 print 一行
    """
    BBS_Name = os.environ.get("BBS_Name")
    BBS_Password = os.environ.get("BBS_Password")
    if not BBS_Name or not BBS_Password:
        raise ValueError("请设置环境变量 BBS_Name 和 BBS_Password")
    page.goto(login_url, wait_until="domcontentloaded")
    page.wait_for_selector(f"#{username_id}", state="visible", timeout=10000)
    page.locator(f"#{username_id}").fill("")
    page.locator(f"#{username_id}").fill(BBS_Name)
    page.locator(f"#{password_id}").fill("")
    page.locator(f"#{password_id}").fill(BBS_Password)
    page.locator(f"#{login_btn_id}").click()
    page.wait_for_url(lambda u: "login" not in u.lower(), timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    if debug:
        print("  [DEBUG] 登录完成")
