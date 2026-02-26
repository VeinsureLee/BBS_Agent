"""
BBS 初始化调试入口：启动浏览器 -> 初始化（爬取登录框->登录->爬取版面->爬取置顶）-> 向量库存储 -> 退出浏览器。
支持仅爬取单个版面；支持仅向量化（不爬取，将已有介绍等内容写入向量库）。

用法:
  全量初始化（含向量库）:  python -m agent.tools.init_tools
  无头模式:                python -m agent.tools.init_tools --headless
  单版面:                  python -m agent.tools.init_tools --board "悄悄话栏目"
  单版面不爬详情:           python -m agent.tools.init_tools --board "版面名" --no-detail
  仅向量化（不爬取）:       python -m rag.vector_store
                          （或 python -m agent.tools.init_tools --vectorize-only）
"""
import sys
import os

# 保证项目根在 path（必须在 import agent 之前）
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv

load_dotenv()

# --vectorize-only 时不导入 init_tools（避免依赖 playwright）；其他分支再导入
def _import_init_tools():
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


def _has_vectorize_only():
    """是否仅向量化（不启动浏览器、不爬取）。"""
    return "--vectorize-only" in sys.argv or "--vectorize" in sys.argv


if __name__ == "__main__":
    vectorize_only = _has_vectorize_only()
    if vectorize_only:
        try:
            from rag.vector_store import VectorStoreService
            vs = VectorStoreService()
            vs.load_document()
            vs.load_introductions()
            print("仅向量化完成: 向量库已更新（知识库文件 + 介绍）。")
            print("  知识库文件: 已同步")
            print("  介绍: 已同步")
        except Exception as e:
            print("仅向量化失败:", e)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        sys.exit(0)

    popup_browser = "--headless" not in sys.argv and "-q" not in sys.argv
    debug = True
    board_name = _get_board_name_from_argv()
    fetch_article_detail = "--no-detail" not in sys.argv

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
        # 流程：初始化 -> 向量库存储 -> 关闭浏览器
        vec = update_vector_store(debug=debug)
        print("  向量库:", vec.get("message", ""))
        if not vec.get("loaded_introductions") and not vec.get("loaded_document"):
            print("  [提示] 向量库未更新成功，可稍后单独运行: python -m agent.tools.init_tools --vectorize-only")
        close_browser()
    except Exception as e:
        print("失败:", e)
        sys.exit(1)
