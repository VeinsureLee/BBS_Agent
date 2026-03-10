import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_handler import load_json_config
from utils.path_tool import get_abs_path
from utils.logger_handler import logger
from utils.dimension_config import get_dimensions_instruction, get_json_schema_for_prompt

# 提示词路径配置（config/prompts/prompts.json）
prompts_conf = load_json_config(default_path="config/prompts/prompts.json")


def load_system_prompts():
    try:
        system_prompt_path = get_abs_path(prompts_conf["main_prompt_path"])
    except KeyError as e:
        logger.error(f"[load_system_prompts]在yaml配置项中没有main_prompt_path配置项")
        raise e

    try:
        return open(system_prompt_path, "r", encoding="utf-8").read()
    except Exception as e:
        logger.error(f"[load_system_prompts]解析系统提示词出错，{str(e)}")
        raise e


def load_rag_prompts():
    try:
        rag_prompt_path = get_abs_path(prompts_conf["rag_summarize_prompt_path"])
    except KeyError as e:
        logger.error(f"[load_rag_prompts]在yaml配置项中没有rag_summarize_prompt_path配置项")
        raise e

    try:
        return open(rag_prompt_path, "r", encoding="utf-8").read()
    except Exception as e:
        logger.error(f"[load_rag_prompts]解析RAG总结提示词出错，{str(e)}")
        raise e


def load_plan_prompts():
    """加载规划阶段提示词（Plan：根据用户输入生成任务列表）。"""
    try:
        plan_prompt_path = get_abs_path(prompts_conf["plan_prompt_path"])
    except KeyError as e:
        logger.error(f"[load_plan_prompts]配置项中没有 plan_prompt_path")
        raise e
    try:
        return open(plan_prompt_path, "r", encoding="utf-8").read()
    except Exception as e:
        logger.error(f"[load_plan_prompts]解析规划提示词出错，{str(e)}")
        raise e


def load_replan_prompts():
    """加载重新规划提示词（Replan：根据执行状态与受阻原因生成后续任务）。"""
    try:
        replan_prompt_path = get_abs_path(prompts_conf["replan_prompt_path"])
    except KeyError as e:
        logger.error(f"[load_replan_prompts]配置项中没有 replan_prompt_path")
        raise e
    try:
        return open(replan_prompt_path, "r", encoding="utf-8").read()
    except Exception as e:
        logger.error(f"[load_replan_prompts]解析重新规划提示词出错，{str(e)}")
        raise e


def load_answer_sufficiency_prompt():
    """加载回答充分性判断提示词（用于轮次结束后判断当前结果是否足以回答用户问题）。"""
    try:
        path = get_abs_path(prompts_conf.get("answer_sufficiency_prompt_path", "prompts/answer_sufficiency_prompt.txt"))
    except Exception:
        path = get_abs_path("prompts/answer_sufficiency_prompt.txt")
    try:
        return open(path, "r", encoding="utf-8").read()
    except Exception as e:
        logger.warning("[load_answer_sufficiency_prompt] 加载失败，使用内联默认: %s", e)
        return (
            "用户问题：{user_input}\n当前已收集信息摘要：{collected_summary}\n\n"
            "请判断这些信息是否足以回答用户问题。若信息与问题无关或过少，判为不充分。\n"
            "仅输出 JSON：{{\"sufficient\": true或false, \"reason\": \"原因\"}}"
        )


def load_prompt_generate():
    """加载版面说明生成用提示词模板（prompts/prompt_generate.txt），并从 config/data/data_dimension.json 填入维度说明与 JSON  schema。"""
    try:
        prompt_generate_path = get_abs_path(prompts_conf["prompt_generate_path"])
    except KeyError as e:
        logger.error(f"[load_prompt_generate]配置项中没有 prompt_generate_path")
        raise e

    try:
        template = open(prompt_generate_path, "r", encoding="utf-8").read()
        template = template.replace("{dimensions_instruction}", get_dimensions_instruction())
        template = template.replace("{json_schema}", get_json_schema_for_prompt())
        return template
    except Exception as e:
        logger.error(f"[load_prompt_generate]解析版面说明生成提示词出错，{str(e)}")
        raise e


if __name__ == '__main__':
    print(load_system_prompts())
    print("="*20)
    print(load_rag_prompts())
    print("="*20)
    print(load_prompt_generate())
    print("="*20)

