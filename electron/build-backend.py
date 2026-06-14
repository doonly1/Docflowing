"""
DocFlow Python 后端构建脚本
用法: python electron/build-backend.py

使用 PyInstaller 将 app_server.py 打包为 dist/backend/backend.exe
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
DIST_DIR = os.path.join(ROOT, 'dist', 'backend')
SPEC_NAME = os.path.join(ROOT, 'electron', 'backend.spec')


def create_spec():
    """生成 PyInstaller .spec 文件"""
    spec = f"""# -*- mode: python ; coding: utf-8 -*-
import sys
sys.setrecursionlimit(10000)

a = Analysis(
    [r'{ROOT}/app_server.py'],
    pathex=[r'{ROOT}'],
    binaries=[],
    datas=[],
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
        # Tools（在 app_server.py 中通过 sys.path 引入）
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
        # 第三方
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
        'PIL',
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
    name='backend',
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
"""
    # 设置环境变量避免 GBK 编码问题
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

    with open(SPEC_NAME, 'w', encoding='utf-8') as f:
        f.write(spec)
    print(f'[build-backend] OK 已生成 spec 文件: {SPEC_NAME}')


def clean():
    """清理旧的构建输出"""
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
        print(f'[build-backend] OK 已清理: {DIST_DIR}')

    build_dir = os.path.join(ROOT, 'build')
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
        print(f'[build-backend] OK 已清理: {build_dir}')


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

    print('[build-backend] ... 开始构建 Python 后端 ...')
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')

    if result.returncode != 0:
        print('[build-backend] ERROR 构建失败:')
        print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        sys.exit(1)

    # 创建 dist/backend/ 目录并将 exe 移入（匹配 electron-builder extraResources 配置）
    built_exe = os.path.join(ROOT, 'dist', 'backend.exe')
    if os.path.exists(built_exe):
        os.makedirs(DIST_DIR, exist_ok=True)
        shutil.move(built_exe, os.path.join(DIST_DIR, 'backend.exe'))
        print(f'[build-backend] OK 已移动 exe 到: {DIST_DIR}')

    print(f'[build-backend] OK 构建成功: {DIST_DIR}')
    print(f'[build-backend] => {os.path.join(DIST_DIR, "backend.exe")}')


if __name__ == '__main__':
    build()
