# -*- coding: utf-8 -*-
"""测试 desktop_window 的后端选择与窗口创建。

这些测试全部不需要真实 GUI —— 用桩模块替换 webview，只验证
「不同后端」下传给 pywebview 的参数是否正确。
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import desktop_window as dw  # noqa: E402

_EVENT_NAMES = ('resized', 'loaded', 'before_show')


class _Hook:
    """模拟 pywebview 的 Event —— 支持 += / -= 注册。"""

    def __init__(self, handlers):
        self.handlers = handlers

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def __isub__(self, fn):
        if fn in self.handlers:
            self.handlers.remove(fn)
        return self

    def fire(self, *args):
        for fn in list(self.handlers):
            fn(*args)


class FakeWindow:
    def __init__(self):
        self.width = 1100
        self.height = 700
        self.resized_calls = []
        self.handlers = {name: [] for name in _EVENT_NAMES}
        self.events = types.SimpleNamespace(
            **{name: _Hook(h) for name, h in self.handlers.items()}
        )

    def resize(self, w, h):
        self.resized_calls.append((w, h))
        self.width, self.height = w, h


@pytest.fixture
def fake_webview(monkeypatch):
    """把 webview 换成桩，记录 create_window / start 收到的参数。"""
    captured = {'kwargs': None, 'window': None, 'start': None}

    fake = types.ModuleType('webview')

    def create_window(title, **kwargs):
        captured['kwargs'] = kwargs
        captured['window'] = FakeWindow()
        return captured['window']

    def start(**kwargs):
        captured['start'] = kwargs

    fake.create_window = create_window
    fake.start = start
    monkeypatch.setitem(sys.modules, 'webview', fake)
    return captured


class TestCreateWindow:
    def test_edgechromium_uses_native_title_bar(self, fake_webview):
        """edgechromium 后端必须用系统原生标题栏（frameless=False）。"""
        dw.create_window('App', 'http://x', backend='edgechromium')

        kwargs = fake_webview['kwargs']
        assert kwargs['frameless'] is False

    def test_winforms_uses_native_title_bar(self, fake_webview):
        """winforms 逃生门同样走原生标题栏（frameless=False）。"""
        dw.create_window('App', 'http://x', backend='winforms')

        kwargs = fake_webview['kwargs']
        assert kwargs['frameless'] is False

    def test_drag_settings_preserved(self, fake_webview):
        """easy_drag 必须关掉，否则会吃掉页面里的点击。"""
        dw.create_window('App', 'http://x', backend='edgechromium')

        kwargs = fake_webview['kwargs']
        assert kwargs['easy_drag'] is False
        assert kwargs['text_select'] is True

    def test_min_size_forwarded(self, fake_webview):
        dw.create_window(
            'App', 'http://x', backend='edgechromium', min_size=(800, 500)
        )
        assert fake_webview['kwargs']['min_size'] == (800, 500)


class TestMinSize:
    def test_clamps_below_minimum(self):
        window = FakeWindow()
        dw.enforce_min_size(window, (800, 500))

        window.width, window.height = 600, 400
        window.events.resized.fire(600, 400)

        assert window.resized_calls == [(800, 500)]

    def test_noop_when_above_minimum(self):
        window = FakeWindow()
        dw.enforce_min_size(window, (800, 500))

        window.width, window.height = 1200, 900
        window.events.resized.fire(1200, 900)

        assert window.resized_calls == []

    def test_reentrancy_guard(self):
        """回调里 resize 会再次触发 resized，必须防重入。

        用一个只回弹一次的钩子模拟真实的「resize 引发 resized」，
        验证最终只发生一次夹紧。
        """
        window = FakeWindow()
        dw.enforce_min_size(window, (800, 500))
        window.width, window.height = 600, 400

        bounced = []

        def bounce(*_a):
            if not bounced:
                bounced.append(1)
                window.events.resized.fire(600, 400)

        window.events.resized += bounce
        window.events.resized.fire(600, 400)

        assert window.resized_calls == [(800, 500)]
        assert bounced == [1]


class TestBackendDetection:
    def test_fixed_backend(self, monkeypatch, fake_webview):
        """默认固定 edgechromium。"""
        monkeypatch.setattr(dw, '_VALID_BACKENDS', ('edgechromium',))

        def fake_import(name, *a, **k):
            if name.endswith('edgechromium'):
                return types.ModuleType(name)
            raise ImportError(name)

        monkeypatch.setattr('builtins.__import__', fake_import)
        assert dw.detect_backend() == 'edgechromium'

    def test_invalid_forced_backend_ignored(self, monkeypatch):
        """'win32' 不是合法 gui 值，应被忽略而不是静默退回。"""
        monkeypatch.setenv('DOCFLOWING_GUI', 'win32')
        monkeypatch.setattr(dw, '_VALID_BACKENDS', ('edgechromium',))

        def fake_import(name, *a, **k):
            if name.endswith('edgechromium'):
                return types.ModuleType(name)
            raise ImportError(name)

        monkeypatch.setattr('builtins.__import__', fake_import)
        assert dw.detect_backend() == 'edgechromium'

    def test_forced_winforms_when_edgechromium_missing(self, monkeypatch):
        """缺 WebView2 时可用 DOCFLOWING_GUI=winforms 手动降级。"""
        monkeypatch.setenv('DOCFLOWING_GUI', 'winforms')
        monkeypatch.setattr(dw, '_VALID_BACKENDS', ('edgechromium', 'winforms'))

        def fake_import(name, *a, **k):
            if name.endswith('winforms'):
                return types.ModuleType(name)
            raise ImportError(name)

        monkeypatch.setattr('builtins.__import__', fake_import)
        assert dw.detect_backend() == 'winforms'

    def test_returns_none_when_nothing_available(self, monkeypatch):
        monkeypatch.setattr(dw, '_VALID_BACKENDS', ('edgechromium',))

        def fake_import(name, *a, **k):
            raise ImportError(name)

        monkeypatch.setattr('builtins.__import__', fake_import)
        assert dw.detect_backend() is None


class TestDescribe:
    def test_describe_reports_backend(self):
        s = dw.describe('edgechromium')
        assert 'edgechromium' in s
        assert '原生' in s