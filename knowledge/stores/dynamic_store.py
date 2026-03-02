"""
论坛动态帖子（data/dynamic 下按讨论区/版面/日期存放的单帖 JSON）的向量库封装：
从传入路径递归加载帖子 JSON（title, time, author, reply_count, url, floors），
将每条帖子转为 Document 写入向量库，使用 MD5 去重。
"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.config_handler import load_json_config
from utils.path_tool import get_abs_path
from utils.file_handler import list_allowed_files_recursive, get_file_md5_hex
from utils.logger_handler import logger

from infrastructure.vector_store.md5 import check_md5_hex, save_md5_hex

from langchain_core.documents import Document

from infrastructure.vector_store.vector_store import VectorStoreService

DYNAMIC_CHROMA_CONFIG_PATH = "config/vector_store/dynamic.json"


def _parse_section_board_date_from_path(abs_path: str) -> tuple[str, str, str]:
    """
    从帖子 JSON 路径解析讨论区、版面、日期。
    路径约定：.../data/dynamic/讨论区/版面/日期/帖子标题.json
    :return: (section_name, board_name, date)
    """
    norm = os.path.normpath(abs_path).replace("\\", "/")
    parts = norm.strip("/").split("/")
    data_idx = -1
    for i, p in enumerate(parts):
        if p == "dynamic":
            data_idx = i
            break
    if data_idx < 0 or data_idx + 3 >= len(parts):
        return "", "", ""
    # dynamic / 讨论区 / 版面 / 日期 / xxx.json
    section = parts[data_idx + 1] or ""
    board = parts[data_idx + 2] or ""
    date = parts[data_idx + 3] or ""
    return section, board, date


def _floor_content_to_text(content) -> str:
    """从楼层 content（可能为 dict 或 str）提取正文。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        return (content.get("正文") or content.get("content") or "").strip()
    return str(content).strip()


def _post_json_to_documents(file_path: str, data: dict) -> list[Document]:
    """
    将单个帖子 JSON（title, time, author, reply_count, url, floors）转为一条或多条 Document。
    每条帖子合并为一条 Document：标题 + 各楼正文，便于检索。
    """
    section, board, date = _parse_section_board_date_from_path(file_path)
    title = data.get("title") or ""
    time_str = data.get("time") or ""
    author = data.get("author") or ""
    reply_count = data.get("reply_count", 0)
    url = data.get("url") or ""
    floors = data.get("floors") or []

    content_parts = [
        f"标题：{title} 作者：{author} 时间：{time_str} 回复数：{reply_count} 链接：{url}"
    ]
    for fl in floors:
        raw = fl.get("content")
        text = _floor_content_to_text(raw)
        if text:
            content_parts.append(text)

    content = "\n\n".join(content_parts)
    if not content.strip():
        return []

    rel_path = os.path.relpath(file_path, get_abs_path("data")).replace("\\", "/")
    meta = {
        "source_file": rel_path,
        "source": "dynamic",
        "section": section,
        "board": board,
        "date": date,
        "title": title,
        "author": author,
        "reply_count": reply_count,
        "url": url,
    }
    return [Document(page_content=content, metadata=meta)]


