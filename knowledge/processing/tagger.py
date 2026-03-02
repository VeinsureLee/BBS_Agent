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
from utils.dimension_config import get_tag_keys, get_tag_key_default

RETRY_DELAYS = (1.0, 2.0, 3.0)
MAX_RETRIES = 1024
REQUEST_KEYERROR_MAX = 10000

# 期望的 JSON 顶层键（来自 config/data/data_dimension.json）
TAG_KEYS = get_tag_keys()

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
    hierarchy_path: str = "",
) -> str:
    """调用 chat 模型生成标签（含重试），返回原始字符串。"""
    prompt = prompt_template.format(
        section_name=section_name or "未知讨论区",
        board_name=board_name or "未知版面",
        hierarchy_path=hierarchy_path or f"{section_name}/{board_name}".strip("/") or "未指定",
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
    hierarchy_path: str = "",
) -> dict:
    """
    根据版面置顶内容生成标签 JSON。
    content: 合并后的版面置顶/介绍内容
    prompt_template: 不传则使用 load_prompt_generate() 加载 prompts/prompt_generate.txt
    hierarchy_path: 版面层级路径，如 北邮校园/院系校区/经济管理学院，用于 prompt 与保存
    返回包含 board_name, section_name, summary, speech_rules, post_types 等字段的字典。
    """
    if not (prompt_template or "").strip():
        prompt_template = load_prompt_generate()
    raw = _invoke_tag_prompt(content, prompt_template, section_name, board_name, hierarchy_path)
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
            result[k] = get_tag_key_default(k)
        elif isinstance(v, list):
            result[k] = [str(x) for x in v]
        else:
            result[k] = str(v) if v else get_tag_key_default(k)
    return result


def _group_docs_by_board(docs: list[Document]) -> dict[tuple[str, str], list[Document]]:
    """按 (section, board) 将文档分组。"""
    by_board: dict[tuple[str, str], list[Document]] = defaultdict(list)
    for d in docs:
        key = (d.metadata.get("section") or "", d.metadata.get("board") or "")
        by_board[key].append(d)
    return by_board


