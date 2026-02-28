"""
初始化工具：提供「初始化」「向量库更新」等能力。
- 启动/关闭浏览器：见 browser_tools，供 main 或调用方使用。
- 初始化：爬取登录框 -> 登录 -> 爬取版面 -> 爬取置顶 -> 生成版面/讨论区提示词 -> 向量库存储；使用 browser_tools 的 page。
- 向量库更新：将知识库文件、讨论区/版面说明、介绍（置顶）写入向量库（MD5 增量）。
- 仅向量化：不爬取，仅将已有内容写入向量库。

同一浏览器实例内顺序：启动浏览器（browser_tools）-> 初始化（使用该 page）-> 向量库存储 -> 关闭浏览器（browser_tools）。
"""
import json
from pathlib import Path

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
from agent.tools.init_tools.browser_tools import start_browser, close_browser, get_page
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
from agent.tools.init_tools.prompts_tools import generate_and_save_boards_prompt
from utils.timer import timer


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


# init.json 中各子状态键名（与 config 一致）
INIT_STATUS_KEYS = (
    "init_status",
    "login_status",       # 登录状态：是否抓取登录各窗口
    "board_status",       # 爬取状态：是否爬取讨论区与版面
    "board_top_status",   # 是否爬取置顶
    "prompts_status",     # 提示词生成状态：是否生成提示词
    "vector_store_status", # 向量库储存：是否按当前规则储存
)


def _load_init_status_data() -> dict:
    """读取 init.json，返回各状态字段，缺失则默认为 False。"""
    path = _get_init_status_path()
    default = {k: False for k in INIT_STATUS_KEYS}
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k in INIT_STATUS_KEYS:
            if k in data:
                default[k] = data[k] is True
        return default
    except Exception:
        return default


def _set_init_status(success: bool) -> None:
    """初始化完成后更新 init.json：成功则写 init_status 与爬取相关子状态为 True，保留 vector_store_status；失败则全部置 False。"""
    path = _get_init_status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = _load_init_status_data()
    if success:
        data = {
            "init_status": True,
            "login_status": True,
            "board_status": True,
            "board_top_status": True,
            "prompts_status": True,
            "vector_store_status": current.get("vector_store_status", False),
        }
    else:
        data = {k: False for k in INIT_STATUS_KEYS}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _update_init_status_fields(updates: dict) -> None:
    """仅更新 init.json 中指定字段，其余保留。"""
    path = _get_init_status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_init_status_data()
    for k, v in updates.items():
        if k in INIT_STATUS_KEYS:
            data[k] = bool(v)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_initialized() -> bool:
    """检查 config/web_structure/init.json 中 init_status 是否为 True；为 True 时整体视为已初始化并跳过。"""
    return _load_init_status_data().get("init_status") is True


# ---------------------------------------------------------------------------
# 初始化（爬取登录框 -> 登录 -> 爬取版面 -> 爬取置顶 -> 生成提示词 -> 向量库）
# ---------------------------------------------------------------------------


