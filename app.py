# -*- coding: utf-8 -*-
"""
公文处理工具后端服务 —— 入口
"""
import os
import socket
from server import create_app

app = create_app()

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
