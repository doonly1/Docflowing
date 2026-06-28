import logging

from kb.database import get_db

logger = logging.getLogger(__name__)


def _escape_fts_term(term: str) -> str:
    """转义 FTS5 查询中的特殊字符，用双引号包裹为短语查询。

    参考 SQLite FTS5 文档：双引号内的内容被视为短语，内部双引号需加倍转义。
    """
    escaped = term.replace('"', '""')
    return f'"{escaped}"'


def search_wiki(usr_id, query):
    if not query or not query.strip():
        return []

    conn = get_db(usr_id)
    search_terms = query.strip().split()
    # 对每个搜索词转义 FTS5 特殊字符，防止语法错误和意外行为
    # 词间 AND、词内字段 OR：每个关键词必须在 title 或 content 中出现至少一次
    # 如搜「项目管理 文档」→ (title:X OR content:X) AND (title:Y OR content:Y)
    fts_query = ' AND '.join(
        f'(title:{_escape_fts_term(t)} OR content:{_escape_fts_term(t)})'
        for t in search_terms
    )

    try:
        rows = conn.execute(
            "SELECT path, title, "
            "snippet(wiki_fts, 1, '<mark>', '</mark>', '...', 30) as title_snippet, "
            "snippet(wiki_fts, 2, '<mark>', '</mark>', '...', 60) as content_snippet "
            "FROM wiki_fts WHERE usr_id = ? AND wiki_fts MATCH ?",
            (usr_id, fts_query)
        ).fetchall()
    except Exception as e:
        logger.warning("FTS5 search failed (query=%r, terms=%r): %s", query, search_terms, e)
        return []

    return [
        {'path': r['path'], 'title': r['title'],
         'title_snippet': r['title_snippet'], 'content_snippet': r['content_snippet']}
        for r in rows
    ]
