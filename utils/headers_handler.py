"""
请求头 handler：提供模拟浏览器的默认请求头，供 requests 等 HTTP 客户端使用。
"""
from typing import Any

# 默认请求头，模拟 Chrome 浏览器
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def get_default_headers() -> dict[str, str]:
    """返回模拟浏览器的默认请求头（副本，可安全修改）。"""
    return dict(DEFAULT_HEADERS)


def get_headers(extra: dict[str, Any] | None = None) -> dict[str, str]:
    """
    返回默认请求头，并可合并额外请求头。
    extra 中的值会覆盖同名字段；非字符串值会被转为字符串。
    """
    headers = get_default_headers()
    if extra:
        for k, v in extra.items():
            if v is not None:
                headers[k] = str(v)
    return headers


if __name__ == "__main__":
    # 调试：打印默认请求头
    print("默认请求头:")
    for k, v in get_default_headers().items():
        print(f"  {k}: {v}")
    print("\n带额外 Referer:")
    h = get_headers({"Referer": "https://bbs.byr.cn/"})
    print(h.get("Referer"))
