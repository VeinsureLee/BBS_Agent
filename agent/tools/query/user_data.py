# -*- coding: utf-8 -*-
"""
查询工具 - 用户数据：根据 query 从用户向量库检索，返回对应的文件信息。

入参：query — 查询文本。
回参：与 query 相关的用户数据文件列表（含路径及可选摘要）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from knowledge.retrieval.memory_retriever import get_relevant_documents
from utils.path_tool import get_abs_path


def query_user_data(query: str, k: int = 10, include_content_preview: bool = False) -> list[dict]:
    """
    根据 query 检索用户上传/记忆数据，返回对应的文件列表。

    :param query: 查询文本。
    :param k: 最多返回的文档条数（每条可能来自同一文件的不同分片）。
    :param include_content_preview: 是否在结果中包含内容摘要（前 200 字）。
    :return: 列表，每项为 {"file": 相对或绝对路径, "content_preview": 可选}，按相关度排序，文件去重。
    """
    docs = get_relevant_documents(query)
    if not docs:
        return []

    # 按 source / source_file 去重，保留首次出现顺序（即更相关的在前）
    seen_files: set[str] = set()
    result: list[dict] = []
    for doc in docs[: k * 2]:  # 多取一些以便去重后仍有 k 个文件
        meta = doc.metadata or {}
        path = meta.get("source_file") or meta.get("source") or ""
        if not path or path in seen_files:
            continue
        seen_files.add(path)
        item: dict = {"file": path}
        if include_content_preview and doc.page_content:
            item["content_preview"] = (doc.page_content[:200] + "…") if len(doc.page_content) > 200 else doc.page_content
        result.append(item)
        if len(result) >= k:
            break

    return result


def query_user_data_files(query: str, k: int = 10, absolute_path: bool = False) -> list[str]:
    """
    根据 query 检索用户数据，仅返回对应文件路径列表（便于直接读文件）。

    :param query: 查询文本。
    :param k: 最多返回文件数。
    :param absolute_path: 若 True，返回相对项目 data 的绝对路径（基于 get_abs_path("data")）。
    :return: 文件路径列表，去重、按相关度排序。
    """
    items = query_user_data(query, k=k, include_content_preview=False)
    paths = [x["file"] for x in items]
    if absolute_path and paths:
        data_abs = get_abs_path("data")
        # 若当前 path 已是绝对路径则不再拼接
        paths = [os.path.join(data_abs, p) if not os.path.isabs(p) else p for p in paths]
    return paths


if __name__ == "__main__":
    # 调试：按 query 检索用户数据并打印文件与摘要
    query = "赛博理塘"
    print(f"[用户数据] query = {query!r}")
    items = query_user_data(query, k=5, include_content_preview=True)
    print(f"  命中 {len(items)} 个文件:")
    for i, x in enumerate(items, 1):
        print(f"  {i}. {x.get('file', '')}")
        if x.get("content_preview"):
            print(f"     摘要: {x['content_preview'][:80]}...")
    files_only = query_user_data_files(query, k=5)
    print(f"  仅路径: {files_only}")
