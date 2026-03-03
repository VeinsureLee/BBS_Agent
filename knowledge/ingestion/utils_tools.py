"""
ingestion 通用工具：路径安全与讨论区/版面树遍历。

功能说明：
    - 提供用于文件路径的安全目录名/文件名（替换非法字符）；
    - 从 section 树中递归收集所有版面，用于批量爬取置顶或归档。

主要接口入参/出参：
    - sanitize_dir(name: str) -> str
        入参：name — 原始目录名或文件名。
        出参：替换 <>:"/\\|?* 等非法字符后的安全字符串；空或仅空白时返回 "未分类"。
    - collect_all_boards(section_node: dict, section_name: str, path_prefix: list) -> list
        入参：section_node — 含 "boards"、"sub_sections" 的讨论区/子区节点；section_name — 讨论区名称；path_prefix — 路径前缀列表。
        出参：[(section_name, path_parts, board), ...]，path_parts 为从根到当前节点的名称列表。
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
