import logging
import threading
import time

from flask import Blueprint, jsonify, request, g
from server.auth import login_required

from .session_db import get_session_db

logger = logging.getLogger(__name__)

def register_session_routes(bp: Blueprint):

    @bp.route('/session/create', methods=['POST'])
    @login_required
    def create_session():

        user_id = g.user_id

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
    @login_required
    def append_message(session_id):

        user_id = g.user_id

        data = request.get_json() or {}

        role = data.get('role')

        content = data.get('content')

        tool_name = data.get('tool_name')

        token_count = data.get('token_count')

        sources = data.get('sources')

        if not role or not content:

            return jsonify({'success': False, 'error': 'role and content are required'}), 400

        db = get_session_db(user_id)

        session = db.get_session(session_id)

        if not session:

            db.create_session(session_id, user_id=user_id)

        msg_id = db.append_message(session_id, role, content, tool_name=tool_name, token_count=token_count, sources=sources)

        if session and not session.get('title') and role == 'user':

            db.set_session_title(session_id, content[:50].strip() + ('...' if len(content) > 50 else ''))

        if role == 'assistant' and session and not session.get('title'):

            _auto_title_async(user_id, session_id, db)

        return jsonify({

            'success': True,

            'message_id': msg_id,

        })

    @bp.route('/session/<session_id>', methods=['GET'])
    @login_required
    def get_session(session_id):

        user_id = g.user_id

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
    @login_required
    def list_sessions():

        user_id = g.user_id

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
    @login_required
    def search_sessions():

        user_id = g.user_id

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
    @login_required
    def delete_session(session_id):

        user_id = g.user_id

        db = get_session_db(user_id)

        deleted = db.delete_session(session_id)

        if not deleted:

            return jsonify({'success': False, 'error': 'Session not found'}), 404

        return jsonify({

            'success': True,

            'message': 'Session deleted',

        })

    @bp.route('/sessions', methods=['DELETE'])
    @login_required
    def clear_all_sessions():

        user_id = g.user_id

        db = get_session_db(user_id)

        count = db.clear_all_sessions()

        return jsonify({

            'success': True,

            'message': 'All sessions cleared',

            'deleted_count': count,

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
