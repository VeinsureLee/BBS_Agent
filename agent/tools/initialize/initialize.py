"""
数据初始化模块：读取 config/init.json，若已初始化则跳过论坛结构爬取；
否则依次执行：论坛初始化（forum init）→ 版面初始化（board init）→ 标签初始化（tag init）→ 向量化（结构向量库、用户向量库）。

并发与多线程（在 config/init.json 中设置）：
- 爬取（异步）：crawl_concurrency，同时爬取的讨论区数量，默认 4。
- 标签化（多线程）：tag_max_workers，打标签线程数，默认 8。
- 结构向量库：static_vector_max_workers，加载 data/static 版面 JSON 的线程数，默认 4。
- 用户向量库：usr_vector_max_workers，加载用户上传数据的线程数，默认 4。
"""
import asyncio
import json
import os
import sys

# 保证从项目根可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.path_tool import get_abs_path
from utils.logger_handler import logger

try:
    from .forum_init import run_forum_init
    from .board_init import run_board_init
    from .tag_init import run_tag_init
    from .static_vector import run_static_vector_init
    from .user_vector import run_usr_vector_init
except ImportError:
    from agent.tools.initialize.forum_init import run_forum_init
    from agent.tools.initialize.board_init import run_board_init
    from agent.tools.initialize.tag_init import run_tag_init
    from agent.tools.initialize.static_vector import run_static_vector_init
    from agent.tools.initialize.user_vector import run_usr_vector_init

INIT_JSON_PATH = "config/init.json"
FORUM_INIT_STATUS_KEY = "forum_init_status"
BOARD_INIT_STATUS_KEY = "board_init_status"


def _load_init_json() -> dict:
    """读取 config/init.json，缺失或解析失败返回默认 dict。"""
    path = get_abs_path(INIT_JSON_PATH)
    default = {
        "usr_vector_store_status": False,
        "static_vector_store_status": False,
        FORUM_INIT_STATUS_KEY: False,
        BOARD_INIT_STATUS_KEY: False,
        "tag_init_status": False,
        "crawl_concurrency": 4,
        "tag_max_workers": 8,
        "static_vector_max_workers": 4,
        "usr_vector_max_workers": 4,
    }
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except (json.JSONDecodeError, IOError):
        return default


def _update_init_status(updates: dict) -> None:
    """仅更新 config/init.json 中指定字段，其余保留。"""
    path = get_abs_path(INIT_JSON_PATH)
    data = _load_init_json()
    data.update(updates)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    logger.info("已更新 config/init.json: %s", list(updates.keys()))


def is_already_initialized() -> bool:
    """根据 config/init.json 的 forum_init_status 判断论坛是否已初始化（是否跳过论坛结构爬取）。"""
    data = _load_init_json()
    return bool(data.get(FORUM_INIT_STATUS_KEY))


def do_initialize() -> bool:
    """
    执行整体数据初始化：forum init → board init → tag init。
    若 forum_init_status 为 true 则跳过论坛结构爬取，否则先执行论坛初始化；
    版面初始化依赖 forum_structure.json，标签初始化依赖 web_structure 下的介绍文件。
    :return: True 表示流程执行完成（或已跳过），False 表示未配置等异常。
    """
    if is_already_initialized():
        logger.info("论坛已初始化（forum_init_status 为 true），跳过论坛结构爬取")
    else:
        logger.info("开始论坛初始化：爬取讨论区与版面结构")
        ok = asyncio.run(run_forum_init())
        if not ok:
            logger.warning("论坛初始化未完成，继续尝试版面与标签初始化（若已有 forum_structure.json）")
        else:
            _update_init_status({FORUM_INIT_STATUS_KEY: True})
            logger.info("论坛初始化完成，已设置 forum_init_status=true")

    init_data = _load_init_json()
    if init_data.get(BOARD_INIT_STATUS_KEY):
        logger.info("版面已初始化（board_init_status 为 true），跳过版面置顶爬取")
    else:
        logger.info("开始版面初始化：爬取各版面置顶并保存介绍 JSON")
        board_ok = asyncio.run(run_board_init())
        if board_ok:
            _update_init_status({BOARD_INIT_STATUS_KEY: True})
    logger.info("版面初始化流程结束")

    run_tag_init()
    # tag_init_status 由 knowledge.processing.tagger 在打标签完成后写入
    logger.info("数据初始化（forum → board → tag）流程结束")

    # 向量化：结构向量库（data/static 版面 JSON）、用户向量库（用户上传数据），线程数从 config/init.json 读取
    logger.info("开始向量化：结构向量库与用户向量库")
    static_ok = run_static_vector_init()
    usr_ok = run_usr_vector_init()
    logger.info("向量化结束：结构向量库=%s，用户向量库=%s", "成功" if static_ok else "失败/跳过", "成功" if usr_ok else "失败/跳过")
    logger.info("数据初始化（forum → board → tag → 向量化）流程结束")
    return True


def main():
    """模块自测入口：执行完整初始化并在控制台输出调试信息。"""
    logger.info("=== 初始化调试：执行 forum init → board init → tag init ===")
    do_initialize()
    logger.info("=== 初始化调试结束 ===")


if __name__ == "__main__":
    main()
