"""
向量库服务：Chroma 的创建、检索与知识库同步。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (
    load_chroma_config,
    get_abs_path,
    list_allowed_files_recursive,
    get_file_md5_hex,
    logger,
)
from langchain_chroma import Chroma
from langchain_core.documents import Document

from model import embed_model
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.knowledge_loader import (
    MD5_RECORD_SEP,
    norm_rel_path,
    load_recorded,
    save_recorded,
    get_file_documents,
)


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

    def load_document(self) -> None:
        """
        从 data_path 下递归读取所有子目录（如以版面名称命名的文件夹）内的数据文件，
        转为向量存入向量库。按「相对路径|MD5」记录已处理文件；能识别文件变更或删除，
        删除向量库中对应旧数据并重新加载新内容。
        说明：若从仅记录 MD5 的旧版本升级，建议先清空 chroma_db 与 md5 记录文件再首次运行，以保证与磁盘一致。
        """
        chroma_cfg = load_chroma_config()
        data_abs = get_abs_path(chroma_cfg["data_path"])
        md5_store_path = get_abs_path(chroma_cfg["md5_hex_store"])
        allowed_types = tuple(chroma_cfg["allow_knowledge_file_type"])

        all_paths = list_allowed_files_recursive(data_abs, allowed_types)
        current: dict[str, str] = {}
        for path in all_paths:
            md5_hex = get_file_md5_hex(path)
            if md5_hex is not None:
                current[norm_rel_path(path, data_abs)] = md5_hex

        recorded = load_recorded(md5_store_path, MD5_RECORD_SEP)

        for rel_path in list(recorded.keys()):
            if rel_path not in current:
                logger.info(f"[加载知识库]文件已删除或移出，移除向量: {rel_path}")
                delete_vectors_by_source(self.vector_store, rel_path)
                del recorded[rel_path]

        for path in all_paths:
            rel_path = norm_rel_path(path, data_abs)
            md5_hex = current.get(rel_path)
            if md5_hex is None:
                continue
            prev_md5 = recorded.get(rel_path)
            if prev_md5 == md5_hex:
                logger.info(f"[加载知识库]{path} 内容未变化，跳过")
                continue

            try:
                if rel_path in recorded:
                    logger.info(f"[加载知识库]{path} 内容已变更，先删除旧向量再重新加载")
                    delete_vectors_by_source(self.vector_store, rel_path)

                documents = get_file_documents(path)
                if not documents:
                    logger.warning(f"[加载知识库]{path} 内没有有效文本内容，跳过")
                    recorded[rel_path] = md5_hex
                    continue

                split_document = self.spliter.split_documents(documents)
                if not split_document:
                    logger.warning(f"[加载知识库]{path} 分片后没有有效文本内容，跳过")
                    continue

                for doc in split_document:
                    doc.metadata["source_file"] = rel_path
                self.vector_store.add_documents(split_document)
                recorded[rel_path] = md5_hex
                logger.info(f"[加载知识库]{path} 内容加载成功")
            except Exception as e:
                logger.error(f"[加载知识库]{path} 加载失败：{str(e)}", exc_info=True)

        save_recorded(recorded, md5_store_path, MD5_RECORD_SEP)


if __name__ == "__main__":
    vs = VectorStoreService()
    vs.load_document()
    retriever = vs.get_retriever()
    res = retriever.invoke("扫地")
    for r in res:
        print(r.page_content)
        print("-" * 20)
