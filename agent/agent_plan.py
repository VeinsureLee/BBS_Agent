'''
Agent Plan：规划阶段入口，对应图中 Planning Phase 的 Plan 模块。
仅根据用户输入调用 Planner 生成任务列表（Generate Tasks），并由 agent 推断与哪些版面有关；供解决阶段执行。
调试时仅生成计划并写入 logs/plan 目录。
'''
import json
import os
import sys
from datetime import datetime

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from utils.path_tool import get_abs_path
from utils.logger_handler import get_logger

from agent.planner import Planner

# 计划专用日志：写入 logs/plan 目录
PLAN_LOG_DIR = get_abs_path("logs/plan")
os.makedirs(PLAN_LOG_DIR, exist_ok=True)
_plan_log_file = os.path.join(PLAN_LOG_DIR, f"plan_{datetime.now().strftime('%Y%m%d')}.log")
plan_logger = get_logger("plan", log_file=_plan_log_file)


def run_plan(user_input: str, planner: Planner | None = None) -> tuple[list[dict], str]:
    """
    仅根据用户输入生成任务列表，并由 agent 推断与哪些版面有关（Plan → Generate Tasks）。
    :param user_input: 用户目标或请求
    :param planner: 可选，未传则使用新建的 Planner 实例
    :return: (任务列表 [{"id": "1", "description": "..."}, ...], 与哪些版面有关 relevant_boards)
    """
    if planner is None:
        planner = Planner()
    tasks, relevant_boards = planner.plan(user_input)
    # 写入 plan 专用日志
    plan_logger.info("[Plan] 用户输入: %s", user_input)
    plan_logger.info("[Plan] 与哪些版面有关: %s", relevant_boards or "（未解析）")
    plan_logger.info("[Plan] 生成任务数: %s", len(tasks))
    plan_logger.debug("[Plan] 任务列表 JSON: %s", json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2))
    return (tasks, relevant_boards)


# 调试入口：仅输入用户问题，生成计划（含与哪些版面有关）并 logger 到 logs/plan
if __name__ == "__main__":
    example_input = "学校附近有什么好吃的？"

    tasks, relevant_boards = run_plan(example_input)

    print("用户输入:", example_input)
    print("与哪些版面有关:", relevant_boards)
    print("生成任务数:", len(tasks))
    for t in tasks:
        print(" -", t.get("id"), t.get("description", ""))
    print("计划已写入 logs/plan 目录。")
