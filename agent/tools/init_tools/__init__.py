"""
init_tools 包：
说明：用于 BBS 版面信息的初始化与爬取。
功能：
1、爬取登录页面信息，找到登录框、用户名输入框、密码输入框、登录按钮的元素 id
2、按照讨论区、版面的层级信息，爬取 BBS 的结构信息，将各个讨论区和版面信息保存
3、将各个版面的首页面的置顶内容进行爬取，置顶内容通常为版面内容的相关介绍

模块：
1、login_tools：爬取登录页面信息，找到登录框、用户名输入框、密码输入框、登录按钮的元素 id
2、board_tools：爬取版面结构信息，将各个讨论区和版面层级信息保存
3、inroductions_tools：爬取版面首页面的置顶内容并保存
4、内置 __main__：调试流程为 启动浏览器 -> 初始化 -> 退出浏览器

三个独立能力：启动浏览器、初始化（爬取登录框->登录->爬取版面->爬取置顶）、关闭浏览器。
仅「初始化」作为整体工具暴露给 Agent；启动/关闭浏览器由 main 或调用方使用。
"""
from .init_tools import (
    start_browser,
    run_init,
    close_browser,
    run_bbs_init,
    is_initialized,
)
from .login_tools import crawl_login_page, do_login
from .board_tools import crawl_section_and_boards, crawl_sections_and_boards, SECTION_COUNT, find_board_info_by_name, board_url_to_request_url
from .inroductions import crawl_board_introductions, crawl_one_section_introductions, crawl_all_introductions, save_introductions

__all__ = [
    "start_browser",
    "run_init",
    "close_browser",
    "run_bbs_init",
    "is_initialized",
    "crawl_login_page",
    "do_login",
    "crawl_section_and_boards",
    "crawl_sections_and_boards",
    "SECTION_COUNT",
    "find_board_info_by_name",
    "board_url_to_request_url",
    "crawl_board_introductions",
    "crawl_one_section_introductions",
    "crawl_all_introductions",
    "save_introductions",
]
