# -*- coding: utf-8 -*-
"""
查询工具 - 历史爬取帖子数据：根据 query 与版面从动态帖子向量库检索，返回对应版面的帖子信息文件。

入参：query — 查询文本；版面（section + board 或 board_path）。
回参：该版面下与 query 相关的帖子信息文件列表（source_file 等）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from knowledge.retrieval.hybrid_retriever import (
    dynamic_similarity_search_with_score,
    get_dynamic_vector_store_instance,
)
from utils.path_tool import get_abs_path


def _parse_board(section: str | None, board: str | None, board_path: str | None) -> tuple[str, str]:
    """
    解析版面：支持 (section, board) 或 board_path（如 "生活时尚/创意生活"）。
    :return: (section, board)
    """
    if section is not None and board is not None:
        return (section or "").strip(), (board or "").strip()
    if board_path:
        parts = [p.strip() for p in (board_path or "").replace("\\", "/").strip("/").split("/") if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[-1]
        if len(parts) == 1:
            return "", parts[0]
    return "", ""


def query_post_data(
    query: str,
    section: str | None = None,
    board: str | None = None,
    board_path: str | None = None,
    k: int = 20,
    include_content_preview: bool = False,
) -> list[dict]:
    """
    根据 query 与版面检索历史爬取的帖子，返回该版面下与 query 相关的帖子信息文件列表。

    :param query: 查询文本。
    :param section: 讨论区名称（与 board 二选一，或使用 board_path）。
    :param board: 版面名称。
    :param board_path: 版面路径，如 "生活时尚/创意生活"（会解析为 section=生活时尚, board=创意生活）。
    :param k: 最多返回的帖子条数。
    :param include_content_preview: 是否在结果中包含内容摘要（前 200 字）。
    :return: 列表，每项含 file（source_file）、title、author、url、date、content_preview（可选）等，按相关度排序，文件去重。
    """
    sec, bd = _parse_board(section, board, board_path)
    vs = get_dynamic_vector_store_instance()
    filter_dict: dict = {}
    if sec or bd:
        if sec:
            filter_dict["section"] = sec
        if bd:
            filter_dict["board"] = bd
    try:
        if filter_dict:
            pairs = vs.similarity_search_with_score(query, k=k * 2, filter=filter_dict)
        else:
            pairs = vs.similarity_search_with_score(query, k=k * 2)
    except Exception:
        pairs = []

    seen_files: set[str] = set()
    result: list[dict] = []
    for doc, score in pairs:
        meta = doc.metadata or {}
        path = meta.get("source_file") or meta.get("source") or ""
        if not path or path in seen_files:
            continue
        seen_files.add(path)
        item: dict = {
            "file": path,
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "url": meta.get("url", ""),
            "date": meta.get("date", ""),
            "reply_count": meta.get("reply_count", 0),
            "score": float(score),
        }
        if include_content_preview and doc.page_content:
            item["content_preview"] = (doc.page_content[:200] + "…") if len(doc.page_content) > 200 else doc.page_content
        result.append(item)
        if len(result) >= k:
            break

    return result


def query_post_data_files(
    query: str,
    section: str | None = None,
    board: str | None = None,
    board_path: str | None = None,
    k: int = 20,
    absolute_path: bool = False,
) -> list[str]:
    """
    根据 query 与版面检索帖子，仅返回对应帖子文件路径列表。

    :param query: 查询文本。
    :param section: 讨论区名称。
    :param board: 版面名称。
    :param board_path: 版面路径，如 "生活时尚/创意生活"。
    :param k: 最多返回文件数。
    :param absolute_path: 若 True，返回相对 data 的绝对路径。
    :return: 文件路径列表，去重、按相关度排序。
    """
    items = query_post_data(
        query,
        section=section,
        board=board,
        board_path=board_path,
        k=k,
        include_content_preview=False,
    )
    paths = [x["file"] for x in items]
    if absolute_path and paths:
        data_abs = get_abs_path("data")
        paths = [os.path.join(data_abs, p) if not os.path.isabs(p) else p for p in paths]
    return paths


if __name__ == "__main__":
    # 调试：按 query + 版面检索帖子并打印
    query = "游戏"
    board_path = "游戏对战/电脑游戏"
    print(f"[帖子数据] query = {query!r}, board_path = {board_path!r}")
    items = query_post_data(query, board_path=board_path, k=5, include_content_preview=True)
    print(f"命中 {len(items)} 条帖子:")
    for i, x in enumerate(items, 1):
        print(f"  [{i}] {x}")
    # 不限定版面时检索全部
    items_all = query_post_data(query, k=3)
    print(f"不限定版面时命中 {len(items_all)} 条帖子:")
    for i, x in enumerate(items_all, 1):
        print(f"  [{i}] {x}")
