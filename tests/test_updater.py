"""应用更新模块测试

覆盖版本比对、清单解析、后台下载与 sha256 校验、状态机流转、安装路径校验。
下载测试用本地 HTTP 服务模拟，不打真实网络。
"""

import hashlib
import json
import os
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import version as version_mod  # noqa: E402
from server import updater  # noqa: E402


# ==================== 版本比对 ====================

class TestVersionCompare:

    def test_basic_ordering(self):
        assert version_mod.compare_versions('1.0.0', '1.0.1') == -1
        assert version_mod.compare_versions('1.0.1', '1.0.0') == 1
        assert version_mod.compare_versions('1.0.0', '1.0.0') == 0

    def test_numeric_not_lexicographic(self):
        """1.0.10 必须大于 1.0.9，字符串比较会得出错误结论"""
        assert version_mod.compare_versions('1.0.9', '1.0.10') == -1
        assert version_mod.compare_versions('2.0.0', '10.0.0') == -1

    def test_v_prefix_tolerated(self):
        assert version_mod.compare_versions('v1.2.3', '1.2.3') == 0

    def test_prerelease_below_release(self):
        assert version_mod.compare_versions('1.2.3-beta.1', '1.2.3') == -1

    def test_missing_segments_padded(self):
        assert version_mod.compare_versions('1.2', '1.2.0') == 0
        assert version_mod.compare_versions('1', '1.0.1') == -1

    def test_garbage_never_raises(self):
        """更新检查不能因为一个怪版本号把进程带崩"""
        for bad in (None, '', 'abc', 'v', '...', '1.x.3'):
            assert isinstance(version_mod.parse_version(bad), tuple)

    def test_app_version_is_semver(self):
        import re
        assert re.fullmatch(r'\d+\.\d+\.\d+', version_mod.format_version())


# ==================== 清单解析 ====================


def _manifest(ver='9.9.9', **kw):
    m = {
        'version': ver,
        'channel': 'stable',
        'notes': '测试更新',
        'published_at': '2026-09-04',
        'packages': {
            'installer': {
                'url': 'https://example.com/Docflowing_Setup.exe',
                'sha256': 'deadbeef',
                'size': 1234,
            }
        },
    }
    m.update(kw)
    return m


class TestEvaluateManifest:

    def test_newer_version_detected(self):
        info = updater.evaluate_manifest(_manifest('99.0.0'))
        assert info is not None
        assert info['latest_version'] == '99.0.0'
        assert info['url'].endswith('Docflowing_Setup.exe')

    def test_same_version_ignored(self):
        assert updater.evaluate_manifest(_manifest(version_mod.format_version())) is None

    def test_older_version_ignored(self):
        assert updater.evaluate_manifest(_manifest('0.0.1')) is None

    def test_min_required_marks_forced(self):
        info = updater.evaluate_manifest(_manifest('99.0.0', min_required='99.0.0'))
        assert info['forced'] is True

    def test_no_forced_when_already_above_min(self):
        info = updater.evaluate_manifest(_manifest('99.0.0', min_required='0.0.1'))
        assert info['forced'] is False

    def test_stable_client_rejects_beta_manifest(self):
        assert updater.evaluate_manifest(_manifest('99.0.0', channel='beta')) is None

    def test_missing_packages_returns_none(self):
        assert updater.evaluate_manifest({'version': '99.0.0'}) is None

    def test_non_exe_url_falls_back_to_safe_name(self):
        m = _manifest('99.0.0')
        m['packages']['installer']['url'] = 'https://example.com/evil.sh'
        info = updater.evaluate_manifest(m)
        assert info['filename'].endswith('.exe')


# ==================== 下载与校验（本地 HTTP） ====================


class _Handler(BaseHTTPRequestHandler):
    """提供 /version.json 与 /Docflowing_Setup.exe，支持 Range。"""

    payload = b''
    manifest = b'{}'
    fail_sha = False

    def log_message(self, *args):
        pass

    def _send(self, body, status=200, headers=None):
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith('/version.json'):
            self._send(self.manifest, headers={'Content-Type': 'application/json'})
            return

        data = self.payload
        rng = self.headers.get('Range')
        if rng and rng.startswith('bytes='):
            start = int(rng[6:].split('-')[0])
            chunk = data[start:]
            self._send(
                chunk,
                status=206,
                headers={'Content-Range': f'bytes {start}-{len(data) - 1}/{len(data)}'},
            )
        else:
            self._send(data, headers={'Content-Length': str(len(data))})


