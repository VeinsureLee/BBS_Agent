import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
import threading
from playwright.async_api import async_playwright

from utils.config_handler import load_json_config
from utils.logger_handler import get_logger


class GlobalBrowser:
    """
    全局浏览器管理类（单例），异步 API，支持多 page 并行爬取。
    """

    _instance = None
    _init_lock = threading.Lock()
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._init_lock:
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
    async def start(self):
        async with self._lock:
            if self.browser:
                return

            self.logger.info("启动浏览器")
            self.playwright = await async_playwright().start()
            self.logger.info("playwright 启动成功")
            launch_args = {
                "headless": self.headless,
            }
            if self.proxy:
                launch_args["proxy"] = self.proxy
            driver_conf = load_json_config(default_path="config/driver/driver.json")
            chrome_path = driver_conf.get("Chrome_Path")
            if chrome_path:
                launch_args["executable_path"] = chrome_path

            self.browser = await self.playwright.chromium.launch(**launch_args)
            self.logger.info("浏览器启动成功")
            context_args = {}

            if self.user_agent:
                context_args["user_agent"] = self.user_agent

            if self.storage_state:
                context_args["storage_state"] = self.storage_state

            self.context = await self.browser.new_context(**context_args)

            print("浏览器已启动")

    # =============================
    # 关闭浏览器
    # =============================
    async def close(self):
        if self.context:
            await self.context.close()

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        self.playwright = None
        self.browser = None
        self.context = None
        print("浏览器已关闭")

    # =============================
    # 打开新页面
    # =============================
    async def new_page(
        self,
        url: str = None,
        wait_until: str = "load",
        timeout: int | None = None,
    ):
        """打开新页面，可选导航到 url。wait_until: 'load' | 'domcontentloaded' | 'networkidle'。timeout: 导航超时毫秒数，默认 Playwright 默认值。"""
        if not self.browser:
            await self.start()

        page = await self.context.new_page()
        if url:
            kwargs = {"url": url, "wait_until": wait_until}
            if timeout is not None:
                kwargs["timeout"] = timeout
            await page.goto(**kwargs)
        return page

    # =============================
    # 爬取页面内容
    # =============================
    async def crawl_page_content(
        self,
        url: str,
        as_text: bool = False,
        wait_after_ms: int = None,
        wait_until: str = "load",
    ) -> str:
        """打开 URL，可选等待若干毫秒（便于 JS 渲染），再取 HTML 或纯文本后关闭页面。"""
        page = await self.new_page(url, wait_until=wait_until)
        try:
            if wait_after_ms and wait_after_ms > 0:
                await page.wait_for_timeout(wait_after_ms)
            return await (self.get_text(page) if as_text else self.get_html(page))
        finally:
            await page.close()

    # =============================
    # 按选择器爬取（只取指定节点，更快）
    # =============================
    async def crawl_selector(
        self,
        url: str,
        selector: str,
        wait_until_selector: str | None = None,
        wait_until: str = "load",
        timeout: int = 8000,
        wait_selector_state: str = "attached",
    ) -> list:
        """
        打开 URL，可选等待目标选择器出现，再只抓取 selector 匹配节点的 text/html，关闭页面。
        wait_selector_state: 'attached'（仅需在 DOM 中）| 'visible'（需可见），SPA 建议 attached。
        返回 list[{"text": str, "html": str}]。
        """
        page = await self.new_page(url, wait_until=wait_until)
        try:
            if wait_until_selector:
                await page.wait_for_selector(
                    wait_until_selector, timeout=timeout, state=wait_selector_state
                )
            return await self.get_elements_data(page, selector)
        finally:
            await page.close()

    # =============================
    # 获取页面HTML
    # =============================
    @staticmethod
    async def get_html(page):
        return await page.content()

    # =============================
    # 获取页面纯文本
    # =============================
    @staticmethod
    async def get_text(page):
        return await page.inner_text("body")

    # =============================
    # 根据CSS选择器抓取数据
    # =============================
    @staticmethod
    async def get_elements_data(page, selector: str):
        elements = page.locator(selector)
        count = await elements.count()

        results = []
        for i in range(count):
            el = elements.nth(i)
            results.append({
                "text": await el.inner_text(),
                "html": await el.inner_html(),
            })

        return results

    # =============================
    # 执行JS
    # =============================
    @staticmethod
    async def execute_js(page, script: str):
        return await page.evaluate(script)

    # =============================
    # 保存登录状态
    # =============================
    async def save_storage(self, path="storage_state.json"):
        await self.context.storage_state(path=path)
        print(f"登录状态已保存到 {path}")
