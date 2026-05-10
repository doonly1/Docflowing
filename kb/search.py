from kb.database import get_db


def search_wiki(usr_id, query):
    if not query or not query.strip():
        return []

    conn = get_db()
    search_terms = query.strip().split()
    fts_query = ' OR '.join(search_terms)

    rows = None
    try:
        rows = conn.execute(
            "SELECT path, title, snippet(wiki_fts, 1, '<mark>', '</mark>', '...', 30) as title_snippet, "
            "snippet(wiki_fts, 2, '<mark>', '</mark>', '...', 60) as content_snippet "
            "FROM wiki_fts WHERE usr_id = ? AND wiki_fts MATCH ?",
            (usr_id, fts_query)
        ).fetchall()
    except Exception:
        try:
            rows = conn.execute(
                "SELECT path, title, '' as title_snippet, '' as content_snippet "
                "FROM wiki_fts WHERE usr_id = ? AND (title LIKE ? OR content LIKE ?)",
                (usr_id, f'%{query}%', f'%{query}%')
            ).fetchall()
        except Exception:
            return []

    if rows is None:
        return []

    results = []
    for row in rows:
        results.append({
            'path': row['path'],
            'title': row['title'],
            'title_snippet': row['title_snippet'],
            'content_snippet': row['content_snippet']
        })

    return results
