import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


MEMORY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "memory",
        "description": (
            "Save durable information to persistent memory that survives across sessions. "
            "Memory is injected into future turns, so keep it compact and focused on facts "
            "that will still matter later.\n\n"
            "WHEN TO SAVE (do this proactively, don't wait to be asked):\n"
            "- User corrects you or says 'remember this' / 'don't do that again'\n"
            "- User shares a preference, habit, or personal detail (name, role, timezone, coding style)\n"
            "- You discover something about the environment (OS, installed tools, project structure)\n"
            "- You learn a convention, API quirk, or workflow specific to this user's setup\n"
            "- You identify a stable fact that will be useful again in future sessions\n\n"
            "PRIORITY: User preferences and corrections > environment facts > procedural knowledge. "
            "The most valuable memory prevents the user from having to repeat themselves.\n\n"
            "Do NOT save task progress, session outcomes, completed-work logs, or temporary TODO "
            "state to memory; use session_search to recall those from past transcripts.\n"
            "If you've discovered a new way to do something, solved a problem that could be "
            "necessary later, save it as a skill with the skill_manage tool.\n\n"
            "TWO TARGETS:\n"
            "- 'user': who the user is -- name, role, preferences, communication style, pet peeves\n"
            "- 'memory': your notes -- environment facts, project conventions, tool quirks, lessons learned\n\n"
            "ACTIONS: add (new entry), replace (update existing -- old_text identifies it), "
            "remove (delete -- old_text identifies it).\n\n"
            "SKIP: trivial/obvious info, things easily re-discovered, raw data dumps, and temporary task state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "replace", "remove"],
                    "description": "The action to perform."
                },
                "target": {
                    "type": "string",
                    "enum": ["memory", "user"],
                    "description": "Which memory store: 'memory' for personal notes, 'user' for user profile."
                },
                "content": {
                    "type": "string",
                    "description": "The entry content. Required for 'add' and 'replace'."
                },
                "old_text": {
                    "type": "string",
                    "description": "Short unique substring identifying the entry to replace or remove."
                }
            },
            "required": ["action", "target"]
        }
    }
}


SKILL_MANAGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "skill_manage",
        "description": (
            "Manage the skill library -- create, view, patch, or list skills. "
            "Skills are reusable knowledge units that persist across sessions.\n\n"
            "WHEN TO CREATE A SKILL:\n"
            "- You solved a problem in a way that could be useful again\n"
            "- You developed a reusable procedure or workflow\n"
            "- You discovered a pattern worth remembering for future sessions\n\n"
            "ACTIONS:\n"
            "- create: Make a new skill with name, content, and optional category\n"
            "- patch: Update part of an existing skill (provide old_string and new_string)\n"
            "- view: Read a skill's content\n"
            "- list: List all skills or filter by category/state\n\n"
            "Do NOT create skills for one-time tasks, temporary state, or information that belongs in memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "patch", "view", "list"],
                    "description": "The action to perform."
                },
                "name": {
                    "type": "string",
                    "description": "Skill name. Required for create, patch, view."
                },
                "content": {
                    "type": "string",
                    "description": "Skill content (markdown). Required for create."
                },
                "category": {
                    "type": "string",
                    "description": "Optional category for the skill."
                },
                "old_string": {
                    "type": "string",
                    "description": "Text to find in the skill. Required for patch."
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement text. Required for patch."
                },
                "state": {
                    "type": "string",
                    "enum": ["active", "stale", "archived"],
                    "description": "Filter by state for list action."
                }
            },
            "required": ["action"]
        }
    }
}


SESSION_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "session_search",
        "description": (
            "Search past conversation sessions for relevant information. "
            "Use this when you need to recall what happened in earlier conversations, "
            "find previous solutions to similar problems, or look up past decisions.\n\n"
            "Returns matching messages from past sessions with timestamps."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query -- keywords or phrases to find in past sessions."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Default: 10."
                }
            },
            "required": ["query"]
        }
    }
}


