"""测试认证系统的 IP 判定契约。

安全设计：_get_real_ip 只信 request.remote_addr（TCP 层真实远端），
X-Forwarded-For 请求头可被客户端伪造，一律忽略 —— 防止伪造 XFF 绕过仅本机认证。
"""

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

    def test_xff_is_ignored_multiple_ips(self, app):
        """多级 X-Forwarded-For 被忽略，只信 remote_addr（防伪造绕过）"""
        from server.auth import _get_real_ip

        with app.test_request_context(headers={
            'X-Forwarded-For': '192.168.1.100, 10.0.0.1, 127.0.0.1'
        }):
            from flask import request
            request.remote_addr = '10.0.0.1'
            result = _get_real_ip()
            assert result == '10.0.0.1'

    def test_xff_local_ip_spoof_still_remote_addr(self, app):
        """XFF 伪造为本机 IP 也无效，仍以 remote_addr 为准"""
        from server.auth import _get_real_ip

        with app.test_request_context(headers={
            'X-Forwarded-For': '127.0.0.1'
        }):
            from flask import request
            request.remote_addr = '10.0.0.1'
            result = _get_real_ip()
            assert result == '10.0.0.1'

    def test_xff_single_ip_ignored(self, app):
        """单个 XFF IP 同样被忽略"""
        from server.auth import _get_real_ip

        with app.test_request_context(headers={
            'X-Forwarded-For': '10.0.0.5'
        }):
            from flask import request
            request.remote_addr = '10.0.0.1'
            result = _get_real_ip()
            assert result == '10.0.0.1'

    def test_xff_empty_header(self, app):
        """X-Forwarded-For 为空/缺失时正常返回 remote_addr（XFF 本就不参与判定）"""
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

    def test_xff_localhost_spoof_blocked(self, app):
        """伪造 X-Forwarded-For: 127.0.0.1 不能绕过本机认证（remote_addr 非回环 → 403）"""
        from server.auth import login_required

        @login_required
        def fake_view():
            return 'ok'

        with app.test_request_context(headers={
            'X-Forwarded-For': '127.0.0.1'
        }):
            from flask import request
            request.remote_addr = '10.0.0.1'  # 真实远端是代理/非本机
            resp = fake_view()
            assert resp[1] == 403
            assert '仅允许本机访问' in str(resp[0].json)
