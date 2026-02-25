import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.tools.middleware import monitor_tool, log_before_model, report_prompt_switch
from agent.tools.query_tools.query_tools import (
    bbs_rag_query,
    query_board_posts,
    list_crawled_boards,
)
from agent.tools.init_tools.init_tools import run_bbs_init, run_full_init, is_initialized
from utils.prompt_loader import load_system_prompts
from model.factory import chat_model
from langchain.agents import create_agent


class ReactAgent:
    def __init__(self, auto_init: bool = True):
        """
        :param auto_init: 若为 True 且尚未初始化（init.json 中 init_status 非 True），则启动时自动执行一次 BBS 初始化。
        """
        if auto_init and not is_initialized():
            try:
                run_full_init(headless=True)
            except Exception as e:
                # 初始化失败不阻塞 Agent 创建，仅依赖后续用户通过 run_bbs_init 再试
                import warnings
                warnings.warn(f"启动时自动初始化未成功: {e}", UserWarning)

        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[bbs_rag_query, query_board_posts, list_crawled_boards, run_bbs_init],
            middleware=[monitor_tool, log_before_model, report_prompt_switch],
        )

    def execute_stream(self, query: str):
        input_dict = {
            "messages": [
                {"role": "user", "content": query},
            ]
        }

        # 第三个参数context就是上下文runtime中的信息，就是我们做提示词切换的标记
        for chunk in self.agent.stream(input_dict, stream_mode="values", context={"report": False}):
            latest_message = chunk["messages"][-1]
            if latest_message.content:
                yield latest_message.content.strip() + "\n"


if __name__ == '__main__':
    agent = ReactAgent()

    for chunk in agent.execute_stream("我想了解有哪些关于职业选择的信息"):
        print(chunk, end="", flush=True)
