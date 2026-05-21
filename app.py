# -*- coding: utf-8 -*-
"""
后端服务入口
"""
import os
import sys
import socket
from server import create_app

app = create_app()


def _get_startup_dir():
    return os.path.join(
        os.environ.get('APPDATA', ''),
        r'Microsoft\Windows\Start Menu\Programs\Startup'
    )


def _get_startup_vbs_path():
    return os.path.join(_get_startup_dir(), 'docproc.vbs')


def install_startup():
    startup_dir = _get_startup_dir()
    if not os.path.isdir(startup_dir):
        print("错误：找不到 Windows 启动文件夹")
        return False

    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(script_dir, 'app.py')
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


def get_local_ip():
    """获取本机局域网 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    if '--install-startup' in sys.argv:
        install_startup()
        sys.exit(0)
    if '--remove-startup' in sys.argv:
        remove_startup()
        sys.exit(0)

    import webbrowser
    from logging_config import get_logger

    logger = get_logger(__name__)
    port = int(os.environ.get('PORT', 5000))
    local_ip = get_local_ip()

    logger.info("=" * 60)
    logger.info("文档处理服务")
    logger.info("本机访问: http://localhost:%s", port)
    logger.info("IP 访问: http://%s:%s", local_ip, port)
    logger.info("=" * 60)

    # 本地运行时打开浏览器（使用 IP 地址）
    if port == 5000:
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            webbrowser.open(f'http://{local_ip}:{port}')

    app.run(host='0.0.0.0', port=port, debug=(port == 5000), threaded=True)
