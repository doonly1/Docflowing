"""DocFlow 桌面版入口 — pywebview 壳

启动 Flask 后台线程 + 原生桌面窗口
支持：系统托盘、开机自启、Owner 签名认证

认证方式：Python 启动时预先生成 Owner Token，通过 evaluate_js 注入前端
无需 JS bridge 参与初始登录，消除 bridge 注入时机问题
"""
import os
import sys
import time
import threading
import urllib.request

from tools.logging_config import get_logger

logger = get_logger(__name__)


def _get_startup_dir():
    return os.path.join(
        os.environ.get('APPDATA', ''),
        r'Microsoft\Windows\Start Menu\Programs\Startup'
    )


def _get_startup_vbs_path():
    return os.path.join(_get_startup_dir(), 'docflow-desktop.vbs')


def install_startup():
    startup_dir = _get_startup_dir()
    if not os.path.isdir(startup_dir):
        print("错误：找不到 Windows 启动文件夹")
        return False

    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(script_dir, 'app_desktop.py')
    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if not os.path.isfile(pythonw):
        pythonw = sys.executable

    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "{pythonw}" "{app_path}", 0, False
'''

    vbs_path = _get_startup_vbs_path()
    with open(vbs_path, 'w', encoding='utf-8') as f:
        f.write(vbs_content)

    print(f"已安装开机自启 -> {vbs_path}")
    return True


def remove_startup():
    vbs_path = _get_startup_vbs_path()
    if os.path.isfile(vbs_path):
        os.remove(vbs_path)
        print(f"已移除开机自启: {vbs_path}")
        return True
    print("未找到开机自启配置")
    return False


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
    }
    if win_x is not None:
        kwargs['x'] = win_x
        kwargs['y'] = win_y

    webview.create_window(**kwargs)
    webview.start(debug=False, http_server=False)


if __name__ == '__main__':
    if '--install-startup' in sys.argv:
        install_startup()
        sys.exit(0)
    if '--remove-startup' in sys.argv:
        remove_startup()
        sys.exit(0)

    main()