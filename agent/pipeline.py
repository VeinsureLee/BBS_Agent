'''
Pipeline，Pipeline是Agent的执行流程，负责协调Agent的各个组件，执行任务，Agent是整个系统的核心，负责与用户交互，调用工具，执行任务
'''
import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.logger_handler import logger


class Pipeline:
    def __init__(self, max_workers: int = 3, task_timeout: int = 30):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.execution_history = []
        self.max_workers = max_workers
        self.task_timeout = task_timeout
        self.retry_attempts = 2

        logger.info(f"Pipeline初始化完成，最大并行任务数: {max_workers}, 任务超时: {task_timeout}秒")

    def execute_task(
        self,
        task: Dict[str, Any],
        tool_name: str,
        tools_registry: Dict,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行单个任务并返回结构化结果。

        Args:
            task: 任务描述（可含 board_path / description）
            tool_name: 要使用的工具名称
            tools_registry: 工具注册表
            context: 可选对话上下文，含 selected_boards 等，供帖子查询/爬取使用

        Returns:
            执行结果字典
        """
        task_id = task.get("id", "unknown")
        execution_start = datetime.now()
        context = context or {}

        logger.info(f"开始执行任务 - ID: {task_id}, 工具: {tool_name}")

        try:
            # 从注册表获取工具
            tool = tools_registry.get(tool_name)
            if not tool:
                error_msg = f"工具'{tool_name}'未在注册表中找到"
                logger.error(error_msg)
                return self._create_error_result(task_id, tool_name, error_msg, execution_start)

            # 执行工具（带重试机制），传入 context 以解析版面等参数
            result = self._execute_with_retry(tool, task, task_id, context)

            execution_time = (datetime.now() - execution_start).total_seconds()

            if result.get("success"):
                execution_record = {
                    "task_id": task_id,
                    "tool_name": tool_name,
                    "status": "success",
                    "result": result.get("data", {}),
                    "execution_time": execution_time,
                    "timestamp": datetime.now().isoformat(),
                    "retry_count": result.get("retry_count", 0)
                }
                logger.info(f"任务执行成功 - ID: {task_id}, 耗时: {execution_time:.2f}秒")
            else:
                execution_record = {
                    "task_id": task_id,
                    "tool_name": tool_name,
                    "status": "failed",
                    "error": result.get("error", "未知错误"),
                    "execution_time": execution_time,
                    "timestamp": datetime.now().isoformat(),
                    "retry_count": result.get("retry_count", 0)
                }
                logger.error(f"任务执行失败 - ID: {task_id}, 错误: {result.get('error')}")

        except Exception as e:
            execution_time = (datetime.now() - execution_start).total_seconds()
            error_msg = f"任务执行异常: {str(e)}"
            logger.exception(f"任务执行异常 - ID: {task_id}")

            execution_record = {
                "task_id": task_id,
                "tool_name": tool_name,
                "status": "failed",
                "error": error_msg,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat(),
                "retry_count": 0
            }

        # 记录执行历史
        self.execution_history.append(execution_record)

        # 限制历史记录大小
        if len(self.execution_history) > 1000:
            self.execution_history = self.execution_history[-500:]

        return execution_record

    def _execute_with_retry(
        self,
        tool,
        task: Dict[str, Any],
        task_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """带重试机制的任务执行"""
        last_error = None
        context = context or {}

        for attempt in range(self.retry_attempts + 1):
            try:
                # 准备工具参数（含 context 中的 selected_boards 等）
                tool_params = self._prepare_tool_params(tool, task, context)

                # 执行工具
                if asyncio.iscoroutinefunction(tool):
                    # 异步工具
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(
                            asyncio.wait_for(tool(**tool_params), timeout=self.task_timeout)
                        )
                    finally:
                        loop.close()
                else:
                    # 同步工具
                    result = tool(**tool_params)

                # 验证结果
                if result is not None:
                    return {
                        "success": True,
                        "data": result,
                        "retry_count": attempt
                    }
                else:
                    raise ValueError("工具返回空结果")

            except asyncio.TimeoutError:
                last_error = f"任务执行超时（{self.task_timeout}秒）"
                logger.warning(f"任务超时 - ID: {task_id}, 尝试: {attempt + 1}")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"任务执行失败 - ID: {task_id}, 尝试: {attempt + 1}, 错误: {e}")

            # 如果不是最后一次尝试，等待后重试
            if attempt < self.retry_attempts:
                time.sleep(0.5 * (attempt + 1))  # 指数退避

        # 所有重试都失败
        return {
            "success": False,
            "error": last_error or "任务执行失败",
            "retry_count": self.retry_attempts
        }

    def _prepare_tool_params(
        self,
        tool,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """准备工具执行参数；帖子查询/爬取优先从 task 或 context.selected_boards 取版面。"""
        description = task.get("description", "")
        context = context or {}

        # 版面：优先 task 内显式字段，否则用 context 中上一任务写入的 selected_boards
        board_path = task.get("board_path") or task.get("hierarchy_path")
        section = task.get("section")
        board = task.get("board")
        if not board_path and not (section and board):
            selected = context.get("selected_boards") or []
            if selected:
                board_path = selected[0] if isinstance(selected[0], str) else str(selected[0])

        params: Dict[str, Any] = {"query": description}

        tool_name = getattr(tool, "__name__", "unknown")

        if "user_data" in tool_name:
            # 用用户问题检索本地/用户上传数据，并带内容摘要供总结使用
            user_input = (context.get("user_input") or "").strip()
            params["query"] = user_input or description
            params.update({"k": 10, "include_content_preview": True})
        elif "post_data" in tool_name:
            params.update({"k": 10, "include_content_preview": False})
            if board_path:
                params["board_path"] = board_path
            elif section is not None and board is not None:
                params["section"] = section
                params["board"] = board
        elif "structure_boards" in tool_name:
            # 按问题内容与版面各维度的相似度检索，不做显式关键词映射（见 prompt 渐进式披露）
            user_input = context.get("user_input") or ""
            params["query"] = (user_input.strip() or description).strip() or description
            params.update({"top_k": 5, "include_docs": False})
        elif "structure" in tool_name:
            params.update({"top_k": 5, "include_docs": False})
        elif "crawl" in tool_name or "crawl_board" in tool_name:
            params = {
                "board_path": board_path or "",
                "max_pages": task.get("max_pages", 1),
            }
        return params

    def _create_error_result(self, task_id: str, tool_name: str, error_msg: str, start_time: datetime) -> Dict[str, Any]:
        """创建错误结果"""
        execution_time = (datetime.now() - start_time).total_seconds()

        result = {
            "task_id": task_id,
            "tool_name": tool_name,
            "status": "failed",
            "error": error_msg,
            "execution_time": execution_time,
            "timestamp": datetime.now().isoformat(),
            "retry_count": 0
        }

        self.execution_history.append(result)
        return result

    def batch_execute(self, tasks: List[Dict], tools_registry: Dict) -> List[Dict]:
        """
        批量执行多个任务

        Args:
            tasks: 任务列表
            tools_registry: 工具注册表

        Returns:
            执行结果列表
        """
        if not tasks:
            return []

        logger.info(f"开始批量执行 {len(tasks)} 个任务")

        # 按工具分组以优化执行
        tool_groups = {}
        for task in tasks:
            tool_name = task.get("assigned_tool", "default")
            if tool_name not in tool_groups:
                tool_groups[tool_name] = []
            tool_groups[tool_name].append(task)

        results = []

        # 执行每个工具组的任务
        for tool_name, group_tasks in tool_groups.items():
            if len(group_tasks) == 1:
                # 单个任务直接执行
                result = self.execute_task(group_tasks[0], tool_name, tools_registry)
                results.append(result)
            else:
                # 并行执行同一工具组的任务
                group_results = self._execute_parallel_tasks(group_tasks, tool_name, tools_registry)
                results.extend(group_results)

        logger.info(f"批量执行完成，共 {len(results)} 个结果")
        return results

    def _execute_parallel_tasks(self, tasks: List[Dict], tool_name: str, tools_registry: Dict) -> List[Dict]:
        """并行执行任务组"""
        results = []

        # 使用线程池并行执行
        with ThreadPoolExecutor(max_workers=min(len(tasks), self.max_workers)) as executor:
            # 提交所有任务
            future_to_task = {
                executor.submit(self.execute_task, task, tool_name, tools_registry): task
                for task in tasks
            }

            # 收集结果
            for future in as_completed(future_to_task):
                try:
                    result = future.result(timeout=self.task_timeout + 10)
                    results.append(result)
                except Exception as e:
                    task = future_to_task[future]
                    error_result = {
                        "task_id": task.get("id", "unknown"),
                        "tool_name": tool_name,
                        "status": "failed",
                        "error": f"并行执行异常: {str(e)}",
                        "execution_time": 0,
                        "timestamp": datetime.now().isoformat(),
                        "retry_count": 0
                    }
                    results.append(error_result)
                    logger.error(f"并行任务执行异常 - 任务ID: {task.get('id')}, 错误: {e}")

        return results

    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        if not self.execution_history:
            return {"total_tasks": 0}

        total_tasks = len(self.execution_history)
        successful_tasks = len([r for r in self.execution_history if r.get("status") == "success"])
        failed_tasks = total_tasks - successful_tasks

        execution_times = [r.get("execution_time", 0) for r in self.execution_history]
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0

        tool_usage = {}
        for record in self.execution_history:
            tool_name = record.get("tool_name", "unknown")
            tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1

        return {
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0,
            "average_execution_time": avg_execution_time,
            "tool_usage": tool_usage,
            "recent_execution": self.execution_history[-1] if self.execution_history else None
        }

    def clear_history(self):
        """清除执行历史"""
        count = len(self.execution_history)
        self.execution_history.clear()
        logger.info(f"清除执行历史，共 {count} 条记录")

    def get_task_result(self, task_id: str) -> Optional[Dict]:
        """获取特定任务的执行结果"""
        for record in reversed(self.execution_history):
            if record.get("task_id") == task_id:
                return record
        return None