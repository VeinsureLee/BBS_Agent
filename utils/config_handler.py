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


def load_bbs_config(config_path: str | None = None, encoding: str = "utf-8") -> dict:
    config_path = config_path or get_abs_path("config/websites/bbs.json")
    return _load_json(config_path, encoding)


def load_driver_config(config_path: str | None = None, encoding: str = "utf-8") -> dict:
    config_path = config_path or get_abs_path("config/driver/driver.json")
    return _load_json(config_path, encoding)


def load_prompts_config(config_path: str | None = None, encoding: str = "utf-8") -> dict:
    config_path = config_path or get_abs_path("config/prompts/prompts.json")
    return _load_json(config_path, encoding)


# ---------------------------------------------------------------------------
# config/websites（站点列表等）
# ---------------------------------------------------------------------------

def load_websites_config(config_path: str | None = None, encoding: str = "utf-8") -> dict:
    """加载 config/websites 下的配置，默认 official_websites.json。"""
    path = config_path or get_abs_path("config/websites/official_websites.json")
    return _load_json(path, encoding)


def get_rag_config_path(path: str = "config/model/rag.json") -> Path:
    return Path(get_abs_path(path))


def load_rag_config(path: str = "config/model/rag.json", encoding: str = "utf-8") -> dict:
    path = get_rag_config_path(path)
    return _load_json(str(path), encoding)


def get_chroma_config_path(path: str = "config/vector_store/chroma.json") -> Path:
    return Path(get_abs_path(path))


def load_chroma_config(path: str = "config/vector_store/chroma.json", encoding: str = "utf-8") -> dict:
    path = get_chroma_config_path(path)
    return _load_json(str(path), encoding)


def get_bbs_url() -> str:
    """从 BBS 配置中获取论坛根 URL。"""
    return (load_bbs_config().get("BBS_Url") or "").strip().rstrip("/")


# ---------------------------------------------------------------------------
# config/data（爬取/原始数据配置）
# ---------------------------------------------------------------------------

def load_webdata_raw_config(config_path: str | None = None, encoding: str = "utf-8") -> dict:
    """加载 config/data/raw/webdata_raw.json（爬取数据路径、类型等）。"""
    path = config_path or get_abs_path("config/data/raw/webdata_raw.json")
    return _load_json(path, encoding)


def load_login_config(config_path: str | None = None, encoding: str = "utf-8") -> dict:
    """加载 config/data/login_structure.json（登录页 URL、表单项 id 等）。"""
    path = config_path or get_abs_path("config/data/login_structure.json")
    return _load_json(path, encoding)


# 模块加载时读取的配置（供其他模块直接引用）
driver_conf = load_driver_config()
bbs_conf = load_bbs_config()
prompts_conf = load_prompts_config()
rag_conf = load_rag_config()
chroma_conf = load_chroma_config()


if __name__ == "__main__":
    sep = "-" * 80
    # 仅加载 config 下存在的文件：(显示名, 相对路径, 加载函数)
    config_entries = [
        ("config/driver/driver.json", lambda: load_driver_config()),
        ("config/websites/bbs.json", lambda: load_bbs_config()),
        ("config/prompts/prompts.json", lambda: load_prompts_config()),
        ("config/model/rag.json", lambda: load_rag_config()),
        ("config/vector_store/chroma.json", lambda: load_chroma_config()),
        ("config/websites/official_websites.json", lambda: load_websites_config()),
        ("config/data/raw/webdata_raw.json", lambda: load_webdata_raw_config()),
    ]
    for rel_path, loader in config_entries:
        path = get_abs_path(rel_path)
        if not os.path.exists(path):
            continue
        data = loader()
        print(f"\n[{rel_path}]")
        print(sep)
        print(json.dumps(data, ensure_ascii=False, indent=2) if data else "(空)")
    path_getters = [
        ("get_rag_config_path", get_rag_config_path),
        ("get_chroma_config_path", get_chroma_config_path),
    ]
    print("\n[路径]")
    for name, getter in path_getters:
        p = getter()
        path_str = str(p.resolve() if hasattr(p, "resolve") else p)
        if os.path.exists(path_str):
            print(f"  {name} = {p}")
