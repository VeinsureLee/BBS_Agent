"""
BBS 初始化调试入口：启动浏览器 -> 初始化（爬取登录框->登录->爬取版面->爬取置顶）-> 退出浏览器。
默认弹出浏览器窗口；加 --headless 或 -q 则不弹出（无头模式）。
  python -m agent.tools.init_tools
  python -m agent.tools.init_tools --headless
"""
import sys
import os

# 保证项目根在 path（必须在 import agent 之前）
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from agent.tools.init_tools.init_tools import start_browser, run_init, close_browser
from dotenv import load_dotenv

load_dotenv()


if __name__ == "__main__":
    # --headless / -q 表示不弹出浏览器；不加则弹出浏览器
    popup_browser = "--headless" not in sys.argv and "-q" not in sys.argv
    debug = True
    try:
        start_browser(debug=popup_browser)
        summary = run_init(debug=debug)
        close_browser()
        if summary.get("skipped"):
            print("已初始化，跳过爬取。")
        else:
            print("BBS 初始化完成（登录页 + 版面结构 + 各版面置顶内容）")
        print("  登录配置:", summary["login_config_path"])
        print("  版面配置:", summary["board_path"])
        print("  置顶内容:", summary.get("introductions_path", ""))
    except Exception as e:
        print("初始化失败:", e)
        sys.exit(1)
