import json
import logging
import threading
from typing import Any, Dict

logger = logging.getLogger(__name__)


_EXTRACT_PROMPT = """Analyze the following conversation exchange and determine if any information should be saved to persistent memory or as a reusable skill.

## Rules for SAVING to memory:
- User explicitly asks to remember something ("remember this", "don't forget", "记住这个", "记下来")
- User corrects the assistant or expresses a preference ("I prefer...", "我喜欢...", "不要...", "以后请...")
- User shares personal details (name, role, timezone, coding style, habits)
- Environment facts discovered (OS, tools, project structure, conventions)
- API quirks, workflow patterns specific to this user

## Rules for SAVING as a skill:
- A reusable problem-solving procedure was developed
- A pattern was discovered that could help in future sessions
- A workflow was established that should be repeated

## Rules for NOT saving:
- Temporary task state or progress
- Completed work logs
- Information easily re-discovered
- Trivial or obvious facts
- Raw data dumps

## Output format:
Return a JSON object with this exact structure:
{
  "should_save": true/false,
  "memory_writes": [
    {"action": "add", "target": "memory" or "user", "content": "..."}
  ],
  "skill_creates": [
    {"name": "skill-name", "content": "...", "category": "..."}
  ]
}

If nothing should be saved, return: {"should_save": false, "memory_writes": [], "skill_creates": []}

Return ONLY the JSON object, no other text."""


def auto_extract_from_conversation(
    user_id: str,
    user_message: str,
    assistant_message: str,
) -> Dict[str, Any]:
    from .llm import call_llm, is_llm_available

    if not is_llm_available(user_id):
        return {"should_save": False, "memory_writes": [], "skill_creates": []}

    user_snippet = (user_message or "")[:1000]
    assistant_snippet = (assistant_message or "")[:1000]

    if not user_snippet.strip():
        return {"should_save": False, "memory_writes": [], "skill_creates": []}

    try:
        raw = call_llm(
            system_prompt=_EXTRACT_PROMPT,
            user_query=f"User: {user_snippet}\n\nAssistant: {assistant_snippet}",
            temperature=0.1,
            max_tokens=500,
            user_id=user_id,
        )
        if not raw:
            return {"should_save": False, "memory_writes": [], "skill_creates": []}

        raw = raw.strip()
        if raw.startswith("```"):
            first_newline = raw.find("\n")
            last_backtick = raw.rfind("```")
            if first_newline > 0 and last_backtick > first_newline:
                raw = raw[first_newline + 1:last_backtick].strip()

        result = json.loads(raw)

        if not isinstance(result, dict):
            return {"should_save": False, "memory_writes": [], "skill_creates": []}

        if not result.get("should_save", False):
            return {"should_save": False, "memory_writes": [], "skill_creates": []}

        return result

    except json.JSONDecodeError:
        logger.debug("Auto-extract response was not valid JSON")
        return {"should_save": False, "memory_writes": [], "skill_creates": []}
    except Exception as e:
        logger.debug("Auto-extract failed: %s", e)
        return {"should_save": False, "memory_writes": [], "skill_creates": []}


def apply_extractions(user_id: str, extractions: Dict[str, Any]) -> None:
    if not extractions.get("should_save"):
        return

    from .memory import get_memory_store
    from .skills.manager import create_skill

    store = get_memory_store(user_id)

    for mw in extractions.get("memory_writes", []):
        action = mw.get("action", "add")
        target = mw.get("target", "memory")
        content = mw.get("content", "")
        if not content:
            continue
        try:
            if action == "add":
                store.add(target, content)
                logger.info("Auto-extract: added to %s: %s", target, content[:80])
        except Exception as e:
            logger.debug("Auto-extract memory write failed: %s", e)

    for sc in extractions.get("skill_creates", []):
        name = sc.get("name", "")
        content = sc.get("content", "")
        category = sc.get("category")
        if not name or not content:
            continue
        try:
            result = create_skill(user_id, name, content, category=category, created_by="agent")
            if result.get("success"):
                logger.info("Auto-extract: created skill '%s'", name)
        except Exception as e:
            logger.debug("Auto-extract skill create failed: %s", e)


def auto_extract_async(user_id: str, user_message: str, assistant_message: str) -> None:
    def _run():
        try:
            extractions = auto_extract_from_conversation(user_id, user_message, assistant_message)
            apply_extractions(user_id, extractions)
        except Exception as e:
            logger.debug("Auto-extract async failed: %s", e)

    t = threading.Thread(target=_run, daemon=True, name="auto-extract")
    t.start()
