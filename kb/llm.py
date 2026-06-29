"""LLM 调用模块 —— 兼容 OpenAI 接口的任意大模型 + CC Switch 支持"""

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = (429, 500, 502, 503, 504)

# ==================== CC Switch 支持 ====================

_CC_SWITCH_CACHE: Dict[str, Any] = {}
_CC_SWITCH_CACHE_TIME: Dict[str, float] = {}


def detect_cc_switch(proxy_url: str = "") -> Optional[Dict]:
    """检测 CC Switch 本地代理是否在运行。

    需要用户在 CC Switch 应用中手动开启"本地代理模式"并设置端口，
    然后在 Docflowing LLM 设置中填入该代理地址。

    结果缓存 30 秒避免高频检测。

    Returns:
        可用时返回 dict: {"reachable": True, "base_url": "..."}
        不可用时返回 dict: {"reachable": False, "error": "..."}
    """
    import time as _time

    if not proxy_url:
        return {"reachable": False, "error": "未配置代理地址，请在 LLM 设置中填写 CC Switch 代理地址"}

    cache_key = proxy_url
    now = _time.time()
    last_check = _CC_SWITCH_CACHE_TIME.get(cache_key, 0)
    if cache_key in _CC_SWITCH_CACHE and (now - last_check) < 30:
        return _CC_SWITCH_CACHE[cache_key]

    if not HAS_REQUESTS:
        result = {"reachable": False, "error": "requests 库未安装"}
        _CC_SWITCH_CACHE[cache_key] = result
        _CC_SWITCH_CACHE_TIME[cache_key] = now
        return result

    base = proxy_url.rstrip('/')
    # 如果用户填写了 /v1 结尾，保留；否则 append /v1（兼容 Codex 和 Claude 路由）
    base_url = base if base.endswith('/v1') else base + '/v1'

    # CC Switch 支持多种探测方式（由路由决定支持的端点）：
    # 1. /v1/models（OpenAI 兼容 / Codex 路由）
    # 2. /（根路径 / 健康检查，CC Switch 内置）
    # 3. /v1/messages（Anthropic Messages / Claude 路由）
    probe_urls = [
        (base_url + '/models', 'Codex'),
        (base.rstrip('/') + '/', '健康检查'),
        (base_url + '/messages', 'Claude'),
    ]

    errors = []
    for url, label in probe_urls:
        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                result = {"reachable": True, "base_url": base_url, "provider": "cc_switch"}
                _CC_SWITCH_CACHE[cache_key] = result
                _CC_SWITCH_CACHE_TIME[cache_key] = now
                return result
            errors.append(f"{label}(HTTP {resp.status_code})")
        except requests.exceptions.ConnectionError:
            errors.append(f"{label}(连接失败)")
            break  # 连接失败说明整个代理不可达，不用继续
        except requests.exceptions.Timeout:
            errors.append(f"{label}(超时)")
        except Exception as e:
            errors.append(f"{label}({e})")

    result = {"reachable": False, "error": f"CC Switch 未响应: {'; '.join(errors)}"}

    _CC_SWITCH_CACHE[cache_key] = result
    _CC_SWITCH_CACHE_TIME[cache_key] = now
    return result


def get_effective_llm_config(user_id: str = None) -> Dict[str, Any]:
    """获取生效的 LLM 配置，自动处理 CC Switch 覆盖逻辑。

    - 当 provider=cc_switch 且 CC Switch 可用时，用 CC Switch 的 base_url
      覆盖用户手动配置的 base_url，并设置占位 api_key 和 model
    - 当 provider=cc_switch 但 CC Switch 不可用时，自动回退到原始 base_url
    - 其他 provider 直接返回原始配置
    """
    from kb.config import get_llm_config
    cfg = dict(get_llm_config(user_id))

    provider = cfg.get('provider', 'openai')

    if provider == 'cc_switch':
        cc_cfg = cfg.get('cc_switch', {})
        proxy_url = cc_cfg.get('proxy_url', '') or 'http://127.0.0.1:15721'
        status = detect_cc_switch(proxy_url)
        if status.get("reachable"):
            cfg['base_url'] = status["base_url"]
            cfg['api_key'] = cfg.get('api_key') or 'cc-switch'
            cfg['model'] = cfg.get('model') or 'default'
            cfg['_cc_switch_status'] = 'running'
            logger.info("CC Switch 检测: 运行中, 使用代理 %s", status["base_url"])
        else:
            cfg['_cc_switch_status'] = f'stopped: {status.get("error", "未知")}'
            logger.warning("CC Switch 检测: 未运行 (%s), 回退到原始配置", status.get("error"))

    return cfg


