# -*- coding: utf-8 -*-
"""
查询工具 - 网站信息数据：根据 query 从结构向量库检索，返回对应的版面信息。

入参：query — 查询文本（版面描述或关键词）。
回参：与 query 最匹配的版面列表（hierarchy_path、board_name、相似度等）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from knowledge.retrieval.structure_retriever import (
    query_boards_by_board_info,
    get_relevant_documents,
)


def query_structure_boards(
    query: str,
    top_k: int = 10,
    include_docs: bool = False,
) -> list[dict]:
    """
    根据 query（版面描述或关键词）检索网站结构，返回最匹配的版面列表。

    :param query: 查询文本，如「发言规则：允许匿名」或「交流讨论」。
    :param top_k: 返回的版面数量。
    :param include_docs: 是否在结果中包含该版面下的检索文档列表（用于 RAG 等）。
    :return: 列表，每项含 hierarchy_path、board_name、similarity、可选 docs。
    """
    ranked = query_boards_by_board_info(
        board_info=query,
        top_k=top_k,
        k_per_collection=500,
        board_score_aggregation="max",
    )
    result: list[dict] = []
    for hierarchy_path, board_name, similarity, docs in ranked:
        item: dict = {
            "hierarchy_path": hierarchy_path,
            "board_name": board_name,
            "similarity": float(similarity),
        }
        if include_docs and docs:
            item["docs"] = [
                {"content": d.page_content[:300] if d.page_content else "", "metadata": d.metadata or {}}
                for d in docs[:5]
            ]
        result.append(item)
    return result


def query_structure_boards_simple(query: str, top_k: int = 10) -> list[str]:
    """
    根据 query 检索版面，仅返回版面路径列表（hierarchy_path），便于下游按版面操作。

    :param query: 查询文本。
    :param top_k: 返回的版面数量。
    :return: hierarchy_path 列表，按相似度降序。
    """
    items = query_structure_boards(query, top_k=top_k, include_docs=False)
    return [x["hierarchy_path"] for x in items if x.get("hierarchy_path")]


def query_structure_documents(query: str, k: int = 10) -> list[dict]:
    """
    根据 query 从结构向量库做普通相似度检索，返回相关文档（不按版面聚合）。
    适用于「任意版面信息片段」的检索。

    :param query: 查询文本。
    :param k: 返回文档条数。
    :return: 列表，每项含 content、metadata（含 hierarchy_path、board_name 等）。
    """
    docs = get_relevant_documents(query)
    result: list[dict] = []
    for doc in docs[:k]:
        meta = doc.metadata or {}
        result.append({
            "content": doc.page_content or "",
            "metadata": meta,
            "hierarchy_path": meta.get("hierarchy_path", ""),
            "board_name": meta.get("board_name", ""),
        })
    return result


if __name__ == "__main__":
    # 调试：按 query 检索版面并打印
    query = "发言规则：允许匿名"
    print(f"[网站信息] query = {query!r}")
    boards = query_structure_boards(query, top_k=5, include_docs=False)
    print(f"  命中 {len(boards)} 个版面:")
    for i, x in enumerate(boards, 1):
        print(f"  {i}. {x.get('board_name')} ({x.get('hierarchy_path')}) similarity={x.get('similarity')}")
    paths = query_structure_boards_simple(query, top_k=3)
    print(f"  仅路径: {paths}")
    docs = query_structure_documents("交流讨论", k=2)
    print(f"  query_structure_documents('交流讨论', k=2): {len(docs)} 条")