def _hierarchy_path_from_source_file(source_file: str, web_structure_prefix: str = "web_structure/") -> str:
    """
    从 Document 的 source_file（相对 data 的路径）解析版面层级路径。
    例如 web_structure/北邮校园/院系校区/经济管理学院/介绍0.json -> 北邮校园/院系校区/经济管理学院
    """
    if not (source_file or "").strip():
        return ""
    path = source_file.replace("\\", "/").strip("/")
    if not path.startswith(web_structure_prefix):
        return ""
    dir_part = os.path.dirname(path)
    hierarchy = dir_part[len(web_structure_prefix):].strip("/")
    return hierarchy


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
    source_file = group[0].metadata.get("source_file") or ""
    hierarchy_path = _hierarchy_path_from_source_file(source_file) or f"{section_name}/{board_name}".strip("/")
    try:
        tags = generate_tags(
            combined,
            prompt_template=prompt_template,
            section_name=section_name or "未知讨论区",
            board_name=board_name or "未知版面",
            hierarchy_path=hierarchy_path,
        )
    except Exception as e:
        print(f"[标签生成失败，使用原文] {section_name}/{board_name} | {type(e).__name__}: {e}", flush=True)
        summary = _fallback_summary_from_raw(combined, max_len=400)
        tags = {k: get_tag_key_default(k) for k in TAG_KEYS}
        tags["board_name"] = board_name or "未知版面"
        tags["section_name"] = section_name or "未知讨论区"
        tags["summary"] = summary
    summary = (tags.get("summary") or "").strip() or _fallback_summary_from_raw(combined, max_len=400)
    if not summary:
        return None
    sample = group[0]
    source_file = sample.metadata.get("source_file") or ""
    hierarchy_path = _hierarchy_path_from_source_file(source_file) or f"{section_name}/{board_name}".strip("/")
    metadata = {
        "section": section_name,
        "board": board_name,
        "hierarchy_path": hierarchy_path,
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
    static_root: str | None = None,
) -> list[Document]:
    """
    将按版面分组的文档列表生成标签，每个版面一条 Document。
    docs: FileLoader 等产生的原始文档（含 section/board metadata）
    prompt_template: 不传则从 prompts/prompt_generate.txt 加载
    max_workers: 大于 1 时多线程处理各版面
    static_root: 若传入，则每处理完一个版面立即写入该目录（处理完及时保存）
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
                if static_root:
                    _save_tagged_doc_to_static(doc, static_root)
                to_add.append(doc)
        return to_add

    total, done = len(items), [0]
    lock = threading.Lock()
    to_add = []

    def run_one(args: tuple[str, str, list[Document]]) -> Document | None:
        sn, bn, grp = args
        doc = tag_one_board(sn, bn, grp, prompt_template)
        if doc is not None and static_root:
            _save_tagged_doc_to_static(doc, static_root)
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
    """
    按 data/web_structure 的目录结构收集所有「介绍*.json」的绝对路径。
    目录层级约定：.../讨论区/版面/介绍N.json 或 .../讨论区/子区/版面/介绍N.json，
    由 FileLoader 从路径解析 section/board。
    """
    root_abs = os.path.abspath(os.path.normpath(root_dir))
    if not os.path.isdir(root_abs):
        return []
    paths: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root_abs):
        for name in filenames:
            if "介绍" in name and name.lower().endswith(".json"):
                full = os.path.join(dirpath, name)
                paths.append(os.path.normpath(os.path.abspath(full)))
    return sorted(paths)


def _collect_all_board_hierarchy_paths(root_dir: str) -> set[str]:
    """
    收集 web_structure 下所有「版面」目录的层级路径（相对 root_dir）。
    版面目录 = 含有 介绍*.json 的目录，或没有子目录的叶子目录（无介绍文件时也需在 static 生成占位）。
    """
    root_abs = os.path.abspath(os.path.normpath(root_dir))
    if not os.path.isdir(root_abs):
        return set()
    out: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root_abs):
        has_intro = any("介绍" in n and n.lower().endswith(".json") for n in filenames)
        is_leaf = len(dirnames) == 0
        if has_intro or is_leaf:
            try:
                rel = os.path.relpath(dirpath, root_abs)
                if rel == ".":
                    continue
                out.add(rel.replace("\\", "/"))
            except ValueError:
                continue
    return out


def _placeholder_doc_for_hierarchy(hierarchy_path: str) -> Document:
    """为无介绍文件的版面生成占位 Document，便于写入 static。"""
    parts = [p for p in hierarchy_path.replace("\\", "/").strip("/").split("/") if p]
    section = parts[0] if len(parts) > 0 else "未知讨论区"
    board = parts[-1] if parts else "未知版面"
    metadata = {
        "section": section,
        "board": board,
        "hierarchy_path": hierarchy_path,
        "summary": "暂无版面介绍",
        "board_name": board,
        "section_name": section,
        "speech_rules": [],
        "post_types": [],
        "board_positioning": [],
        "target_audience": [],
        "content_style": [],
        "interaction_form": [],
        "hierarchy": f"{section} > {board} > 介绍",
        "doc_type": "介绍",
    }
    return Document(page_content="暂无版面介绍", metadata=metadata)


def _save_tagged_doc_to_static(doc: Document, static_root: str) -> None:
    """按原层级路径写入：static_root/北邮校园/院系校区/.../版面名.json。"""
    hierarchy_path = (doc.metadata.get("hierarchy_path") or "").replace("\\", "/").strip("/")
    if hierarchy_path:
        parts = [p for p in hierarchy_path.split("/") if p]
        if parts:
            out_dir = os.path.join(static_root, *parts[:-1]) if len(parts) > 1 else static_root
            file_name = f"{parts[-1]}.json"
        else:
            hierarchy_path = ""
    if not hierarchy_path:
        section = (doc.metadata.get("section") or "未知讨论区").replace("/", "_")
        board = (doc.metadata.get("board") or "未知版面").replace("/", "_")
        out_dir = os.path.join(static_root, section)
        file_name = f"{board}.json"
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "summary": doc.page_content or "",
        **doc.metadata,
    }
    out_path = os.path.join(out_dir, file_name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("[Tagger] 已写入: %s", out_path)


def run_from_web_structure_to_static(
    web_structure_dir: str | None = None,
    static_dir: str | None = None,
    max_workers: int | None = None,
) -> int:
    """
    从 data/web_structure 读取所有介绍 JSON，多线程调用模型打标签，保存到 data/static。
    原文件夹中无介绍文件的版面也会在 static 中生成占位 JSON，不跳过。
    web_structure_dir: 不传则使用 get_abs_path("data/web_structure")
    static_dir: 不传则使用 get_abs_path("data/static")
    max_workers: 不传则从环境变量 TAG_MAX_WORKERS 读取，默认 8
    返回写入 data/static 的版面数（含占位）。
    """
    web_structure_dir = web_structure_dir or get_abs_path("data/web_structure")
    static_dir = static_dir or get_abs_path("data/static")
    if max_workers is None:
        try:
            max_workers = int(os.environ.get("TAG_MAX_WORKERS", "8"))
        except ValueError:
            max_workers = 8
    max_workers = max(1, max_workers)

    all_board_paths = _collect_all_board_hierarchy_paths(web_structure_dir)
    intro_paths = _collect_intro_json_paths(web_structure_dir)
    tagged: list[Document] = []

    if intro_paths:
        from infrastructure.vector_store.file_loader import FileLoader

        loader = FileLoader()
        docs = loader.load_files(intro_paths)
        if docs:
            os.makedirs(static_dir, exist_ok=True)
            logger.info("[Tagger] 已从 web_structure 加载 %d 个介绍文件，共 %d 条原始文档，按版面合并后多线程打标签（workers=%d），处理完即保存。", len(intro_paths), len(docs), max_workers)
            tagged = tag_documents(docs, max_workers=max_workers, static_root=static_dir)
            logger.info("[Tagger] 打标签完成，共 %d 个版面（已及时写入 data/static）。", len(tagged))

    tagged_hierarchy = {doc.metadata.get("hierarchy_path") for doc in tagged if doc.metadata.get("hierarchy_path")}
    missing = all_board_paths - tagged_hierarchy
    if missing:
        os.makedirs(static_dir, exist_ok=True)
        for hierarchy_path in sorted(missing):
            placeholder = _placeholder_doc_for_hierarchy(hierarchy_path)
            _save_tagged_doc_to_static(placeholder, static_dir)
        logger.info("[Tagger] 为 %d 个无介绍文件的版面生成占位并写入 data/static。", len(missing))

    total = len(tagged) + len(missing)
    if total > 0:
        logger.info("[Tagger] 合计写入 data/static 共 %d 个版面。", total)
    return total


if __name__ == "__main__":
    """
    入口：按 data/web_structure 结构读取介绍 JSON，多线程调用模型打标签，保存到 data/static。
    运行: python -m knowledge.processing.tagger
    可选环境变量: TAG_MAX_WORKERS（默认 8）
    """
    n = run_from_web_structure_to_static(max_workers=128)
    if n == 0:
        print("[Tagger] 未处理任何版面（无介绍文件或加载失败），退出。", flush=True)
        sys.exit(1)
    print(f"[Tagger] 已全部写入 data/static（共 {n} 个版面）。", flush=True)
