"""
调试入口：打开浏览器 -> 登录 -> 关闭浏览器。所有步骤均带 logger。
仅依赖 utils 与 infrastructure.browser_manager。
"""

import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from infrastructure.browser_manager.login import run_login
from infrastructure.browser_manager.browser_manager import global_browser_manager
from utils.logger_handler import get_logger
from utils.env_handler import load_env

# 可选：加载 .env（utils.env_handler 内部也会按需 load_env）
try:
    load_env()
except Exception:
    pass

logger = get_logger("browser_manager_main")


if __name__ == "__main__":
    logger.info("开始调试：打开浏览器 -> 登录 -> 关闭浏览器")
    try:
        # 1. 打开浏览器（browser_manager 内部已打 logger）
        global_browser_manager.open_browser(headless=False)
        logger.info("步骤 1/3：浏览器已打开")

        # 2. 登录（login 模块内部已打 logger）
        run_login(debug=True)
        logger.info("步骤 2/3：登录完成")

        # 可选：抓取当前页面 HTML 用于调试
        html = global_browser_manager.get_page_content()
        if html:
            logger.info("当前页面 HTML 长度: %d 字符", len(html))

        # 3. 关闭浏览器
        global_browser_manager.close_browser()
        logger.info("步骤 3/3：浏览器已关闭，调试结束")
    except Exception as e:
        logger.exception("调试失败: %s", e)
        if global_browser_manager.is_running():
            global_browser_manager.close_browser()
        sys.exit(1)
