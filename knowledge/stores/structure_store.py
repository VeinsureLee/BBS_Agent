"""
论坛结构向量库封装：将 data/static 下版面 JSON 按字段拆成文档写入 Chroma。

功能说明：
    - 从 data/static 加载版面 JSON，按层级（讨论区、版面、子版面）与字段（speech_rules、post_types 等）拆成多条 Document；
    - 列表型维度按条拆成多条文档存储，便于按版面聚合做相似度查询；
    - 使用 MD5 去重，成功后更新 config/init.json 中 static_vector_store_status 为 True；
    - 提供单例及 get_static_structure_retriever / get_static_structure_vector_store 供检索使用。

主要接口入参/出参：
    - init_static_structure_store(static_folder_path: str | None, max_workers: int = 4) -> bool
        入参：static_folder_path — 版面 JSON 目录，None 时使用 data/static；max_workers — 加载线程数。
        出参：是否初始化成功；成功时写入 init.json 的 static_vector_store_status。
    - get_static_structure_store(chroma_cfg: dict | None) -> VectorStoreService
        入参：chroma_cfg — 可选，None 时从 config/vector_store/static.json 加载。
        出参：结构向量库服务实例（单例）。
    - get_static_structure_vector_store(chroma_cfg) / get_static_structure_retriever(chroma_cfg)
        入参：同上。出参：Chroma 实例或 Retriever。
"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.config_handler import load_json_config
from utils.path_tool import get_abs_path
from utils.dimension_config import get_board_field_keys, get_field_label_map
from utils.file_handler import list_allowed_files_recursive, get_file_md5_hex
from utils.logger_handler import logger

from infrastructure.vector_store.md5 import check_md5_hex, save_md5_hex

from langchain_core.documents import Document

from infrastructure.vector_store.vector_store import VectorStoreService

# 与 usr_store 保持一致：使用 static 向量库配置与 init 状态
STATIC_CHROMA_CONFIG_PATH = "config/vector_store/static.json"
STATIC_DATA_PATH = "data/static"
INIT_JSON_PATH = "config/init.json"
INIT_STATUS_KEY = "static_vector_store_status"

def _get_init_json_path() -> str:
    return get_abs_path(INIT_JSON_PATH)


def _load_init_json() -> dict:
    """读取 config/init.json，缺失或解析失败返回默认 dict。"""
    path = _get_init_json_path()
    default = {"usr_vector_store_status": False, INIT_STATUS_KEY: False}
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


def _parse_hierarchy(hierarchy_path: str) -> tuple[str, str, str | None]:
    """
    从 hierarchy_path 解析层级信息。
    :return: (讨论区, 版面, 父版面或None)
    """
    if not hierarchy_path or not isinstance(hierarchy_path, str):
        return "", "", None
    parts = [p.strip() for p in hierarchy_path.replace("\\", "/").split("/") if p.strip()]
    if not parts:
        return "", "", None
    discussion_area = parts[0]
    board = parts[-1]
    parent_board = parts[-2] if len(parts) >= 3 else None
    return discussion_area, board, parent_board


def _board_json_to_documents(file_path: str, data: dict) -> list[Document]:
    """
    将单个版面 JSON 转为多条 Document，每条对应一个字段（如 speech_rules、post_types 等），
    并带上层级元数据。
    """
    hierarchy_path = data.get("hierarchy_path") or data.get("hierarchy") or ""
    discussion_area, board, parent_board = _parse_hierarchy(hierarchy_path)

    base_meta = {
        "source": "structure",
        "hierarchy_path": hierarchy_path,
        "discussion_area": discussion_area,
        "board": board,
        "board_name": data.get("board_name") or board,
    }
    if parent_board is not None:
        base_meta["parent_board"] = parent_board

    board_field_keys = get_board_field_keys()
    field_label_map = get_field_label_map()
    docs: list[Document] = []
    for field in board_field_keys:
        value = data.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            content = value.strip()
            if not content:
                continue
            page_content = content
            meta = {**base_meta, "field_name": field}
            docs.append(Document(page_content=page_content, metadata=meta))
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                content = str(item).strip() if item else ""
                if not content:
                    continue
                field_label = field_label_map.get(field, field)
                page_content = f"{field_label}：\n{content}"
                meta = {**base_meta, "field_name": field, "rule_index": idx}
                docs.append(Document(page_content=page_content, metadata=meta))
        else:
            continue

    return docs


def init_static_structure_store(
    static_folder_path: str | None = None,
    max_workers: int = 4,
) -> bool:
    """
    创建 static 向量库实例，从 data/static 加载版面结构 JSON，
    按层级（讨论区、版面、子版面）和按字段（speech_rules、post_types 等）拆成多条文档写入向量库。
    使用多线程并行读取与解析，写入向量库时加锁保证线程安全。
    成功后将 config/init.json 中 static_vector_store_status 置为 True。
    :param static_folder_path: 版面 JSON 所在目录，为 None 时使用 data/static
    :param max_workers: 批量加载时的线程数，默认 4
    :return: 是否初始化成功
    """
    try:
        chroma_conf = load_json_config(default_path=STATIC_CHROMA_CONFIG_PATH)
        if not chroma_conf:
            logger.error("[结构向量库] 未找到配置 config/vector_store/static.json")
            return False

        vs = VectorStoreService(chroma_cfg=chroma_conf)
        data_dir = static_folder_path or STATIC_DATA_PATH
        static_abs = get_abs_path(data_dir)
        if not os.path.isdir(static_abs):
            logger.warning(f"[结构向量库] {static_abs} 不是目录，跳过加载")
            return False

        allowed_paths = list_allowed_files_recursive(static_abs, (".json",))
        if not allowed_paths:
            logger.warning("[结构向量库] 未找到任何 JSON 文件，请检查 data/static 下是否有版面 JSON")
            return False

        md5_store_path = get_abs_path(chroma_conf.get("md5_hex_store", "vector_db/static/md5.txt"))
        write_lock = threading.Lock()
        total_docs = 0

        def process_one_file(path: str) -> tuple[str, list[Document], str, str] | None:
            """单文件处理：读 MD5、JSON，转为 Document 列表，返回 (path, docs, board_name, md5_hex)，跳过则返回 None。"""
            md5_hex = get_file_md5_hex(path)
            if md5_hex is None:
                return None
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    return None
                docs = _board_json_to_documents(path, data)
                if not docs:
                    logger.debug("[结构向量库] 版面无有效字段，跳过: %s", path)
                    return None
                board_name = (
                    data.get("board_name")
                    or (data.get("hierarchy_path") or "").split("/")[-1]
                    or path
                )
                return (path, docs, board_name, md5_hex)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"[结构向量库] 读取或解析失败 {path}: {e}")
                return None

        def add_to_store_and_save_md5(
            path: str, docs: list[Document], board_name: str, md5_hex: str
        ) -> int:
            """写入向量库并保存 MD5；若已存在则跳过。返回本次写入的文档数（0 表示已跳过）。"""
            with write_lock:
                if check_md5_hex(md5_hex, md5_store_path):
                    logger.info("[结构向量库] 内容已存在知识库内，跳过: %s", path)
                    return 0
                vs.vector_store.add_documents(docs)
                save_md5_hex(md5_hex, md5_store_path)
                logger.info(
                    "[结构向量库] 版面向量化完成 | 版面=%s | 文件=%s | 文档数=%d",
                    board_name,
                    path,
                    len(docs),
                )
                return len(docs)

        logger.info(
            "[结构向量库] 共 %d 个文件，使用 %d 个线程",
            len(allowed_paths),
            max_workers,
        )
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_one_file, p): p for p in allowed_paths}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    path, docs, board_name, md5_hex = result
                    total_docs += add_to_store_and_save_md5(path, docs, board_name, md5_hex)

        if total_docs == 0:
            logger.warning("[结构向量库] 未生成任何文档，请检查 data/static 下是否有版面 JSON")
            return False

        global _static_structure_store_instance
        _static_structure_store_instance = vs
        _update_init_status({INIT_STATUS_KEY: True})
        logger.info(
            "[结构向量库] 初始化成功，共写入 %d 条结构文档，已更新 config/init.json 中 static_vector_store_status 为 True",
            total_docs,
        )
        return True
    except Exception as e:
        logger.error(f"[结构向量库] 初始化失败：{e}", exc_info=True)
        return False


# 模块级单例：供其他模块直接使用「已按 static.json 配置好的」结构向量库
_static_structure_store_instance: VectorStoreService | None = None


def get_static_structure_store(chroma_cfg: dict | None = None) -> VectorStoreService:
    """获取结构向量库服务实例；若未创建则使用 static.json 创建（不自动加载数据）。"""
    global _static_structure_store_instance
    if _static_structure_store_instance is None:
        cfg = chroma_cfg or load_json_config(default_path=STATIC_CHROMA_CONFIG_PATH)
        _static_structure_store_instance = VectorStoreService(chroma_cfg=cfg)
    return _static_structure_store_instance


def get_static_structure_vector_store(chroma_cfg: dict | None = None):
    """
    供外部调用的结构向量库（Chroma）实例，可直接用于 similarity_search、as_retriever 等。
    """
    return get_static_structure_store(chroma_cfg=chroma_cfg).vector_store


def get_static_structure_retriever(chroma_cfg: dict | None = None):
    """供外部调用的结构向量库检索器。"""
    return get_static_structure_store(chroma_cfg=chroma_cfg).get_retriever()


# 模块加载时：读取 init.json，已初始化则跳过，否则执行初始化
_init_data = _load_init_json()
if _init_data.get(INIT_STATUS_KEY) is True:
    get_static_structure_store()
    logger.info("结构向量库已初始化，跳过")
else:
    success = init_static_structure_store(max_workers=128)
    logger.info("结构向量库初始化: %s", "成功" if success else "失败")
