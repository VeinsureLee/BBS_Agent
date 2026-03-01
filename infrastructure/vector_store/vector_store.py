"""
Vector Store：向量库服务。
1. 加载给定路径文件（FileLoader）
2. 生成介绍总结（可选，summarize=False 则直接入库）
3. 存入向量库（Chroma + 分块）
"""
import os
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_here))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from infrastructure.vector_store.file_loader import FileLoader
from infrastructure.vector_store.summarizer import summarize_with_prompt
from infrastructure.model_factory.factory import embed_model
from utils.prompt_loader import load_prompt_generate
from utils.config_handler import load_json_config
from utils.path_tool import get_abs_path
from utils.logger_handler import logger
from utils import list_allowed_files_recursive, get_file_md5_hex
from infrastructure.vector_store.md5 import load_recorded, save_recorded, rel_path_to_section_board


def _default_vector_config() -> dict:
    return load_json_config(default_path="config/vector_store/static.json")


class VectorStore:
    """向量库服务：加载文件 → 生成帖子介绍总结 → 存入向量库。"""

    def __init__(self, config_path: str | None = None):
        """
        config_path: 向量库配置 JSON 路径，不传则使用 config/vector_store/store.json。
        """
        cfg = (
            load_json_config(config_path=config_path)
            if config_path
            else _default_vector_config()
        )
        self._config = cfg
        self._file_loader = FileLoader()
        persist_dir = get_abs_path(cfg.get("persist_directory", "vector_db/store"))
        self._persist_dir = persist_dir
        self._vector_store = Chroma(
            collection_name=cfg.get("collection_name", "usr_knowledge_base"),
            embedding_function=embed_model,
            persist_directory=persist_dir,
        )
        print(f"[VectorStore] 向量库路径: {persist_dir} | collection: {cfg.get('collection_name', 'usr_knowledge_base')}", flush=True)
        chunk_size = cfg.get("chunk_size", 200)
        chunk_overlap = cfg.get("chunk_overlap", 20)
        separators = cfg.get("separators", ["\n\n", "\n", "。", "！", "？", " ", ""])
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
            length_function=len,
        )

    def _enrich_doc_metadata(self, doc: Document) -> None:
        section = doc.metadata.get("section")
        board = doc.metadata.get("board")
        title = doc.metadata.get("title", "")
        if section is not None and board is not None:
            doc.metadata["hierarchy"] = f"{section} > {board} > {title or '介绍'}"
            doc.metadata["doc_type"] = "介绍"

    def _delete_vectors_by_board(self, section_name: str, board_name: str) -> None:
        """按版面元数据删除该版面在向量库中的全部向量。"""
        try:
            self._vector_store._collection.delete(
                where={"section": section_name, "board": board_name}
            )
        except Exception as e:
            logger.warning("[VectorStore] 按版面删除向量时出错: %s", e)

    @staticmethod
    def _group_docs_by_board(docs: list[Document]) -> dict[tuple[str, str], list[Document]]:
        """按 (section, board) 将文档分组。"""
        by_board: dict[tuple[str, str], list[Document]] = defaultdict(list)
        for d in docs:
            key = (d.metadata.get("section") or "", d.metadata.get("board") or "")
            by_board[key].append(d)
        return by_board

    def _summarize_one_board(
        self,
        section_name: str,
        board_name: str,
        group: list[Document],
        prompt_template: str,
    ) -> Document | None:
        """单个版面：合并该版面下所有文档内容后做一次总结，返回一条 Document。供多线程调用。"""
        parts = [(d.page_content or "").strip() for d in group if (d.page_content or "").strip()]
        if not parts:
            return None
        combined = "\n\n---\n\n".join(parts)
        try:
            content = summarize_with_prompt(
                combined, prompt_template,
                section_name=section_name or "未知讨论区",
                board_name=board_name or "未知版面",
            )
        except Exception as e:
            print(f"[总结失败，使用原文入库] {section_name}/{board_name} | {type(e).__name__}: {e}", flush=True)
            content = combined
        if not content.strip():
            return None
        sample = group[0]
        new_doc = Document(
            page_content=content.strip(),
            metadata={"section": section_name, "board": board_name, **{k: v for k, v in sample.metadata.items() if k in ("source_file",)}},
        )
        self._enrich_doc_metadata(new_doc)
        return new_doc

    def _summarize_boards(
        self,
        by_board: dict[tuple[str, str], list[Document]],
        prompt_template: str,
        max_workers: int = 1,
    ) -> list[Document]:
        """按版面合并并总结。max_workers>1 时多线程，每个线程处理一个版面（该版面下所有 json 合并后总结）。"""
        items = [(sn, bn, group) for (sn, bn), group in by_board.items()]
        if not items:
            return []
        if max_workers <= 1:
            to_add: list[Document] = []
            for section_name, board_name, group in items:
                doc = self._summarize_one_board(section_name, board_name, group, prompt_template)
                if doc is not None:
                    to_add.append(doc)
            return to_add
        total, done = len(items), [0]
        lock = threading.Lock()
        to_add = []

        def run_one(args: tuple[str, str, list[Document]]) -> Document | None:
            sn, bn, grp = args
            doc = self._summarize_one_board(sn, bn, grp, prompt_template)
            with lock:
                done[0] += 1
                print(f"[介绍处理] ({done[0]}/{total}) {sn} / {bn} 总结完成", flush=True)
            return doc

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_one, (sn, bn, group)) for sn, bn, group in items]
            for fut in as_completed(futures):
                doc = fut.result()
                if doc is not None:
                    to_add.append(doc)
        return to_add

    def get_retriever(self):
        """返回向量库检索器，k 从配置读取。"""
        k = self._config.get("k", 10)
        return self._vector_store.as_retriever(search_kwargs={"k": k})

    def load_document(
        self,
        file_path: str | list[str],
        summarize: bool = True,
        use_splitter: bool = True,
    ) -> list[Document]:
        """加载给定路径文件。summarize=True 时按版面合并后总结；summarize=False 时直接入库。"""
        paths = [file_path] if isinstance(file_path, str) else file_path
        all_docs: list[Document] = []
        for path in paths:
            docs = self._file_loader.load_file(path)
            all_docs.extend(docs)
            if docs:
                s, b = docs[0].metadata.get("section", ""), docs[0].metadata.get("board", "")
                print(f"[加载] {path} -> {len(docs)} 条 | {s} / {b}", flush=True)
        if not all_docs:
            logger.warning("[VectorStore] 未加载到任何文档，请检查路径与文件类型。")
            return []
        prompt_template = load_prompt_generate()
        if summarize:
            by_board = self._group_docs_by_board(all_docs)
            to_add = self._summarize_boards(by_board, prompt_template)
            print(f"[介绍处理] 按版面共同总结，共 {len(to_add)} 条完成", flush=True)
        else:
            to_add = []
            for d in all_docs:
                content = (d.page_content or "").strip()
                if not content:
                    continue
                new_doc = Document(page_content=content, metadata=dict(d.metadata))
                self._enrich_doc_metadata(new_doc)
                to_add.append(new_doc)
            print(f"[直接入库] 共 {len(to_add)} 条，不做总结", flush=True)
        if use_splitter and to_add:
            to_add = self._splitter.split_documents(to_add)
        if to_add:
            for d in to_add:
                if "hierarchy" not in d.metadata and d.metadata.get("section") is not None:
                    self._enrich_doc_metadata(d)
            try:
                self._vector_store.add_documents(to_add)
                logger.info("[VectorStore] 已入库 %s 条文档。", len(to_add))
                print(f"[入库成功] 本次入库 {len(to_add)} 条 -> {self._persist_dir}", flush=True)
            except Exception as e:
                logger.exception("[VectorStore] 入库失败: %s", e)
                print(f"[入库失败] {type(e).__name__}: {e}", flush=True)
                raise
        else:
            print("[入库跳过] 无有效文档可入库", flush=True)
        return to_add

    def _split_and_add(self, docs: list[Document], use_splitter: bool) -> list[Document]:
        """按版面分组、分块、补全元数据并写入向量库。返回分块后的列表。"""
        for d in docs:
            if "hierarchy" not in d.metadata and d.metadata.get("section") is not None:
                self._enrich_doc_metadata(d)
        by_board: dict[tuple[str, str], list[Document]] = defaultdict(list)
        for d in docs:
            by_board[(d.metadata.get("section") or "", d.metadata.get("board") or "")].append(d)
        result: list[Document] = []
        for (_, __), group in by_board.items():
            if use_splitter and group:
                split_docs = self._splitter.split_documents(group)
                for d in split_docs:
                    if "hierarchy" not in d.metadata and d.metadata.get("section") is not None:
                        self._enrich_doc_metadata(d)
                result.extend(split_docs)
            else:
                result.extend(group)
        if not result:
            return result
        print(f"[阶段3] 分块完成，共 {len(result)} 条。正在写入向量库…", flush=True)
        batch_size = max(1, int(self._config.get("ingest_batch_size", 100)))
        for i in range(0, len(result), batch_size):
            self._vector_store.add_documents(result[i : i + batch_size])
            print(f"[入库中] 已写入 {min(i + batch_size, len(result))}/{len(result)} 条", flush=True)
        logger.info("[VectorStore] 已入库 %s 条文档。", len(result))
        print(f"[入库成功] 共 {len(result)} 条 -> {self._persist_dir}", flush=True)
        return result

    def load_documents(
        self,
        dir_path: str,
        summarize: bool = True,
        use_splitter: bool = True,
        max_workers: int | None = None,
    ) -> list[Document]:
        """递归加载目录。配置了 md5_hex_store 时做 MD5 增量：仅对变更/新增版面的文件重新总结并更新向量，无变更则跳过。"""
        abs_dir = dir_path if os.path.isabs(dir_path) else get_abs_path(dir_path)
        if not os.path.isdir(abs_dir):
            logger.warning("[VectorStore] 路径不是目录: %s", dir_path)
            return []
        allowed = self._config.get("allow_knowledge_file_type", ["txt", "pdf", "json"])
        suffix_tuple = tuple(f".{t}" if not t.startswith(".") else t for t in allowed)
        file_list = list_allowed_files_recursive(abs_dir, suffix_tuple)
        if not file_list:
            logger.warning("[VectorStore] 未找到允许类型的文件: %s", dir_path)
            return []
        rel_paths = [os.path.relpath(p, get_abs_path(".")).replace("\\", "/") for p in file_list]
        workers = max(1, int(max_workers if max_workers is not None else 8))
        md5_store_path = self._config.get("md5_hex_store")
        if md5_store_path:
            md5_store_path = get_abs_path(md5_store_path)

        # MD5 增量：计算当前文件 MD5，与记录比对得到需更新的版面
        current: dict[str, str] = {}
        for rel in rel_paths:
            abs_p = get_abs_path(rel)
            if os.path.isfile(abs_p):
                h = get_file_md5_hex(abs_p)
                if h is not None:
                    current[rel] = h
        recorded = load_recorded(md5_store_path) if md5_store_path else {}
        dirty_boards: set[tuple[str, str]] = set()
        if md5_store_path:
            for rel in list(recorded):
                if rel not in current:
                    sb = rel_path_to_section_board(rel)
                    if sb:
                        dirty_boards.add(sb)
                    del recorded[rel]
            for rel in current:
                if recorded.get(rel) != current[rel]:
                    sb = rel_path_to_section_board(rel)
                    if sb:
                        dirty_boards.add(sb)
            if not dirty_boards and set(recorded.keys()) == set(current.keys()) and all(recorded.get(r) == current.get(r) for r in current):
                for k in current:
                    recorded[k] = current[k]
                save_recorded(recorded, md5_store_path)
                print("[MD5] 无文件变更，跳过加载与入库", flush=True)
                return []

        all_docs: list[Document] = []
        for path in rel_paths:
            docs = self._file_loader.load_file(path)
            if docs:
                s, b = docs[0].metadata.get("section", ""), docs[0].metadata.get("board", "")
                print(f"[加载] {path} -> {len(docs)} 条 | {s} / {b}", flush=True)
                all_docs.extend(docs)
            else:
                print(f"[加载] {path} -> 0 条 (跳过)", flush=True)
        if not all_docs:
            return []

        by_board = self._group_docs_by_board(all_docs)
        if md5_store_path and dirty_boards:
            by_board = {k: v for k, v in by_board.items() if k in dirty_boards}
            for (sn, bn) in dirty_boards:
                self._delete_vectors_by_board(sn, bn)
            print(f"[MD5] 本批次仅更新 {len(dirty_boards)} 个版面", flush=True)

        if summarize:
            prompt_template = load_prompt_generate()
            all_to_add = self._summarize_boards(by_board, prompt_template, max_workers=workers)
            print(f"[介绍处理] 按版面多线程共同总结，共 {len(all_to_add)} 个版面完成 (workers={workers})", flush=True)
        else:
            all_to_add = []
            for (_, __), group in by_board.items():
                for d in group:
                    content = (d.page_content or "").strip()
                    if not content:
                        continue
                    new_doc = Document(page_content=content, metadata=dict(d.metadata))
                    self._enrich_doc_metadata(new_doc)
                    all_to_add.append(new_doc)
            print(f"[直接入库] 共 {len(all_to_add)} 条，不做总结", flush=True)

        if not all_to_add:
            print("[入库跳过] 未产生任何文档", flush=True)
            if md5_store_path:
                for k in current:
                    recorded[k] = current[k]
                save_recorded(recorded, md5_store_path)
            return []
        n_boards = len(set((d.metadata.get("section"), d.metadata.get("board")) for d in all_to_add))
        print(f"[阶段3] 共 {n_boards} 个版面，分块并入库…", flush=True)
        result = self._split_and_add(all_to_add, use_splitter)
        if md5_store_path:
            for k in current:
                recorded[k] = current[k]
            save_recorded(recorded, md5_store_path)
            print(f"[MD5] 已更新记录 -> {md5_store_path}", flush=True)
        return result


if __name__ == "__main__":
    # 调试：多线程总结并入库；遇 KeyError('request') 时在 summarizer 内重试直至正确总结
    vs = VectorStore(config_path="config/vector_store/dynamic.json")
    root = "data/web_structure"
    max_workers = 1024  # 多线程总结，可按机器与 API 限流调整
    added = vs.load_documents(root, summarize=False, use_splitter=True, max_workers=max_workers)
    print(f"[调试] 从 {root} 加载并入库 {len(added)} 条文档（多线程数={max_workers}）。")
    if added:
        d0 = added[0]
        print(f"[调试] 首条文档 metadata 层级信息: {d0.metadata}")
        print(f"[调试] 首条内容预览: {d0.page_content[:120]}...")
    retriever = vs.get_retriever()
    test_query = "有哪些允许匿名回答的版面？"
    hits = retriever.invoke(test_query)
    print(f"[调试] 检索「{test_query}」返回 {len(hits)} 条。")
    for i, h in enumerate(hits):
        print(f"  [{i+1}] hierarchy={h.metadata.get('hierarchy')} | {h.page_content}...")
