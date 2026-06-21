"""
Docflowing 桌面应用构建脚本（pywebview 版本）
用法:
  python build-desktop.py              # onedir 模式（默认，资源在 exe 同级目录）
  python build-desktop.py --onefile    # 单文件模式（全部嵌入 exe）
  python build-desktop.py --installer  # 打包后生成 NSIS 安装包（需要 NSIS 环境）

使用 PyInstaller 将 desktop_app.py 打包，
包含 pywebview 桌面壳 + Flask 后端 + 前端 UI + FTS5 扩展 + 系统技能。
"""
import argparse
import os
import shutil
import subprocess
import sys

# 强制 stdout/stderr 使用 UTF-8 编码（修复 CI 环境 cp1252 编码问题）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC_NAME = os.path.join(ROOT, 'build.spec')
OUTPUT_NAME = 'Docflowing'
WORK_DIR = os.path.join(ROOT, 'build', 'pyi-build')


def _ensure_skills_init():
    """确保 kb/skills/__init__.py 存在"""
    skills_init = os.path.join(ROOT, 'kb', 'skills', '__init__.py')
    if not os.path.exists(skills_init):
        os.makedirs(os.path.dirname(skills_init), exist_ok=True)
        with open(skills_init, 'w', encoding='utf-8') as f:
            f.write("# 自动生成：保证 kb.skills 被识别为 Python 包\n")


def _datas_lines():
    """组装 datas 元组列表"""
    lines = []
    mapping = {
        os.path.join(ROOT, 'ui'):                'ui',
        os.path.join(ROOT, 'kb', 'skills', 'system'): 'kb/skills/system',
        os.path.join(ROOT, 'tools'):             'tools',
        os.path.join(ROOT, 'kb', 'fts_ext'):     'kb/fts_ext',
    }
    for src, dst in mapping.items():
        if os.path.isdir(src):
            lines.append(f"    (r'{src}', '{dst}'),")
    return '\n'.join(lines) if lines else "    # 暂无额外资源"


_HIDDEN_IMPORTS = [
    # ========== KB 模块 ==========
    'kb', 'kb.auto_extract', 'kb.config', 'kb.context_compressor',
    'kb.context_fence', 'kb.database', 'kb.file_lock', 'kb.file_safety',
    'kb.insights', 'kb.interrupt', 'kb.llm', 'kb.memory', 'kb.models',
    'kb.routes', 'kb.routes_session', 'kb.routes_memory', 'kb.routes_insights',
    'kb.routes_skills', 'kb.search', 'kb.session_db', 'kb.sync_converters',
    'kb.sync_state', 'kb.sync_subprocess', 'kb.sync_worker', 'kb.user_tools',
    'kb.agent_tools', 'kb.skills', 'kb.skills.manager', 'kb.skills.curator',
    'kb.skills.usage',
    # ========== FB 模块 ==========
    'fb', 'fb.models', 'fb.routes', 'fb.routes_base', 'fb.routes_files',
    'fb.routes_files_edit', 'fb.routes_files_ops', 'fb.routes_locks',
    'fb.routes_p2p', 'fb.routes_search', 'fb.routes_sync', 'fb.routes_tools',
    'fb.routes_trash', 'fb.database', 'fb.decorators',
    # ========== P2P 模块 ==========
    'p2p', 'p2p.node', 'p2p.discovery', 'p2p.auth', 'p2p.api', 'p2p.models',
    'p2p.proxy',
    # ========== Server 模块 ==========
    'server', 'server.auth', 'server.middleware', 'server.runner',
    'server.settings', 'server.workspace', 'server.tool_runner',
    # ========== pywebview（edgechromium 后端） ==========
    'webview', 'webview.platforms.edgechromium',
    'webview.platforms.winforms', 'webview.platforms.windows',
    # ========== Tools（Python 模块形式引入） ==========
    'logging_config', 'doc_process', 'mystyle', 'to_compare', 'to_docx',
    'to_redhead', 'to_index', 'to_pageNum', 'to_pdf', 'float_picture',
    'load_config', 'tool_defs', 'WordKeepAlive',
    # ========== 第三方隐式依赖 ==========
    'flask', 'flask_cors', 'zeroconf', 'yaml', 'cryptography', 'requests',
    'pdfplumber', 'bs4', 'beautifulsoup4', 'markitdown', 'openpyxl',
    'docx', 'pptx', 'pystray', 'PIL', 'PIL._tkinter_finder', 'PIL.Image',
    'PIL.ImageTk', 'packaging',
    # ========== Windows 可选依赖（COM + Word） ==========
    'win32com', 'pythoncom', 'win32api', 'win32con', 'win32gui',
    'pywintypes', 'docx2pdf',
]

_EXCLUDES = [
    'unittest', 'pdb', 'test', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    'matplotlib', 'scipy', 'notebook', 'jupyter', 'IPython', 'numpy.testing',
    'pandas', 'cefpython3',
]


