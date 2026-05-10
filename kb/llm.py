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
        yield None


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
) -> Dict[str, Any]:
    result = {
        "content": "",
        "tool_calls_made": [],
        "tool_results": [],
    }

    if not is_llm_available(user_id):
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
        return result

    for round_idx in range(max_tool_rounds + 1):
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
            return result
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
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
