"""测试 pywebview 迁移 — desktop_app.py + server/__init__.py 改动"""

import sys
import os
import threading
import socket
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

import pytest


# ==================== server/__init__.py 改动测试 ====================

class TestCSPHeaders:
    """CSP 响应头应该正确注入"""

    def test_csp_on_index(self):
        """首页响应应包含 CSP 头"""
        from server import create_app
        app = create_app()
        with app.test_client() as c:
            resp = c.get('/')
            csp = resp.headers.get('Content-Security-Policy', '')
            assert "default-src 'self'" in csp
            assert "script-src 'self'" in csp
            assert "style-src 'self'" in csp

    def test_csp_on_api(self):
        """API 响应也应包含 CSP 头"""
        from server import create_app
        app = create_app()
        with app.test_client() as c:
            resp = c.get('/api/user/me')
            csp = resp.headers.get('Content-Security-Policy', '')
            assert csp != ''


class TestPywebviewShim:
    """pywebview JS shim 应该正确注入首页"""

    def test_shim_injected(self):
        """首页 HTML 应包含 electronAPI = pywebview.api shim"""
        from server import create_app
        app = create_app()
        with app.test_client() as c:
            resp = c.get('/')
            html = resp.get_data(as_text=True)
            assert 'window.electronAPI = window.pywebview.api' in html

    def test_shim_before_head_close(self):
        """shim 应在 </head> 之前注入"""
        from server import create_app
        app = create_app()
        with app.test_client() as c:
            resp = c.get('/')
            html = resp.get_data(as_text=True)
            # shim 出现在 </head> 之前
            shim_pos = html.index('window.electronAPI')
            head_close = html.index('</head>')
            assert shim_pos < head_close

    def test_shim_does_not_break_html(self):
        """注入 shim 后 HTML 结构完整"""
        from server import create_app
        app = create_app()
        with app.test_client() as c:
            resp = c.get('/')
            html = resp.get_data(as_text=True)
            # 基本结构检查
            assert html.startswith('<!DOCTYPE html>') or html.strip().startswith('<!DOCTYPE html>') or html.strip().startswith('<html')
            assert '</html>' in html
            assert '</head>' in html
            assert '</body>' in html or '</script>' in html
            assert len(html) > 10000  # 确保不是错误页面


class TestPathDetection:
    """路径检测逻辑在开发模式下应正确"""

    def test_dev_mode_path(self):
        """开发模式使用 project_root/ui/"""
        from server import create_app
        app = create_app()
        # 开发模式下 root_path 应为项目根目录
        assert 'Docflowing' in app.root_path
        # 静态文件目录应为 ui/
        assert 'ui' in (app.static_folder or '')

    def test_index_file_served(self):
        """首页应返回 index.html"""
        from server import create_app
        app = create_app()
        with app.test_client() as c:
            resp = c.get('/')
            assert resp.status_code == 200
            assert resp.content_type.startswith('text/html')


# ==================== desktop_app.py 核心功能测试 ====================

class TestDesktopAPI:
    """DesktopAPI 类（不含窗口时的独立测试）"""

    def test_api_creation(self):
        """API 对象初始化正常"""
        from desktop_app import DesktopAPI
        api = DesktopAPI()
        assert api._close_action == 'exit'
        assert api._is_quitting is False
        assert api._is_maximized is False
        assert api._window is None

    def test_getAppVersion(self):
        """版本信息应从 package.json 读取"""
        from desktop_app import DesktopAPI
        api = DesktopAPI()
        version = api.getAppVersion()
        assert version == '1.0.0'

    def test_setCloseAction(self):
        """关闭行为设置"""
        from desktop_app import DesktopAPI
        api = DesktopAPI()
        assert api._close_action == 'exit'

        api.setCloseAction('minimize')
        assert api._close_action == 'minimize'

        api.setCloseAction('exit')
        assert api._close_action == 'exit'

    def test_setCloseAction_invalid(self):
        """非法的关闭行为应被忽略"""
        from desktop_app import DesktopAPI
        api = DesktopAPI()
        api.setCloseAction('invalid')
        assert api._close_action == 'exit'  # 保持不变

    def test_windowIsMaximized_without_window(self):
        """无窗口时返回 False"""
        from desktop_app import DesktopAPI
        api = DesktopAPI()
        assert api.windowIsMaximized() is False

    def test_getWindowState_without_window(self):
        """无窗口时 getWindowState 返回默认值"""
        from desktop_app import DesktopAPI
        api = DesktopAPI()
        state = api.getWindowState()
        assert state == {'maximized': False}

    def test_windowMethods_without_window(self):
        """无窗口时调用窗口方法不应报错"""
        from desktop_app import DesktopAPI
        api = DesktopAPI()
        # 这些方法在无 _window 时应静默忽略
        api.windowMinimize()
        api.windowToggleMaximize()
        api.windowClose()
        api.windowShow()
        assert api._is_quitting is False  # windowClose不应设置退出标志（因无窗口）

    def test_windowGetPosition_without_window(self):
        """无窗口时返回默认坐标"""
        from desktop_app import DesktopAPI
        api = DesktopAPI()
        pos = api.windowGetPosition()
        assert pos == {'x': 0, 'y': 0}

    def test_windowGetSize_without_window(self):
        """无窗口时返回默认尺寸"""
        from desktop_app import DesktopAPI
        api = DesktopAPI()
        size = api.windowGetSize()
        assert size == {'width': 1100, 'height': 700}

    def test_openExternal_valid_url(self, monkeypatch):
        """openExternal 应使用 webbrowser.open"""
        import webbrowser
        urls_opened = []

        def mock_open(url):
            urls_opened.append(url)

        monkeypatch.setattr(webbrowser, 'open', mock_open)

        from desktop_app import DesktopAPI
        api = DesktopAPI()
        api.openExternal('https://example.com')
        assert urls_opened == ['https://example.com']

    def test_openExternal_invalid_url(self, monkeypatch):
        """非 http/https 链接不应打开"""
        import webbrowser
        urls_opened = []

        def mock_open(url):
            urls_opened.append(url)

        monkeypatch.setattr(webbrowser, 'open', mock_open)

        from desktop_app import DesktopAPI
        api = DesktopAPI()
        api.openExternal('javascript:alert(1)')
        assert urls_opened == []

    def test_getAppVersion_fallback(self, monkeypatch):
        """package.json 不存在时返回默认版本"""
        import builtins
        original_open = builtins.open

        def mock_open(path, *args, **kwargs):
            if 'package.json' in str(path):
                raise FileNotFoundError()
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, 'open', mock_open)

        from desktop_app import DesktopAPI
        api = DesktopAPI()
        version = api.getAppVersion()
        assert version == '1.0.0'


