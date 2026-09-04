// ==================== 应用更新 ====================
// 交互模型：默认「后台静默下载 → 下载好了才提示 → 用户点一下就装上」。
// 用户等待时间只剩安装那几秒，这是更新完成率的关键。
// 除非用户在设置里关掉自动下载，否则不会拿「发现新版本」去打断人。

var DocflowingUpdater = {
    state: null,
    _timer: null,
    _bannerShown: false,
    _lastRendered: '',

    // ────────── 轮询 ──────────

    start: function () {
        this.refresh();
        this._schedule();
    },

    _schedule: function () {
        var self = this;
        if (this._timer) clearTimeout(this._timer);
        // 下载中刷新快一点，让用户看到进度在动；其余情况没必要频繁打扰后端
        var st = this.state && this.state.state;
        var interval = (st === 'downloading') ? 1500 : 300000;
        this._timer = setTimeout(function () { self.refresh(); self._schedule(); }, interval);
    },

    refresh: async function () {
        try {
            const data = await apiFetch('/api/updater/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
                timeout: 10000,
                showError: false
            });
            const json = await data.json();
            if (json && json.success) this._apply(json.status);
        } catch (e) {
            // 更新状态获取失败不该干扰正常使用，静默吞掉
        }
    },

    _apply: function (status) {
        this.state = status;
        this._renderBanner();
        if (typeof this._settingsHook === 'function') this._settingsHook(status);
    },

    // ────────── 操作 ──────────

    check: async function () {
        try {
            const data = await apiFetch('/api/updater/check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
                timeout: 20000,
                showError: false
            });
            const json = await data.json();
            if (json && json.success) {
                this._apply(json.status);
                if (json.status.state === 'idle') showToast('已是最新版本', 'success');
            }
        } catch (e) {
            showToast('检查更新失败，请检查网络', 'error');
        }
    },

    download: async function () {
        try {
            await apiFetch('/api/updater/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
                timeout: 15000,
                showError: false
            });
            this.refresh();
        } catch (e) {
            showToast('开始下载失败', 'error');
        }
    },

    cancel: async function () {
        try {
            await apiFetch('/api/updater/cancel', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}), timeout: 15000, showError: false
            });
            this.refresh();
        } catch (e) { /* 忽略 */ }
    },

    skip: async function () {
        var v = this.state && this.state.latest_version;
        if (!v) return;
        try {
            const r = await apiFetch('/api/updater/skip', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ version: v }), timeout: 15000, showError: false
            });
            const json = await r.json();
            if (json && json.success === false) { showToast(json.message || '操作失败', 'error'); return; }
            this._apply(json.status);
        } catch (e) { /* 忽略 */ }
    },

    dismiss: async function () {
        try {
            const r = await apiFetch('/api/updater/dismiss', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}), timeout: 15000, showError: false
            });
            const json = await r.json();
            if (json && json.success) this._apply(json.status);
        } catch (e) { /* 忽略 */ }
    },

    setAutoDownload: async function (enabled) {
        try {
            const r = await apiFetch('/api/updater/auto_download', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: enabled }), timeout: 15000, showError: false
            });
            const json = await r.json();
            if (json && json.success) this._apply(json.status);
        } catch (e) { /* 忽略 */ }
    },

    install: async function () {
        var s = this.state;
        if (!s || !s.installer_path) { showToast('安装包尚未就绪', 'error'); return; }
        if (!window.electronAPI || !window.electronAPI.installUpdate) {
            showToast('当前不是桌面模式，请手动运行下载好的安装包', 'error');
            return;
        }
        showToast('正在启动安装程序…', 'success');
        try {
            const r = await window.electronAPI.installUpdate(s.installer_path, true);
            // 成功时应用会立刻退出，一般走不到这里
            if (r && r.success === false) showToast(r.message || '启动安装程序失败', 'error');
        } catch (e) {
            showToast('启动安装程序失败: ' + e.message, 'error');
        }
    },

    openDownloadPage: function () {
        var url = (this.state && this.state.download_url) || 'https://github.com/doonly1/Docflowing/releases/latest';
        if (window.electronAPI && window.electronAPI.openExternal) window.electronAPI.openExternal(url);
        else window.open(url, '_blank');
    },

    // ────────── 提示条 ──────────

    _shouldShowBanner: function (s) {
        if (!s) return false;
        if (s.state === 'ready') return true;
        if (s.state === 'downloading') return true;
        if (s.state === 'failed') return true;
        // 关掉自动下载的用户，才需要「发现新版本」这条提示；
        // 开着自动下载的话会直接进 downloading → ready，不必多打扰一次。
        if (s.state === 'available' && !s.auto_download) return true;
        return false;
    },

    _renderBanner: function () {
        var host = document.getElementById('updateBannerHost');
        if (!host) return;
        var s = this.state;
        if (!this._shouldShowBanner(s)) {
            if (this._bannerShown) { host.innerHTML = ''; this._bannerShown = false; }
            return;
        }

        var body = '';
        var btns = '';

        if (s.state === 'ready') {
            body = '<div style="font-size:13px;font-weight:600;color:#1a1a2e;">新版本 ' + _updaterEsc(s.latest_version) + ' 已就绪</div>'
                + '<div style="font-size:11px;color:#888;margin-top:3px;">下载完成，安装约需 1 分钟</div>'
                + (s.notes ? '<div style="font-size:11px;color:#666;margin-top:6px;line-height:1.6;max-height:60px;overflow:auto;">' + _updaterEsc(s.notes) + '</div>' : '');
            btns = '<button onclick="DocflowingUpdater.install()" style="padding:5px 14px;background:#e94560;color:#fff;border:none;border-radius:4px;font-size:12px;cursor:pointer;">立即安装</button>'
                 + '<button onclick="DocflowingUpdater.dismiss()" style="padding:5px 10px;background:transparent;color:#888;border:1px solid #ddd;border-radius:4px;font-size:12px;cursor:pointer;">稍后</button>';
        } else if (s.state === 'downloading') {
            var pct = Math.round(s.progress || 0);
            body = '<div style="font-size:13px;color:#1a1a2e;">正在后台下载 ' + _updaterEsc(s.latest_version) + '…</div>'
                + '<div style="margin-top:6px;height:4px;background:#eee;border-radius:2px;overflow:hidden;">'
                + '<div style="height:100%;width:' + pct + '%;background:#e94560;transition:width .3s;"></div></div>'
                + '<div style="font-size:11px;color:#888;margin-top:4px;">' + pct + '% · 下载完成后会提示你安装</div>';
            btns = '<button onclick="DocflowingUpdater.cancel()" style="padding:4px 10px;background:transparent;color:#888;border:1px solid #ddd;border-radius:4px;font-size:12px;cursor:pointer;">取消</button>';
        } else if (s.state === 'failed') {
            body = '<div style="font-size:13px;color:#1a1a2e;">更新下载失败</div>'
                + '<div style="font-size:11px;color:#888;margin-top:3px;">' + _updaterEsc(s.error || '网络异常') + '</div>';
            btns = '<button onclick="DocflowingUpdater.download()" style="padding:5px 14px;background:#e94560;color:#fff;border:none;border-radius:4px;font-size:12px;cursor:pointer;">重试</button>'
                 + '<button onclick="DocflowingUpdater.openDownloadPage()" style="padding:5px 10px;background:transparent;color:#888;border:1px solid #ddd;border-radius:4px;font-size:12px;cursor:pointer;">手动下载</button>'
                 + '<button onclick="DocflowingUpdater.dismiss()" style="padding:5px 10px;background:transparent;color:#bbb;border:none;font-size:12px;cursor:pointer;">关闭</button>';
        } else {
            body = '<div style="font-size:13px;font-weight:600;color:#1a1a2e;">发现新版本 ' + _updaterEsc(s.latest_version) + '</div>'
                + (s.notes ? '<div style="font-size:11px;color:#666;margin-top:6px;line-height:1.6;max-height:60px;overflow:auto;">' + _updaterEsc(s.notes) + '</div>' : '');
            btns = '<button onclick="DocflowingUpdater.download()" style="padding:5px 14px;background:#e94560;color:#fff;border:none;border-radius:4px;font-size:12px;cursor:pointer;">下载更新</button>'
                 + '<button onclick="DocflowingUpdater.skip()" style="padding:5px 10px;background:transparent;color:#888;border:1px solid #ddd;border-radius:4px;font-size:12px;cursor:pointer;">跳过</button>';
        }

        var html = '<div style="background:#fff;border-radius:10px;padding:12px 14px;width:280px;'
            + 'box-shadow:0 6px 24px rgba(0,0,0,0.14);border:1px solid rgba(0,0,0,0.08);">'
            + body
            + '<div style="display:flex;gap:6px;justify-content:flex-end;margin-top:10px;flex-wrap:wrap;">' + btns + '</div>'
            + '</div>';

        if (html !== this._lastRendered) {
            host.innerHTML = html;
            this._lastRendered = html;
        }
        this._bannerShown = true;
    },

    // ────────── 设置面板 ──────────

    // 由 main.js 的设置弹窗调用，渲染「更新」卡片
    renderSettingsSection: function () {
        var s = this.state || { current_version: '', state: 'idle' };
        var line = '';

        if (s.state === 'checking') line = '正在检查…';
        else if (s.state === 'downloading') line = '正在后台下载 ' + _updaterEsc(s.latest_version || '') + '（' + Math.round(s.progress || 0) + '%）';
        else if (s.state === 'ready') line = '<span style="color:#c0392b;">新版本 ' + _updaterEsc(s.latest_version) + ' 已下载完成</span>';
        else if (s.state === 'failed') line = '<span style="color:#c0392b;">下载失败：' + _updaterEsc(s.error || '') + '</span>';
        else if (s.state === 'available') line = '有新版本 ' + _updaterEsc(s.latest_version) + ' 可用';
        else line = '当前已是最新版本（' + _updaterEsc(s.current_version) + '）';

        var action = '';
        if (s.state === 'ready') {
            action = '<button onclick="DocflowingUpdater.install()" style="padding:4px 12px;background:#e94560;color:#fff;border:none;border-radius:4px;font-size:12px;cursor:pointer;">立即安装</button>';
        } else if (s.state === 'downloading') {
            action = '<button onclick="DocflowingUpdater.cancel()" style="padding:4px 12px;background:#6c757d;color:#fff;border:none;border-radius:4px;font-size:12px;cursor:pointer;">取消</button>';
        } else if (s.state === 'available') {
            action = '<button onclick="DocflowingUpdater.download()" style="padding:4px 12px;background:#e94560;color:#fff;border:none;border-radius:4px;font-size:12px;cursor:pointer;">下载更新</button>';
        } else {
            action = '<button onclick="DocflowingUpdater.check()" style="padding:4px 12px;background:#6c757d;color:#fff;border:none;border-radius:4px;font-size:12px;cursor:pointer;">检查更新</button>';
        }

        return ''
            + '<div style="margin-bottom:16px;border-top:1px solid #eee;padding-top:12px;">'
            + '<div style="font-size:13px;color:#333;margin-bottom:6px;">应用更新 <span style="font-size:11px;color:#aaa;">v' + _updaterEsc(s.current_version) + '</span></div>'
            + '<div style="font-size:11px;color:#999;margin-bottom:8px;">' + line + '</div>'
            + '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:12px;color:#555;margin-bottom:8px;">'
            + '<input type="checkbox" id="settingAutoUpdate" ' + (s.auto_download !== false ? 'checked' : '') + ' onchange="DocflowingUpdater.setAutoDownload(this.checked)">'
            + '后台自动下载更新（下载完成后提示我安装）'
            + '</label>'
            + '<div style="display:flex;gap:8px;">' + action
            + (s.state === 'ready' || s.state === 'available'
                ? '<button onclick="DocflowingUpdater.skip()" style="padding:4px 12px;background:transparent;color:#888;border:1px solid #ddd;border-radius:4px;font-size:12px;cursor:pointer;">跳过此版本</button>'
                : '')
            + '</div>'
            + '</div>';
    },

    // 设置弹窗打开时由 main.js 注册：状态变化时就地刷新「更新」卡片，
    // 这样下载进度不用重新打开设置也能看到。
    _settingsHook: null
};

function _updaterEsc(s) {
    return String(s === undefined || s === null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// 应用启动后开始轮询更新状态（失败静默，不打扰用户）
(function () {
    function boot() {
        try {
            DocflowingUpdater.start();
        } catch (e) {
            console.warn('[updater] 启动轮询失败', e);
        }
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
