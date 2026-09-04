"""Docflowing 桌面窗口层 —— pywebview 后端选择与窗口创建。

设计
----
不再使用 winui3 自绘标题栏，也放弃 frameless（自绘 header + 窗口按钮调的是
Electron IPC，pywebview 下是死的，无边框还会丢系统缩放和吸附）。统一走
**系统原生标题栏**：缩放、Aero Snap、最小化/最大化/关闭全部交给系统，
前端不再依赖任何 Electron 窗口 IPC。

后端固定默认用 edgechromium（依赖系统 WebView2）。若本机缺 WebView2 或
edgechromium 后端加载失败，可用环境变量 DOCFLOWING_GUI=winforms 手动降级
（winforms 仅作逃生门，若 WebView2 不可用至少能出界面）。

环境变量
--------
DOCFLOWING_GUI=edgechromium|winforms   强制后端，缺省自动探测（edgechromium → winforms）
"""

from __future__ import annotations

import logging
import os
import platform
import sys

logger = logging.getLogger('docflowing.desktop_window')

# 合法的 pywebview GUI 名称。注意 'win32' 不是合法的 gui 值 —— 传给
# webview.start() 会被静默忽略并退回 winforms，所以这里不列它。
_VALID_BACKENDS = ('edgechromium', 'winforms')


# ==================== 后端探测 ====================

def detect_backend() -> str | None:
    """探测可用的 pywebview 后端，按 edgechromium → winforms 顺序。"""
    if platform.system() != 'Windows':
        return None

    forced = os.environ.get('DOCFLOWING_GUI', '').strip().lower()
    if forced and forced not in _VALID_BACKENDS:
        logger.warning('DOCFLOWING_GUI=%r 不是合法后端，忽略', forced)
        forced = ''

    candidates = [forced] if forced else list(_VALID_BACKENDS)

    for name in candidates:
        try:
            __import__('webview.platforms.' + name)
        except Exception as e:
            logger.debug('后端 %s 不可用：%s', name, e)
            continue
        return name

    return None


# ==================== min_size 兜底 ====================

def enforce_min_size(window, min_size: tuple[int, int]) -> None:
    """用 resized 事件夹住窗口最小尺寸。

    edgechromium 原生支持 min_size；这里统一兜底，兼容 winforms 后端，
    保证任何后端下窗口都不会被拖到比 min_size 更小。
    """
    min_w, min_h = int(min_size[0]), int(min_size[1])
    if min_w <= 0 and min_h <= 0:
        return

    state = {'busy': False}

    def _clamp(*_args) -> None:
        if state['busy']:
            return
        try:
            w, h = window.width, window.height
        except Exception:
            return

        new_w, new_h = max(w, min_w), max(h, min_h)
        if (new_w, new_h) == (w, h):
            return

        state['busy'] = True
        try:
            window.resize(new_w, new_h)
        except Exception as e:
            logger.debug('min_size 夹紧失败：%s', e)
        finally:
            state['busy'] = False

    window.events.resized += _clamp


# ==================== 对外入口 ====================

def create_window(
    title: str,
    url: str | None = None,
    *,
    backend: str,
    html: str | None = None,
    width: int = 1100,
    height: int = 700,
    x: int | None = None,
    y: int | None = None,
    min_size: tuple[int, int] = (0, 0),
    js_api=None,
    **kwargs,
):
    """创建 pywebview 窗口，统一走系统原生标题栏。"""
    import webview

    window = webview.create_window(
        title,
        url=url,
        html=html,
        width=width,
        height=height,
        x=x,
        y=y,
        min_size=min_size,
        # 原生标题栏：缩放、Aero Snap、最小化/最大化/关闭交给系统
        frameless=False,
        # 全局 easy_drag 会吃掉页面里的点击，关闭
        easy_drag=False,
        text_select=True,
        js_api=js_api,
        # 显式指定窗口背景色与 HTML body 同色（#f2f2f2），
        # 避免 pywebview 默认 #FFFFFF 在 WebView 边缘亚像素留白处
        # 露出形成细白边。允许调用方通过 kwargs 覆盖（如果传了）。
        background_color=kwargs.pop('background_color', '#f2f2f2'),
        **kwargs,
    )

    enforce_min_size(window, min_size)

    return window


def start(backend: str, **kwargs) -> None:
    """启动 GUI 主循环。"""
    import webview

    kwargs.setdefault('http_server', False)
    webview.start(gui=backend, **kwargs)


def describe(backend: str) -> str:
    """返回一行人类可读的运行配置，便于打日志/排障。"""
    return (
        f'pywebview 后端={backend}，标题栏策略=原生（系统标题栏）'
        f'（Python {sys.version.split()[0]}，{platform.platform()}）'
    )