"""
标签初始化：根据 data/web_structure 中的介绍内容，调用大模型生成版面标签并写入 data/static。
线程数由 config/init.json 的 tag_max_workers 控制。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.path_tool import get_abs_path
from utils.logger_handler import logger

from knowledge.processing.tagger import run_from_web_structure_to_static

INIT_JSON_PATH = "config/init.json"
TAG_MAX_WORKERS_KEY = "tag_max_workers"


def _load_init_json() -> dict:
    """读取 config/init.json，缺失或解析失败返回默认 dict。"""
    path = get_abs_path(INIT_JSON_PATH)
    default = {
        "usr_vector_store_status": False,
        "static_vector_store_status": False,
        "tag_init_status": False,
        "crawl_concurrency": 4,
        TAG_MAX_WORKERS_KEY: 8,
    }
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except (json.JSONDecodeError, IOError):
        return default


def _tag_max_workers() -> int:
    """从 config/init.json 读取标签化线程数（tag_max_workers），默认 8。"""
    data = _load_init_json()
    try:
        return max(1, int(data.get(TAG_MAX_WORKERS_KEY, 8)))
    except (TypeError, ValueError):
        return 8


def run_tag_init(
    web_structure_dir: str | None = None,
    static_dir: str | None = None,
    max_workers: int | None = None,
) -> int:
    """
    执行标签初始化：从 web_structure 读取介绍 JSON，多线程打标签后保存到 static。
    :param web_structure_dir: 默认 data/web_structure
    :param static_dir: 默认 data/static
    :param max_workers: 不传则从 config/init.json 的 tag_max_workers 读取（默认 8）
    :return: 写入 data/static 的版面数（含占位）
    """
    if max_workers is None:
        max_workers = _tag_max_workers()
    logger.info("开始标签初始化，多线程数: %s（config/init.json 中 tag_max_workers）", max_workers)
    count = run_from_web_structure_to_static(
        web_structure_dir=web_structure_dir,
        static_dir=static_dir,
        max_workers=max_workers,
    )
    logger.info("标签初始化完成，共处理 %s 个版面", count)
    return count