def _common_analysis() -> str:
    """生成 Analysis 块（onedir / onefile 共用）"""
    datas = _datas_lines()
    hidden = '\n'.join(f"        '{m}'," for m in _HIDDEN_IMPORTS)
    excludes = '\n'.join(f"        '{m}'," for m in _EXCLUDES)
    return f"""a = Analysis(
    [r'{ROOT}/desktop_app.py'],
    pathex=[r'{ROOT}'],
    binaries=[],
    datas=[
{datas}
    ],
    hiddenimports=[
{hidden}
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
{excludes}
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)
"""


ICON_PATH = os.path.join(ROOT, 'ui', 'favicon.ico')


def _exe_block() -> str:
    """EXE 块（onedir / onefile 共用配置，不含 COLLECT）"""
    icon_line = f"    icon=r'{ICON_PATH}'," if os.path.isfile(ICON_PATH) else ""
    return f"""exe = EXE(
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
{icon_line}
    contents_directory='.',
    onefile=False,
)
"""


def create_onedir_spec():
    """生成 onedir 模式的 spec（COLLECT 收集全部文件到目录）"""
    _ensure_skills_init()
    spec = (
        '# -*- mode: python ; coding: utf-8 -*-\n'
        'import sys\n'
        'sys.setrecursionlimit(10000)\n\n'
        + _common_analysis()
        + _exe_block()
        + f"""coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{OUTPUT_NAME}',
)
"""
    )
    with open(SPEC_NAME, 'w', encoding='utf-8') as f:
        f.write(spec)
    print(f'[build-desktop] OK 已生成 onedir spec: {SPEC_NAME}')


def create_onefile_spec():
    """生成 onefile 模式的 spec（全部嵌入 exe，运行时解压到临时目录）"""
    _ensure_skills_init()
    icon_line = f"    icon=r'{ICON_PATH}'," if os.path.isfile(ICON_PATH) else ""
    spec = (
        '# -*- mode: python ; coding: utf-8 -*-\n'
        'import sys\n'
        'sys.setrecursionlimit(10000)\n\n'
        + _common_analysis()
        + f"""exe = EXE(
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
{icon_line}
    contents_directory='.',
    onefile=True,
)
"""
    )
    with open(SPEC_NAME, 'w', encoding='utf-8') as f:
        f.write(spec)
    print(f'[build-desktop] OK 已生成 onefile spec: {SPEC_NAME}')


def clean():
    """清理旧的构建输出（跳过被锁定的文件）"""
    for d in [os.path.join(ROOT, 'dist'), WORK_DIR]:
        if not os.path.exists(d):
            continue
        # 多次重试，应对进程未完全退出的情况
        for attempt in range(3):
            try:
                shutil.rmtree(d)
                print(f'[build-desktop] OK 已清理: {d}')
                break
            except PermissionError as e:
                if attempt < 2:
                    import time
                    time.sleep(1)
                else:
                    # 最后尝试：逐个删除，跳过被锁的文件
                    print(f'[build-desktop] WARNING 部分文件被锁定，跳过: {e}')
                    # 删不掉也继续，PyInstaller --noconfirm 会覆盖
        else:
            # 如果 for 循环正常结束（没 break），说明一直失败
            print(f'[build-desktop] WARNING 无法完全清理 {d}，将覆盖构建')


def build(mode: str):
    """执行 PyInstaller 构建"""
    if mode == 'onedir':
        create_onedir_spec()
    else:
        create_onefile_spec()

    tmp_dist = os.path.join(ROOT, 'dist_tmp')
    if os.path.exists(tmp_dist):
        shutil.rmtree(tmp_dist, ignore_errors=True)
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        '--distpath', tmp_dist,
        '--workpath', WORK_DIR,
        SPEC_NAME,
    ]

    print(f'[build-desktop] ... 开始构建（{mode} 模式）...')
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')

    if result.returncode != 0:
        print('[build-desktop] ERROR 构建失败:')
        print(result.stderr[-3000:] if len(result.stderr) > 3000 else result.stderr)
        sys.exit(1)

    # 构建成功后移到正式 dist 目录
    final_dist = os.path.join(ROOT, 'dist')
    src = os.path.join(tmp_dist, OUTPUT_NAME) if mode == 'onedir' else os.path.join(tmp_dist, f'{OUTPUT_NAME}.exe')
    dst = os.path.join(final_dist, OUTPUT_NAME) if mode == 'onedir' else os.path.join(final_dist, f'{OUTPUT_NAME}.exe')

    if os.path.isdir(src):
        # 删除已存在的目标目录（可能被锁的就跳过）
        if os.path.exists(dst):
            try:
                shutil.rmtree(dst)
            except PermissionError:
                print('[build-desktop] WARNING 旧 dist 被锁定，将在下次覆盖')
        # 用 robocopy 兼容文件锁
        subprocess.run(['robocopy', src, dst, '/E', '/MOVE', '/NFL', '/NDL', '/NJH', '/NJS'],
                       capture_output=True, cwd=ROOT)
    elif os.path.isfile(src):
        os.makedirs(final_dist, exist_ok=True)
        if os.path.exists(dst):
            try:
                os.remove(dst)
            except PermissionError:
                pass
        shutil.move(src, dst)

    # 清理临时目录
    if os.path.exists(tmp_dist):
        try:
            # 先改名再删，绕过短时间锁
            import random
            tmp_rename = tmp_dist + '_' + str(random.randint(1000, 9999))
            os.rename(tmp_dist, tmp_rename)
            shutil.rmtree(tmp_rename, ignore_errors=True)
        except Exception:
            pass

    result_path = os.path.join(final_dist, OUTPUT_NAME, f'{OUTPUT_NAME}.exe') if mode == 'onedir' else os.path.join(final_dist, f'{OUTPUT_NAME}.exe')
    if os.path.exists(result_path):
        print(f'[build-desktop] OK 构建成功: {result_path}')
    elif os.path.isdir(os.path.join(final_dist, OUTPUT_NAME)):
        print(f'[build-desktop] OK 构建成功: {os.path.join(final_dist, OUTPUT_NAME)}')
    else:
        print('[build-desktop] WARNING 输出文件未找到，请检查 dist/ 目录')

    print('[build-desktop] 完成')


