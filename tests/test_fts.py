# -*- coding: utf-8 -*-
"""
FTS5 分词器行为回归测试。

背景（2026-09 崩溃修复）：
- 旧实现依赖 kb/fts_ext/simple.dll 外部扩展，与 Python 3.12 内置 SQLite 3.49.1
  不兼容，任意 FTS 写入都会 SIGSEGV 闪退（「同步到知识库」后无法启动）。
- 修复方案：改用 SQLite 内置 trigram 分词器（>=3.34 即支持，无需扩展），
  对任意多字节文本（含中文）均可安全写入。
- trigram 的已知限制：<3 个字符的词条用 MATCH 查不到任何行（不报错），
  因此 kb/search.py / kb/session_db.py 对短词走 LIKE 兜底。本文件固化该契约。
"""
import sqlite3


def _conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    return c


def test_trigram_write_is_safe_for_cjk():
    """trigram 对中文写入必须安全（不复现 simple.dll 的崩溃路径）。"""
    conn = _conn()
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(content, tokenize=trigram)")
    conn.execute("INSERT INTO t VALUES('项目管理和文档编写的最佳实践')")
    conn.execute("INSERT INTO t VALUES('Python编程语言基础教程')")
    n = conn.execute("SELECT count(*) FROM t").fetchone()[0]
    assert n == 2


def test_trigram_phrase_match_ge3_chars():
    """>=3 字符的短语 MATCH 可命中。"""
    conn = _conn()
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(content, tokenize=trigram)")
    conn.execute("INSERT INTO t VALUES('项目管理和文档编写的最佳实践')")
    for term in ('项目管理', '文档编写', '最佳实践'):
        r = conn.execute("SELECT count(*) FROM t WHERE t MATCH ?", (term,)).fetchone()
        assert r[0] >= 1, 'trigram 应命中 {}'.format(term)


def test_trigram_short_term_returns_zero_no_error():
    """
    2 字中文词条 MATCH 返回 0 行且不报错 ——
    这正是 kb/search.py / kb/session_db.py 短词 LIKE 兜底存在的原因。
    """
    conn = _conn()
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(content, tokenize=trigram)")
    conn.execute("INSERT INTO t VALUES('项目管理和文档编写的最佳实践')")
    for term in ('文档', '管理'):
        r = conn.execute("SELECT count(*) FROM t WHERE t MATCH ?", (term,)).fetchone()
        assert r[0] == 0


def test_trigram_content_table_is_plain_rows():
    """
    FTS5 shadow 表（t_content）是普通行，可直接 SELECT 全量读取重建，
    不触发分词器 —— schema 迁移因此可无损重建索引。
    """
    conn = _conn()
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(content, tokenize=trigram)")
    conn.execute("INSERT INTO t VALUES('项目管理和文档编写的最佳实践')")
    # FTS5 影子表 t_content(id, c0)：c0 为原文，直接 SELECT 不触发分词器
    rows = conn.execute("SELECT id, c0 FROM t_content").fetchall()
    assert len(rows) == 1
    assert rows[0]['c0'] == '项目管理和文档编写的最佳实践'
    assert 'trigram' in conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='t'"
    ).fetchone()[0]
