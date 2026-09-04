"""应用更新：清单拉取、后台静默预下载、完整性校验、状态机。

设计要点
--------
1. **静默预下载**。检测到新版本后立刻在后台线程把安装包拉下来并校验，
   等提示用户时安装包已经躺在本地，用户只需点一次「安装」。等待时间从
   「下载 + 安装」压缩到只剩「安装」，这是更新完成率的关键差异。
2. **网络与磁盘 IO 全在后台线程**。失败一律降级成「手动下载」，不弹错误、
   不阻塞启动、不影响正常使用。更新功能永远不该成为用户用不了软件的理由。
3. **sha256 必校验**。国内网络环境下代理、下载工具改写二进制的情况很常见，
   校验不通过就丢弃重来，绝不把没验过的文件交给安装器。
4. **状态可被反复查询**。前端轮询 /api/updater/status 即可，无需长连接。

状态流转::

    idle ──check──> checking ──┬─ 无更新 ──> idle
                               ├─ 有更新 ──> available ──download──> downloading
                               │                                        │
                               │                              成功 ──> ready
                               └────────────────────────────── 失败 ──> failed
"""

import hashlib
import json
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request

from flask import Blueprint, jsonify, request

from server.auth import login_required
from server.settings import _load_app_settings, _save_app_settings
from server.workspace import _get_runtime_dir

import version

updater_bp = Blueprint('updater', __name__, url_prefix='/api/updater')

# ==================== 常量 ====================

# 默认清单地址：指向 GitHub 最新 Release 的 version.json 资产。
# releases/latest/download/ 是稳定 URL，由 CI 在发布时生成并上传该资产，
# 不需要调用 api.github.com（国内可达性差）。
# 自建 CDN / 镜像时用环境变量 DOCFLOWING_UPDATE_URL 覆盖即可。
DEFAULT_MANIFEST_URL = (
    'https://github.com/doonly1/Docflowing/releases/latest/download/version.json'
)

STATE_IDLE = 'idle'
STATE_CHECKING = 'checking'
STATE_AVAILABLE = 'available'
STATE_DOWNLOADING = 'downloading'
STATE_READY = 'ready'
STATE_FAILED = 'failed'

# 自动检查节流：同一进程内自动检查的最小间隔（秒）
AUTO_CHECK_INTERVAL = 6 * 3600
# 启动后延迟多久做第一次自动检查：避开启动高峰，别和用户抢带宽和 CPU
STARTUP_CHECK_DELAY = 20
# 清单请求超时（秒）。宁可超时静默失败，也不要卡住。
MANIFEST_TIMEOUT = 8
# 下载单块大小
CHUNK_SIZE = 256 * 1024
# 已下载成功的标记文件名（避免每次启动都重新 hash 几十 MB）
READY_MARKER = '.ready.json'

# ==================== 路径 / 配置 ====================


def get_manifest_url():
    """更新清单地址：环境变量可覆盖（自建 CDN / 镜像场景）"""
    return (os.environ.get('DOCFLOWING_UPDATE_URL') or DEFAULT_MANIFEST_URL).strip()


def get_update_dir():
    """更新包下载目录（每个版本一个子目录）"""
    d = os.path.join(_get_runtime_dir(), 'updates')
    os.makedirs(d, exist_ok=True)
    return os.path.abspath(d)


def is_portable():
    """便携版：数据目录在 exe 同级，没有安装器可覆盖，只能引导手动下载"""
    return '--portable' in sys.argv


def _setting(key, default):
    try:
        return _load_app_settings().get(key, default)
    except Exception:
        return default


def _set_setting(key, value):
    try:
        s = _load_app_settings()
        s[key] = value
        _save_app_settings(s)
        return True
    except Exception:
        return False


# ==================== 状态 ====================

_lock = threading.RLock()
_state = {
    'state': STATE_IDLE,
    'current_version': version.format_version(),
    'latest_version': None,
    'channel': version.UPDATE_CHANNEL,
    'notes': '',
    'published_at': '',
    'forced': False,
    'progress': 0.0,
    'downloaded_bytes': 0,
    'total_bytes': 0,
    'installer_path': None,
    'download_url': '',
    'error': '',
    'checked_at': 0,
    'portable': False,
    'auto_download': True,
    'skipped_version': '',
}

_downloader = None
_last_auto_check = 0


