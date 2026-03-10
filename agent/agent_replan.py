'''
Agent Replan：根据当前 to-do table 与 context 更新 table，不调用 prompt。
由 Task Agent 在遇阻或回答不充分时触发，Planner 仅做 table 规则更新。
'''
from typing import List, Dict, Callable, Optional

from agent.planner import Planner


def run_replan(
    user_input: str,
    executed_summary: str,
    replan_reason: str,
    planner: Planner | None = None,
    current_tasks: Optional[List[dict]] = None,
    get_context: Optional[Callable[[], dict]] = None,
) -> List[dict]:
    """
    根据当前剩余任务与上下文更新 to-do table（不调用 LLM）。
    :param user_input: 用户原始目标（保留参数，表更新逻辑不依赖）
    :param executed_summary: 已执行摘要（保留参数，表更新逻辑不依赖）
    :param replan_reason: 受阻或需调整的原因
    :param planner: 可选，未传则新建 Planner
    :param current_tasks: 当前剩余任务列表（即当前 table）
    :param get_context: 可选，用于取 selected_boards 等
    :return: 更新后的任务列表（新 table）
    """
    if planner is None:
        planner = Planner()
    return planner.replan(
        user_input=user_input,
        executed_summary=executed_summary,
        replan_reason=replan_reason,
        current_tasks=current_tasks,
        get_context=get_context,
    )
