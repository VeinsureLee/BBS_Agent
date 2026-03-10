'''
Agent，Agent是整个系统的核心，负责与用户交互，调用工具，执行任务
'''
import json
import re
import sys
import os
import time
from datetime import datetime
from typing import Optional, Callable, Any, List, Dict, Tuple

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from langchain_core.messages import HumanMessage

from agent.planner import Planner
from agent.router import Router
from agent.pipeline import Pipeline
from agent.memory import Memory
from agent.agent_task import run_tasks
from infrastructure.model_factory.factory import chat_model
from utils.prompt_loader import load_answer_sufficiency_prompt
from utils.logger_handler import logger
from agent.tools.summarize import rag_summarize


def _invoke_cb(callbacks: Optional[Dict[str, Callable]], name: str, *args, **kwargs) -> None:
    """若 callbacks 中存在 name 且为可调用，则调用，忽略异常。"""
    if not callbacks or not callable(callbacks.get(name)):
        return
    try:
        callbacks[name](*args, **kwargs)
    except Exception as e:
        logger.debug("回调 %s 执行异常: %s", name, e)


class Agent:
    def __init__(self):
        self.planner = Planner()
        self.router = Router()
        self.pipeline = Pipeline()
        self.memory = Memory()
        self.tools_registry = {}  # 工具注册表
        self._answer_sufficiency_template = ""
        self._initialize_tools()

    def _initialize_tools(self):
        """初始化工具注册表"""
        from agent.tools.query import (
            query_user_data,
            query_post_data,
            query_structure_boards,
        )
        from agent.tools.search import crawl_board_recent_posts

        self.tools_registry = {
            "query_user_data": query_user_data,
            "query_post_data": query_post_data,
            "query_structure_data": query_structure_boards,
            "crawl_board_recent_posts": crawl_board_recent_posts,
        }

        logger.info(f"已注册 {len(self.tools_registry)} 个工具")

    def run(
        self,
        user_input: str,
        callbacks: Optional[Dict[str, Callable[..., None]]] = None,
    ) -> str:
        """
        完整的Agent工作流：
        1. 基于用户输入生成初始计划
        2. 通过pipeline执行任务
        3. 根据需要重新规划
        4. 生成最终响应

        :param user_input: 用户问题
        :param callbacks: 可选回调，用于渐进式披露。支持键：
            on_plan_ready(tasks)、on_task_start(task)、on_task_done(task, result)、on_replan(new_tasks)
        """
        logger.info(f"开始处理用户输入: {user_input}")

        conversation_id = self.memory.create_conversation(user_input)
        logger.info(f"创建对话会话: {conversation_id}")

        tasks = self.planner.plan(user_input)
        self.memory.store_tasks(conversation_id, tasks)
        logger.info(f"生成初始计划，包含 {len(tasks)} 个任务")
        _invoke_cb(callbacks, "on_plan_ready", tasks)

        get_context = lambda: self.memory.get_context(conversation_id)
        execute_task_fn = lambda task, ctx: self._execute_one_task(task, ctx, conversation_id)

        def _on_todo_updated(updated_tasks):
            self.memory.update_todo_table(conversation_id, updated_tasks or [])

        task_callbacks = {
            "on_task_start": (callbacks or {}).get("on_task_start"),
            "on_task_done": (callbacks or {}).get("on_task_done"),
            "on_replan": (callbacks or {}).get("on_replan"),
            "on_todo_updated": _on_todo_updated,
        }
        executed_results, _remaining = run_tasks(
            user_input=user_input,
            tasks=tasks,
            planner=self.planner,
            execute_task_fn=execute_task_fn,
            get_context=get_context,
            max_replan=5,
            needs_replan_fn=self._needs_replanning,
            analyze_replan_reason_fn=self._analyze_replan_reason,
            is_answer_sufficient_fn=lambda ui, er, ctx=None: self._is_answer_sufficient(ui, er, ctx),
            callbacks=task_callbacks,
        )
        completed_tasks = [{"task": r["task"], "result": r["result"]} for r in executed_results]

        final_result = self._generate_final_response(user_input, completed_tasks)
        self.memory.store_final_response(conversation_id, final_result)

        logger.info("Agent工作流完成")
        return final_result

    def _execute_one_task(
        self,
        task: Dict[str, Any],
        context: Dict[str, Any],
        conversation_id: str,
    ) -> tuple[bool, Dict[str, Any]]:
        """执行单任务：路由 -> Pipeline -> 更新 Memory；供 run_tasks 调用。"""
        tool_name = self.router.route(task, context)
        logger.info(f"路由决策: 使用工具 {tool_name}")
        result = self.pipeline.execute_task(
            task, tool_name, self.tools_registry, context=context
        )
        # 记录本任务使用的版面，供充分性判断时按版面逐一排查
        if tool_name in ("query_post_data", "crawl_board_recent_posts"):
            used = context.get("selected_boards") or []
            result = dict(result) if isinstance(result, dict) else {"status": "failed", "result": result}
            result["board_path_used"] = used[:1] if isinstance(used, list) else [used] if used else []
        self.memory.update_task_result(
            conversation_id, task.get("id", ""), result, task.get("description", "")
        )
        success = result.get("status") == "success"
        return success, result

    def _needs_replanning(self, result: dict, task: dict, tool_name: str = "") -> bool:
        """判断是否需要重新规划（含结果充分性：帖子过少可触发爬取）。"""
        if result.get("status") == "failed":
            return True

        task_result = result.get("result", {})
        if not task_result or (isinstance(task_result, list) and len(task_result) == 0):
            return True

        # 结果充分性：获取版面帖子任务若返回条数过少，可触发 Replan（增加爬取步骤）
        min_post_results = 3
        desc = (task.get("description") or "").strip()
        if (
            "版面帖子" in desc or "query_post_data" in tool_name
        ) and isinstance(task_result, list) and 0 < len(task_result) < min_post_results:
            return True

        return False

    def _analyze_replan_reason(self, result: dict, task: dict, tool_name: str = "") -> str:
        """分析重新规划的原因"""
        if result.get("status") == "failed":
            return f"任务执行失败: {result.get('error', '未知错误')}"

        task_result = result.get("result", {})
        if not task_result:
            return "任务执行结果为空，需要尝试其他方法"

        desc = (task.get("description") or "").strip()
        if (
            ("版面帖子" in desc or "query_post_data" in tool_name)
            and isinstance(task_result, list)
            and len(task_result) < 3
        ):
            return "历史帖子数量不足，建议爬取最近帖子"

        return "需要调整执行策略"

    def _build_collected_summary(self, executed_results: List[dict], max_chars: int = 1800) -> str:
        """从已执行结果构建用于充分性判断的摘要，控制总长度。"""
        parts = []
        for r in executed_results:
            task = r.get("task") or {}
            res = r.get("result") or {}
            desc = task.get("description", "")
            status = res.get("status", "")
            if status != "success":
                parts.append(f"- {desc}: 未成功")
                continue
            raw = res.get("result")
            if isinstance(raw, list):
                parts.append(f"- {desc}: 共 {len(raw)} 条")
                for i, item in enumerate(raw[:5]):
                    if isinstance(item, dict):
                        title = item.get("title", item.get("board_name", "")) or str(item)[:80]
                        preview = item.get("content_preview", "")
                        line = f"  [{i+1}] {title}"
                        if preview:
                            line += f" | {preview[:80]}…" if len(preview) > 80 else f" | {preview}"
                        parts.append(line)
                    else:
                        parts.append(f"  [{i+1}] {str(item)[:100]}")
                if len(raw) > 5:
                    parts.append(f"  ... 还有 {len(raw) - 5} 条")
            elif isinstance(raw, str) and raw:
                parts.append(f"- {desc}: {raw[:200]}")
            else:
                parts.append(f"- {desc}: 有结果")
        summary = "\n".join(parts)
        if len(summary) > max_chars:
            summary = summary[: max_chars - 20] + "\n...(已截断)"
        return summary or "无"

    def _is_answer_sufficient(self, user_input: str, executed_results: List[dict], context: Optional[Dict] = None) -> Tuple[bool, str]:
        """判断当前已收集信息是否足以回答用户问题；考虑各版面逐一排查，仅在已检索版面与待检索版面基础上判断。返回 (是否充分, 原因说明)。"""
        if not executed_results:
            return False, "尚未执行任何任务，需要继续获取信息"
        text = (user_input or "").strip()
        if not text:
            return True, "无具体问题"
        # 简单问候/寒暄无需继续检索或爬取，直接判为充分
        _greetings = {"你好", "您好", "嗨", "在吗", "在么", "hello", "hi", "hey"}
        if text.lower() in _greetings or len(text) <= 2:
            return True, "简单问候无需更多信息"
        # 按版面逐一排查：汇总已检索版面与待检索版面
        boards_queried: List[str] = []
        for r in executed_results:
            res = r.get("result") or {}
            used = res.get("board_path_used")
            if used:
                for b in (used if isinstance(used, list) else [used]):
                    if b and b not in boards_queried:
                        boards_queried.append(b)
        selected = list(context.get("selected_boards") or []) if context else []
        boards_pending = [b for b in selected if b not in boards_queried]
        boards_queried_summary = "、".join(boards_queried) if boards_queried else "无"
        boards_pending_summary = "、".join(boards_pending) if boards_pending else "无"
        try:
            if not self._answer_sufficiency_template:
                self._answer_sufficiency_template = load_answer_sufficiency_prompt()
        except Exception as e:
            logger.warning("[Agent] 加载回答充分性提示词失败: %s，使用默认", e)
            self._answer_sufficiency_template = (
                "用户问题：{user_input}\n当前已收集信息摘要：{collected_summary}\n"
                "已检索版面：{boards_queried_summary}\n待检索版面：{boards_pending_summary}\n\n"
                "请判断这些信息是否足以回答用户问题。应在各版面之间逐一排查：只有在已排查完所有相关版面（待检索版面为空）或当前已检索内容已足以回答时，才判为充分；若尚有待检索版面且当前结果不足以回答，应判为不充分。\n"
                "仅输出 JSON：{{\"sufficient\": true或false, \"reason\": \"原因\"}}"
            )
        summary = self._build_collected_summary(executed_results)
        prompt = self._answer_sufficiency_template.format(
            user_input=text,
            collected_summary=summary,
            boards_queried_summary=boards_queried_summary,
            boards_pending_summary=boards_pending_summary,
        )
        try:
            response = chat_model.invoke([HumanMessage(content=prompt)])
            raw = (getattr(response, "content", None) or str(response) or "").strip()
        except Exception as e:
            logger.exception("[Agent] 回答充分性 LLM 调用失败: %s", e)
            return False, "解析失败，保守判定为不足，建议继续搜索或爬取"
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        if m:
            raw = m.group(1).strip()
        try:
            data = json.loads(raw)
            sufficient = bool(data.get("sufficient", False))
            reason = str(data.get("reason", "")).strip() or ("信息已足以回答" if sufficient else "当前结果不足以回答用户问题")
            return sufficient, reason
        except json.JSONDecodeError as e:
            logger.warning("[Agent] 回答充分性 JSON 解析失败: %s，原始: %s", e, raw[:200])
            return False, "解析失败，保守判定为不足"

    def _summarize_executed_tasks(self, completed_tasks: list) -> str:
        """总结已执行的任务"""
        summary = "已执行任务总结:\n"
        for item in completed_tasks:
            task = item["task"]
            result = item["result"]
            status = result.get("status", "unknown")
            summary += f"- 任务 {task.get('id')}: {task.get('description')} [状态: {status}]\n"
        return summary

    def _format_result_for_response(self, result: Any, max_items: int = 5, max_preview_len: int = 80) -> str:
        """将单条任务结果格式化为可读说明（标题、摘要等），用于最终回复。"""
        if isinstance(result, list) and result:
            parts = [f"共 {len(result)} 条相关结果。"]
            for i, item in enumerate(result[:max_items]):
                if isinstance(item, dict):
                    title = item.get("title", item.get("board_name", "")) or ""
                    preview = item.get("content_preview", "")
                    if title:
                        parts.append(f"  · {title}" + (f"：{preview[:max_preview_len]}…" if preview and len(preview) > max_preview_len else (f"：{preview}" if preview else "")))
                    else:
                        parts.append(f"  · {str(item)[:max_preview_len]}…")
                else:
                    parts.append(f"  · {str(item)[:max_preview_len]}…")
            if len(result) > max_items:
                parts.append(f"  … 还有 {len(result) - max_items} 条")
            return "\n".join(parts)
        if isinstance(result, str) and result:
            return result[:300] + ("…" if len(result) > 300 else "")
        return "执行完成"

    def _collect_references(self, completed_tasks: list) -> List[str]:
        """从已完成任务中收集参考来源：版面地址、帖子链接、文件路径，带说明而非裸地址。"""
        lines = []
        seen = set()
        for item in completed_tasks:
            result = item.get("result")
            if not result or result.get("status") != "success":
                continue
            raw = result.get("result")
            if not isinstance(raw, list):
                continue
            for it in raw:
                if not isinstance(it, dict):
                    continue
                # 版面：路径/名称
                hierarchy_path = it.get("hierarchy_path") or it.get("board_path")
                board_name = it.get("board_name", "")
                if hierarchy_path or board_name:
                    key = hierarchy_path or board_name
                    if key and key not in seen:
                        seen.add(key)
                        desc = f"版面：{board_name or hierarchy_path}"
                        if hierarchy_path:
                            desc += f"（路径：{hierarchy_path}）"
                        lines.append(desc)
                # 帖子：标题（链接）；文件：路径
                title = it.get("title", "")
                url = it.get("url", "")
                file_path = it.get("file", "")
                if url and url not in seen:
                    seen.add(url)
                    lines.append(f"帖子：{title or '无标题'}（链接：{url}）")
                if file_path and file_path not in seen:
                    seen.add(file_path)
                    lines.append(f"文件：{file_path}")
        return lines

    def _build_answer_summary(self, user_input: str, completed_tasks: list) -> str:
        """根据检索结果生成回答摘要（叙述性说明），包含内容概要而非仅条数。"""
        parts = [f"根据您的问题「{user_input}」，检索到以下相关内容："]
        for item in completed_tasks:
            result = item.get("result")
            if not result or result.get("status") != "success":
                continue
            raw = result.get("result", "")
            part = self._format_result_for_response(raw, max_items=5, max_preview_len=80)
            if part and part != "执行完成":
                parts.append(part)
        if len(parts) <= 1:
            return "暂未检索到可用的具体内容。"
        return "\n".join(parts)

    def _build_rag_context(self, completed_tasks: list) -> str:
        """从已完成任务中拼出供 RAG 总结使用的参考资料全文；本地文件优先，其次版面/帖子。"""
        lines = []
        for item in completed_tasks:
            result = item.get("result")
            if not result or result.get("status") != "success":
                continue
            raw = result.get("result")
            if not isinstance(raw, list):
                if isinstance(raw, str) and raw:
                    lines.append(raw[:500])
                continue
            for it in raw:
                if not isinstance(it, dict):
                    continue
                # 本地文件（用户上传/用户数据）：有 file 且无 hierarchy_path，优先纳入并带内容摘要
                file_path = it.get("file", "")
                content_preview = (it.get("content_preview") or "").strip()
                hierarchy_path = it.get("hierarchy_path") or it.get("board_path") or ""
                if file_path and not hierarchy_path:
                    line = f"本地文件：{file_path}"
                    if content_preview:
                        line += f"；内容摘要：{content_preview}"
                    lines.append(line)
                    continue
                # 版面/帖子信息
                board_name = it.get("board_name", "") or hierarchy_path
                url = it.get("url", "")
                title = it.get("title", "")
                post_preview = (it.get("content_preview") or "")[:200]
                agree_count = it.get("agree_count", it.get("likes", ""))
                reply_count = it.get("reply_count", it.get("replies", ""))
                parts = []
                if board_name or hierarchy_path:
                    parts.append(f"版面：{board_name}" + (f"，路径/从属：{hierarchy_path}" if hierarchy_path else ""))
                if title:
                    parts.append(f"标题：{title}")
                if url:
                    parts.append(f"链接：{url}")
                if post_preview:
                    parts.append(f"内容摘要：{post_preview}")
                if agree_count not in (None, ""):
                    parts.append(f"赞同/点赞：{agree_count}")
                if reply_count not in (None, ""):
                    parts.append(f"回复数：{reply_count}")
                if parts:
                    lines.append("；".join(parts))
        return "\n".join(lines) if lines else "无"

    def _generate_final_response(self, user_input: str, completed_tasks: list) -> str:
        """根据已完成任务生成最终响应：使用 RAG 总结模块生成层级化、口语化回答，并附参考来源。"""
        successful = [it for it in completed_tasks if (it.get("result") or {}).get("status") == "success"]
        if not successful:
            return f"很抱歉，我无法完成您的请求「{user_input}」。请尝试重新描述您的问题。"
        context = self._build_rag_context(completed_tasks)
        try:
            answer_summary = rag_summarize(user_input, context)
        except Exception as e:
            logger.warning("[Agent] RAG 总结失败，回退为简单摘要: %s", e)
            answer_summary = self._build_answer_summary(user_input, completed_tasks)
        references = self._collect_references(completed_tasks)
        response = f"根据你的问题「{user_input}」，我已经查过相关版面与帖子，结论如下。\n\n【回答】\n{answer_summary}"
        if references:
            response += f"\n\n【参考来源】\n" + "\n".join(references)
        return response