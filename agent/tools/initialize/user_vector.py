"""
用户向量库初始化封装：在 agent/tools/initialize 层实例化 knowledge.stores.usr_store，
从 config/init.json 读取 usr_vector_max_workers 作为线程数，供 initialize 流程统一调用。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.path_tool import get_abs_path
from utils.logger_handler import logger

try:
    from knowledge.stores.usr_store import (
        init_usr_vector_store,
        get_usr_vector_store as _get_usr_vector_store,
        get_usr_vector_store_vector_store as _get_usr_vector_store_vector_store,
        get_usr_vector_store_retriever as _get_usr_vector_store_retriever,
    )
except ImportError:
    from knowledge.stores import (
        init_usr_vector_store,
        get_usr_vector_store as _get_usr_vector_store,
        get_usr_vector_store_vector_store as _get_usr_vector_store_vector_store,
        get_usr_vector_store_retriever as _get_usr_vector_store_retriever,
    )

INIT_JSON_PATH = "config/init.json"
CONFIG_KEY_MAX_WORKERS = "usr_vector_max_workers"
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


def run_usr_vector_init(folder_path: str | None = None) -> bool:
    """
    执行用户向量库初始化：从 config/init.json 读取 usr_vector_max_workers，
    调用 knowledge.stores.usr_store.init_usr_vector_store。
    :param folder_path: 要扫描的数据目录，None 时使用 store.json 的 data_path
    :return: 是否初始化成功
    """
    init_data = _load_init_json()
    max_workers = init_data.get(CONFIG_KEY_MAX_WORKERS, DEFAULT_MAX_WORKERS)
    if not isinstance(max_workers, int) or max_workers < 1:
        max_workers = DEFAULT_MAX_WORKERS
    logger.info("[用户向量库] 使用线程数: %s（来自 config/init.json usr_vector_max_workers）", max_workers)
    return init_usr_vector_store(folder_path=folder_path, max_workers=max_workers)


# 对外暴露与 usr_store 一致的检索接口，便于其他模块从本层引用
def get_usr_vector_store(chroma_cfg=None):
    """获取用户向量库服务实例（单例）。"""
    return _get_usr_vector_store(chroma_cfg=chroma_cfg)


def get_usr_vector_store_vector_store(chroma_cfg=None):
    """获取用户向量库 Chroma 实例。"""
    return _get_usr_vector_store_vector_store(chroma_cfg=chroma_cfg)


def get_usr_vector_store_retriever(chroma_cfg=None):
    """获取用户向量库检索器。"""
    return _get_usr_vector_store_retriever(chroma_cfg=chroma_cfg)
