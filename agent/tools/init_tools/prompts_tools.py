"""
根据爬取到的讨论区、版面及置顶内容，生成「讨论区与版面说明」提示词并保存到 prompts/。
说明包含：讨论区整体类型与下属版面；版面的发言规则与帖子类型由模型根据版面名、讨论区及置顶摘要生成。
"""
import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage

from utils.config_handler import (
    load_web_structure_board_config,
    get_web_structure_introductions_root,
)
from utils.path_tool import get_abs_path
from utils.prompt_loader import load_prompt_generate


def _sanitize_for_path(name: str) -> str:
    """用于文件/目录名的安全名称。"""
    if not name or not str(name).strip():
        return "未命名"
    return re.sub(r'[<>:"/\\|?*]', "_", str(name).strip()) or "未命名"


def _get_board_cache_path(section_name: str, board_name: str) -> Path:
    """按版面返回缓存文件路径：data/boards_guide/{讨论区}/{版面}.json"""
    root = Path(get_abs_path("data")).resolve() / "boards_guide"
    safe_sec = _sanitize_for_path(section_name or "未分类")
    safe_board = _sanitize_for_path(board_name or "board")
    return root / safe_sec / f"{safe_board}.json"


def _load_board_cached_rules(section_name: str, board_name: str) -> tuple[str, str] | None:
    """读取已保存的版面发言规则与帖子类型，不存在返回 None。"""
    path = _get_board_cache_path(section_name, board_name)
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        rules = (data.get("rules") or "").strip() or "常规发帖，需遵守版规。"
        post_type = (data.get("post_type") or "").strip() or f"与「{board_name or '该版面'}」主题相关的讨论与信息。"
        return (rules, post_type)
    except Exception:
        return None


