# -*- coding: utf-8 -*-
"""
基于参考资料（RAG）的总结工具：结合用户提问与检索/爬取得到的参考资料，生成带层级、口语化的概括回答。
供 Agent 在判定当前任务完成后生成最终答案时调用；提示词由 prompts/rag_summarize.txt 提供。
"""
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _root not in sys.path:
    sys.path.insert(0, _root)

from langchain_core.messages import HumanMessage
from infrastructure.model_factory.factory import chat_model
from utils.prompt_loader import load_rag_prompts
from utils.logger_handler import logger


def rag_summarize(user_input: str, context: str) -> str:
    """
    根据用户提问和参考资料生成概括回答。回答具有层级结构且保持口语化。

    :param user_input: 用户提问原文。
    :param context: 参考资料全文（版面列表、帖子摘要、链接等，可由 Agent 从 completed_tasks 拼成）。
    :return: 概括回答字符串，格式示例：
        根据问题...，经过爬取/检索后发现有以下版面符合：
        1、版面1，url，从属关系，有***人赞同
        2、版面2，...
        综上所述你的问题***的回答是***
    """
    if not (user_input or "").strip():
        return "请提供具体问题以便生成回答。"
    try:
        template = load_rag_prompts()
    except Exception as e:
        logger.warning("[rag_summarize] 加载提示词失败: %s，使用内联模板", e)
        template = (
            "你是专注于「基于参考资料总结」的 AI 助手。请结合用户提问和参考资料，生成简洁、有层级、口语化的概括回答。\n\n"
            "用户提问：{input}\n\n"
            "参考资料：\n{context}\n\n"
            "要求：仅输出概括内容本身，纯文本，不输出 JSON 或代码块；语气口语化，结构清晰（如：根据问题…→ 发现以下版面符合：1、… 2、… → 综上所述…）。"
        )
    prompt = template.replace("{input}", (user_input or "").strip()).replace(
        "{context}", (context or "无").strip()
    )
    try:
        response = chat_model.invoke([HumanMessage(content=prompt)])
        raw = (getattr(response, "content", None) or str(response) or "").strip()
        return raw or "暂无法根据当前资料生成概括，请补充更多检索结果。"
    except Exception as e:
        logger.exception("[rag_summarize] LLM 调用失败: %s", e)
        return "生成概括时发生错误，请稍后重试。"
