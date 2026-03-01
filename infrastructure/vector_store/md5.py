"""
MD5 增量记录：读写 rel_path -> md5_hex，用于向量库仅更新变更文件。
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_here))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from utils.path_tool import get_abs_path

# 记录文件格式：每行 rel_path|md5_hex
MD5_RECORD_SEP = "|"


def load_recorded(md5_store_path: str) -> dict[str, str]:
    """从 md5 记录文件读取 rel_path -> md5_hex。"""
    out: dict[str, str] = {}
    path = get_abs_path(md5_store_path) if not os.path.isabs(md5_store_path) else md5_store_path
    if not os.path.isfile(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if MD5_RECORD_SEP in line:
                rel, md5_val = line.split(MD5_RECORD_SEP, 1)
                out[rel.strip()] = md5_val.strip()
    return out


def save_recorded(recorded: dict[str, str], md5_store_path: str) -> None:
    """将 rel_path -> md5_hex 写回 md5 记录文件。"""
    path = get_abs_path(md5_store_path) if not os.path.isabs(md5_store_path) else md5_store_path
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rel, md5_val in sorted(recorded.items()):
            f.write(f"{rel}{MD5_RECORD_SEP}{md5_val}\n")


def rel_path_to_section_board(rel_path: str) -> tuple[str, str] | None:
    """从相对路径解析讨论区/版面。约定 .../讨论区/版面/介绍*.json。"""
    parts = rel_path.replace("\\", "/").strip("/").split("/")
    if len(parts) >= 3 and "介绍" in (parts[-1] or ""):
        return parts[-3], parts[-2]
    return None


def check_md5_hex(md5_for_check: str, md5_store_path: str) -> bool:
    """
    检查 md5 是否已记录（按行存储的 md5 文件格式）。
    若记录文件不存在则创建空文件并返回 False。
    :return: True 表示已处理过，False 表示未处理过
    """
    path = get_abs_path(md5_store_path) if not os.path.isabs(md5_store_path) else md5_store_path
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(path, "w", encoding="utf-8").close()
        return False
    with open(path, "r", encoding="utf-8") as f:
        for line in f.readlines():
            if line.strip() == md5_for_check:
                return True
    return False


def save_md5_hex(md5_for_check: str, md5_store_path: str) -> None:
    """将 md5 追加写入记录文件（按行存储）。"""
    path = get_abs_path(md5_store_path) if not os.path.isabs(md5_store_path) else md5_store_path
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(md5_for_check + "\n")