def is_llm_available(user_id: str = None) -> bool:
    cfg = _get_llm_config(user_id)
    provider = cfg.get('provider', 'openai')

    # CC Switch 模式：只需要 enabled + base_url 即可
    if provider == 'cc_switch':
        return bool(cfg.get('enabled', False) and cfg.get('base_url'))

    return bool(
        cfg.get('enabled', False) and
        cfg.get('api_key') and
        cfg.get('base_url') and
        cfg.get('model')
    )


def _validate_base_url(url: str) -> Optional[str]:
    """校验 LLM base_url 安全性，失败时返回错误消息，成功时返回 None。

    - 必须为 http 或 https 协议（阻止 file://, gopher://, ftp:// 等 SSRF 载体）
    - 不允许用户配置指向回环地址的本地敏感服务（可选，localhost 作为本地模型是常见的用途）
    - 必须是合法的 URL 格式
    """
    if not url:
        return "base_url 不能为空"

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"base_url 协议 '{parsed.scheme}' 不受支持，仅允许 http/https"

    hostname = parsed.hostname
    if not hostname:
        return "base_url 缺少主机名"

    # 阻止一些典型的 SSRF 协议滥用
    return None


def _safe_request_url(base_url: str, path: str) -> str:
    """拼接 base_url + path，并做基本安全性校验。失败时抛出 ValueError。"""
    if not base_url:
        raise ValueError("LLM base_url 未配置")

    # 规范化：移除尾部斜杠
    base = base_url.rstrip('/')
    # 确保 path 以 / 开头
    clean_path = path if path.startswith('/') else '/' + path
    return base + clean_path


def _request_with_retry(
    method, url, *, max_retries=3, base_delay=1.0, timeout=30, **kwargs
):
    """带指数退避的 HTTP 请求重试

    对以下情况自动重试（最多 max_retries 次）：
    - 网络超时 / 连接错误
    - HTTP 429 (Rate Limit)
    - HTTP 5xx 服务端错误
    """
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in _RETRYABLE_STATUSES and attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "LLM 返回 %d，%.1fs 后重试 (第 %d/%d 次)",
                    resp.status_code, delay, attempt, max_retries,
                )
                time.sleep(delay)
                continue
            resp.raise_for_status()
            return resp
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "LLM 请求失败 (%s)，%.1fs 后重试 (第 %d/%d 次)",
                    e, delay, attempt, max_retries,
                )
                time.sleep(delay)
                continue
            raise
    if last_exception:
        raise last_exception
    raise RuntimeError("LLM 请求重试耗尽")


