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
from utils.prompt_loader import load_plan_prompts
from utils.logger_handler import logger


def _parse_plan_response(raw: str) -> list[dict]:
    """从模型原始输出中解析出 tasks 列表。支持纯 JSON 或被 markdown 包裹。"""
    text = (raw or "").strip()
    # 去掉可能的 markdown 代码块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
        tasks = data.get("tasks")
        if isinstance(tasks, list):
            return [t if isinstance(t, dict) else {"id": str(i), "description": str(t)} for i, t in enumerate(tasks, 1)]
        return []
    except json.JSONDecodeError as e:
        logger.warning("[Planner] JSON 解析失败: %s，原始: %s", e, text[:200])
        return []


class Planner:
    """规划器：根据用户输入生成任务列表（Plan），或根据执行状态重新规划（Replan）。"""

    def __init__(self):
        self._prompt_template = load_plan_prompts()

    def plan(self, user_input: str) -> list[dict]:
        """
        根据用户输入生成任务列表（对应图中 Plan → Generate Tasks）。
        :param user_input: 用户目标或请求
        :return: [{"id": "1", "description": "..."}, ...]
        """
        prompt = self._prompt_template.format(
            user_input=user_input or "",
            replan_section="",
        )
        try:
            response = chat_model.invoke([HumanMessage(content=prompt)])
            raw = (getattr(response, "content", None) or str(response) or "").strip()
            return _parse_plan_response(raw)
        except Exception as e:
            logger.exception("[Planner] plan 调用失败: %s", e)
            return []

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
        replan_section = (
            "\n- 当前已执行任务及结果：{executed_summary}\n- 受阻或需调整的原因：{replan_reason}"
            .format(executed_summary=executed_summary or "无", replan_reason=replan_reason or "需要调整")
        )
        prompt = self._prompt_template.format(
            user_input=user_input or "",
            replan_section=replan_section,
        )
        try:
            response = chat_model.invoke([HumanMessage(content=prompt)])
            raw = (getattr(response, "content", None) or str(response) or "").strip()
            return _parse_plan_response(raw)
        except Exception as e:
            logger.exception("[Planner] replan 调用失败: %s", e)
            return []
