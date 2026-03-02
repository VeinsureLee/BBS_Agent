"""
从 config/data/data_dimension.json 加载版面维度配置，供 structure_store、tagger、prompt_loader 等统一调用。
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_handler import load_json_config
from utils.path_tool import get_abs_path

DATA_DIMENSION_PATH = "config/data/data_dimension.json"

_dimension_cache: dict | None = None


def get_data_dimension() -> dict:
    """加载并缓存 data_dimension.json，返回完整配置。"""
    global _dimension_cache
    if _dimension_cache is None:
        _dimension_cache = load_json_config(default_path=DATA_DIMENSION_PATH)
    return _dimension_cache


def get_board_field_keys() -> tuple[str, ...]:
    """返回版面字段键列表（与 structure_store 拆文档顺序一致）。"""
    data = get_data_dimension()
    dims = data.get("dimensions") or []
    return tuple(d.get("key") for d in dims if d.get("key"))


def get_field_label_map() -> dict[str, str]:
    """返回字段 key -> 中文 label 的映射。"""
    data = get_data_dimension()
    dims = data.get("dimensions") or []
    return {d["key"]: d.get("label", d["key"]) for d in dims if d.get("key")}


def get_tag_keys() -> tuple[str, ...]:
    """返回标签 JSON 的键顺序：board_name, section_name, summary, 及各维度 key。"""
    return ("board_name", "section_name") + get_board_field_keys()


def get_tag_key_default(key: str):
    """返回某标签键的默认值：字符串类型为 \"\"，数组类型为 []。"""
    if key in ("board_name", "section_name"):
        return ""
    data = get_data_dimension()
    for d in data.get("dimensions") or []:
        if d.get("key") == key:
            return "" if d.get("type") == "string" else []
    return []


def get_dimensions_instruction() -> str:
    """生成提示词中「按以下 N 个维度提取标签」的编号说明文本（含开头一句）。"""
    data = get_data_dimension()
    dims = data.get("dimensions") or []
    n = len(dims)
    intro = f"请严格按以下 {n} 个维度提取标签（每个维度为字符串数组，只填关键词，不写句子、不解释）："
    lines = [intro]
    for i, d in enumerate(dims, 1):
        key = d.get("key", "")
        label = d.get("label", key)
        desc = d.get("description", "")
        lines.append(f"{i}、{label}：{desc}")
    return "\n".join(lines)


def get_json_schema_for_prompt() -> str:
    """生成提示词中「字段名与类型如下」的说明及示例格式。"""
    data = get_data_dimension()
    dims = data.get("dimensions") or []
    lines = [
        "- board_name：版面名称（字符串）",
        "- section_name：所属讨论区（字符串）",
    ]
    for d in dims:
        key = d.get("key", "")
        label = d.get("label", key)
        t = d.get("type", "array")
        type_desc = "字符串数组" if t == "array" else "字符串"
        lines.append(f"- {key}：{label}（{type_desc}）")

    example_parts = ['"board_name":"xxx"', '"section_name":"xxx"']
    for d in dims:
        k = d.get("key", "")
        if d.get("type") == "array":
            example_parts.append(f'"{k}":["a","b"]')
        else:
            example_parts.append(f'"{k}":"xxx"')
    # 双花括号以便后续 prompt_template.format() 时不被当作占位符
    example = "{{" + ",".join(example_parts) + "}}"
    return "\n".join(lines) + "\n\n示例格式：\n" + example
