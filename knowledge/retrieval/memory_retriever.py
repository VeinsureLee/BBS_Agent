"""
用户上传数据（记忆）向量库检索：封装对 usr_store 的相似度查询与检索器获取。

功能说明：
    - 提供对 usr_store（用户向量库）的检索入口；
    - 支持相似度检索（含/不含分数）、以及通过 Retriever 获取相关文档；
    - 供 Agent 或外部模块调用，用于用户上传/记忆类内容的 RAG 检索。
    本模块 __main__ 可调试：对指定查询返回最接近的文档及距离。

主要接口入参/出参：
    - get_memory_retriever() / get_memory_vector_store()
        入参：无。出参：用户向量库检索器或 Chroma 实例。
    - similarity_search(query: str, k: int = 4, **kwargs) -> list[Document]
        入参：query — 查询文本；k — 返回条数；kwargs — 透传 Chroma（如 filter）。
        出参：最相似的 k 条 Document 列表。
    - similarity_search_with_score(query, k=4, **kwargs) -> list[tuple[Document, float]]
        入参：同上。出参：[(Document, score), ...]，score 为距离（越小越相似）。
    - get_relevant_documents(query: str) -> list[Document]
        入参：query — 查询文本。出参：检索器返回的相关文档列表（使用 store 配置的 k）。
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
from langchain_core.documents import Document

from knowledge.stores.usr_store import (
    get_usr_vector_store,
    get_usr_vector_store_vector_store,
    get_usr_vector_store_retriever,
)


def get_memory_retriever():
    """供外部调用的用户向量库检索器。"""
    return get_usr_vector_store_retriever()


def get_memory_vector_store():
    """供外部调用的用户向量库（Chroma）实例。"""
    return get_usr_vector_store_vector_store()


def similarity_search(query: str, k: int = 4, **kwargs) -> list[Document]:
    """
    用户向量库相似度检索，返回最相似的 k 条文档。
    :param query: 查询文本
    :param k: 返回文档数量
    :param kwargs: 透传给 Chroma（如 filter）
    :return: Document 列表
    """
    vs = get_memory_vector_store()
    return vs.similarity_search(query, k=k, **kwargs)


def similarity_search_with_score(query: str, k: int = 4, **kwargs) -> list[tuple[Document, float]]:
    """
    用户向量库相似度检索并返回分数（距离，越小越相似）。
    :param query: 查询文本
    :param k: 返回文档数量
    :param kwargs: 透传给 Chroma（如 filter）
    :return: [(Document, score), ...]
    """
    vs = get_memory_vector_store()
    return vs.similarity_search_with_score(query, k=k, **kwargs)


def get_relevant_documents(query: str) -> list[Document]:
    """通过检索器获取与查询相关的文档（使用 store 配置的 k）。"""
    retriever = get_memory_retriever()
    return retriever.invoke(query)


if __name__ == "__main__":
    # 调试：返回与「赛博理塘」最接近的文档
    query = "赛博理塘"
    pairs = similarity_search_with_score(query, k=5)
    print(f"[用户向量库] 与「{query}」最接近的文档：")
    for i, (doc, score) in enumerate(pairs, 1):
        content = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
        print(f"--- 第 {i} 名 | 距离={score:.4f} ---")
        print("  ", content)
        if doc.metadata:
            print("  metadata:", doc.metadata)
        print()
