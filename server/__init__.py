"""DocProc 后端服务 —— create_app 工厂入口"""

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'tools'))
sys.path.insert(0, project_root)

from flask import Flask, jsonify, request
from flask_cors import CORS

from logging_config import setup_logging, get_logger
from server.middleware import setup_middleware
from server.auth import auth_bp, ensure_admin_user
from server.workspace import workspace_bp, MAX_SESSION_SIZE
from server.settings import settings_bp
from server.runner import runner_bp

setup_logging()
logger = get_logger(__name__)


def create_app():
    app = Flask(__name__,
                root_path=project_root,
                template_folder='web',
                static_folder='web',
                static_url_path='')
    CORS(app)
    app.config['MAX_CONTENT_LENGTH'] = MAX_SESSION_SIZE

    # 中间件
    setup_middleware(app)

    # 首页
    @app.route('/')
    def index():
        return app.send_static_file('index.html')

    # 请求体过大处理
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({
            'success': False,
            'message': f'上传总大小超过 {MAX_SESSION_SIZE // 1024 // 1024}MB 限制'
        }), 413

    # 全局错误处理器 - 确保API请求返回JSON
    @app.errorhandler(500)
    def internal_error(error):
        # 如果是API请求，返回JSON
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'message': '服务器内部错误，请稍后重试'
            }), 500
        # 否则返回默认的HTML错误页面
        return error

    @app.errorhandler(404)
    def not_found(error):
        # 如果是API请求，返回JSON
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'message': f'接口不存在: {request.path}'
            }), 404
        # 否则返回默认的HTML错误页面
        return error

    # 注册蓝图
    app.register_blueprint(auth_bp)
    app.register_blueprint(workspace_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(runner_bp)

    # 外部蓝图
    from fb.routes import kb_bp
    from kb.routes import wiki_bp
    app.register_blueprint(kb_bp)
    app.register_blueprint(wiki_bp)

    # 确保管理员用户存在（无妨多次调用）
    ensure_admin_user()
    logger.info("App created successfully")

    return app
