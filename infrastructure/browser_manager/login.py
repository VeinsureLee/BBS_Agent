"""
登录功能：整体逻辑集中在本文件，仅依赖 utils 与 browser_manager。
首次爬取登录页时解析表单并写入 config/data/login_structure.json；
若已存在该文件则直接加载并用于登录。保留 logger。
"""
import sys
import os
import re
import json

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from utils.config_handler import get_bbs_url
from utils.path_tool import get_abs_path
from utils.env_handler import get_bbs_credentials, load_env
from utils.logger_handler import get_logger
from infrastructure.browser_manager.browser_manager import global_browser_manager

logger = get_logger("browser_login")

_LOGIN_STRUCTURE_PATH = get_abs_path("config/data/login_structure.json")


def _load_json(path: str, encoding: str = "utf-8") -> dict:
    """读取 JSON，不存在或解析失败返回空字典。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding=encoding) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def _save_json(path: str, data: dict, encoding: str = "utf-8") -> None:
    """写入 JSON。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=encoding) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_login_config() -> dict:
    """从 config/data/login_structure.json 加载登录页结构配置。"""
    return _load_json(_LOGIN_STRUCTURE_PATH)


def save_login_config(data: dict) -> None:
    """将登录页结构配置保存到 config/data/login_structure.json。"""
    _save_json(_LOGIN_STRUCTURE_PATH, data)
    logger.info("登录页配置已保存至 config/data/login_structure.json")


