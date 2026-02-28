"""
版面说明总结：调用 chat 模型生成介绍总结，遇 KeyError('request') 等时重试并 print。
"""
import time

from langchain_core.messages import HumanMessage

from infrastructure.model_factory.factory import chat_model

# 重试间隔（秒）
RETRY_DELAYS = (1.0, 2.0, 3.0)
# 其他异常最大重试次数
MAX_RETRIES = 1024
# KeyError('request') 最大重试次数（重复直至正确总结）
REQUEST_KEYERROR_MAX = 10000


def summarize_with_prompt(
    content: str,
    prompt_template: str,
    section_name: str = "",
    board_name: str = "",
) -> str:
    """根据讨论区/版面与置顶内容生成版面说明总结。遇 KeyError('request') 重复直至成功或达上限。"""
    prompt = prompt_template.format(
        section_name=section_name or "未知讨论区",
        board_name=board_name or "未知版面",
        intro_summary=content,
    )
    request_err_count = 0
    other_err_count = 0
    last_err: Exception | None = None
    while True:
        try:
            response = chat_model.invoke([HumanMessage(content=prompt)])
            result = (getattr(response, "content", None) or str(response) or "").strip()
            if result:
                return result
            last_err = ValueError("模型返回空内容")
            other_err_count += 1
            if other_err_count >= MAX_RETRIES:
                raise last_err
            delay = RETRY_DELAYS[(other_err_count - 1) % len(RETRY_DELAYS)]
            print(f"[总结失败并重试] 返回空 | {section_name}/{board_name} | {delay}s 后重试 ({other_err_count}/{MAX_RETRIES})", flush=True)
            time.sleep(delay)
        except KeyError as e:
            if e.args and e.args[0] == "request":
                last_err = e
                request_err_count += 1
                if request_err_count >= REQUEST_KEYERROR_MAX:
                    print(f"[总结失败] KeyError('request') 已达最大重试 {REQUEST_KEYERROR_MAX}，放弃", flush=True)
                    raise last_err
                delay = RETRY_DELAYS[(request_err_count - 1) % len(RETRY_DELAYS)]
                print(f"[总结失败并重试] KeyError('request') | {section_name}/{board_name} | {delay}s 后重试 ({request_err_count}/{REQUEST_KEYERROR_MAX})", flush=True)
                time.sleep(delay)
            else:
                last_err = e
                other_err_count += 1
                if other_err_count >= MAX_RETRIES:
                    print(f"[总结失败] KeyError 已达最大重试 {MAX_RETRIES}，放弃: {e}", flush=True)
                    raise last_err
                delay = RETRY_DELAYS[min(other_err_count - 1, len(RETRY_DELAYS) - 1)]
                print(f"[总结失败并重试] KeyError | {section_name}/{board_name} | {delay}s 后重试 ({other_err_count}/{MAX_RETRIES}): {e}", flush=True)
                time.sleep(delay)
        except (ConnectionError, TimeoutError) as e:
            last_err = e
            other_err_count += 1
            if other_err_count >= MAX_RETRIES:
                print(f"[总结失败] 网络/超时已达最大重试 {MAX_RETRIES}，放弃: {e}", flush=True)
                raise last_err
            delay = RETRY_DELAYS[min(other_err_count - 1, len(RETRY_DELAYS) - 1)]
            print(f"[总结失败并重试] {type(e).__name__} | {section_name}/{board_name} | {delay}s 后重试 ({other_err_count}/{MAX_RETRIES}): {e}", flush=True)
            time.sleep(delay)
