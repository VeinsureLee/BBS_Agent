"""
浏览器启动与关闭：委托给 infrastructure.browser_manager 全局实例。
与 init_tools 配合：start_browser -> run_init（使用 get_page）-> close_browser。
"""
from infrastructure.browser_manager.browser_manager import global_browser_manager


def start_browser(debug: bool = False) -> str:
    """
    启动浏览器（委托给 global_browser_manager）。debug=True 弹窗，debug=False 无头。
    """
    return global_browser_manager.open_browser(headless=not debug)


def close_browser() -> str:
    """关闭浏览器（委托给 global_browser_manager）。"""
    return global_browser_manager.close_browser()


def get_page():
    """返回当前浏览器页面，未启动时为 None。供 init_tools 等调用。"""
    return global_browser_manager.get_page()