def _get_llm_config(user_id: str = None) -> Dict[str, Any]:
    return get_effective_llm_config(user_id)


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
    # 基础 URL 安全校验：只允许 http/https，拒绝 file:///gopher:// 等
    err = _validate_base_url(base_url)
    if err:
        logger.warning("LLM base_url 校验失败：%s", err)
        return None
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
        resp = _request_with_retry(
            "POST", _safe_request_url(base_url, "/chat/completions"),
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
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("LLM 调用失败 (重试耗尽): %s", e)
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
    # 基础 URL 安全校验：只允许 http/https，拒绝 file:///gopher:// 等
    err = _validate_base_url(base_url)
    if err:
        logger.warning("LLM base_url 校验失败：%s", err)
        return None
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
        resp = _request_with_retry(
            "POST", _safe_request_url(base_url, "/chat/completions"),
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
        logger.error("LLM 流式调用失败 (重试耗尽): %s", e)


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
    # 基础 URL 安全校验：只允许 http/https，拒绝 file:///gopher:// 等
    err = _validate_base_url(base_url)
    if err:
        logger.warning("LLM base_url 校验失败：%s", err)
        return None
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
            resp = _request_with_retry(
                "POST", _safe_request_url(base_url, "/chat/completions"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            data = resp.json()
        except Exception as e:
            logger.error("LLM 调用失败 (重试耗尽): %s", e)
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
    # 基础 URL 安全校验：只允许 http/https，拒绝 file:///gopher:// 等
    err = _validate_base_url(base_url)
    if err:
        logger.warning("LLM base_url 校验失败：%s", err)
        return None
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

        request_url = _safe_request_url(base_url, "/chat/completions")
        logger.info("LLM 请求 → %s | model=%s | provider=%s", request_url, model, cfg.get('provider', 'openai'))

        try:
            resp = _request_with_retry(
                "POST", request_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
                stream=True,
            )
        except Exception as e:
            logger.error("LLM 流式调用失败 (重试耗尽): %s", e)
            yield {"type": "error", "message": f"LLM 调用失败: {e}"}
            return

        round_content = ""
        tool_calls_buffer = {}  # index -> {id, name, arguments}
        tool_calls_invoked = False
        response_model = None   # 记录响应中实际使用的模型名

        try:
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

                # 记录/显示响应中实际使用的模型名称
                if response_model is None and 'model' in data:
                    response_model = data['model']
                    logger.info("LLM 响应来自 model=%s", response_model)

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
                done_event = {"type": "done", "content": full_content, "tool_calls": total_tool_calls}
                if response_model:
                    done_event["model"] = response_model
                yield done_event
                return

        except requests.exceptions.ChunkedEncodingError as e:
            logger.error("LLM 流式传输中断 (ChunkedEncodingError): %s", e)
            if full_content:
                done_event = {"type": "done", "content": full_content, "tool_calls": total_tool_calls, "interrupted": True}
                if response_model:
                    done_event["model"] = response_model
                yield done_event
            else:
                yield {"type": "error", "message": "连接中断，请重试"}
            return
        except requests.exceptions.ConnectionError as e:
            logger.error("LLM 连接中断: %s", e)
            if full_content:
                done_event = {"type": "done", "content": full_content, "tool_calls": total_tool_calls, "interrupted": True}
                if response_model:
                    done_event["model"] = response_model
                yield done_event
            else:
                yield {"type": "error", "message": "连接中断，请重试"}
            return
        except Exception as e:
            logger.error("LLM 流式解析异常: %s", e)
            if full_content:
                done_event = {"type": "done", "content": full_content, "tool_calls": total_tool_calls, "interrupted": True}
                if response_model:
                    done_event["model"] = response_model
                yield done_event
            else:
                yield {"type": "error", "message": f"流式响应异常: {e}"}
            return

        # 如果没有工具调用、没有 stop 信号（异常 EOF），结束
        if not tool_calls_invoked:
            break

    done_event = {"type": "done", "content": full_content, "tool_calls": total_tool_calls}
    if response_model:
        done_event["model"] = response_model
    yield done_event


# ==================== Anthropic Messages API（CC Switch 模式）====================

_ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-6"


def call_anthropic_messages(
    system_prompt: str,
    user_query: str,
    messages_history: List[Dict[str, str]] = None,
    max_tool_rounds: int = 5,
    tools: List[Dict] = None,
    tool_executor: Callable = None,
    temperature: float = None,
    max_tokens: int = None,
    user_id: str = None,
    interrupt_event=None,
) -> Dict[str, Any]:
    """通过 CC Switch 代理 + Anthropic SDK 发送请求（非流式）"""
    result = {"content": "", "tool_calls_made": [], "tool_results": [], "error": None, "interrupted": False}

    try:
        client = _get_anthropic_client(user_id)
        if client is None:
            result["error"] = "CC Switch 代理地址未配置"
            return result
    except Exception as e:
        result["error"] = str(e)
        return result

    model = _get_anthropic_model(user_id)
    max_tok = max_tokens or 4096
    temp = temperature if temperature is not None else 0.7
    anthropic_tools = _convert_to_anthropic_tools(tools) if tools else None

    messages = []
    if messages_history:
        for m in messages_history:
            role = m.get("role", "")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_query})

    for round_idx in range(max_tool_rounds + 1):
        if interrupt_event and interrupt_event.is_set():
            result["interrupted"] = True
            return result

        kwargs = dict(model=model, max_tokens=max_tok, messages=messages, temperature=temp)
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        try:
            resp = client.messages.create(**kwargs)
        except Exception as e:
            result["error"] = f"Anthropic Messages 调用失败: {e}"
            return result

        text_parts, tool_uses = [], []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        if not tool_uses:
            result["content"] = "\n".join(text_parts)
            return result

        assistant_blocks = [{"type": "text", "text": "\n".join(text_parts)}] if text_parts else []
        for tu in tool_uses:
            assistant_blocks.append({"type": "tool_use", "id": tu.id, "name": tu.name, "input": tu.input})
        messages.append({"role": "assistant", "content": assistant_blocks})

        for tu in tool_uses:
            if interrupt_event and interrupt_event.is_set():
                result["interrupted"] = True
                return result

            logger.info("Anthropic tool call: %s(%s)", tu.name, json.dumps(tu.input, ensure_ascii=False)[:200])
            result["tool_calls_made"].append({"id": tu.id, "name": tu.name, "arguments": tu.input})
            tr = tool_executor(tu.name, dict(tu.input)) if tool_executor else ""
            result["tool_results"].append({"tool_name": tu.name, "result": tr})
            messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tu.id, "content": tr}]})

    result["content"] = messages[-1].get("content", "") if messages else ""
    return result


