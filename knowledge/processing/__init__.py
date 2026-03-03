"""
knowledge.processing 子包：版面内容清理与版面标签生成。

功能说明：
    - 标签生成（tagger）：加载 prompts/prompt_generate.txt，调用 chat 模型根据版面置顶/介绍内容生成多维度标签 JSON
      （board_name、section_name、summary、speech_rules、post_types 等），可写入 data/static；
      支持单版面 generate_tags、tag_one_board 与按文档列表按版面分组批量 tag_documents，以及从 web_structure 到 static 的 run_from_web_structure_to_static。
    - 内容清理（clean）：将 data/dynamic 下帖子 JSON 的楼层 content 按发信人、信区、标题、发信站、正文、来源分块并写回；
      本包 __all__ 不导出 clean，需使用 knowledge.processing.clean 或 from knowledge.processing import clean 后调用 clean_board、parse_content_blocks 等。

子模块与主要接口（入参/出参见各模块文件头）：
    - tagger：generate_tags(content, prompt_template?, section_name, board_name, hierarchy_path) -> dict；
              tag_one_board(section_name, board_name, group, prompt_template?) -> Document|None；
              tag_documents(docs, prompt_template?, max_workers=1, static_root?) -> list[Document]；
              run_from_web_structure_to_static(web_structure_dir?, static_dir?, max_workers?) -> int。
    - clean：parse_content_blocks(content) -> dict；clean_floor_content(floor) -> None；
             get_board_json_paths(data_root, board) -> list[Path]；clean_board(board, data_root?) -> int。
"""

from .tagger import (
    generate_tags,
    tag_one_board,
    tag_documents,
)

__all__ = ["generate_tags", "tag_one_board", "tag_documents"]