@pytest.fixture
def update_env(tmp_path, monkeypatch):
    """把运行时目录与清单地址都指向测试环境，并重置模块状态。"""
    data_dir = tmp_path / 'runtime'
    data_dir.mkdir()
    monkeypatch.setenv('DOCFLOWING_DATA_DIR', str(data_dir))

    payload = os.urandom(64 * 1024) + b'Docflowing-fake-installer'
    server = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
    port = server.server_address[1]
    _Handler.payload = payload
    threading.Thread(target=server.serve_forever, daemon=True).start()

    ctx = {
        'server': server,
        'base': f'http://127.0.0.1:{port}',
        'payload': payload,
        'sha': hashlib.sha256(payload).hexdigest(),
        'update_dir': os.path.join(str(data_dir), 'updates'),
    }

    def set_manifest(m):
        _Handler.manifest = json.dumps(m).encode('utf-8')
        monkeypatch.setenv('DOCFLOWING_UPDATE_URL', f'{ctx["base"]}/version.json')

    ctx['set_manifest'] = set_manifest

    _reset_state()
    yield ctx

    server.shutdown()
    server.server_close()
    _reset_state()


def _reset_state():
    with updater._lock:
        updater._state.update({
            'state': updater.STATE_IDLE,
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
            'portable': False,
        })
    updater._downloader = None
    updater._last_auto_check = 0