ALL_TOOL_SCHEMAS = [MEMORY_SCHEMA, SKILL_MANAGE_SCHEMA, SESSION_SEARCH_SCHEMA]


def execute_tool_call(tool_name: str, args: Dict[str, Any], user_id: str) -> str:
    try:
        if tool_name == "memory":
            return _execute_memory(args, user_id)
        elif tool_name == "skill_manage":
            return _execute_skill_manage(args, user_id)
        elif tool_name == "session_search":
            return _execute_session_search(args, user_id)
        else:
            return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
    except Exception as e:
        logger.error("Tool execution failed: %s %s -> %s", tool_name, args, e)
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _validate_content_safety(content: str) -> Optional[str]:
    from .file_safety import validate_content_safety
    return validate_content_safety(content)


def _execute_memory(args: Dict[str, Any], user_id: str) -> str:
    from .memory import get_memory_store

    store = get_memory_store(user_id)
    action = args.get("action", "")
    target = args.get("target", "memory")

    if action == "add":
        content = args.get("content", "")
        if not content:
            return json.dumps({"success": False, "error": "content is required for add"}, ensure_ascii=False)
        result = store.add(target, content)
    elif action == "replace":
        old_text = args.get("old_text", "")
        content = args.get("content", "")
        if not old_text or not content:
            return json.dumps({"success": False, "error": "old_text and content are required for replace"}, ensure_ascii=False)
        result = store.replace(target, old_text, content)
    elif action == "remove":
        old_text = args.get("old_text", "")
        if not old_text:
            return json.dumps({"success": False, "error": "old_text is required for remove"}, ensure_ascii=False)
        result = store.remove(target, old_text)
    else:
        result = {"success": False, "error": f"Unknown action: {action}"}

    return json.dumps(result, ensure_ascii=False)


def _execute_skill_manage(args: Dict[str, Any], user_id: str) -> str:
    from .skills.manager import create_skill, patch_skill, get_skill, list_skills
    from .file_safety import validate_skill_path

    action = args.get("action", "")

    if action == "create":
        name = args.get("name", "")
        content = args.get("content", "")
        category = args.get("category")
        if not name or not content:
            return json.dumps({"success": False, "error": "name and content are required"}, ensure_ascii=False)
        path_error = validate_skill_path(user_id, name, None)
        if path_error:
            return json.dumps({"success": False, "error": path_error}, ensure_ascii=False)
        content_error = _validate_content_safety(content)
        if content_error:
            return json.dumps({"success": False, "error": content_error}, ensure_ascii=False)
        result = create_skill(user_id, name, content, category=category, created_by="agent")
    elif action == "patch":
        name = args.get("name", "")
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")
        if not name or not old_string or not new_string:
            return json.dumps({"success": False, "error": "name, old_string and new_string are required"}, ensure_ascii=False)
        content_error = _validate_content_safety(new_string)
        if content_error:
            return json.dumps({"success": False, "error": content_error}, ensure_ascii=False)
        result = patch_skill(user_id, name, old_string, new_string)
    elif action == "view":
        name = args.get("name", "")
        if not name:
            return json.dumps({"success": False, "error": "name is required"}, ensure_ascii=False)
        result = get_skill(user_id, name)
    elif action == "list":
        category = args.get("category")
        state = args.get("state")
        skills = list_skills(user_id, category=category, state=state)
        result = {"success": True, "skills": skills, "count": len(skills)}
    else:
        result = {"success": False, "error": f"Unknown action: {action}"}

    return json.dumps(result, ensure_ascii=False)


def _execute_session_search(args: Dict[str, Any], user_id: str) -> str:
    from .session_db import get_session_db

    query = args.get("query", "")
    limit = args.get("limit", 10)
    if not query:
        return json.dumps({"success": False, "error": "query is required"}, ensure_ascii=False)

    db = get_session_db(user_id)
    results = db.search_messages(query, user_id=user_id, limit=limit)
    return json.dumps({"success": True, "results": results, "count": len(results)}, ensure_ascii=False)
