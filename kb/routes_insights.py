import json

import logging

import os

from flask import Blueprint, jsonify, request, g
from server.auth import login_required

from .insights import InsightsEngine

logger = logging.getLogger(__name__)

def register_insights_routes(bp: Blueprint):

    @bp.route('/insights', methods=['GET'])
    @login_required
    def api_insights():

        user_id = g.user_id

        days = request.args.get('days', 30, type=int)

        engine = InsightsEngine(user_id)

        report = engine.generate(days=days)

        return jsonify({

            'success': True,

            'report': report,

        })

    @bp.route('/insights/overview', methods=['GET'])
    @login_required
    def api_insights_overview():

        user_id = g.user_id

        days = request.args.get('days', 30, type=int)

        engine = InsightsEngine(user_id)

        report = engine.generate(days=days)

        return jsonify({

            'success': True,

            'overview': report.get('overview', {}),

            'memory_usage': report.get('memory_usage', {}),

        })