def _snapshot():
    with _lock:
        return dict(_state)


def get_status():
    """返回当前更新状态（纯内存查询，不触网）"""
    s = _snapshot()
    s['auto_download'] = bool(_setting('auto_download_update', True))
    s['skipped_version'] = _setting('skip_update_version', '') or ''
    s['manifest_url'] = get_manifest_url()
    return s


def _reset(**kw):
    with _lock:
        _state.update({
            'latest_version': None,
            'notes': '',
            'published_at': '',
            'forced': False,
            'progress': 0.0,
            'downloaded_bytes': 0,
            'total_bytes': 0,
            'installer_path': None,
            'download_url': '',
            'error': '',
        })
        _state.update(kw)


# ==================== 清单 ====================


def fetch_manifest(timeout=MANIFEST_TIMEOUT):
    """拉取并解析更新清单，失败返回 None（静默）。"""
    url = get_manifest_url()
    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': f'Docflowing/{version.format_version()}',
                'Accept': 'application/json',
                'Cache-Control': 'no-cache',
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        data = json.loads(raw.decode('utf-8'))
        if not isinstance(data, dict) or not data.get('version'):
            return None
        return data
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _pick_package(manifest):
    """按运行形态挑选对应的包：安装版取 installer，便携版取 portable。

    返回 (package_dict, package_key)，找不到返回 (None, None)。
    """
    packages = manifest.get('packages')
    if not isinstance(packages, dict):
        # 兼容旧格式：清单顶层直接放 url/sha256
        if manifest.get('url'):
            return manifest, 'installer'
        return None, None

    want = 'portable' if is_portable() else 'installer'
    pkg = packages.get(want) or packages.get('installer')
    key = want if packages.get(want) else 'installer'
    if not pkg or not pkg.get('url'):
        return None, None
    return pkg, key


def _channel_accepts(manifest_channel):
    """通道过滤：stable 客户端不接 beta 清单。"""
    mine = (version.UPDATE_CHANNEL or 'stable').lower()
    theirs = (manifest_channel or 'stable').lower()
    if mine == 'stable' and theirs not in ('stable', ''):
        return False
    return True


def evaluate_manifest(manifest):
    """把清单解析成结构化的更新信息；无可用更新返回 None。

    返回::

        {
          'latest_version', 'notes', 'published_at', 'forced',
          'url', 'mirror', 'sha256', 'size', 'filename', 'portable'
        }
    """
    if not manifest or not _channel_accepts(manifest.get('channel')):
        return None

    latest = manifest.get('version')
    if version.compare_versions(latest, version.format_version()) <= 0:
        return None

    pkg, key = _pick_package(manifest)
    if not pkg:
        return None

    forced = False
    min_required = manifest.get('min_required')
    if min_required and version.compare_versions(version.format_version(), min_required) < 0:
        forced = True

    url = pkg.get('url') or ''
    filename = os.path.basename(url.split('?')[0]) or 'Docflowing_Setup.exe'
    if not filename.lower().endswith('.exe'):
        filename = 'Docflowing_Setup.exe'

    return {
        'latest_version': latest,
        'notes': manifest.get('notes') or '',
        'published_at': manifest.get('published_at') or '',
        'forced': forced,
        'url': url,
        'mirror': pkg.get('mirror') or '',
        'sha256': (pkg.get('sha256') or '').lower(),
        'size': int(pkg.get('size') or 0),
        'filename': filename,
        'portable': key == 'portable',
    }


# ==================== 下载 ====================


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _open_stream(url, resume_from):
    """打开下载流，尽量断点续传。

    返回 (resp, total_bytes, resumed)。服务端不支持 Range 会返回 200，
    此时 resumed=False，调用方必须从 0 重新写。
    """
    headers = {'User-Agent': f'Docflowing/{version.format_version()}'}
    if resume_from > 0:
        headers['Range'] = f'bytes={resume_from}-'
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=30)
    resumed = resume_from > 0 and resp.status == 206
    total = 0
    try:
        cr = resp.headers.get('Content-Range')
        if cr and '/' in cr:
            total = int(cr.rsplit('/', 1)[1])
        else:
            total = int(resp.headers.get('Content-Length') or 0)
            if resumed:
                total += resume_from
    except (ValueError, AttributeError):
        total = 0
    return resp, total, resumed