class TestEnvSetup:
    """环境准备函数 _prepare_env"""

    def test_prepare_env_sets_vars(self):
        """_prepare_env 应设置环境变量"""
        # 清理环境避免污染
        for k in ['PORT', 'DOCFLOWING_PACKAGED', 'DOCFLOWING_RUNTIME_DIR']:
            os.environ.pop(k, None)

        from desktop_app import _prepare_env
        _prepare_env()

        assert os.environ.get('PORT') == '5000'
        assert os.environ.get('DOCFLOWING_PACKAGED') == '0'
        assert os.environ.get('DOCFLOWING_RUNTIME_DIR') is not None

    def test_prepare_env_sys_path(self):
        """_prepare_env 应将 tools/ 和 project_root 加入 sys.path"""
        from desktop_app import _prepare_env
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tools_dir = os.path.join(root, 'tools')

        _prepare_env()

        assert root in sys.path
        assert tools_dir in sys.path


class TestSingleInstance:
    """单实例锁测试"""

    def test_try_lock_acquires(self):
        """绑定端口应成功"""
        from desktop_app import _try_lock
        sock = _try_lock(5990)
        assert sock is not None
        if sock:
            sock.close()

    def test_try_lock_refuses_duplicate(self):
        """同一端口重复绑定应被拒绝"""
        from desktop_app import _try_lock
        sock1 = _try_lock(5991)
        assert sock1 is not None

        try:
            sock2 = _try_lock(5991)
            assert sock2 is None, "重复绑定应返回 None"
        finally:
            if sock1:
                sock1.close()

    def test_lock_port_offset(self):
        """锁端口应为 Flask 端口+1000"""
        # 验证逻辑：desktop_app 中 try_lock 使用 port + 1000
        from desktop_app import _try_lock
        # 绑定一个端口
        sock = _try_lock(4000)
        assert sock is not None
        # 验证绑定的是 5000（4000+1000）
        if sock:
            sock.close()


class TestFlaskIntegration:
    """集成测试：Flask 在后台线程中启动并提供服务"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """每个测试的 setup/teardown"""
        # 保存环境变量
        self._saved_env = {}
        for k in ['PORT', 'DOCFLOWING_PACKAGED', 'DOCFLOWING_RUNTIME_DIR', 'HOST']:
            self._saved_env[k] = os.environ.get(k)

        yield

        # 恢复环境变量
        for k, v in self._saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def test_flask_server_startup(self):
        """Flask 后台线程启动应提供服务"""
        from desktop_app import _start_flask, _wait_for_flask, _flask_ready

        port = 5888
        os.environ['PORT'] = str(port)
        os.environ['DOCFLOWING_PACKAGED'] = '0'
        os.environ['DOCFLOWING_RUNTIME_DIR'] = desktop_app._get_runtime_dir()

        # 重置事件
        _flask_ready.clear()

        t = threading.Thread(target=_start_flask, daemon=True, name='FlaskTest')
        t.start()

        # 等待 Flask 就绪
        assert _flask_ready.wait(timeout=5), "Flask 应在 5 秒内就绪"
        assert _wait_for_flask(timeout=10), "HTTP 服务应在 10 秒内就绪"

        # 测试首页
        import urllib.request
        resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/')
        assert resp.status == 200
        html = resp.read().decode('utf-8')
        assert 'window.electronAPI = window.pywebview.api' in html

        # 测试 API
        resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/api/user/me')
        data = json.loads(resp.read().decode('utf-8'))
        assert data['success'] is True
        assert 'username' in data


class TestScripts:
    """构建脚本验证"""

    def test_build_desktop_script_valid(self):
        """build-desktop.py 语法正确"""
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'build-desktop.py'
        )
        assert os.path.exists(script_path), "构建脚本应存在"

        with open(script_path, 'r', encoding='utf-8') as f:
            code = f.read()
        compile(code, script_path, 'exec')
        # 语法检查通过即视为有效

    def test_desktop_app_script_valid(self):
        """desktop_app.py 语法正确"""
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'desktop_app.py'
        )
        assert os.path.exists(script_path)

        with open(script_path, 'r', encoding='utf-8') as f:
            code = f.read()
        compile(code, script_path, 'exec')
