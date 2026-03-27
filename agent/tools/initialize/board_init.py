"""
版面初始化（TS版）：调用 infrastructure/browser_manager_ts/board-init.ts
根据 forum_structure.json 爬取各版面置顶及详情并生成介绍 JSON。
"""
import asyncio
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.config_handler import load_config
from utils.path_tool import get_abs_path
from utils.logger_handler import logger

STRUCTURE_PATH = "data/web_structure/forum_structure.json"


def _ts_working_dir() -> str:
    return get_abs_path("infrastructure/browser_manager_ts")


def _resolve_npm_command() -> list[str]:
    """在 Windows venv 场景下优先定位 npm.cmd，找不到时回退 cmd /c npm。"""
    npm = shutil.which("npm")
    if npm:
        return [npm]
    npm_cmd = shutil.which("npm.cmd")
    if npm_cmd:
        return [npm_cmd]
    npm_exe = shutil.which("npm.exe")
    if npm_exe:
        return [npm_exe]
    if os.name == "nt":
        return ["cmd", "/c", "npm"]
    return ["npm"]


async def _run_ts_init(script_name: str) -> bool:
    cwd = _ts_working_dir()
    if not os.path.isdir(cwd):
        logger.warning("未找到 TS 初始化目录: %s", cwd)
        return False
    cmd = [*_resolve_npm_command(), "run", script_name]
    logger.info("开始执行 TS 初始化脚本: %s (cwd=%s)", " ".join(cmd), cwd)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
    )
    code = await proc.wait()
    if code != 0:
        logger.warning("TS 初始化脚本执行失败（exit=%s）: %s", code, script_name)
        return False
    return True


async def run_board_init() -> bool:
    """
    根据 data/web_structure/forum_structure.json 收集所有版面，
    爬取各版面置顶帖列表，对每个置顶打开详情并保存为 介绍[index].json。
    :return: True 表示成功，False 表示无结构文件或未配置 BBS_Url。
    """
    structure_path = get_abs_path(STRUCTURE_PATH)
    if not os.path.exists(structure_path):
        logger.warning("未找到 forum_structure.json 或内容为空，跳过版面初始化")
        return False

    bbs_cfg = load_config()
    home_url = (bbs_cfg.get("BBS_Url") or "").strip().rstrip("/")
    if not home_url:
        logger.warning("未配置 BBS_Url，退出版面初始化")
        return False
    ok = await _run_ts_init("board-init")
    if ok:
        logger.info("TS 版面初始化完成")
    return ok
