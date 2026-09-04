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


def _rel_to_root(abs_path: str) -> str:
    """把绝对路径转成相对项目根的 posix 相对路径（spec 用 SPECPATH 再拼回）。"""
    return os.path.relpath(abs_path, ROOT).replace(os.sep, '/')


def _datas_lines():
    """组装 datas 元组列表。

    项目内资源一律输出 `os.path.join(SPECPATH, '<相对路径>')`——SPECPATH 是
    PyInstaller 执行 spec 时注入的「spec 文件所在目录」绝对路径，因此生成的
    build.spec 不依赖构建机的盘符/目录，整个项目文件夹移到任何位置都能直接
    `pyinstaller build.spec`，无需重新生成。
    仅 site-packages 类构建机环境路径（pythonnet runtime 等）保留绝对路径。
    """
    lines = []

    # 1. 前端 ui/：剔除 pdf.min.js / pdf.worker.min.js（不再内置 PDF 预览）
    ui_src = os.path.join(ROOT, 'ui')
    if os.path.isdir(ui_src):
        for root, dirs, files in os.walk(ui_src):
            rel_root = os.path.relpath(root, ui_src)
            dst_root = 'ui' if rel_root == '.' else f"ui/{rel_root.replace(os.sep, '/')}"
            for f in files:
                if f.lower().startswith('pdf.') and f.lower().endswith(('.min.js', '.js')):
                    continue  # 跳过 pdf.min.js / pdf.worker.min.js
                src_f = os.path.join(root, f)
                rel = _rel_to_root(src_f)
                dst_f = dst_root if dst_root.endswith('/') else dst_root
                lines.append(f"    (os.path.join(SPECPATH, '{rel}'), '{dst_f}'),")

    # 2. kb/skills/system
    if os.path.isdir(os.path.join(ROOT, 'kb', 'skills', 'system')):
        lines.append("    (os.path.join(SPECPATH, 'kb/skills/system'), 'kb/skills/system'),")

    # 3. tools
    if os.path.isdir(os.path.join(ROOT, 'tools')):
        lines.append("    (os.path.join(SPECPATH, 'tools'), 'tools'),")

    # 4. kb/fts_ext：保留全部跨平台二进制（Windows .dll + Linux .so + macOS .dylib/.so），
    #    确保同一工作区文件库跨平台运行时 FTS5 中文分词扩展都能加载。
    if os.path.isdir(os.path.join(ROOT, 'kb', 'fts_ext')):
        lines.append("    (os.path.join(SPECPATH, 'kb/fts_ext'), 'kb/fts_ext'),")

    # 5. pythonnet .NET runtime DLL（固定 edgechromium 后端仍保留，用于与 WebView2 COM 互操作的运行时）
    #    注：该路径位于构建机 site-packages，不属于项目目录，无法用 SPECPATH 相对化，只能写绝对路径。
    try:
        import pythonnet
        pynt_dir = os.path.dirname(pythonnet.__file__)
        rt_dir = os.path.join(pynt_dir, 'runtime')
        if os.path.isdir(rt_dir):
            lines.append(f"    (r'{rt_dir}', 'pythonnet/runtime'),")
    except ImportError:
        pass

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
    # ========== pywebview（后端按优先级：edgechromium → winforms → win32） ==========
    'webview',
    'webview.platforms.edgechromium', 'webview.platforms.winforms',
    'webview.platforms.win32',
    'pythonnet', 'clr_loader', 'clr_loader.netfx', 'clr_loader.types',
    # ========== Tools（Python 模块形式引入） ==========
    'logging_config', 'doc_process', 'mystyle', 'to_compare', 'to_docx',
    'to_redhead', 'to_index', 'to_pageNum', 'to_pdf', 'float_picture',
    'load_config', 'tool_defs', 'WordKeepAlive',
    # ========== 第三方隐式依赖 ==========
    'flask', 'flask_cors', 'zeroconf', 'yaml', 'requests',
    'bs4', 'beautifulsoup4', 'markitdown', 'openpyxl',
    'docx', 'pptx', 'pystray',
    'PIL', 'PIL._imaging', 'PIL._tkinter_finder', 'PIL.Image',
    'PIL.ImageTk', 'packaging',
    # ========== tkinter（弹窗用，打包时常被裁掉） ==========
    'tkinter', '_tkinter',
    # ========== Windows 可选依赖（COM + Word） ==========
    'win32com', 'pythoncom', 'win32api', 'win32con', 'win32gui',
    'pywintypes', 'docx2pdf',
]

