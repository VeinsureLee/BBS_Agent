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


# ---------------------------------------------------------------------------
# config/web_structure（保存路径由 save.json 定义）
# ---------------------------------------------------------------------------

def load_web_structure_save_config(encoding: str = "utf-8") -> dict:
    """加载 config/web_structure/save.json，得到各保存路径（login_config, board, init_status_file 等）。"""
    path = get_abs_path("config/web_structure/save.json")
    if not os.path.exists(path):
        return {
            "login_config": "config/web_structure/config.json",
            "board": "config/web_structure/board/board.json",
            "init_status_file": "config/web_structure/init.json",
        }
    return _load_json(path, encoding)


def get_web_structure_login_config_path() -> Path:
    """登录页配置 JSON 路径（由 save.json 的 login_config 决定）。"""
    cfg = load_web_structure_save_config()
    return Path(get_abs_path(cfg.get("login_config", "config/web_structure/board/login_page.json")))


def get_web_structure_board_path() -> Path:
    """版面结构 JSON 路径（由 save.json 的 board 决定）。"""
    cfg = load_web_structure_save_config()
    return Path(get_abs_path(cfg.get("board", "config/web_structure/board/board.json")))


def get_web_structure_init_status_path() -> Path:
    """初始化状态 JSON 路径（由 save.json 的 init_status_file 决定）。"""
    cfg = load_web_structure_save_config()
    return Path(get_abs_path(cfg.get("init_status_file", "config/web_structure/init.json")))


def get_web_structure_introductions_path() -> Path:
    """版面置顶内容（介绍）根目录（由 save.json 的 introductions_root 决定）。介绍保存为 根目录/讨论区名称/版面名称/介绍[index].json"""
    return get_web_structure_introductions_root()


def get_web_structure_introductions_root() -> Path:
    """介绍文件根目录，其下为 讨论区名称/版面名称/介绍0.json, 介绍1.json ..."""
    cfg = load_web_structure_save_config()
    return Path(get_abs_path(cfg.get("introductions_root", "config/web_structure/board"))).resolve()


def load_web_structure_login_config(encoding: str = "utf-8") -> dict:
    """读取登录页配置（login_page_url, username_input_id, password_input_id, login_button_id）。"""
    path = get_web_structure_login_config_path()
    return _load_json(str(path), encoding)


def save_web_structure_login_config(new_values: dict, encoding: str = "utf-8") -> None:
    """将登录页配置写入 save.json 中 login_config 指定的路径。"""
    path = get_web_structure_login_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=encoding) as f:
        json.dump(new_values, f, ensure_ascii=False, indent=2)
    print(f"配置已保存到: {path}")


def load_web_structure_board_config(encoding: str = "utf-8") -> dict:
    """读取版面结构（sections 等）。"""
    path = get_web_structure_board_path()
    return _load_json(str(path), encoding)


# ---------------------------------------------------------------------------
# config/websites（站点列表等）
# ---------------------------------------------------------------------------

def load_websites_config(config_path: str = None, encoding: str = "utf-8") -> dict:
    """加载 config/websites 下的配置，默认 official_websites.json。"""
    path = config_path or get_abs_path("config/websites/official_websites.json")
    return _load_json(path, encoding)


def get_rag_config_path(path: str = "config/prompts/rag.json") -> Path:
    return Path(get_abs_path(path))


def load_rag_config(path: str = "config/prompts/rag.json", encoding: str = "utf-8") -> dict:
    path = get_rag_config_path(path)
    return _load_json(str(path), encoding)


def get_chroma_config_path(path: str = "config/local/chroma.json") -> Path:
    return Path(get_abs_path(path))


def load_chroma_config(path: str = "config/local/chroma.json", encoding: str = "utf-8") -> dict:
    path = get_chroma_config_path(path)
    return _load_json(str(path), encoding)


# 模块加载时读取的配置（供其他模块直接引用）
driver_conf = load_driver_config()
bbs_conf = load_bbs_config()
prompts_conf = load_prompts_config()
rag_conf = load_rag_config()
chroma_conf = load_chroma_config()


if __name__ == "__main__":
    print(driver_conf.get("Chrome_Path"))
    print(driver_conf.get("Chrome_Driver_Path"))
    print(bbs_conf.get("BBS_Url"))
    print("web_structure login path:", get_web_structure_login_config_path())
    print("web_structure login config:", load_web_structure_login_config())
    print("prompts config:", prompts_conf)
    print("rag config:", rag_conf)
    print("chroma config:", chroma_conf)