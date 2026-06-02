"""文件库全文搜索"""

import os
from flask import Blueprint, request, jsonify, g

from server.auth import login_required
from fb.database import get_db, get_visible_fb_ids
from fb.decorators import _is_admin

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')


@fb_bp.route('/search', methods=['GET'])
@login_required
def search_documents():
    """全文搜索文档"""
    user_id = g.user_id
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'success': True, 'results': []})

    is_admin = _is_admin(user_id)
    visible_ids = get_visible_fb_ids(user_id, is_admin)
    if not visible_ids:
        return jsonify({'success': True, 'results': []})

    db = get_db()
    results = []
    keywords = q.lower().split()

    for filebase_id in visible_ids:
        kb_row = db.execute("SELECT name, filebase_type, local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
        if not kb_row:
            continue
        fb_name = kb_row['name'] or ''
        local_path = (kb_row['local_path'] if 'local_path' in kb_row.keys() else '') or ''

        if local_path and os.path.isdir(local_path):
            results.extend(_search_local_dir(local_path, filebase_id, fb_name, keywords))

    return jsonify({'success': True, 'results': results, 'query': q})


def _search_local_dir(base_path, filebase_id, fb_name, keywords):
    """在本地目录中搜索"""
    results = []
    try:
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not d.startswith('~$')]
            for fname in files:
                if fname.startswith('~$'):
                    continue
                matched = False
                match_type = ''
                fname_lower = fname.lower()

                for kw in keywords:
                    if kw in fname_lower:
                        matched = True
                        match_type = 'filename'
                        break

                if not matched:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in ('.md', '.txt', '.html', '.htm', '.xml', '.json', '.csv'):
                        file_path = os.path.join(root, fname)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read().lower()
                            for kw in keywords:
                                if kw in content:
                                    matched = True
                                    match_type = 'content'
                                    break
                        except Exception:
                            pass

                if matched:
                    full_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(full_path, base_path).replace('\\', '/')
                    stat = os.stat(full_path)
                    results.append({
                        'document_id': rel_path,
                        'fb_id': filebase_id,
                        'fb_name': fb_name,
                        'filename': fname,
                        'file_type': os.path.splitext(fname)[1],
                        'file_size': stat.st_size,
                        'updated_at': stat.st_mtime,
                        'match_type': match_type,
                        'rel_path': rel_path
                    })
    except PermissionError:
        pass
    return results
