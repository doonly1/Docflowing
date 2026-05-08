"""请求 ID 中间件"""

import uuid
from flask import request, g
from logging_config import set_request_id


def setup_middleware(app):
    @app.before_request
    def _capture_request_id():
        req_id = request.headers.get('X-Request-Id') or str(uuid.uuid4())
        set_request_id(req_id)
        g.request_id = req_id

    @app.after_request
    def _inject_request_id(response):
        response.headers['X-Request-Id'] = g.get('request_id', '')
        return response
