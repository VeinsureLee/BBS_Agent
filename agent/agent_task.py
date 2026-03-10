'''
Agent Task：解决阶段的任务代理，对应图中 Solving Phase 的 Task Agent。
接收规划阶段产生的任务列表（Exec），循环执行任务；必要时触发 Replan 获取新任务并继续执行。
'''
import os
import sys
from typing import Callable, Optional, Any

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from agent.planner import Planner
from agent.agent_replan import run_replan
from utils.logger_handler import logger


# 单任务执行回调：(task) -> (success, result_summary) 或 (task, context) -> (success, result_dict)
# 返回 (False, reason/result) 时可由调用方决定是否触发 Replan
ExecuteTaskFn = Callable[..., tuple[bool, Any]]


def _default_execute_task(task: dict, context: Optional[dict] = None) -> tuple[bool, str]:
    """默认执行器：仅记录描述并返回成功，实际业务可注入真实执行逻辑。"""
    desc = task.get("description", "") or str(task)
    return True, f"已执行: {desc}"


def run_tasks(
    user_input: str,
    tasks: list[dict],
    planner: Planner | None = None,
    execute_task_fn: ExecuteTaskFn | None = None,
    get_context: Optional[Callable[[], dict]] = None,
    max_replan: int = 3,
    needs_replan_fn: Optional[Callable[[dict, dict, Any], bool]] = None,
    analyze_replan_reason_fn: Optional[Callable[[dict, dict, Any], str]] = None,
    is_answer_sufficient_fn: Optional[Callable[[str, list], tuple[bool, str]]] = None,
    callbacks: Optional[dict] = None,
) -> tuple[list[dict], list[dict]]:
    """
    循环执行任务列表；遇失败或需调整时触发 Replan，用新任务继续执行。
    当当前任务列表执行完后，若提供了 is_answer_sufficient_fn 且判定为不充分，会触发 Replan 并继续执行直到充分或达到 max_replan。
    :param user_input: 用户原始目标（Replan 时需要）
    :param tasks: 初始任务列表 [{"id": "1", "description": "..."}, ...]
    :param planner: 可选，用于 Replan 时复用
    :param execute_task_fn: (task, context?) -> (success, result_dict)；未传则用默认占位。result_dict 会存入 executed_results["result"]，并用于 Replan 摘要。
    :param get_context: 可选，() -> context dict，每轮执行前调用以传入 execute_task_fn
    :param max_replan: 最大 Replan 次数，防止死循环
    :param needs_replan_fn: 可选，(result_dict, task, tool_name?) -> bool，为 True 时触发 Replan（默认仅 success=False 时触发）
    :param analyze_replan_reason_fn: 可选，(result_dict, task, tool_name?) -> str，生成 replan_reason
    :param is_answer_sufficient_fn: 可选，(user_input, executed_results[, context]) -> (sufficient: bool, reason: str)；当任务列表执行完后调用，可传入 context 以便按版面逐一排查；若返回 (False, reason) 则用 reason 触发 Replan 继续收集信息
    :param callbacks: 可选，on_task_start(task)、on_task_done(task, result)、on_replan(new_tasks) 用于渐进式披露
    :return: (已执行结果列表 [{"task", "success", "summary", "result"}, ...], 剩余未执行任务)
    """
    if planner is None:
        planner = Planner()
    execute_task_fn = execute_task_fn or _default_execute_task
    get_context = get_context or (lambda: {})
    callbacks = callbacks or {}

    def _cb(name: str, *args, **kwargs) -> None:
        fn = callbacks.get(name)
        if callable(fn):
            try:
                fn(*args, **kwargs)
            except Exception as e:
                logger.debug("run_tasks 回调 %s 异常: %s", name, e)

    executed_results: list[dict] = []
    current_tasks = list(tasks)
    replan_count = 0

    while replan_count <= max_replan:
        if current_tasks:
            task = current_tasks.pop(0)
            _cb("on_task_start", task)
            context = get_context()
            try:
                if _arity(execute_task_fn) >= 2:
                    success, result = execute_task_fn(task, context)
                else:
                    success, result = execute_task_fn(task)
            except Exception as e:
                success, result = False, {"status": "failed", "error": str(e)}
            result_dict = result if isinstance(result, dict) else {"result": result}
            _cb("on_task_done", task, result_dict)
            summary = _result_to_summary(result)
            executed_results.append({
                "task": task,
                "success": success,
                "summary": summary,
                "result": result_dict,
            })

            needs_replan = not success
            tool_name = result.get("tool_name", "") if isinstance(result, dict) else ""
            if needs_replan_fn and isinstance(result, dict):
                needs_replan = needs_replan_fn(result, task, tool_name)
            replan_reason = summary or "任务执行失败，需要调整后续步骤"
            if analyze_replan_reason_fn and isinstance(result, dict):
                replan_reason = analyze_replan_reason_fn(result, task, tool_name)

            if needs_replan and replan_count < max_replan:
                executed_summary = _format_executed_summary(executed_results)
                new_tasks = run_replan(
                    user_input=user_input,
                    executed_summary=executed_summary,
                    replan_reason=replan_reason,
                    planner=planner,
                )
                if new_tasks:
                    current_tasks = new_tasks
                    replan_count += 1
                    _cb("on_replan", new_tasks)
                    logger.info("[TaskAgent] 触发 Replan，获得 %s 项新任务", len(new_tasks))
                else:
                    logger.warning("[TaskAgent] Replan 未返回新任务，停止执行")
                    break
            continue

        # 当前任务列表已空：做回答充分性检查（传入 context 以便按版面逐一排查），不充分则 Replan 继续
        if not is_answer_sufficient_fn or replan_count >= max_replan:
            break
        context = get_context()
        try:
            if _arity(is_answer_sufficient_fn) >= 3:
                sufficient, reason = is_answer_sufficient_fn(user_input, executed_results, context)
            else:
                sufficient, reason = is_answer_sufficient_fn(user_input, executed_results)
        except Exception as e:
            logger.warning("[TaskAgent] 回答充分性检查异常: %s，视为不充分并尝试 Replan", e)
            sufficient, reason = False, f"检查异常: {e}"
        if sufficient:
            logger.info("[TaskAgent] 回答已充分，结束执行")
            break
        executed_summary = _format_executed_summary(executed_results)
        new_tasks = run_replan(
            user_input=user_input,
            executed_summary=executed_summary,
            replan_reason=reason or "当前结果不足以回答用户问题，建议扩大搜索或爬取更多版面",
            planner=planner,
        )
        if not new_tasks:
            logger.warning("[TaskAgent] 回答不充分但 Replan 未返回新任务，停止执行")
            break
        current_tasks = new_tasks
        replan_count += 1
        _cb("on_replan", new_tasks)
        logger.info("[TaskAgent] 回答不充分，触发 Replan 获得 %s 项新任务", len(new_tasks))

    return executed_results, current_tasks


def _arity(fn: Callable) -> int:
    """返回可调用对象参数个数（不含 *args/**kwargs 的近似）。"""
    try:
        return fn.__code__.co_argcount
    except Exception:
        return 1


def _result_to_summary(result: Any) -> str:
    """将 execute_task_fn 的 result 转为简短摘要字符串。"""
    if result is None:
        return "无结果"
    if isinstance(result, dict):
        if result.get("status") == "failed":
            return result.get("error", "执行失败")
        r = result.get("result", result)
        if isinstance(r, list):
            return f"共 {len(r)} 条结果"
        return str(r)[:200]
    return str(result)[:200]


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
