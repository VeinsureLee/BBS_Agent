"""
浏览器启动与关闭：供 main 或调用方使用，不暴露给 Agent。
与 init_tools 配合：start_browser -> run_init（使用 get_page）-> close_browser。
"""
from playwright.sync_api import sync_playwright

from utils.config_handler import driver_conf, bbs_conf

# ---------------------------------------------------------------------------
# 浏览器实例（由 start_browser 设置，由 close_browser 清除）
# ---------------------------------------------------------------------------
_playwright = None
_browser = None
_page = None


def start_browser(debug: bool = False) -> str:
    """
    启动 Playwright 浏览器并创建新页面，将 page 存入模块状态供 run_init 使用。
    debug=True 时弹出浏览器窗口，debug=False 时无头模式不弹出。
    与 close_browser 配对使用；main 中调试流程：start_browser -> run_init -> close_browser。
    """
    global _playwright, _browser, _page
    if _page is not None:
        print("浏览器已在运行，无需重复启动。")
        return "浏览器已在运行，无需重复启动。"
    BBS_Url = (bbs_conf.get("BBS_Url") or "").strip().rstrip("/")
    if not BBS_Url:
        raise ValueError("未配置 BBS_Url，请在 config/local/bbs.json 中设置")
    Chrome_Path = driver_conf.get("Chrome_Path")
    launch_options = {"headless": not debug}
    if Chrome_Path:
        launch_options["executable_path"] = Chrome_Path
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(**launch_options)
    _page = _browser.new_page()
    print("浏览器已启动。")
    return "浏览器已启动。"


def close_browser() -> str:
    """关闭当前浏览器并清除模块状态。与 start_browser 配对使用。"""
    global _playwright, _browser, _page
    if _browser is not None:
        _browser.close()
        _browser = None
    if _playwright is not None:
        _playwright.stop()
        _playwright = None
    _page = None
    return "浏览器已关闭。"


def get_page():
    """返回当前浏览器页面，未启动时为 None。供 init_tools 等调用。"""
    return _page
