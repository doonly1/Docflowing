"""Docflowing 桌面窗口层 —— pywebview 后端选择与无边框策略封装。

背景
----
官方 pywebview 在 Windows 上只有 winforms / edgechromium 两个后端，frameless
窗口没有系统缩放边框。早前靠给 HWND 补 WS_THICKFRAME 提供缩放抓手，但该做法
在 Win10 下会残留单侧黑边（DWM 非客户区渲染被禁后仍画出 1px 边框线，且无法
可靠消除），已移除 —— frameless 现仅作显示逃生门，不承诺系统缩放。

pywebview-winui3 分支（F:\\download\\Tools\\pywebview-winui3）新增了 winui3
后端，修好了 frameless 的几个具体问题：

  * 拖拽移动（XAML 下 ReleaseCapture + WM_NCLBUTTONDOWN 失效，改用
    WH_MOUSE_LL 全局钩子 + SetWindowPos）
  * 拖拽容差（5px，避免点击被误判成拖拽）
  * HiDPI 坐标（PhysicalToLogicalPointForPerMonitorDPI 换算）
  * 滚轮事件（XAML 会吞 WM_MOUSEWHEEL，钩子转发到 Chrome_WidgetWin_0）
  * WS_EX_APPWINDOW（frameless 后窗口从任务栏/自动化枚举中消失）

但仍有两个缺口，本模块负责补上：

  * 无边框缩放 —— winui3 的 set_border_and_title_bar(False, False) 不提供
    任何 resize 抓手。改用「自定义标题栏」策略：内容延伸到标题栏区域，
    保留系统边框、Aero Snap 和最小化/最大化/关闭按钮。
  * min_size —— winui3 后端未实现（源码 winui3.py:560 留了 TODO），
    这里用 resized 事件兜底夹一次。

设计原则：**默认走系统原生标题栏**。winui3 可用时用 XAML 自绘标题栏（保留
系统边框）；其余后端（edgechromium / winforms）默认 frameless=False，缩放、
Aero Snap、最小化/最大化/关闭全部交给系统 —— 前端自绘 header 里那组 Electron
IPC 窗口按钮在 pywebview 下是死的，别依赖它们。显式强制 frameless（逃生门）
时也不补 WS_THICKFRAME —— 窗口无系统缩放，仅保证能显示与拖动。

环境变量
--------
DOCFLOWING_GUI=winui3|edgechromium|winforms      强制后端，缺省自动探测
DOCFLOWING_TITLEBAR=custom|frameless|native      标题栏策略，缺省按后端自动选

用法（desktop_app.py 中）
------------------------
    from desktop_window import detect_backend, create_window, start

    backend = detect_backend()
    window = create_window(APP_NAME, url, backend=backend, ...)
    start(backend)
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import sys

logger = logging.getLogger('docflowing.desktop_window')

# 合法的 pywebview GUI 名称。注意 'win32' 不是合法的 gui 值 —— 传给
# webview.start() 会被静默忽略并退回 winforms，所以这里不列它。
_VALID_BACKENDS = ('winui3', 'edgechromium', 'winforms')

# 标题栏策略
TITLE_BAR_CUSTOM = 'custom'      # XAML 自绘标题栏，保留系统边框与缩放（仅 winui3）
TITLE_BAR_FRAMELESS = 'frameless'  # frameless=True，无系统边框
TITLE_BAR_NATIVE = 'native'      # 完全交给系统


# ==================== 后端探测 ====================

def _installed_app_runtime_versions() -> list[tuple[int, ...]]:
    """列出本机已安装的 Windows App Runtime 版本（四段式元组）。

    Windows App Runtime 以 MSIX 框架包形式并存安装，同时查两个来源：
    %ProgramFiles%\\WindowsApps 目录名 与 包仓库注册表。任一不可读就跳过。
    """
    versions: list[tuple[int, ...]] = []
    arch = 'x64' if ctypes.sizeof(ctypes.c_void_p) == 8 else 'x86'

    def _add(raw: str) -> None:
        try:
            versions.append(tuple(int(p) for p in raw.split('.')))
        except ValueError:
            pass

    windowsapps = os.path.join(
        os.environ.get('ProgramFiles', r'C:\Program Files'), 'WindowsApps'
    )
    try:
        for name in os.listdir(windowsapps):
            # 形如 Microsoft.WindowsAppRuntime.1.5_5001.373.1736.0_x64__8wekyb3d8bbwe
            if not name.startswith('Microsoft.WindowsAppRuntime.'):
                continue
            parts = name.split('_')
            if len(parts) < 3 or parts[2] != arch:
                continue
            _add(parts[1])
    except OSError:
        pass

    try:
        import winreg

        path = (
            r'SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows'
            r'\CurrentVersion\AppModel\PackageRepository\Packages'
        )
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                    i += 1
                except OSError:
                    break
                if 'WindowsAppRuntime' not in name:
                    continue
                parts = name.split('_')
                if len(parts) < 3 or parts[2] != arch:
                    continue
                _add(parts[1])
    except Exception:
        pass

    return versions


def _winui3_runtime_satisfied() -> tuple[bool, str]:
    """判断本机的 Windows App Runtime 是否满足 winui3 绑定要求。

    绑定在 import 时就把要求的版本编进了扩展模块（RELEASE_VERSION /
    RUNTIME_VERSION）。若不满足，winui3.setup_app() 里的
    initialize(options=ON_NO_MATCH_SHOW_UI) 会弹下载界面 —— 对桌面应用
    是不可接受的，所以这里提前探测并降级。
    """
    try:
        from winui3 import (
            _winui3_microsoft_windows_applicationmodel_dynamicdependency_bootstrap as b,
        )

        need = tuple(int(p) for p in b.RUNTIME_VERSION.split('.'))
        want_release = b.RELEASE_VERSION
    except Exception as e:
        return False, f'无法读取 winui3 绑定的 SDK 版本要求: {e}'

    installed = _installed_app_runtime_versions()
    if not installed:
        return False, (
            f'未安装 Windows App Runtime；winui3 绑定需要 Windows App SDK {want_release} '
            f'(运行时 >= {b.RUNTIME_VERSION})。'
            f'可安装 https://aka.ms/windowsappsdk/{want_release}/latest/windowsappruntimeinstall-x64.exe'
        )

    best = max(installed)
    if best < need:
        return False, (
            f'已装 Windows App Runtime {".".join(map(str, best))}，'
            f'低于 winui3 绑定要求的 {b.RUNTIME_VERSION} (SDK {want_release})'
        )

    return True, f'Windows App Runtime {".".join(map(str, best))} 满足 SDK {want_release}'


def detect_backend() -> str | None:
    """探测可用的 pywebview 后端，按 winui3 → edgechromium → winforms 顺序。"""
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

        if name == 'winui3':
            ok, msg = _winui3_runtime_satisfied()
            if not ok:
                logger.warning('跳过 winui3 后端：%s', msg)
                continue
            logger.info('winui3 后端可用：%s', msg)

        return name

    return None


# ==================== min_size 兜底 ====================

def enforce_min_size(window, min_size: tuple[int, int]) -> None:
    """用 resized 事件夹住窗口最小尺寸。

    winui3 后端未实现 min_size（源码 TODO），其他后端原生支持，这里统一兜底。
    注意两处坑：

    1. winui3 的 resized 事件上报的是**物理像素**（on_resize 直接透传
       args.size），而 window.width / window.height 走 get_size() 返回
       **逻辑像素**。所以回调里不信任事件参数，重新读 window.width/height。
    2. 在 resized 回调里 resize 会再次触发 resized，需要重入保护。
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


