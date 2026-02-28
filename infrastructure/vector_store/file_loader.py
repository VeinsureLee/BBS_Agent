"""
File Loader：加载清理后的数据到内存中。

1. 用户数据：不进行清理，直接按扩展名加载到内存中。
2. 知识库数据：已处理（如 html -> json）的数据，按扩展名用对应 loader 加载。
3. 已加载到内存的数据进行缓存（路径 + MD5），避免重复加载。
4. 加载后生成 Document 对象，便于后续检索。
5. MD5 检测：数据变化时自动失效缓存并重新加载。

JSON 层级约定：
- 版面每日爬取格式：section_name, board_name, date, posts → 使用 utils.json_loader。
- 介绍/置顶格式：路径为 .../讨论区/版面/介绍*.json，内容为 title, time, author, reply_count, url, floors → 使用 _load_introduction_json。
"""
import json
import os
import sys

# 保证可从项目根目录导入 utils
_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_here))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from langchain_core.documents import Document
from utils import (
    get_abs_path,
    get_file_md5_hex,
    pdf_loader,
    txt_loader,
    json_loader,
)


def _parse_section_board_from_path(abs_path: str) -> tuple[str, str]:
    """
    从介绍 JSON 的路径解析讨论区/版面。路径层级：.../讨论区/版面/介绍*.json。
    返回 (section_name, board_name)。
    """
    parts = os.path.normpath(abs_path).replace("\\", "/").strip("/").split("/")
    if len(parts) >= 3 and "介绍" in (parts[-1] or ""):
        return parts[-3], parts[-2]
    return "", ""


def _load_introduction_json(abs_path: str) -> list[Document]:
    """
    加载「介绍」JSON（置顶帖子格式：title, time, author, reply_count, url, floors）。
    从路径解析层级：.../讨论区/版面/介绍0.json → section=讨论区, board=版面。
    每个帖子生成一条 Document，内容为标题 + 各楼内容摘要。
    """
    section_name, board_name = _parse_section_board_from_path(abs_path)
    out: list[Document] = []
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
    # 使用相对 data 的路径作为 source_file，与 chroma 约定一致
    rel_path = os.path.relpath(abs_path, get_abs_path("data")).replace("\\", "/")
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


def _get_file_documents(read_path: str) -> list[Document]:
    """按扩展名及路径层级用对应 loader 加载为 Document 列表。"""
    path_lower = read_path.lower()
    if path_lower.endswith(".txt"):
        return txt_loader(read_path)
    if path_lower.endswith(".pdf"):
        return pdf_loader(read_path)
    if path_lower.endswith(".json"):
        basename = os.path.basename(read_path)
        if "介绍" in basename:
            return _load_introduction_json(read_path)
        return json_loader(read_path)
    return []


class FileLoader:
    """文件加载器：带 MD5 缓存，按扩展名加载为 Document 列表。"""

    def __init__(self):
        # 缓存：abs_path -> (documents, md5_hex)
        self._cache: dict[str, tuple[list[Document], str]] = {}

    def load_file(self, file_path: str) -> list[Document]:
        """
        加载单个文件为 Document 列表。
        - 若路径非绝对，则相对项目根解析。
        - 通过 MD5 判断是否变化，未变化则返回缓存。
        - 支持 .txt / .pdf / .json；其他扩展名返回空列表。
        """
        abs_path = file_path if os.path.isabs(file_path) else get_abs_path(file_path)
        if not os.path.isfile(abs_path):
            return []

        md5_hex = get_file_md5_hex(abs_path)
        if md5_hex is None:
            return []

        cached = self._cache.get(abs_path)
        if cached is not None and cached[1] == md5_hex:
            return cached[0]

        documents = _get_file_documents(abs_path)
        self._cache[abs_path] = (documents, md5_hex)
        return documents

    def load_files(self, file_paths: list[str]) -> list[Document]:
        """加载多个文件，合并为 Document 列表；依赖 load_file 的缓存与 MD5 逻辑。"""
        result: list[Document] = []
        for path in file_paths:
            result.extend(self.load_file(path))
        return result

    def clear_cache(self) -> None:
        """清空缓存，下次 load 将重新读取并计算 MD5。"""
        self._cache.clear()


if __name__ == "__main__":
    """
    测试示例：加载项目内真实文件，需在项目根目录执行。
    运行: python -m infrastructure.vector_store.file_loader

    测试文件：
    - data/web_structure/北邮校园/北邮保卫处/介绍0.json（介绍类 JSON，层级：讨论区/版面/介绍*.json）
    - data/raw/usr_uploads/usr.txt（用户上传文本）
    """
    loader = FileLoader()

    # 路径相对项目根
    intro_json = "data/raw/web_structure/北邮校园/北邮保卫处/介绍0.json"
    user_txt = "data/raw/usr_uploads/usr.txt"

    # 1）加载介绍 JSON（注意层级：北邮校园=讨论区，北邮保卫处=版面）
    docs_intro = loader.load_file(intro_json)
    print(f"[测试] 介绍 JSON 加载: {len(docs_intro)} 条 (应为 1 条)")
    assert len(docs_intro) >= 1, "介绍0.json 应至少解析出 1 条 Document"
    d = docs_intro[0]
    print(f"  层级 metadata: section={d.metadata.get('section')!r}, board={d.metadata.get('board')!r}")
    assert d.metadata.get("section") == "北邮校园"
    assert d.metadata.get("board") == "北邮保卫处"
    assert "开版公告" in d.page_content or "title" in d.page_content.lower()
    print(f"  首条内容前 80 字: {d.page_content[:80]!r}...")

    # 2）加载用户上传 txt
    docs_usr = loader.load_file(user_txt)
    print(f"[测试] 用户 txt 加载: {len(docs_usr)} 条")
    assert len(docs_usr) == 1
    print(f"  内容: {docs_usr[0].page_content!r}")
    assert "赛博理塘" in docs_usr[0].page_content

    # 3）load_files 合并加载
    all_docs = loader.load_files([intro_json, user_txt])
    print(f"[测试] load_files([介绍JSON, usr.txt]): 共 {len(all_docs)} 条")
    assert len(all_docs) == len(docs_intro) + len(docs_usr)

    # 4）缓存：再次加载同一文件应命中缓存
    docs_intro2 = loader.load_file(intro_json)
    assert docs_intro2 is docs_intro or (len(docs_intro2) == len(docs_intro) and docs_intro2[0].page_content == docs_intro[0].page_content)
    print("[测试] 缓存命中 OK")

    # 5）不存在的路径
    empty = loader.load_file("data/nonexistent.txt")
    assert len(empty) == 0
    print("[测试] 不存在文件返回空列表 OK")

    print("\n[测试] 全部通过。")
