'''
Agent Plan：规划阶段入口，对应图中 Planning Phase 的 Plan 模块。
根据用户输入调用 Planner 生成任务列表（Generate Tasks），供解决阶段执行。
'''
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from agent.planner import Planner


def run_plan(user_input: str, planner: Planner | None = None) -> list[dict]:
    """
    根据用户输入生成任务列表（Plan → Generate Tasks）。
    :param user_input: 用户目标或请求
    :param planner: 可选，未传则使用新建的 Planner 实例
    :return: 任务列表 [{"id": "1", "description": "..."}, ...]
    """
    if planner is None:
        planner = Planner()
    return planner.plan(user_input)


# 实例：从用户输入生成计划并返回任务列表
if __name__ == "__main__":
    example_input = "帮我整理 BBS 各版面的标签，并生成一份汇总报告"
    tasks = run_plan(example_input)
    print("用户输入:", example_input)
    print("生成任务数:", len(tasks))
    for t in tasks:
        print(" -", t.get("id"), t.get("description", ""))
