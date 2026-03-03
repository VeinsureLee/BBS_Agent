"""
数据初始化工具：forum init、board init、tag init；
根据 config/init.json 判断是否已初始化，未初始化时爬取讨论区与版面结构并保存为 forum_structure.json。
"""
from .initialize import (
    is_already_initialized,
    do_initialize,
    main,
)
from .forum_init import run_forum_init
from .board_init import run_board_init
from .tag_init import run_tag_init

__all__ = [
    "is_already_initialized",
    "do_initialize",
    "main",
    "run_forum_init",
    "run_board_init",
    "run_tag_init",
]
