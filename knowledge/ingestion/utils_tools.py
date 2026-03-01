"""
ingestion 通用工具：路径安全、讨论区/版面树遍历等。
"""
import re


def sanitize_dir(name: str) -> str:
    """用于文件路径的安全目录名/文件名。"""
    if not name or not str(name).strip():
        return "未分类"
    return re.sub(r'[<>:"/\\|?*]', "_", str(name).strip()) or "未分类"


def collect_all_boards(section_node: dict, section_name: str, path_prefix: list) -> list:
    """从 section 树中收集所有版面，返回 [(section_name, path_parts, board), ...]。"""
    out = []
    name = section_node.get("name") or ""
    prefix = path_prefix + [name]
    for b in section_node.get("boards") or []:
        out.append((section_name, prefix, b))
    for sub in section_node.get("sub_sections") or []:
        out.extend(collect_all_boards(sub, section_name, prefix))
    return out
