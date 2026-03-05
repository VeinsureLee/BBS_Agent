'''
Agent Task：解决阶段的任务代理，对应图中 Solving Phase 的 Task Agent。
接收规划阶段产生的任务列表（Exec），循环执行任务；必要时触发 Replan 获取新任务并继续执行。
'''
import os
import sys
from typing import Callable

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from agent.planner import Planner
from agent.agent_replan import run_replan
from utils.logger_handler import logger


# 单任务执行回调：task -> (success, result_summary)
# 返回 (False, reason) 时可由调用方决定是否触发 Replan
ExecuteTaskFn = Callable[[dict], tuple[bool, str]]


def _default_execute_task(task: dict) -> tuple[bool, str]:
    """默认执行器：仅记录描述并返回成功，实际业务可注入真实执行逻辑。"""
    desc = task.get("description", "") or str(task)
    return True, f"已执行: {desc}"


def run_tasks(
    user_input: str,
    tasks: list[dict],
    planner: Planner | None = None,
    execute_task_fn: ExecuteTaskFn | None = None,
    max_replan: int = 3,
) -> tuple[list[dict], list[dict]]:
    """
    循环执行任务列表；遇失败或需调整时触发 Replan，用新任务继续执行。
    :param user_input: 用户原始目标（Replan 时需要）
    :param tasks: 初始任务列表 [{"id": "1", "description": "..."}, ...]
    :param planner: 可选，用于 Replan 时复用
    :param execute_task_fn: 单任务执行函数 (task) -> (success, result_summary)，未传则用默认占位
    :param max_replan: 最大 Replan 次数，防止死循环
    :return: (已执行结果列表 [{"task": {...}, "success": bool, "summary": str}, ...], 剩余未执行任务)
    """
    if planner is None:
        planner = Planner()
    execute_task_fn = execute_task_fn or _default_execute_task

    executed_results: list[dict] = []
    current_tasks = list(tasks)
    replan_count = 0

    while current_tasks and replan_count <= max_replan:
        task = current_tasks.pop(0)
        success, summary = execute_task_fn(task)
        executed_results.append({
            "task": task,
            "success": success,
            "summary": summary,
        })

        if not success and replan_count < max_replan:
            executed_summary = _format_executed_summary(executed_results)
            replan_reason = summary or "任务执行失败，需要调整后续步骤"
            new_tasks = run_replan(
                user_input=user_input,
                executed_summary=executed_summary,
                replan_reason=replan_reason,
                planner=planner,
            )
            if new_tasks:
                current_tasks = new_tasks
                replan_count += 1
                logger.info("[TaskAgent] 触发 Replan，获得 %s 项新任务", len(new_tasks))
            else:
                logger.warning("[TaskAgent] Replan 未返回新任务，停止执行")
                break

    return executed_results, current_tasks


def _format_executed_summary(executed_results: list[dict]) -> str:
    """将已执行结果格式化为简短摘要，供 Replan 使用。"""
    parts = []
    for i, r in enumerate(executed_results, 1):
        t = r.get("task") or {}
        desc = t.get("description", "")
        ok = r.get("success", False)
        summary = (r.get("summary") or "").strip()
        parts.append(f"任务{i}({'成功' if ok else '失败'}): {desc}; 结果: {summary}")
    return "\n".join(parts)


# 实例：先通过 Plan 生成任务，再交给 Task Agent 执行（含一次模拟失败触发 Replan）
if __name__ == "__main__":
    from agent.agent_plan import run_plan

    user_input = "帮我整理 BBS 各版面的标签，并生成一份汇总报告"
    tasks = run_plan(user_input)
    if not tasks:
        tasks = [
            {"id": "1", "description": "获取所有版面列表"},
            {"id": "2", "description": "对每个版面调用标签生成并保存"},
            {"id": "3", "description": "汇总并生成报告"},
        ]

    def mock_execute(task: dict) -> tuple[bool, str]:
        tid = task.get("id", "")
        # 模拟任务 2 失败，触发 Replan
        if tid == "2":
            return False, "部分版面接口超时，仅完成 60%"
        return True, f"完成: {task.get('description', '')}"

    executed, remaining = run_tasks(
        user_input=user_input,
        tasks=tasks,
        execute_task_fn=mock_execute,
        max_replan=2,
    )
    print("用户目标:", user_input)
    print("已执行数:", len(executed))
    for r in executed:
        print(" -", r["task"].get("description"), "->", r["success"], r["summary"])
    print("剩余任务数:", len(remaining))
