# -*- coding: utf-8 -*-
"""
BBS Agent 交互入口：循环接收用户输入，调用 Agent 回答，并将整场会话保存到 usr_history。
会话目录名由本场会话中第一个问题的摘要（去非法字符、截断）构成。
"""
import os
import re
import sys
import json
from datetime import datetime

# 保证项目根在 path 中
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from utils.path_tool import get_abs_path
from agent.agent import Agent


USR_HISTORY_DIR = "usr_history"
CHAT_FILENAME = "chat.jsonl"
READABLE_FILENAME = "chat.txt"
MAX_FOLDER_NAME_LEN = 40


def _sanitize_folder_name(text: str) -> str:
    """将首问摘要为合法文件夹名：去非法字符、截断。"""
    if not (text or "").strip():
        return "session_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    s = re.sub(r'[\s\\/:*?"<>|]+', "_", (text or "").strip())
    s = s.strip("_")[:MAX_FOLDER_NAME_LEN].strip("_")
    return s or "session_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_usr_history_root() -> str:
    root = get_abs_path(USR_HISTORY_DIR)
    os.makedirs(root, exist_ok=True)
    return root


def _session_dir_for_first_question(first_question: str) -> str:
    """根据本场会话第一个问题生成会话目录路径。"""
    root = _ensure_usr_history_root()
    name = _sanitize_folder_name(first_question)
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    return path


def _append_turn(session_dir: str, role: str, content: str) -> None:
    line = json.dumps(
        {"role": role, "content": content, "at": datetime.now().isoformat()},
        ensure_ascii=False,
    ) + "\n"
    path = os.path.join(session_dir, CHAT_FILENAME)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def _write_readable(session_dir: str, turns: list[dict]) -> None:
    path = os.path.join(session_dir, READABLE_FILENAME)
    lines = []
    for t in turns:
        role = t.get("role", "")
        content = (t.get("content") or "").strip()
        at = t.get("at", "")
        lines.append(f"[{at}] {role}\n{content}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run():
    agent = Agent()
    print("BBS Agent 已启动。输入问题后回车获取回答；输入空行或 exit/quit 结束本场会话并保存。\n")

    session_dir: str | None = None
    turns: list[dict] = []

    while True:
        try:
            user_input = input("你: ").strip()
        except EOFError:
            break
        if not user_input or user_input.lower() in ("exit", "quit", "q"):
            break

        if session_dir is None:
            session_dir = _session_dir_for_first_question(user_input)
            print(f"[会话已保存到: {session_dir}]\n")

        _append_turn(session_dir, "user", user_input)
        turns.append({"role": "user", "content": user_input, "at": datetime.now().isoformat()})

        response = agent.run(user_input)
        print(f"\nAgent: {response}\n")

        _append_turn(session_dir, "assistant", response)
        turns.append({"role": "assistant", "content": response, "at": datetime.now().isoformat()})

    if session_dir and turns:
        _write_readable(session_dir, turns)
        print(f"会话已保存至: {session_dir}")


if __name__ == "__main__":
    run()
