"""
知识库文件与 MD5 记录读写，不依赖向量库。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.documents import Document
from utils import pdf_loader, txt_loader, json_loader


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


def get_file_documents(read_path: str) -> list[Document]:
    """按扩展名用对应 loader 加载为 Document 列表。"""
    if read_path.endswith("txt"):
        return txt_loader(read_path)
    if read_path.endswith("pdf"):
        return pdf_loader(read_path)
    if read_path.endswith("json"):
        return json_loader(read_path)
    return []
