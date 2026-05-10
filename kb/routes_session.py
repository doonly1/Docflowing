import json
import logging
import os
import threading
import time
from flask import Blueprint, jsonify, request

from .session_db import get_session_db

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


def register_session_routes(bp: Blueprint):

    @bp.route('/session/create', methods=['POST'])
    def create_session():
        user_id = _get_user_id()
        data = request.get_json() or {}
        session_id = data.get('session_id')
        model = data.get('model')

        if not session_id:
            session_id = f"kb_{int(time.time() * 1000)}"

        db = get_session_db(user_id)
        db.create_session(session_id, user_id=user_id, model=model)

        return jsonify({
            'success': True,
            'session_id': session_id,
        })

    @bp.route('/session/<session_id>/message', methods=['POST'])
    def append_message(session_id):
        user_id = _get_user_id()
        data = request.get_json() or {}
        role = data.get('role')
        content = data.get('content')
        tool_name = data.get('tool_name')
        token_count = data.get('token_count')

        if not role or not content:
            return jsonify({'success': False, 'error': 'role and content are required'}), 400

        db = get_session_db(user_id)
        session = db.get_session(session_id)
        if not session:
            db.create_session(session_id, user_id=user_id)

        msg_id = db.append_message(session_id, role, content, tool_name=tool_name, token_count=token_count)

        if session and not session.get('title') and role == 'user':
            db.set_session_title(session_id, content[:50].strip() + ('...' if len(content) > 50 else ''))

        if role == 'assistant' and session and not session.get('title'):
            _auto_title_async(user_id, session_id, db)

        return jsonify({
            'success': True,
            'message_id': msg_id,
        })

    @bp.route('/session/<session_id>', methods=['GET'])
    def get_session(session_id):
        user_id = _get_user_id()
        db = get_session_db(user_id)
        session = db.get_session(session_id)
        if not session:
            return jsonify({'success': False, 'error': 'Session not found'}), 404

        limit = request.args.get('limit', type=int)
        messages = db.get_messages(session_id, limit=limit)

        return jsonify({
            'success': True,
            'session': session,
            'messages': messages,
        })

    @bp.route('/sessions', methods=['GET'])
    def list_sessions():
        user_id = _get_user_id()
        db = get_session_db(user_id)
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)

        sessions = db.list_sessions(user_id=user_id, limit=limit, offset=offset)

        return jsonify({
            'success': True,
            'sessions': sessions,
            'count': len(sessions),
        })

    @bp.route('/sessions/search', methods=['GET'])
    def search_sessions():
        user_id = _get_user_id()
        query = request.args.get('q', '')
        if not query:
            return jsonify({'success': False, 'error': 'Query parameter q is required'}), 400

        db = get_session_db(user_id)
        limit = request.args.get('limit', 20, type=int)

        results = db.search_messages(query, user_id=user_id, limit=limit)

        return jsonify({
            'success': True,
            'query': query,
            'results': results,
            'count': len(results),
        })

    @bp.route('/session/<session_id>', methods=['DELETE'])
    def delete_session(session_id):
        user_id = _get_user_id()
        db = get_session_db(user_id)
        deleted = db.delete_session(session_id)
        if not deleted:
            return jsonify({'success': False, 'error': 'Session not found'}), 404

        return jsonify({
            'success': True,
            'message': 'Session deleted',
        })


def _auto_title_async(user_id: str, session_id: str, db):
    def _generate():
        try:
            from kb.llm import generate_title
            messages = db.get_messages(session_id, limit=4)
            user_msg = ""
            assistant_msg = ""
            for m in messages:
                if m.get('role') == 'user' and not user_msg:
                    user_msg = m.get('content', '')
                elif m.get('role') == 'assistant' and not assistant_msg:
                    assistant_msg = m.get('content', '')

            if not user_msg:
                return

            title = generate_title(user_msg, assistant_msg, user_id=user_id)
            if title:
                existing = db.get_session(session_id)
                if existing and not existing.get('title'):
                    db.set_session_title(session_id, title)
        except Exception as e:
            logger.debug("Auto-title generation failed: %s", e)

    t = threading.Thread(target=_generate, daemon=True, name="auto-title")
    t.start()
