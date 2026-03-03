"""
knowledge.stores 子包：BBS 知识库向量存储封装（Chroma），含动态帖、结构、用户数据三套库。

功能说明：
    - 动态帖子库（dynamic_store）：从 data/dynamic 递归加载帖子 JSON，转为 Document 写入 Chroma，MD5 去重；
      提供 init_dynamic_store、get_dynamic_store、get_dynamic_retriever、get_dynamic_vector_store。
    - 结构库（structure_store）：从 data/static 加载版面 JSON，按层级与字段拆成多条 Document 写入 Chroma，
      成功后更新 config/init.json 的 static_vector_store_status；
      提供 init_static_structure_store、get_static_structure_store、get_static_structure_retriever、get_static_structure_vector_store。
    - 用户库（usr_store）：按 config/vector_store/store.json 加载用户上传数据，更新 config/init.json 的 usr_vector_store_status；
      提供 init_usr_vector_store、get_usr_vector_store、get_usr_vector_store_retriever、get_usr_vector_store_vector_store。
    各 store 均提供单例访问；入参/出参详见各模块文件头注释。

主要接口入参/出参摘要：
    - init_dynamic_store(folder_path?, max_workers=4) -> bool
    - get_dynamic_store(chroma_cfg?) -> VectorStoreService
    - init_static_structure_store(static_folder_path?, max_workers=4) -> bool
    - get_static_structure_store(chroma_cfg?) -> VectorStoreService
    - init_usr_vector_store(folder_path?, max_workers=4) -> bool
    - get_usr_vector_store(chroma_cfg?) -> VectorStoreService
"""

from .dynamic_store import (
    init_dynamic_store,
    get_dynamic_store,
    get_dynamic_vector_store,
    get_dynamic_retriever,
)
from .structure_store import (
    init_static_structure_store,
    get_static_structure_store,
    get_static_structure_vector_store,
    get_static_structure_retriever,
)
from .usr_store import (
    init_usr_vector_store,
    get_usr_vector_store,
    get_usr_vector_store_vector_store,
    get_usr_vector_store_retriever,
)

__all__ = [
    "init_dynamic_store",
    "get_dynamic_store",
    "get_dynamic_vector_store",
    "get_dynamic_retriever",
    "init_static_structure_store",
    "get_static_structure_store",
    "get_static_structure_vector_store",
    "get_static_structure_retriever",
    "init_usr_vector_store",
    "get_usr_vector_store",
    "get_usr_vector_store_vector_store",
    "get_usr_vector_store_retriever",
]