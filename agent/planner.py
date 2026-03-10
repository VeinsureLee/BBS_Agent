'''
Planner：Agent 的规划器，负责维护显式 to-do table，不再使用 prompt 生成任务。
Plan 时初始化 table；Replan 时根据 context 与原因更新 table（展开版面、追加爬取等）。
'''
import copy
from typing import List, Dict, Any, Callable, Optional

from utils.logger_handler import logger


# 默认 to-do table 模板（plan 后初始表）
DEFAULT_TODO_TABLE = [
    {"id": "1", "description": "调用已有用户上传数据"},
    {"id": "2", "description": "获取版面结构信息"},
    {"id": "3", "description": "获取版面帖子"},
    {"id": "4", "description": "在历史帖子不满足问题时，爬取指定版面的最近帖子"},
]

# 常用子集：仅版面结构 + 版面帖子（无用户数据、无爬取时使用）
DEFAULT_TODO_TABLE_CORE = [
    {"id": "2", "description": "获取版面结构信息"},
    {"id": "3", "description": "获取版面帖子"},
]


def _is_generic_board_post_row(task: dict) -> bool:
    """是否为未展开的「获取版面帖子」行（id=3 且无 board_path）。"""
    tid = task.get("id", "")
    desc = (task.get("description") or "").strip()
    return (tid == "3" or "版面帖子" in desc) and not task.get("board_path")


def _expand_board_post_row(boards: List[str]) -> List[dict]:
    """将「获取版面帖子」展开为按版面逐个搜寻的多行。"""
    rows = []
    for i, path in enumerate(boards, 1):
        path_str = path if isinstance(path, str) else str(path)
        rows.append({
            "id": f"3-{i}",
            "description": f"在版面（{path_str}）中搜寻与问题相关的帖子",
            "board_path": path_str,
        })
    return rows


def _make_crawl_rows(boards: List[str]) -> List[dict]:
    """生成「爬取版面 XXX」多行（id 4-1, 4-2, ...）。"""
    rows = []
    for i, path in enumerate(boards, 1):
        path_str = path if isinstance(path, str) else str(path)
        rows.append({
            "id": f"4-{i}",
            "description": f"爬取版面 {path_str} 的最近帖子",
            "board_path": path_str,
        })
    return rows


def update_todo_table(
    current_tasks: List[dict],
    context: Dict[str, Any],
    replan_reason: str,
) -> List[dict]:
    """
    根据当前剩余任务、上下文与 replan 原因，更新 to-do table（不调用 LLM）。
    - 若表头为「获取版面帖子」且 context 有 selected_boards：展开为「在版面 X 搜寻」多行。
    - 若当前表为空且原因含「不充分/不足」且有待爬取版面：追加「爬取版面 XXX」多行。
    - 若原因含「历史帖子不足/任务失败」且有待爬取版面：在表头前插入「爬取版面 XXX」多行。
    """
    reason = (replan_reason or "").strip()
    boards = context.get("selected_boards") or []
    tasks = list(current_tasks)

    # 1）表头为「获取版面帖子」且有待选版面 → 展开为按版面搜寻
    if tasks and boards:
        first = tasks[0]
        if _is_generic_board_post_row(first):
            tasks.pop(0)
            expanded = _expand_board_post_row(boards)
            tasks = expanded + tasks
            logger.info("[Planner] 更新 table：将「获取版面帖子」展开为 %s 个版面搜寻项", len(expanded))
            return tasks

    # 2）当前表为空且（回答不充分/不足）且有待选版面 → 追加爬取版面
    if not tasks and boards:
        if "不充分" in reason or "不足" in reason or "不足以回答" in reason:
            crawl_rows = _make_crawl_rows(boards)
            logger.info("[Planner] 更新 table：回答不充分，追加 %s 项爬取版面任务", len(crawl_rows))
            return crawl_rows

    # 3）原因含「历史帖子不足」或「任务失败」且有待选版面 → 表头前插入爬取任务
    if tasks and boards and ("历史帖子不足" in reason or "任务失败" in reason or "执行失败" in reason):
        crawl_rows = _make_crawl_rows(boards)
        tasks = crawl_rows + tasks
        logger.info("[Planner] 更新 table：插入 %s 项爬取版面任务", len(crawl_rows))
        return tasks

    return tasks


class Planner:
    """规划器：仅维护 to-do table，不调用 LLM。"""

    def __init__(self):
        self._todo_table: List[dict] = []

    def plan(self, user_input: str) -> List[dict]:
        """
        初始化 to-do table，不调用 prompt。
        返回默认表（与可选步骤一致），作为初始任务列表。
        """
        # 使用与原先一致的四步表，便于路由与展开
        self._todo_table = copy.deepcopy(DEFAULT_TODO_TABLE)
        logger.info("[Planner] plan 初始化 to-do table，共 %s 项（未使用 prompt）", len(self._todo_table))
        return list(self._todo_table)

    def replan(
        self,
        user_input: str,
        executed_summary: str,
        replan_reason: str,
        current_tasks: Optional[List[dict]] = None,
        get_context: Optional[Callable[[], dict]] = None,
    ) -> List[dict]:
        """
        根据当前剩余任务与上下文更新 to-do table，不调用 prompt。
        :param current_tasks: 当前剩余任务（即当前 table 的待执行部分）
        :param get_context: 用于获取 selected_boards 等
        :return: 更新后的任务列表（新 table）
        """
        tasks = list(current_tasks) if current_tasks is not None else []
        context = get_context() if callable(get_context) else {}
        updated = update_todo_table(tasks, context, replan_reason)
        self._todo_table = updated
        logger.info("[Planner] replan 更新 to-do table，共 %s 项（未使用 prompt）", len(updated))
        return updated

    def get_todo_table(self) -> List[dict]:
        """返回当前维护的 to-do table 副本。"""
        return list(self._todo_table) if self._todo_table else []
