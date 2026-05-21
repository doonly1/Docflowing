"""DocProc 后端服务 —— create_app 工厂入口"""

import os
import sys
import traceback

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

from p2p.node import NodeIdentity
from p2p.discovery import NodeDiscovery

setup_logging()
logger = get_logger(__name__)

_p2p_discovery: NodeDiscovery | None = None


def get_p2p_discovery() -> NodeDiscovery | None:
    return _p2p_discovery


def create_app():
    app = Flask(__name__,
                root_path=project_root,
                template_folder='ui',
                static_folder='ui',
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
        logger.error('Unhandled 500 error: %s\n%s', error, traceback.format_exc())
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'message': '服务器内部错误，请稍后重试'
            }), 500
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
    from fb.routes import fb_bp
    from kb.routes import wiki_bp
    app.register_blueprint(fb_bp)
    app.register_blueprint(wiki_bp)

    # P2P 蓝图
    from p2p.api import p2p_bp
    app.register_blueprint(p2p_bp)

    # 确保管理员用户存在（无妨多次调用）
    ensure_admin_user()

    # 启动 FB 同步后台线程
    try:
        from kb.sync_worker import get_sync_worker
        worker = get_sync_worker()
        worker.start()
        logger.info("FB Sync worker started")
    except Exception as e:
        logger.warning(f"Failed to start FB sync worker: {e}")

    # 初始化 P2P 子系统
    try:
        global _p2p_discovery
        node_identity = NodeIdentity()
        node_identity.load_or_create()
        app.config['P2P_NODE_ID'] = node_identity.node_id
        app.config['P2P_NODE_NAME'] = node_identity.display_name

        _p2p_discovery = NodeDiscovery(
            node_id=node_identity.node_id,
            display_name=node_identity.display_name,
            port=node_identity.port,
            public_key_b64=node_identity.get_public_key_b64()
        )
        _p2p_discovery.start()
        logger.info("P2P subsystem initialized: %s (%s)", node_identity.display_name, node_identity.node_id[:8])
    except Exception as e:
        logger.warning("Failed to initialize P2P subsystem: %s", e)

    logger.info("App created successfully")

    return app
