import logging

from kb.database import get_db

logger = logging.getLogger(__name__)


def _escape_fts_term(term: str) -> str:
    """转义 FTS5 查询中的特殊字符，用双引号包裹为短语查询。

    参考 SQLite FTS5 文档：双引号内的内容被视为短语，内部双引号需加倍转义。
    """
    escaped = term.replace('"', '""')
    return f'"{escaped}"'


def _first_hit_snippet(text, keywords, max_len=60):
    """为 LIKE 兜底手动生成带 <mark> 高亮的片段。"""
    if not text:
        return ''
    text_lower = text.lower()
    best = -1
    best_kw = None
    for kw in keywords:
        pos = text_lower.find(kw.lower())
        if pos != -1 and (best == -1 or pos < best):
            best = pos
            best_kw = kw
    if best == -1:
        return text[:max_len]
    start = max(0, best - max_len // 3)
    end = min(len(text), start + max_len)
    if end - start < max_len:
        start = max(0, end - max_len)
    seg = text[start:end]
    if best_kw:
        idx = seg.lower().find(best_kw.lower())
        if idx != -1:
            seg = (seg[:idx] + '<mark>' + seg[idx:idx + len(best_kw)]
                   + '</mark>' + seg[idx + len(best_kw):])
    prefix = '...' if start > 0 else ''
    suffix = '...' if end < len(text) else ''
    return f'{prefix}{seg}{suffix}'


def _like_search_wiki(conn, usr_id, search_terms):
    """FTS5 空结果时的 LIKE 兜底。

    trigram 分词器对 <3 字符的查询词（常见中文 2 字词）无法命中，退回子串扫描。
    也顺带覆盖分词/标点粘连导致 FTS 漏召回的边界情况。对 FTS5 虚拟表直接执行
    LIKE 会退化为全表扫描，数据量有限时可接受；结果最多取 50 条。
    """
    params = [usr_id]
    conds = []
    for t in search_terms:
        conds.append("(title LIKE ? OR content LIKE ?)")
        params += [f'%{t}%', f'%{t}%']
    where = ' AND '.join(conds)
    try:
        rows = conn.execute(
            f"SELECT path, title, content FROM wiki_fts "
            f"WHERE usr_id = ? AND {where} LIMIT 50",
            params,
        ).fetchall()
    except Exception as e:
        logger.warning("wiki LIKE fallback failed (terms=%r): %s", search_terms, e)
        return []
    return [
        {
            'path': r['path'],
            'title': r['title'],
            'title_snippet': _first_hit_snippet(r['title'], search_terms, 30),
            'content_snippet': _first_hit_snippet(r['content'], search_terms, 60),
        }
        for r in rows
    ]


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
        rows = []

    if rows:
        return [
            {'path': r['path'], 'title': r['title'],
             'title_snippet': r['title_snippet'], 'content_snippet': r['content_snippet']}
            for r in rows
        ]

    # FTS 无结果：trigram 对 <3 字符查询词无法命中，退回 LIKE 子串匹配
    return _like_search_wiki(conn, usr_id, search_terms)