_EXCLUDES = [
    'unittest', 'pdb', 'test', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    'matplotlib', 'scipy', 'notebook', 'jupyter', 'IPython', 'numpy.testing',
    'pandas', 'cefpython3',
    # 已移除的依赖，残留时防止误打包
    'cryptography',
    # markitdown 死重链：代码走 converters 子模块（跳过 magika），
    # 顶层 _markitdown 会 import magika → onnxruntime → onnx/numpy。
    # 运行时永不触发，排除后大幅缩小安装包。
    'magika', 'onnxruntime', 'onnx',
    # win32ui 是 Pythonwin IDE 组件，win32com.client 不依赖它，
    # 排除后连带不打包 mfc140u.dll（~6 MB）。
    'win32ui',
    # PIL 格式插件：代码只用 Image.new('RGBA') 和 Image.open(ico)，
    # 不涉及 AVIF/WebP/FreeType/色彩管理等格式编解码。
    'PIL._avif', 'PIL._webp', 'PIL._imagingft', 'PIL._imagingcms',
    # numpy 由 PIL.Image.fromarray()（numpy 数组→图像）惰性导入拉入，
    # 但代码只用 Image.new/Image.open，从不调用 fromarray，完全不需 numpy。
    # 排除后连带去掉 numpy.libs 里的 OpenBLAS（~19.4MB）+ numpy（~6.6MB）。
    'numpy',
    # ────── PDF 处理全栈已移除（预览改用系统默认程序、同步直接排除 PDF）──────
    # 原占用: pdfminer 7.5 + pypdfium2_raw/pdfium.dll 6.8 + 前端 pdf*.js 1.3 ≈ 15.6 MB
    'pdfminer', 'pdfplumber', 'pypdfium2', 'pypdfium2_raw',
]


