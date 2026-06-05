"""DocFlow 桌面版入口 — pywebview 壳（已废弃）

注意：此文件已迁移至 Electron，请使用 npm run dev 启动。
保留此文件仅用于回退参考，未来版本将删除。
启动 Flask 后台线程 + 原生桌面窗口
开机自启管理由 settings API 通过 Windows 注册表完成
"""
import os
import sys
import time
import threading
import subprocess
import urllib.request

from tools.logging_config import get_logger

logger = get_logger(__name__)


def _run_startup_scripts():
    """启动时运行工具脚本"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tools_dir = os.path.join(base_dir, 'tools')

    scripts = [
        # ('fetch_github_hosts.py', False),  # 一次性任务（已禁用）
    ]

    # WordKeepAlive 仅 Windows 可用
    if sys.platform == 'win32':
        scripts.append(('WordKeepAlive.py', True))

    for script_name, is_daemon in scripts:
        script_path = os.path.join(tools_dir, script_name)
        if not os.path.exists(script_path):
            continue
        try:
            if is_daemon:
                # 守护进程：静默后台运行
                subprocess.Popen(
                    [sys.executable, script_path, '--silent'],
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # 一次性任务：静默运行
                subprocess.Popen([sys.executable, script_path, '--silent'], shell=True)
            logger.info("%s 已启动", script_name)
        except Exception as e:
            logger.warning("%s 启动失败: %s", script_name, e)


def _wait_for_server(url: str, timeout: float = 10.0) -> bool:
    """等待 Flask 服务就绪"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


class JsBridge:
    """JS Bridge: 暴露给前端调用的原生 API"""

    def __init__(self):
        self._window = None
        self._maximized = False  # 跟踪最大化状态

    def _get_window(self):
        if self._window is None:
            import webview
            self._window = webview.active_window()
        return self._window

    def selectDirectory(self):
        """弹出 Windows 原生目录选择对话框"""
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askdirectory(title='选择文件夹')
        root.destroy()
        return path or ''

    def saveFileAs(self, suggested_name):
        """弹出 Windows 原生文件保存对话框，返回用户选择的路径（取消返回空字符串）"""
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(
            title='另存为',
            initialfile=suggested_name or '文件',
            defaultextension=''
        )
        root.destroy()
        return path or ''

    def windowMinimize(self):
        """最小化窗口"""
        try:
            w = self._get_window()
            if w:
                w.minimize()
                return True
        except Exception as e:
            logger.warning("windowMinimize error: %s", e)
        return False

    def windowMaximize(self):
        """最大化窗口"""
        try:
            w = self._get_window()
            if w:
                w.maximize()
                self._maximized = True
                return True
        except Exception as e:
            logger.warning("windowMaximize error: %s", e)
        return False

    def windowRestore(self):
        """恢复窗口"""
        try:
            w = self._get_window()
            if w:
                w.restore()
                self._maximized = False
                return True
        except Exception as e:
            logger.warning("windowRestore error: %s", e)
        return False

    def windowToggleMaximize(self):
        """切换最大化/还原状态"""
        try:
            w = self._get_window()
            if w:
                if self._maximized:
                    w.restore()
                    self._maximized = False
                else:
                    w.maximize()
                    self._maximized = True
                return True
        except Exception as e:
            logger.warning("windowToggleMaximize error: %s", e)
        return False

    def windowIsMaximized(self):
        """返回窗口是否最大化"""
        return self._maximized

    def windowGetPosition(self):
        """返回窗口位置 {x, y}"""
        try:
            w = self._get_window()
            if w:
                state = w.get_state()
                return {
                    'x': int(state.get('x') or 0),
                    'y': int(state.get('y') or 0)
                }
        except Exception as e:
            logger.warning("windowGetPosition error: %s", e)
        return {'x': 0, 'y': 0}

    def windowGetSize(self):
        """返回窗口大小 {width, height}"""
        try:
            w = self._get_window()
            if w:
                state = w.get_state()
                return {
                    'width': int(state.get('width') or 1100),
                    'height': int(state.get('height') or 700)
                }
        except Exception as e:
            logger.warning("windowGetSize error: %s", e)
        return {'width': 1100, 'height': 700}

    def windowMove(self, x, y):
        """移动窗口到指定位置"""
        try:
            if x is None or y is None:
                return False
            w = self._get_window()
            if w:
                w.move(int(x), int(y))
                return True
        except Exception as e:
            logger.warning("windowMove error: %s", e)
        return False

    def windowResize(self, width, height):
        """调整窗口大小"""
        try:
            if width is None or height is None:
                return False
            w = self._get_window()
            if w:
                w.resize(int(width), int(height))
                return True
        except Exception as e:
            logger.warning("windowResize error: %s", e)
        return False

    def windowClose(self):
        """关闭窗口"""
        try:
            w = self._get_window()
            if w:
                w.destroy()
                return True
        except Exception as e:
            logger.warning("windowClose error: %s", e)
        return False


# ==================== 主入口 ====================

def main():
    port = int(os.environ.get('PORT', 5000))

    # 运行启动脚本
    _run_startup_scripts()

    # 启动 Flask 后台线程
    from server import create_app
    flask_app = create_app()

    def _run_flask():
        flask_app.run(host='127.0.0.1', port=port, threaded=True, debug=False, use_reloader=False)

    t = threading.Thread(target=_run_flask, daemon=True, name='flask-thread')
    t.start()

    server_url = f'http://127.0.0.1:{port}'
    if not _wait_for_server(server_url):
        logger.error("Flask 服务启动失败")
        print("错误：Flask 服务启动超时")
        sys.exit(1)

    logger.info("Flask 服务已就绪: %s", server_url)

    import webview

    # 计算屏幕居中位置
    win_w, win_h = 1100, 700
    try:
        import ctypes
        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        win_x = (screen_w - win_w) // 2
        win_y = (screen_h - win_h) // 2
    except Exception:
        win_x = win_y = None

    # 图标路径（相对于脚本所在目录）
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui', 'favicon.ico')

    kwargs = {
        'title': '文枢',
        'url': server_url,
        'width': win_w,
        'height': win_h,
        'min_size': (800, 500),
        'resizable': True,
        'frameless': True,
        'easy_drag': False,
        'js_api': JsBridge(),
    }
    if win_x is not None:
        kwargs['x'] = win_x
        kwargs['y'] = win_y

    webview.create_window(**kwargs)
    webview.start(debug=False, http_server=False, icon=icon_path)


if __name__ == '__main__':
    main()
