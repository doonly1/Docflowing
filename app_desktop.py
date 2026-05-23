"""DocFlow 桌面版入口 — pywebview 壳

启动 Flask 后台线程 + 原生桌面窗口
开机自启管理由 settings API 通过 Windows 注册表完成
"""
import os
import sys
import time
import threading
import urllib.request

from tools.logging_config import get_logger

logger = get_logger(__name__)


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


# ==================== 主入口 ====================

def main():
    port = int(os.environ.get('PORT', 5000))

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

    kwargs = {
        'title': '文枢',
        'url': server_url,
        'width': win_w,
        'height': win_h,
        'min_size': (800, 500),
        'resizable': True,
        'easy_drag': False,
        'js_api': JsBridge(),
    }
    if win_x is not None:
        kwargs['x'] = win_x
        kwargs['y'] = win_y

    webview.create_window(**kwargs)
    webview.start(debug=False, http_server=False)


if __name__ == '__main__':
    main()
