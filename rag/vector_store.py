"""
向量库服务：Chroma 的创建、检索与知识库同步。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (
    load_chroma_config,
    get_abs_path,
    get_file_md5_hex,
    logger,
)
from langchain_chroma import Chroma
from langchain_core.documents import Document

from model import embed_model
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.knowledge_loader import (
    MD5_RECORD_SEP,
    INTRODUCTIONS_PREFIX,
    norm_rel_path,
    load_recorded,
    save_recorded,
    get_file_documents,
    list_files_by_chroma_config,
    list_introduction_files,
    get_introduction_file_documents,
)

# 讨论区/版面说明在向量库中的相对路径前缀（data/boards_guide 下每版面一个 JSON）
BOARD_GUIDE_PREFIX = "board_guide/boards_guide/"


def delete_vectors_by_source(vector_store: Chroma, rel_path: str) -> None:
    """按 source_file 元数据删除该文件对应的所有向量。"""
    try:
        vector_store._collection.delete(where={"source_file": rel_path})
    except Exception as e:
        logger.warning(f"[加载知识库]删除向量 rel_path={rel_path} 时出错: {e}")


class VectorStoreService:
    def __init__(self):
        cfg = load_chroma_config()
        self.vector_store = Chroma(
            collection_name=cfg["collection_name"],
            embedding_function=embed_model,
            persist_directory=cfg["persist_directory"],
        )
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=cfg["chunk_size"],
            chunk_overlap=cfg["chunk_overlap"],
            separators=cfg["separators"],
            length_function=len,
        )

    def get_retriever(self):
        return self.vector_store.as_retriever(
            search_kwargs={"k": load_chroma_config()["k"]}
        )

    def load_document(self, _retry_after_rebuild: bool = False, verbose: bool = False) -> None:
        """
        按 chroma 配置（info_path、section_info）加载知识库文件，带层级信息并更新向量库。
        1）按 config 递归列出文件，为每条文档写入 source_file 与层级元数据（版面/子版面/帖子题目、回复数等）；
        2）通过 MD5 检测文件与帖子变化，仅对变更或新增文件更新向量，对已删除文件移除对应向量；
        3）若加载过程因向量库或 MD5 异常出错，则清空向量库与 MD5 记录后重试一次全量加载。
        verbose=True 时在控制台打印每个文件的处理结果。
        """
        chroma_cfg = load_chroma_config()
        md5_store_path = get_abs_path(chroma_cfg["md5_hex_store"])

        try:
            self._load_document_impl(chroma_cfg, md5_store_path, verbose=verbose)
        except Exception as e:
            logger.error(f"[加载知识库]加载过程出错：{str(e)}", exc_info=True)
            if not _retry_after_rebuild:
                logger.info("[加载知识库]将清空向量库与 MD5 记录后重试一次全量加载")
                force_rebuild_knowledge_base()
                self.vector_store = Chroma(
                    collection_name=chroma_cfg["collection_name"],
                    embedding_function=embed_model,
                    persist_directory=chroma_cfg["persist_directory"],
                )
                self._load_document_impl(chroma_cfg, md5_store_path, verbose=verbose)
            else:
                raise

    def _enrich_doc_metadata(self, doc: Document, rel_path: str) -> None:
        """为文档写入 source_file 与层级信息（版面/子版面/题目/回复数或层级路径）。"""
        doc.metadata["source_file"] = rel_path
        section = doc.metadata.get("section")
        if section is not None:
            board = doc.metadata.get("board", "")
            title = doc.metadata.get("title", "")
            reply_count = doc.metadata.get("reply_count", 0)
            doc.metadata["hierarchy"] = f"{section} > {board} > {title}"
            doc.metadata["reply_count"] = reply_count
        else:
            doc.metadata["hierarchy_path"] = rel_path

    def _load_document_impl(self, chroma_cfg: dict, md5_store_path: str, verbose: bool = False) -> None:
        """实际执行：按配置列举文件、比对 MD5、更新向量库。verbose 为 True 时打印每条处理信息。"""
        file_list = list_files_by_chroma_config(chroma_cfg)
        current: dict[str, str] = {}
        for abs_path, rel_path in file_list:
            md5_hex = get_file_md5_hex(abs_path)
            if md5_hex is not None:
                current[rel_path] = md5_hex

        if not os.path.exists(md5_store_path) and (file_list or chroma_cfg.get("introductions")):
            logger.info("[加载知识库]MD5 记录不存在但向量库可能已有数据，先清空向量库再全量加载，避免重复写入")
            if verbose:
                print("[加载知识库] MD5 记录不存在，先清空向量库再全量加载", flush=True)
            force_rebuild_knowledge_base()
            self.vector_store = Chroma(
                collection_name=chroma_cfg["collection_name"],
                embedding_function=embed_model,
                persist_directory=chroma_cfg["persist_directory"],
            )

        recorded = load_recorded(md5_store_path, MD5_RECORD_SEP)

        if verbose and not file_list:
            print("  （无知识库文件）", flush=True)

        for rel_path in list(recorded.keys()):
            if rel_path.startswith(INTRODUCTIONS_PREFIX):
                continue
            if rel_path.startswith(BOARD_GUIDE_PREFIX):
                continue
            if rel_path not in current:
                logger.info(f"[加载知识库]文件已删除或移出，移除向量: {rel_path}")
                if verbose:
                    print(f"  [移除] {rel_path}", flush=True)
                delete_vectors_by_source(self.vector_store, rel_path)
                del recorded[rel_path]

        for abs_path, rel_path in file_list:
            md5_hex = current.get(rel_path)
            if md5_hex is None:
                continue
            prev_md5 = recorded.get(rel_path)
            if prev_md5 == md5_hex:
                logger.debug(f"[加载知识库]{rel_path} 内容未变化，跳过")
                if verbose:
                    print(f"  [跳过] {rel_path}（未变化）", flush=True)
                continue

            try:
                if rel_path in recorded:
                    logger.info(f"[加载知识库]{rel_path} 内容已变更，先删除旧向量再重新加载")
                    if verbose:
                        print(f"  [更新] {rel_path}（先删后载）", flush=True)
                    delete_vectors_by_source(self.vector_store, rel_path)

                documents = get_file_documents(abs_path)
                if not documents:
                    logger.warning(f"[加载知识库]{rel_path} 内没有有效文本内容，跳过")
                    if verbose:
                        print(f"  [跳过] {rel_path}（无有效内容）", flush=True)
                    recorded[rel_path] = md5_hex
                    continue

                for doc in documents:
                    self._enrich_doc_metadata(doc, rel_path)
                split_document = self.spliter.split_documents(documents)
                if not split_document:
                    logger.warning(f"[加载知识库]{rel_path} 分片后没有有效文本内容，跳过")
                    if verbose:
                        print(f"  [跳过] {rel_path}（分片后无内容）", flush=True)
                    continue

                for doc in split_document:
                    if "source_file" not in doc.metadata:
                        self._enrich_doc_metadata(doc, rel_path)
                self.vector_store.add_documents(split_document)
                recorded[rel_path] = md5_hex
                logger.info(f"[加载知识库]{rel_path} 内容加载成功")
                if verbose:
                    print(f"  [加载] {rel_path}（{len(split_document)} 个分片）", flush=True)
            except Exception as e:
                logger.error(f"[加载知识库]{rel_path} 加载失败：{str(e)}", exc_info=True)
                raise

        save_recorded(recorded, md5_store_path, MD5_RECORD_SEP)

    def load_board_guide(self, guide_dir: str = None, verbose: bool = False) -> None:
        """
        将 data/boards_guide 下每个讨论区/版面对应的 JSON 纳入向量库。
        按「讨论区、版面、发言规则、帖子类型」生成文本并向量化，MD5 增量：仅变更的版面更新。
        guide_dir 不传时使用 data/boards_guide 目录。
        verbose=True 时在控制台打印处理结果。
        """
        if guide_dir is None:
            try:
                from agent.tools.init_tools.prompts_tools import get_boards_guide_dir
                guide_dir = str(get_boards_guide_dir().resolve())
            except Exception:
                guide_dir = get_abs_path("data/boards_guide")
        root = os.path.abspath(guide_dir)
        if not os.path.isdir(root):
            logger.warning("[加载知识库]讨论区/版面说明目录不存在，跳过: %s", root)
            if verbose:
                print(f"  [跳过] 讨论区/版面说明目录不存在: {root}", flush=True)
            return
        import json
        file_list = []
        for sec_dir in os.listdir(root):
            sec_path = os.path.join(root, sec_dir)
            if not os.path.isdir(sec_path):
                continue
            for fname in os.listdir(sec_path):
                if not fname.endswith(".json"):
                    continue
                abs_path = os.path.join(sec_path, fname)
                if not os.path.isfile(abs_path):
                    continue
                rel_path = f"{BOARD_GUIDE_PREFIX}{sec_dir}/{fname}"
                file_list.append((abs_path, rel_path))
        chroma_cfg = load_chroma_config()
        md5_store_path = get_abs_path(chroma_cfg["md5_hex_store"])
        recorded = load_recorded(md5_store_path, MD5_RECORD_SEP)
        current = {}
        for abs_path, rel_path in file_list:
            md5_hex = get_file_md5_hex(abs_path)
            if md5_hex is not None:
                current[rel_path] = md5_hex
        for rel_path in list(recorded.keys()):
            if rel_path.startswith(BOARD_GUIDE_PREFIX) and rel_path not in current:
                logger.info("[加载知识库]版面说明已删除，移除向量: %s", rel_path)
                if verbose:
                    print(f"  [移除] {rel_path}", flush=True)
                delete_vectors_by_source(self.vector_store, rel_path)
                del recorded[rel_path]
        for abs_path, rel_path in file_list:
            md5_hex = current.get(rel_path)
            if md5_hex is None:
                continue
            prev_md5 = recorded.get(rel_path)
            if prev_md5 == md5_hex:
                logger.debug("[加载知识库]%s 内容未变化，跳过", rel_path)
                if verbose:
                    print(f"  [跳过] {rel_path}（未变化）", flush=True)
                continue
            try:
                if rel_path in recorded:
                    logger.info("[加载知识库]%s 内容已变更，先删除旧向量再重新加载", rel_path)
                    if verbose:
                        print(f"  [更新] {rel_path}（先删后载）", flush=True)
                    delete_vectors_by_source(self.vector_store, rel_path)
                with open(abs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                section_name = (data.get("section_name") or "").strip() or "未命名讨论区"
                board_name = (data.get("board_name") or "").strip() or "未命名版面"
                rules = (data.get("rules") or "").strip() or "常规发帖，需遵守版规。"
                post_type = (data.get("post_type") or "").strip() or f"与「{board_name}」主题相关的讨论与信息。"
                text = (
                    f"讨论区：{section_name}\n"
                    f"版面：{board_name}\n"
                    f"发言规则：{rules}\n"
                    f"帖子类型：{post_type}"
                )
                if not text.strip():
                    recorded[rel_path] = md5_hex
                    if verbose:
                        print(f"  [跳过] {rel_path}（内容为空）", flush=True)
                    continue
                documents = [
                    Document(
                        page_content=text,
                        metadata={"source_file": rel_path, "doc_type": "board_guide", "section": section_name, "board": board_name},
                    )
                ]
                split_document = self.spliter.split_documents(documents)
                if not split_document:
                    recorded[rel_path] = md5_hex
                    if verbose:
                        print(f"  [跳过] {rel_path}（分片后无内容）", flush=True)
                    continue
                for doc in split_document:
                    if "source_file" not in doc.metadata:
                        doc.metadata["source_file"] = rel_path
                        doc.metadata["doc_type"] = "board_guide"
                        doc.metadata["section"] = section_name
                        doc.metadata["board"] = board_name
                self.vector_store.add_documents(split_document)
                recorded[rel_path] = md5_hex
                logger.info("[加载知识库]%s 内容加载成功", rel_path)
                if verbose:
                    print(f"  [加载] {rel_path}（{section_name} / {board_name}）", flush=True)
            except Exception as e:
                logger.error("[加载知识库]%s 加载失败：%s", rel_path, str(e), exc_info=True)
                raise
        save_recorded(recorded, md5_store_path, MD5_RECORD_SEP)

    def remove_introductions_vectors(self) -> None:
        """
        移除向量库中所有「置顶帖子全文」（source_file 以 introductions/ 开头）的向量。
        配合「仅保存精简版面说明」策略，避免保留冗余的置顶全文。
        """
        chroma_cfg = load_chroma_config()
        md5_store_path = get_abs_path(chroma_cfg["md5_hex_store"])
        recorded = load_recorded(md5_store_path, MD5_RECORD_SEP)
        removed = 0
        for rel_path in list(recorded.keys()):
            if rel_path.startswith(INTRODUCTIONS_PREFIX):
                try:
                    delete_vectors_by_source(self.vector_store, rel_path)
                    del recorded[rel_path]
                    removed += 1
                    logger.info("[加载知识库]已移除置顶全文向量: %s", rel_path)
                except Exception as e:
                    logger.warning("[加载知识库]移除向量 %s 时出错: %s", rel_path, e)
        if removed:
            save_recorded(recorded, md5_store_path, MD5_RECORD_SEP)

    def load_introductions(self, introductions_root: str = None) -> None:
        """
        将「介绍」目录下所有 介绍*.json 纳入向量库（MD5 增量：仅变更/新增的更新，已删除的移除）。
        introductions_root 不传时从 chroma 配置的 introductions.path 或 config 的 get_web_structure_introductions_root 取得。
        """
        chroma_cfg = load_chroma_config()
        md5_store_path = get_abs_path(chroma_cfg["md5_hex_store"])
        if introductions_root is None:
            intro_cfg = chroma_cfg.get("introductions") or {}
            path_cfg = intro_cfg.get("path")
            if path_cfg:
                root_abs = get_abs_path(path_cfg)
            else:
                try:
                    from utils.config_handler import get_web_structure_introductions_root
                    root_abs = str(get_web_structure_introductions_root().resolve())
                except Exception:
                    logger.warning("[加载知识库]未配置 introductions 路径且无法读取 web_structure，跳过介绍向量化")
                    return
        else:
            root_abs = os.path.abspath(introductions_root)
        file_list = list_introduction_files(root_abs)
        current: dict[str, str] = {}
        for abs_path, rel_path in file_list:
            md5_hex = get_file_md5_hex(abs_path)
            if md5_hex is not None:
                current[rel_path] = md5_hex
        recorded = load_recorded(md5_store_path, MD5_RECORD_SEP)
        for rel_path in list(recorded.keys()):
            if rel_path.startswith(INTRODUCTIONS_PREFIX) and rel_path not in current:
                logger.info(f"[加载知识库]介绍文件已删除或移出，移除向量: {rel_path}")
                delete_vectors_by_source(self.vector_store, rel_path)
                del recorded[rel_path]
        for abs_path, rel_path in file_list:
            md5_hex = current.get(rel_path)
            if md5_hex is None:
                continue
            prev_md5 = recorded.get(rel_path)
            if prev_md5 == md5_hex:
                logger.debug(f"[加载知识库]{rel_path} 内容未变化，跳过")
                continue
            try:
                if rel_path in recorded:
                    logger.info(f"[加载知识库]{rel_path} 内容已变更，先删除旧向量再重新加载")
                    delete_vectors_by_source(self.vector_store, rel_path)
                documents = get_introduction_file_documents(abs_path, rel_path)
                if not documents:
                    logger.warning(f"[加载知识库]{rel_path} 内没有有效文本内容，跳过")
                    recorded[rel_path] = md5_hex
                    continue
                for doc in documents:
                    self._enrich_doc_metadata(doc, rel_path)
                split_document = self.spliter.split_documents(documents)
                if not split_document:
                    logger.warning(f"[加载知识库]{rel_path} 分片后没有有效文本内容，跳过")
                    recorded[rel_path] = md5_hex
                    continue
                for doc in split_document:
                    if "source_file" not in doc.metadata:
                        self._enrich_doc_metadata(doc, rel_path)
                self.vector_store.add_documents(split_document)
                recorded[rel_path] = md5_hex
                logger.info(f"[加载知识库]{rel_path} 内容加载成功")
            except Exception as e:
                logger.error(f"[加载知识库]{rel_path} 加载失败：{str(e)}", exc_info=True)
                raise
        save_recorded(recorded, md5_store_path, MD5_RECORD_SEP)


def force_rebuild_knowledge_base() -> None:
    """删除 chroma_db 与 md5 记录；调用方随后可再次执行 load_document 以全量重建。"""
    import shutil

    chroma_cfg = load_chroma_config()
    chroma_path = get_abs_path(chroma_cfg["persist_directory"])
    md5_path = get_abs_path(chroma_cfg["md5_hex_store"])
    if os.path.exists(chroma_path):
        shutil.rmtree(chroma_path, ignore_errors=True)
        logger.info(f"[清空知识库]已清空向量库目录: {chroma_path}")
    if os.path.exists(md5_path):
        os.remove(md5_path)
        logger.info(f"[清空MD5记录]已删除 MD5 记录文件: {md5_path}")


if __name__ == "__main__":
    if "--force-reload" in sys.argv:
        force_rebuild_knowledge_base()
    vs = VectorStoreService()
    vs.load_document()
    vs.load_board_guide()
    retriever = vs.get_retriever()
    query = "恋爱"
    res = retriever.invoke(query)
    print(f"[检索测试] 查询「{query}」返回 {len(res)} 条。")
    if len(res) == 0:
        print("[检索测试] 未命中任何文档。请使用 --force-reload 重建知识库后重试：")
        print(f"  python -m rag.vector_store --force-reload")
    for r in res:
        print(r.page_content)
        print("-" * 20)
    print("="*20)
    print(f"[检索测试] 查询「{query}」返回 {len(res)} 条。")
    print("="*20)
