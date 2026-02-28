import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import threading
from playwright.sync_api import sync_playwright

from utils.config_handler import get_bbs_url, driver_conf
from utils.logger_handler import get_logger


class GlobalBrowser:
    """
    全局浏览器管理类（单例）
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        headless: bool = True,
        proxy: dict = None,
        user_agent: str = None,
        storage_state: str = None,
    ):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self.headless = headless
        self.proxy = proxy
        self.user_agent = user_agent
        self.storage_state = storage_state

        self.playwright = None
        self.browser = None
        self.context = None
        
        self.logger = get_logger("browser_manager")

    # =============================
    # 启动浏览器
    # =============================
    def start(self):
        if self.browser:
            return
        
        self.logger.info("启动浏览器")
        self.playwright = sync_playwright().start()
        self.logger.info("playwright 启动成功")
        launch_args = {
            "headless": self.headless,
        }
        if self.proxy:
            launch_args["proxy"] = self.proxy
        chrome_path = driver_conf.get("Chrome_Path")
        if chrome_path:
            launch_args["executable_path"] = chrome_path

        self.browser = self.playwright.chromium.launch(**launch_args)
        self.logger.info("浏览器启动成功")
        context_args = {}

        if self.user_agent:
            context_args["user_agent"] = self.user_agent

        if self.storage_state:
            context_args["storage_state"] = self.storage_state

        self.context = self.browser.new_context(**context_args)

        print("浏览器已启动")

    # =============================
    # 关闭浏览器
    # =============================
    def close(self):
        if self.context:
            self.context.close()

        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()

        self.browser = None
        self.context = None
        print("浏览器已关闭")

    # =============================
    # 打开新页面
    # =============================
    def new_page(self, url: str = None):
        if not self.browser:
            self.start()

        page = self.context.new_page()
        if url:
            page.goto(url, wait_until="networkidle")
        return page

    # =============================
    # 爬取页面内容
    # =============================
    def crawl_page_content(self, url: str, as_text: bool = False, wait_after_ms: int = None) -> str:
        """打开 URL，可选等待若干毫秒（便于 JS 渲染），再取 HTML 或纯文本后关闭页面。"""
        page = self.new_page(url)
        try:
            if wait_after_ms and wait_after_ms > 0:
                page.wait_for_timeout(wait_after_ms)
            return self.get_text(page) if as_text else self.get_html(page)
        finally:
            page.close()

    # =============================
    # 获取页面HTML
    # =============================
    @staticmethod
    def get_html(page):
        return page.content()

    # =============================
    # 获取页面纯文本
    # =============================
    @staticmethod
    def get_text(page):
        return page.inner_text("body")

    # =============================
    # 根据CSS选择器抓取数据
    # =============================
    @staticmethod
    def get_elements_data(page, selector: str):
        elements = page.locator(selector)
        count = elements.count()

        results = []
        for i in range(count):
            el = elements.nth(i)
            results.append({
                "text": el.inner_text(),
                "html": el.inner_html(),
            })

        return results

    # =============================
    # 执行JS
    # =============================
    @staticmethod
    def execute_js(page, script: str):
        return page.evaluate(script)

    # =============================
    # 保存登录状态
    # =============================
    def save_storage(self, path="storage_state.json"):
        self.context.storage_state(path=path)
        print(f"登录状态已保存到 {path}")