class _UpdateDownloader(threading.Thread):
    """后台下载线程：断点续传 → sha256 校验 → 落定标记。

    只用 urllib，避免给打包体积和依赖树增加负担。
    """

    def __init__(self, info):
        super().__init__(daemon=True, name='UpdateDownloader')
        self.info = info
        self._cancel = threading.Event()
        self.dest_dir = os.path.join(get_update_dir(), info['latest_version'])
        self.dest = os.path.join(self.dest_dir, info['filename'])
        self.part = self.dest + '.part'
        self.marker = os.path.join(self.dest_dir, READY_MARKER)

    def cancel(self):
        self._cancel.set()

    def run(self):
        info = self.info
        try:
            os.makedirs(self.dest_dir, exist_ok=True)
            for candidate in (info['url'], info['mirror']):
                if not candidate or self._cancel.is_set():
                    continue
                if self._try_url(candidate):
                    return
            if not self._cancel.is_set():
                with _lock:
                    # 仅在还没有更具体的错误（如 sha256 校验失败）时，
                    # 才回退到通用「下载失败」提示，避免覆盖精准原因。
                    if not _state.get('error'):
                        _state.update({
                            'state': STATE_FAILED,
                            'error': '下载失败，请检查网络后重试，或前往发布页手动下载',
                        })
        except Exception as e:  # 下载线程绝不能把进程带崩
            with _lock:
                _state.update({'state': STATE_FAILED, 'error': f'下载异常: {e}'})

    def _try_url(self, url):
        """从单个 URL 下载。成功并校验通过返回 True。"""
        have = 0
        if os.path.isfile(self.part):
            have = os.path.getsize(self.part)

        resp, total, resumed = _open_stream(url, have)
        if not resumed and have:
            have = 0  # 服务端不支持续传，从头再来

        mode = 'ab' if resumed and have else 'wb'
        expected = total or self.info.get('size') or 0

        with _lock:
            _state.update({
                'state': STATE_DOWNLOADING,
                'downloaded_bytes': have,
                'total_bytes': expected,
                'progress': (have * 100.0 / expected) if expected else 0.0,
                'error': '',
            })

        try:
            with open(self.part, mode) as out, resp:
                while True:
                    if self._cancel.is_set():
                        return False
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    out.write(chunk)
                    have += len(chunk)
                    with _lock:
                        _state['downloaded_bytes'] = have
                        _state['total_bytes'] = expected or have
                        _state['progress'] = (
                            have * 100.0 / _state['total_bytes'] if _state['total_bytes'] else 0.0
                        )
        except (urllib.error.URLError, OSError):
            return False

        if self._cancel.is_set():
            return False

        # 体积校验：能提前拦掉绝大多数被截断/被改写的下载
        if self.info.get('size') and os.path.getsize(self.part) != self.info['size']:
            return False

        return self._finalize()

    def _finalize(self):
        """sha256 校验 → 落定 → 写 ready 标记。"""
        expected = self.info.get('sha256')
        if expected:
            actual = _sha256_of(self.part)
            if actual.lower() != expected.lower():
                try:
                    os.remove(self.part)
                except OSError:
                    pass
                with _lock:
                    _state.update({
                        'state': STATE_FAILED,
                        'error': '安装包校验失败，已丢弃，请重试或手动下载',
                    })
                return False

        if os.path.exists(self.dest):
            os.remove(self.dest)
        os.replace(self.part, self.dest)

        try:
            with open(self.marker, 'w', encoding='utf-8') as f:
                json.dump({
                    'version': self.info['latest_version'],
                    'file': os.path.basename(self.dest),
                    'sha256': expected or _sha256_of(self.dest),
                    'size': os.path.getsize(self.dest),
                    'finished_at': time.time(),
                }, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

        # 只保留当前这一版，避免更新目录无限膨胀
        prune_old_updates(keep=self.info['latest_version'])

        with _lock:
            _state.update({
                'state': STATE_READY,
                'installer_path': self.dest,
                'progress': 100.0,
                'downloaded_bytes': os.path.getsize(self.dest),
                'total_bytes': os.path.getsize(self.dest),
                'error': '',
            })
        return True


def prune_old_updates(keep=None):
    """清理非当前版本的下载残留（中断的 .part、旧版本目录）"""
    root = get_update_dir()
    try:
        for name in os.listdir(root):
            if keep and name == keep:
                continue
            p = os.path.join(root, name)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except OSError:
                    pass
    except OSError:
        pass


def restore_ready_state():
    """启动时恢复「已下载待安装」状态。

    靠 .ready.json 标记判断，不重新 hash 几十 MB 的安装包——
    启动路径上不该有这种开销。
    """
    root = get_update_dir()
    current = version.format_version()
    try:
        candidates = []
        for name in os.listdir(root):
            marker = os.path.join(root, name, READY_MARKER)
            if not os.path.isfile(marker):
                continue
            try:
                with open(marker, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            exe = os.path.join(root, name, data.get('file') or '')
            if not os.path.isfile(exe):
                continue
            if version.compare_versions(data.get('version'), current) <= 0:
                continue  # 已经装上或落后了，没有提示价值
            candidates.append((data.get('version'), exe, data.get('size') or 0))
    except OSError:
        return

    if not candidates:
        return

    candidates.sort(key=lambda x: version.parse_version(x[0]), reverse=True)
    ver, exe, size = candidates[0]
    with _lock:
        _state.update({
            'state': STATE_READY,
            'latest_version': ver,
            'installer_path': exe,
            'download_url': '',
            'progress': 100.0,
            'downloaded_bytes': size or os.path.getsize(exe),
            'total_bytes': size or os.path.getsize(exe),
            'portable': is_portable(),
            'checked_at': time.time(),
            'error': '',
        })


# ==================== 检查 / 下载调度 ====================


def check_update(force=False, auto_download=None):
    """检查更新；有更新且允许时自动开始后台静默下载。

    force=True 时忽略节流（用户手动点击「检查更新」）。
    返回最新状态字典。
    """
    global _last_auto_check

    if os.environ.get('DOCFLOWING_DISABLE_UPDATE_CHECK') == '1':
        with _lock:
            _state['state'] = STATE_IDLE
            _state['checked_at'] = time.time()
        return get_status()

    now = time.time()
    if not force and now - _last_auto_check < AUTO_CHECK_INTERVAL:
        return get_status()
    _last_auto_check = now

    with _lock:
        if _state['state'] == STATE_DOWNLOADING:
            return get_status()
        _state['state'] = STATE_CHECKING
        _state['error'] = ''
    with _lock:
        _state['checked_at'] = now

    manifest = fetch_manifest()
    with _lock:
        _state['checked_at'] = time.time()

    if not manifest:
        with _lock:
            if _state['state'] == STATE_CHECKING:
                _state['state'] = STATE_IDLE
        return get_status()

    info = evaluate_manifest(manifest)
    if not info:
        with _lock:
            _reset(state=STATE_IDLE)
        return get_status()

    with _lock:
        _reset(
            state=STATE_AVAILABLE,
            latest_version=info['latest_version'],
            notes=info['notes'],
            published_at=info['published_at'],
            forced=info['forced'],
            download_url=info['url'],
            portable=info['portable'],
            total_bytes=info['size'],
        )

    # 已被用户跳过的版本，不再自动下载，但强制更新（forced）不受此限
    skipped = _setting('skip_update_version', '') or ''
    if skipped and skipped == info['latest_version'] and not info['forced']:
        return get_status()

    if auto_download is None:
        auto_download = bool(_setting('auto_download_update', True))

    # 便携版没有安装器可覆盖，下载下来也只能让用户自己解压覆盖，
    # 价值不大，直接引导到下载页即可。
    if auto_download and not info['portable']:
        start_download(info)
    return get_status()


def start_download(info=None):
    """开始（或继续）后台下载。

    info 由 check_update 直接传入时就不再二次拉取清单——一次更新检查只该
    打一次网络请求，重复请求既慢又容易在弱网下前后拿到不一致的结果。
    手动点「下载更新」时没有现成 info，才回退到重新取清单。
    """
    global _downloader

    if info is None:
        info = _current_info_from_manifest()
        if not info:
            with _lock:
                if _state['state'] == STATE_DOWNLOADING:
                    return get_status()
                _state.update({
                    'state': STATE_FAILED,
                    'error': '无法获取更新信息，请重新检查更新',
                })
            return get_status()

    with _lock:
        if _state['state'] == STATE_DOWNLOADING and _downloader and _downloader.is_alive():
            return get_status()
        if _state['state'] == STATE_READY:
            return get_status()
        _downloader = _UpdateDownloader(info)
        _downloader.start()
        _state.update({
            'state': STATE_DOWNLOADING,
            'latest_version': info['latest_version'],
            'download_url': info['url'],
            'total_bytes': info.get('size') or 0,
            'error': '',
            'progress': 0.0,
        })
    return get_status()


def _current_info_from_manifest():
    """重新拉清单并取出与当前已知版本匹配的那条更新信息。"""
    manifest = fetch_manifest()
    if not manifest:
        return None
    info = evaluate_manifest(manifest)
    if not info:
        return None
    with _lock:
        known = _state.get('latest_version')
    # 目标版本变了就不要沿用旧信息，避免下到一半版本漂移
    if known and info['latest_version'] != known:
        return None
    return info


def cancel_download():
    """取消后台下载并清理半成品"""
    global _downloader
    with _lock:
        if _downloader:
            _downloader.cancel()
            _downloader = None
        if _state['state'] in (STATE_DOWNLOADING, STATE_FAILED):
            _state['state'] = STATE_AVAILABLE if _state['latest_version'] else STATE_IDLE
            _state['progress'] = 0.0
            _state['downloaded_bytes'] = 0
            _state['error'] = ''
    prune_old_updates(keep=_state.get('latest_version'))
    return get_status()


def start_background_check(delay=STARTUP_CHECK_DELAY):
    """启动后延迟做一次自动检查（含触发静默下载），不阻塞主线程。"""

    def _runner():
        try:
            # 分段 sleep，便于测试与快速退出
            waited = 0.0
            while waited < delay:
                time.sleep(min(1.0, delay - waited))
                waited += 1.0
            restore_ready_state()
            check_update(force=False)
        except Exception:
            pass

    t = threading.Thread(target=_runner, daemon=True, name='UpdateCheck')
    t.start()
    return t


# ==================== API ====================


@updater_bp.route('/status', methods=['POST'])
@login_required
def api_status():
    return jsonify({'success': True, 'status': get_status()})


@updater_bp.route('/check', methods=['POST'])
@login_required
def api_check():
    """手动检查更新（忽略节流）"""
    data = request.get_json(silent=True) or {}
    return jsonify({
        'success': True,
        'status': check_update(force=True, auto_download=data.get('auto_download')),
    })


@updater_bp.route('/download', methods=['POST'])
@login_required
def api_download():
    """手动触发后台下载"""
    return jsonify({'success': True, 'status': start_download()})


@updater_bp.route('/cancel', methods=['POST'])
@login_required
def api_cancel():
    return jsonify({'success': True, 'status': cancel_download()})


@updater_bp.route('/skip', methods=['POST'])
@login_required
def api_skip():
    """跳过指定版本（强制更新不允许跳过）"""
    data = request.get_json(silent=True) or {}
    ver = data.get('version')
    if not ver:
        return jsonify({'success': False, 'message': '缺少版本号'})
    if _state.get('forced'):
        return jsonify({'success': False, 'message': '该版本为必需更新，无法跳过'})
    _set_setting('skip_update_version', ver)
    cancel_download()
    with _lock:
        _reset(state=STATE_IDLE)
    return jsonify({'success': True, 'status': get_status()})


@updater_bp.route('/clear_skip', methods=['POST'])
@login_required
def api_clear_skip():
    _set_setting('skip_update_version', '')
    return jsonify({'success': True, 'status': get_status()})


@updater_bp.route('/auto_download', methods=['POST'])
@login_required
def api_set_auto_download():
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled', True))
    _set_setting('auto_download_update', enabled)
    if enabled:
        # 开启后若已有可用更新，立刻补一次下载
        if _state.get('state') in (STATE_AVAILABLE, STATE_FAILED):
            start_download()
    else:
        cancel_download()
    return jsonify({'success': True, 'status': get_status()})


@updater_bp.route('/dismiss', methods=['POST'])
@login_required
def api_dismiss():
    """关掉「已就绪」提示：保留本地安装包，只把状态收回 available。

    用户可能正在忙，不该一直被提示条打扰；安装包留着，下次启动还能接着装。
    """
    with _lock:
        if _state['state'] == STATE_READY:
            _state['state'] = STATE_AVAILABLE
    return jsonify({'success': True, 'status': get_status()})