# ==================== winui3 自定义标题栏 ====================

_TITLE_BAR_XAML = """\
<Grid
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    Name="DocflowingTitleBar">
    <Grid.ColumnDefinitions>
        <ColumnDefinition Width="0"/>
        <ColumnDefinition Width="*"/>
    </Grid.ColumnDefinitions>
    <TextBlock
        Grid.Column="1"
        Name="TitleText"
        VerticalAlignment="Center"
        Margin="16,0,0,0"
        FontSize="12"
        Opacity="0.75"/>
</Grid>
"""

_TITLE_ROW_XAML = (
    '<RowDefinition'
    ' xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"'
    ' Height="Auto"/>'
)


def install_winui3_title_bar(window, title: str) -> None:
    """在 winui3 窗口上装自定义标题栏（保留系统边框、缩放与吸附）。

    与 frameless=True 的区别：frameless 会连边框一起去掉，于是失去缩放抓手
    和 Aero Snap；这里改用 extends_content_into_title_bar，让 XAML 内容铺满
    标题栏区域，但保留系统边框 —— 缩放、吸附布局、最小化/最大化/关闭按钮
    全部照常工作。

    参考 examples/custom_title_bar.py 与
    https://learn.microsoft.com/en-us/windows/apps/develop/title-bar
    """
    def on_before_show(win) -> None:
        from winui3.microsoft.ui.xaml import GridLength, GridUnitType
        from winui3.microsoft.ui.xaml.controls import Grid, RowDefinition, TextBlock
        from winui3.microsoft.ui.xaml.markup import XamlReader

        native = win.native

        # 1. 去掉系统标题栏那一横条，让 XAML 内容顶到窗口顶部
        native.extends_content_into_title_bar = True

        # 2. 在根 Grid 顶部插一行。pywebview 建的根 Grid 原本是：
        #      Row 0 - Auto - MenuBar（默认折叠）
        #      Row 1 - *    - WebView2
        #    插入后它们变成 Row 1 / Row 2。
        root = native.content.as_(Grid)
        root.row_definitions.insert_at(
            0, XamlReader.load(_TITLE_ROW_XAML).as_(RowDefinition)
        )
        for child in root.children:
            Grid.set_row(child, Grid.get_row(child) + 1)

        # 3. 建标题栏、放进 Row 0、挂到可视树
        title_bar = XamlReader.load(_TITLE_BAR_XAML).as_(Grid)
        Grid.set_row(title_bar, 0)
        Grid.set_column_span(title_bar, 2)
        root.children.append(title_bar)
        title_text = title_bar.find_name('TitleText').as_(TextBlock)
        title_text.text = title

        # 4. 注册为拖拽区域 —— 必须在挂进可视树之后，否则 WinUI 3 不认
        native.set_title_bar(title_bar)

        # 5. 首次布局后，按系统 caption 按钮的左右内缩对齐，并按当前 DPI
        #    取整到整数逻辑像素，避免文字发虚。
        def on_loaded(sender, _args):
            tb = sender.as_(Grid)
            scale = tb.xaml_root.rasterization_scale
            logical_height = round(native.app_window.title_bar.height / scale)
            tb.height = logical_height
            root.row_definitions[0].height = GridLength(
                logical_height, GridUnitType.PIXEL
            )
            tb.column_definitions[0].width = GridLength(
                round(native.app_window.title_bar.left_inset / scale),
                GridUnitType.PIXEL,
            )

        title_bar.add_loaded(on_loaded)

    window.events.before_show += on_before_show


