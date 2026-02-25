import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.tools.middleware import monitor_tool, log_before_model, report_prompt_switch
from agent.tools.query_tools.query_tools import (
    bbs_rag_query,
    query_board_posts,
    list_crawled_boards,
)
from utils.prompt_loader import load_system_prompts
from model.factory import chat_model
from langchain.agents import create_agent


class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[bbs_rag_query, query_board_posts, list_crawled_boards],
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
