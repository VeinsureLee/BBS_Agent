"""
BBS 查询工具：基于 data 下文档与爬取版面信息的查询。
供 Agent 查询论坛知识库（RAG）与版面帖子列表。
"""
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger_handler import logger
from utils.path_tool import get_abs_path
from utils.config_handler import load_chroma_config
from utils import list_allowed_files_recursive
from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService

# 与 agent_tools 一致：单例 RAG 服务
_rag_service: RagSummarizeService | None = None


def _get_rag_service() -> RagSummarizeService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RagSummarizeService()
    return _rag_service


def _get_data_path() -> str:
    """获取 data 目录绝对路径（与向量库配置一致）。"""
    cfg = load_chroma_config()
    return get_abs_path(cfg["data_path"])


def _collect_board_json_paths() -> list[str]:
    """收集 data 下所有版面爬取 JSON 路径。"""
    data_abs = _get_data_path()
    if not os.path.isdir(data_abs):
        logger.warning(f"[query_tools] data 目录不存在: {data_abs}")
        return []
    return list_allowed_files_recursive(data_abs, (".json",))


def _load_board_file(filepath: str) -> dict | None:
    """加载单份版面 JSON，返回 None 表示非版面格式或读取出错。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.debug(f"[query_tools] 读取 {filepath} 失败: {e}")
        return None
    if not isinstance(data.get("posts"), list):
        return None
    return data


@tool(description="从 BBS 知识库（向量库）中根据问题检索参考资料并总结回答，适用于论坛内容、版面讨论等语义查询")
def bbs_rag_query(query: str) -> str:
    """基于 data 下已入库文档的 RAG 检索与总结。"""
    return _get_rag_service().rag_summarize(query)


@tool(
    description="根据分区名、版面名、日期或标题关键词，从 data 下已爬取的版面 JSON 中查询帖子列表。"
    " section/board/date 可留空表示不限制；keyword 为标题包含的关键词；max_posts 限制返回条数，默认 20。"
)
def query_board_posts(
    section: str = "",
    board: str = "",
    date: str = "",
    keyword: str = "",
    max_posts: int = 20,
) -> str:
    """
    从 data 下爬取的版面信息文件中查询帖子。
    - section: 分区名（如「生活时尚」）
    - board: 版面名（如「悄悄话」）
    - date: 日期，格式 YYYY-MM-DD（如 2026-02-25）
    - keyword: 标题包含的关键词
    - max_posts: 最多返回帖子条数
    返回格式化的帖子列表字符串，便于后续回答。
    """
    paths = _collect_board_json_paths()
    if not paths:
        return "当前没有可用的版面爬取数据（data 下未找到 JSON 文件）。"

    section = (section or "").strip()
    board = (board or "").strip()
    date = (date or "").strip()
    keyword = (keyword or "").strip()
    max_posts = max(1, min(200, max_posts))

    collected: list[dict] = []
    data_abs = _get_data_path()

    for path in paths:
        rel = os.path.relpath(path, data_abs).replace("\\", "/")
        # data/分区/版面/日期.json -> 用于过滤
        parts = rel.replace(".json", "").split("/")
        if len(parts) < 3:
            continue
        file_section, file_board, file_date = parts[0], parts[1], parts[2]
        if section and file_section != section:
            continue
        if board and file_board != board:
            continue
        if date and file_date != date:
            continue

        data = _load_board_file(path)
        if not data:
            continue
        posts = data.get("posts") or []
        for p in posts:
            title = (p.get("title") or "").strip()
            if keyword and keyword not in title:
                continue
            collected.append({
                "section": file_section,
                "board": file_board,
                "date": file_date,
                "title": title,
                "author": p.get("author", ""),
                "time": p.get("time", ""),
                "reply_count": p.get("reply_count", 0),
                "url": p.get("url", ""),
            })
        if len(collected) >= max_posts:
            break

    collected = collected[:max_posts]
    if not collected:
        return "未找到符合条件的帖子。可尝试放宽分区、版面、日期或关键词条件，或先调用 list_crawled_boards 查看已有数据。"

    lines = []
    for i, p in enumerate(collected, 1):
        lines.append(
            f"{i}. 【{p['section']} / {p['board']}】{p['date']} | {p['title']} | 作者:{p['author']} 回复:{p['reply_count']} 链接:{p['url']}"
        )
    return "\n".join(lines)


@tool(description="列出 data 下已爬取的分区与版面列表，以及各版面下已有日期样例，便于后续按分区/版面/日期查询")
def list_crawled_boards() -> str:
    """列出当前 data 下已爬取的版面信息对应的分区、版面及日期。"""
    paths = _collect_board_json_paths()
    if not paths:
        return "当前没有可用的版面爬取数据（data 下未找到 JSON 文件）。"

    data_abs = _get_data_path()
    # rel_path: data/分区/版面/日期.json
    section_board_dates: dict[tuple[str, str], list[str]] = {}

    for path in paths:
        rel = os.path.relpath(path, data_abs).replace("\\", "/")
        parts = rel.replace(".json", "").split("/")
        if len(parts) < 3:
            continue
        sec, bd, dt = parts[0], parts[1], parts[2]
        key = (sec, bd)
        if key not in section_board_dates:
            section_board_dates[key] = []
        if dt not in section_board_dates[key]:
            section_board_dates[key].append(dt)

    for k in section_board_dates:
        section_board_dates[k].sort()

    lines = ["已爬取版面（分区 / 版面 -> 日期列表）："]
    for (sec, bd), dates in sorted(section_board_dates.items()):
        sample = ", ".join(dates[:5])
        if len(dates) > 5:
            sample += f" 等共 {len(dates)} 天"
        lines.append(f"  - {sec} / {bd}: {sample}")
    return "\n".join(lines)
