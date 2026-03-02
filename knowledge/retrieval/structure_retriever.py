"""
论坛结构向量库检索：封装对 structure_store 的查询，包括按版面相似度等。
支持「最佳匹配」聚合：版面内取与查询最相关的若干条计算得分，避免无关条目拉低相似度。
"""
import sys
import os
from typing import Literal

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from langchain_core.documents import Document

from knowledge.stores.structure_store import (
    get_static_structure_store,
    get_static_structure_vector_store,
    get_static_structure_retriever,
)
from utils.dimension_config import get_field_label_map


def get_structure_retriever():
    """供外部调用的结构向量库检索器。"""
    return get_static_structure_retriever()


def get_structure_vector_store():
    """供外部调用的结构向量库（Chroma）实例。"""
    return get_static_structure_vector_store()


def similarity_search(query: str, k: int = 4, **kwargs) -> list[Document]:
    """
    结构向量库相似度检索，返回最相似的 k 条文档。
    :param query: 查询文本
    :param k: 返回文档数量
    :param kwargs: 透传给 Chroma（如 filter）
    :return: Document 列表
    """
    vs = get_structure_vector_store()
    return vs.similarity_search(query, k=k, **kwargs)


def similarity_search_with_score(query: str, k: int = 4, **kwargs) -> list[tuple[Document, float]]:
    """
    结构向量库相似度检索并返回分数（距离，越小越相似）。
    :param query: 查询文本
    :param k: 返回文档数量
    :param kwargs: 透传给 Chroma（如 filter）
    :return: [(Document, score), ...]
    """
    vs = get_structure_vector_store()
    return vs.similarity_search_with_score(query, k=k, **kwargs)


def get_relevant_documents(query: str) -> list[Document]:
    """通过检索器获取与查询相关的文档（使用 store 配置的 k）。"""
    retriever = get_structure_retriever()
    return retriever.invoke(query)


def _parse_board_info_to_field_and_query(board_info: str) -> tuple[str | None, str]:
    """
    从「版面信息」中解析出可选维度字段与查询文本。
    例如 "发言规则：允许匿名" -> (speech_rules, "允许匿名")，未匹配到标签时 -> (None, 全文)。
    """
    board_info = (board_info or "").strip()
    if not board_info:
        return None, ""
    label_to_key = {v: k for k, v in get_field_label_map().items()}
    if "：" in board_info:
        label, rest = board_info.split("：", 1)
        label = label.strip()
        rest = rest.strip()
        if label and label in label_to_key:
            return label_to_key[label], rest or board_info
    return None, board_info


def query_boards_by_board_info(
    board_info: str,
    top_k: int = 5,
    k_per_collection: int = 500,
    vector_store=None,
    board_score_aggregation: Literal["avg", "max", "top_k_avg"] = "max",
    top_k_for_avg: int = 3,
) -> list[tuple[str, str, float, list]]:
    """
    根据给出的版面信息（如「发言规则：允许匿名」）检索最相似的版面，按相似度降序返回。
    默认使用「最佳匹配」：版面内只要有一条与描述高度一致即得高分，避免无关条目拉低整体相似度。
    :param board_info: 版面描述，可带维度标签如「发言规则：允许匿名」
    :param top_k: 返回的版面数量
    :param k_per_collection: 内部检索时每维度/全局取回的文档数上限
    :param vector_store: Chroma 实例，为 None 时使用默认结构向量库
    :param board_score_aggregation: 版面内多条条目聚合成一个分数的方式，默认 "max"（取最佳匹配）
    :param top_k_for_avg: aggregation 为 "top_k_avg" 时使用的 k
    :return: [(hierarchy_path, board_name, similarity, docs), ...]，similarity 越大越相似
    """
    field_name, query_text = _parse_board_info_to_field_and_query(board_info)
    vs = vector_store or get_structure_vector_store()

    if field_name and query_text:
        ranked = query_by_field_similarity(
            query_text,
            field_name=field_name,
            k_per_collection=k_per_collection,
            vector_store=vs,
            board_score_aggregation=board_score_aggregation,
            top_k_for_avg=top_k_for_avg,
        )
    else:
        pairs = vs.similarity_search_with_score(
            query_text or board_info,
            k=k_per_collection,
        )
        by_board: dict[str, tuple[list[float], list]] = {}
        for doc, score in pairs:
            path = (doc.metadata or {}).get("hierarchy_path") or ""
            if path not in by_board:
                by_board[path] = ([], [])
            by_board[path][0].append(score)
            by_board[path][1].append(doc)
        ranked = []
        for path, (scores, docs) in by_board.items():
            if not scores:
                continue
            sim = _board_similarity_from_scores(
                scores,
                aggregation=board_score_aggregation,
                top_k_for_avg=top_k_for_avg,
            )
            ranked.append((path, sim, docs))
        ranked.sort(key=lambda x: -x[1])

    result = []
    for path, sim, docs in ranked[:top_k]:
        board_name = (
            (docs[0].metadata or {}).get("board_name")
            if docs
            else (path.split("/")[-1] if path else path)
        )
        result.append((path, board_name or path, sim, docs))
    return result


