"""测试认证系统改进（X-Forwarded-For 支持）"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask


@pytest.fixture
def app():
    """创建 Flask 测试应用"""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


class TestGetRealIP:
    """测试 _get_real_ip 函数"""

    def test_remote_addr_when_no_xff(self, app):
        """无 X-Forwarded-For 时返回 request.remote_addr"""
        from server.auth import _get_real_ip

        with app.test_request_context():
            from flask import request
            request.remote_addr = '127.0.0.1'
            result = _get_real_ip()
            assert result == '127.0.0.1'

    def test_xff_client_ip(self, app):
        """有 X-Forwarded-For 时返回第一个 IP（客户端真实 IP）"""
        from server.auth import _get_real_ip

        with app.test_request_context(headers={
            'X-Forwarded-For': '192.168.1.100, 10.0.0.1, 127.0.0.1'
        }):
            from flask import request
            request.remote_addr = '10.0.0.1'
            result = _get_real_ip()
            assert result == '192.168.1.100'

    def test_xff_local_ip(self, app):
        """X-Forwarded-For 为本机地址时返回本机 IP"""
        from server.auth import _get_real_ip

        with app.test_request_context(headers={
            'X-Forwarded-For': '127.0.0.1'
        }):
            from flask import request
            request.remote_addr = '127.0.0.1'
            result = _get_real_ip()
            assert result == '127.0.0.1'

    def test_xff_single_ip(self, app):
        """X-Forwarded-For 只有一个 IP"""
        from server.auth import _get_real_ip

        with app.test_request_context(headers={
            'X-Forwarded-For': '10.0.0.5'
        }):
            from flask import request
            request.remote_addr = '10.0.0.1'
            result = _get_real_ip()
            assert result == '10.0.0.5'

    def test_xff_empty_header(self, app):
        """X-Forwarded-For 为空字符串时回退到 remote_addr"""
        from server.auth import _get_real_ip

        with app.test_request_context(headers={
            'X-Forwarded-For': ''
        }):
            from flask import request
            request.remote_addr = '::1'
            result = _get_real_ip()
            assert result == '::1'


class TestLoginRequired:
    """测试 login_required 装饰器的 IP 校验"""

    def test_localhost_access_passes(self, app):
        """本机地址（127.0.0.1）通过认证"""
        from server.auth import login_required

        @login_required
        def fake_view():
            return 'ok'

        with app.test_request_context():
            from flask import request
            request.remote_addr = '127.0.0.1'
            resp = fake_view()
            assert resp == 'ok'

    def test_remote_access_blocked(self, app):
        """非本机地址被 403 拒绝"""
        from server.auth import login_required

        @login_required
        def fake_view():
            return 'ok'

        with app.test_request_context():
            from flask import request
            request.remote_addr = '192.168.1.100'
            resp = fake_view()
            assert resp[1] == 403
            assert '仅允许本机访问' in str(resp[0].json)

    def test_xff_localhost_passes(self, app):
        """通过 X-Forwarded-For 传来的本机地址应通过认证"""
        from server.auth import login_required

        @login_required
        def fake_view():
            return 'ok'

        with app.test_request_context(headers={
            'X-Forwarded-For': '127.0.0.1'
        }):
            from flask import request
            request.remote_addr = '10.0.0.1'  # 代理 IP
            resp = fake_view()
            assert resp == 'ok'