def init_dynamic_store(
    folder_path: str | None = None,
    max_workers: int = 4,
) -> bool:
    """
    创建 dynamic 向量库实例，从指定路径递归加载帖子 JSON，转为 Document 写入向量库。
    使用 MD5 去重。
    :param folder_path: 要扫描的目录（如 data/dynamic/生活时尚/创意生活），为 None 时使用配置中的 data_path
    :param max_workers: 批量加载时的线程数，默认 4
    :return: 是否初始化/写入成功
    """
    try:
        chroma_conf = load_json_config(default_path=DYNAMIC_CHROMA_CONFIG_PATH)
        if not chroma_conf:
            logger.error("[动态向量库] 未找到配置 config/vector_store/dynamic.json")
            return False

        vs = VectorStoreService(chroma_cfg=chroma_conf)
        data_dir = folder_path or chroma_conf.get("data_path", "data/dynamic")
        data_abs = get_abs_path(data_dir)
        if not os.path.isdir(data_abs):
            logger.warning(f"[动态向量库] {data_abs} 不是目录，跳过加载")
            return False

        allowed_paths = list_allowed_files_recursive(data_abs, (".json",))
        if not allowed_paths:
            logger.warning("[动态向量库] 未找到任何 JSON 文件，请检查路径下是否有帖子 JSON")
            return False

        md5_store_path = get_abs_path(chroma_conf.get("md5_hex_store", "vector_db/dynamic/md5.txt"))
        write_lock = threading.Lock()
        total_docs = 0

        def process_one_file(path: str) -> tuple[str, list[Document], str] | None:
            """单文件处理：读 MD5、JSON，转为 Document 列表，返回 (path, docs, md5_hex)，跳过则返回 None。"""
            md5_hex = get_file_md5_hex(path)
            if md5_hex is None:
                return None
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    return None
                docs = _post_json_to_documents(path, data)
                if not docs:
                    logger.debug("[动态向量库] 帖子无有效内容，跳过: %s", path)
                    return None
                return (path, docs, md5_hex)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("[动态向量库] 读取或解析失败 %s: %s", path, e)
                return None

        def add_to_store_and_save_md5(path: str, docs: list[Document], md5_hex: str) -> int:
            """写入向量库并保存 MD5；若已存在则跳过。返回本次写入的文档数（0 表示已跳过）。"""
            with write_lock:
                if check_md5_hex(md5_hex, md5_store_path):
                    logger.info("[动态向量库] 内容已存在知识库内，跳过: %s", path)
                    return 0
                split_docs = vs.spliter.split_documents(docs)
                if split_docs:
                    vs.vector_store.add_documents(split_docs)
                save_md5_hex(md5_hex, md5_store_path)
                logger.info(
                    "[动态向量库] 帖面向量化完成 | 文件=%s | 文档数=%d",
                    path,
                    len(split_docs),
                )
                return len(split_docs)

        logger.info(
            "[动态向量库] 共 %d 个文件，使用 %d 个线程",
            len(allowed_paths),
            max_workers,
        )
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_one_file, p): p for p in allowed_paths}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    path, docs, md5_hex = result
                    total_docs += add_to_store_and_save_md5(path, docs, md5_hex)

        if total_docs == 0:
            logger.warning("[动态向量库] 未生成任何文档，请检查路径下是否有帖子 JSON")
            return False

        global _dynamic_store_instance
        _dynamic_store_instance = vs
        logger.info("[动态向量库] 初始化成功，共写入 %d 条文档", total_docs)
        return True
    except Exception as e:
        logger.error("[动态向量库] 初始化失败：%s", e, exc_info=True)
        return False


_dynamic_store_instance: VectorStoreService | None = None


def get_dynamic_store(chroma_cfg: dict | None = None) -> VectorStoreService:
    """获取动态向量库服务实例；若未创建则使用 dynamic.json 创建（不自动加载数据）。"""
    global _dynamic_store_instance
    if _dynamic_store_instance is None:
        cfg = chroma_cfg or load_json_config(default_path=DYNAMIC_CHROMA_CONFIG_PATH)
        _dynamic_store_instance = VectorStoreService(chroma_cfg=cfg)
    return _dynamic_store_instance


def get_dynamic_vector_store(chroma_cfg: dict | None = None):
    """供外部调用的动态向量库（Chroma）实例，可直接用于 similarity_search、as_retriever 等。"""
    return get_dynamic_store(chroma_cfg=chroma_cfg).vector_store


def get_dynamic_retriever(chroma_cfg: dict | None = None):
    """供外部调用的动态向量库检索器。"""
    return get_dynamic_store(chroma_cfg=chroma_cfg).get_retriever()
