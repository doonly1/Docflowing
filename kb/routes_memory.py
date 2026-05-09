import json
import logging
import os
from flask import Blueprint, jsonify, request

from .memory import get_memory_store

logger = logging.getLogger(__name__)


def _get_user_id():
    user_id = getattr(request, '_user_id', None)
    if not user_id:
        auth_header = request.headers.get('Authorization', '')
        token = None
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        elif auth_header:
            token = auth_header

        if not token:
            data = request.get_json(silent=True) or {}
            token = data.get('token') or data.get('client_id')

        if not token:
            token = request.args.get('token') or request.args.get('client_id')

        if token:
            tokens_path = os.path.join(os.path.expanduser('~'), '.config', 'DocProc', 'auth', 'tokens.json')
            try:
                if os.path.exists(tokens_path):
                    with open(tokens_path, 'r', encoding='utf-8') as f:
                        tokens = json.load(f)
                    user_id = tokens.get(token)
            except Exception:
                pass

    if not user_id:
        user_id = 'default'
    return user_id


def register_memory_routes(bp: Blueprint):

    @bp.route('/memory', methods=['GET'])
    def get_memory():
        user_id = _get_user_id()
        store = get_memory_store(user_id)
        target = request.args.get('target')
        if target and target not in ('memory', 'user'):
            return jsonify({'success': False, 'error': "Invalid target. Use 'memory' or 'user'."}), 400

        targets = [target] if target else ['memory', 'user']
        result = {}
        for t in targets:
            entries = store._entries_for(t)
            result[t] = {
                'entries': entries,
                'count': len(entries),
                'usage': store._char_count(t),
                'limit': store._char_limit(t),
            }

        return jsonify({
            'success': True,
            'memory': result,
            'usage_info': store.get_usage_info(),
        })

    @bp.route('/memory/add', methods=['POST'])
    def add_memory():
        user_id = _get_user_id()
        data = request.get_json() or {}
        target = data.get('target', 'memory')
        content = data.get('content')

        if not content:
            return jsonify({'success': False, 'error': 'Content is required.'}), 400
        if target not in ('memory', 'user'):
            return jsonify({'success': False, 'error': "Invalid target. Use 'memory' or 'user'."}), 400

        store = get_memory_store(user_id)
        result = store.add(target, content)

        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code

    @bp.route('/memory/replace', methods=['POST'])
    def replace_memory():
        user_id = _get_user_id()
        data = request.get_json() or {}
        target = data.get('target', 'memory')
        old_text = data.get('old_text')
        new_content = data.get('new_content')

        if not old_text or not new_content:
            return jsonify({'success': False, 'error': 'old_text and new_content are required.'}), 400
        if target not in ('memory', 'user'):
            return jsonify({'success': False, 'error': "Invalid target. Use 'memory' or 'user'."}), 400

        store = get_memory_store(user_id)
        result = store.replace(target, old_text, new_content)

        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code

    @bp.route('/memory/remove', methods=['POST'])
    def remove_memory():
        user_id = _get_user_id()
        data = request.get_json() or {}
        target = data.get('target', 'memory')
        old_text = data.get('old_text')

        if not old_text:
            return jsonify({'success': False, 'error': 'old_text is required.'}), 400
        if target not in ('memory', 'user'):
            return jsonify({'success': False, 'error': "Invalid target. Use 'memory' or 'user'."}), 400

        store = get_memory_store(user_id)
        result = store.remove(target, old_text)

        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code

    @bp.route('/memory/prompt', methods=['GET'])
    def get_memory_prompt():
        user_id = _get_user_id()
        store = get_memory_store(user_id)
        target = request.args.get('target')
        prompt_text = store.format_for_system_prompt(target=target if target else None)
        return jsonify({
            'success': True,
            'prompt': prompt_text,
            'usage_info': store.get_usage_info(),
        })
