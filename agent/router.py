'''
Router，Router是Agent的路线规划器，负责规划Agent的行动路线
'''
from typing import Dict, Any, Optional
from utils.logger_handler import logger


class Router:
    def __init__(self):
        self.tool_capabilities = self._load_tool_capabilities()
        self.decision_history = []
        logger.info("Router初始化完成")

    def _load_tool_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """加载工具能力描述"""
        return {
            "query_user_data": {
                "description": "查询用户上传的数据文件",
                "keywords": ["用户数据", "上传文件", "本地文件", "个人收藏", "历史记录"],
                "capabilities": {"works_offline": True, "requires_network": False},
            },
            "query_structure_data": {
                "description": "获取论坛版面结构信息",
                "keywords": ["版面结构", "讨论区", "论坛结构", "导航", "层级"],
                "capabilities": {"works_offline": True, "requires_network": False},
            },
            "query_post_data": {
                "description": "查询版面内的帖子内容",
                "keywords": ["帖子内容", "版面帖子", "讨论内容", "帖子列表", "具体内容"],
                "capabilities": {"works_offline": True, "requires_network": False},
            },
            "crawl_board_recent_posts": {
                "description": "爬取指定版面的最近帖子并清理、向量化",
                "keywords": ["爬取最近帖子", "爬取版面", "抓取帖子", "更新版面", "拉取最近"],
                "capabilities": {"works_offline": False, "requires_network": True},
            },
        }

    def route(self, task: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        智能路由决策

        Args:
            task: 任务描述，包含id和description
            context: 当前对话上下文

        Returns:
            选择使用的工具名称
        """
        task_description = task.get("description", "").lower()
        task_id = task.get("id", "")

        logger.info(f"开始路由决策 - 任务ID: {task_id}, 描述: {task_description}")

        # 基于任务ID的直接路由（含按版面展开的任务 3-1, 3-2, ...）
        id_routing = {
            "1": "query_user_data",
            "2": "query_structure_data",
            "3": "query_post_data",
            "4": "crawl_board_recent_posts",
        }
        if task_id in id_routing:
            selected_tool = id_routing[task_id]
        elif task_id and task_id.startswith("3-"):
            selected_tool = "query_post_data"
        elif task_id and task_id.startswith("4-"):
            selected_tool = "crawl_board_recent_posts"
        else:
            selected_tool = None

        if selected_tool is not None:
            logger.info(f"基于任务ID路由到工具: {selected_tool}")
            self.decision_history.append({
                "task": task,
                "context": context,
                "selected_tool": selected_tool,
                "reason": f"任务ID匹配: {task_id}"
            })
            return selected_tool

        # 基于关键词描述的路由
        keyword_mappings = {
            "用户上传": "query_user_data",
            "本地文件": "query_user_data",
            "个人收藏": "query_user_data",
            "历史记录": "query_user_data",
            "版面结构": "query_structure_data",
            "讨论区": "query_structure_data",
            "论坛结构": "query_structure_data",
            "版面帖子": "query_post_data",
            "帖子内容": "query_post_data",
            "具体内容": "query_post_data",
            "爬取最近帖子": "crawl_board_recent_posts",
            "爬取版面": "crawl_board_recent_posts",
            "抓取帖子": "crawl_board_recent_posts",
        }

        for keyword, tool_name in keyword_mappings.items():
            if keyword in task_description:
                logger.info(f"基于关键词'{keyword}'路由到工具: {tool_name}")
                self.decision_history.append({
                    "task": task,
                    "context": context,
                    "selected_tool": tool_name,
                    "reason": f"关键词匹配: {keyword}"
                })
                return tool_name

        # 回退：语义匹配
        selected_tool = self._semantic_route(task_description, context)
        logger.info(f"基于语义匹配路由到工具: {selected_tool}")
        self.decision_history.append({
            "task": task,
            "context": context,
            "selected_tool": selected_tool,
            "reason": "语义匹配"
        })
        return selected_tool

    def _semantic_route(self, task_description: str, context: Dict[str, Any]) -> str:
        """基于工具能力和任务需求的语义路由"""
        best_match = None
        best_score = 0

        for tool_name, capabilities in self.tool_capabilities.items():
            score = self._calculate_match_score(task_description, capabilities, context)
            logger.debug(f"工具 {tool_name} 匹配得分: {score}")

            if score > best_score:
                best_score = score
                best_match = tool_name

        # 默认回退到用户数据查询
        return best_match or "query_user_data"

    def _calculate_match_score(self, task_desc: str, capabilities: Dict[str, Any], context: Dict[str, Any]) -> float:
        """计算工具与任务需求的匹配度"""
        score = 0.0

        # 关键词匹配得分
        keywords = capabilities.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in task_desc:
                score += 2.0  # 关键词匹配权重较高

        # 上下文相关得分
        user_expertise = context.get("user_expertise", "medium")
        if user_expertise == "beginner" and capabilities.get("works_offline"):
            score += 0.5  # 初学者偏好离线工具

        # 工具描述匹配
        description = capabilities.get("description", "").lower()
        if any(word in description for word in task_desc.split()):
            score += 1.0

        return score

    def get_decision_history(self) -> list:
        """获取路由决策历史"""
        return self.decision_history.copy()

    def clear_history(self):
        """清除决策历史"""
        self.decision_history.clear()