def query_boards_by_multi_board_info(
    board_info_list: list[str],
    top_k: int = 5,
    k_per_collection: int = 500,
    vector_store=None,
    board_score_aggregation: Literal["avg", "max", "top_k_avg"] = "max",
    top_k_for_avg: int = 3,
    multi_criterion_aggregation: Literal["avg", "min"] = "avg",
) -> list[tuple[str, str, float, dict[str, float]]]:
    """
    根据给出的多条版面信息（如 ["发言规则：允许匿名", "版面定位：交流讨论"]）检索最相似的版面。
    每条信息单独做维度检索并得到版面排序，再按版面合并：每个版面在各条标准上的得分做 avg 或 min，
    得到综合相似度后排序。min 更偏「每条都要满足」，avg 更偏「总体匹配度」。
    :param board_info_list: 多条版面描述
    :param top_k: 返回的版面数量
    :param k_per_collection: 内部检索文档数上限
    :param vector_store: Chroma 实例
    :param board_score_aggregation: 单条标准下版面内条目的聚合方式
    :param top_k_for_avg: 单条标准下 top_k_avg 的 k
    :param multi_criterion_aggregation: 多标准间合并方式。"avg" 各标准得分平均；"min" 取最低分（短板）
    :return: [(hierarchy_path, board_name, combined_similarity, per_criterion_scores), ...]
             per_criterion_scores 为 {board_info: score} 便于解释
    """
    board_info_list = [s.strip() for s in board_info_list if (s or "").strip()]
    if not board_info_list:
        return []

    vs = vector_store or get_structure_vector_store()
    # 每个版面 path -> (board_name, list of (criterion, score))
    board_scores: dict[str, tuple[str, dict[str, float]]] = {}

    def add_scores(ranked: list[tuple[str, float, list]], criterion: str) -> None:
        for path, sim, docs in ranked:
            board_name = (
                (docs[0].metadata or {}).get("board_name")
                if docs
                else (path.split("/")[-1] if path else path)
            )
            if path not in board_scores:
                board_scores[path] = (board_name or path, {})
            board_scores[path][1][criterion] = sim

    for info in board_info_list:
        field_name, query_text = _parse_board_info_to_field_and_query(info)
        if field_name and query_text:
            ranked = query_by_field_similarity(
                query_text,
                field_name=field_name,
                k_per_collection=k_per_collection,
                vector_store=vs,
                board_score_aggregation=board_score_aggregation,
                top_k_for_avg=top_k_for_avg,
            )
        else:
            pairs = vs.similarity_search_with_score(
                query_text or info,
                k=k_per_collection,
            )
            by_board: dict[str, tuple[list[float], list]] = {}
            for doc, score in pairs:
                path = (doc.metadata or {}).get("hierarchy_path") or ""
                if path not in by_board:
                    by_board[path] = ([], [])
                by_board[path][0].append(score)
                by_board[path][1].append(doc)
            ranked = []
            for path, (scores, docs) in by_board.items():
                if not scores:
                    continue
                sim = _board_similarity_from_scores(
                    scores,
                    aggregation=board_score_aggregation,
                    top_k_for_avg=top_k_for_avg,
                )
                ranked.append((path, sim, docs))
        add_scores(ranked, info)

    combined = []
    for path, (board_name, per_criterion) in board_scores.items():
        if multi_criterion_aggregation == "min":
            comb = min(per_criterion.values()) if per_criterion else -float("inf")
        else:
            comb = sum(per_criterion.values()) / len(per_criterion) if per_criterion else -float("inf")
        combined.append((path, board_name, comb, per_criterion))
    combined.sort(key=lambda x: -x[2])
    return combined[:top_k]


