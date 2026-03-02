'''
Agent，Agent是整个系统的核心，负责与用户交互，调用工具，执行任务
'''
import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from agent.planner import Planner
from agent.router import Router
from agent.pipeline import Pipeline
from agent.memory import Memory


class Agent:
    def __init__(self):
        self.planner = Planner()
        self.router = Router()
        self.pipeline = Pipeline()
        self.memory = Memory()
        pass

    def run(self):
        pass