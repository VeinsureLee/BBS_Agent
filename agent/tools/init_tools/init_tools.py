"""
初始化工具：提供「启动浏览器」「初始化」「向量库更新」「关闭浏览器」等能力。
- 启动/关闭浏览器：供 main 或调用方使用，不暴露给 Agent。
- 初始化：爬取登录框 -> 登录 -> 爬取版面 -> 爬取置顶，作为整体，使用当前已打开的 page；可由 Agent 通过 run_bbs_init 调用。
- 向量库更新：将知识库配置中的文件与介绍（介绍*.json）写入向量库（MD5 增量）。
- 仅向量化：不爬取，仅将已有介绍等内容写入向量库。

同一浏览器实例内顺序：启动浏览器 -> 初始化（使用该 page）-> 向量库存储 -> 关闭浏览器。
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from utils.config_handler import (
    driver_conf,
    bbs_conf,
    load_web_structure_save_config,
    load_web_structure_login_config,
    load_web_structure_board_config,
    get_web_structure_login_config_path,
    get_web_structure_board_path,
    get_web_structure_init_status_path,
    get_web_structure_introductions_path,
)
from agent.tools.init_tools.login_tools import crawl_login_page, do_login
from agent.tools.init_tools.board_tools import (
    crawl_sections_and_boards,
    SECTION_COUNT,
    find_board_info_by_name,
    board_url_to_request_url,
)
from agent.tools.init_tools.inroductions import (
    crawl_one_section_introductions,
    crawl_board_introductions,
    save_introductions,
)
from utils.timer import timer

# ---------------------------------------------------------------------------
# 浏览器实例（由 start_browser 设置，由 close_browser 清除）
# ---------------------------------------------------------------------------
_playwright = None
_browser = None
_page = None


# ---------------------------------------------------------------------------
# 保存路径（通过 utils 加载 config/web_structure）
# ---------------------------------------------------------------------------


def _get_login_config_path() -> Path:
    return get_web_structure_login_config_path().resolve()


def _get_board_path() -> Path:
    return get_web_structure_board_path().resolve()


def _get_init_status_path() -> Path:
    return get_web_structure_init_status_path().resolve()


def _get_introductions_path() -> Path:
    return get_web_structure_introductions_path().resolve()


def _set_init_status(success: bool) -> None:
    """初始化成功后更新 init.json。"""
    path = _get_init_status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"init_status": success}, f, ensure_ascii=False, indent=2)


def is_initialized() -> bool:
    """检查 config/web_structure/init.json 中 init_status 是否为 True。"""
    path = _get_init_status_path()
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("init_status") is True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 工具一：启动浏览器（不暴露给 Agent）
# ---------------------------------------------------------------------------


def start_browser(debug: bool = False) -> str:
    """
    启动 Playwright 浏览器并创建新页面，将 page 存入模块状态供 run_init 使用。
    debug=True 时弹出浏览器窗口，debug=False 时无头模式不弹出。
    与 close_browser 配对使用；main 中调试流程：start_browser -> run_init -> close_browser。
    """
    global _playwright, _browser, _page
    if _page is not None:
        print("浏览器已在运行，无需重复启动。")
        return "浏览器已在运行，无需重复启动。"
    BBS_Url = (bbs_conf.get("BBS_Url") or "").strip().rstrip("/")
    if not BBS_Url:
        raise ValueError("未配置 BBS_Url，请在 config/local/bbs.json 中设置")
    Chrome_Path = driver_conf.get("Chrome_Path")
    launch_options = {"headless": not debug}
    if Chrome_Path:
        launch_options["executable_path"] = Chrome_Path
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(**launch_options)
    _page = _browser.new_page()
    print("浏览器已启动。")
    return "浏览器已启动。"


# ---------------------------------------------------------------------------
# 工具二：初始化（爬取登录框 -> 登录 -> 爬取版面 -> 爬取置顶）
# ---------------------------------------------------------------------------


def run_init(debug: bool = False) -> dict:
    """
    使用当前已打开的 page 执行完整初始化：爬取登录页并保存 -> 登录 -> 爬取讨论区与版面并保存 -> 爬取各版面置顶并保存。
    必须先调用 start_browser()，否则抛出 RuntimeError。
    若已初始化（init.json 中 init_status 为 True），则跳过爬取并直接返回路径信息。
    """
    global _page
    if _page is None:
        raise RuntimeError("请先调用 start_browser() 启动浏览器。")
    load_web_structure_save_config()
    if is_initialized():
        if debug:
            print("[DEBUG] 已初始化（init.json 中 init_status 为 true），跳过爬取。")
        return {
            "login_config_path": str(_get_login_config_path()),
            "board_path": str(_get_board_path()),
            "init_status_path": str(_get_init_status_path()),
            "introductions_path": str(_get_introductions_path()),
            "skipped": True,
        }

    BBS_Url = (bbs_conf.get("BBS_Url") or "").strip().rstrip("/")
    if not BBS_Url:
        raise ValueError("未配置 BBS_Url，请在 config/local/bbs.json 中设置")

    login_config_path = _get_login_config_path()
    board_path = _get_board_path()
    introductions_path = _get_introductions_path()

    try:
        # 1. 爬取登录页并保存
        login_result = crawl_login_page(_page, BBS_Url, debug=debug)
        login_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(login_config_path, "w", encoding="utf-8") as f:
            json.dump(login_result, f, ensure_ascii=False, indent=2)
        if debug:
            print("[DEBUG] 登录配置已保存到:", login_config_path)

        # 2. 登录
        do_login(
            _page,
            login_result["login_page_url"],
            login_result["username_input_id"],
            login_result["password_input_id"],
            login_result["login_button_id"],
            debug=debug,
        )

        # 3. board_tools：爬取页面结构并计时，保存到 board_path
        if debug:
            print("[DEBUG] 版面结构爬取（board_tools）:")
        board_path.parent.mkdir(parents=True, exist_ok=True)
        sections = crawl_sections_and_boards(_page, BBS_Url, section_count=SECTION_COUNT, debug=debug)
        with open(board_path, "w", encoding="utf-8") as f:
            json.dump({"sections": sections}, f, ensure_ascii=False, indent=2)
        if debug:
            print("[DEBUG] 版面配置已保存到:", board_path)

        # 4. introduction tools：爬取置顶信息，每爬完一个讨论区下的版面就保存（含计时）
        if debug:
            print("[DEBUG] 置顶内容爬取（introduction tools），每区保存:")
        sections_with_intros = []
        for sec in sections:
            with timer(f"置顶-讨论区 {sec.get('name', '')}"):
                sec_with_intros = crawl_one_section_introductions(
                    _page, sec, BBS_Url, debug=debug, fetch_article_detail=True
                )
                sections_with_intros.append(sec_with_intros)
                save_introductions(sections_with_intros, only_last_section=True)
                if debug:
                    print("  [DEBUG] 已保存讨论区", sec_with_intros.get("name", ""), "->", introductions_path)

        _set_init_status(True)
        return {
            "login_config_path": str(login_config_path),
            "board_path": str(board_path),
            "init_status_path": str(_get_init_status_path()),
            "introductions_path": str(introductions_path),
        }
    except Exception:
        _set_init_status(False)
        raise


def run_single_board_init(
    board_name: str,
    fetch_article_detail: bool = True,
    debug: bool = False,
) -> dict:
    """
    仅爬取单个版面的置顶介绍并保存，避免全量初始化时间过长。
    需先 start_browser()；依赖已有 login 配置与 board.json（至少跑过一次全量初始化或已有版面结构）。
    :param board_name: 版面名称（与 board.json 中一致，如「悄悄话栏目」）
    :param fetch_article_detail: 是否点开每条置顶爬取详情（时间、人物、赞踩等）
    :param debug: 是否打印调试信息
    :return: 含 board_name, section_name, introductions_path, count 等
    """
    global _page
    if _page is None:
        raise RuntimeError("请先调用 start_browser() 启动浏览器。")
    load_web_structure_save_config()
    BBS_Url = (bbs_conf.get("BBS_Url") or "").strip().rstrip("/")
    if not BBS_Url:
        raise ValueError("未配置 BBS_Url，请在 config/local/bbs.json 中设置")

    board_cfg = load_web_structure_board_config()
    sections = board_cfg.get("sections", [])
    board_url, section_name = find_board_info_by_name(sections, board_name)
    if not board_url or not section_name:
        raise ValueError(f"未在 board.json 中找到版面「{board_name}」，请先执行全量初始化或确认版面名称正确")

    login_cfg = load_web_structure_login_config()
    if not login_cfg.get("login_page_url"):
        raise ValueError("未找到登录配置，请先执行一次全量初始化以生成 login 配置")
    do_login(
        _page,
        login_cfg["login_page_url"],
        login_cfg.get("username_input_id", "id"),
        login_cfg.get("password_input_id", "pwd"),
        login_cfg.get("login_button_id", "b_login"),
        debug=debug,
    )

    request_url = board_url_to_request_url(board_url, BBS_Url)
    introductions = crawl_board_introductions(
        _page, request_url, section_name, board_name, debug=debug
    )
    if fetch_article_detail and introductions:
        from agent.tools.init_tools.inroductions import crawl_article_detail
        for item in introductions:
            url = (item.get("url") or "").strip()
            if url:
                try:
                    item["floors"] = crawl_article_detail(_page, url, BBS_Url, debug=debug)
                except Exception:
                    item["floors"] = []
            else:
                item["floors"] = []

    section_url = ""
    for s in sections:
        if (s.get("name") or "").strip() == section_name:
            section_url = (s.get("url") or "").strip()
            break
    section_with_intros = {
        "name": section_name,
        "url": section_url,
        "boards": [{"name": board_name, "url": board_url, "introductions": introductions}],
    }
    save_introductions([section_with_intros], only_last_section=True)
    intro_path = _get_introductions_path()
    return {
        "board_name": board_name,
        "section_name": section_name,
        "introductions_path": str(intro_path),
        "count": len(introductions),
    }


# ---------------------------------------------------------------------------
# 向量库更新（在初始化之后调用，或单独「仅向量化」）
# ---------------------------------------------------------------------------


def update_vector_store(debug: bool = False) -> dict:
    """
    更新向量库：先按 chroma 配置加载知识库文件（info_path、section_info），再加载介绍目录下 介绍*.json。
    可在 run_init / run_single_board_init 之后调用，也可单独调用（仅向量化已有内容，不爬取）。
    :return: {"loaded_document": True, "loaded_introductions": True, "message": "..."}
    """
    try:
        from rag.vector_store import VectorStoreService
        vs = VectorStoreService()
        vs.load_document()
        if debug:
            print("[DEBUG] 知识库文件（info_path/section_info）已同步到向量库")
        vs.load_introductions()
        if debug:
            print("[DEBUG] 介绍（介绍*.json）已同步到向量库")
        return {
            "loaded_document": True,
            "loaded_introductions": True,
            "message": "向量库已更新（知识库文件 + 介绍）。",
        }
    except Exception as e:
        if debug:
            print(f"[DEBUG] 向量库更新失败: {e}")
        return {
            "loaded_document": False,
            "loaded_introductions": False,
            "message": f"向量库更新失败: {e}",
        }


def run_vectorize_only(debug: bool = False) -> dict:
    """
    不爬取，仅将已有内容向量化：将 config 中知识库路径与介绍目录下的 介绍*.json 写入向量库。
    无需启动浏览器，直接调用 update_vector_store。
    """
    return update_vector_store(debug=debug)


# ---------------------------------------------------------------------------
# 工具三：关闭浏览器（不暴露给 Agent）
# ---------------------------------------------------------------------------


def close_browser() -> str:
    """关闭当前浏览器并清除模块状态。与 start_browser 配对使用。"""
    global _playwright, _browser, _page
    if _browser is not None:
        _browser.close()
        _browser = None
    if _playwright is not None:
        _playwright.stop()
        _playwright = None
    _page = None
    return "浏览器已关闭。"


# ---------------------------------------------------------------------------
# Agent 可调用的工具：仅暴露「初始化」整体（内部若无 page 则先启动再初始化再关闭）
# ---------------------------------------------------------------------------


def _get_tool_run_bbs_init():
    from langchain_core.tools import tool

    @tool(
        description="执行 BBS 初始化：爬取登录页配置、讨论区与版面结构、各版面置顶内容并保存到 config/web_structure，然后更新向量库。若当前未打开浏览器则会自动启动并完成后关闭；若已打开则复用当前页面。"
    )
    def run_bbs_init() -> str:
        """执行 BBS 初始化（爬取登录框 -> 登录 -> 爬取版面 -> 爬取置顶 -> 向量库存储）。"""
        global _page
        try:
            if _page is None:
                start_browser(debug=False)
                try:
                    summary = run_init(debug=False)
                    vec = update_vector_store(debug=False)
                finally:
                    close_browser()
            else:
                summary = run_init(debug=False)
                vec = update_vector_store(debug=False)
            base_msg = (
                "当前已初始化，未重复执行爬取。\n" if summary.get("skipped") else "BBS 初始化完成。\n"
            )
            base_msg += (
                f"登录页配置: {summary['login_config_path']}\n"
                f"版面配置: {summary['board_path']}\n"
                f"置顶内容: {summary.get('introductions_path', '')}\n"
            )
            if summary.get("skipped"):
                base_msg += f"向量库: {vec.get('message', '')}\n"
            else:
                base_msg += "init.json 已更新为 init_status: true。\n"
                base_msg += f"向量库: {vec.get('message', '')}\n"
            return base_msg.strip()
        except Exception as e:
            return f"初始化失败: {e}"

    return run_bbs_init


run_bbs_init = _get_tool_run_bbs_init()
