"""
knowledge.retrieval 子包：对动态帖、结构、用户三套向量库的检索封装。

功能说明：
    - 动态帖检索（hybrid_retriever）：对 dynamic_store 的相似度检索与 Retriever 获取；
      get_dynamic_retriever_instance、get_dynamic_vector_store_instance、
      dynamic_similarity_search、dynamic_similarity_search_with_score、dynamic_get_relevant_documents。
    - 结构检索（structure_retriever）：按版面信息/多维度检索最相似版面，支持单条/多条条件与聚合策略；
      get_structure_retriever、get_structure_vector_store、similarity_search、similarity_search_with_score、get_relevant_documents；
      query_boards_by_board_info、query_boards_by_multi_board_info、query_by_field_similarity、query_by_field_avg_similarity。
    - 用户/记忆检索（memory_retriever）：对 usr_store 的相似度检索与 Retriever 获取；
      get_memory_retriever、get_memory_vector_store、similarity_search、similarity_search_with_score、get_relevant_documents。
    入参/出参详见各模块文件头注释。

主要接口入参/出参摘要：
    - dynamic_similarity_search(query, k?, **kwargs) -> list[Document]
    - dynamic_get_relevant_documents(query) -> list[Document]
    - structure: similarity_search(query, k=4, **kwargs) -> list[Document]
    - structure: query_boards_by_board_info(board_info, top_k=5, ...) -> list[(hierarchy_path, board_name, sim, docs)]
    - structure: query_boards_by_multi_board_info(board_info_list, ...) -> list[(path, board_name, combined_sim, per_criterion)]
    - memory: similarity_search(query, k=4, **kwargs) -> list[Document]
    - memory: get_relevant_documents(query) -> list[Document]
"""

from .hybrid_retriever import (
    get_dynamic_retriever_instance,
    get_dynamic_vector_store_instance,
    dynamic_similarity_search,
    dynamic_similarity_search_with_score,
    dynamic_get_relevant_documents,
)
from knowledge.stores.dynamic_store import init_dynamic_store
from .structure_retriever import (
    get_structure_retriever,
    get_structure_vector_store,
    similarity_search as structure_similarity_search,
    similarity_search_with_score as structure_similarity_search_with_score,
    get_relevant_documents as structure_get_relevant_documents,
    query_boards_by_board_info,
    query_boards_by_multi_board_info,
    query_by_field_similarity,
    query_by_field_avg_similarity,
)
from .memory_retriever import (
    get_memory_retriever,
    get_memory_vector_store,
    similarity_search as memory_similarity_search,
    similarity_search_with_score as memory_similarity_search_with_score,
    get_relevant_documents as memory_get_relevant_documents,
)

__all__ = [
    "get_dynamic_retriever_instance",
    "get_dynamic_vector_store_instance",
    "dynamic_similarity_search",
    "dynamic_similarity_search_with_score",
    "dynamic_get_relevant_documents",
    "init_dynamic_store",
    "get_structure_retriever",
    "get_structure_vector_store",
    "structure_similarity_search",
    "structure_similarity_search_with_score",
    "structure_get_relevant_documents",
    "query_boards_by_board_info",
    "query_boards_by_multi_board_info",
    "query_by_field_similarity",
    "query_by_field_avg_similarity",
    "get_memory_retriever",
    "get_memory_vector_store",
    "memory_similarity_search",
    "memory_similarity_search_with_score",
    "memory_get_relevant_documents",
]