# ==================== 对外入口 ====================

def resolve_title_bar_mode(backend: str, requested: str | None) -> str:
    """把 'auto'/None 解析成具体策略。"""
    mode = (requested or os.environ.get('DOCFLOWING_TITLEBAR') or 'auto').lower()
    if mode != 'auto':
        return mode
    # winui3 用自定义标题栏（保住缩放和吸附），其余后端用原生标题栏
    # （frameless 下那组窗口按钮调 Electron IPC，在 pywebview 里是死的）
    return TITLE_BAR_CUSTOM if backend == 'winui3' else TITLE_BAR_NATIVE


def create_window(
    title: str,
    url: str,
    *,
    backend: str,
    width: int = 1100,
    height: int = 700,
    x: int | None = None,
    y: int | None = None,
    min_size: tuple[int, int] = (0, 0),
    title_bar: str | None = None,
    js_api=None,
    **kwargs,
):
    """创建 pywebview 窗口并套上对应后端的无边框策略。"""
    import webview

    mode = resolve_title_bar_mode(backend, title_bar)
    frameless = mode == TITLE_BAR_FRAMELESS

    window = webview.create_window(
        title,
        url=url,
        width=width,
        height=height,
        x=x,
        y=y,
        min_size=min_size,
        frameless=frameless,
        # 全局 easy_drag 会吃掉页面里的点击，只用 CSS class 限定区域
        easy_drag=False,
        draggable=True,
        text_select=True,
        js_api=js_api,
        # 显式指定窗口背景色与 HTML body 同色（#f2f2f2），
        # 避免 pywebview 默认 #FFFFFF 在 WebView 边缘亚像素留白处
        # 露出形成细白边。允许调用方通过 kwargs 覆盖（如果传了）。
        background_color=kwargs.pop('background_color', '#f2f2f2'),
        **kwargs,
    )

    if mode == TITLE_BAR_CUSTOM:
        if backend == 'winui3':
            install_winui3_title_bar(window, title)
        else:
            logger.warning(
                'custom 标题栏策略仅 winui3 支持，当前后端 %s 退化为原生标题栏', backend
            )

    if frameless:
        # frameless 逃生门：无系统边框，也就没有系统缩放抓手。早前的
        # WS_THICKFRAME 补丁在 Win10 下残留单侧黑边（见模块 docstring），
        # 已移除。窗口仍可拖动（header 拖动区由服务端在逃生门模式注入），
        # 需要完整缩放请走默认 native 或 winui3 custom。
        logger.warning(
            'frameless 逃生门窗口不支持系统缩放（无边框即无缩放抓手）；'
            '如需缩放请去掉 DOCFLOWING_TITLEBAR=frameless，改用默认原生标题栏。'
        )

    # winui3 不实现 min_size，其余后端原生支持；统一兜底不冲突
    enforce_min_size(window, min_size)

    return window


def start(backend: str, **kwargs) -> None:
    """启动 GUI 主循环。"""
    import webview

    kwargs.setdefault('http_server', False)
    webview.start(gui=backend, **kwargs)


def describe(backend: str, title_bar: str | None = None) -> str:
    """返回一行人类可读的运行配置，便于打日志/排障。"""
    mode = resolve_title_bar_mode(backend, title_bar)
    return (
        f'pywebview 后端={backend}，标题栏策略={mode}'
        f'（Python {sys.version.split()[0]}，{platform.platform()}）'
    )
