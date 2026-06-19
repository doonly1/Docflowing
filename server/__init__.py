"""Docflowing 后端服务 —— create_app 工厂入口"""

import os
import sys
import threading
import traceback

# PyInstaller 打包模式下，资源文件在 sys._MEIPASS 下
is_frozen = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
if is_frozen:
    project_root = sys._MEIPASS
else:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.join(project_root, 'tools'))
sys.path.insert(0, project_root)

from flask import Flask, jsonify, request
from flask_cors import CORS

from logging_config import setup_logging, get_logger
from server.middleware import setup_middleware
from server.auth import auth_bp
from server.workspace import workspace_bp
from server.settings import settings_bp
from server.runner import runner_bp

from p2p.node import NodeIdentity
from p2p.discovery import NodeDiscovery

setup_logging()
logger = get_logger(__name__)

_node_identity: NodeIdentity | None = None
_p2p_discovery: NodeDiscovery | None = None


def get_node_identity() -> NodeIdentity | None:
    return _node_identity


def get_p2p_discovery() -> NodeDiscovery | None:
    return _p2p_discovery


def create_app():
    # PyInstaller 打包模式下，静态资源在 sys._MEIPASS/ui/
    # is_frozen 和 project_root 已在模块顶部定义
    if is_frozen:
        static_folder = 'ui'
        template_folder = 'ui'
        root_path = project_root
    else:
        # 开发模式：静态资源在项目根目录
        static_folder = 'ui'
        template_folder = 'ui'
        root_path = project_root

    app = Flask(__name__,
                root_path=root_path,
                template_folder=template_folder,
                static_folder=static_folder,
                static_url_path='')
    # 仅允许本地页面访问 API，禁止任意跨域请求
    CORS(app, resources={
        r"/*": {
            "origins": [
                "null",           # file:// 协议
                "http://127.0.0.1:*",
                "http://localhost:*",
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "X-Request-Id"],
            "supports_credentials": True,
        }
    })
    MAX_SESSION_SIZE = 200 * 1024 * 1024
    app.config['MAX_CONTENT_LENGTH'] = MAX_SESSION_SIZE

    # 中间件
    setup_middleware(app)

    # CSP 策略（移至 Flask 端，不再依赖 Electron session）
    @app.after_request
    def add_security_headers(response):
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws:; "
            "font-src 'self' data:; "
            "object-src 'none'; "
            "media-src 'self' blob:; "
            "frame-src 'self' blob: data:; "
            "form-action 'self'; "
            "base-uri 'self'"
        )
        response.headers['Content-Security-Policy'] = csp
        return response

    # 首页（注入 pywebview 兼容 shim）
    @app.route('/')
    def index():
        # 读取 index.html 并注入 pywebview 兼容层
        import os
        static_dir = app.static_folder or os.path.join(app.root_path, app.static_folder or 'ui')
        index_path = os.path.join(static_dir, 'index.html')
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return app.send_static_file('index.html')

        shim = (
            '<script>\n'
            '(function() {\n'
            '  function _checkPywebview() {\n'
            '    if (window.pywebview && window.pywebview.api) {\n'
            '      window.electronAPI = window.pywebview.api;\n'
            '    } else {\n'
            '      setTimeout(_checkPywebview, 50);\n'
            '    }\n'
            '  }\n'
            '  _checkPywebview();\n'
            '})();\n'
            '</script>\n'
        )
        content = content.replace('</head>', shim + '</head>')
        return app.response_class(content, mimetype='text/html; charset=utf-8')

    # 请求体过大处理
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({
            'success': False,
            'message': f'上传总大小超过 {MAX_SESSION_SIZE // 1024 // 1024}MB 限制'
        }), 413

    # 上游网关超时（代理场景）
    @app.errorhandler(504)
    def gateway_timeout(error):
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'message': '请求超时，请稍后重试'
            }), 504
        return error

    # 上游网关错误
    @app.errorhandler(502)
    def bad_gateway(error):
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'message': '服务暂时不可用，请稍后重试'
            }), 502
        return error

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

    # 启动 FB 同步后台线程
    try:
        from kb.sync_worker import get_sync_worker
        worker = get_sync_worker()
        worker.start()
        logger.info("FB Sync worker started")
    except Exception as e:
        logger.warning(f"Failed to start FB sync worker: {e}")

    # 预加载节点身份（轻量，不阻塞）
    global _node_identity, _p2p_discovery
    try:
        _node_identity = NodeIdentity()
        _node_identity.load_or_create()
        app.config['P2P_NODE_ID'] = _node_identity.node_id
        app.config['P2P_NODE_NAME'] = _node_identity.display_name
        logger.info("Node identity loaded: %s (%s)", _node_identity.display_name, _node_identity.node_id[:8])
    except Exception as e:
        logger.warning("Failed to load node identity: %s", e)

    # 后台启动 P2P 发现（mDNS 注册不阻塞主线程）
    def _start_p2p():
        # Windows 上为 zeroconf 强制使用兼容的事件循环策略
        if sys.platform == 'win32':
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        try:
            global _p2p_discovery
            if not _node_identity:
                return
            _p2p_discovery = NodeDiscovery(
                node_id=_node_identity.node_id,
                display_name=_node_identity.display_name,
                port=_node_identity.port,
                public_key_b64=_node_identity.get_public_key_b64()
            )
            _p2p_discovery.start()
            logger.info("P2P discovery started")
        except Exception as e:
            logger.warning("Failed to start P2P discovery: %s", e)

    t = threading.Thread(target=_start_p2p, daemon=True, name="P2PInit")
    t.start()

    logger.info("App created successfully")

    return app
