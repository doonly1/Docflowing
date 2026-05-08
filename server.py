# -*- coding: utf-8 -*-
"""
公文处理工具后端服务 —— 入口
"""
import os
from server import create_app

app = create_app()

if __name__ == '__main__':
    import webbrowser
    from logging_config import get_logger

    logger = get_logger(__name__)
    port = int(os.environ.get('PORT', 5000))

    logger.info("=" * 50)
    logger.info("文档处理服务")
    logger.info("访问地址: http://0.0.0.0:%s", port)
    logger.info("=" * 50)

    # 本地运行时打开浏览器
    if port == 5000:
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            webbrowser.open(f'http://localhost:{port}')

    app.run(host='0.0.0.0', port=port, debug=(port == 5000), threaded=True)
