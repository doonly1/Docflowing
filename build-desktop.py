"""
Docflowing 桌面应用构建脚本（pywebview 版本）
用法: python build-desktop.py

使用 PyInstaller 将 desktop_app.py 打包为 onedir 目录，
包含 pywebview 桌面壳 + Flask 后端 + 前端 UI + FTS5 扩展 + 系统技能。
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

ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC_NAME = os.path.join(ROOT, 'build.spec')
DIST_DIR = os.path.join(ROOT, 'dist', 'desktop')
OUTPUT_NAME = '文澜'


def create_spec():
    """生成 PyInstaller .spec 文件（onedir 模式，contents_directory='.'）

    关键修复点（与之前版本对比）：
      - 入口改为 desktop_app.py（桌面壳 + Flask 后端一体）
      - datas 补齐 ui/、kb/fts_ext/、kb/skills/system/、tools/
      - binaries 加入 simple.{dll,so,dylib}，让 sqlite3.load_extension 可以找到
      - hiddenimports 去掉不存在的 kb.tools、cefpython3，
        补上 kb.agent_tools / kb.user_tools / kb.interrupt /
        kb.sync_state / kb.sync_subprocess 等隐式引用
      - excludes 不再排除 tkinter（desktop_app.py 的文件对话框依赖）
    """
    ui_dir = os.path.join(ROOT, 'ui')
    fts_ext_dir = os.path.join(ROOT, 'kb', 'fts_ext')
    skills_system_dir = os.path.join(ROOT, 'kb', 'skills', 'system')
    skills_init = os.path.join(ROOT, 'kb', 'skills', '__init__.py')
    tools_dir = os.path.join(ROOT, 'tools')

    # 确保系统技能目录存在，避免 PyInstaller 因目录不存在报错
    if not os.path.exists(skills_system_dir):
        os.makedirs(skills_system_dir, exist_ok=True)
    if not os.path.exists(skills_init):
        with open(skills_init, 'w', encoding='utf-8') as f:
            f.write("# 自动生成：保证 kb.skills 被识别为 Python 包\n")

    # 组装 datas 元组（仅将真实存在的目录打进来，避免失败）
    datas = []
    if os.path.isdir(ui_dir):
        datas.append(f"    (r'{ui_dir}', 'ui'),")
    if os.path.isdir(skills_system_dir):
        datas.append(
            f"    (r'{skills_system_dir}', 'kb/skills/system'),"
        )
    if os.path.isdir(tools_dir):
        datas.append(f"    (r'{tools_dir}', 'tools'),")
    # FTS5 扩展放在 datas 中，便于 kb/session_db.py 按 _MEIPASS/kb/fts_ext/simple.dll 读取
    if os.path.isdir(fts_ext_dir):
        datas.append(f"    (r'{fts_ext_dir}', 'kb/fts_ext'),")
    datas_str = "\n".join(datas) if datas else "    # 暂无额外资源"

    spec = f"""# -*- mode: python ; coding: utf-8 -*-
import sys
sys.setrecursionlimit(10000)

a = Analysis(
    [r'{ROOT}/desktop_app.py'],
    pathex=[r'{ROOT}'],
    binaries=[],
    datas=[
{datas_str}
    ],
    hiddenimports=[
        # ========== KB 模块 ==========
        'kb',
        'kb.auto_extract',
        'kb.config',
        'kb.context_compressor',
        'kb.context_fence',
        'kb.database',
        'kb.file_lock',
        'kb.file_safety',
        'kb.insights',
        'kb.interrupt',
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
        'kb.sync_state',
        'kb.sync_subprocess',
        'kb.sync_worker',
        'kb.user_tools',
        'kb.agent_tools',
        'kb.skills',
        'kb.skills.manager',
        'kb.skills.curator',
        'kb.skills.usage',
        # ========== FB 模块 ==========
        'fb',
        'fb.models',
        'fb.routes',
        'fb.routes_base',
        'fb.routes_files',
        'fb.routes_files_edit',
        'fb.routes_files_ops',
        'fb.routes_locks',
        'fb.routes_p2p',
        'fb.routes_search',
        'fb.routes_sync',
        'fb.routes_tools',
        'fb.routes_trash',
        'fb.database',
        'fb.decorators',
        # ========== P2P 模块 ==========
        'p2p',
        'p2p.node',
        'p2p.discovery',
        'p2p.auth',
        'p2p.api',
        'p2p.models',
        'p2p.proxy',
        # ========== Server 模块 ==========
        'server',
        'server.auth',
        'server.middleware',
        'server.runner',
        'server.settings',
        'server.workspace',
        # ========== pywebview（edgechromium 后端） ==========
        'webview',
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'webview.platforms.windows',
        # ========== Tools（Python 模块形式引入） ==========
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
        'tool_defs',
        'WordKeepAlive',
        # ========== 第三方隐式依赖 ==========
        'flask',
        'flask_cors',
        'zeroconf',
        'yaml',
        'cryptography',
        'requests',
        'pdfplumber',
        'bs4',
        'beautifulsoup4',
        'markitdown',
        'openpyxl',
        'docx',
        'pptx',
        'pystray',
        'PIL',
        'PIL._tkinter_finder',
        'PIL.Image',
        'PIL.ImageTk',
        'appdirs',
        'packaging',
        # ========== Windows 可选依赖（COM + Word） ==========
        'win32com',
        'pythoncom',
        'win32api',
        'win32con',
        'win32gui',
        'pywintypes',
        'docx2pdf',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        # 注意：不排除 tkinter —— desktop_app.py 的文件选择/保存对话框依赖它
        'unittest',
        'pdb',
        'test',
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
        'cefpython3',
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

# onedir 模式（保持目录结构便于调试 + 资源文件按原生路径读写）
# 若要切换为单文件模式，将 EXE 改为 COLLECT + 独立 EXE(onefile=True)。
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
