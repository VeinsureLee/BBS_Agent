'''
Agent Replan：解决阶段中的重新规划模块，对应图中 Solving Phase 的 Replan。
由 Task Agent 在遇到阻碍或需要调整时触发，根据当前执行状态与原因重新生成后续任务。
'''
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from agent.planner import Planner


def run_replan(
    user_input: str,
    executed_summary: str,
    replan_reason: str,
    planner: Planner | None = None,
) -> list[dict]:
    """
    根据当前执行状态与受阻原因重新规划后续任务（Replan）。
    :param user_input: 用户原始目标
    :param executed_summary: 已执行任务及结果摘要
    :param replan_reason: 受阻或需要调整的原因
    :param planner: 可选，未传则使用新建的 Planner 实例
    :return: 后续任务列表 [{"id": "1", "description": "..."}, ...]
    """
    if planner is None:
        planner = Planner()
    return planner.replan(
        user_input=user_input,
        executed_summary=executed_summary,
        replan_reason=replan_reason,
    )


# 实例：执行受阻时触发重新规划
if __name__ == "__main__":
    user_goal = "帮我整理 BBS 各版面的标签，并生成一份汇总报告"
    executed = "任务1：已拉取版面列表；任务2：在打标签时部分版面接口超时，仅完成 60% 版面。"
    reason = "部分版面接口超时，需跳过失败版面继续处理其余版面，并最后汇总成功与失败列表。"
    tasks = run_replan(user_goal, executed, reason)
    print("用户目标:", user_goal)
    print("已执行摘要:", executed)
    print("受阻原因:", reason)
    print("重新规划任务数:", len(tasks))
    for t in tasks:
        print(" -", t.get("id"), t.get("description", ""))
