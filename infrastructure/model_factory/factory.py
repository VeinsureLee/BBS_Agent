import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from abc import ABC, abstractmethod
from typing import Optional
from langchain_core.embeddings import Embeddings
from langchain_community.chat_models.tongyi import BaseChatModel
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.chat_models import ChatOllama
from utils.config_handler import load_json_config
from utils.env_handler import load_env

load_env()

_rag_cfg = lambda: load_json_config(default_path="config/model/rag.json")


def _is_ollama_model_name(value: str) -> bool:
    """判断是否为 Ollama 模型名（如 qwen2.5:7b），而非本地路径。"""
    if not value or not value.strip():
        return True
    s = value.strip()
    # 绝对路径（含盘符或 /）视为本地路径
    if os.path.isabs(s) or s.startswith("/") or (len(s) > 1 and s[1] == ":"):
        return False
    # 含 ":" 且像 Ollama 名（短、无路径分隔符）则视为 Ollama
    if ":" in s and os.path.sep not in s and "\\" not in s:
        return True
    # 否则若为已存在的本地目录，视为路径
    if os.path.isdir(s):
        return False
    # 默认为 Ollama 名（向后兼容）
    return True


def _chat_model_from_local_path(model_path: str):
    """从本地路径（ModelScope/HuggingFace 缓存目录）加载对话模型。"""
    path = os.path.abspath(os.path.expanduser(model_path))
    if not os.path.isdir(path):
        raise FileNotFoundError(f"本地模型路径不存在或不是目录: {path}")
    try:
        from langchain_huggingface import HuggingFacePipeline, ChatHuggingFace
    except ImportError:
        from langchain_community.llms import HuggingFacePipeline
        from langchain_community.chat_models.huggingface import ChatHuggingFace
    try:
        # from_model_id 支持本地路径（transformers 会从路径加载）
        llm = HuggingFacePipeline.from_model_id(
            model_id=path,
            task="text-generation",
            pipeline_kwargs={"max_new_tokens": 2048, "max_length": None},
            model_kwargs={"trust_remote_code": True},
        )
    except Exception:
        # 部分环境需手动构建 pipeline（如 ModelScope 缓存目录）
        from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
        tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(path, trust_remote_code=True)
        pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            max_new_tokens=2048,
            max_length=None,
        )
        llm = HuggingFacePipeline(pipeline=pipe)
    return ChatHuggingFace(llm=llm)


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass


class ChatModelFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        cfg = _rag_cfg()
        if not cfg.get("use_local_chat"):
            return ChatTongyi(model=cfg["chat_model_name"])
        local = (cfg.get("local_chat_model") or "qwen2.5:7b").strip()
        if _is_ollama_model_name(local):
            return ChatOllama(model=local)
        return _chat_model_from_local_path(local)


class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        cfg = _rag_cfg()
        if not cfg.get("use_local_embed"):
            return DashScopeEmbeddings(model=cfg["embedding_model_name"])
        # local_embed_model：可为 HuggingFace repo id（如 shibing624/text2vec-base-chinese）
        # 或本地目录路径（如 .../models--shibing624--text2vec-base-chinese/snapshots/<hash>）
        model_name = cfg.get("local_embed_model", "shibing624/text2vec-base-chinese")
        embed_path = os.path.abspath(os.path.expanduser(model_name.strip()))
        kwargs = {"model_name": model_name.strip()}
        if os.path.isdir(embed_path):
            kwargs["model_kwargs"] = {"local_files_only": True}
        return HuggingFaceEmbeddings(**kwargs)


chat_model = ChatModelFactory().generator()
embed_model = EmbeddingsFactory().generator()