def call_anthropic_messages_stream(
    system_prompt: str,
    user_query: str,
    messages_history: List[Dict[str, str]] = None,
    max_tool_rounds: int = 5,
    tools: List[Dict] = None,
    tool_executor: Callable = None,
    temperature: float = None,
    max_tokens: int = None,
    user_id: str = None,
    interrupt_event=None,
    sources: List[Dict] = None,
):
    """通过 CC Switch 代理 + Anthropic SDK 发送请求（流式）"""
    try:
        client = _get_anthropic_client(user_id)
        if client is None:
            yield {"type": "error", "message": "CC Switch 代理地址未配置"}
            return
    except Exception as e:
        yield {"type": "error", "message": str(e)}
        return

    model = _get_anthropic_model(user_id)
    max_tok = max_tokens or 4096
    temp = temperature if temperature is not None else 0.7
    anthropic_tools = _convert_to_anthropic_tools(tools) if tools else None

    if sources:
        yield {"type": "source", "sources": sources}

    messages = []
    if messages_history:
        for m in messages_history:
            role = m.get("role", "")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_query})

    full_content = ""
    total_tool_calls = 0

    for round_idx in range(max_tool_rounds + 1):
        if interrupt_event and interrupt_event.is_set():
            yield {"type": "interrupted"}
            return

        kwargs = dict(model=model, max_tokens=max_tok, messages=messages, temperature=temp, stream=True)
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        try:
            stream = client.messages.create(**kwargs)
        except Exception as e:
            yield {"type": "error", "message": f"Anthropic Messages 调用失败: {e}"}
            return

        round_text = ""
        pending_tool_uses = {}
        current_tool_index = -1

        for event in stream:
            if interrupt_event and interrupt_event.is_set():
                yield {"type": "interrupted"}
                return

            if event.type == "content_block_start":
                if event.content_block and event.content_block.type == "tool_use":
                    current_tool_index = event.index
                    pending_tool_uses[current_tool_index] = {
                        "id": event.content_block.id,
                        "name": event.content_block.name,
                        "_partial": "",
                    }

            elif event.type == "content_block_delta":
                if event.delta and event.delta.type == "text_delta":
                    text = event.delta.text or ""
                    if text:
                        round_text += text
                        full_content += text
                        yield {"type": "token", "content": text}
                elif event.delta and event.delta.type == "input_json_delta":
                    idx = event.index
                    if idx in pending_tool_uses:
                        pending_tool_uses[idx]["_partial"] += (event.delta.partial_json or "")

            elif event.type == "message_delta":
                if event.delta and event.delta.stop_reason == "tool_use":
                    pass  # 标记等待

            elif event.type == "error":
                yield {"type": "error", "message": str(event.error or "未知错误")}
                return

        if pending_tool_uses:
            # 解析 tool_use input
            for idx in list(pending_tool_uses.keys()):
                tu = pending_tool_uses[idx]
                try:
                    tu["input"] = json.loads(tu["_partial"]) if tu["_partial"] else {}
                except json.JSONDecodeError:
                    tu["input"] = {}
                del tu["_partial"]

            # 构建 assistant 消息
            assistant_blocks = []
            if round_text:
                assistant_blocks.append({"type": "text", "text": round_text})
            for idx in sorted(pending_tool_uses.keys()):
                tu = pending_tool_uses[idx]
                assistant_blocks.append({"type": "tool_use", "id": tu["id"], "name": tu["name"], "input": tu["input"]})
            messages.append({"role": "assistant", "content": assistant_blocks})

            # 执行工具
            for idx in sorted(pending_tool_uses.keys()):
                if interrupt_event and interrupt_event.is_set():
                    yield {"type": "interrupted"}
                    return

                tu = pending_tool_uses[idx]
                logger.info("Anthropic tool call: %s(%s)", tu["name"], json.dumps(tu["input"], ensure_ascii=False)[:200])
                total_tool_calls += 1
                yield {"type": "tool_call", "name": tu["name"], "arguments": tu["input"]}

                tr = tool_executor(tu["name"], tu["input"]) if tool_executor else "{}"
                yield {"type": "tool_result", "tool_name": tu["name"], "result": tr}

                if sources is not None:
                    try:
                        rd = json.loads(tr)
                        if rd.get("success"):
                            existing = {s.get("path") for s in sources}
                            if tu["name"] == "wiki_search":
                                for r_item in rd.get("results", []):
                                    if r_item["path"] not in existing:
                                        sources.append({"path": r_item["path"], "title": r_item["title"]})
                                yield {"type": "source", "sources": sources}
                            elif tu["name"] == "web_search":
                                for r_item in rd.get("results", []):
                                    url = r_item.get("url", "")
                                    if url and url not in existing:
                                        sources.append({"path": url, "title": r_item.get("title", url), "_type": "web"})
                                yield {"type": "source", "sources": sources}
                    except (json.JSONDecodeError, KeyError):
                        pass

                messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tu["id"], "content": tr}]})

            continue

        yield {"type": "done", "content": full_content, "tool_calls": total_tool_calls}
        return

    yield {"type": "done", "content": full_content, "tool_calls": total_tool_calls}


