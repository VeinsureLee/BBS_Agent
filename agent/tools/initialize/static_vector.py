"""
结构向量库初始化封装：在 agent/tools/initialize 层实例化 knowledge.stores.structure_store，
从 config/init.json 读取 static_vector_max_workers 作为线程数，供 initialize 流程统一调用。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.path_tool import get_abs_path
from utils.logger_handler import logger

try:
    from knowledge.stores.structure_store import (
        init_static_structure_store,
        get_static_structure_store as _get_static_structure_store,
        get_static_structure_vector_store as _get_static_structure_vector_store,
        get_static_structure_retriever as _get_static_structure_retriever,
    )
except ImportError:
    from knowledge.stores import (
        init_static_structure_store,
        get_static_structure_store as _get_static_structure_store,
        get_static_structure_vector_store as _get_static_structure_vector_store,
        get_static_structure_retriever as _get_static_structure_retriever,
    )

INIT_JSON_PATH = "config/init.json"
CONFIG_KEY_MAX_WORKERS = "static_vector_max_workers"
DEFAULT_MAX_WORKERS = 4


def _load_init_json() -> dict:
    """读取 config/init.json，缺失或解析失败返回默认 dict。"""
    path = get_abs_path(INIT_JSON_PATH)
    default = {CONFIG_KEY_MAX_WORKERS: DEFAULT_MAX_WORKERS}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except (json.JSONDecodeError, IOError):
        return default


def run_static_vector_init(static_folder_path: str | None = None) -> bool:
    """
    执行结构向量库初始化：从 config/init.json 读取 static_vector_max_workers，
    调用 knowledge.stores.structure_store.init_static_structure_store。
    :param static_folder_path: 版面 JSON 目录，None 时使用 data/static
    :return: 是否初始化成功
    """
    init_data = _load_init_json()
    max_workers = init_data.get(CONFIG_KEY_MAX_WORKERS, DEFAULT_MAX_WORKERS)
    if not isinstance(max_workers, int) or max_workers < 1:
        max_workers = DEFAULT_MAX_WORKERS
    logger.info("[结构向量库] 使用线程数: %s（来自 config/init.json static_vector_max_workers）", max_workers)
    return init_static_structure_store(static_folder_path=static_folder_path, max_workers=max_workers)


# 对外暴露与 structure_store 一致的检索接口，便于其他模块从本层引用
def get_static_structure_store(chroma_cfg=None):
    """获取结构向量库服务实例（单例）。"""
    return _get_static_structure_store(chroma_cfg=chroma_cfg)


def get_static_structure_vector_store(chroma_cfg=None):
    """获取结构向量库 Chroma 实例。"""
    return _get_static_structure_vector_store(chroma_cfg=chroma_cfg)


def get_static_structure_retriever(chroma_cfg=None):
    """获取结构向量库检索器。"""
    return _get_static_structure_retriever(chroma_cfg=chroma_cfg)
