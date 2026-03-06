'''
Planner：Agent 的规划器，负责根据用户输入生成计划（Plan），或在执行受阻时重新规划（Replan）。
对应流程：Planning Phase 的 Plan → Generate Tasks；Solving Phase 中 Task Agent 触发的 Replan。
'''
import json
import os
import re
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from langchain_core.messages import HumanMessage

from infrastructure.model_factory.factory import chat_model
from utils.prompt_loader import load_plan_prompts, load_replan_prompts
from utils.logger_handler import logger


def _parse_plan_response(raw: str) -> list[dict]:
    """从模型原始输出中解析出 tasks 列表。支持纯 JSON 或被 markdown 包裹。"""
    text = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
        tasks = data.get("tasks")
        if isinstance(tasks, list):
            task_list = [t if isinstance(t, dict) else {"id": str(i), "description": str(t)} for i, t in enumerate(tasks, 1)]
        else:
            task_list = []
        return task_list
    except json.JSONDecodeError as e:
        logger.warning("[Planner] JSON 解析失败: %s，原始: %s", e, text[:200])
        return []


class Planner:
    """规划器：Plan 与 Replan 使用独立提示词，分别生成任务列表与重新规划后续任务。"""

    def __init__(self):
        self._plan_template = load_plan_prompts()
        self._replan_template = load_replan_prompts()

    # 可选三步：API 根据用户问题判断需要执行哪些
    POSSIBLE_TASKS = [
        {"id": "1", "description": "调用已有用户上传数据"},
        {"id": "2", "description": "获取版面结构信息"},
        {"id": "3", "description": "获取版面帖子"},
    ]

    def plan(self, user_input: str) -> list[dict]:
        """
        调用 API，根据用户问题判断是否需要执行：调用已有用户上传数据、获取版面结构信息、获取版面帖子。
        仅返回需要执行的任务列表，不判断版面从属。
        :param user_input: 用户目标或请求
        :return: 任务列表
        """
        prompt = self._plan_template.format(user_input=user_input or "")
        try:
            response = chat_model.invoke([HumanMessage(content=prompt)])
            raw = (getattr(response, "content", None) or str(response) or "").strip()
            tasks = _parse_plan_response(raw)
            if tasks:
                return tasks
            logger.warning("[Planner] plan API 返回空任务，使用默认计划")
        except Exception as e:
            logger.exception("[Planner] plan 调用失败: %s，使用默认计划", e)
        return list(self.POSSIBLE_TASKS)

    def replan(
        self,
        user_input: str,
        executed_summary: str,
        replan_reason: str,
    ) -> list[dict]:
        """
        根据当前执行状态与受阻原因重新规划后续任务（对应图中 Replan）。
        :param user_input: 用户原始目标
        :param executed_summary: 已执行任务及结果摘要
        :param replan_reason: 受阻或需要调整的原因
        :return: 后续任务列表 [{"id": "1", "description": "..."}, ...]
        """
        prompt = self._replan_template.format(
            user_input=user_input or "",
            executed_summary=executed_summary or "无",
            replan_reason=replan_reason or "需要调整",
        )
        try:
            response = chat_model.invoke([HumanMessage(content=prompt)])
            raw = (getattr(response, "content", None) or str(response) or "").strip()
            return _parse_plan_response(raw)
        except Exception as e:
            logger.exception("[Planner] replan 调用失败: %s", e)
            return []
