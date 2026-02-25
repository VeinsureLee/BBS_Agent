"""
知识库文件与 MD5 记录读写，不依赖向量库。
支持按 chroma 配置（info_path、section_info）递归列出文件并生成相对路径。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.documents import Document
from utils import (
    get_abs_path,
    list_allowed_files_recursive,
    pdf_loader,
    txt_loader,
    json_loader,
)


MD5_RECORD_SEP = "|"


def norm_rel_path(path: str, data_abs: str) -> str:
    """相对 data_abs 的路径，统一用 / 便于跨平台与 Chroma 一致。"""
    return os.path.relpath(path, data_abs).replace("\\", "/")


def load_recorded(md5_store_path: str, sep: str = MD5_RECORD_SEP) -> dict[str, str]:
    """从 md5 记录文件读取：rel_path -> md5。"""
    out: dict[str, str] = {}
    if not os.path.exists(md5_store_path):
        return out
    with open(md5_store_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if sep in line:
                rel, md5 = line.split(sep, 1)
                out[rel.strip()] = md5.strip()
    return out


def save_recorded(
    recorded: dict[str, str],
    md5_store_path: str,
    sep: str = MD5_RECORD_SEP,
) -> None:
    """将当前 recorded（rel_path -> md5）写回 md5 记录文件。"""
    parent = os.path.dirname(md5_store_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(md5_store_path, "w", encoding="utf-8") as f:
        for rel, md5 in sorted(recorded.items()):
            f.write(f"{rel}{sep}{md5}\n")


def _normalize_file_types(ft) -> tuple[str, ...]:
    """将 file_type 配置转为 list_allowed_files_recursive 所需的后缀元组。"""
    if ft is None:
        return ()
    if isinstance(ft, str):
        return (ft,) if ft else ()
    return tuple(ft) if ft else ()


def list_files_by_chroma_config(chroma_cfg: dict) -> list[tuple[str, str]]:
    """
    按 chroma 配置中的 info_path、section_info 递归列出知识库文件。
    返回 [(绝对路径, 相对 data 的路径), ...]，相对路径统一用 /。
    """
    data_abs = get_abs_path("data")
    result: list[tuple[str, str]] = []
    for key in ("info_path", "section_info"):
        cfg = chroma_cfg.get(key)
        if not cfg or not isinstance(cfg, dict):
            continue
        path_cfg = cfg.get("path")
        if not path_cfg:
            continue
        path_abs = get_abs_path(path_cfg)
        if not os.path.isdir(path_abs):
            continue
        allowed = _normalize_file_types(cfg.get("file_type"))
        if not allowed:
            continue
        for abs_path in list_allowed_files_recursive(path_abs, allowed):
            rel_path = norm_rel_path(abs_path, data_abs)
            result.append((abs_path, rel_path))
    return result


def get_file_documents(read_path: str) -> list[Document]:
    """按扩展名用对应 loader 加载为 Document 列表。"""
    if read_path.endswith("txt"):
        return txt_loader(read_path)
    if read_path.endswith("pdf"):
        return pdf_loader(read_path)
    if read_path.endswith("json"):
        return json_loader(read_path)
    return []
