"""
统一从 config 目录下的 JSON 文件加载配置。
"""
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.path_tool import get_abs_path


def _load_json(config_path: str, encoding: str = "utf-8") -> dict:
    """读取 JSON 文件，不存在或解析失败返回空字典。"""
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding=encoding) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def load_config(config_path: str | None = None, encoding: str = "utf-8") -> dict:
    config_path = config_path or get_abs_path("config/websites/bbs.json")
    return _load_json(config_path, encoding)


def load_json_config(
    config_path: str | None = None,
    default_path: str = "",
    encoding: str = "utf-8",
) -> dict:
    """加载指定路径的 JSON 配置。config_path 优先；若为 None 则使用 default_path。"""
    path_str = config_path if config_path else get_abs_path(default_path)
    return _load_json(path_str, encoding)