def _common_analysis() -> str:
    """生成 Analysis 块（onedir / onefile 共用）"""
    datas = _datas_lines()
    hidden = '\n'.join(f"        '{m}'," for m in _HIDDEN_IMPORTS)
    excludes = '\n'.join(f"        '{m}'," for m in _EXCLUDES)
    return f"""# --- PIL C 扩展二进制（_imaging.pyd 等） ---
import glob, os
import PIL
_pil_dir = PIL.__path__[0]
# 只收集 PIL 核心 pyd，跳过 _avif(28MB)/_webp/_imagingft/_imagingcms 等格式插件
_pil_skip = {{'_avif', '_webp', '_imagingft', '_imagingcms', '_imagingtk', '_imagingmorph'}}
_pil_pyds = [(f, 'PIL') for f in glob.glob(os.path.join(_pil_dir, '*.pyd'))
             if os.path.basename(f).split('.')[0] not in _pil_skip]

# SPECPATH：PyInstaller 注入的 spec 文件所在目录。用它派生所有项目内路径，
# build.spec 即可跨盘符/跨机器直接使用（相对路径本身会按运行 cwd 解析，不可靠）。
a = Analysis(
    [os.path.join(SPECPATH, 'desktop_app.py')],
    pathex=[SPECPATH],
    binaries=list(_pil_pyds),
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
    icon_line = ("    icon=os.path.join(SPECPATH, 'ui', 'favicon.ico'),"
                 if os.path.isfile(ICON_PATH) else "")
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
    upx_exclude=['*.pyd', '*.dll'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
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
    upx_exclude=['*.pyd', '*.dll'],
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
    icon_line = ("    icon=os.path.join(SPECPATH, 'ui', 'favicon.ico'),"
                 if os.path.isfile(ICON_PATH) else "")
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
    upx_exclude=['*.pyd', '*.dll'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
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
    # 保证 workpath 目录干净（PyInstaller 需要自己创建 build/ 子目录）
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    # 确保父目录存在
    os.makedirs(os.path.dirname(WORK_DIR.rstrip('\\/')), exist_ok=True)

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

    # ──── UPX 后处理：PyInstaller upx=True 只压 DLL，exe 和残留 DLL 手动补压 ────
    _upx_post_process(final_dist, mode, OUTPUT_NAME)

    print('[build-desktop] 完成')


def _upx_post_process(dist_dir: str, mode: str, app_name: str):
    """PyInstaller upx=True 只处理部分 DLL，手动补压 exe 和残留 DLL。

    GUARD_CF (Control Flow Guard) 的 exe 需要 --force。
    *.pyd 不压缩（UPX 对 Python C 扩展有损坏风险）。
    """
    upx = shutil.which('upx')
    if not upx:
        print('[build-desktop] UPX 未找到，跳过 UPX 后处理')
        return
    print(f'[build-desktop] UPX 后处理: {upx}')

    # 收集 exe + 所有 DLL（排除 pyd）
    if mode == 'onedir':
        exe = os.path.join(dist_dir, app_name, f'{app_name}.exe')
        base = os.path.join(dist_dir, app_name)
    else:
        exe = os.path.join(dist_dir, f'{app_name}.exe')
        base = dist_dir

    targets = []
    if os.path.exists(exe):
        targets.append(exe)
    for root, dirs, files in os.walk(base):
        for f in files:
            if f.lower().endswith('.dll'):
                # fts_ext/ 下的 SQLite 扩展 DLL 不压缩：UPX 会改写 PE 加载行为，
                # 对 sqlite load_extension 有不可预测风险（偶发加载失败/崩溃），保持原样。
                if 'fts_ext' in os.path.relpath(root, base).replace('\\', '/').split('/'):
                    continue
                targets.append(os.path.join(root, f))

    for t in targets:
        result = subprocess.run(
            [upx, '--best', '--lzma', '--force', t],
            capture_output=True, text=True, timeout=120
        )
        short = os.path.relpath(t, dist_dir)
        if result.returncode == 0:
            print(f'  UPX OK: {short}')
        else:
            print(f'  UPX skip: {short}')


def _find_makensis():
    """查找 makensis：PATH → 系统安装目录 → 便携版 bundle

    支持两种常见安装形态：
    1. 标准安装（NSIS 官网安装器）：makensis.exe 在 NSIS 根目录，
       Stubs/Include/Plugins 与其同级，直接执行即可。
    2. electron-builder 便携 bundle：makensis.exe 位于 windows/ 子目录，
       需要设置 NSISDIR 指向其所在目录才能定位 Stubs/Include/Plugins。
    """
    exe = shutil.which('makensis')
    if exe:
        return exe, None
    candidates = [
        r'C:\Program Files (x86)\NSIS\makensis.exe',
        r'C:\Program Files\NSIS\makensis.exe',
        os.path.expanduser(r'~\.workbuddy\tools\nsis-eb\nsis-bundle\windows\makensis.exe'),
        os.path.expanduser(r'~\.workbuddy\tools\nsis\nsis-3.10.0\makensis.exe'),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p, os.path.dirname(p)  # NSISDIR 指向 exe 所在目录
    return None, None


def build_installer():
    """构建 onedir + NSIS 安装包（需要机器上安装 NSIS）"""
    print('[build-desktop] ... 先生成 onedir 包 ...')
    build('onedir')

    dist_path = os.path.join(ROOT, 'dist', OUTPUT_NAME)
    if not os.path.isdir(dist_path):
        print('[build-desktop] ERROR onedir 构建产物不存在，无法生成安装包')
        sys.exit(1)

    nsis_script = os.path.join(ROOT, 'installer.nsi')
    makensis, nsis_dir = _find_makensis()

    if not makensis:
        print('[build-desktop] WARNING 未找到 NSIS (makensis)，跳过安装包生成')
        print('[build-desktop] 请安装 NSIS (https://nsis.sourceforge.io) 后重试')
        print(f'[build-desktop] onedir 产物已在: {dist_path}，可手动压缩分发')
        return

    # 生成 installer.nsi（UTF-8 BOM，避免中文 Windows 下 makensis 编码报错）
    _create_nsis_script(nsis_script, dist_path)
    print('[build-desktop] ... 生成安装包 ...')
    env = os.environ.copy()
    if nsis_dir:
        env['NSISDIR'] = nsis_dir
    try:
        result = subprocess.run([makensis, nsis_script], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                env=env)
    finally:
        # 清理 License 的 UTF-8 BOM 临时副本
        _lic_bom = os.path.join(ROOT, '_nsis_license_bom.txt')
        if os.path.exists(_lic_bom):
            try:
                os.remove(_lic_bom)
            except OSError:
                pass
    if result.returncode == 0:
        print(f'[build-desktop] OK 安装包已生成: {os.path.join(ROOT, "dist", f"{OUTPUT_NAME}_Setup.exe")}')
    else:
        print('[build-desktop] ERROR 安装包生成失败:')
        # stdout 常含具体错误行，优先展示；stdout 为空时回退 stderr
        err_text = result.stdout if result.stdout.strip() else result.stderr
        print(err_text[-2000:] if len(err_text) > 2000 else err_text)
    print('[build-desktop] 完成')


def _create_nsis_script(nsis_path: str, source_dir: str):
    """生成 NSIS 安装脚本"""
    # NSIS(Unicode)的 License 页要求文本文件为 UTF-8 with BOM,
    # 否则中文会按本地 ANSI 代码页(GBK)解析 → 安装向导显示乱码。
    # 这里生成一个 BOM 副本供 makensis 引用,源 LICENSE 保持干净 UTF-8(无 BOM)。
    license_ref = 'LICENSE'
    license_bom = os.path.join(ROOT, '_nsis_license_bom.txt')
    license_src = os.path.join(ROOT, 'LICENSE')
    if os.path.isfile(license_src):
        with open(license_src, 'r', encoding='utf-8') as f:
            _lic_text = f.read()
        with open(license_bom, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(_lic_text)
        license_ref = os.path.basename(license_bom)

    # 安装包图标：与主程序统一使用 ui/favicon.ico(相对 makensis 的 cwd=ROOT 解析)。
    # NSIS 会读取 .ico 内嵌的 16/32/48/256 多尺寸位图,单尺寸 ico 也能用但资源管理器大图标会模糊。
    icon_lines = ""
    if os.path.isfile(os.path.join(ROOT, 'ui', 'favicon.ico')):
        icon_lines = (
            'Icon "ui\\\\favicon.ico"\n'
            '!define MUI_ICON "ui\\\\favicon.ico"\n'
            '!define MUI_UNICON "ui\\\\favicon.ico"\n'
        )

    script = f'''; Docflowing 安装脚本 — NSIS
; 由 build-desktop.py 自动生成

Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!define PRODUCT_NAME "{OUTPUT_NAME}"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "Docflowing"

Name "${{PRODUCT_NAME}}"
OutFile "dist\\{OUTPUT_NAME}_Setup.exe"
InstallDir "$PROGRAMFILES64\\${{PRODUCT_NAME}}"
RequestExecutionLevel admin

; ====== 安装程序与卸载程序图标(与主程序同款) ======
{icon_lines}; ====== 安装向导页面（用户可选择安装目录） ======
!include "MUI2.nsh"

!define MUI_ABORTWARNING
!define MUI_LANGDLL_ALLLANGUAGES

!insertmacro MUI_PAGE_WELCOME                  ; 欢迎页
!insertmacro MUI_PAGE_LICENSE "{license_ref}" ; 许可协议页(UTF-8 BOM 副本,避免中文乱码)
!insertmacro MUI_PAGE_DIRECTORY                ; 目录选择页（用户可更改安装路径）
!insertmacro MUI_PAGE_INSTFILES                ; 安装进度页
!insertmacro MUI_PAGE_FINISH                   ; 完成页

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; 许可协议页兜底：没有 LICENSE 文件时跳过
!macro MUI_PAGE_LICENSE_TEXT_MACRO
!macroend

Section "安装主程序" SEC01
  SetOutPath "$INSTDIR"
  File /r "{source_dir}\\*"
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
    with open(nsis_path, 'w', encoding='utf-8-sig') as f:
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