def _save_board_cached_rules(section_name: str, board_name: str, rules: str, post_type: str) -> Path:
    """按版面保存发言规则与帖子类型，便于中断后复用。"""
    path = _get_board_cache_path(section_name, board_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "section_name": (section_name or "").strip(),
        "board_name": (board_name or "").strip(),
        "rules": rules,
        "post_type": post_type,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def _infer_section_type(section_name: str) -> str:
    """根据讨论区名称推断整体类型。"""
    name = (section_name or "").strip()
    if not name:
        return "综合讨论区"
    if "情感" in name or "悄悄话" in name or "树洞" in name:
        return "情感类讨论区"
    if "教务" in name or "学习" in name or "学术" in name:
        return "教务/学习类讨论区"
    if "交易" in name or "二手" in name or "市场" in name:
        return "交易/生活类讨论区"
    if "站务" in name or "管理" in name:
        return "站务/管理类讨论区"
    if "休闲" in name or "娱乐" in name:
        return "休闲娱乐类讨论区"
    return "综合讨论区"


def _parse_model_rules_response(text: str, board_name: str) -> tuple[str, str]:
    """从模型回复中解析出发言规则和帖子类型。"""
    rules = ""
    post_type = ""
    if text:
        # 尝试匹配 "发言规则：xxx" 与 "帖子类型：xxx"（允许换行、冒号为中文或英文）
        m_rules = re.search(r"发言规则[：:]\s*(.+?)(?=帖子类型|$)", text, re.DOTALL)
        m_type = re.search(r"帖子类型[：:]\s*(.+?)(?=发言规则|$)", text, re.DOTALL)
        if m_rules:
            rules = m_rules.group(1).strip().replace("\n", " ")[:500]
        if m_type:
            post_type = m_type.group(1).strip().replace("\n", " ")[:500]
    if not rules:
        rules = "常规发帖，需遵守版规。"
    if not post_type:
        post_type = f"与「{board_name}」主题相关的讨论与信息。"
    return rules, post_type


def _generate_board_rules_and_type_by_model(
    section_name: str,
    board_name: str,
    intro_summary: str,
    debug: bool = False,
) -> tuple[str, str]:
    """调用模型根据讨论区、版面名及置顶摘要生成发言规则与帖子类型。"""
    try:
        from model.factory import chat_model
        template = load_prompt_generate()
        prompt = template.format(
            section_name=section_name or "未命名讨论区",
            board_name=board_name or "未命名版面",
            intro_summary=intro_summary or "（无）",
        )
        response = chat_model.invoke([HumanMessage(content=prompt)])
        text = (response.content if hasattr(response, "content") else str(response)) or ""
        if debug:
            print(f"  [DEBUG] 模型生成 版面「{board_name}」: {text[:80]}…")
        return _parse_model_rules_response(text, board_name)
    except Exception as e:
        if debug:
            print(f"  [DEBUG] 模型生成失败 {board_name}: {e}，使用默认说明")
        return (
            "常规发帖，需遵守版规。",
            f"与「{board_name or '该版面'}」主题相关的讨论与信息。",
        )


def _load_board_introductions_summary(introductions_root: Path, section_name: str, board_name: str) -> str:
    """读取某版面下所有介绍 JSON，汇总为简短说明（置顶内容摘要）。"""
    root = Path(introductions_root)
    safe_sec = re.sub(r'[<>:"/\\|?*]', "_", (section_name or "未分类").strip()) or "未分类"
    safe_board = re.sub(r'[<>:"/\\|?*]', "_", (board_name or "").strip()) or "board"
    dir_path = root / safe_sec / safe_board
    if not dir_path.is_dir():
        return ""
    parts = []
    for fname in sorted(dir_path.iterdir()):
        if fname.suffix != ".json" or "介绍" not in fname.name:
            continue
        try:
            with open(fname, "r", encoding="utf-8") as f:
                data = json.load(f)
            title = (data.get("title") or "").strip()
            if title:
                parts.append(title)
            for fl in (data.get("floors") or [])[:2]:
                c = (fl.get("content") or "").strip()
                if c and len(c) < 300:
                    parts.append(c)
                elif c:
                    parts.append(c[:300] + "…")
        except Exception:
            continue
    return "；".join(parts[:5]) if parts else ""


def generate_boards_sections_prompt(
    sections: list = None,
    introductions_root: Path = None,
    debug: bool = False,
) -> str:
    """
    根据讨论区列表与介绍目录生成「讨论区与版面说明」全文。
    :param sections: 讨论区列表（含 name, url, boards），不传则从 load_web_structure_board_config 读取
    :param introductions_root: 介绍根目录，不传则从 config 读取
    :param debug: 是否打印调试信息
    :return: 生成的提示词全文
    """
    if sections is None:
        cfg = load_web_structure_board_config()
        sections = cfg.get("sections") or []
    if introductions_root is None:
        introductions_root = get_web_structure_introductions_root()
    lines = [
        "# BBS 讨论区与版面说明",
        "",
        "本文档描述各讨论区（版面父类）的整体类型、下属版面，以及各版面的发言规则与帖子类型。",
        "",
    ]
    for sec in sections:
        sec_name = (sec.get("name") or "").strip() or "未命名讨论区"
        sec_type = _infer_section_type(sec_name)
        lines.append(f"## 讨论区：{sec_name}")
        lines.append(f"**整体类型**：{sec_type}")
        boards = sec.get("boards") or []
        lines.append(f"**下属版面**：{', '.join((b.get('name') or '').strip() or '' for b in boards)}")
        lines.append("")
        for board in boards:
            board_name = (board.get("name") or "").strip() or "未命名版面"
            intro_summary = _load_board_introductions_summary(introductions_root, sec_name, board_name)
            # 优先使用已保存的版面缓存，避免终止后重新生成
            cached = _load_board_cached_rules(sec_name, board_name)
            if cached is not None:
                rules, post_type = cached
                if debug:
                    print(f"  [DEBUG] 版面「{board_name}」使用已缓存")
            else:
                rules, post_type = _generate_board_rules_and_type_by_model(
                    sec_name, board_name, intro_summary, debug=debug
                )
                _save_board_cached_rules(sec_name, board_name, rules, post_type)
            lines.append(f"### 版面：{board_name}")
            lines.append(f"- **发言规则**：{rules}")
            lines.append(f"- **帖子类型**：{post_type}")
            if intro_summary:
                lines.append(f"- **版面说明（置顶摘要）**：{intro_summary}")
            lines.append("")
        lines.append("")
    text = "\n".join(lines)
    if debug:
        print("[DEBUG] 讨论区与版面说明已生成，共", len(sections), "个讨论区")
    return text


def get_boards_guide_dir() -> Path:
    """返回版面说明保存目录：data/boards_guide"""
    return Path(get_abs_path("data")).resolve() / "boards_guide"


def generate_and_save_boards_prompt(debug: bool = False) -> Path:
    """
    根据当前 config 中的版面配置与介绍目录，仅生成讨论区下各版面的说明并保存到 data/boards_guide（每版面一个 JSON）。
    不生成 boards_sections_guide.txt。在 run_init 爬取完成后调用。
    :return: 保存目录路径（data/boards_guide）
    """
    generate_boards_sections_prompt(introductions_root=None, debug=debug)
    path = get_boards_guide_dir()
    path.mkdir(parents=True, exist_ok=True)
    if debug:
        print("[DEBUG] 版面说明已保存到:", path)
    return path
