"""
版面标签生成：加载 prompts/prompt_generate.txt，调用 chat 模型生成各维度标签（JSON），
供知识库入库或检索使用。
"""
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict

_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_here))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from infrastructure.model_factory.factory import chat_model
from utils.prompt_loader import load_prompt_generate
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

RETRY_DELAYS = (1.0, 2.0, 3.0)
MAX_RETRIES = 1024
REQUEST_KEYERROR_MAX = 10000

# 期望的 JSON 顶层键（用于校验与写入 metadata）
TAG_KEYS = (
    "board_name", "section_name", "summary",
    "speech_rules", "post_types", "board_positioning",
    "target_audience", "content_style", "interaction_form",
)

# 原文中常见「简介」标记，用于 fallback 时提取版面简介
_INTRO_MARKERS = ("简介：", "简介:", "版面简介：", "版面简介:")

# 发信人/信区等行头，fallback 时若未匹配到简介则 strip 掉再截取
_HEADER_LINE_PATTERN = re.compile(
    r"^(?:标题：|作者：|时间：|回复数：|链接：|发信人:.*?站内|标\s*题:.*|发信站:.*)$",
    re.MULTILINE,
)


def _fallback_summary_from_raw(combined: str, max_len: int = 400) -> str:
    """
    从「原文」中提取更合适的版面简介，供标签生成失败时使用。
    优先取「简介：」后的一段话；否则去掉标题/发信人等行后取前 max_len 字。
    """
    if not (combined or "").strip():
        return ""
    text = combined.strip()
    for marker in _INTRO_MARKERS:
        if marker in text:
            start = text.index(marker) + len(marker)
            rest = text[start:].strip()
            # 取到下一个明显段落或 max_len
            first_para = rest.split("\n\n")[0].strip() if "\n\n" in rest else rest
            first_para = first_para.split("\n")[0].strip()
            if len(first_para) > max_len:
                first_para = first_para[: max_len - 1] + "…"
            if first_para:
                return first_para
    # 无简介标记：去掉标题/发信人等行，再取前 max_len 字
    lines = text.split("\n")
    kept = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _HEADER_LINE_PATTERN.match(line):
            continue
        kept.append(line)
        if sum(len(l) for l in kept) >= max_len:
            break
    result = " ".join(kept).strip()[:max_len]
    return result + ("…" if len(" ".join(kept)) > max_len else "")


def _extract_json(text: str) -> str:
    """从模型输出中提取 JSON：去掉 ```json ... ``` 包裹及前后杂项。"""
    text = (text or "").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _invoke_tag_prompt(
    content: str,
    prompt_template: str,
    section_name: str = "",
    board_name: str = "",
) -> str:
    """调用 chat 模型生成标签（含重试），返回原始字符串。"""
    prompt = prompt_template.format(
        section_name=section_name or "未知讨论区",
        board_name=board_name or "未知版面",
        intro_summary=content,
    )
    request_err_count = 0
    other_err_count = 0
    last_err: Exception | None = None
    while True:
        try:
            response = chat_model.invoke([HumanMessage(content=prompt)])
            result = (getattr(response, "content", None) or str(response) or "").strip()
            if result:
                return result
            last_err = ValueError("模型返回空内容")
            other_err_count += 1
            if other_err_count >= MAX_RETRIES:
                raise last_err
            delay = RETRY_DELAYS[(other_err_count - 1) % len(RETRY_DELAYS)]
            print(f"[标签生成失败并重试] 返回空 | {section_name}/{board_name} | {delay}s 后重试 ({other_err_count}/{MAX_RETRIES})", flush=True)
            time.sleep(delay)
        except KeyError as e:
            if e.args and e.args[0] == "request":
                last_err = e
                request_err_count += 1
                if request_err_count >= REQUEST_KEYERROR_MAX:
                    print(f"[标签生成失败] KeyError('request') 已达最大重试 {REQUEST_KEYERROR_MAX}，放弃", flush=True)
                    raise last_err
                delay = RETRY_DELAYS[(request_err_count - 1) % len(RETRY_DELAYS)]
                print(f"[标签生成失败并重试] KeyError('request') | {section_name}/{board_name} | {delay}s 后重试 ({request_err_count}/{REQUEST_KEYERROR_MAX})", flush=True)
                time.sleep(delay)
            else:
                last_err = e
                other_err_count += 1
                if other_err_count >= MAX_RETRIES:
                    raise last_err
                delay = RETRY_DELAYS[min(other_err_count - 1, len(RETRY_DELAYS) - 1)]
                print(f"[标签生成失败并重试] KeyError | {section_name}/{board_name}: {e}", flush=True)
                time.sleep(delay)
        except (ConnectionError, TimeoutError) as e:
            last_err = e
            other_err_count += 1
            if other_err_count >= MAX_RETRIES:
                raise last_err
            delay = RETRY_DELAYS[min(other_err_count - 1, len(RETRY_DELAYS) - 1)]
            print(f"[标签生成失败并重试] {type(e).__name__} | {section_name}/{board_name}: {e}", flush=True)
            time.sleep(delay)


