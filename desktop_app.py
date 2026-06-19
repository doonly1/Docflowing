"""Docflowing 桌面应用入口 — pywebview

替换 Electron 桌面壳，内嵌 Flask 后端，使用 pywebview 渲染。
用法：
  python desktop_app.py              # 开发模式
  python desktop_app.py --portable   # 便携版模式（使用可执行文件所在目录作为数据目录）
"""

import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import webbrowser

# ==================== 配置 ====================

APP_NAME = '文澜'
DEFAULT_PORT = 5000
DEV_MODE = os.environ.get('DOCFLOWING_DEV') == '1'


def _get_root_dir():
    """获取项目根目录（资源文件定位用）。

    - 开发模式：desktop_app.py 所在目录。
    - PyInstaller 打包模式：优先使用 sys._MEIPASS（PyInstaller 解压到的临时目录，
      ui/、kb/fts_ext/、kb/skills/system/、tools/ 等资源均在此目录下），
      回退到 sys.executable 目录。
    """
    if getattr(sys, 'frozen', False):
        # contents_directory='.' 时，_MEIPASS 等于 exe 同级目录
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass and os.path.isdir(meipass):
            return meipass
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_runtime_dir():
    """获取运行时数据目录（配置、工作区等）"""
    is_packaged = getattr(sys, 'frozen', False) or os.environ.get('DOCFLOWING_PACKAGED') == '1'
    if '--portable' in sys.argv:
        # 便携版：数据目录在 exe 同级
        return os.path.join(_get_root_dir(), 'data')
    if is_packaged:
        # 打包模式：使用 %APPDATA%/Docflowing
        from appdirs import user_data_dir
        return user_data_dir(APP_NAME, 'Docflowing')
    # 开发模式：项目根下的 workspaces/
    return os.path.join(_get_root_dir(), 'workspaces')


# ==================== 单实例锁 ====================

