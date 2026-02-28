"""
全局浏览器管理器：仅依赖 utils。根据 config/driver/driver.json 启动/关闭浏览器、爬取页面信息并返回。
使用标准库 urllib + cookiejar 实现，不依赖 Playwright。
"""
import sys
import os
import urllib.request
import urllib.parse
import http.cookiejar
import ssl

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from utils.config_handler import load_driver_config
from utils.logger_handler import get_logger

logger = get_logger("browser_manager")

# 默认不验证 SSL，避免部分站点证书问题
_ssl_context = ssl.create_default_context()
_ssl_context.check_hostname = False
_ssl_context.verify_mode = ssl.CERT_NONE


class GlobalBrowserManager:
    """全局单例：基于 urllib 的“浏览器”会话（Cookie 保持），用于爬取与登录。"""

    def __init__(self):
        self._opener = None
        self._driver_config = None
        self._last_html = ""

    def open_browser(self, headless: bool = False) -> str:
        """
        根据 config/driver/driver.json 启动“浏览器”会话（创建带 Cookie 的 opener）。
        headless 在此实现中仅用于兼容接口，实际无 GUI。
        """
        if self._opener is not None:
            logger.info("浏览器会话已在运行，无需重复启动。")
            return "浏览器已在运行，无需重复启动。"
        self._driver_config = load_driver_config()
        # Chrome_Path 等在此实现中不用于启动进程，仅记录
        if self._driver_config.get("Chrome_Path"):
            logger.debug("driver 配置已加载 Chrome_Path（当前实现为 HTTP 会话，未启动真实浏览器）")
        try:
            cj = http.cookiejar.CookieJar()
            self._opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(cj),
                urllib.request.HTTPSHandler(context=_ssl_context),
            )
            self._opener.addheaders = [
                ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"),
                ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
                ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),
            ]
            self._last_html = ""
            logger.info("浏览器会话已启动（基于 HTTP + Cookie）。")
            return "浏览器已启动。"
        except Exception as e:
            logger.exception("打开浏览器会话失败: %s", e)
            raise

    def close_browser(self) -> str:
        """关闭会话并释放资源。"""
        self._opener = None
        self._driver_config = None
        self._last_html = ""
        logger.info("浏览器已关闭。")
        return "浏览器已关闭。"

    def _request(self, url: str, data=None, method: str = "GET") -> str:
        """【内部】发起 HTTP 请求，将响应 body 写入 _last_html 并返回。crawl_page/post_page 复用此方法。"""
        if self._opener is None:
            logger.warning("请先调用 open_browser() 启动会话。")
            return ""
        url = url.strip()
        if not url:
            logger.warning("请求需要有效 url。")
            return ""
        try:
            if data is not None and isinstance(data, dict):
                data = urllib.parse.urlencode(data).encode("utf-8")
            req = urllib.request.Request(url, data=data, method=method)
            with self._opener.open(req, timeout=15) as resp:
                body = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                try:
                    text = body.decode(charset)
                except Exception:
                    text = body.decode("utf-8", errors="replace")
                self._last_html = text
                return text
        except Exception as e:
            logger.exception("请求失败 %s: %s", url, e)
            return ""

    def get_page_content(self) -> str:
        """返回最近一次请求缓存的 HTML（不发新请求）。用于登录/爬取后直接取当前页内容，避免重复请求。"""
        return self._last_html or ""

    def crawl_page(self, url: str, wait_until: str = "domcontentloaded") -> str:
        """
        打开指定 URL，爬取页面信息并返回 HTML。
        wait_until 在此实现中仅用于兼容，无实际等待。
        """
        return self._request(url, method="GET")

    def post_page(self, url: str, data: dict) -> str:
        """向 url 提交 POST 表单，返回响应 HTML。用于登录等。"""
        return self._request(url, data=data, method="POST")

    def is_running(self) -> bool:
        """会话是否已打开。"""
        return self._opener is not None


# 全局单例
global_browser_manager = GlobalBrowserManager()