def generate_tags(
    content: str,
    prompt_template: str | None = None,
    section_name: str = "",
    board_name: str = "",
) -> dict:
    """
    根据版面置顶内容生成标签 JSON。
    content: 合并后的版面置顶/介绍内容
    prompt_template: 不传则使用 load_prompt_generate() 加载 prompts/prompt_generate.txt
    返回包含 board_name, section_name, summary, speech_rules, post_types 等字段的字典。
    """
    if not (prompt_template or "").strip():
        prompt_template = load_prompt_generate()
    raw = _invoke_tag_prompt(content, prompt_template, section_name, board_name)
    json_str = _extract_json(raw)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning("[Tagger] JSON 解析失败，使用原文摘要: %s", e)
        data = {
            "board_name": board_name or "未知版面",
            "section_name": section_name or "未知讨论区",
            "summary": content[:500] if content else "",
            "speech_rules": [],
            "post_types": [],
            "board_positioning": [],
            "target_audience": [],
            "content_style": [],
            "interaction_form": [],
        }
    # 统一为可序列化格式（列表转 list，保证键存在）
    result = {}
    for k in TAG_KEYS:
        v = data.get(k)
        if v is None:
            result[k] = [] if k != "summary" and k not in ("board_name", "section_name") else ""
        elif isinstance(v, list):
            result[k] = [str(x) for x in v]
        else:
            result[k] = str(v) if v else (""
                if k in ("board_name", "section_name", "summary") else [])
    return result


def _group_docs_by_board(docs: list[Document]) -> dict[tuple[str, str], list[Document]]:
    """按 (section, board) 将文档分组。"""
    by_board: dict[tuple[str, str], list[Document]] = defaultdict(list)
    for d in docs:
        key = (d.metadata.get("section") or "", d.metadata.get("board") or "")
        by_board[key].append(d)
    return by_board


def tag_one_board(
    section_name: str,
    board_name: str,
    group: list[Document],
    prompt_template: str | None = None,
) -> Document | None:
    """
    单个版面：合并该版面下所有文档内容后生成标签，返回一条 Document。
    page_content 为 summary，metadata 含 section、board 及所有标签维度。
    """
    parts = [(d.page_content or "").strip() for d in group if (d.page_content or "").strip()]
    if not parts:
        return None
    combined = "\n\n---\n\n".join(parts)
    try:
        tags = generate_tags(
            combined,
            prompt_template=prompt_template,
            section_name=section_name or "未知讨论区",
            board_name=board_name or "未知版面",
        )
    except Exception as e:
        print(f"[标签生成失败，使用原文] {section_name}/{board_name} | {type(e).__name__}: {e}", flush=True)
        summary = _fallback_summary_from_raw(combined, max_len=400)
        tags = {
            "board_name": board_name or "未知版面",
            "section_name": section_name or "未知讨论区",
            "summary": summary,
            "speech_rules": [],
            "post_types": [],
            "board_positioning": [],
            "target_audience": [],
            "content_style": [],
            "interaction_form": [],
        }
    summary = (tags.get("summary") or "").strip() or _fallback_summary_from_raw(combined, max_len=400)
    if not summary:
        return None
    sample = group[0]
    metadata = {
        "section": section_name,
        "board": board_name,
        **{k: v for k, v in sample.metadata.items() if k in ("source_file",)},
    }
    for k, v in tags.items():
        metadata[k] = v
    metadata["hierarchy"] = f"{section_name} > {board_name} > 介绍"
    metadata["doc_type"] = "介绍"
    return Document(page_content=summary, metadata=metadata)


