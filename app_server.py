"""DocFlow 服务端入口 — gunicorn / Flask 双模式

用法：
  # 生产（推荐 gunicorn）
  gunicorn -w 1 -b 127.0.0.1:5000 app_server:app

  # 开发 / 调试
  python app_server.py
"""

import os
import sys

# 强制 stdout/stderr 使用 UTF-8，避免中文日志乱码
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# 确保路径与 server/__init__.py 一致
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(project_root, 'tools'))
sys.path.insert(0, project_root)

from server import create_app

app = create_app()

if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', '').lower() in ('1', 'true', 'yes')

    print(f"DocFlow 服务启动 -> http://{host}:{port}")
    app.run(host=host, port=port, threaded=True, debug=debug)