import json
import os
import hashlib
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger_handler import logger
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader


def get_file_md5_hex(filepath: str):     # 获取文件的md5的十六进制字符串

    if not os.path.exists(filepath):
        logger.error(f"[md5计算]文件{filepath}不存在")
        return

    if not os.path.isfile(filepath):
        logger.error(f"[md5计算]路径{filepath}不是文件")
        return

    md5_obj = hashlib.md5()

    chunk_size = 4096       # 4KB分片，避免文件过大爆内存
    try:
        with open(filepath, "rb") as f:     # 必须二进制读取
            while chunk := f.read(chunk_size):
                md5_obj.update(chunk)

            """
            chunk = f.read(chunk_size)
            while chunk:
                
                md5_obj.update(chunk)
                chunk = f.read(chunk_size)
            """
            md5_hex = md5_obj.hexdigest()
            return md5_hex
    except Exception as e:
        logger.error(f"计算文件{filepath}md5失败，{str(e)}")
        return None


def listdir_with_allowed_type(path: str, allowed_types: tuple[str]):        # 返回文件夹内的文件列表（允许的文件后缀）
    files = []

    if not os.path.isdir(path):
        logger.error(f"[listdir_with_allowed_type]{path}不是文件夹")
        return allowed_types

    for f in os.listdir(path):
        if f.endswith(allowed_types):
            files.append(os.path.join(path, f))

    return tuple(files)


def list_allowed_files_recursive(path: str, allowed_types: tuple[str]) -> list[str]:
    """递归列出目录及所有子目录下允许后缀的文件路径（用于按版面名称命名的多级文件夹）。"""
    files = []
    if not os.path.isdir(path):
        logger.error(f"[list_allowed_files_recursive]{path}不是文件夹")
        return files
    for root, _, names in os.walk(path):
        for name in names:
            if name.endswith(allowed_types):
                files.append(os.path.join(root, name))
    return files


def pdf_loader(filepath: str, passwd=None) -> list[Document]:
    return PyPDFLoader(filepath, passwd).load()


def txt_loader(filepath: str) -> list[Document]:
    return TextLoader(filepath, encoding="utf-8").load()


def json_loader(filepath: str) -> list[Document]:
    """
    加载 BBS 版面每日爬取的 JSON（含 section_name, board_name, date, posts）。
    每个帖子转为一条 Document，便于检索。
    """
    out = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"[json_loader]读取 {filepath} 失败: {e}")
        return out
    section = data.get("section_name", "")
    board = data.get("board_name", "")
    date = data.get("date", "")
    posts = data.get("posts") or []
    for p in posts:
        title = p.get("title", "")
        author = p.get("author", "")
        time_str = p.get("time", "")
        reply_count = p.get("reply_count", 0)
        url = p.get("url", "")
        content = (
            f"版面：{section} {board} 日期：{date} "
            f"标题：{title} 作者：{author} 时间：{time_str} 回复数：{reply_count} 链接：{url}"
        )
        out.append(
            Document(
                page_content=content,
                metadata={
                    "source": filepath,
                    "section": section,
                    "board": board,
                    "date": date,
                    "title": title,
                    "reply_count": reply_count,
                },
            )
        )
    return out