def _get_anthropic_client(user_id: str = None):
    """获取 Anthropic SDK 客户端（指向 CC Switch 代理）

    get_effective_llm_config 返回的 base_url 已带 /v1（如 http://127.0.0.1:15721/v1），
    而 SDK 内部会自动拼接 /v1/messages，所以传给 SDK 的 base_url 要去掉 /v1。
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        return None

    cfg = get_effective_llm_config(user_id)
    base_url = cfg.get('base_url', '').rstrip('/')
    if not base_url:
        return None

    # SDK 会自动追加 /v1/messages，所以去掉 base_url 中的 /v1
    if base_url.endswith('/v1'):
        base_url = base_url[:-3]

    return Anthropic(api_key="cc-switch", base_url=base_url)


def _get_anthropic_model(user_id: str = None) -> str:
    cfg = get_effective_llm_config(user_id)
    model = cfg.get('model')
    # 如果用户没有配置 model，或 get_effective_llm_config 设置的是占位 'default'，
    # 则使用 Anthropic SDK 的默认模型
    if not model or model == 'default':
        return _ANTHROPIC_DEFAULT_MODEL
    return model


def _convert_to_anthropic_tools(openai_tools):
    """将 OpenAI Function Calling 格式的工具列表转换为 Anthropic Tool 格式"""
    if not openai_tools:
        return None
    result = []
    for t in openai_tools:
        fn = t.get("function", {})
        result.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return result if result else None
