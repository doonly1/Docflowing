"""
Docflowing 桌面应用构建脚本（pywebview 版本）
用法: python electron/build-desktop.py

使用 PyInstaller 将 desktop_app.py 打包为单个 exe，
包含 pywebview 桌面壳 + Flask 后端 + 前端 UI。
"""
import os
import sys
import shutil
import subprocess

# 强制 stdout/stderr 使用 UTF-8 编码（修复 CI 环境 cp1252 编码问题）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_NAME = os.path.join(ROOT, 'electron', 'desktop.spec')
DIST_DIR = os.path.join(ROOT, 'dist', 'desktop')
OUTPUT_NAME = '文澜'


def create_spec():
    """生成 PyInstaller .spec 文件（onedir 模式）"""
    ui_dir = os.path.join(ROOT, 'ui')

    spec = f"""# -*- mode: python ; coding: utf-8 -*-
import sys
sys.setrecursionlimit(10000)

a = Analysis(
    [r'{ROOT}/desktop_app.py'],
    pathex=[r'{ROOT}', r'{ROOT}/tools'],
    binaries=[],
    datas=[
        # 前端 UI 文件
        (r'{ui_dir}', 'ui'),
    ],
    hiddenimports=[
        # KB 模块
        'kb.auto_extract',
        'kb.config',
        'kb.context_compressor',
        'kb.context_fence',
        'kb.database',
        'kb.file_lock',
        'kb.file_safety',
        'kb.insights',
        'kb.llm',
        'kb.memory',
        'kb.models',
        'kb.routes',
        'kb.routes_session',
        'kb.routes_memory',
        'kb.routes_insights',
        'kb.routes_skills',
        'kb.search',
        'kb.session_db',
        'kb.sync_converters',
        'kb.sync_worker',
        'kb.tools',
        'kb.skills',
        'kb.skills.manager',
        'kb.skills.curator',
        'kb.skills.usage',
        # FB 模块
        'fb.models',
        'fb.routes',
        # P2P 模块
        'p2p.node',
        'p2p.discovery',
        'p2p.auth',
        'p2p.api',
        'p2p.models',
        'p2p.proxy',
        # Server 模块
        'server.auth',
        'server.middleware',
        'server.runner',
        'server.settings',
        'server.workspace',
        # pywebview 及其依赖
        'webview',
        # Tools
        'logging_config',
        'doc_process',
        'mystyle',
        'to_compare',
        'to_docx',
        'to_redhead',
        'to_index',
        'to_pageNum',
        'to_pdf',
        'float_picture',
        'load_config',
        # 第三方隐式依赖
        'flask',
        'flask_cors',
        'zeroconf',
        'yaml',
        'cryptography',
        'requests',
        'pdfplumber',
        'beautifulsoup4',
        'markitdown',
        'openpyxl',
        'docx',
        'pptx',
        'pystray',
        'PIL',
        'PIL._tkinter_finder',
        'appdirs',
        'cefpython3',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'pdb',
        'test',
        'setuptools',
        'pip',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'matplotlib',
        'scipy',
        'notebook',
        'jupyter',
        'IPython',
        'numpy.testing',
        'pandas',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='{OUTPUT_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',
)

# onedir 模式（保持目录结构便于调试）
# 如果需要单文件模式，将 EXE 改为 COLLECT + EXE with onefile=True
"""
    with open(SPEC_NAME, 'w', encoding='utf-8') as f:
        f.write(spec)
    print(f'[build-desktop] OK 已生成 spec 文件: {SPEC_NAME}')


def clean():
    """清理旧的构建输出"""
    for d in [DIST_DIR, os.path.join(ROOT, 'build')]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f'[build-desktop] OK 已清理: {d}')


def build():
    """执行 PyInstaller 构建"""
    create_spec()
    clean()

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        '--distpath', os.path.join(ROOT, 'dist'),
        '--workpath', os.path.join(ROOT, 'build', 'pyi-build'),
        SPEC_NAME,
    ]

    print('[build-desktop] ... 开始构建桌面应用 ...')
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')

    if result.returncode != 0:
        print('[build-desktop] ERROR 构建失败:')
        print(result.stderr[-3000:] if len(result.stderr) > 3000 else result.stderr)
        sys.exit(1)

    exe_path = os.path.join(ROOT, 'dist', f'{OUTPUT_NAME}.exe')
    if os.path.exists(exe_path):
        print(f'[build-desktop] OK 构建成功: {exe_path}')
    else:
        # onedir 模式
        dir_path = os.path.join(ROOT, 'dist', OUTPUT_NAME)
        if os.path.isdir(dir_path):
            print(f'[build-desktop] OK 构建成功: {dir_path}')
        else:
            print('[build-desktop] WARNING 输出文件未找到，请检查 dist/ 目录')

    print('[build-desktop] 完成')


if __name__ == '__main__':
    build()