def _wait_for(target_states, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = updater.get_status()['state']
        if st in target_states:
            return st
        time.sleep(0.05)
    return updater.get_status()['state']


class TestDownloadFlow:

    def test_silent_download_then_ready(self, update_env):
        """核心场景：检查到新版本后自动在后台下完，状态转为 ready。"""
        m = _manifest('99.0.0')
        m['packages']['installer'] = {
            'url': f'{update_env["base"]}/Docflowing_Setup.exe',
            'sha256': update_env['sha'],
            'size': len(update_env['payload']),
        }
        update_env['set_manifest'](m)

        updater.check_update(force=True)
        state = _wait_for({updater.STATE_READY, updater.STATE_FAILED})

        assert state == updater.STATE_READY, updater.get_status()['error']
        status = updater.get_status()
        assert status['latest_version'] == '99.0.0'
        assert os.path.isfile(status['installer_path'])
        with open(status['installer_path'], 'rb') as f:
            assert f.read() == update_env['payload']
        # 不应留下 .part 半成品
        assert not os.path.exists(status['installer_path'] + '.part')

    def test_ready_marker_written(self, update_env):
        """落定后要写 .ready.json，下次启动才能免 hash 直接恢复状态"""
        m = _manifest('99.0.0')
        m['packages']['installer'] = {
            'url': f'{update_env["base"]}/Docflowing_Setup.exe',
            'sha256': update_env['sha'],
            'size': len(update_env['payload']),
        }
        update_env['set_manifest'](m)
        updater.check_update(force=True)
        assert _wait_for({updater.STATE_READY, updater.STATE_FAILED}) == updater.STATE_READY

        marker = os.path.join(update_env['update_dir'], '99.0.0', updater.READY_MARKER)
        assert os.path.isfile(marker)
        with open(marker, 'r', encoding='utf-8') as f:
            assert json.load(f)['version'] == '99.0.0'

    def test_sha_mismatch_discards_file(self, update_env):
        """校验不通过必须丢弃，绝不能把没验过的文件交给安装器"""
        m = _manifest('99.0.0')
        m['packages']['installer'] = {
            'url': f'{update_env["base"]}/Docflowing_Setup.exe',
            'sha256': '0' * 64,
            'size': len(update_env['payload']),
        }
        update_env['set_manifest'](m)
        updater.check_update(force=True)
        state = _wait_for({updater.STATE_READY, updater.STATE_FAILED})

        assert state == updater.STATE_FAILED
        assert '校验失败' in updater.get_status()['error']
        assert updater.get_status()['installer_path'] is None

    def test_restores_ready_state_on_restart(self, update_env):
        """重启后应从标记恢复「已就绪」，而不是让用户重新下载一遍"""
        vdir = os.path.join(update_env['update_dir'], '99.0.0')
        os.makedirs(vdir, exist_ok=True)
        exe = os.path.join(vdir, 'Docflowing_Setup.exe')
        with open(exe, 'wb') as f:
            f.write(update_env['payload'])
        with open(os.path.join(vdir, updater.READY_MARKER), 'w', encoding='utf-8') as f:
            json.dump({'version': '99.0.0', 'file': 'Docflowing_Setup.exe',
                       'sha256': update_env['sha'], 'size': len(update_env['payload'])}, f)

        updater.restore_ready_state()
        status = updater.get_status()
        assert status['state'] == updater.STATE_READY
        assert status['installer_path'] == exe

    def test_stale_ready_marker_ignored(self, update_env):
        """装过的/落后版本的残留不该再提示"""
        vdir = os.path.join(update_env['update_dir'], '0.0.1')
        os.makedirs(vdir, exist_ok=True)
        exe = os.path.join(vdir, 'Docflowing_Setup.exe')
        with open(exe, 'wb') as f:
            f.write(b'x')
        with open(os.path.join(vdir, updater.READY_MARKER), 'w', encoding='utf-8') as f:
            json.dump({'version': '0.0.1', 'file': 'Docflowing_Setup.exe', 'size': 1}, f)

        updater.restore_ready_state()
        assert updater.get_status()['state'] != updater.STATE_READY

    def test_prunes_other_versions(self, update_env):
        stale = os.path.join(update_env['update_dir'], '1.0.0')
        os.makedirs(stale, exist_ok=True)
        updater.prune_old_updates(keep='99.0.0')
        assert not os.path.isdir(stale)

    def test_manifest_unreachable_is_silent(self, update_env, monkeypatch):
        """清单拉不到就当没更新，不能报错、不能卡住"""
        monkeypatch.setenv('DOCFLOWING_UPDATE_URL', 'http://127.0.0.1:1/version.json')
        status = updater.check_update(force=True)
        assert status['state'] == updater.STATE_IDLE
        assert status['error'] == ''

    def test_skipped_version_not_auto_downloaded(self, update_env):
        m = _manifest('99.0.0')
        m['packages']['installer'] = {
            'url': f'{update_env["base"]}/Docflowing_Setup.exe',
            'sha256': update_env['sha'],
            'size': len(update_env['payload']),
        }
        update_env['set_manifest'](m)
        updater._set_setting('skip_update_version', '99.0.0')

        try:
            status = updater.check_update(force=True)
            # 仍要告知有更新，但不自动下载
            assert status['state'] == updater.STATE_AVAILABLE
            assert status['latest_version'] == '99.0.0'
        finally:
            updater._set_setting('skip_update_version', '')

    def test_forced_update_ignores_skip(self, update_env):
        """强制更新（min_required 命中）不能被用户的跳过设置绕过"""
        m = _manifest('99.0.0', min_required='99.0.0')
        m['packages']['installer'] = {
            'url': f'{update_env["base"]}/Docflowing_Setup.exe',
            'sha256': update_env['sha'],
            'size': len(update_env['payload']),
        }
        update_env['set_manifest'](m)
        updater._set_setting('skip_update_version', '99.0.0')

        try:
            updater.check_update(force=True)
            state = _wait_for({updater.STATE_READY, updater.STATE_FAILED})
            assert state == updater.STATE_READY
        finally:
            updater._set_setting('skip_update_version', '')


# ==================== 安装路径校验 ====================


class TestInstallPathValidation:
    """installUpdate 暴露给页面 JS，必须拒绝任意可执行文件。"""

    @staticmethod
    def _api():
        from desktop_app import DesktopAPI
        from server import updater as up
        api = DesktopAPI()
        api._updater = up
        return api

    def test_rejects_non_exe(self, tmp_path, monkeypatch):
        monkeypatch.setenv('DOCFLOWING_DATA_DIR', str(tmp_path))
        api = self._api()
        r = api.installUpdate('C:\\Windows\\System32\\cmd.exe'.replace('cmd.exe', 'notepad.exe'))
        assert r['success'] is False

    def test_rejects_path_outside_update_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv('DOCFLOWING_DATA_DIR', str(tmp_path))
        outside = tmp_path / 'evil.exe'
        outside.write_bytes(b'MZ')
        api = self._api()
        r = api.installUpdate(str(outside))
        assert r['success'] is False
        assert '更新目录' in r['message']

    def test_rejects_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv('DOCFLOWING_DATA_DIR', str(tmp_path))
        api = self._api()
        r = api.installUpdate(str(tmp_path / 'updates' / '9.9.9' / 'nope.exe'))
        assert r['success'] is False
