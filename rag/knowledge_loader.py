"""
知识库文件与 MD5 记录读写，不依赖向量库。
支持按 chroma 配置（info_path、section_info）递归列出文件并生成相对路径；
支持介绍（置顶）JSON 的列出与加载用于向量化。
"""
import json
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


INTRODUCTIONS_PREFIX = "introductions/"


def list_introduction_files(introductions_root_abs: str) -> list[tuple[str, str]]:
    """
    递归列出介绍根目录下所有 介绍*.json 文件。
    返回 [(绝对路径, rel_path), ...]，rel_path 形如 introductions/讨论区/版面/介绍0.json（用于向量库 source_file）。
    """
    result: list[tuple[str, str]] = []
    root = introductions_root_abs.rstrip(os.sep)
    if not os.path.isdir(root):
        return result
    for section_name in os.listdir(root):
        section_dir = os.path.join(root, section_name)
        if not os.path.isdir(section_dir):
            continue
        for board_name in os.listdir(section_dir):
            board_dir = os.path.join(section_dir, board_name)
            if not os.path.isdir(board_dir):
                continue
            for fname in os.listdir(board_dir):
                if fname.endswith(".json") and "介绍" in fname:
                    abs_path = os.path.join(board_dir, fname)
                    if not os.path.isfile(abs_path):
                        continue
                    rel_path = f"{INTRODUCTIONS_PREFIX}{section_name}/{board_name}/{fname}"
                    result.append((abs_path, rel_path))
    return result


def get_introduction_file_documents(abs_path: str, rel_path: str) -> list[Document]:
    """
    加载「介绍」JSON（置顶帖子格式：title, time, author, reply_count, url, floors）。
    从 rel_path 解析 section/board：introductions/讨论区/版面/介绍0.json。
    每个帖子生成一条 Document，内容为标题 + 各楼内容摘要。
    """
    parts = rel_path.replace("\\", "/").strip("/").split("/")
    if len(parts) >= 3 and (parts[0] == "introductions" or rel_path.startswith(INTRODUCTIONS_PREFIX)):
        section_name = parts[1]
        board_name = parts[2]
    else:
        section_name = ""
        board_name = ""
    out = []
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return out
    title = data.get("title", "")
    time_str = data.get("time", "")
    author = data.get("author", "")
    reply_count = data.get("reply_count", 0)
    url = data.get("url", "")
    floors = data.get("floors") or []
    content_parts = [f"标题：{title} 作者：{author} 时间：{time_str} 回复数：{reply_count} 链接：{url}"]
    for fl in floors:
        c = (fl.get("content") or "").strip()
        if c:
            content_parts.append(c[:2000] if len(c) > 2000 else c)
    content = "\n\n".join(content_parts)
    if not content.strip():
        return out
    out.append(
        Document(
            page_content=content,
            metadata={
                "source_file": rel_path,
                "section": section_name,
                "board": board_name,
                "title": title,
                "reply_count": reply_count,
            },
        )
    )
    return out
