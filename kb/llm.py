"""LLM 调用模块 —— 兼容 OpenAI 接口的任意大模型"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger(__name__)


def _get_llm_config(user_id: str = None) -> Dict[str, Any]:
    from kb.config import get_llm_config
    return get_llm_config(user_id)


def is_llm_available(user_id: str = None) -> bool:
    cfg = _get_llm_config(user_id)
    return bool(
        cfg.get('enabled', False) and
        cfg.get('api_key') and
        cfg.get('base_url') and
        cfg.get('model')
    )


def call_llm(
    system_prompt: str,
    user_query: str,
    messages_history: List[Dict[str, str]] = None,
    temperature: float = None,
    max_tokens: int = None,
    user_id: str = None,
) -> str:
    cfg = _get_llm_config(user_id)

    if not is_llm_available(user_id):
        return None

    api_key = cfg['api_key']
    base_url = cfg['base_url'].rstrip('/')
    model = cfg['model']
    temperature = temperature if temperature is not None else cfg.get('temperature', 0.7)
    max_tokens = max_tokens if max_tokens is not None else cfg.get('max_tokens', 4096)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if messages_history:
        messages.extend(messages_history)
    messages.append({"role": "user", "content": user_query})

    if not HAS_REQUESTS:
        logger.error("requests 库未安装，无法调用 LLM")
        return None

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        logger.error("LLM 调用超时 (60s)")
        return None
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        return None


def call_llm_stream(
    system_prompt: str,
    user_query: str,
    messages_history: List[Dict[str, str]] = None,
    temperature: float = None,
    max_tokens: int = None,
    user_id: str = None,
):
    if not is_llm_available(user_id):
        return

    cfg = _get_llm_config(user_id)
    api_key = cfg['api_key']
    base_url = cfg['base_url'].rstrip('/')
    model = cfg['model']
    temperature = temperature if temperature is not None else cfg.get('temperature', 0.7)
    max_tokens = max_tokens if max_tokens is not None else cfg.get('max_tokens', 4096)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if messages_history:
        messages.extend(messages_history)
    messages.append({"role": "user", "content": user_query})

    if not HAS_REQUESTS:
        logger.error("requests 库未安装，无法调用 LLM")
        return

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
            timeout=120,
            stream=True,
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                data_str = line_str[6:]
                if data_str.strip() == '[DONE]':
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error("LLM 流式调用失败: %s", e)


_TITLE_PROMPT = (
    "Generate a short, descriptive title (3-7 words) for a conversation that starts with the "
    "following exchange. The title should capture the main topic or intent. "
    "Return ONLY the title text, nothing else. No quotes, no punctuation at the end, no prefixes."
)


def generate_title(user_message: str, assistant_response: str, user_id: str = None) -> Optional[str]:
    if not is_llm_available(user_id):
        return None

    user_snippet = (user_message or "")[:500]
    assistant_snippet = (assistant_response or "")[:500]

    try:
        title = call_llm(
            system_prompt=_TITLE_PROMPT,
            user_query=f"User: {user_snippet}\n\nAssistant: {assistant_snippet}",
            temperature=0.3,
            max_tokens=100,
            user_id=user_id,
        )
        if not title:
            return None
        title = title.strip().strip('"\'')
        if title.lower().startswith("title:"):
            title = title[6:].strip()
        if len(title) > 80:
            title = title[:77] + "..."
        return title if title else None
    except Exception as e:
        logger.debug("Title generation failed: %s", e)
        return None


def call_llm_with_tools(
    system_prompt: str,
    user_query: str,
    messages_history: List[Dict[str, str]] = None,
    tools: List[Dict] = None,
    max_tool_rounds: int = 5,
    tool_executor: Callable = None,
    temperature: float = None,
    max_tokens: int = None,
    user_id: str = None,
    interrupt_event=None,
) -> Dict[str, Any]:
    result = {
        "content": "",
        "tool_calls_made": [],
        "tool_results": [],
        "error": None,
        "interrupted": False,
    }

    if not is_llm_available(user_id):
        result["error"] = "LLM 未配置或不可用"
        return result

    cfg = _get_llm_config(user_id)
    api_key = cfg['api_key']
    base_url = cfg['base_url'].rstrip('/')
    model = cfg['model']
    temperature = temperature if temperature is not None else cfg.get('temperature', 0.7)
    max_tokens = max_tokens if max_tokens is not None else cfg.get('max_tokens', 4096)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if messages_history:
        messages.extend(messages_history)
    messages.append({"role": "user", "content": user_query})

    if not HAS_REQUESTS:
        logger.error("requests 库未安装，无法调用 LLM")
        result["error"] = "requests 库未安装"
        return result

    for round_idx in range(max_tool_rounds + 1):
        if interrupt_event and interrupt_event.is_set():
            logger.info("LLM 调用被用户中断 (round %d)", round_idx)
            result["interrupted"] = True
            result["content"] = messages[-1].get("content", "") if messages else ""
            return result

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            logger.error("LLM 调用超时 (120s)")
            result["error"] = "LLM 调用超时"
            return result
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            result["error"] = f"LLM 调用失败: {e}"
            return result

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            content = msg.get("content", "")
            result["content"] = content or ""
            return result

        if not tool_executor:
            content = msg.get("content", "")
            result["content"] = content or ""
            return result

        messages.append(msg)

        for tc in tool_calls:
            if interrupt_event and interrupt_event.is_set():
                logger.info("工具执行被用户中断 (round %d)", round_idx)
                result["interrupted"] = True
                result["content"] = messages[-1].get("content", "") if messages else ""
                return result

            tc_id = tc.get("id", "")
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            logger.info("Tool call: %s(%s)", tool_name, json.dumps(args, ensure_ascii=False)[:200])
            tool_result = tool_executor(tool_name, args)

            result["tool_calls_made"].append({
                "id": tc_id,
                "name": tool_name,
                "arguments": args,
            })
            result["tool_results"].append({
                "tool_name": tool_name,
                "result": tool_result,
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": tool_result,
            })

    result["content"] = messages[-1].get("content", "") if messages else ""
    return result


def call_llm_with_tools_stream(
    system_prompt: str,
    user_query: str,
    messages_history: List[Dict[str, str]] = None,
    tools: List[Dict] = None,
    max_tool_rounds: int = 5,
    tool_executor: Callable = None,
    temperature: float = None,
    max_tokens: int = None,
    user_id: str = None,
    interrupt_event=None,
    sources: List[Dict] = None,
):
    """
    流式版本的多轮工具调用 LLM 生成器。
    逐个 token 产出事件字典，由调用方序列化为 SSE 事件。
    事件类型: source / token / tool_call / tool_result / done / interrupted / error
    """
    if not is_llm_available(user_id):
        yield {"type": "error", "message": "LLM 未配置或不可用"}
        return

    if sources:
        yield {"type": "source", "sources": sources}

    cfg = _get_llm_config(user_id)
    api_key = cfg['api_key']
    base_url = cfg['base_url'].rstrip('/')
    model = cfg['model']
    temperature = temperature if temperature is not None else cfg.get('temperature', 0.7)
    max_tokens = max_tokens if max_tokens is not None else cfg.get('max_tokens', 4096)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if messages_history:
        messages.extend(messages_history)
    messages.append({"role": "user", "content": user_query})

    if not HAS_REQUESTS:
        yield {"type": "error", "message": "requests 库未安装"}
        return

    full_content = ""
    total_tool_calls = 0

    for round_idx in range(max_tool_rounds + 1):
        if interrupt_event and interrupt_event.is_set():
            yield {"type": "interrupted"}
            return

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
                stream=True,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error("LLM 流式调用失败: %s", e)
            yield {"type": "error", "message": f"LLM 调用失败: {e}"}
            return

        round_content = ""
        tool_calls_buffer = {}  # index -> {id, name, arguments}
        tool_calls_invoked = False

        for line in resp.iter_lines():
            if not line:
                continue

            if interrupt_event and interrupt_event.is_set():
                resp.close()
                yield {"type": "interrupted"}
                return

            line_str = line.decode('utf-8')
            if not line_str.startswith('data: '):
                continue
            data_str = line_str[6:]
            if data_str.strip() == '[DONE]':
                break

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            choices = data.get("choices", [])
            if not choices:
                continue

            delta = choices[0].get("delta", {})
            finish_reason = choices[0].get("finish_reason")

            # 文本 token
            content = delta.get("content")
            if content:
                round_content += content
                full_content += content
                yield {"type": "token", "content": content}

            # 工具调用（流式增量）
            tc_delta = delta.get("tool_calls")
            if tc_delta:
                for tc in tc_delta:
                    idx = tc.get("index", 0)
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": tc.get("id", ""),
                            "name": "",
                            "arguments": "",
                        }
                    buf = tool_calls_buffer[idx]
                    if tc.get("id"):
                        buf["id"] = tc["id"]
                    fn = tc.get("function", {})
                    if fn.get("name"):
                        buf["name"] += fn["name"]
                    if fn.get("arguments"):
                        buf["arguments"] += fn["arguments"]

            if finish_reason == "tool_calls":
                # 构建 assistant 消息加入对话历史
                assistant_msg = {"role": "assistant", "content": round_content or None}
                tool_calls_list = []
                for idx in sorted(tool_calls_buffer.keys()):
                    buf = tool_calls_buffer[idx]
                    tool_calls_list.append({
                        "id": buf["id"],
                        "type": "function",
                        "function": {"name": buf["name"], "arguments": buf["arguments"]},
                    })
                assistant_msg["tool_calls"] = tool_calls_list
                messages.append(assistant_msg)

                # 逐个执行工具
                for tc_data in tool_calls_list:
                    if interrupt_event and interrupt_event.is_set():
                        yield {"type": "interrupted"}
                        return

                    tc_id = tc_data["id"]
                    fn_data = tc_data["function"]
                    tool_name = fn_data.get("name", "")
                    try:
                        args = json.loads(fn_data.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}

                    logger.info("Tool call: %s(%s)", tool_name, json.dumps(args, ensure_ascii=False)[:200])
                    total_tool_calls += 1
                    yield {"type": "tool_call", "name": tool_name, "arguments": args}

                    tool_result = tool_executor(tool_name, args)
                    yield {"type": "tool_result", "tool_name": tool_name, "result": tool_result}

                    # 将工具自动搜索到的结果也加入参考来源
                    if sources is not None:
                        try:
                            result_data = json.loads(tool_result)
                            if result_data.get("success"):
                                existing_paths = {s.get("path") for s in sources}
                                if tool_name == "wiki_search":
                                    for r in result_data.get("results", []):
                                        if r["path"] not in existing_paths:
                                            sources.append({"path": r["path"], "title": r["title"]})
                                    yield {"type": "source", "sources": sources}
                                elif tool_name == "web_search":
                                    for r in result_data.get("results", []):
                                        url = r.get("url", "")
                                        if url and url not in existing_paths:
                                            sources.append({"path": url, "title": r.get("title", url), "_type": "web"})
                                    yield {"type": "source", "sources": sources}
                        except (json.JSONDecodeError, KeyError):
                            pass

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": tool_result,
                    })

                tool_calls_invoked = True
                break  # 跳出 line 循环，进入下一轮

            if finish_reason == "stop":
                yield {"type": "done", "content": full_content, "tool_calls": total_tool_calls}
                return

        # 如果没有工具调用、没有 stop 信号（异常 EOF），结束
        if not tool_calls_invoked:
            break

    yield {"type": "done", "content": full_content, "tool_calls": total_tool_calls}
