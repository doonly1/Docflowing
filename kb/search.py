from kb.database import get_db


def search_wiki(usr_id, query):
    if not query or not query.strip():
        return []

    conn = get_db(usr_id)
    search_terms = query.strip().split()
    fts_query = ' OR '.join(search_terms)

    # FTS5 全文搜索（trigram tokenizer 对中文词组匹配良好）
    try:
        rows = conn.execute(
            "SELECT path, title, "
            "snippet(wiki_fts, 1, '<mark>', '</mark>', '...', 30) as title_snippet, "
            "snippet(wiki_fts, 2, '<mark>', '</mark>', '...', 60) as content_snippet "
            "FROM wiki_fts WHERE usr_id = ? AND wiki_fts MATCH ?",
            (usr_id, fts_query)
        ).fetchall()
    except Exception:
        rows = []

    # trigram 仍可能有遗漏，用 LIKE 补充
    if not rows:
        try:
            rows = conn.execute(
                "SELECT path, title, '' as title_snippet, '' as content_snippet "
                "FROM wiki_fts WHERE usr_id = ? AND (title LIKE ? OR content LIKE ?)",
                (usr_id, f'%{query}%', f'%{query}%')
            ).fetchall()
        except Exception:
            return []

    return [
        {'path': r['path'], 'title': r['title'],
         'title_snippet': r['title_snippet'], 'content_snippet': r['content_snippet']}
        for r in rows
    ]
