'''
Memory，Memory是Agent的记忆，负责存储Agent的记忆，Agent是整个系统的核心，负责与用户交互，调用工具，执行任务
'''
import time
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from utils.logger_handler import logger
from utils.path_tool import get_abs_path


class Memory:
    def __init__(self, max_conversations: int = 100, ttl_hours: int = 24):
        self.conversations = {}  # conversation_id -> conversation_data
        self.max_conversations = max_conversations
        self.ttl_hours = ttl_hours
        self.cleanup_threshold = 0.8  # 80%满时清理
        self.persistence_enabled = True
        self.persistence_file = os.path.join(get_abs_path("data"), "conversation_memory.json")

        # 加载持久化的对话数据
        if self.persistence_enabled:
            self._load_persistence()

        logger.info(f"Memory初始化完成，最大对话数: {max_conversations}")

    def create_conversation(self, user_input: str) -> str:
        """创建新对话并返回对话ID"""
        conversation_id = f"conv_{int(time.time())}_{hash(user_input) % 10000}"

        self.conversations[conversation_id] = {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "user_input": user_input,
            "tasks": [],
            "todo_table": [],
            "results": {},
            "context": {
                "current_step": 0,
                "data_sources": [],
                "selected_boards": [],
                "last_query_results": [],
                "user_expertise": self._assess_user_expertise(user_input)
            },
            "metadata": {
                "status": "active",
                "complexity": self._assess_complexity(user_input),
                "task_count": 0
            }
        }

        logger.info(f"创建新对话: {conversation_id}")

        # 清理旧对话
        self._cleanup_old_conversations()

        # 持久化保存
        if self.persistence_enabled:
            self._save_persistence()

        return conversation_id

    def store_tasks(self, conversation_id: str, tasks: List[Dict]):
        """存储规划的任务，并同步更新 to-do table"""
        if conversation_id in self.conversations:
            self.conversations[conversation_id]["tasks"] = tasks
            self.conversations[conversation_id]["todo_table"] = list(tasks)
            self.conversations[conversation_id]["metadata"]["task_count"] = len(tasks)
            self.conversations[conversation_id]["last_updated"] = datetime.now().isoformat()

            logger.info(f"存储 {len(tasks)} 个任务到对话 {conversation_id}，并更新 todo_table")

            if self.persistence_enabled:
                self._save_persistence()

    def update_todo_table(self, conversation_id: str, todo_table: List[Dict]):
        """显式更新 to-do table（replan 或展开版面后调用）"""
        if conversation_id in self.conversations:
            self.conversations[conversation_id]["todo_table"] = list(todo_table)
            self.conversations[conversation_id]["last_updated"] = datetime.now().isoformat()
            logger.info(f"更新对话 {conversation_id} 的 todo_table，共 {len(todo_table)} 项")
            if self.persistence_enabled:
                self._save_persistence()

    def get_todo_table(self, conversation_id: str) -> List[Dict]:
        """获取当前 to-do table 副本"""
        if conversation_id not in self.conversations:
            return []
        return list(self.conversations[conversation_id].get("todo_table", []))

    def update_task_result(
        self,
        conversation_id: str,
        task_id: str,
        result: Any,
        task_description: str = "",
    ):
        """更新特定任务的结果；若为版面结构任务且成功，将 hierarchy_path 列表写入 context.selected_boards。"""
        if conversation_id not in self.conversations:
            return
        conv = self.conversations[conversation_id]
        conv["results"][task_id] = {
            "result": result,
            "completed_at": datetime.now().isoformat(),
            "status": result.get("status", "unknown") if isinstance(result, dict) else "completed",
        }
        conv["last_updated"] = datetime.now().isoformat()
        logger.info(f"更新任务结果 - 对话: {conversation_id}, 任务: {task_id}")

        # 版面结构任务成功时，将检索到的版面路径写入 context，供后续帖子查询/爬取使用
        desc = (task_description or "").strip()
        if "版面结构" in desc or "获取版面结构" in desc:
            if isinstance(result, dict) and result.get("status") == "success":
                raw = result.get("result")
                if isinstance(raw, list) and raw:
                    paths = []
                    for item in raw:
                        if isinstance(item, dict) and item.get("hierarchy_path"):
                            paths.append(item["hierarchy_path"])
                        elif isinstance(item, (list, tuple)) and len(item) >= 1:
                            paths.append(str(item[0]))
                    if paths:
                        conv["context"]["selected_boards"] = paths
                        logger.info(f"写入 selected_boards: {len(paths)} 个版面")

        if self.persistence_enabled:
            self._save_persistence()

    def update_context(self, conversation_id: str, updates: Dict[str, Any]):
        """批量更新对话上下文字段（如 selected_boards、last_query_results）。"""
        if conversation_id not in self.conversations:
            return
        conv = self.conversations[conversation_id]
        for key, value in updates.items():
            conv["context"][key] = value
        conv["last_updated"] = datetime.now().isoformat()
        if self.persistence_enabled:
            self._save_persistence()

    def get_context(self, conversation_id: str) -> Dict:
        """获取对话的当前上下文"""
        if conversation_id not in self.conversations:
            logger.warning(f"对话未找到: {conversation_id}")
            return {"error": "对话未找到"}

        conv = self.conversations[conversation_id]
        completed_tasks = len(conv["results"])
        total_tasks = len(conv["tasks"])

        context = {
            "progress": f"{completed_tasks}/{total_tasks}" if total_tasks > 0 else "0/0",
            "completed_tasks": list(conv["results"].keys()),
            "pending_tasks": [t for t in conv["tasks"] if t.get("id") not in conv["results"]],
            "user_expertise": conv["context"].get("user_expertise", "medium"),
            "complexity": conv["metadata"].get("complexity", "medium"),
            "data_sources": conv["context"].get("data_sources", []),
            "selected_boards": conv["context"].get("selected_boards", []),
            "last_query_results": conv["context"].get("last_query_results", []),
            "user_input": conv.get("user_input", ""),
            "conversation_age_minutes": self._get_conversation_age_minutes(conversation_id),
        }

        return context

    def store_final_response(self, conversation_id: str, response: str):
        """存储最终响应"""
        if conversation_id in self.conversations:
            self.conversations[conversation_id]["final_response"] = response
            self.conversations[conversation_id]["metadata"]["status"] = "completed"
            self.conversations[conversation_id]["last_updated"] = datetime.now().isoformat()

            logger.info(f"存储最终响应到对话 {conversation_id}")

            if self.persistence_enabled:
                self._save_persistence()

    def get_conversation(self, conversation_id: str) -> Optional[Dict]:
        """获取完整的对话数据"""
        return self.conversations.get(conversation_id)

    def list_conversations(self) -> List[Dict]:
        """列出所有对话的摘要信息"""
        summaries = []
        for conv_id, conv_data in self.conversations.items():
            summary = {
                "conversation_id": conv_id,
                "user_input": conv_data["user_input"],
                "created_at": conv_data["created_at"],
                "status": conv_data["metadata"]["status"],
                "task_count": conv_data["metadata"]["task_count"],
                "completed_tasks": len(conv_data["results"])
            }
            summaries.append(summary)

        # 按创建时间倒序排列
        summaries.sort(key=lambda x: x["created_at"], reverse=True)
        return summaries

    def clear_conversation(self, conversation_id: str):
        """清除特定对话"""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            logger.info(f"清除对话: {conversation_id}")

            if self.persistence_enabled:
                self._save_persistence()

    def clear_all_conversations(self):
        """清除所有对话"""
        count = len(self.conversations)
        self.conversations.clear()
        logger.info(f"清除所有 {count} 个对话")

        if self.persistence_enabled:
            self._save_persistence()

    def _assess_user_expertise(self, user_input: str) -> str:
        """评估用户专业程度"""
        expertise_indicators = {
            "expert": ["API", "代码", "技术", "分析", "统计", "配置", "调试"],
            "beginner": ["简单", "基本", "大概", "随便", "看看", "帮忙"]
        }

        input_lower = user_input.lower()

        for level, indicators in expertise_indicators.items():
            if any(indicator in input_lower for indicator in indicators):
                return level

        return "medium"  # 默认中等专业程度

    def _assess_complexity(self, user_input: str) -> str:
        """评估用户输入的复杂度"""
        complexity_indicators = {
            "high": ["分析", "统计", "比较", "预测", "优化", "详细", "综合"],
            "medium": ["查找", "搜索", "获取", "查询", "了解", "介绍"],
            "low": ["简单", "基本", "大概", "随便", "看看", "是什么"]
        }

        input_lower = user_input.lower()

        for level, indicators in complexity_indicators.items():
            if any(indicator in input_lower for indicator in indicators):
                return level

        return "medium"  # 默认中等复杂度

    def _get_conversation_age_minutes(self, conversation_id: str) -> float:
        """获取对话年龄（分钟）"""
        if conversation_id not in self.conversations:
            return 0.0

        created_at = datetime.fromisoformat(self.conversations[conversation_id]["created_at"])
        age = datetime.now() - created_at
        return age.total_seconds() / 60.0

    def _cleanup_old_conversations(self):
        """清理过期对话"""
        # 检查是否需要清理
        if len(self.conversations) < self.max_conversations * self.cleanup_threshold:
            return

        logger.info("开始清理过期对话")

        # 计算过期时间
        cutoff_time = datetime.now() - timedelta(hours=self.ttl_hours)

        # 找出过期对话
        expired_conversations = []
        for conv_id, conv_data in self.conversations.items():
            created_at = datetime.fromisoformat(conv_data["created_at"])
            if created_at < cutoff_time:
                expired_conversations.append(conv_id)

        # 清理过期对话
        for conv_id in expired_conversations:
            del self.conversations[conv_id]
            logger.info(f"清理过期对话: {conv_id}")

        # 如果仍然过多，按时间清理最旧的
        if len(self.conversations) > self.max_conversations:
            sorted_conversations = sorted(
                self.conversations.items(),
                key=lambda x: x[1]["created_at"]
            )

            to_remove = len(self.conversations) - self.max_conversations
            for i in range(to_remove):
                conv_id = sorted_conversations[i][0]
                del self.conversations[conv_id]
                logger.info(f"清理最旧对话: {conv_id}")

        # 保存清理后的状态
        if self.persistence_enabled:
            self._save_persistence()

    def _save_persistence(self):
        """保存对话数据到文件"""
        try:
            # 创建数据目录
            os.makedirs(os.path.dirname(self.persistence_file), exist_ok=True)

            # 保存数据（只保存可序列化的数据）
            save_data = {}
            for conv_id, conv_data in self.conversations.items():
                # 深度复制并清理不可序列化的数据
                save_data[conv_id] = json.loads(json.dumps(conv_data, default=str))

            with open(self.persistence_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)

            logger.debug(f"持久化保存 {len(save_data)} 个对话到 {self.persistence_file}")

        except Exception as e:
            logger.error(f"持久化保存失败: {e}")

    def _load_persistence(self):
        """从文件加载对话数据"""
        try:
            if os.path.exists(self.persistence_file):
                with open(self.persistence_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)

                # 过滤过期对话
                cutoff_time = datetime.now() - timedelta(hours=self.ttl_hours)
                valid_conversations = {}

                for conv_id, conv_data in loaded_data.items():
                    try:
                        created_at = datetime.fromisoformat(conv_data["created_at"])
                        if created_at >= cutoff_time:
                            valid_conversations[conv_id] = conv_data
                    except (ValueError, KeyError):
                        # 跳过格式错误的数据
                        continue

                self.conversations = valid_conversations
                logger.info(f"从持久化文件加载 {len(valid_conversations)} 个有效对话")

        except Exception as e:
            logger.error(f"持久化加载失败: {e}")
            self.conversations = {}