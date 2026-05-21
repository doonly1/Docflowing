"""DocProc 桌面版入口 — pywebview 壳

启动 Flask 后台线程 + 原生桌面窗口
支持：系统托盘、开机自启、Owner 签名认证
"""
import os
import sys
import time
import socket
import threading

from logging_config import get_logger

logger = get_logger(__name__)


def _get_startup_dir():
    return os.path.join(
        os.environ.get('APPDATA', ''),
        r'Microsoft\Windows\Start Menu\Programs\Startup'
    )


def _get_startup_vbs_path():
    return os.path.join(_get_startup_dir(), 'docproc-desktop.vbs')


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
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


# ==================== JS Bridge ====================

class DesktopBridge:
    """pywebview JS bridge — 暴露给前端调用的 Python 方法"""

    def sign(self, data: str) -> str:
        from p2p.node import NodeIdentity
        node = NodeIdentity()
        node.load_or_create()
        sig = node.sign(data.encode('utf-8'))
        return sig

    def get_node_id(self) -> str:
        from p2p.node import NodeIdentity
        node = NodeIdentity()
        node.load_or_create()
        return node.node_id

    def get_display_name(self) -> str:
        from p2p.node import NodeIdentity
        node = NodeIdentity()
        node.load_or_create()
        return node.display_name

    def get_app_port(self) -> int:
        return int(os.environ.get('PORT', 5000))


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

    bridge = DesktopBridge()

    window = webview.create_window(
        title='文枢 — 文档处理工具集',
        url=server_url,
        js_api=bridge,
        width=1280,
        height=800,
        min_size=(900, 600),
        resizable=True,
        easy_drag=False,
    )

    webview.start(debug=False, http_server=False)


if __name__ == '__main__':
    if '--install-startup' in sys.argv:
        install_startup()
        sys.exit(0)
    if '--remove-startup' in sys.argv:
        remove_startup()
        sys.exit(0)

    main()