def _try_lock(port):
    """通过绑定端口实现单实例锁"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port + 1000))  # 用 Flask 端口+1000 作为锁端口
        sock.listen(1)
        return sock
    except OSError:
        return None


def _signal_existing_instance(port):
    """通知已有实例显示窗口（通过 HTTP 请求触发）"""
    try:
        import urllib.request
        urllib.request.urlopen(f'http://127.0.0.1:{port}/__pywebview_show__', timeout=2)
    except Exception:
        pass


# ==================== Flask 后端管理 ====================

_flask_thread = None
_flask_ready = threading.Event()
_flask_app = None


def _prepare_env():
    """设置环境变量供 Flask app 使用"""
    # 确保路径
    root = _get_root_dir()
    tools_dir = os.path.join(root, 'tools')
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    if root not in sys.path:
        sys.path.insert(0, root)

    # 设置环境变量
    is_packaged = getattr(sys, 'frozen', False)
    os.environ.setdefault('PORT', str(DEFAULT_PORT))
    os.environ['DOCFLOWING_PACKAGED'] = '1' if is_packaged else '0'
    os.environ['DOCFLOWING_RUNTIME_DIR'] = _get_runtime_dir()


def _start_flask():
    """在后台线程中启动 Flask"""
    global _flask_app
    _prepare_env()

    from server import create_app
    _flask_app = create_app()

    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', DEFAULT_PORT))
    debug = os.environ.get('DEBUG', '0').lower() in ('1', 'true', 'yes')
    if debug:
        import warnings
        warnings.warn('[Docflowing] DEBUG 模式已启用，生产环境请勿使用！', UserWarning)

    # 添加一个隐藏端点用于显示窗口（由单实例锁激活）
    @_flask_app.route('/__pywebview_show__')
    def _pywebview_show():
        return 'ok'

    _flask_ready.set()
    print(f"[Desktop] Flask 服务启动 -> http://{host}:{port}")
    _flask_app.run(host=host, port=port, threaded=True, debug=debug)


# ==================== pywebview JS Bridge API ====================

class DesktopAPI:
    """暴露给前端 JS 的桌面 API（替换 Electron IPC）"""

    def __init__(self):
        self._window = None
        self._close_action = 'exit'  # 'exit' 或 'minimize'
        self._is_quitting = False
        self._is_maximized = False
        self._word_keep_alive_proc = None
        self._tray_icon = None

    def set_window(self, window):
        self._window = window
        # 监听最大化/恢复事件以更新状态
        window.events.maximized += lambda: setattr(self, '_is_maximized', True)
        window.events.restored += lambda: setattr(self, '_is_maximized', False)

    def set_tray_icon(self, icon):
        self._tray_icon = icon

    # ──── 窗口控制 ────

    def windowMinimize(self):
        if self._window:
            self._window.minimize()

    def windowToggleMaximize(self):
        if self._window:
            if self._is_maximized:
                self._window.restore()
            else:
                self._window.maximize()

    def windowClose(self):
        if not self._window:
            return
        if self._close_action == 'exit':
            self._is_quitting = True
            self._window.destroy()
        else:
            # 最小化到托盘
            self._window.hide()

    def windowIsMaximized(self):
        return self._is_maximized

    def windowShow(self):
        if self._window:
            self._window.show()

    # ──── 窗口位置/大小 ────

    def windowGetPosition(self):
        if self._window:
            return {'x': self._window.x, 'y': self._window.y}
        return {'x': 0, 'y': 0}

    def windowGetSize(self):
        if self._window:
            return {'width': self._window.width, 'height': self._window.height}
        return {'width': 1100, 'height': 700}

    def windowMove(self, x, y):
        if self._window:
            self._window.move(x, y)

    def windowResize(self, width, height):
        if self._window:
            self._window.resize(width, height)

    # ──── 原生对话框 ────

    def selectDirectory(self):
        """用 tkinter 打开文件夹选择对话框（绕过 edgechromium 缺少 create_file_dialog 的 bug）"""
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askdirectory()
        root.destroy()
        return path or ''

    def saveFileAs(self, suggested_name='文件'):
        """用 tkinter 打开文件保存对话框"""
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(initialfile=suggested_name or '文件')
        root.destroy()
        return path or ''

    # ──── Shell 操作 ────

    def openExternal(self, url):
        """用默认浏览器打开外部链接"""
        if isinstance(url, str) and (url.startswith('http://') or url.startswith('https://')):
            webbrowser.open(url)

    def openFileWithOsApp(self, absolute_path):
        """用 OS 默认软件打开文件"""
        try:
            if platform.system() == 'Windows':
                os.startfile(absolute_path)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', absolute_path])
            else:
                subprocess.Popen(['xdg-open', absolute_path])
            return {'success': True}
        except Exception as e:
            print(f'[Desktop] openFileWithOsApp error: {e}')
            return {'success': False, 'message': str(e)}

    def openFolder(self, absolute_path):
        """打开文件或文件夹所在的目录"""
        try:
            if not absolute_path:
                return {'success': False, 'message': '路径为空'}
            norm_path = os.path.normpath(absolute_path)
            target_dir = norm_path if os.path.isdir(norm_path) else os.path.dirname(norm_path)
            if not os.path.exists(target_dir):
                return {'success': False, 'message': '路径不存在: ' + target_dir}
            if platform.system() == 'Windows':
                os.startfile(target_dir)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', target_dir])
            else:
                subprocess.Popen(['xdg-open', target_dir])
            return {'success': True}
        except Exception as e:
            print(f'[Desktop] openFolder error: {e}')
            return {'success': False, 'message': str(e)}

    def showItemInFolder(self, absolute_path):
        """在文件管理器中选中并高亮文件"""
        try:
            if not absolute_path:
                return {'success': False, 'message': '路径为空'}
            norm_path = os.path.normpath(absolute_path)
            if not os.path.exists(norm_path):
                return {'success': False, 'message': '路径不存在: ' + norm_path}
            if platform.system() == 'Windows':
                # explorer 要求 /select, 和路径必须作为一个参数，否则无法高亮
                subprocess.Popen(['explorer', '/select,' + norm_path])
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', '-R', norm_path])
            else:
                subprocess.Popen(['xdg-open', os.path.dirname(norm_path)])
            return {'success': True}
        except Exception as e:
            print(f'[Desktop] showItemInFolder error: {e}')
            return {'success': False, 'message': str(e)}

    # ──── 应用信息 ────

    def getAppVersion(self):
        """获取应用版本"""
        root = _get_root_dir()
        pkg_json = os.path.join(root, 'package.json')
        try:
            with open(pkg_json, 'r', encoding='utf-8') as f:
                return json.load(f).get('version', '1.0.0')
        except Exception:
            return '1.0.0'

    # ──── 设置同步 ────

    def setCloseAction(self, action):
        """设置关闭行为（来自前端设置页面）"""
        if action in ('exit', 'minimize'):
            self._close_action = action

    def setWordKeepAlive(self, enabled):
        """控制 Word 保活脚本"""
        if platform.system() != 'Windows':
            return
        if enabled:
            self._start_word_keep_alive()
        else:
            self._stop_word_keep_alive()

    def _start_word_keep_alive(self):
        """启动 WordKeepAlive 脚本"""
        if self._word_keep_alive_proc:
            return
        script = os.path.join(_get_root_dir(), 'tools', 'WordKeepAlive.py')
        if not os.path.exists(script):
            return
        try:
            # 打包后 sys.executable 是 exe 文件，无法直接执行 Python 脚本
            # 需使用系统 python 命令
            if getattr(sys, 'frozen', False):
                python_exe = sys.executable  # 打包后的 exe 本身支持 --word-keepalive 参数
                cmd = [python_exe, '--word-keepalive', '--silent']
            else:
                cmd = [sys.executable, script, '--silent']
            self._word_keep_alive_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            )
            print('[Desktop] WordKeepAlive 已启动')
        except Exception as e:
            print(f'[Desktop] WordKeepAlive 启动失败: {e}')

    def _stop_word_keep_alive(self):
        """停止 WordKeepAlive 脚本"""
        if self._word_keep_alive_proc:
            try:
                self._word_keep_alive_proc.terminate()
                self._word_keep_alive_proc.wait(timeout=5)
            except Exception:
                try:
                    self._word_keep_alive_proc.kill()
                except Exception:
                    pass
            self._word_keep_alive_proc = None
        # 也尝试通过 --stop 参数停止
        script = os.path.join(_get_root_dir(), 'tools', 'WordKeepAlive.py')
        if os.path.exists(script):
            try:
                subprocess.Popen(
                    [sys.executable, script, '--stop'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
                )
            except Exception:
                pass

    # ──── 窗口状态监听（轮询替代事件） ────

    def getWindowState(self):
        """返回窗口状态，供前端轮询"""
        return {
            'maximized': self._is_maximized,
        }


# ==================== 系统托盘 ====================

def _create_tray(api, window):
    """创建系统托盘图标"""
    import pystray
    from PIL import Image

    icon_path = os.path.join(_get_root_dir(), 'ui', 'favicon.ico')
    if not os.path.exists(icon_path):
        # 用默认图标
        img = Image.new('RGBA', (16, 16), (233, 69, 96, 255))
    else:
        try:
            img = Image.open(icon_path)
            img = img.resize((16, 16), Image.LANCZOS)
        except Exception:
            img = Image.new('RGBA', (16, 16), (233, 69, 96, 255))

    def on_show(icon, item):
        if window:
            window.show()
            window.on_top = True
            window.on_top = False

    def on_exit(icon, item):
        api._is_quitting = True
        if window:
            window.destroy()

    menu = pystray.Menu(
        pystray.MenuItem(f'打开 {APP_NAME}', on_show, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('退出', on_exit),
    )

    icon = pystray.Icon(APP_NAME, img, APP_NAME, menu)
    api.set_tray_icon(icon)

    # pystray 需要在后台线程运行
    t = threading.Thread(target=icon.run, daemon=True, name='TrayIcon')
    t.start()
    return icon


# ==================== 窗口创建 ====================

def _enable_frameless_resize(window):
    """为 frameless 窗口添加 WS_THICKFRAME 并关闭 DWM NC 渲染，实现无白边缩放"""
    if platform.system() != 'Windows':
        return

    # 守卫：无论成败只执行一次
    if getattr(_enable_frameless_resize, '_done', False):
        return

    import ctypes

    # ──── 获取 HWND ────
    hwnd = None
    for attempt in range(3):  # 重试 3 次，应对窗口尚未完全创建的情况
        gui = getattr(window, 'gui', None)
        if gui and hasattr(gui, 'hwnd'):
            hwnd = gui.hwnd
        if not hwnd:
            hwnd = ctypes.windll.user32.FindWindowW(None, APP_NAME)
        if hwnd:
            break
        time.sleep(0.3)

    if not hwnd:
        print('[Desktop] 无法获取窗口句柄，跳过边缘缩放')
        return

    # 标记 done 在 HWND 确认后立刻置位，避免多线程反复尝试
    _enable_frameless_resize._done = True

    # ──── 添加 WS_THICKFRAME 启用缩放 ────
    GWL_STYLE = -16
    WS_THICKFRAME = 0x00040000
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
    if not (style & WS_THICKFRAME):
        style |= WS_THICKFRAME
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                          0x0001 | 0x0002 | 0x0020)

    # ──── 关闭 DWM 非客户区渲染（消除 1px 白边）───
    try:
        hwnd_int = ctypes.c_int64(hwnd) if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_int32(hwnd)
        DWMWA_NCRENDERING_POLICY = 2
        DWMNCRP_DISABLED = 2
        policy = ctypes.c_int(DWMNCRP_DISABLED)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd_int, DWMWA_NCRENDERING_POLICY,
            ctypes.byref(policy), ctypes.sizeof(policy)
        )
    except Exception as e:
        print(f'[Desktop] DWM NC 渲染关闭失败（不影响缩放）: {e}')

    print('[Desktop] 已启用窗口边缘缩放（WS_THICKFRAME + DWMNCRP_DISABLED）')


def _wait_for_flask(timeout=30):
    """轮询等待 Flask 就绪"""
    port = int(os.environ.get('PORT', DEFAULT_PORT))
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/api/user/me', timeout=1)
            if resp.status < 400:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def run_word_keepalive():
    """运行 WordKeepAlive 功能（打包后通过 --word-keepalive 参数调用）"""
    # 动态导入 WordKeepAlive 模块
    root = _get_root_dir()
    tools_dir = os.path.join(root, 'tools')
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        from WordKeepAlive import main as wka_main
        wka_main()
    except ImportError as e:
        print(f'[Desktop] 无法加载 WordKeepAlive: {e}')
        sys.exit(1)


def main():
    # ──── 参数处理 ────
    if '--word-keepalive' in sys.argv:
        run_word_keepalive()
        return

    # ──── 单实例锁 ────
    port = int(os.environ.get('PORT', DEFAULT_PORT))
    lock_sock = _try_lock(port)
    if lock_sock is None:
        print('[Desktop] 已有实例运行，激活已有窗口')
        _signal_existing_instance(port)
        return

    # ──── 启动 Flask ────
    flask_thread = threading.Thread(target=_start_flask, daemon=True, name='Flask')
    flask_thread.start()
    _flask_ready.wait(timeout=5)

    if not _wait_for_flask():
        print('[Desktop] Flask 启动失败')
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('启动失败', '后端服务启动超时，请重试')
        root.destroy()
        return

    # ──── 创建 pywebview 窗口 ────
    import webview

    # 补充 edgechromium 后端缺失的 create_file_dialog（对话框用）
    import webview.platforms.edgechromium as _edge
    from webview.platforms.winforms import create_file_dialog as _wfd
    _edge.EdgeChrome.create_file_dialog = lambda self, dt, d, am, sf, ft, uid: _wfd(dt, d, am, sf, ft, uid)

    # 创建窗口前算好居中坐标，直接传给 create_window（WinForms 用 Manual 定位）
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
    _sw = _root.winfo_screenwidth()
    _sh = _root.winfo_screenheight()
    _root.destroy()
    _cx = max(0, (_sw - 1100) // 2)
    _cy = max(0, (_sh - 700) // 2)

    api = DesktopAPI()
    window = webview.create_window(
        APP_NAME,
        url=f'http://127.0.0.1:{port}',
        width=1100,
        height=700,
        x=_cx, y=_cy,          # 预计算居中坐标，WinForms 用 Manual 模式定位
        min_size=(800, 500),
        frameless=True,
        easy_drag=False,       # 关闭全局拖拽，避免吃点击事件
        draggable=True,        # 启用 CSS class 限定区域拖拽
        text_select=True,      # 允许文本选择（默认 False 会注入 user-select: none）
        js_api=api,
    )
    api.set_window(window)

    # ──── 窗口事件 ────

    # loaded 事件触发时启用边缘缩放（此时窗口已存在）
    window.events.loaded += lambda: _enable_frameless_resize(window)

    # 后台线程兜底（loaded 可能早于 getgui.hwnd 就绪）
    threading.Thread(
        target=lambda: (
            time.sleep(1.5),
            _enable_frameless_resize(window),
        ),
        daemon=True, name='EnableFramelessResize'
    ).start()
    window.events.closing += lambda: _on_closing(api)

    # ──── 系统托盘 ────
    tray_icon = _create_tray(api, window)

    # 启动 WordKeepAlive（默认启用）
    api._start_word_keep_alive()

    # ──── 主循环 ────
    webview.start(
        gui='edgechromium',  # 使用 Edge WebView2（Windows 10+ 内置，无需额外安装）
        http_server=False,   # 我们用 Flask 做 HTTP 服务器
    )

    # ──── 清理 ────
    _cleanup(api, lock_sock)


def _on_closing(api):
    """窗口关闭时触发（同步事件，返回 False 可阻止关闭）"""
    if api._is_quitting:
        return  # 允许关闭
    # 非退出状态：阻止关闭，改为隐藏到托盘
    if api._close_action == 'minimize' and api._window:
        api._window.hide()
        return False


def _cleanup(api, lock_sock):
    """清理资源"""
    print('[Desktop] 正在清理...')
    api._stop_word_keep_alive()
    if api._tray_icon:
        try:
            api._tray_icon.stop()
        except Exception:
            pass
    # 关闭 Flask
    if _flask_app:
        try:
            _flask_app.do_teardown_appcontext()
        except Exception:
            pass
    # 释放锁端口
    if lock_sock:
        try:
            lock_sock.close()
        except Exception:
            pass
    print('[Desktop] 已退出')


if __name__ == '__main__':
    main()
