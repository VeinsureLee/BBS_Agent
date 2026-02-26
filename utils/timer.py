"""
计时工具：可作为装饰器或上下文管理器，将耗时写入 logs。
"""
import functools
import time
from contextlib import contextmanager

from utils.logger_handler import get_logger

logger = get_logger("timer")


def timed(name: str = None):
    """
    装饰器：记录函数执行耗时并 logger 到 logs。
    :param name: 显示名称，不传则用函数名
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            display = name or getattr(func, "__name__", "unknown")
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                logger.info("【计时】%s 用时: %.2f 秒", display, elapsed)

        return wrapper

    return decorator


@contextmanager
def timer(name: str):
    """
    上下文管理器：记录代码块执行耗时并 logger 到 logs。
    用法: with timer("讨论区0"): ... 爬取讨论区
    """
    display = name or "block"
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.info("【计时】%s 用时: %.2f 秒", display, elapsed)