def _parse_form_from_html(html: str, base_url: str) -> dict:
    """
    从登录页 HTML 中解析表单：form action、账号/密码/提交按钮的 name。
    返回含 login_page_url, form_action, username_input_id, password_input_id, login_button_id 的字典。
    """
    from urllib.parse import urljoin

    result = {
        "login_page_url": base_url.rstrip("/"),
        "form_action": base_url.rstrip("/"),
        "username_input_id": "id",
        "password_input_id": "pwd",
        "login_button_id": "b_login",
    }

    # 解析 <form ... action="...">
    form_match = re.search(
        r'<form[^>]*\s+action\s*=\s*["\']([^"\']*)["\'][^>]*>',
        html,
        re.I | re.DOTALL,
    )
    if form_match:
        result["form_action"] = urljoin(base_url, form_match.group(1).strip())

    # 密码框：取 name，无则用 id
    pwd_match = re.search(
        r'<input[^>]*type\s*=\s*["\']password["\'][^>]*name\s*=\s*["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if not pwd_match:
        pwd_match = re.search(
            r'<input[^>]*name\s*=\s*["\']([^"\']+)["\'][^>]*type\s*=\s*["\']password["\']',
            html,
            re.I,
        )
    if pwd_match:
        result["password_input_id"] = pwd_match.group(1).strip()
    else:
        # 仅 type=password
        pwd_match = re.search(r'<input[^>]*type\s*=\s*["\']password["\'][^>]*>', html, re.I)
        if pwd_match:
            m = re.search(r'id\s*=\s*["\']([^"\']+)["\']', pwd_match.group(0), re.I)
            if m:
                result["password_input_id"] = m.group(1).strip()

    # 账号框：form 内 type=text 或 无 type 的 input
    text_match = re.search(
        r'<input[^>]*type\s*=\s*["\']text["\'][^>]*name\s*=\s*["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if not text_match:
        text_match = re.search(
            r'<input[^>]*name\s*=\s*["\']([^"\']+)["\'][^>]*type\s*=\s*["\']text["\']',
            html,
            re.I,
        )
    if not text_match:
        text_match = re.search(
            r'<input(?![^>]*type)[^>]*name\s*=\s*["\']([^"\']+)["\']',
            html,
            re.I,
        )
    if text_match:
        result["username_input_id"] = text_match.group(1).strip()
    else:
        id_match = re.search(r'<input[^>]*id\s*=\s*["\']id["\'][^>]*>', html, re.I)
        if id_match:
            result["username_input_id"] = "id"

    # 提交按钮：含“登录”或 type=submit 的 input/button 的 name
    submit_match = re.search(
        r'<input[^>]*type\s*=\s*["\']submit["\'][^>]*name\s*=\s*["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if not submit_match:
        submit_match = re.search(
            r'<input[^>]*name\s*=\s*["\']([^"\']+)["\'][^>]*type\s*=\s*["\']submit["\']',
            html,
            re.I,
        )
    if submit_match:
        result["login_button_id"] = submit_match.group(1).strip()
    else:
        btn_match = re.search(
            r'<button[^>]*type\s*=\s*["\']submit["\'][^>]*name\s*=\s*["\']([^"\']+)["\']',
            html,
            re.I,
        )
        if btn_match:
            result["login_button_id"] = btn_match.group(1).strip()
        else:
            b_login = re.search(r'<input[^>]*id\s*=\s*["\']b_login["\'][^>]*>', html, re.I)
            if b_login:
                result["login_button_id"] = "b_login"

    return result


def crawl_login_page_and_save(login_url: str, debug: bool = False) -> dict:
    """
    使用 global_browser_manager 爬取登录页，解析表单结构并写入 login_structure.json。
    返回解析得到的结构字典。
    """
    if not login_url or not login_url.strip():
        raise ValueError("BBS_Url 未设置或为空")
    login_url = login_url.strip().rstrip("/")
    logger.info("正在爬取登录页并解析表单: %s", login_url)
    html = global_browser_manager.crawl_page(login_url)
    if not html:
        raise RuntimeError("爬取登录页失败，未获取到 HTML")
    structure = _parse_form_from_html(html, login_url)
    save_login_config(structure)
    if debug:
        logger.debug(
            "登录页结构: username=%s, password=%s, button=%s, form_action=%s",
            structure["username_input_id"],
            structure["password_input_id"],
            structure["login_button_id"],
            structure["form_action"],
        )
    return structure


def do_login(
    form_action: str,
    username_field: str,
    password_field: str,
    login_button_field: str,
    debug: bool = False,
) -> None:
    """
    使用 global_browser_manager 的会话 POST 提交账号密码完成登录。
    """
    load_env()
    BBS_Name, BBS_Password = get_bbs_credentials()
    if not BBS_Name or not BBS_Password:
        raise ValueError("请设置环境变量 BBS_Name 和 BBS_Password（或 .env 中配置）")
    post_data = {
        username_field: BBS_Name,
        password_field: BBS_Password,
    }
    if login_button_field:
        post_data[login_button_field] = "登录"  # 部分站点需要提交按钮的 value
    logger.info("正在提交登录表单: %s", form_action)
    html = global_browser_manager.post_page(form_action, post_data)
    if debug and html:
        logger.debug("登录响应 HTML 长度: %d", len(html))
    logger.info("登录请求已提交。")


def run_login(debug: bool = False, force_crawl: bool = False) -> None:
    """
    执行登录：若存在 config/data/login_structure.json 则直接使用；
    否则先爬取登录页、解析并保存配置，再登录。仅依赖 utils 与 browser_manager。
    """
    if not global_browser_manager.is_running():
        logger.error("请先调用 global_browser_manager.open_browser() 打开浏览器。")
        raise RuntimeError("请先打开浏览器再执行登录。")

    BBS_Url = (get_bbs_url() or "").strip().rstrip("/")
    if not BBS_Url:
        logger.error("未配置 BBS_Url，请在 config/websites/bbs.json 中设置")
        raise ValueError("未配置 BBS_Url，请在 config/websites/bbs.json 中设置")

    login_cfg = load_login_config()
    need_crawl = force_crawl or not (login_cfg.get("login_page_url"))

    if need_crawl:
        structure = crawl_login_page_and_save(BBS_Url, debug=debug)
        do_login(
            structure.get("form_action", structure["login_page_url"]),
            structure["username_input_id"],
            structure["password_input_id"],
            structure.get("login_button_id", "b_login"),
            debug=debug,
        )
    else:
        form_action = login_cfg.get("form_action") or login_cfg.get("login_page_url")
        do_login(
            form_action,
            login_cfg.get("username_input_id", "id"),
            login_cfg.get("password_input_id", "pwd"),
            login_cfg.get("login_button_id", "b_login"),
            debug=debug,
        )
    logger.info("登录流程结束。")
