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
    fts_query = ' OR '.join(f'title:{_escape_fts_term(t)} OR content:{_escape_fts_term(t)}' for t in search_terms)

    try:
        rows = conn.execute(
            "SELECT path, title, "
            "snippet(wiki_fts, 1, '<mark>', '</mark>', '...', 30) as title_snippet, "
            "snippet(wiki_fts, 2, '<mark>', '</mark>', '...', 60) as content_snippet "
            "FROM wiki_fts WHERE usr_id = ? AND wiki_fts MATCH ?",
            (usr_id, fts_query)
        ).fetchall()
    except Exception as e:
        logger.warning("FTS5 search failed, fallback to LIKE (query=%r, terms=%r): %s", query, search_terms, e)
        rows = []

    if not rows:
        try:
            like_parts = []
            like_params = []
            for t in search_terms:
                like_parts.append("(title LIKE ? OR content LIKE ?)")
                like_params.extend([f'%{t}%', f'%{t}%'])
            like_params.insert(0, usr_id)

            # 先用 AND：所有关键词都必须匹配
            sql = (
                "SELECT path, title, '' as title_snippet, '' as content_snippet "
                "FROM wiki_fts WHERE usr_id = ? AND ({}) LIMIT 99"
            ).format(' AND '.join(like_parts))
            rows = conn.execute(sql, like_params).fetchall()

            # AND 无结果时降级为 OR：匹配任意关键词即可
            if not rows:
                sql = (
                    "SELECT path, title, '' as title_snippet, '' as content_snippet "
                    "FROM wiki_fts WHERE usr_id = ? AND ({}) LIMIT 99"
                ).format(' OR '.join(like_parts))
                rows = conn.execute(sql, like_params).fetchall()
        except Exception as e:
            logger.error("LIKE fallback search failed (query=%r): %s", query, e)
            return []

    return [
        {'path': r['path'], 'title': r['title'],
         'title_snippet': r['title_snippet'], 'content_snippet': r['content_snippet']}
        for r in rows
    ]
