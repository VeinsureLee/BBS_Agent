# -*- coding: utf-8 -*-
"""
动态帖子 JSON 内容清理：将楼层 content 按邮件头格式分块并写回原文件。

功能说明：
    - 解析北邮人论坛楼层 content 的邮件头格式（发信人、信区、标题、发信站、正文、来源等）；
    - 将每层 content 从单一字符串转为分块 dict（发信人、信区、标题、发信站、正文、来源）；
    - 支持按版面或「分类/版面」路径收集 data/dynamic 下所有帖子 JSON，清理后写回原路径。

主要接口入参/出参：
    - parse_content_blocks(content: str) -> dict[str, str]
        入参：content — 楼层原始文本（可能含发信人、信区、标题、发信站、--、※ 来源 等）。
        出参：{"发信人","信区","标题","发信站","正文","来源"} 等键的字典，未匹配到的键为空字符串。
    - clean_floor_content(floor: dict) -> None
        入参：floor — 单层楼 dict，若 "content" 为 str 则原地替换为 parse_content_blocks 结果。
        出参：无（原地修改）。
    - get_board_json_paths(data_root: Path, board: str) -> list[Path]
        入参：data_root — data/dynamic 根路径；board — 版面名（如 "创意生活"）或 "分类/版面"。
        出参：该版面下所有 .json 文件的 Path 列表。
    - clean_board(board: str, data_root: str | Path = "data/dynamic") -> int
        入参：board — 版面名或 "分类/版面"；data_root — 动态数据根目录。
        出参：处理并写回的 JSON 文件数量。
"""

import json
import re
from pathlib import Path
from typing import Any


def parse_content_blocks(content: str) -> dict[str, str]:
    """
    将北邮人论坛楼层 content 按邮件头格式分块解析。
    格式示例：
        发信人: xxx (昵称), 信区: xxx
        标  题: xxx
        发信站: 北邮人论坛 (日期), 站内
        [正文]
        --
        ※ 来源:·北邮人论坛
        http://...
        ·[FROM: ...]
    """
    blocks: dict[str, str] = {
        "发信人": "",
        "信区": "",
        "标题": "",
        "发信站": "",
        "正文": "",
        "来源": "",
    }
    if not content or not content.strip():
        return blocks

    text = content.strip()

    # 发信人: xxx (昵称), 信区: xxx
    m_sender = re.search(r"发信人:\s*([^\n]+?)(?=\n|$)", text)
    if m_sender:
        blocks["发信人"] = m_sender.group(1).strip()
    m_board = re.search(r"信区:\s*(\S+)", text)
    if m_board:
        blocks["信区"] = m_board.group(1).strip()

    # 标  题: 或 标题:（可能有多空格/全角空格）
    m_title = re.search(r"标\s*题:\s*(.+?)(?=\n发信站|\n\s*\n|$)", text, re.DOTALL)
    if m_title:
        blocks["标题"] = m_title.group(1).strip()

    # 发信站: 北邮人论坛 (日期), 站内
    m_station = re.search(r"发信站:\s*(.+?)(?=\n\s*\n|\n--|\n※|$)", text, re.DOTALL)
    if m_station:
        blocks["发信站"] = m_station.group(1).strip()

    # 正文与来源：以 \n--\n 为界，-- 之后到 ※ 来源 之前为正文，※ 来源 及之后为来源
    parts = re.split(r"\n--\s*\n", text, maxsplit=1)

    if len(parts) == 2:
        after_sep = parts[1]
        # 再按 ※ 来源 拆成 正文 和 来源
        source_match = re.search(r"\n?※\s*来源\s*:", after_sep)
        if source_match:
            blocks["正文"] = after_sep[: source_match.start()].strip()
            blocks["来源"] = after_sep[source_match.start() :].strip()
        else:
            blocks["正文"] = after_sep.strip()
        # 若发信站后、-- 前还有内容，也并入正文（少数帖子）
        before_sep = parts[0]
        after_station = re.search(r"发信站:[^\n]+\n", before_sep)
        if after_station:
            mid = before_sep[after_station.end() :].strip()
            if mid and not blocks["正文"]:
                blocks["正文"] = mid
            elif mid:
                blocks["正文"] = mid + "\n\n" + blocks["正文"]
    else:
        # 无 -- 分隔，发信站之后全部当正文
        after_station = re.search(r"发信站:[^\n]+\n", text)
        if after_station:
            blocks["正文"] = text[after_station.end() :].strip()
        else:
            blocks["正文"] = text

    return blocks


def clean_floor_content(floor: dict[str, Any]) -> None:
    """原地修改楼层：若 content 为字符串则替换为分块后的 dict。"""
    raw = floor.get("content")
    if raw is None:
        return
    if isinstance(raw, dict):
        # 已是分块格式，跳过
        return
    if isinstance(raw, str):
        floor["content"] = parse_content_blocks(raw)
    return


def get_board_json_paths(data_root: Path, board: str) -> list[Path]:
    """
    根据版面名收集该版面下所有 JSON 路径。
    - board 为 "创意生活"：匹配 data_root/*/创意生活/*/*.json
    - board 为 "生活时尚/创意生活"：匹配 data_root/生活时尚/创意生活/*/*.json
    """
    data_root = Path(data_root)
    if "/" in board or "\\" in board:
        # 视为 分类/版面
        parts = board.replace("\\", "/").strip("/").split("/")
        board_dir = data_root.joinpath(*parts)
        if not board_dir.is_dir():
            return []
        return list(board_dir.rglob("*.json"))
    # 单版面名：任意一层目录名为 board 的下的所有 json
    out: list[Path] = []
    for d in data_root.iterdir():
        if not d.is_dir():
            continue
        board_dir = d / board
        if board_dir.is_dir():
            out.extend(board_dir.rglob("*.json"))
    return out


def clean_json_files(file_paths: list[Path] | list[str]) -> int:
    """
    仅对给定的 JSON 文件路径做 content 分块清理并写回，不处理其他文件。
    :param file_paths: 要清理的帖子 JSON 文件路径列表（Path 或 str）
    :return: 成功处理并写回的文件数量
    """
    count = 0
    for p in file_paths:
        path = Path(p) if not isinstance(p, Path) else p
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        floors = data.get("floors")
        if not isinstance(floors, list):
            continue
        for floor in floors:
            if isinstance(floor, dict):
                clean_floor_content(floor)
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            continue
        count += 1
    return count


def clean_board(
    board: str,
    data_root: str | Path = "data/dynamic",
) -> int:
    """
    清理指定版面下所有帖子的 content，按发信人、信区、标题等分块并写回原路径。

    :param board: 版面名，如 "创意生活" 或 "生活时尚/创意生活"
    :param data_root: data/dynamic 的根路径，默认项目下的 data/dynamic
    :return: 处理过的 JSON 文件数量
    """
    root = Path(data_root)
    if not root.is_absolute():
        # 相对路径：相对于项目根（本文件在 knowledge/processing/clean.py）
        root = Path(__file__).resolve().parent.parent.parent / root
    paths = get_board_json_paths(root, board)
    return clean_json_files(paths)


if __name__ == "__main__":
    import sys

    board_name = sys.argv[1] if len(sys.argv) > 1 else "创意生活"
    n = clean_board(board_name)
    print(f"已处理版面 {board_name} 下 {n} 个文件")
