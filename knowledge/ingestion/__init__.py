"""
knowledge.ingestion 子包：BBS 讨论区/版面结构爬取与置顶帖、动态帖归档。

功能说明：
    - 讨论区列表：从「全部讨论区」或 section 页获取讨论区列表（forum_ingestor）。
    - 版面树：从侧栏或主表格解析版面与二级目录，支持递归爬取子区版面（board_ingestor）。
    - 置顶与帖子详情：爬取版面置顶列表、打开帖子详情解析楼层，组装为「介绍」JSON（board_ingestor）。
    - 按版面增量更新：加载 forum_structure，按讨论区/版面爬取多页帖子并保存为 日期/帖子名.json（forum_updater）。
    - 工具：路径安全命名、从 section 树递归收集所有版面（utils_tools）。
    命令行入口：python -m knowledge.ingestion，见 __main__.py 头部注释。

子模块与主要接口（入参/出参见各模块文件头）：
    - forum_ingestor：parse_section_list_from_html(html) -> list；crawl_section_list(browser, base_url, section_count?) -> list。
    - board_ingestor：crawl_section_boards_tree(browser, base_url, section_id_or_slug) -> dict；
                      crawl_board_pinned(browser, base_url, board_id) -> list；
                      crawl_article_detail(browser, base_url, article_url) -> list；
                      build_intro_dict(pinned_item, floors) -> dict。
    - forum_updater：load_forum_structure(structure_path?) -> dict；
                     get_board_by_section_and_name(structure, section_name, board_name) -> dict|None；
                     update_board_posts(browser, base_url, section_name, board, output_root, max_pages?, concurrency?) -> list[str]。
    - utils_tools：sanitize_dir(name) -> str；collect_all_boards(section_node, section_name, path_prefix) -> list。
"""

from .forum_ingestor import (
    SECTION_COUNT,
    parse_section_list_from_html,
    crawl_section_list,
)
from .board_ingestor import (
    crawl_section_boards_tree,
    crawl_board_pinned,
    crawl_article_detail,
    build_intro_dict,
)
from .forum_updater import (
    load_forum_structure,
    get_board_by_section_and_name,
    update_board_posts,
)
from .utils_tools import sanitize_dir, collect_all_boards

__all__ = [
    "SECTION_COUNT",
    "parse_section_list_from_html",
    "crawl_section_list",
    "crawl_section_boards_tree",
    "crawl_board_pinned",
    "crawl_article_detail",
    "build_intro_dict",
    "load_forum_structure",
    "get_board_by_section_and_name",
    "update_board_posts",
    "sanitize_dir",
    "collect_all_boards",
]
