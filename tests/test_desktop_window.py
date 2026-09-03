# -*- coding: utf-8 -*-
"""测试 desktop_window 的后端策略分支。

这些测试全部不需要真实 GUI —— 用桩模块替换 webview，只验证
「不同后端 + 不同标题栏策略」下传给 pywebview 的参数是否正确。
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


@pytest.fixture
def no_native_calls(monkeypatch):
    """屏蔽真正碰 Win32 / WinUI 的函数，但记录它们是否被调用。

    install_winui3_title_bar 的替身仍会往 before_show 挂一个空钩子，
    这样上层断言才看得到「确实注册了标题栏」这件事。

    frameless_resize 键恒为空：WS_THICKFRAME 缩放补丁已整体移除，
    保留它只为让旧断言（== []）表达「从未触发任何缩放补丁」。
    """
    calls = {'title_bar': [], 'frameless_resize': []}

    def _install(window, title):
        calls['title_bar'].append(title)
        window.events.before_show += lambda *_a: None

    monkeypatch.setattr(dw, 'install_winui3_title_bar', _install)
    return calls


class TestTitleBarResolution:
    def test_winui3_defaults_to_custom(self):
        assert dw.resolve_title_bar_mode('winui3', None) == dw.TITLE_BAR_CUSTOM

    def test_non_winui3_defaults_to_native(self):
        """非 winui3 后端默认用原生标题栏（frameless=False）。

        之前默认 frameless：自绘 header 的窗口按钮调 Electron IPC，
        在 pywebview 下是死的，缩放还得靠 WS_THICKFRAME hack（现也已移除）。
        """
        assert dw.resolve_title_bar_mode('edgechromium', None) == dw.TITLE_BAR_NATIVE
        assert dw.resolve_title_bar_mode('winforms', None) == dw.TITLE_BAR_NATIVE

    def test_explicit_mode_wins(self):
        assert dw.resolve_title_bar_mode('winui3', 'frameless') == 'frameless'

    def test_env_var_respected(self, monkeypatch):
        monkeypatch.setenv('DOCFLOWING_TITLEBAR', 'native')
        assert dw.resolve_title_bar_mode('winui3', None) == 'native'


class TestCreateWindow:
    def test_winui3_custom_keeps_border(self, fake_webview, no_native_calls):
        """winui3 + custom 绝不能传 frameless=True，否则丢掉缩放和吸附。"""
        window = dw.create_window('App', 'http://x', backend='winui3')

        assert fake_webview['kwargs']['frameless'] is False
        assert no_native_calls['title_bar'] == ['App']
        assert len(window.handlers['before_show']) == 1

    def test_edgechromium_defaults_to_native_title_bar(self, fake_webview, no_native_calls):
        """默认策略下非 winui3 后端必须 frameless=False，缩放/吸附交给系统。"""
        dw.create_window('App', 'http://x', backend='edgechromium')
        assert fake_webview['kwargs']['frameless'] is False
        assert no_native_calls['frameless_resize'] == []

    def test_forced_frameless_is_borderless_escape_hatch(
        self, fake_webview, no_native_calls, caplog
    ):
        """显式强制 frameless：无边框逃生门，不再补 WS_THICKFRAME。

        旧实现会给 HWND 补 WS_THICKFRAME 提供缩放抓手，但 Win10 下
        DWM 会残留单侧黑边（左缘 1px 线），已整体移除。
        逃生门只保证显示与拖动，不支持系统缩放。
        """
        import logging

        with caplog.at_level(logging.WARNING, logger='docflowing.desktop_window'):
            dw.create_window(
                'App', 'http://x', backend='edgechromium', title_bar='frameless'
            )

        assert fake_webview['kwargs']['frameless'] is True
        # 不再挂 enable_frameless_resize（loaded 事件 + 后台线程都不该有）
        assert no_native_calls['frameless_resize'] == []
        assert any('不支持系统缩放' in r.message for r in caplog.records)

    def test_custom_on_non_winui3_degrades_to_native(self, fake_webview, no_native_calls):
        """custom 仅 winui3 支持；其他后端应退化为原生标题栏而非 frameless。"""
        dw.create_window('App', 'http://x', backend='winforms', title_bar='custom')
        assert fake_webview['kwargs']['frameless'] is False
        assert no_native_calls['title_bar'] == []
        assert no_native_calls['frameless_resize'] == []

    def test_drag_settings_preserved(self, fake_webview, no_native_calls):
        """easy_drag 必须关掉，否则会吃掉页面里的点击。"""
        dw.create_window('App', 'http://x', backend='edgechromium')

        kwargs = fake_webview['kwargs']
        assert kwargs['easy_drag'] is False
        assert kwargs['draggable'] is True
        assert kwargs['text_select'] is True

    def test_min_size_forwarded(self, fake_webview, no_native_calls):
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
    def test_invalid_forced_backend_ignored(self, monkeypatch):
        """'win32' 不是合法 gui 值，应被忽略而不是静默退回。"""
        monkeypatch.setenv('DOCFLOWING_GUI', 'win32')
        monkeypatch.setattr(dw, '_VALID_BACKENDS', ('winforms',))

        def fake_import(name, *a, **k):
            if name.endswith('winforms'):
                return types.ModuleType(name)
            raise ImportError(name)

        monkeypatch.setattr('builtins.__import__', fake_import)
        assert dw.detect_backend() == 'winforms'

    def test_returns_none_when_nothing_available(self, monkeypatch):
        monkeypatch.setattr(dw, '_VALID_BACKENDS', ('winui3',))

        def fake_import(name, *a, **k):
            raise ImportError(name)

        monkeypatch.setattr('builtins.__import__', fake_import)
        assert dw.detect_backend() is None

    def test_local_runtime_below_binding_requirement(self):
        """本机是 App Runtime 1.5，winui3 绑定要 1.7 —— 应判为不满足。"""
        versions = dw._installed_app_runtime_versions()
        if not versions:
            pytest.skip('本机未安装 Windows App Runtime，跳过版本比对')
        assert max(versions)[0] < 7000
