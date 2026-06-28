# -*- coding: utf-8 -*-
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect(':memory:')

# unicode61
conn.execute("CREATE VIRTUAL TABLE t1 USING fts5(content, tokenize=unicode61)")
conn.execute("INSERT INTO t1 VALUES('项目管理和文档编写的最佳实践')")
conn.execute("INSERT INTO t1 VALUES('Python编程语言基础教程')")

terms = ['文档', '管理', '项目管理']
for w in terms:
    r = conn.execute("SELECT count(*) FROM t1 WHERE t1 MATCH ?", (w,)).fetchone()
    print('bare "{}": {}'.format(w, r[0]))
    r = conn.execute("SELECT count(*) FROM t1 WHERE t1 MATCH ?", (f'"{w}"',)).fetchone()
    print('  phrase "{}": {}'.format(w, r[0]))

# AND
r = conn.execute("SELECT count(*) FROM t1 WHERE t1 MATCH '\"管理\" AND \"文档\"'").fetchone()
print('phrase AND: {}'.format(r[0]))

# 直接查 unicode61 的词表
print('\nunicode61 token table:')
for row in conn.execute("SELECT * FROM t1_content").fetchall():
    print('  ', dict(row))

conn.close()

# trigram
print('\ntrigram:')
conn2 = sqlite3.connect(':memory:')
conn2.execute("CREATE VIRTUAL TABLE t2 USING fts5(content, tokenize=trigram)")
conn2.execute("INSERT INTO t2 VALUES('项目管理和文档编写的最佳实践')")

for w in terms:
    r = conn2.execute("SELECT count(*) FROM t2 WHERE t2 MATCH ?", (w,)).fetchone()
    print('bare "{}": {}'.format(w, r[0]))

print('\ntrigram token table:')
for row in conn2.execute("SELECT * FROM t2_content").fetchall():
    print('  ', dict(row))

conn2.close()