def _board_similarity_from_scores(
    scores: list[float],
    aggregation: Literal["avg", "max", "top_k_avg"],
    top_k_for_avg: int = 3,
) -> float:
    """
    根据版面内多条条目的距离列表，按策略计算版面整体相似度。
    Chroma 返回的 score 为距离，越小越相似；返回值为相似度（越大越相似）。
    - avg: 所有条目的平均距离取反，无关条目会拉低得分。
    - max: 取最佳匹配条目的相似度，只要有一条明确匹配即得高分。
    - top_k_avg: 取相似度最高的 top_k 条的平均，兼顾「有匹配」与「匹配条数」。
    """
    if not scores:
        return -float("inf")
    # 距离升序 = 越相似的在前面
    sorted_distances = sorted(scores)
    if aggregation == "max":
        return -sorted_distances[0]
    if aggregation == "top_k_avg":
        k = min(top_k_for_avg, len(sorted_distances))
        return -sum(sorted_distances[:k]) / k
    # avg
    return -sum(scores) / len(scores)


def query_by_field_similarity(
    query_text: str,
    field_name: str = "speech_rules",
    k_per_collection: int = 500,
    vector_store=None,
    board_score_aggregation: Literal["avg", "max", "top_k_avg"] = "max",
    top_k_for_avg: int = 3,
) -> list[tuple[str, float, list]]:
    """
    在指定维度（如发言规则）中，按「版面」聚合，计算查询与每个版面的相似度并排序。
    默认使用「最佳匹配」聚合：版面得分取该版面内与查询最相似的一条，避免无关条目拉低得分
    （例如版面有多条发言规则，仅一条写「允许匿名」时仍能获得高相似度）。
    :param query_text: 查询文本（如「允许匿名」）
    :param field_name: 维度字段名
    :param k_per_collection: 最多取回的文档数
    :param vector_store: Chroma 实例，为 None 时使用默认结构向量库
    :param board_score_aggregation: 版面内多条条目如何聚合成一个分数。"avg" 全量平均；"max" 取最佳匹配；"top_k_avg" 取最相似 top_k 条平均
    :param top_k_for_avg: board_score_aggregation="top_k_avg" 时使用的 k
    :return: [(hierarchy_path, similarity, [doc, ...]), ...]，similarity 越大越相似
    """
    vs = vector_store or get_structure_vector_store()
    pairs = vs.similarity_search_with_score(
        query_text,
        k=k_per_collection,
        filter={"field_name": field_name},
    )
    by_board: dict[str, tuple[list[float], list]] = {}
    for doc, score in pairs:
        path = (doc.metadata or {}).get("hierarchy_path") or ""
        if path not in by_board:
            by_board[path] = ([], [])
        by_board[path][0].append(score)
        by_board[path][1].append(doc)
    result = []
    for path, (scores, docs) in by_board.items():
        if not scores:
            continue
        sim = _board_similarity_from_scores(
            scores, aggregation=board_score_aggregation, top_k_for_avg=top_k_for_avg
        )
        result.append((path, sim, docs))
    result.sort(key=lambda x: -x[1])
    return result


def query_by_field_avg_similarity(
    query_text: str,
    field_name: str = "speech_rules",
    k_per_collection: int = 500,
    vector_store=None,
) -> list[tuple[str, float, list]]:
    """
    在指定维度中按版面聚合，使用「全量平均」相似度（保留旧接口兼容）。
    更推荐使用 query_by_field_similarity(..., board_score_aggregation="max") 以获得更贴合「明确匹配」的排序。
    """
    return query_by_field_similarity(
        query_text,
        field_name=field_name,
        k_per_collection=k_per_collection,
        vector_store=vector_store,
        board_score_aggregation="avg",
    )


if __name__ == "__main__":
    # 单条版面信息 + 最佳匹配算法（明确写「允许匿名」的版面会排前面）
    board_info = "发言规则：允许匿名"
    boards = query_boards_by_board_info(
        board_info, top_k=10, k_per_collection=3000, board_score_aggregation="max"
    )
    print(f"[结构向量库] 版面信息「{board_info}」→ 最相似的版面（聚合方式=最佳匹配）：")
    for i, (hierarchy_path, board_name, sim, docs) in enumerate(boards, 1):
        print(f"  {i}. {board_name}（{hierarchy_path}） 相似度={sim:.4f}")
    # 多条版面信息综合排序
    multi_info = ["发言规则：允许匿名", "版面定位：交流讨论"]
    multi_boards = query_boards_by_multi_board_info(
        multi_info, top_k=10, k_per_collection=3000, multi_criterion_aggregation="avg"
    )
    print("\n[结构向量库] 多条信息综合 → 最相似的版面：")
    for i, (path, board_name, comb, per_criterion) in enumerate(multi_boards, 1):
        print(f"  {i}. {board_name} 综合={comb:.4f} 各条={per_criterion}")