def tag_documents(
    docs: list[Document],
    prompt_template: str | None = None,
    max_workers: int = 1,
) -> list[Document]:
    """
    将按版面分组的文档列表生成标签，每个版面一条 Document。
    docs: FileLoader 等产生的原始文档（含 section/board metadata）
    prompt_template: 不传则从 prompts/prompt_generate.txt 加载
    max_workers: 大于 1 时多线程处理各版面
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not prompt_template or not prompt_template.strip():
        prompt_template = load_prompt_generate()
    by_board = _group_docs_by_board(docs)
    items = [(sn, bn, group) for (sn, bn), group in by_board.items()]
    if not items:
        return []

    if max_workers <= 1:
        to_add: list[Document] = []
        for section_name, board_name, group in items:
            doc = tag_one_board(section_name, board_name, group, prompt_template)
            if doc is not None:
                to_add.append(doc)
        return to_add

    total, done = len(items), [0]
    lock = threading.Lock()
    to_add = []

    def run_one(args: tuple[str, str, list[Document]]) -> Document | None:
        sn, bn, grp = args
        doc = tag_one_board(sn, bn, grp, prompt_template)
        with lock:
            done[0] += 1
            print(f"[标签处理] ({done[0]}/{total}) {sn} / {bn} 完成", flush=True)
        return doc

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(run_one, (sn, bn, group)) for sn, bn, group in items]
        for fut in as_completed(futures):
            doc = fut.result()
            if doc is not None:
                to_add.append(doc)
    return to_add


def _collect_intro_json_paths(root_dir: str) -> list[str]:
    """收集 root_dir 下所有「介绍*.json」的绝对路径。"""
    root_abs = os.path.normpath(root_dir)
    if not os.path.isdir(root_abs):
        return []
    paths: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root_abs):
        for name in filenames:
            if "介绍" in name and name.lower().endswith(".json"):
                paths.append(os.path.join(dirpath, name))
    return paths


def _save_tagged_doc_to_static(doc: Document, static_root: str) -> None:
    """将一条打标后的 Document 写入 static_root/section/board.json。"""
    section = (doc.metadata.get("section") or "未知讨论区").replace("/", "_")
    board = (doc.metadata.get("board") or "未知版面").replace("/", "_")
    out_dir = os.path.join(static_root, section)
    os.makedirs(out_dir, exist_ok=True)
    # 可序列化：summary + metadata（Chroma 等可能不接受的键可过滤）
    payload = {
        "summary": doc.page_content or "",
        **doc.metadata,
    }
    out_path = os.path.join(out_dir, f"{board}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("[Tagger] 已写入: %s", out_path)


if __name__ == "__main__":
    """
    调试入口：从 data/web_structure 加载所有介绍 JSON，打标签后写入 data/static。
    运行: python -m knowledge.processing.tagger
    """
    web_structure_dir = get_abs_path("data/web_structure")
    static_dir = get_abs_path("data/static")

    intro_paths = _collect_intro_json_paths(web_structure_dir)
    if not intro_paths:
        print("[Tagger] 未在 data/web_structure 下找到任何 介绍*.json，退出。", flush=True)
        sys.exit(0)

    from infrastructure.vector_store.file_loader import FileLoader

    loader = FileLoader()
    docs = loader.load_files(intro_paths)
    if not docs:
        print("[Tagger] 未加载到任何 Document，退出。", flush=True)
        sys.exit(0)

    print(f"[Tagger] 已加载 {len(docs)} 条原始文档，开始打标签（按版面合并）...", flush=True)
    tagged = tag_documents(docs, max_workers=8)
    print(f"[Tagger] 打标签完成，共 {len(tagged)} 个版面。", flush=True)

    os.makedirs(static_dir, exist_ok=True)
    for doc in tagged:
        _save_tagged_doc_to_static(doc, static_dir)
    print("[Tagger] 已全部写入 data/static。", flush=True)
