"""子进程入口 —— 重型文件转换（独立进程，独立 GIL，不阻塞主进程）"""

import sys
import os
import json
import time


if __name__ == '__main__':
    source_path = sys.argv[1]
    relative_path = sys.argv[2]
    source_mtime = float(sys.argv[3])

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    from kb.sync_converters import convert_file

    try:
        md_content = convert_file(source_path, relative_path, "")
        if md_content:
            result = (relative_path, source_mtime, 'synced', None, time.time(), md_content)
        else:
            result = (relative_path, source_mtime, 'failed', 'conversion_failed', None, None)
    except Exception as e:
        result = (relative_path, source_mtime, 'failed', str(e), None, None)

    print(json.dumps(result))