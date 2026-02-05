"""
统一从 config 目录下的 JSON 文件加载配置；爬取类配置（如登录页 id）的读写也在此模块。
"""
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
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


def load_bbs_config(config_path: str = None, encoding: str = "utf-8") -> dict:
    config_path = config_path or get_abs_path("config/local/bbs.json")
    return _load_json(config_path, encoding)


def load_driver_config(config_path: str = None, encoding: str = "utf-8") -> dict:
    config_path = config_path or get_abs_path("config/local/driver.json")
    return _load_json(config_path, encoding)


def load_prompts_config(config_path: str = None, encoding: str = "utf-8") -> dict:
    config_path = config_path or get_abs_path("config/prompts/prompts.json")
    return _load_json(config_path, encoding)


def get_crawled_config_path(path: str = "config/crawled/config.json") -> Path:
    """获取爬取配置（登录页 id、版面地址等）的 JSON 路径，固定为 config/crawled/config.json。"""
    return Path(get_abs_path(path))


def load_crawled_config(path: str = "config/crawled/config.json", encoding: str = "utf-8") -> dict:
    """读取爬取配置（登录页 url、username_input_id、password_input_id、login_button_id 等）。"""
    path = get_crawled_config_path(path)
    return _load_json(str(path), encoding)


def save_crawled_config(new_values: dict, path: str = "config/crawled/config.json", encoding: str = "utf-8") -> None:
    """将新配置与已有爬取配置合并后写入 config/crawled/config.json。"""
    path = get_crawled_config_path(path)
    config = load_crawled_config(encoding=encoding)
    config.update(new_values)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=encoding) as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"配置已保存到: {path}")


# 模块加载时读取的配置（供其他模块直接引用）
driver_conf = load_driver_config()
bbs_conf = load_bbs_config()
prompts_conf = load_prompts_config()


if __name__ == "__main__":
    print(driver_conf.get("Chrome_Path"))
    print(driver_conf.get("Chrome_Driver_Path"))
    print(bbs_conf.get("BBS_Url"))
    print("crawled path:", get_crawled_config_path())
    print("crawled config:", load_crawled_config())