def run_init(debug: bool = False) -> dict:
    """
    使用当前已打开的 page 执行完整初始化：登录 -> 爬取讨论区与版面 -> 爬取置顶 -> 生成版面/讨论区提示词。
    必须先调用 start_browser()，否则抛出 RuntimeError。
    若已初始化（init.json 中 init_status 为 True），则跳过爬取并直接返回路径信息。
    未完全初始化时按 init.json 中的 login_status / board_status / board_top_status / prompts_status 跳过已完成步骤。
    """
    _page = get_page()
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
    status = _load_init_status_data()

    try:
        # 1. 登录（使用 infrastructure.browser_manager.login，配置与保存走 utils）
        from infrastructure.browser_manager.login import run_login
        run_login(debug=debug, force_crawl=not status.get("login_status"))
        if not status.get("login_status"):
            _update_init_status_fields({"login_status": True})

        # 2. 爬取状态：是否爬取讨论区与版面
        if not status.get("board_status"):
            if debug:
                print("[DEBUG] 版面结构爬取（board_tools）:")
            board_path.parent.mkdir(parents=True, exist_ok=True)
            sections = crawl_sections_and_boards(_page, BBS_Url, section_count=SECTION_COUNT, debug=debug)
            with open(board_path, "w", encoding="utf-8") as f:
                json.dump({"sections": sections}, f, ensure_ascii=False, indent=2)
            if debug:
                print("[DEBUG] 版面配置已保存到:", board_path)
            _update_init_status_fields({"board_status": True})
        else:
            board_cfg = load_web_structure_board_config()
            sections = board_cfg.get("sections", [])

        # 3. 是否爬取置顶
        if not status.get("board_top_status"):
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
            _update_init_status_fields({"board_top_status": True})
        else:
            # 置顶已爬过，需 sections 用于后续提示词（若未生成）
            sections_with_intros = []  # 仅 prompts 可能用到 board 结构，此处不重读 introductions

        # 4. 提示词生成状态：是否生成提示词
        if not status.get("prompts_status"):
            generate_and_save_boards_prompt(debug=debug)
            _update_init_status_fields({"prompts_status": True})

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
    if get_page() is None:
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
    from infrastructure.browser_manager.login import run_login
    run_login(debug=debug, force_crawl=False)

    request_url = board_url_to_request_url(board_url, BBS_Url)
    introductions = crawl_board_introductions(
        get_page(), request_url, section_name, board_name, debug=debug
    )
    if fetch_article_detail and introductions:
        from agent.tools.init_tools.inroductions import crawl_article_detail
        for item in introductions:
            url = (item.get("url") or "").strip()
            if url:
                try:
                    item["floors"] = crawl_article_detail(get_page(), url, BBS_Url, debug=debug)
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
    更新向量库：加载知识库文件与 data/boards_guide 下各版面向量化说明，不写入置顶帖子全文，避免冗余。
    可在 run_init / run_single_board_init 之后调用，也可单独调用（仅向量化已有内容，不爬取）。
    成功后会将 init.json 中 vector_store_status 置为 True。
    :return: {"loaded_document": True, "loaded_board_guide": True, "message": "..."}
    """
    try:
        from rag.vector_store import VectorStoreService
        vs = VectorStoreService()
        vs.load_document()
        if debug:
            print("[DEBUG] 知识库文件（info_path/section_info）已同步到向量库")
        vs.load_board_guide()
        if debug:
            print("[DEBUG] 讨论区/版面说明（data/boards_guide）已同步到向量库")
        _update_init_status_fields({"vector_store_status": True})
        return {
            "loaded_document": True,
            "loaded_board_guide": True,
            "message": "向量库已更新（知识库文件 + 讨论区/版面说明）。",
        }
    except Exception as e:
        if debug:
            print(f"[DEBUG] 向量库更新失败: {e}")
        return {
            "loaded_document": False,
            "loaded_board_guide": False,
            "message": f"向量库更新失败: {e}",
        }


def run_vectorize_only(debug: bool = False) -> dict:
    """
    不爬取，仅将已有内容向量化：将知识库文件与 data/boards_guide 下版面说明写入向量库（不写入置顶帖子全文）。
    无需启动浏览器，直接调用 update_vector_store。
    """
    return update_vector_store(debug=debug)


# ---------------------------------------------------------------------------
# Agent 可调用的工具：仅暴露「初始化」整体（内部若无 page 则先启动再初始化再关闭）
# ---------------------------------------------------------------------------


def _get_tool_run_bbs_init():
    from langchain_core.tools import tool

    @tool(
        description="执行 BBS 初始化：登录浏览器 -> 爬取讨论区与版面 -> 爬取置顶 -> 生成讨论区/版面说明到 data/boards_guide -> 将版面说明与知识库写入向量库。若当前未打开浏览器则会自动启动并完成后关闭；若已打开则复用当前页面。"
    )
    def run_bbs_init() -> str:
        """执行 BBS 初始化（登录 -> 爬取版面 -> 爬取置顶 -> 生成提示词 -> 仅将精简讨论区/版面说明与知识库存向量库）。"""
        try:
            if get_page() is None:
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


# ---------------------------------------------------------------------------
# 供 Agent 爬取前启动、爬取后关闭浏览器
# ---------------------------------------------------------------------------


def _get_tool_start_browser():
    from langchain_core.tools import tool

    @tool(description="启动浏览器并保持打开，用于后续爬取版面列表或帖子详情。爬取前若未打开浏览器可先调用此工具。")
    def start_browser_tool(debug: bool = False) -> str:
        return start_browser(debug=debug)

    return start_browser_tool


def _get_tool_close_browser():
    from langchain_core.tools import tool

    @tool(description="关闭当前已打开的浏览器。完成爬取后可调用此工具释放资源。")
    def close_browser_tool() -> str:
        return close_browser()

    return close_browser_tool


start_browser_tool = _get_tool_start_browser()
close_browser_tool = _get_tool_close_browser()