def build_installer():
    """构建 onedir + NSIS 安装包（需要机器上安装 NSIS）"""
    print('[build-desktop] ... 先生成 onedir 包 ...')
    build('onedir')

    dist_path = os.path.join(ROOT, 'dist', OUTPUT_NAME)
    if not os.path.isdir(dist_path):
        print('[build-desktop] ERROR onedir 构建产物不存在，无法生成安装包')
        sys.exit(1)

    nsis_script = os.path.join(ROOT, 'installer.nsi')
    makensis = shutil.which('makensis')

    if not makensis:
        print('[build-desktop] WARNING 未找到 NSIS (makensis)，跳过安装包生成')
        print('[build-desktop] 请安装 NSIS (https://nsis.sourceforge.io) 后重试')
        print(f'[build-desktop] onedir 产物已在: {dist_path}，可手动压缩分发')
        return

    # 生成 installer.nsi
    _create_nsis_script(nsis_script, dist_path)
    print('[build-desktop] ... 生成安装包 ...')
    result = subprocess.run([makensis, nsis_script], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode == 0:
        print(f'[build-desktop] OK 安装包已生成: {os.path.join(ROOT, "dist", f"{OUTPUT_NAME}_Setup.exe")}')
    else:
        print('[build-desktop] ERROR 安装包生成失败:')
        print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
    print('[build-desktop] 完成')


def _create_nsis_script(nsis_path: str, source_dir: str):
    """生成 NSIS 安装脚本"""
    script = f'''; Docflowing 安装脚本 — NSIS
; 由 build-desktop.py 自动生成

Unicode true

!define PRODUCT_NAME "{OUTPUT_NAME}"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "Docflowing"

Name "${{PRODUCT_NAME}}"
OutFile "dist\\{OUTPUT_NAME}_Setup.exe"
InstallDir "$PROGRAMFILES64\\${{PRODUCT_NAME}}"
RequestExecutionLevel admin

Section "安装主程序" SEC01
  SetOutPath "$INSTDIR"
  File /r "{source_dir}\\*.*"
SectionEnd

Section "创建快捷方式" SEC02
  CreateShortCut "$DESKTOP\\${{PRODUCT_NAME}}.lnk" "$INSTDIR\\{OUTPUT_NAME}.exe"
  CreateDirectory "$SMPROGRAMS\\${{PRODUCT_NAME}}"
  CreateShortCut "$SMPROGRAMS\\${{PRODUCT_NAME}}\\${{PRODUCT_NAME}}.lnk" "$INSTDIR\\{OUTPUT_NAME}.exe"
  CreateShortCut "$SMPROGRAMS\\${{PRODUCT_NAME}}\\卸载.lnk" "$INSTDIR\\uninst.exe"
SectionEnd

Section "卸载程序" SEC03
  WriteUninstaller "$INSTDIR\\uninst.exe"
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$DESKTOP\\${{PRODUCT_NAME}}.lnk"
  RMDir /r "$SMPROGRAMS\\${{PRODUCT_NAME}}"
SectionEnd
'''
    with open(nsis_path, 'w', encoding='utf-8') as f:
        f.write(script)
    print(f'[build-desktop] OK 已生成 NSIS 脚本: {nsis_path}')


def main():
    parser = argparse.ArgumentParser(description='Docflowing 桌面应用构建脚本')
    parser.add_argument('--onefile', action='store_true', help='单文件模式（全部嵌入 exe）')
    parser.add_argument('--installer', action='store_true', help='打包后生成 NSIS 安装包')
    args = parser.parse_args()

    if args.installer:
        build_installer()
    elif args.onefile:
        build('onefile')
    else:
        build('onedir')


if __name__ == '__main__':
    main()