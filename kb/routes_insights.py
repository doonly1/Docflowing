import json
import logging
import os
from flask import Blueprint, jsonify, request

from .insights import InsightsEngine

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


def register_insights_routes(bp: Blueprint):

    @bp.route('/insights', methods=['GET'])
    def api_insights():
        user_id = _get_user_id()
        days = request.args.get('days', 30, type=int)

        engine = InsightsEngine(user_id)
        report = engine.generate(days=days)

        return jsonify({
            'success': True,
            'report': report,
        })

    @bp.route('/insights/overview', methods=['GET'])
    def api_insights_overview():
        user_id = _get_user_id()
        days = request.args.get('days', 30, type=int)

        engine = InsightsEngine(user_id)
        report = engine.generate(days=days)

        return jsonify({
            'success': True,
            'overview': report.get('overview', {}),
            'memory_usage': report.get('memory_usage', {}),
        })
