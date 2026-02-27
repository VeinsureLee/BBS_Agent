"""
BBS 查询工具：基于 data 下文档与 config 下版面信息的查询。
供 Agent 查询论坛知识库（RAG）、版面结构、版面介绍与用户资料。

数据来源：
- 版面结构：config/web_structure/board 目录下的 board.json（所属讨论区，名称，url）
- 版面介绍：data/boards_guide 下各版面的 JSON（发言规则，帖子类型等）
- 用户资料：data/bbs_info 目录下的 pdf、txt、json 文件
- 知识库：vector_db/chroma_db 向量库，用于语义检索与总结

模块功能：
1、bbs_structure_query：查询版面结构信息，返回版面结构信息（所属讨论区，名称，url）
2、bbs_introduction_query：查询版面介绍信息，返回版面介绍信息（发言规则，帖子类型等）
3、bbs_user_files_query：查询用户自带的资料文件，返回用户自带的资料文件（pdf，txt，json文件）
4、bbs_rag_query：查询知识库，返回知识库信息（根据问题检索参考资料并总结回答，适用于论坛内容、版面讨论等语义查询）
"""
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger_handler import logger
from utils.path_tool import get_abs_path
from utils.config_handler import load_chroma_config, load_web_structure_board_config
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


def _get_boards_guide_root() -> str:
    """返回 data/boards_guide 的绝对路径。"""
    return get_abs_path("data/boards_guide")


def _get_bbs_info_root() -> str:
    """返回用户资料目录 data/bbs_info 的绝对路径（优先从 chroma 的 info_path 读取）。"""
    cfg = load_chroma_config()
    info_cfg = cfg.get("info_path") if isinstance(cfg.get("info_path"), dict) else None
    if info_cfg and info_cfg.get("path"):
        return get_abs_path(info_cfg["path"])
    return get_abs_path("data/bbs_info")


# ---------------------------------------------------------------------------
# 1. 版面结构查询
# ---------------------------------------------------------------------------

@tool(description="查询 BBS 版面结构信息，返回讨论区与版面的所属关系、名称及 URL（所属讨论区，名称，url）")
def bbs_structure_query(section_name: str = "") -> str:
    """
    从 config/web_structure/board 的 board.json 读取版面结构。
    - section_name: 可选，仅返回该讨论区下的版面；留空则返回全部。
    返回格式化的讨论区与版面列表（讨论区名、版面名、url）。
    """
    try:
        board_cfg = load_web_structure_board_config()
    except Exception as e:
        logger.warning(f"[query_tools] 读取版面结构失败: {e}")
        return "当前无法读取版面结构（请先执行 BBS 初始化以生成 config/web_structure/board 下的配置）。"

    sections = board_cfg.get("sections") or []
    if not sections:
        return "版面结构为空，请先执行 BBS 初始化。"

    section_filter = (section_name or "").strip()
    lines = ["【版面结构】讨论区 | 版面名称 | URL"]

    for sec in sections:
        sec_name = (sec.get("name") or "").strip() or "未命名讨论区"
        if section_filter and sec_name != section_filter:
            continue
        sec_url = (sec.get("url") or "").strip()
        boards = sec.get("boards") or []
        for b in boards:
            board_name = (b.get("name") or "").strip() or "未命名版面"
            board_url = (b.get("url") or "").strip()
            lines.append(f"  {sec_name} | {board_name} | {board_url}")
        if not boards:
            lines.append(f"  {sec_name} | （无下属版面） | {sec_url}")

    if len(lines) == 1:
        return "未找到符合条件的版面结构。"
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. 版面介绍查询
# ---------------------------------------------------------------------------

@tool(description="查询版面介绍信息，返回各版面的发言规则、帖子类型等（发言规则，帖子类型等）")
def bbs_introduction_query(section_name: str = "", board_name: str = "") -> str:
    """
    从 data/boards_guide 下各版面的 JSON 读取介绍（发言规则、帖子类型）。
    - section_name: 可选，按讨论区过滤。
    - board_name: 可选，按版面名过滤。
    留空表示不限制，返回全部版面介绍。
    """
    root = _get_boards_guide_root()
    if not os.path.isdir(root):
        logger.warning(f"[query_tools] 版面介绍目录不存在: {root}")
        return "当前没有版面介绍数据（请先执行 BBS 初始化以生成 data/boards_guide）。"

    section_filter = (section_name or "").strip()
    board_filter = (board_name or "").strip()
    lines = ["【版面介绍】讨论区 | 版面 | 发言规则 | 帖子类型"]

    for sec_dir in os.listdir(root):
        sec_path = os.path.join(root, sec_dir)
        if not os.path.isdir(sec_path):
            continue
        for fname in os.listdir(sec_path):
            if not fname.endswith(".json"):
                continue
            abs_path = os.path.join(sec_path, fname)
            if not os.path.isfile(abs_path):
                continue
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.debug(f"[query_tools] 读取 {abs_path} 失败: {e}")
                continue
            sec_label = (data.get("section_name") or "").strip() or sec_dir
            board_label = (data.get("board_name") or "").strip() or fname.replace(".json", "")
            if section_filter and sec_label != section_filter:
                continue
            if board_filter and board_label != board_filter:
                continue
            rules = (data.get("rules") or "").strip() or "常规发帖，需遵守版规。"
            post_type = (data.get("post_type") or "").strip() or f"与「{board_label}」主题相关的讨论与信息。"
            lines.append(f"  {sec_label} | {board_label} | {rules[:80]}{'…' if len(rules) > 80 else ''} | {post_type[:80]}{'…' if len(post_type) > 80 else ''}")

    if len(lines) == 1:
        return "未找到符合条件的版面介绍。"
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. 用户资料文件查询
# ---------------------------------------------------------------------------

@tool(description="查询用户自带的资料文件列表，返回 data/bbs_info 下的 pdf、txt、json 文件")
def bbs_user_files_query() -> str:
    """
    列出用户资料目录（默认 data/bbs_info）下所有允许类型的文件（pdf、txt、json）。
    返回文件相对路径列表，便于 Agent 了解用户已添加的资料。
    """
    root = _get_bbs_info_root()
    if not os.path.isdir(root):
        logger.warning(f"[query_tools] 用户资料目录不存在: {root}")
        return "当前没有用户资料目录或目录为空（可将 pdf、txt、json 放入 data/bbs_info）。"

    allowed = (".pdf", ".txt", ".json")
    files = list_allowed_files_recursive(root, allowed)
    if not files:
        return "用户资料目录下暂无 pdf、txt、json 文件。"

    data_abs = get_abs_path("data")
    lines = ["【用户资料文件】"]
    for path in sorted(files):
        try:
            rel = os.path.relpath(path, data_abs).replace("\\", "/")
        except ValueError:
            rel = path
        lines.append(f"  - {rel}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. 知识库 RAG 查询
# ---------------------------------------------------------------------------

@tool(description="从 BBS 知识库（向量库）中根据问题检索参考资料并总结回答，适用于论坛内容、版面讨论等语义查询")
def bbs_rag_query(query: str) -> str:
    """根据问题检索知识库并总结回答。"""
    return _get_rag_service().rag_summarize(query)
