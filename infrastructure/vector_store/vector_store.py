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
from utils import list_allowed_files_recursive


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

    def _summarize_and_enrich_docs(
        self, docs: list[Document], prompt_template: str, summarize: bool
    ) -> list[Document]:
        """对 docs 逐条可选总结、补全元数据，返回 to_add。总结失败时 print 并用原文入库。"""
        to_add: list[Document] = []
        for doc in docs:
            content = (doc.page_content or "").strip()
            if not content:
                continue
            section_name = doc.metadata.get("section", "") or ""
            board_name = doc.metadata.get("board", "") or ""
            if summarize:
                try:
                    content = summarize_with_prompt(
                        content, prompt_template,
                        section_name=section_name,
                        board_name=board_name,
                    )
                except Exception as e:
                    print(f"[总结失败，使用原文入库] {section_name}/{board_name} | {type(e).__name__}: {e}", flush=True)
            if not content.strip():
                continue
            new_doc = Document(page_content=content.strip(), metadata=dict(doc.metadata))
            self._enrich_doc_metadata(new_doc)
            to_add.append(new_doc)
        return to_add

    def _process_one_file(
        self, path: str, docs: list[Document], prompt_template: str, summarize: bool
    ) -> tuple[str, list[Document]]:
        to_add = self._summarize_and_enrich_docs(docs, prompt_template, summarize)
        return (path, to_add)

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
        """加载给定路径文件 → 可选总结 → 存入向量库。"""
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
        to_add = self._summarize_and_enrich_docs(all_docs, load_prompt_generate(), summarize)
        print(f"[介绍处理] 共 {len(to_add)} 条完成", flush=True)
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
        """递归加载目录 → 可选多线程总结 → 统一分块入库。summarize=False 则直接入库。"""
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
        workers = max(0, int(max_workers if max_workers is not None else 8))

        path_docs_list: list[tuple[str, list[Document]]] = []
        for path in rel_paths:
            docs = self._file_loader.load_file(path)
            if docs:
                s, b = docs[0].metadata.get("section", ""), docs[0].metadata.get("board", "")
                print(f"[加载] {path} -> {len(docs)} 条 | {s} / {b}", flush=True)
                path_docs_list.append((path, docs))
            else:
                print(f"[加载] {path} -> 0 条 (跳过)", flush=True)
        if not path_docs_list:
            return []

        prompt_template = load_prompt_generate()
        total, done = len(path_docs_list), [0]
        lock = threading.Lock()

        def run_one(item: tuple[str, list[Document]]) -> tuple[str, list[Document]]:
            path, docs = item
            out = self._process_one_file(path, docs, prompt_template, summarize)
            with lock:
                done[0] += 1
                _, to_add = out
                s = to_add[0].metadata.get("section", "") if to_add else ""
                b = to_add[0].metadata.get("board", "") if to_add else ""
                print(f"[介绍处理] ({done[0]}/{total}) {path} | {s} / {b} 总结完成", flush=True)
            return out

        if workers <= 1:
            all_to_add = []
            for item in path_docs_list:
                _, to_add = run_one(item)
                all_to_add.extend(to_add)
        else:
            all_to_add = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(run_one, item) for item in path_docs_list]
                for fut in as_completed(futures):
                    _, to_add = fut.result()
                    all_to_add.extend(to_add)

        if not all_to_add:
            print("[入库跳过] 阶段2 未产生任何文档", flush=True)
            return []
        n_boards = len(set((d.metadata.get("section"), d.metadata.get("board")) for d in all_to_add))
        print(f"[阶段3] 共 {n_boards} 个版面，分块并入库…", flush=True)
        return self._split_and_add(all_to_add, use_splitter)


if __name__ == "__main__":
    # 调试：多线程总结并入库；遇 KeyError('request') 时在 summarizer 内重试直至正确总结
    vs = VectorStore()
    root = "data/raw/web_structure"
    max_workers = 1024  # 多线程总结，可按机器与 API 限流调整
    added = vs.load_documents(root, summarize=True, use_splitter=True, max_workers=max_workers)
    print(f"[调试] 从 {root} 加载并入库 {len(added)} 条文档（多线程数={max_workers}）。")
    if added:
        d0 = added[0]
        print(f"[调试] 首条文档 metadata 层级信息: {d0.metadata}")
        print(f"[调试] 首条内容预览: {d0.page_content[:120]}...")
    retriever = vs.get_retriever()
    test_query = "开版公告"
    hits = retriever.invoke(test_query)
    print(f"[调试] 检索「{test_query}」返回 {len(hits)} 条。")
    for i, h in enumerate(hits):
        print(f"  [{i+1}] hierarchy={h.metadata.get('hierarchy')} | {h.page_content}...")
