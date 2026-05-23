import json
import logging
import re
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


WEB_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information. "
            "Use this when you need up-to-date information that may not be in the knowledge base, "
            "such as latest news, recent events, current API documentation, or real-time data.\n\n"
            "Returns a list of search results with titles, snippets, and URLs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Default: 5, max: 10."
                }
            },
            "required": ["query"]
        }
    }
}


WIKI_READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wiki_read",
        "description": (
            "Read the full content of a knowledge base (wiki) document by its path. "
            "Use this when you've retrieved matched excerpts via the reference information "
            "but need to read an entire document for complete context.\n\n"
            "The path corresponds to the 'path' field in the sources list provided alongside "
            "search results. Only paths appearing in the sources are valid."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The relative path of the wiki document to read, as shown in the sources list."
                }
            },
            "required": ["path"]
        }
    }
}


WIKI_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wiki_search",
        "description": (
            "PRIMARY search tool: Search the user's local knowledge base (wiki) for documents matching a query. "
            "Always use this tool FIRST before falling back to web_search, because the wiki contains "
            "private/custom knowledge specific to the user and is faster than web search.\n\n"
            "Returns a list of matching documents with their paths, titles, and content snippets. "
            "Use wiki_read afterwards to read a specific document in full."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query — keywords or phrases to find in the knowledge base."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Default: 5, max: 10."
                }
            },
            "required": ["query"]
        }
    }
}


ALL_TOOL_SCHEMAS = [MEMORY_SCHEMA, SKILL_MANAGE_SCHEMA, SESSION_SEARCH_SCHEMA, WEB_SEARCH_SCHEMA, WIKI_READ_SCHEMA, WIKI_SEARCH_SCHEMA]


def execute_tool_call(tool_name: str, args: Dict[str, Any], user_id: str) -> str:
    try:
        if tool_name == "memory":
            return _execute_memory(args, user_id)
        elif tool_name == "skill_manage":
            return _execute_skill_manage(args, user_id)
        elif tool_name == "session_search":
            return _execute_session_search(args, user_id)
        elif tool_name == "web_search":
            return _execute_web_search(args)
        elif tool_name == "wiki_read":
            return _execute_wiki_read(args, user_id)
        elif tool_name == "wiki_search":
            return _execute_wiki_search(args, user_id)
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


def _execute_web_search(args: Dict[str, Any]) -> str:
    query = args.get("query", "")
    max_results = min(args.get("max_results", 5), 10)
    if not query:
        return json.dumps({"success": False, "error": "query is required"}, ensure_ascii=False)

    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            timeout=15,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for item in soup.select(".result")[:max_results]:
            title_el = item.select_one(".result__title a")
            snippet_el = item.select_one(".result__snippet")
            if not title_el:
                continue
            results.append({
                "title": title_el.get_text(strip=True),
                "url": title_el.get("href", ""),
                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
            })

        return json.dumps({
            "success": True,
            "results": results,
            "count": len(results),
            "query": query,
        }, ensure_ascii=False)

    except ImportError:
        return json.dumps({
            "success": False,
            "error": "Web search requires beautifulsoup4. Install with: pip install beautifulsoup4",
        }, ensure_ascii=False)
    except requests.exceptions.Timeout:
        return json.dumps({"success": False, "error": "Web search timed out"}, ensure_ascii=False)
    except Exception as e:
        logger.error("Web search failed: %s", e)
        return json.dumps({"success": False, "error": f"Web search failed: {str(e)}"}, ensure_ascii=False)


def _extract_from_keyword(text: str, keywords: list) -> str:
    """从关键词所在句子的开头截取文本，使上下文更紧凑且有针对性。"""
    pos = -1
    text_lower = text.lower()
    for kw in keywords:
        p = text_lower.find(kw.lower())
        if p != -1:
            pos = p
            break
    if pos == -1:
        return text
    sentence_start = 0
    for sep in ('。', '！', '？', '!', '?', '\n'):
        idx = text.rfind(sep, 0, pos)
        if idx != -1:
            sentence_start = max(sentence_start, idx + len(sep))
    return text[sentence_start:].strip()


def _extract_relevant_snippets(content: str, keywords: list, max_chars: int = 3000) -> str:
    """提取包含关键词的段落，从关键词所在句子开头截取，限制总长度。

    Args:
        content: 文档全文
        keywords: 关键词列表（小写）
        max_chars: 最大返回字符数

    Returns:
        经截取和修剪后的文本片段
    """
    if not content.strip():
        return ""

    # 按空行分割段落，提取包含关键词的段落
    paragraphs = re.split(r'\n\s*\n', content)
    matched_bodies = []
    for para in paragraphs:
        if any(kw in para.lower() for kw in keywords):
            matched_bodies.append(para.strip())

    # 兜底：无匹配段落则展示开头
    if not matched_bodies:
        matched_bodies = [content.strip()[:300]]

    # 从关键词所在句子开头截取
    trimmed_bodies = []
    for para in matched_bodies:
        trimmed_bodies.append(_extract_from_keyword(para, keywords))

    # 限制总长
    snippet = '\n'.join(trimmed_bodies)
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "..."

    return snippet


def _execute_wiki_read(args: Dict[str, Any], user_id: str) -> str:
    path = args.get("path", "")
    if not path:
        return json.dumps({"success": False, "error": "path is required"}, ensure_ascii=False)

    from .database import get_db
    conn = get_db(user_id)
    row = conn.execute(
        "SELECT content FROM wiki_fts WHERE usr_id = ? AND path = ?",
        (user_id, path)
    ).fetchone()
    if not row:
        return json.dumps({"success": False, "error": f"Document not found: {path}"}, ensure_ascii=False)

    content = row['content']
    if len(content) > 50000:
        content = content[:50000] + "\n\n... (truncated at 50000 characters)"
    return json.dumps({"success": True, "path": path, "content": content}, ensure_ascii=False)


def _execute_wiki_search(args: Dict[str, Any], user_id: str) -> str:
    from .search import search_wiki
    from .database import get_db

    query = args.get("query", "")
    limit = min(args.get("limit", 5), 10)
    if not query:
        return json.dumps({"success": False, "error": "query is required"}, ensure_ascii=False)

    try:
        results = search_wiki(user_id, query)
        if limit:
            results = results[:limit]

        conn = get_db(user_id)
        enriched = []
        keywords = query.lower().split()
        max_snippet_chars = 3000

        for r in results:
            row = conn.execute(
                "SELECT content FROM wiki_fts WHERE usr_id = ? AND path = ?",
                (user_id, r['path'])
            ).fetchone()
            content = row['content'] if row else ""
            if not content.strip():
                continue

            snippet = _extract_relevant_snippets(content, keywords, max_snippet_chars)
            enriched.append({
                "path": r['path'],
                "title": r['title'],
                "content_snippet": snippet,
            })

        return json.dumps({
            "success": True,
            "results": enriched,
            "count": len(enriched),
            "query": query,
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("Wiki search failed: %s", e)
        return json.dumps({"success": False, "error": f"Wiki search failed: {str(e)}"}, ensure_ascii=False)
