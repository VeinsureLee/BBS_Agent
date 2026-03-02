"""
动态帖子向量库检索与混合检索封装：封装对 dynamic_store 的查询，并提供检索测试。
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from langchain_core.documents import Document

from knowledge.stores.dynamic_store import (
    get_dynamic_store,
    get_dynamic_vector_store,
    get_dynamic_retriever,
    init_dynamic_store,
)
from utils.logger_handler import logger


def get_dynamic_retriever_instance():
    """供外部调用的动态向量库检索器。"""
    return get_dynamic_retriever()


def get_dynamic_vector_store_instance():
    """供外部调用的动态向量库（Chroma）实例。"""
    return get_dynamic_vector_store()


def dynamic_similarity_search(query: str, k: int | None = None, **kwargs) -> list[Document]:
    """
    动态向量库相似度检索，返回最相似的 k 条文档。
    :param query: 查询文本
    :param k: 返回文档数量，为 None 时使用 store 配置的 k
    :param kwargs: 透传给 Chroma（如 filter）
    :return: Document 列表
    """
    vs = get_dynamic_vector_store()
    if k is None:
        k = get_dynamic_store().chroma_conf.get("k", 10)
    return vs.similarity_search(query, k=k, **kwargs)


def dynamic_similarity_search_with_score(
    query: str, k: int | None = None, **kwargs
) -> list[tuple[Document, float]]:
    """
    动态向量库相似度检索并返回分数（距离，越小越相似）。
    :param query: 查询文本
    :param k: 返回文档数量，为 None 时使用 store 配置的 k
    :param kwargs: 透传给 Chroma（如 filter）
    :return: [(Document, score), ...]
    """
    vs = get_dynamic_vector_store()
    if k is None:
        k = get_dynamic_store().chroma_conf.get("k", 10)
    return vs.similarity_search_with_score(query, k=k, **kwargs)


def dynamic_get_relevant_documents(query: str) -> list[Document]:
    """通过动态检索器获取与查询相关的文档（使用 store 配置的 k）。"""
    retriever = get_dynamic_retriever()
    return retriever.invoke(query)


if __name__ == "__main__":
    # 测试：使用 data/dynamic/生活时尚/创意生活 版面，先写入向量库（若未写入过），再查询并打印
    test_path = "data/dynamic/生活时尚/创意生活"
    success = init_dynamic_store(folder_path=test_path, max_workers=4)
    logger.info("动态向量库(写入): %s", "成功" if success else "跳过(已存在)或失败")

    query = "游戏挂"
    docs = dynamic_get_relevant_documents(query)
    print(f"检索「{query}」前 3 条:")
    for i, r in enumerate(docs[:3]):
        print(f"--- 结果 {i + 1} ---")
        text = r.page_content[:300]
        try:
            print(text)
        except UnicodeEncodeError:
            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            print(text.encode(enc, errors="replace").decode(enc))
        print("metadata:", r.metadata)
        print()
