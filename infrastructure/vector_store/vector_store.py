import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.config_handler import load_json_config
from utils.path_tool import get_abs_path
from utils.file_handler import list_allowed_files_recursive, get_file_md5_hex
from utils.logger_handler import logger

from langchain_chroma import Chroma
from langchain_core.documents import Document

from infrastructure.model_factory.factory import embed_model
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from .md5 import check_md5_hex, save_md5_hex
    from .file_loader import get_file_documents
except ImportError:
    from md5 import check_md5_hex, save_md5_hex
    from file_loader import get_file_documents


# 默认使用 store 配置（data/store）
DEFAULT_CHROMA_CONFIG_PATH = "config/vector_store/store.json"
STATIC_CHROMA_CONFIG_PATH = "config/vector_store/static.json"


class VectorStoreService:
    def __init__(self, chroma_cfg: dict | None = None):
        self.chroma_conf = chroma_cfg or load_json_config(default_path=DEFAULT_CHROMA_CONFIG_PATH)
        self.vector_store = Chroma(
            collection_name=self.chroma_conf["collection_name"],
            embedding_function=embed_model,
            persist_directory=self.chroma_conf["persist_directory"],
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=self.chroma_conf["chunk_size"],
            chunk_overlap=self.chroma_conf["chunk_overlap"],
            separators=self.chroma_conf["separators"],
            length_function=len,
        )

    def get_retriever(self):
        return self.vector_store.as_retriever(
            search_kwargs={"k": self.chroma_conf["k"]}
        )

    def load_document(self):
        """
        从数据文件夹内递归读取数据文件，转为向量存入向量库。
        使用文件 MD5 做去重。
        :return: None
        """
        md5_store_path = get_abs_path(self.chroma_conf["md5_hex_store"])
        data_abs = get_abs_path(self.chroma_conf["data_path"])
        allowed_types = tuple(self.chroma_conf["allow_knowledge_file_type"])

        if not os.path.isdir(data_abs):
            logger.warning(f"[加载知识库]{data_abs} 不是目录，跳过加载")
            return

        allowed_files_path: list[str] = list_allowed_files_recursive(
            data_abs,
            allowed_types,
        )

        for path in allowed_files_path:
            md5_hex = get_file_md5_hex(path)
            if md5_hex is None:
                continue

            if check_md5_hex(md5_hex, md5_store_path):
                logger.info(f"[加载知识库]{path} 内容已存在知识库内，跳过")
                continue

            try:
                documents: list[Document] = get_file_documents(path)

                if not documents:
                    logger.warning(f"[加载知识库]{path} 内没有有效文本内容，跳过")
                    continue

                split_document: list[Document] = self.spliter.split_documents(documents)

                if not split_document:
                    logger.warning(f"[加载知识库]{path} 分片后没有有效文本内容，跳过")
                    continue

                self.vector_store.add_documents(split_document)
                save_md5_hex(md5_hex, md5_store_path)

                logger.info(f"[加载知识库]{path} 内容加载成功")
            except Exception as e:
                logger.error(f"[加载知识库]{path} 加载失败：{str(e)}", exc_info=True)
                continue

    def load_document_batch(
        self,
        folder_path: str | None = None,
        max_workers: int = 4,
    ) -> None:
        """
        批量读取指定文件夹下所有符合要求的文件，多线程读取并向量化存储。
        使用文件 MD5 做去重；写入向量库与 MD5 记录时加锁保证线程安全。
        :param folder_path: 要扫描的文件夹路径，为 None 时使用配置中的 data_path
        :param max_workers: 线程池大小，默认 4
        :return: None
        """
        data_abs = get_abs_path(folder_path or self.chroma_conf["data_path"])
        md5_store_path = get_abs_path(self.chroma_conf["md5_hex_store"])
        allowed_types = tuple(self.chroma_conf["allow_knowledge_file_type"])

        if not os.path.isdir(data_abs):
            logger.warning(f"[批量加载知识库] {data_abs} 不是目录，跳过加载")
            return

        allowed_files_path: list[str] = list_allowed_files_recursive(
            data_abs,
            allowed_types,
        )
        if not allowed_files_path:
            logger.info(f"[批量加载知识库] {data_abs} 下没有符合类型的文件")
            return

        # 写入向量库与 MD5 时使用同一把锁，保证线程安全
        write_lock = threading.Lock()

        def process_one_file(path: str) -> tuple[str, list[Document], str] | None:
            """单文件处理：读取、分片，返回 (path, split_documents, md5_hex)，跳过则返回 None。"""
            md5_hex = get_file_md5_hex(path)
            if md5_hex is None:
                return None
            try:
                documents: list[Document] = get_file_documents(path)
                if not documents:
                    logger.warning(f"[批量加载知识库] {path} 内没有有效文本内容，跳过")
                    return None
                split_document: list[Document] = self.spliter.split_documents(documents)
                if not split_document:
                    logger.warning(f"[批量加载知识库] {path} 分片后没有有效文本内容，跳过")
                    return None
                return (path, split_document, md5_hex)
            except Exception as e:
                logger.error(f"[批量加载知识库] {path} 读取/分片失败：{str(e)}", exc_info=True)
                return None

        def add_to_store_and_save_md5(path: str, split_document: list[Document], md5_hex: str) -> None:
            with write_lock:
                if check_md5_hex(md5_hex, md5_store_path):
                    logger.info(f"[批量加载知识库] {path} 内容已存在知识库内，跳过")
                    return
                self.vector_store.add_documents(split_document)
                save_md5_hex(md5_hex, md5_store_path)
                logger.info(f"[批量加载知识库] {path} 内容加载成功")

        logger.info(f"[批量加载知识库] 共 {len(allowed_files_path)} 个文件，使用 {max_workers} 个线程")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_one_file, p): p for p in allowed_files_path}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    path, split_document, md5_hex = result
                    add_to_store_and_save_md5(path, split_document, md5_hex)
        logger.info("[批量加载知识库] 批量加载结束")


if __name__ == "__main__":
    # 加载 data/store 配置，将 data/store 下各元素写入向量库
    chroma_conf = load_json_config(default_path=DEFAULT_CHROMA_CONFIG_PATH)
    vs = VectorStoreService(chroma_cfg=chroma_conf)

    vs.load_document_batch(max_workers=1)

    retriever = vs.get_retriever()
    res = retriever.invoke("理塘")
    for r in res:
        print(r.page_content)
        print("-" * 20)
