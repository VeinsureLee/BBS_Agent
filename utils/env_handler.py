"""
环境变量 handler：负责加载 .env 及读取环境变量，供项目统一使用。
环境变量文件：.env，存储项目运行所需的环境变量（敏感信息），如BBS_Name、BBS_Password、DEBUG等。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_loaded = False


def _get_project_root() -> str:
    """项目根目录（utils 的上一级），避免本模块直接运行时导入 path_tool 触发整包。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(dotenv_path: str | None = None) -> bool:
    """
    加载 .env 文件到环境变量。默认使用项目根目录下的 .env。
    仅加载一次，重复调用不会重复加载；返回是否成功加载。
    """
    global _loaded
    if _loaded:
        return True
    try:
        from dotenv import load_dotenv
        path = dotenv_path or os.path.join(_get_project_root(), ".env")
        load_dotenv(path)
        _loaded = True
        return True
    except Exception:
        return False


def get_env(key: str, default: str = "") -> str:
    """获取环境变量，不存在或空时返回 default。"""
    v = os.environ.get(key) or ""
    return (v.strip() if isinstance(v, str) else str(v)) or default


def get_bool_env(key: str) -> bool:
    """判断环境变量是否为“真”：1、true、yes（不区分大小写）为 True，否则为 False。"""
    v = get_env(key).lower()
    return v in ("1", "true", "yes")


def is_debug_mode() -> bool:
    """是否为 debug 模式：环境变量 DEBUG 为 1/true/yes 时视为 debug。"""
    return get_bool_env("DEBUG")


def get_bbs_credentials() -> tuple[str, str]:
    """从环境变量读取 BBS 账号密码，返回 (BBS_Name, BBS_Password)。未设置时返回空字符串。"""
    load_env()
    return get_env("BBS_Name"), get_env("BBS_Password")


def get_api_key() -> str:
    """从环境变量读取 DASHSCOPE_API_KEY。"""
    load_env()
    return get_env("DASHSCOPE_API_KEY")

if __name__ == "__main__":
    # 调试：加载 .env 并打印常用环境变量
    load_env()
    print("DEBUG:", is_debug_mode())
    print("-"*100)
    name, pwd = get_bbs_credentials()
    print("BBS_Name:", name or "(未设置)")
    print("-"*100)
    print("BBS_Password:", pwd or "(未设置)")
    print("-"*100)
    print("get_env('DEBUG', '0'):", get_env("DEBUG", "0"))
    print("-"*100)
    print("get_bool_env('DEBUG'):", get_bool_env("DEBUG"))
    print("-"*100)
    print("DASHSCOPE_API_KEY:", get_api_key() or "(未设置)")
    print("-"*100)
    