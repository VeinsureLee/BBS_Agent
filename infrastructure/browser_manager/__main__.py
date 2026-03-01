"""
入口：创建全局浏览器实例，登录，爬取首页内容并保存，关闭浏览器。
仅使用 utils 读取 config 与路径，不使用 utils 之外模块。
"""
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.config_handler import load_config
from utils.env_handler import load_env, get_bbs_credentials
from utils.path_tool import get_abs_path

from infrastructure.browser_manager.browser_manager import GlobalBrowser
from infrastructure.browser_manager.login import login


async def async_main():
    # 加载 .env 环境变量（含 BBS_Name、BBS_Password）
    load_env()

    # 从 config 读取 BBS 首页 URL
    bbs_cfg = load_config()
    home_url = (bbs_cfg.get("BBS_Url") or "").strip().rstrip("/")
    if not home_url:
        print("未配置 BBS_Url，退出")
        return

    # 创建全局浏览器实例并启动
    browser = GlobalBrowser(headless=True)
    await browser.start()

    # 登录（从 .env 读取 BBS_Name、BBS_Password）
    username, password = get_bbs_credentials()
    if username and password:
        await login(browser, username, password)
    else:
        print("未设置 BBS_Name/BBS_Password（可在项目根目录 .env 中配置），跳过登录")

    # 爬取论坛首页（帖子列表）；BBS 为 SPA，登录后跳转为 /#!default
    forum_home = home_url.rstrip("/") + "/#!board/BUPTDNF"
    content = await browser.crawl_page_content(forum_home, wait_after_ms=3000)
    # 格式化 HTML 便于查看（项目已依赖 beautifulsoup4）
    try:
        from bs4 import BeautifulSoup
        content = BeautifulSoup(content, "html.parser").prettify()
    except Exception:
        pass
    out_path = get_abs_path("data/test/test.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    browser.logger.info(f"首页内容已保存到: {out_path}")

    await browser.close()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
