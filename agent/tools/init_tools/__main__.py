"""
BBS 初始化调试入口。默认：启动浏览器 -> 登录 -> 爬取版面与置顶 -> 生成提示词 -> 向量库存储 -> 关闭浏览器。

用法:
  1. 默认（完整流程，弹窗浏览器）:
     python -m agent.tools.init_tools

  2. 无头模式（完整流程，不弹窗）:
     python -m agent.tools.init_tools --headless

  3. 单版面（只爬指定版面置顶，再更新向量库）:
     python -m agent.tools.init_tools --board "悄悄话栏目"

  4. 单版面不爬详情（不点开置顶帖详情）:
     python -m agent.tools.init_tools --board "版面名" --no-detail

  5. 仅生成提示词（不爬取，根据已有 board/介绍 生成 data/boards_guide）:
     python -m agent.tools.init_tools --prompt-only

  6. 仅向量化（不爬取、不启动浏览器）:
     python -m agent.tools.init_tools --vectorize-only
"""
import sys
import os

# 保证项目根在 path（必须在 import agent 之前）
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv

load_dotenv()


def _import_init_tools():
    """需要浏览器时再导入（避免 --vectorize-only / --prompt-only 依赖 playwright）。"""
    from agent.tools.init_tools.init_tools import (
        start_browser,
        run_init,
        run_single_board_init,
        update_vector_store,
        close_browser,
    )
    return start_browser, run_init, run_single_board_init, update_vector_store, close_browser


def _get_board_name_from_argv():
    """解析 --board 后的版面名称。"""
    argv = sys.argv
    for i, a in enumerate(argv):
        if a in ("--board", "-b") and i + 1 < len(argv):
            return argv[i + 1].strip()
    return None


def _has_flag(*flags):
    """是否包含任一参数。"""
    return any(f in sys.argv for f in flags)


if __name__ == "__main__":
    # 6. 仅向量化（不爬取、不启动浏览器）
    if _has_flag("--vectorize-only", "--vectorize"):
        print("正在执行仅向量化（知识库 + 讨论区/版面说明）", flush=True)
        try:
            from rag.vector_store import VectorStoreService
            vs = VectorStoreService()
            print("知识库文件:", flush=True)
            vs.load_document(verbose=True)
            print("讨论区/版面说明:", flush=True)
            vs.load_board_guide(verbose=True)
            print("仅向量化完成: 向量库已更新（知识库文件 + 讨论区/版面说明）。")
            print("  知识库文件: 已同步")
            print("  讨论区/版面说明: 已同步")
        except Exception as e:
            print("仅向量化失败:", e)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        sys.exit(0)

    # 5. 仅生成提示词（不爬取，依赖已有 board.json 与介绍目录）
    if _has_flag("--prompt-only", "-p", "--prompt"):
        try:
            from agent.tools.init_tools.prompts_tools import generate_and_save_boards_prompt
            path = generate_and_save_boards_prompt(debug=True)
            print("仅生成提示词完成: 已写入目录", path)
        except Exception as e:
            print("仅生成提示词失败:", e)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        sys.exit(0)

    # 1/2：默认 或 无头模式；3/4：单版面 或 单版面不爬详情
    popup_browser = not _has_flag("--headless", "-q")
    debug = True
    board_name = _get_board_name_from_argv()
    fetch_article_detail = not _has_flag("--no-detail")

    try:
        start_browser, run_init, run_single_board_init, update_vector_store, close_browser = _import_init_tools()
        start_browser(debug=popup_browser)
        if board_name:
            summary = run_single_board_init(
                board_name,
                fetch_article_detail=fetch_article_detail,
                debug=debug,
            )
            print(f"单版面爬取完成: {summary['board_name']}（{summary['section_name']}）")
            print(f"  置顶条数: {summary['count']}")
            print(f"  保存目录: {summary['introductions_path']}")
        else:
            summary = run_init(debug=debug)
            if summary.get("skipped"):
                print("已初始化，跳过爬取。")
            else:
                print("BBS 初始化完成（登录页 + 版面结构 + 各版面置顶内容）")
            print("  登录配置:", summary["login_config_path"])
            print("  版面配置:", summary["board_path"])
            print("  置顶内容:", summary.get("introductions_path", ""))
        vec = update_vector_store(debug=debug)
        print("  向量库:", vec.get("message", ""))
        if not vec.get("loaded_board_guide") and not vec.get("loaded_document"):
            print("  [提示] 向量库未更新成功，可稍后单独运行: python -m agent.tools.init_tools --vectorize-only")
        close_browser()
    except Exception as e:
        print("失败:", e)
        sys.exit(1)
