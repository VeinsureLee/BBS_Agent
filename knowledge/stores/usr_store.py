"""
用户上传数据的向量库封装：创建实例、按配置加载用户数据，成功后更新 config/init.json 中的 usr_vector_store_status。
"""
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.config_handler import load_json_config
from utils.path_tool import get_abs_path
from utils.logger_handler import logger

from infrastructure.vector_store.vector_store import VectorStoreService

# 用户上传数据向量库配置（与 store.json 对应）
USR_CHROMA_CONFIG_PATH = "config/vector_store/store.json"
INIT_JSON_PATH = "config/init.json"
INIT_STATUS_KEY = "usr_vector_store_status"


def _get_init_json_path() -> str:
    return get_abs_path(INIT_JSON_PATH)


def _load_init_json() -> dict:
    """读取 config/init.json，缺失或解析失败返回默认 dict。"""
    path = _get_init_json_path()
    default = {INIT_STATUS_KEY: False, "static_vector_store_status": False}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except (json.JSONDecodeError, IOError):
        return default


def _update_init_status(updates: dict) -> None:
    """仅更新 config/init.json 中指定字段，其余保留。"""
    path = _get_init_json_path()
    data = _load_init_json()
    data.update(updates)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def init_usr_vector_store(
    folder_path: str | None = None,
    max_workers: int = 4,
) -> bool:
    """
    创建用户向量库实例，按用户上传数据初始化；成功后将 config/init.json 中 usr_vector_store_status 置为 True。
    :param folder_path: 要扫描的数据目录，为 None 时使用 store.json 中的 data_path
    :param max_workers: 批量加载时的线程数，默认 4
    :return: 是否初始化成功
    """
    try:
        chroma_conf = load_json_config(default_path=USR_CHROMA_CONFIG_PATH)
        if not chroma_conf:
            logger.error("[用户向量库] 未找到配置 config/vector_store/store.json")
            return False

        vs = VectorStoreService(chroma_cfg=chroma_conf)
        vs.load_document_batch(folder_path=folder_path, max_workers=max_workers)
        global _usr_vector_store_instance
        _usr_vector_store_instance = vs
        _update_init_status({INIT_STATUS_KEY: True})
        logger.info("[用户向量库] 初始化成功，已更新 config/init.json 中 usr_vector_store_status 为 True")
        return True
    except Exception as e:
        logger.error(f"[用户向量库] 初始化失败：{e}", exc_info=True)
        return False


# 模块级单例：供其他模块直接使用「已按 store.json 配置好的」用户向量库
_usr_vector_store_instance: VectorStoreService | None = None


def get_usr_vector_store(chroma_cfg: dict | None = None) -> VectorStoreService:
    """获取用户向量库服务实例；若未创建则使用 store.json 创建。"""
    global _usr_vector_store_instance
    if _usr_vector_store_instance is None:
        cfg = chroma_cfg or load_json_config(default_path=USR_CHROMA_CONFIG_PATH)
        _usr_vector_store_instance = VectorStoreService(chroma_cfg=cfg)
    return _usr_vector_store_instance


def get_usr_vector_store_vector_store(chroma_cfg: dict | None = None):
    """
    供外部调用的用户向量库（Chroma）实例，可直接用于 similarity_search、as_retriever 等。
    """
    return get_usr_vector_store(chroma_cfg=chroma_cfg).vector_store


def get_usr_vector_store_retriever(chroma_cfg: dict | None = None):
    """供外部调用的用户向量库检索器。"""
    return get_usr_vector_store(chroma_cfg=chroma_cfg).get_retriever()


# 模块加载时初始化用户向量库
success = init_usr_vector_store(max_workers=2)
logger.info("用户向量库初始化: %s", "成功" if success else "失败")
