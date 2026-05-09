import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ContextCompressor:
    def __init__(
        self,
        token_threshold: int = 8000,
        protect_first_n: int = 3,
        protect_last_n: int = 6,
        max_summary_tokens: int = 1000,
    ):
        self.token_threshold = token_threshold
        self.protect_first_n = protect_first_n
        self.protect_last_n = protect_last_n
        self.max_summary_tokens = max_summary_tokens

    def estimate_tokens(self, messages: List[Dict]) -> int:
        total = 0
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                total += len(content) // 4
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        total += len(part.get("text", "")) // 4
        return total

    def should_compress(self, messages: List[Dict]) -> bool:
        return self.estimate_tokens(messages) > self.token_threshold

    def compress(
        self,
        messages: List[Dict],
        user_id: str = None,
        previous_summary: str = None,
    ) -> List[Dict]:
        if not messages or len(messages) <= self.protect_first_n + self.protect_last_n:
            return self._filter_incompatible_messages(messages)

        head = messages[:self.protect_first_n]
        tail = messages[-self.protect_last_n:]
        middle = messages[self.protect_first_n:-self.protect_last_n]

        if not middle:
            return self._filter_incompatible_messages(messages)

        trimmed_middle = self._trim_tool_outputs(middle)

        summary = self._generate_summary(trimmed_middle, user_id, previous_summary)
        if summary:
            summary_msg = {
                "role": "system",
                "content": f"[上下文摘要 — 早期对话已压缩]\n{summary}",
            }
            result = head + [summary_msg] + tail
            return self._filter_incompatible_messages(result)

        return self._filter_incompatible_messages(head + trimmed_middle + tail)

    def _filter_incompatible_messages(self, messages: List[Dict]) -> List[Dict]:
        filtered = []
        for m in messages:
            role = m.get("role", "")
            if role == "tool":
                continue
            if role == "assistant" and m.get("tool_calls"):
                filtered.append({"role": "assistant", "content": m.get("content", "") or ""})
                continue
            filtered.append(m)
        return filtered

    def _trim_tool_outputs(self, messages: List[Dict]) -> List[Dict]:
        trimmed = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")

            if role == "tool" and isinstance(content, str) and len(content) > 500:
                summary = self._summarize_tool_output(content)
                trimmed.append({**m, "content": summary})
            elif role == "assistant":
                tool_calls = m.get("tool_calls")
                if tool_calls and isinstance(content, str) and len(content) > 500:
                    trimmed.append({**m, "content": content[:300] + "..."})
                else:
                    trimmed.append(m)
            else:
                trimmed.append(m)

        return trimmed

    def _summarize_tool_output(self, content: str) -> str:
        lines = content.strip().split("\n")
        line_count = len(lines)
        first_line = lines[0][:100] if lines else ""

        json_match = re.match(r'^\s*\{', content)
        if json_match:
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    success = data.get("success")
                    count = data.get("count")
                    name = data.get("name", data.get("skill", ""))
                    if success is not None:
                        parts = [f"[tool] {name}" if name else "[tool]"]
                        if count is not None:
                            parts.append(f"{count} items")
                        if success:
                            parts.append("OK")
                        else:
                            err = data.get("error", "failed")
                            parts.append(f"ERROR: {err[:60]}")
                        return " ".join(parts)
            except json.JSONDecodeError:
                pass

        if line_count <= 3:
            return content[:200]

        return f"[tool] {first_line}... ({line_count} lines total)"

    def _generate_summary(
        self,
        messages: List[Dict],
        user_id: str = None,
        previous_summary: str = None,
    ) -> Optional[str]:
        from .llm import call_llm, is_llm_available

        if not is_llm_available():
            return None

        conversation_text = self._format_for_summary(messages)
        if not conversation_text.strip():
            return None

        if previous_summary:
            prompt = f"""根据最近的对话内容，更新以下对话摘要。

## 之前的摘要
{previous_summary}

## 最近的对话
{conversation_text}

## 要求
生成一个更新后的摘要，要求：
1. 保留之前摘要中的所有关键事实、决策和待办事项
2. 整合最近对话中的新信息
3. 移除已被更正或过时的信息
4. 保持摘要简洁且结构化

格式：
- **当前任务**：正在处理什么
- **目标**：用户想要达成什么
- **进展**：已完成什么
- **决策**：做出的关键决策
- **关键事实**：发现的重要事实或上下文"""
        else:
            prompt = f"""总结以下对话片段，聚焦于后续对话中需要保留的关键信息。

## 对话内容
{conversation_text}

## 要求
生成简洁、结构化的摘要，聚焦于：
- 用户想要达成什么
- 目前完成了什么
- 关键决策及其理由
- 发现的重要事实或上下文
- 未解决的问题或下一步

格式：
- **当前任务**：正在处理什么
- **目标**：用户想要达成什么
- **进展**：已完成什么
- **决策**：做出的关键决策
- **关键事实**：发现的重要事实或上下文"""

        try:
            summary = call_llm(
                system_prompt="你是一个对话摘要生成器。请保持简洁、客观，只保留关键信息。",
                user_query=prompt,
                temperature=0.1,
                max_tokens=self.max_summary_tokens,
            )
            return summary.strip() if summary else None
        except Exception as e:
            logger.debug("Summary generation failed: %s", e)
            return None

    def _format_for_summary(self, messages: List[Dict]) -> str:
        parts = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if not content:
                continue
            if isinstance(content, str):
                snippet = content[:500]
                if len(content) > 500:
                    snippet += "..."
                parts.append(f"[{role}]: {snippet}")
        return "\n\n".join(parts)
