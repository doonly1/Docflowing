import json

import logging

import os

from flask import Blueprint, jsonify, request, g
from server.auth import login_required

from .memory import get_memory_store

logger = logging.getLogger(__name__)

def register_memory_routes(bp: Blueprint):

    @bp.route('/memory', methods=['GET'])
    @login_required
    def get_memory():

        user_id = g.user_id

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
    @login_required
    def add_memory():

        user_id = g.user_id

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
    @login_required
    def replace_memory():

        user_id = g.user_id

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
    @login_required
    def remove_memory():

        user_id = g.user_id

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
    @login_required
    def get_memory_prompt():

        user_id = g.user_id

        store = get_memory_store(user_id)

        target = request.args.get('target')

        prompt_text = store.format_for_system_prompt(target=target if target else None)

        return jsonify({

            'success': True,

            'prompt': prompt_text,

            'usage_info': store.get_usage_info(),

        })
