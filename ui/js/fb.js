var FileBase = {

    _lsGet: function(key) { try { return localStorage.getItem(key); } catch(e) { return null; } },
    _lsSet: function(key, val) { try { localStorage.setItem(key, val); } catch(e) {} },
    _lsDel: function(key) { try { localStorage.removeItem(key); } catch(e) {} },

    // ---- Granular permission bit constants ----
    PERM_VIEW:   1,
    PERM_CREATE: 2,
    PERM_EDIT:   4,
    PERM_RENAME: 8,
    PERM_MOVE:   16,
    PERM_COPY:   32,
    PERM_DELETE: 64,
    PERM_MANAGE: 128,


    hasPerm: function(bits) {
        return (this.fbPermMask & bits) === bits;
    },


    currentFbId: null,
    fbCurrentPermission: null,
    fbIsRemote: false,  // 是否为远程文件库（其他节点共享的）
    selectedDocs: {},
    _lastClickedIndex: null,
    _openingPath: null,
    _undoStack: [],
    _MAX_UNDO: 10,
    currentSort: { field: 'mtime', asc: false },
    currentPath: [],
    fbName: '',
    fbPermMask: 0,
    fbLocalPath: '',
    fbLocalCurrentSubdir: '',
    fbCategoryTree: null,
    fbTreeLoaded: false,
    fbExpandedTreePaths: {},  // 跟踪手动展开的树节点路径
    fbDisplayPath: '',
    fbClipboard: null,
    _renderVersion: 0,  // 用于取消因异步竞态导致的冗余渲染

    api: function(url, method, body) {
        var o = {
            method: method || 'GET',
            headers: { 'Content-Type': 'application/json' }
        };
        if (body && method !== 'GET') o.body = JSON.stringify(body);
        return fetch(url, o).then(function(r) { return r.json(); }).catch(function() { return { success: false, message: '请求失败' }; });
    },

    _pushUndo: function(action) {
        this._undoStack.push(action);
        if (this._undoStack.length > this._MAX_UNDO) {
            this._undoStack.shift();
        }
    },

    _performUndo: async function() {
        var action = this._undoStack.pop();
        if (!action) { showToast('没有可撤销的操作', 'info'); return; }
        var self = this;
        try {
            switch (action.type) {
                case 'delete':
                    var trashRes = await this.api('/api/fb/' + this.currentFbId + '/local-files/trash-items', 'GET');
                    var trashItems = trashRes.success ? (trashRes.items || []) : [];
                    for (var i = 0; i < action.items.length; i++) {
                        var origPath = action.items[i].path;
                        var matched = null;
                        for (var j = 0; j < trashItems.length; j++) {
                            if (trashItems[j].original_path === origPath) {
                                matched = trashItems[j];
                                break;
                            }
                        }
                        if (matched) {
                            await this.api('/api/fb/' + this.currentFbId + '/local-files/trash-restore', 'POST', {name: matched.name});
                        } else {
                            await this.api('/api/fb/trash-restore', 'POST', {name: action.items[i].name});
                        }
                    }
                    break;
                case 'move':
                    for (var i = 0; i < action.items.length; i++) {
                        var item = action.items[i];
                        var name = item.name;
                        var newPath = (action.dest ? action.dest + '/' : '') + name;
                        var sepIdx = item.oldPath.replace(/\\/g, '/').lastIndexOf('/');
                        var oldParent = sepIdx >= 0 ? item.oldPath.substring(0, sepIdx) : '';
                        await this.api('/api/fb/' + this.currentFbId + '/local-files/move', 'PUT', {sources: [newPath], dest: oldParent});
                    }
                    break;
                case 'rename':
                    var newPath = (action.parentDir ? action.parentDir + '/' : '') + action.newName;
                    await this.api('/api/fb/' + this.currentFbId + '/local-files/rename', 'PUT', {path: newPath, new_name: action.oldName});
                    break;
                case 'copy':
                    var cpPaths = [];
                    for (var i = 0; i < action.items.length; i++) {
                        cpPaths.push((action.dest ? action.dest + '/' : '') + action.items[i].name);
                    }
                    await this.api('/api/fb/' + this.currentFbId + '/local-files', 'DELETE', {paths: cpPaths});
                    break;
                case 'newFolder':
                case 'newFile':
                    await this.api('/api/fb/' + this.currentFbId + '/local-files', 'DELETE', {paths: [action.path]});
                    break;
            }
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } catch (e) {
            showToast('撤销失败: ' + (e.message || ''), 'error');
            this._undoStack.push(action);
        }
    },

    refreshAuthRole: async function() {
        try {
            var resp = await fetch('/api/user/me');
            var data = await resp.json();
            if (data.success && data.role) {
                window.authRole = data.role;
                window.authUserId = data.user_id;
                try { localStorage.setItem('docflow_role', data.role); } catch(e) {}
            }
        } catch (e) {
            console.warn('refreshAuthRole failed, will use cached role:', window.authRole);
        }
    },

    refreshUserCache: async function() {
        // 本机模式，无需用户缓存
    },

    getUserRole: function() {
        return window.authRole || 'viewer';
    },

    init: async function() {
        this.selectedDocs = {};
        this.currentSort = { field: 'mtime', asc: false };
        // 如果 main.js 已加载用户角色，跳过重复请求
        if (!window.authRole) await this.refreshAuthRole();
        // 窗口重新获得焦点时自动刷新（从OS删除文件后切回）
        if (!this._focusRefreshRegistered) {
            this._focusRefreshRegistered = true;
            var self = this;
            window.addEventListener('focus', function() {
                if (self.currentFbId) {
                    self.renderDetail();
                }
            });
        }
        // 记录当前渲染版本，用于后续检测是否被取消
        var myVersion = ++this._renderVersion;
        await this.refreshUserCache();
        // 异步恢复后检查版本：如果版本已被其他操作（如 switchTab 守卫）递增，则放弃本次渲染
        if (this._renderVersion !== myVersion) return;
        if (this.currentFbId) {
            await this.renderDetail();
        } else {
            await this.renderKbList();
        }
    },

    goBackToList: function() {
        this.currentFbId = null;
        this.fbLocalPath = '';
        this.renderKbList();
    },

    navigateTo: function(view) {
        if (typeof globalNavigateTo === 'function') { globalNavigateTo(view); return; }
        if (view === 'home') {
            document.getElementById('content-view').style.display = 'none';
            document.getElementById('home-view').style.display = '';
            this.currentFbId = null;
        } else if (view === 'fb') {
            document.getElementById('home-view').style.display = 'none';
            document.getElementById('content-view').style.display = '';
            this.init();
        }
    },

    refreshKbList: async function() {
        this.hideContextMenu();
        if (this.currentFbId) {
            await this.renderDetail();
        } else {
            await this.renderKbList();
        }
    },

    renderKbList: async function() {
        try {
            this.currentFbId = null;
            this.fbName = '';
            this.fbLocalPath = '';
            this.currentPath = [{ id: null, name: '文件库', type: 'home' }];
            this._lsDel('docflow_current_fb_id');
            this._lsDel('docflow_current_fb_name');
            this._lsDel('docflow_current_fb_local_path');
            this._lsDel('docflow_current_fb_display_path');
            this._lsDel('docflow_current_fb_permission');
            this._lsDel('docflow_current_subdir');
            this.fbExpandedTreePaths = {};

            // 同步更新当前 fb 标签状态为列表态
            if (typeof tabManager !== 'undefined') {
                var activeTab = tabManager._findById(tabManager.activeTabId);
                if (activeTab && activeTab.type === 'fb') {
                    activeTab.state.fbId = null;
                    activeTab.state.fbName = '文件库';
                    activeTab.state.fbLocalPath = '';
                    activeTab.state.fbDisplayPath = '';
                    activeTab.state.fbPermission = '';
                    activeTab.state.fbSubdir = '';
                    activeTab.state.fbCurrentPath = [];
                    activeTab._identified = false;
                    tabManager._renderBar();
                }
            }
            var role = this.getUserRole();

            var kbView = document.getElementById('content-view');
            if (!kbView) {
                console.warn('content-view not found, cannot render list');
                return;
            }

            var h = '<div class="fb-explorer">';
            h += '<div class="fb-breadcrumb"><span class="fb-bc-current">🏠 文件库</span></div>';
            h += '<div class="fb-explorer-body" style="border-radius:6px;border:1px solid #e1e4e8;background:#fff">';
            h += '<div class="fb-file-pane" style="width:100%">';
            h += '<div class="fb-file-toolbar">';
            h += '<input type="text" id="fb-search-input" placeholder="搜索文档..." onkeydown="if(event.keyCode===13) FileBase.search()">';
            h += '<button onclick="FileBase.search()">🔍</button>';
            h += '<button onclick="FileBase.showCreateRootFolder()">📁 新建文件库</button>';
            h += '<button onclick="FileBase.showCreateNetworkRootFolder()">🌐 新建网络文件库</button>';
            h += '<span class="fb-toolbar-spacer"></span>';
            h += '<span id="fb-online-nodes"><span class="fb-p2p-indicator fb-p2p-offline" title="扫描中...">◉</span></span>';
            h += '<button onclick="FileBase.showTrash()" title="回收站" style="border:none;background:transparent;font-size:15px;padding:2px 6px">🗑️</button>';
            h += '<button class="fb-p2p-settings-btn" onclick="FileBase.showP2PSettings()" title="P2P 节点设置">⚙️</button>';
            h += '</div>';
            h += '<div class="fb-file-body" id="fb-grid-container" oncontextmenu="FileBase.showKbListContextMenu(event)"><div class="fb-empty">刷新中...</div></div>';
            h += '</div></div></div>';
            kbView.innerHTML = h;

            var grid = document.getElementById('fb-grid-container');
            if (!grid) {
                console.warn('fb-grid-container not found');
                return;
            }

            var res = await this.api('/api/fb/list', 'GET');
            if (!res || !res.success) {
                grid.innerHTML = '<div class="fb-empty">刷新失败: ' + (res && res.message ? res.message : '未知错误') + '</div>';
                return;
            }

            var kbs = res.kbs || [];

            if (kbs.length === 0) {
                grid.innerHTML = '<div class="fb-empty">暂无文件库，右键区域创建</div>';
                return;
            }

            var html = '<div class="fb-grid">';
            for (var i = 0; i < kbs.length; i++) {
                var kb = kbs[i];
                var initialCountHtml = '';
                if (kb.total_files !== undefined && kb.total_files !== null) {
                    initialCountHtml = '<small style="color:#666;font-size:11px;">文件数: ' + kb.total_files + '</small>';
                }
                html += '<div class="fb-card" data-fb-id="' + kb.id + '" data-fb-permission="' + kb.permission + '" data-fb-name="' + escapeHtmlText(kb.name) + '" data-fb-type="' + (kb.filebase_type || 'local') + '" data-fb-local-path="' + escapeHtmlText(kb.local_path || '') + '" data-fb-display-path="' + escapeHtmlText(kb.display_path || '') + '" onclick="FileBase.openKb(\'' + kb.id + '\',\'' + kb.permission + '\',\'' + escapeHtmlText(kb.name) + '\',\'' + escapeHtmlText(kb.local_path || '') + '\',\'' + escapeHtmlText(kb.display_path || '') + '\')">';
                html += '<h3>📁 ' + escapeHtmlText(kb.name) + '</h3>';
                html += '<div class="fb-card-meta">' + (kb.display_path || kb.local_path || '') + '</div>';
                html += '<div class="fb-card-sync-status" id="sync-status-' + kb.id + '" data-fb-id="' + kb.id + '">' + initialCountHtml + '</div>';
                html += '</div>';
            }
            html += '</div>';
            grid.innerHTML = html;

            for (var i = 0; i < kbs.length; i++) {
                this._loadSyncStatus(kbs[i].id);
            }

            this.initNodePolling();
        } catch (e) {
            console.error('renderKbList error:', e);
            var grid = document.getElementById('fb-grid-container');
            if (grid) {
                grid.innerHTML = '<div class="fb-empty">刷新出错: ' + e.message + '</div>';
            }
        }
    },

    _loadSyncStatus: async function(kbId) {
        try {
            var res = await this.api('/api/fb/' + kbId + '/sync-status', 'GET');
            var statusEl = document.getElementById('sync-status-' + kbId);
            if (!statusEl || !res.success) return;

            var status = res.status || {};
            var total = status.total_files || 0;
            var syncable = status.syncable_files || 0;
            var synced = status.synced_files || 0;

            var display = '文件数: ' + total;
            if (res.enabled) {
                display = '文件数: ' + total + ' | 同步: ' + total + '/' + syncable + '/' + synced;
            }

            statusEl.innerHTML = '<small style="color:#666;font-size:11px;">' + display + '</small>';
        } catch (e) {
            console.warn('Failed to load sync status for ' + kbId, e);
        }
    },

    showCreateRootFolder: function() {
        this._showLocalPathDialog();
    },

    _showLocalPathDialog: function() {
        var self = this;
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal" style="max-width:420px">';
        h += '<h3>📁 新建文件库</h3>';
        h += '<div style="margin-bottom:12px">';
        h += '<input type="text" id="fb-local-name" placeholder="输入文件库名称" style="width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px;box-sizing:border-box">';
        h += '</div>';
        h += '<div class="fb-modal-actions">';
        h += '<button class="fb-btn-primary" onclick="FileBase._doCreateLocalRootFolder()">创建</button>';
        h += '<button class="fb-btn-cancel" onclick="FileBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'fb-modal-overlay') self.closeModal(); });
        setTimeout(function() { document.getElementById('fb-local-name').focus(); }, 100);
    },

    _doCreateLocalRootFolder: async function() {
        var name = (document.getElementById('fb-local-name').value || '').trim();
        if (!name) { showToast('请输入文件库名称', 'error'); return; }
        this.closeModal();
        await this._createLocalRootFolder(name);
    },

    _createLocalRootFolder: async function(name) {
        var self = this;
        var res = await this.api('/api/fb/create-folder', 'POST', {
            filebase_type: 'local',
            name: name
        });
        if (res.success) {
            await self.renderKbList();
        } else {
            showToast(res.message || '添加失败', 'error');
        }
    },

    // ─────────────────── 网络文件库 ───────────────────

    showCreateNetworkRootFolder: function() {
        this._showNetworkPathDialog();
    },

    _showNetworkPathDialog: function() {
        var self = this;
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal" style="max-width:420px">';
        h += '<h3>🌐 新建网络文件库</h3>';
        h += '<div style="margin-bottom:12px">';
        h += '<input type="text" id="fb-net-path" placeholder="如 \\\\server\\share\\folder" style="width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px;box-sizing:border-box">';
        h += '</div>';
        h += '<div class="fb-modal-actions">';
        h += '<button class="fb-btn-primary" onclick="FileBase._doCreateNetworkRootFolder()">创建</button>';
        h += '<button class="fb-btn-cancel" onclick="FileBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'fb-modal-overlay') self.closeModal(); });
        setTimeout(function() { document.getElementById('fb-net-path').focus(); }, 100);
    },

    _doCreateNetworkRootFolder: async function() {
        var networkPath = (document.getElementById('fb-net-path').value || '').trim();
        if (!networkPath) { showToast('请输入网络路径', 'error'); return; }
        var parts = networkPath.replace(/\\/g, '/').split('/').filter(function(p) { return p && p !== ''; });
        var name = parts.length > 0 ? parts[parts.length - 1] : '网络文件库';
        this.closeModal();
        await this._createNetworkRootFolder(name, networkPath);
    },

    _createNetworkRootFolder: async function(name, networkPath) {
        var self = this;
        var res = await this.api('/api/fb/create-folder', 'POST', {
            name: name,
            filebase_type: 'net',
            network_path: networkPath
        });
        if (res.success) {
            await self.renderKbList();
        } else {
            showToast(res.message || '创建失败', 'error');
        }
    },

    showKbListContextMenu: function(event) {
        event.preventDefault();
        event.stopPropagation();
        this.hideContextMenu();

        var target = event.target;
        var kbCard = target.closest('.fb-card');

        var menu = document.createElement('div');
        menu.className = 'fb-context-menu';
        menu.id = 'fb-context-menu';

        if (kbCard) {
            var kbId = kbCard.getAttribute('data-fb-id');
            var kbName = kbCard.getAttribute('data-fb-name');
            var kbPermission = kbCard.getAttribute('data-fb-permission');
            var kbLocalPath = kbCard.getAttribute('data-fb-local-path');
            var kbDisplayPath = kbCard.getAttribute('data-fb-display-path');
            menu.innerHTML = this._buildKbCardContextMenu(kbId, kbName, kbPermission, kbLocalPath, kbDisplayPath);
        } else {
            var emptyMenu = '<div class="fb-menu-item" onclick="FileBase.showCreateRootFolder();FileBase.hideContextMenu()"><span class="icon">📁</span> 新建文件库</div>';
            if (window.authRole === 'admin') {
                emptyMenu += '<div class="fb-menu-item" onclick="FileBase.showCreateNetworkRootFolder();FileBase.hideContextMenu()"><span class="icon">🌐</span> 新建网络文件库</div>';
            }
            emptyMenu += '<div class="fb-menu-divider"></div><div class="fb-menu-item" onclick="FileBase.refreshKbList()"><span class="icon">🔄</span> 刷新</div>';
            menu.innerHTML = emptyMenu;
        }

        menu.style.left = Math.min(event.clientX, window.innerWidth - 180) + 'px';
        menu.style.top = Math.min(event.clientY, window.innerHeight - 160) + 'px';
        document.body.appendChild(menu);

        this.fbHideContextMenuHandler = function() { FileBase.hideContextMenu(); };
        setTimeout(function() {
            document.addEventListener('click', FileBase.fbHideContextMenuHandler);
        }, 0);
    },

    _buildKbCardContextMenu: function(kbId, kbName, permission, localPath, displayPath) {
        var escId = kbId.replace(/'/g, "\\'");
        var escName = (kbName || '').replace(/'/g, "\\'");
        var escLocalPath = (localPath || '').replace(/'/g, "\\'");
        var escDisplayPath = (displayPath || '').replace(/'/g, "\\'");

        var h = '';
        if (permission === 'manage') {
            h += '<div class="fb-menu-item" onclick="FileBase.kbListManage(\'' + escId + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="2.8" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="7" r="4.8" stroke="currentColor" stroke-width=".7" stroke-dasharray="1.3 1.3"/></svg></span> 管理</div>';
            h += '<div class="fb-menu-item" onclick="FileBase.showShareDialog(\'' + escId + '\',\'' + escName + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M4 4.5a2 2 0 100-4 2 2 0 000 4zM10 7a2 2 0 100-4 2 2 0 000 4zM4 13.5a2 2 0 100-4 2 2 0 000 4z" stroke="currentColor" stroke-width="1.2"/><path d="M6 6l4 1M6 8l4-1" stroke="currentColor" stroke-width="1.2"/></svg></span> 共享...</div>';
            h += '<div class="fb-menu-divider"></div>';
            h += '<div class="fb-menu-item" onclick="FileBase.toggleSync(\'' + escId + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M4 9.5a2.5 2.5 0 01-.5-4.97A3 3 0 019.5 6a1.8 1.8 0 01.5 3.5H4z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7 6v4M6 7l1-1.5L8 7" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 同步到知识库</div>';
            h += '<div class="fb-menu-item" onclick="FileBase.convertDoc(\'' + escId + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 2.5h4l3 3v6a1 1 0 01-1 1H2a1 1 0 01-1-1v-8a1 1 0 011-1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M6 2.5v3h3" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M9 8.5l1.5-1.5L9 5.5M10.5 7H8" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span> doc转docx</div>';
            h += '<div class="fb-menu-divider"></div>';
            h += '<div class="fb-menu-item" onclick="FileBase.kbListRename(\'' + escId + '\',\'' + escName + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M9.5 1.5l3 3-8 8H1.5v-3l8-8z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M8 3l3 3" stroke="currentColor" stroke-width="1.2"/></svg></span> 重命名</div>';
            h += '<div class="fb-menu-item" onclick="FileBase.kbListCopy(\'' + escId + '\',\'' + escName + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2.5 1.5h7a1 1 0 011 1v7a1 1 0 01-1 1h-7a1 1 0 01-1-1v-7a1 1 0 011-1z" stroke="currentColor" stroke-width="1.1"/><path d="M4.5 4h7a1 1 0 011 1v7a1 1 0 01-1 1h-7a1 1 0 01-1-1V5a1 1 0 011-1z" stroke="currentColor" stroke-width="1.1"/></svg></span> 复制</div>';
            h += '<div class="fb-menu-divider"></div>';
            h += '<div class="fb-menu-item" onclick="FileBase.kbListDelete(\'' + escId + '\',\'' + escName + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 4h8l-.8 8a1 1 0 01-1 .9H4.8a1 1 0 01-1-.9L3 4z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M2 3.5h10M5.5 2h3a1 1 0 011 1v.5h-5V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg></span> 删除</div>';
        }
        return h;
    },

    toggleSync: async function(kbId) {
        this.hideContextMenu();
        try {
            var res = await this.api('/api/fb/' + kbId + '/sync-status', 'GET');
            if (!res.success) {
                showToast('获取同步状态失败', 'error');
                return;
            }

            var newEnabled = !res.enabled;
            var res2 = await this.api('/api/fb/' + kbId + '/sync', 'POST', { enabled: newEnabled });
            if (res2.success) {
                await this._loadSyncStatus(kbId);
            } else {
                showToast(res2.message || '操作失败', 'error');
            }
        } catch (e) {
            showToast('操作失败: ' + e.message, 'error');
        }
    },

    syncNow: async function(kbId) {
        this.hideContextMenu();
        try {
            var res = await this.api('/api/fb/' + kbId + '/sync-now', 'POST');
            if (!res.success) {
                showToast(res.message || '同步触发失败', 'error');
                return;
            }
            setTimeout(function() {
                FileBase._loadSyncStatus(kbId);
            }, 1000);
        } catch (e) {
            showToast('同步失败: ' + e.message, 'error');
        }
    },

    convertDoc: async function(kbId) {
        this.hideContextMenu();
        try {
            await this.api('/api/fb/' + kbId + '/convert-doc', 'POST');
        } catch (e) {
            showToast('转换失败: ' + e.message, 'error');
        }
    },

    kbListManage: function(kbId) {
        this.hideContextMenu();
        this.currentFbId = kbId;
        this.showSettings();
    },

    kbListRename: async function(kbId, oldName) {
        this.hideContextMenu();
        var newName = await showPrompt('重命名文件库：', oldName);
        if (!newName || !newName.trim() || newName.trim() === oldName) return;
        var res = await this.api('/api/fb/' + kbId, 'PUT', { name: newName.trim() });
        if (res.success) {
            await this.renderKbList();
        } else {
            showToast(res.message || '重命名失败', 'error');
        }
    },

    kbListCopy: async function(kbId, kbName) {
        this.hideContextMenu();
        var newName = await showPrompt('复制文件库为：', kbName + '_副本');
        if (!newName || !newName.trim()) return;
        var res = await this.api('/api/fb/copy-folder', 'POST', {
            kb_id: kbId,
            new_name: newName.trim()
        });
        if (res.success) {
            await this.renderKbList();
        } else {
            showToast(res.message || '复制失败', 'error');
        }
    },

    kbListDelete: async function(kbId, kbName) {
        this.hideContextMenu();
        if (!(await showConfirm('确定删除文件库 "' + kbName + '" 吗？'))) return;
        try {
            var res = await this.api('/api/fb/' + kbId, 'DELETE');
            if (res.success) {
                await this.renderKbList();
            } else {
                showToast(res.message || '删除失败', 'error');
            }
        } catch (e) {
            console.error('kbListDelete error:', e);
            showToast('删除请求失败: ' + e.message, 'error');
        }
    },

    openKb: async function(kbId, permission, name, localPath, displayPath) {
        // 通过 tabManager 管理标签
        if (typeof tabManager !== 'undefined') {
            // 查找是否已有该文件库的标签
            for (var i = 0; i < tabManager.tabs.length; i++) {
                if (tabManager.tabs[i].type === 'fb' && tabManager.tabs[i].state.fbId === kbId) {
                    tabManager.switchTab(tabManager.tabs[i].id);
                    return;
                }
            }
            // 复用当前未标识的 fb 标签（列表态），进入具体库
            var activeTab = tabManager._findById(tabManager.activeTabId);
            if (activeTab && activeTab.type === 'fb' && !activeTab._identified) {
                activeTab._identified = true;
                activeTab.state = {
                    fbId: kbId,
                    fbName: name,
                    fbLocalPath: localPath,
                    fbDisplayPath: displayPath,
                    fbPermission: permission,
                    fbSubdir: ''
                };
                this.currentFbId = kbId;
                this.fbCurrentPermission = permission;
                this.fbPermMask = permission === 'manage' ? 255 : (permission === 'edit' ? 127 : 1);
                this.fbIsRemote = !localPath;
                this.selectedDocs = {};
                this.fbName = name || '';
                this.fbLocalPath = localPath || '';
                this.fbDisplayPath = displayPath || '';
                this.fbLocalCurrentSubdir = '';
                this.currentPath = [{ id: kbId, name: name || '未知文件库', type: 'kb' }];
                this.currentSort = { field: 'mtime', asc: false };
                this.fbCategoryTree = null;
                this.fbTreeLoaded = false;
                this.fbExpandedTreePaths = {};
                this._lsSet('docflow_current_fb_id', kbId);
                this._lsSet('docflow_current_fb_permission', permission);
                this._lsSet('docflow_current_fb_name', name || '');
                this._lsSet('docflow_current_fb_local_path', localPath || '');
                this._lsSet('docflow_current_fb_display_path', displayPath || '');
                this._lsDel('docflow_current_subdir');
                tabManager._renderBar();
                await this.renderDetail();
                return;
            }
            // 创建新标签
            var id = 't' + (tabManager.nextId++);
            var tab = {
                id: id,
                type: 'fb',
                state: {
                    fbId: kbId,
                    fbName: name,
                    fbLocalPath: localPath,
                    fbDisplayPath: displayPath,
                    fbPermission: permission,
                    fbSubdir: ''
                },
                _identified: true
            };
            tabManager.tabs.push(tab);
            tabManager.switchTab(id);
            tabManager._renderBar();
            return;
        }

        // 后备：原有行为（无 tabManager 时）
        this.currentFbId = kbId;
        this.fbCurrentPermission = permission;
        this.fbPermMask = permission === 'manage' ? 255 : (permission === 'edit' ? 127 : 1);
        // 无本地路径 = 远程文件库（其他节点共享的）
        this.fbIsRemote = !localPath;
        this.selectedDocs = {};
        this.fbName = name || '';
        this.fbLocalPath = localPath || '';
        this.fbDisplayPath = displayPath || '';
        this.fbLocalCurrentSubdir = '';
        this.currentPath = [{ id: kbId, name: name || '未知文件库', type: 'kb' }];
        this.currentSort = { field: 'mtime', asc: false };
        this.fbCategoryTree = null;
        this.fbTreeLoaded = false;
        this.fbExpandedTreePaths = {};

        this._lsSet('docflow_current_fb_id', kbId);
        this._lsSet('docflow_current_fb_permission', permission);
        this._lsSet('docflow_current_fb_name', name || '');
        this._lsSet('docflow_current_fb_local_path', localPath || '');
        this._lsSet('docflow_current_fb_display_path', displayPath || '');
        this._lsDel('docflow_current_subdir');

        await this.renderDetail();
    },

    renderDetail: async function() {
        var self = this;

        var fileContent = document.getElementById('fb-file-content');
        if (!fileContent) {
            var h = '<div class="fb-explorer">';
            h += '<div class="fb-breadcrumb" id="fb-breadcrumb"></div>';
            h += '<div class="fb-explorer-body">';
            h += '<div class="fb-file-toolbar" id="fb-file-toolbar">';
            h += '<button class="fb-tree-toggle-btn" onclick="FileBase.toggleTreePane()" title="折叠/展开"></button>';
            h += '<span class="fb-toolbar-spacer"></span>';
            h += '<input type="text" id="fb-search-input" placeholder="搜索..." onkeydown="if(event.keyCode===13) FileBase.search()">';
            h += '<button onclick="FileBase.search()">🔍</button>';
            h += '<div class="fb-upload-wrap">';
            h += '<button onclick="FileBase.toggleUploadMenu(event)">上传</button>';
            h += '<div class="fb-upload-menu" style="display:none">';
            h += '<div class="fb-menu-item" onclick="FileBase.triggerFileUpload()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3.5 2.5h4l3 3v6a1 1 0 01-1 1h-6a1 1 0 01-1-1v-8a1 1 0 011-1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7.5 2.5v3h3" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7 7v4M5.5 8.5L7 7l1.5 1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 上传文件</div>';
            h += '<div class="fb-menu-item" onclick="FileBase.triggerFolderUpload()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1.5 4.5v6a1 1 0 001 1h9a1 1 0 001-1V5a1 1 0 00-1-1H7L5.5 2.5H2.5a1 1 0 00-1 1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7 7v4M5.5 8.5L7 7l1.5 1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 上传文件夹</div>';
            h += '</div>';
            h += '</div>';
            h += '<button onclick="FileBase.downloadAction()">下载</button>';
            h += '<button onclick="FileBase.showLockManager()" class="fb-lock-btn" title="文件锁管理">🔒 锁</button>';
            h += '<button onclick="FileBase.showTrash()" title="回收站" style="border:none;background:transparent;font-size:15px;padding:2px 6px;cursor:pointer;color:#888;transition:color 0.15s" onmouseover="this.style.color=\'#e94560\'" onmouseout="this.style.color=\'#888\'">🗑️</button>';
            h += '<input type="file" id="fb-file-upload-input" multiple style="display:none" onchange="FileBase.handleFileUpload(this)">';
            h += '<input type="file" id="fb-folder-upload-input" webkitdirectory style="display:none" onchange="FileBase.handleFolderUpload(this)">';
            h += '<input type="file" id="fb-replace-input" style="display:none" onchange="FileBase.handleReplace(this)">';
            h += '</div>';
            h += '<div class="fb-body-row">';
            h += '<div class="fb-tree-pane" id="fb-tree-pane"><div class="fb-tree-title">目录</div><div id="fb-tree-content"></div></div>';
            h += '<div class="fb-tree-resize-handle" id="fb-tree-resize-handle"></div>';
            h += '<div class="fb-file-pane" id="fb-file-pane">';
            h += '<div class="fb-file-body" id="fb-file-body" oncontextmenu="FileBase.showContextMenu(event)">';
            h += '<div id="fb-file-content"></div>';
            h += '</div></div></div></div>';

            document.getElementById('content-view').innerHTML = h;
            if (this._lsGet('fb_tree_collapsed') === '1') {
                document.querySelector('.fb-explorer-body').classList.add('collapsed');
            }
            this._fbBodyEventsBound = false;
            this.initTreeResize();
            this._initFileBodyEvents();
        }
        this.renderBreadcrumb();

        var res = await this.api('/api/fb/' + this.currentFbId + '/local-categories?recursive=1', 'GET');
        this.fbCategoryTree = res.success ? (res.categories || []) : [];
        this.fbTreeLoaded = true;
        this.renderCategoryTree();
        await this.loadFiles();
        this.initTreeResize();
    },

    renderBreadcrumb: function() {
        var el = document.getElementById('fb-breadcrumb');
        if (!el) return;
        var h = '<span class="fb-bc-home" onclick="FileBase.currentFbId=null;FileBase.renderKbList()">🏠 文件库</span>';
        for (var i = 0; i < this.currentPath.length; i++) {
            var p = this.currentPath[i];
            h += '<span class="fb-bc-sep">›</span>';
            if (i < this.currentPath.length - 1) {
                h += '<span class="fb-bc-item" onclick="FileBase.breadcrumbClick(' + i + ')">' + escapeHtmlText(p.name) + '</span>';
            } else {
                h += '<span class="fb-bc-current">' + escapeHtmlText(p.name) + '</span>';
            }
        }
        el.innerHTML = h;
    },

    breadcrumbClick: async function(index) {
        this.currentPath = this.currentPath.slice(0, index + 1);
        var parts = [];
        for (var i = 1; i < this.currentPath.length; i++) {
            if (this.currentPath[i].type === 'category') parts.push(this.currentPath[i].id);
        }
        this.fbLocalCurrentSubdir = parts.join('/');
        this._lsSet('docflow_current_subdir', this.fbLocalCurrentSubdir);
        await this.renderDetail();
    },

    renderCategoryTree: function() {
        var content = document.getElementById('fb-tree-content');
        if (!content) return;

        var curPathNorm = (this.fbLocalCurrentSubdir || '').replace(/\\/g, '/');
        var pathParts = curPathNorm ? ('/' + curPathNorm).replace(/\/+/g, '/') : '/';

        var h = '<div class="fb-tree-node">';
        h += '<div class="fb-tree-label' + (!curPathNorm ? ' active' : '') + '" onclick="FileBase.goToRoot()" oncontextmenu="FileBase.showTreeContextMenu(event, \'\')" data-local-path="">📂 ' + (escapeHtmlText(this.fbName) || '文件库') + '</div>';
        h += '</div>';

        h += this._renderTreeNodes(this.fbCategoryTree, 0, pathParts);
        content.innerHTML = h;
    },

    _renderTreeNodes: function(nodes, depth, activePath) {
        var h = '';
        var ml = depth * 12;
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            var hasChildren = n.children && n.children.length > 0;
            var nodePath = '/' + (n.path || '').replace(/\\/g, '/').replace(/\/+/g, '/');
            var isActive = activePath === nodePath;
            var isInActivePath = activePath && activePath.indexOf(nodePath + '/') === 0;
            // 展开条件：活跃路径上的默认展开，用户手动展开的也保持
            var shouldExpand = isInActivePath || !!this.fbExpandedTreePaths[nodePath];
            var h2 = '';
            if (hasChildren) {
                h2 = this._renderTreeNodes(n.children, depth + 1, activePath);
            }
            h += '<div class="fb-tree-node">';
            h += '<div class="fb-tree-label' + (isActive ? ' active' : '') + '" style="padding-left:' + (ml + 8) + 'px" onclick="FileBase._treeLabelClick(this, \'' + (n.path || '').replace(/'/g, "\\'") + '\')" oncontextmenu="FileBase.showTreeContextMenu(event, \'' + (n.path || '').replace(/'/g, "\\'") + '\')" data-local-path="' + (n.path || '').replace(/'/g, "\\'") + '">';
            if (hasChildren) {
                h += '<span class="fb-tree-toggle' + (shouldExpand ? ' open' : '') + '" onclick="event.stopPropagation();FileBase.toggleTreeNode(this)"></span>';
            } else {
                h += '<span class="fb-tree-toggle" style="visibility:hidden"></span>';
            }
            h += '<span class="icon">📁</span>' + escapeHtmlText(n.name);
            h += '</div>';
            if (hasChildren) {
                h += '<div class="fb-tree-children' + (shouldExpand ? ' open' : '') + '">';
                h += h2;
                h += '</div>';
            }
            h += '</div>';
        }
        return h;
    },

    _treeLabelClick: function(labelEl, path) {
        var toggleEl = labelEl.querySelector('.fb-tree-toggle');
        if (toggleEl && toggleEl.style.visibility !== 'hidden') {
            var nodePath = '/' + (path || '').replace(/\\/g, '/').replace(/\/+/g, '/');
            var isCurrentlyOpen = !!FileBase.fbExpandedTreePaths[nodePath];
            if (isCurrentlyOpen) {
                delete FileBase.fbExpandedTreePaths[nodePath];
            } else {
                FileBase.fbExpandedTreePaths[nodePath] = true;
            }
        }
        FileBase.navigateSubdir(path);
    },

    toggleTreeNode: function(toggleEl) {
        var childrenDiv = toggleEl.parentElement.nextElementSibling;
        if (!childrenDiv || !childrenDiv.classList.contains('fb-tree-children')) return;
        var isOpen = childrenDiv.classList.contains('open');
        // 同步更新展开状态数据
        var labelEl = toggleEl.parentElement;
        var onclickAttr = labelEl.getAttribute('onclick') || '';
        var match = onclickAttr.match(/FileBase\._treeLabelClick\([^,]+,\s*'([^']+)'/);
        if (match) {
            var path = match[1];
            var nodePath = '/' + path.replace(/\\/g, '/').replace(/\/+/g, '/');
            if (isOpen) {
                delete FileBase.fbExpandedTreePaths[nodePath];
            } else {
                FileBase.fbExpandedTreePaths[nodePath] = true;
            }
        }
        if (isOpen) {
            childrenDiv.classList.remove('open');
            toggleEl.classList.remove('open');
        } else {
            childrenDiv.classList.add('open');
            toggleEl.classList.add('open');
        }
    },

    goToRoot: function() {
        this.fbLocalCurrentSubdir = '';
        this.currentSort = { field: 'mtime', asc: false };
        this.selectedDocs = {};
        this._lsDel('docflow_current_subdir');
        this.renderDetail();
    },

    navigateSubdir: function(subdir) {
        this.fbLocalCurrentSubdir = subdir || '';
        this.currentSort = { field: 'mtime', asc: false };
        this.selectedDocs = {};
        this.currentPath = [{ id: this.currentFbId, name: this.fbName || '未知文件库', type: 'kb' }];
        if (subdir) {
            var parts = subdir.replace(/\\/g, '/').split('/');
            for (var i = 0; i < parts.length; i++) {
                this.currentPath.push({ id: parts[i], name: parts[i], type: 'category' });
            }
        }
        this._lsSet('docflow_current_subdir', this.fbLocalCurrentSubdir);
        this.renderDetail();
    },

    loadFiles: async function() {
        var div = document.getElementById('fb-file-content');
        if (!div) return;
        var url = '/api/fb/' + this.currentFbId + '/local-files';
        if (this.fbLocalCurrentSubdir) url += '?subdir=' + encodeURIComponent(this.fbLocalCurrentSubdir);
        var res = await this.api(url, 'GET');

        if (!res.success || (!res.files && !res.categories)) {
            div.innerHTML = '<div class="fb-empty">此目录为空或不可访问</div>';
            return;
        }

        var files = res.files || [];
        var categories = res.categories || [];
        var sf = this.currentSort.field;
        var sa = this.currentSort.asc;

        files.sort(function(a, b) {
            var va = a[sf], vb = b[sf];
            if (sf === 'name') {
                va = (va || '').toLowerCase(); vb = (vb || '').toLowerCase();
                return sa ? va.localeCompare(vb) : vb.localeCompare(va);
            }
            if (va < vb) return sa ? -1 : 1;
            if (va > vb) return sa ? 1 : -1;
            return 0;
        });

        var self = this;
        var h = '<table class="fb-file-table"><thead><tr>';
        h += '<th class="col-icon"></th>';
        h += '<th class="col-name" onclick="FileBase.setSort(\'name\')">名称<span class="sort-arrow">' + (sf === 'name' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-date" onclick="FileBase.setSort(\'mtime\')">修改时间<span class="sort-arrow">' + (sf === 'mtime' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-type" onclick="FileBase.setSort(\'ext\')">类型<span class="sort-arrow">' + (sf === 'ext' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-size" onclick="FileBase.setSort(\'size\')">大小<span class="sort-arrow">' + (sf === 'size' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-actions">操作</th></tr></thead><tbody>';

        for (var i = 0; i < categories.length; i++) {
            var cat = categories[i];
            var catEscPathAttr = cat.path.replace(/'/g, "\\'");
            h += '<tr class="fb-file-row fb-local-dir" data-local-path="' + catEscPathAttr + '" data-row-index="' + i + '" draggable="true">';
            h += '<td class="col-icon"><span class="fb-file-icon">📁</span></td>';
            h += '<td class="col-name"><div class="fb-file-name">' + escapeHtmlText(cat.name) + '</div></td>';
            h += '<td class="col-date"></td>';
            h += '<td class="col-type">文件夹</td>';
            h += '<td class="col-size"></td>';
            h += '<td class="col-actions"></td></tr>';
        }

        for (var i = 0; i < files.length; i++) {
            var f = files[i];
            var icon = self.getFileIcon(f.ext || '');
            var ext = (f.ext || '').replace('.', '').toUpperCase() || '文件';
            var size = self.formatSize(f.size);
            var date = self.formatDate(f.mtime);
            var fname = escapeHtmlText(f.name);
            var escPath = f.path.replace(/'/g, "\\'").replace(/\\/g, '\\\\');
            var escPathAttr = f.path.replace(/'/g, "\\'");

            h += '<tr class="fb-file-row" data-local-path="' + escPath + '" data-doc-name="' + fname + '" data-row-index="' + (categories.length + i) + '" draggable="true">';
            h += '<td class="col-icon"><span class="fb-file-icon">' + icon + '</span></td>';
            h += '<td class="col-name"><div class="fb-file-name">' + fname + '<span class="fb-file-type-tag">' + ext + '</span></div></td>';
            h += '<td class="col-date"><span class="fb-file-date">' + date + '</span></td>';
            h += '<td class="col-type">' + ext + '</td>';
            h += '<td class="col-size"><span class="fb-file-size">' + size + '</span></td>';
            h += '<td class="col-actions"><span class="fb-file-actions">';
            h += '<a href="#" onclick="FileBase.triggerReplace(\'' + escPathAttr + '\');return false">替换</a>';
            h += '</span></td></tr>';
        }
        h += '</tbody></table>';
        div.innerHTML = h;

        // 从参考来源右键定位到文件库，滚动并高亮目标文件
        var targetPath = self._lsGet('docflow_target_file_path');
        console.log('[FB Locate] targetPath from localStorage:', targetPath);
        if (targetPath) {
            self._lsDel('docflow_target_file_path');
            // 归一化目标路径：转小写、统一为正斜杠、去掉两端空白和尾部斜杠
            var normTarget = targetPath.trim().toLowerCase().replace(/\\/g, '/').replace(/\/+$/, '');
            console.log('[FB Locate] normalized target:', normTarget);
            var rows = div.querySelectorAll('.fb-file-row');
            var found = false;
            for (var ri = 0; ri < rows.length; ri++) {
                var rowPath = rows[ri].getAttribute('data-local-path') || '';
                var normRow = rowPath.trim().toLowerCase().replace(/\\/g, '/').replace(/\/+$/, '');
                console.log('[FB Locate] row[' + ri + '] data-local-path:', rowPath, '| normalized:', normRow);
                if (normRow === normTarget) {
                    rows[ri].classList.add('selected');
                    rows[ri].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                    console.log('[FB Locate] MATCH found and highlighted, row index:', ri);
                    found = true;
                    break;
                }
            }
            if (!found) {
                console.warn('[FB Locate] No matching row found for targetPath:', targetPath);
            }
        }

        this.initColumnResize();
    },

    toggleSelectAll: function() {
        var rows = document.querySelectorAll('#fb-file-body .fb-file-row');
        var selectedRows = document.querySelectorAll('#fb-file-body .fb-file-row.selected');
        if (selectedRows.length > 0) {
            for (var i = 0; i < rows.length; i++) {
                rows[i].classList.remove('selected');
            }
        } else {
            for (var i = 0; i < rows.length; i++) {
                rows[i].classList.add('selected');
            }
            this._lastClickedIndex = rows.length > 0 ? parseInt(rows[rows.length - 1].getAttribute('data-row-index'), 10) : null;
        }
    },

    getSelectedPaths: function() {
        var rows = document.querySelectorAll('#fb-file-body .fb-file-row.selected');
        var paths = [];
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            paths.push({
                path: row.getAttribute('data-local-path'),
                type: row.classList.contains('fb-local-dir') ? 'dir' : 'file'
            });
        }
        return paths;
    },

    downloadAction: async function() {
        var items = this.getSelectedPaths();
        if (items.length === 0) {
            showToast('请至少选择一个文件或文件夹', 'error');
            return;
        }

        var hasElectronAPI = typeof window.electronAPI !== 'undefined' && window.electronAPI && window.electronAPI.saveFileAs;

        if (items.length === 1 && items[0].type === 'file') {
            if (hasElectronAPI) {
                var fileName = items[0].path.split('/').pop().split('\\').pop();
                try {
                    var savePath = await window.electronAPI.saveFileAs(fileName);
                    if (!savePath) return;
                    var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/save-as', 'POST', { path: items[0].path, save_path: savePath });
                    if (res.success) {
                        showToast('文件已保存', 'success');
                    } else {
                        showToast(res.message || '保存失败', 'error');
                    }
                } catch (e) {
                    showToast('保存失败: ' + e.message, 'error');
                }
            } else {
                showToast('正在下载...', 'info');
                window.open('/api/fb/' + this.currentFbId + '/local-files/download?path=' + encodeURIComponent(items[0].path), '_blank');
            }
        } else {
            if (hasElectronAPI) {
                try {
                    var destDir = await window.electronAPI.selectDirectory();
                    if (!destDir) return;
                    var paths = [];
                    for (var i = 0; i < items.length; i++) {
                        paths.push(items[i].path);
                    }
                    var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/batch-save-as', 'POST', { paths: paths, dest_dir: destDir });
                    if (res.success) {
                        showToast('文件已保存', 'success');
                    } else {
                        showToast(res.message || '保存失败', 'error');
                    }
                } catch (e) {
                    showToast('保存失败: ' + e.message, 'error');
                }
            } else {
                var paths = [];
                for (var i = 0; i < items.length; i++) {
                    paths.push(items[i].path);
                }
                if (paths.length === 0) {
                    showToast('请至少选择一个文件或文件夹', 'error');
                    return;
                }
                showToast('正在打包下载...', 'info');
                var url = '/api/fb/' + this.currentFbId + '/local-files/batch-download';
                try {
                    var resp = await fetch(url, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ paths: paths })
                    });
                    if (!resp.ok) { showToast('下载失败', 'error'); return; }
                    var blob = await resp.blob();
                    var a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = 'files.zip';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(a.href);
                } catch (e) {
                    showToast('下载失败', 'error');
                }
            }
        }
    },

    batchDelete: async function() {
        var items = this.getSelectedPaths();
        if (items.length === 0) {
            showToast('请至少选择一个文件或文件夹', 'error');
            return;
        }
        if (!(await showConfirm('确定删除选中的 ' + items.length + ' 个项目吗？（将移入回收站）'))) return;
        var paths = [];
        for (var i = 0; i < items.length; i++) paths.push(items[i].path);
        var undoItems = [];
        for (var i = 0; i < paths.length; i++) undoItems.push({path: paths[i], name: paths[i].split('/').pop()});
        this._pushUndo({type: 'delete', items: undoItems});
        var self = this;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files', 'DELETE', { paths: paths });
        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            if (res.errors && res.errors.length > 0) {
                showToast('成功删除 ' + res.deleted + ' 个，失败: ' + res.errors.join(', '), 'error');
            }
            await self.renderDetail();
        } else {
            showToast(res.message || '删除失败', 'error');
        }
    },

    triggerReplace: function(relPath) {
        this.fbReplacePath = relPath;
        var inp = document.getElementById('fb-replace-input');
        if (inp) inp.click();
    },

    handleReplace: async function(fileInput) {
        var relPath = this.fbReplacePath;
        if (!relPath || !fileInput.files || !fileInput.files[0]) return;
        this.fbReplacePath = null;

        var formData = new FormData();
        formData.append('file', fileInput.files[0]);

        var url = '/api/fb/' + this.currentFbId + '/local-files/replace?path=' + encodeURIComponent(relPath);
        var resp = await fetch(url, { method: 'PUT', body: formData });
        var res = await resp.json();
        fileInput.value = '';

        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            showToast(res.message || '替换失败', 'error');
        }
    },

    toggleUploadMenu: function(e) {
        e.stopPropagation();
        var menu = document.querySelector('.fb-upload-menu');
        if (!menu) return;
        var isVisible = menu.style.display === 'block';
        this._hideAllMenus();
        if (!isVisible) {
            menu.style.display = 'block';
            var self = this;
            self.fbHideUploadMenuHandler = function() { self._hideAllMenus(); };
            setTimeout(function() {
                document.addEventListener('click', self.fbHideUploadMenuHandler);
            }, 0);
        }
    },

    _hideAllMenus: function() {
        var menus = document.querySelectorAll('.fb-upload-menu');
        for (var i = 0; i < menus.length; i++) {
            menus[i].style.display = 'none';
        }
        if (this.fbHideUploadMenuHandler) {
            document.removeEventListener('click', this.fbHideUploadMenuHandler);
            this.fbHideUploadMenuHandler = null;
        }
    },

    triggerFileUpload: function() {
        this._hideAllMenus();
        var inp = document.getElementById('fb-file-upload-input');
        if (inp) inp.click();
    },

    triggerFolderUpload: function() {
        this._hideAllMenus();
        var inp = document.getElementById('fb-folder-upload-input');
        if (inp) inp.click();
    },

    triggerUpload: function() {
        var inp = document.getElementById('fb-file-upload-input');
        if (inp) inp.click();
    },

    handleFileUpload: async function(fileInput) {
        if (!fileInput.files || fileInput.files.length === 0) return;
        var self = this;
        var formData = new FormData();
        for (var i = 0; i < fileInput.files.length; i++) {
            formData.append('files', fileInput.files[i]);
        }

        var subdir = this.fbLocalCurrentSubdir || '';
        var url = '/api/fb/' + this.currentFbId + '/local-files?subdir=' + encodeURIComponent(subdir);
        var resp = await fetch(url, { method: 'POST', body: formData });
        var res = await resp.json();
        fileInput.value = '';

        if (res.success) {
            self.fbCategoryTree = null;
            self.fbTreeLoaded = false;
            await self.renderDetail();
        } else {
            showToast(res.message || '上传失败', 'error');
        }
    },

    handleFolderUpload: async function(fileInput) {
        if (!fileInput.files || fileInput.files.length === 0) return;
        var self = this;
        var formData = new FormData();
        for (var i = 0; i < fileInput.files.length; i++) {
            var f = fileInput.files[i];
            var relativePath = f.webkitRelativePath || f.name;
            formData.append('files', f, relativePath);
        }

        var subdir = this.fbLocalCurrentSubdir || '';
        var url = '/api/fb/' + this.currentFbId + '/local-files?subdir=' + encodeURIComponent(subdir);
        var resp = await fetch(url, { method: 'POST', body: formData });
        var res = await resp.json();
        fileInput.value = '';

        if (res.success) {
            self.fbCategoryTree = null;
            self.fbTreeLoaded = false;
            await self.renderDetail();
        } else {
            showToast(res.message || '上传失败', 'error');
        }
    },

    showCreateFolderDialog: function() {
        this._createFolder('新建文件夹');
    },

    _createFolder: async function(name) {
        var self = this;
        var fullPath = (this.fbLocalCurrentSubdir ? this.fbLocalCurrentSubdir + '/' : '') + name;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/dir', 'POST', {
            name: name,
            parent: this.fbLocalCurrentSubdir || ''
        });
        if (res.success) {
            self._pushUndo({type: 'newFolder', path: fullPath});
            self.fbCategoryTree = null;
            self.fbTreeLoaded = false;
            await self.renderDetail();
        } else {
            showToast(res.message || '创建失败', 'error');
        }
    },

    showCreateMdDialog: function() {
        this._createMdFile('新建文件');
    },

    _createMdFile: async function(name) {
        var self = this;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/create', 'POST', {
            name: name,
            parent: this.fbLocalCurrentSubdir || ''
        });
        if (res.success) {
            self._pushUndo({type: 'newFile', path: res.path});
            self.fbCategoryTree = null;
            self.fbTreeLoaded = false;
            await self.renderDetail();
        } else {
            showToast(res.message || '创建失败', 'error');
        }
    },

    showCreateTxtDialog: function() {
        this._createTxtFile('新建文本文档.txt');
    },

    _createTxtFile: async function(name) {
        var self = this;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/create', 'POST', {
            name: name,
            parent: this.fbLocalCurrentSubdir || ''
        });
        if (res.success) {
            self._pushUndo({type: 'newFile', path: res.path});
            self.fbCategoryTree = null;
            self.fbTreeLoaded = false;
            await self.renderDetail();
        } else {
            showToast(res.message || '创建失败', 'error');
        }
    },

    showCreateOfficeFile: function(ext, label) {
        var name = '新建' + label + '.' + ext;
        this._createOfficeFile(name);
    },

    _createOfficeFile: async function(name) {
        var self = this;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/create-office', 'POST', {
            name: name,
            parent: this.fbLocalCurrentSubdir || ''
        });
        if (res.success) {
            self._pushUndo({type: 'newFile', path: res.path});
            self.fbCategoryTree = null;
            self.fbTreeLoaded = false;
            await self.renderDetail();
        } else {
            showToast(res.message || '创建失败', 'error');
        }
    },

    showContextMenu: function(event) {
        event.preventDefault();
        event.stopPropagation();
        this.hideContextMenu();

        var target = event.target;
        var fileRow = target.closest('.fb-file-row');
        var selectedRows = document.querySelectorAll('#fb-file-body .fb-file-row.selected');

        var menu = document.createElement('div');
        menu.className = 'fb-context-menu';
        menu.id = 'fb-context-menu';
        menu.style.zIndex = '4000';

        if (fileRow) {
            if (fileRow.classList.contains('selected') && selectedRows.length > 1) {
                menu.innerHTML = this._buildMultiSelectContextMenu();
            } else {
                this._clearSelection();
                fileRow.classList.add('selected');
                this._lastClickedIndex = parseInt(fileRow.getAttribute('data-row-index'), 10);
                var path = fileRow.getAttribute('data-local-path') || '';
                var isDir = fileRow.classList.contains('fb-local-dir');
                menu.innerHTML = this._buildFileContextMenu(path, isDir);
            }
        } else {
            menu.innerHTML = this._buildEmptyContextMenu();
        }

        menu.style.left = Math.min(event.clientX, window.innerWidth - 180) + 'px';
        menu.style.top = Math.min(event.clientY, window.innerHeight - 220) + 'px';
        document.body.appendChild(menu);

        this.fbHideContextMenuHandler = function() { FileBase.hideContextMenu(); };
        setTimeout(function() {
            document.addEventListener('click', FileBase.fbHideContextMenuHandler);
        }, 0);
    },

    hideContextMenu: function() {
        var existing = document.getElementById('fb-context-menu');
        if (existing) existing.remove();
        if (this.fbHideContextMenuHandler) {
            document.removeEventListener('click', this.fbHideContextMenuHandler);
            this.fbHideContextMenuHandler = null;
        }
    },

    showTreeContextMenu: function(event, path) {
        event.preventDefault();
        event.stopPropagation();
        this.hideContextMenu();

        var menu = document.createElement('div');
        menu.className = 'fb-context-menu';
        menu.id = 'fb-context-menu';
        menu.style.zIndex = '4000';
        menu.innerHTML = this._buildTreeContextMenu(path);

        menu.style.left = Math.min(event.clientX, window.innerWidth - 180) + 'px';
        menu.style.top = Math.min(event.clientY, window.innerHeight - 220) + 'px';
        document.body.appendChild(menu);

        this.fbHideContextMenuHandler = function() { FileBase.hideContextMenu(); };
        setTimeout(function() {
            document.addEventListener('click', FileBase.fbHideContextMenuHandler);
        }, 0);
    },

    _buildFileContextMenu: function(path, isDir) {
        var escPath = path.replace(/'/g, "\\'");
        var h = '';
        if (this.hasPerm(this.PERM_RENAME)) {
            h += '<div class="fb-menu-item" onclick="FileBase.contextRename(\'' + escPath + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M9.5 1.5l3 3-8 8H1.5v-3l8-8z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M8 3l3 3" stroke="currentColor" stroke-width="1.2"/></svg></span> 重命名</div>';
        }
        if (this.hasPerm(this.PERM_COPY)) {
            h += '<div class="fb-menu-item" onclick="FileBase.contextCopyOne(\'' + escPath + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2.5 1.5h7a1 1 0 011 1v7a1 1 0 01-1 1h-7a1 1 0 01-1-1v-7a1 1 0 011-1z" stroke="currentColor" stroke-width="1.1"/><path d="M4.5 4h7a1 1 0 011 1v7a1 1 0 01-1 1h-7a1 1 0 01-1-1V5a1 1 0 011-1z" stroke="currentColor" stroke-width="1.1"/></svg></span> 复制</div>';
        }
        if (this.hasPerm(this.PERM_MOVE)) {
            h += '<div class="fb-menu-item" onclick="FileBase.contextMoveOne(\'' + escPath + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1.5 4v6.5a1 1 0 001 1h9a1 1 0 001-1V5a1 1 0 00-1-1H7L5.5 3H2.5a1 1 0 00-1 1z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M8 5l3 3-3 3M11 8H5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 移动</div>';
        }
        h += '<div class="fb-menu-item" onclick="FileBase.contextDownloadOne(\'' + escPath + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1.5v7M4 6l3 3.5L10 6" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 10v1.5a1 1 0 001 1h8a1 1 0 001-1V10" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 下载</div>';
        if (this.hasPerm(this.PERM_RENAME) || this.hasPerm(this.PERM_COPY) || this.hasPerm(this.PERM_MOVE)) {
            h += '<div class="fb-menu-divider"></div>';
        }
        if (this.hasPerm(this.PERM_EDIT)) {
            h += '<div class="fb-menu-item" onclick="FileBase.contextLockFile(\'' + escPath + '\')"><span class="icon">🔒</span> 锁定</div>';
            h += '<div class="fb-menu-item" onclick="FileBase.contextUnlockFile(\'' + escPath + '\')"><span class="icon">🔓</span> 解锁</div>';
        }
        if (this.hasPerm(this.PERM_EDIT) && this.hasPerm(this.PERM_DELETE)) {
            h += '<div class="fb-menu-divider"></div>';
        }
        if (this.hasPerm(this.PERM_DELETE)) {
            h += '<div class="fb-menu-item" onclick="FileBase.contextDeleteOne(\'' + escPath + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 4h8l-.8 8a1 1 0 01-1 .9H4.8a1 1 0 01-1-.9L3 4z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M2 3.5h10M5.5 2h3a1 1 0 011 1v.5h-5V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg></span> 删除</div>';
        }
        h += '<div class="fb-menu-divider"></div>';
        h += '<div class="fb-menu-item" onclick="FileBase.showProperties(\'' + escPath + '\')"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="5" r=".8" fill="currentColor"/><path d="M6.5 7h1v3h-1z" fill="currentColor"/></svg></span> 属性</div>';
        return h;
    },

    _buildMultiSelectContextMenu: function() {
        var h = '';
        if (this.hasPerm(this.PERM_COPY)) {
            h += '<div class="fb-menu-item" onclick="FileBase.contextCopyMulti();FileBase.hideContextMenu()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2.5 1.5h7a1 1 0 011 1v7a1 1 0 01-1 1h-7a1 1 0 01-1-1v-7a1 1 0 011-1z" stroke="currentColor" stroke-width="1.1"/><path d="M4.5 4h7a1 1 0 011 1v7a1 1 0 01-1 1h-7a1 1 0 01-1-1V5a1 1 0 011-1z" stroke="currentColor" stroke-width="1.1"/></svg></span> 复制</div>';
        }
        if (this.hasPerm(this.PERM_MOVE)) {
            h += '<div class="fb-menu-item" onclick="FileBase.showMoveDialog();FileBase.hideContextMenu()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1.5 4v6.5a1 1 0 001 1h9a1 1 0 001-1V5a1 1 0 00-1-1H7L5.5 3H2.5a1 1 0 00-1 1z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M8 5l3 3-3 3M11 8H5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 移动</div>';
        }
        h += '<div class="fb-menu-item" onclick="FileBase.downloadAction();FileBase.hideContextMenu()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1.5v7M4 6l3 3.5L10 6" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 10v1.5a1 1 0 001 1h8a1 1 0 001-1V10" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 下载</div>';
        if (this.hasPerm(this.PERM_COPY) || this.hasPerm(this.PERM_MOVE)) {
            h += '<div class="fb-menu-divider"></div>';
        }
        if (this.hasPerm(this.PERM_EDIT)) {
            h += '<div class="fb-menu-item" onclick="FileBase.contextLockSelected()"><span class="icon">🔒</span> 锁定选中</div>';
            h += '<div class="fb-menu-item" onclick="FileBase.contextUnlockSelected()"><span class="icon">🔓</span> 解锁选中</div>';
        }
        if ((this.hasPerm(this.PERM_EDIT) && this.hasPerm(this.PERM_DELETE))) {
            h += '<div class="fb-menu-divider"></div>';
        }
        if (this.hasPerm(this.PERM_DELETE)) {
            h += '<div class="fb-menu-item" onclick="FileBase.batchDelete();FileBase.hideContextMenu()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 4h8l-.8 8a1 1 0 01-1 .9H4.8a1 1 0 01-1-.9L3 4z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M2 3.5h10M5.5 2h3a1 1 0 011 1v.5h-5V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg></span> 删除</div>';
        }
        return h;
    },

    _buildEmptyContextMenu: function() {
        var h = '';
        if (this.hasPerm(this.PERM_EDIT)) {
            h += '<div class="fb-menu-item fb-menu-item-has-sub">' +
                    '<span class="icon">📄</span> 新建' +
                    '<span class="fb-menu-arrow">▸</span>' +
                    '<div class="fb-context-submenu">' +
                    '<div class="fb-menu-item" onclick="FileBase.showCreateFolderDialog();FileBase.hideContextMenu()"><span class="icon">📁</span> 新建文件夹</div>' +
                    '<div class="fb-menu-item" onclick="FileBase.showCreateMdDialog();FileBase.hideContextMenu()"><span class="icon">📝</span> 新建md</div>' +
                    '<div class="fb-menu-item" onclick="FileBase.showCreateTxtDialog();FileBase.hideContextMenu()"><span class="icon">📄</span> 新建txt</div>' +
                    '<div class="fb-menu-item" onclick="FileBase.showCreateOfficeFile(\'docx\',\'Word文档\');FileBase.hideContextMenu()"><span class="icon">📃</span> 新建docx</div>' +
                    '<div class="fb-menu-item" onclick="FileBase.showCreateOfficeFile(\'xlsx\',\'Excel表格\');FileBase.hideContextMenu()"><span class="icon">📊</span> 新建xlsx</div>' +
                    '<div class="fb-menu-item" onclick="FileBase.showCreateOfficeFile(\'pptx\',\'PPT演示\');FileBase.hideContextMenu()"><span class="icon">📽️</span> 新建pptx</div>' +
                    '</div></div>';
            h += '<div class="fb-menu-item fb-menu-item-has-sub">' +
                    '<span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3.5 2.5h4l3 3v6a1 1 0 01-1 1h-6a1 1 0 01-1-1v-8a1 1 0 011-1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7.5 2.5v3h3" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7 7v4M5.5 8.5L7 7l1.5 1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 上传' +
                    '<span class="fb-menu-arrow">▸</span>' +
                    '<div class="fb-context-submenu">' +
                    '<div class="fb-menu-item" onclick="FileBase.triggerFileUpload();FileBase.hideContextMenu()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3.5 2.5h4l3 3v6a1 1 0 01-1 1h-6a1 1 0 01-1-1v-8a1 1 0 011-1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7.5 2.5v3h3" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7 7v4M5.5 8.5L7 7l1.5 1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 上传文件</div>' +
                    '<div class="fb-menu-item" onclick="FileBase.triggerFolderUpload();FileBase.hideContextMenu()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1.5 4.5v6a1 1 0 001 1h9a1 1 0 001-1V5a1 1 0 00-1-1H7L5.5 2.5H2.5a1 1 0 00-1 1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7 7v4M5.5 8.5L7 7l1.5 1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 上传文件夹</div>' +
                    '</div></div>';
            h += '<div class="fb-menu-divider"></div>';
        }
        h += '<div class="fb-menu-item" onclick="FileBase.contextOpenTools()"><span class="icon">🔧</span> 工具</div>' +
                '<div class="fb-menu-item" onclick="FileBase.contextPaste()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 2h8a1 1 0 011 1v8a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.1"/><path d="M5 1h4v2H5V1z" stroke="currentColor" stroke-width="1.1"/><path d="M5 7l2 2 3-3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span> 粘贴</div>' +
                '<div class="fb-menu-divider"></div>' +
                '<div class="fb-menu-item" onclick="FileBase.refreshKbList();FileBase.hideContextMenu()"><span class="icon">🔄</span> 刷新</div>';
        return h;
    },

    _buildTreeContextMenu: function(path) {
        var escPath = path.replace(/'/g, "\\'");
        var h = '';
        if (this.hasPerm(this.PERM_EDIT)) {
            h += '<div class="fb-menu-item" onclick="FileBase.treeNewFolder(\'' + escPath + '\');FileBase.hideContextMenu()"><span class="icon">📁</span> 新建文件夹</div>';
        }
        if (this.hasPerm(this.PERM_RENAME)) {
            h += '<div class="fb-menu-item" onclick="FileBase.treeRename(\'' + escPath + '\');FileBase.hideContextMenu()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M9.5 1.5l3 3-8 8H1.5v-3l8-8z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M8 3l3 3" stroke="currentColor" stroke-width="1.2"/></svg></span> 重命名</div>';
        }
        if (this.hasPerm(this.PERM_DELETE)) {
            h += '<div class="fb-menu-item" onclick="FileBase.treeDelete(\'' + escPath + '\');FileBase.hideContextMenu()"><span class="icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 4h8l-.8 8a1 1 0 01-1 .9H4.8a1 1 0 01-1-.9L3 4z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M2 3.5h10M5.5 2h3a1 1 0 011 1v.5h-5V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg></span> 删除</div>';
        }
        if (this.hasPerm(this.PERM_EDIT) || this.hasPerm(this.PERM_RENAME) || this.hasPerm(this.PERM_DELETE)) {
            h += '<div class="fb-menu-divider"></div>';
        }
        h += '<div class="fb-menu-item" onclick="FileBase.refreshKbList();FileBase.hideContextMenu()"><span class="icon">🔄</span> 刷新</div>';
        return h;
    },

    contextRename: function(path) {
        this.hideContextMenu();
        this._inlineRename(path);
    },

    _inlineRename: function(path) {
        var row = document.querySelector('.fb-file-row[data-local-path="' + path.replace(/\\/g, '\\\\') + '"]');
        if (!row) return;
        var nameCell = row.querySelector('.col-name .fb-file-name');
        if (!nameCell) return;
        var oldName = path.split('/').pop();
        var originalHTML = nameCell.innerHTML;

        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'fb-inline-rename-input';
        input.value = oldName;
        input.setAttribute('data-original', oldName);

        nameCell.innerHTML = '';
        nameCell.appendChild(input);
        input.focus();
        input.select();

        var self = this;
        function finishRename(save) {
            var val = input.value.trim();
            if (save && val && val !== input.getAttribute('data-original')) {
                self.api('/api/fb/' + self.currentFbId + '/local-files/rename', 'PUT', {
                    path: path,
                    new_name: val
                }).then(function(res) {
                    if (res.success) {
                        var sepIdx = path.replace(/\\/g, '/').lastIndexOf('/');
                        var pDir = sepIdx >= 0 ? path.substring(0, sepIdx) : '';
                        self._pushUndo({type: 'rename', parentDir: pDir, oldName: input.getAttribute('data-original'), newName: val});
                        self.fbCategoryTree = null;
                        self.fbTreeLoaded = false;
                        self.renderDetail();
                    } else {
                        showToast(res.message || '重命名失败', 'error');
                        nameCell.innerHTML = originalHTML;
                    }
                });
            } else {
                nameCell.innerHTML = originalHTML;
            }
        }

        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                input.blur();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                nameCell.innerHTML = originalHTML;
            }
            e.stopPropagation();
        });
        input.addEventListener('blur', function(e) {
            finishRename(true);
        });
    },

    contextCopyOne: function(path) {
        this.hideContextMenu();
        this.fbClipboard = [path];
        showToast('已复制');
    },

    contextCopyMulti: function() {
        this.hideContextMenu();
        var items = this.getSelectedPaths();
        if (items.length === 0) {
            showToast('请至少选择一个文件或文件夹', 'error');
            return;
        }
        this.fbClipboard = items.map(function(item) { return item.path; });
        showToast('已复制 ' + items.length + ' 项');
    },

    contextPaste: async function() {
        this.hideContextMenu();
        var items = this.fbClipboard;
        if (!items || items.length === 0) {
            showToast('没有可粘贴的内容', 'error');
            return;
        }
        if (typeof items === 'string') items = [items];
        var dest = this.fbLocalCurrentSubdir || '';
        var undoItems = [];
        for (var i = 0; i < items.length; i++) undoItems.push({name: items[i].split('/').pop()});
        this._pushUndo({type: 'copy', items: undoItems, dest: dest});
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/copy', 'POST', {
            sources: items,
            dest: dest
        });
        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            showToast(res.message || '粘贴失败', 'error');
        }
    },

    showCopyDialog: function() {
        this.hideContextMenu();
        var items = this.getSelectedPaths();
        if (items.length === 0) {
            showToast('请至少选择一个文件或文件夹', 'error');
            return;
        }
        var self = this;
        var label = items.length === 1 ? escapeHtmlText(items[0].path) : ('已选 ' + items.length + ' 项');
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal">';
        h += '<h3>批量复制到</h3>';
        h += '<p style="color:#666;font-size:12px">' + label + '</p>';
        h += '<div class="fb-move-tree" style="max-height:300px;overflow-y:auto;border:1px solid #e1e4e8;border-radius:4px;padding:8px;margin:8px 0">';
        h += '<div class="fb-tree-node"><div class="fb-tree-label active" onclick="FileBase._selectMoveDest(\'\', this)" data-dest="">📂 / (根目录)</div></div>';
        h += this._renderMoveTree(this.fbCategoryTree, 0);
        h += '</div>';
        h += '<div style="color:#666;font-size:12px;margin:4px 0">目标: <span id="fb-move-dest-label">根目录</span></div>';
        h += '<div class="fb-modal-actions">';
        h += '<button class="fb-btn-primary" onclick="FileBase.doBatchCopy()">复制</button>';
        h += '<button class="fb-btn-cancel" onclick="FileBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        this.fbMoveDest = '';
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'fb-modal-overlay') self.closeModal(); });
    },

    doBatchCopy: async function() {
        var items = this.getSelectedPaths();
        var dest = this.fbMoveDest || '';
        var sources = [];
        for (var i = 0; i < items.length; i++) sources.push(items[i].path);
        var undoItems = [];
        for (var i = 0; i < sources.length; i++) undoItems.push({name: sources[i].split('/').pop()});
        this._pushUndo({type: 'copy', items: undoItems, dest: dest});
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/copy', 'POST', {
            sources: sources,
            dest: dest
        });
        this.closeModal();
        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            showToast(res.message || '复制失败', 'error');
        }
    },

    doCopyOne: async function() {
        var src = this.fbCopySource;
        var dest = this.fbMoveDest || '';
        this._pushUndo({type: 'copy', items: [{name: src.split('/').pop()}], dest: dest});
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/copy', 'POST', {
            sources: [src],
            dest: dest
        });
        this.closeModal();
        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            showToast(res.message || '复制失败', 'error');
        }
    },

    contextMoveOne: function(path) {
        this.hideContextMenu();
        this._clearSelection();
        var row = document.querySelector('.fb-file-row[data-local-path="' + path.replace(/\\/g, '\\\\') + '"]');
        if (row) {
            row.classList.add('selected');
        }
        this.showMoveDialog();
    },

    contextDownloadOne: function(path) {
        this.hideContextMenu();
        this._clearSelection();
        var row = document.querySelector('.fb-file-row[data-local-path="' + path.replace(/\\/g, '\\\\') + '"]');
        if (row) row.classList.add('selected');
        FileBase.downloadAction();
    },

    contextDeleteOne: async function(path) {
        this.hideContextMenu();
        if (!(await showConfirm('确定删除 "' + path.split('/').pop() + '" 吗？（移入回收站）'))) return;
        this._pushUndo({type: 'delete', items: [{path: path, name: path.split('/').pop()}]});
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files', 'DELETE', { paths: [path] });
        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            showToast(res.message || '删除失败', 'error');
        }
    },

    // ──────────── 文件锁 右键菜单 ────────────

    contextLockFile: async function(path) {
        this.hideContextMenu();
        var res = await this.api('/api/fb/' + this.currentFbId + '/locks', 'POST', { path: path });
        if (res.success) {
            showToast('已锁定: ' + path.split('/').pop(), 'success');
        } else {
            showToast(res.message || '锁定失败', 'error');
        }
    },

    contextUnlockFile: async function(path) {
        this.hideContextMenu();
        if (!(await showConfirm('确定解锁 "' + path.split('/').pop() + '" 吗？'))) return;
        var res = await this.api('/api/fb/' + this.currentFbId + '/locks?path=' + encodeURIComponent(path), 'DELETE');
        if (res.success) {
            showToast('已解锁: ' + path.split('/').pop(), 'success');
            await this.renderDetail();
        } else {
            showToast(res.message || '解锁失败', 'error');
        }
    },

    contextLockSelected: async function() {
        this.hideContextMenu();
        var rows = document.querySelectorAll('#fb-file-body .fb-file-row.selected');
        var paths = [];
        for (var i = 0; i < rows.length; i++) {
            var p = rows[i].getAttribute('data-local-path');
            if (p) paths.push(p);
        }
        if (paths.length === 0) { showToast('没有选中的文件', 'error'); return; }
        var ok = 0, fail = 0, lastErr = '';
        for (var i = 0; i < paths.length; i++) {
            var res = await this.api('/api/fb/' + this.currentFbId + '/locks', 'POST', { path: paths[i] });
            if (res.success) { ok++; } else { fail++; lastErr = res.message || '锁定失败'; }
        }
        if (fail === 0) {
            showToast('已锁定 ' + ok + ' 个文件', 'success');
        } else {
            showToast('锁定完成：' + ok + ' 成功，' + fail + ' 失败' + (lastErr ? '（' + lastErr + '）' : ''), fail === 0 ? 'success' : 'error');
        }
    },

    contextUnlockSelected: async function() {
        this.hideContextMenu();
        var rows = document.querySelectorAll('#fb-file-body .fb-file-row.selected');
        var paths = [];
        for (var i = 0; i < rows.length; i++) {
            var p = rows[i].getAttribute('data-local-path');
            if (p) paths.push(p);
        }
        if (paths.length === 0) { showToast('没有选中的文件', 'error'); return; }
        if (!(await showConfirm('确定解锁选中的 ' + paths.length + ' 个文件吗？'))) return;
        var ok = 0, fail = 0, lastErr = '';
        for (var i = 0; i < paths.length; i++) {
            var res = await this.api('/api/fb/' + this.currentFbId + '/locks?path=' + encodeURIComponent(paths[i]), 'DELETE');
            if (res.success) { ok++; } else { fail++; lastErr = res.message || '解锁失败'; }
        }
        if (fail === 0) {
            showToast('已解锁 ' + ok + ' 个文件', 'success');
            await this.renderDetail();
        } else {
            showToast('解锁完成：' + ok + ' 成功，' + fail + ' 失败' + (lastErr ? '（' + lastErr + '）' : ''), 'error');
        }
    },

    contextOpenTools: function() {
        if (this.currentFbId) {
            window._toolsPreselect = {
                type: 'kb',
                kbId: this.currentFbId,
                name: this.fbName || '文件库',
                subdir: this.fbLocalCurrentSubdir || ''
            };
        }
        this.hideContextMenu();
        navigateTo('tools');
    },

    treeNewFolder: async function(parentPath) {
        var name = await showPrompt('新建文件夹名称：', '新建文件夹');
        if (!name || !name.trim()) return;
        var fullPath = parentPath ? parentPath + '/' + name.trim() : name.trim();
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/new-folder', 'POST', {
            path: fullPath
        });
        if (res.success) {
            this._pushUndo({type: 'newFolder', path: fullPath});
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            showToast(res.message || '创建失败', 'error');
        }
    },

    treeRename: async function(path) {
        this.hideContextMenu();
        var oldName = path.split('/').pop();
        var newName = await showPrompt('重命名为：', oldName);
        if (!newName || !newName.trim() || newName.trim() === oldName) return;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/rename', 'PUT', {
            path: path,
            new_name: newName.trim()
        });
        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            showToast(res.message || '重命名失败', 'error');
        }
    },

    treeDelete: async function(path) {
        this.hideContextMenu();
        var name = path.split('/').pop();
        if (!(await showConfirm('确定删除文件夹 "' + name + '" 吗？（此操作不可恢复）'))) return;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files', 'DELETE', { paths: [path] });
        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            showToast(res.message || '删除失败', 'error');
        }
    },

    showProperties: function(path) {
        this.hideContextMenu();
        var row = document.querySelector('.fb-file-row[data-local-path="' + path.replace(/\\/g, '\\\\') + '"]');
        if (!row) { showToast('找不到文件信息', 'error'); return; }
        var isDir = row.classList.contains('fb-local-dir');
        var name = path.split('/').pop();
        var nameEl = row.querySelector('.fb-file-name');
        var dateEl = row.querySelector('.fb-file-date');
        var sizeEl = row.querySelector('.fb-file-size');
        var typeEl = row.querySelector('.col-type');
        var typeText = isDir ? '文件夹' : (typeEl ? typeEl.textContent.trim() : '文件');

        var self = this;
        var overlay = document.createElement('div');
        overlay.className = 'fb-modal-overlay';
        overlay.id = 'fb-modal-overlay';
        overlay.innerHTML =
            '<div class="fb-modal">' +
            '<h3>' + (isDir ? '📁' : '📄') + ' ' + escapeHtmlText(name) + '</h3>' +
            '<div style="padding:12px 0;line-height:2">' +
            '<div><strong>名称：</strong>' + escapeHtmlText(name) + '</div>' +
            '<div><strong>类型：</strong>' + escapeHtmlText(typeText) + '</div>' +
            (sizeEl && sizeEl.textContent ? '<div><strong>大小：</strong>' + sizeEl.textContent.trim() + '</div>' : '') +
            (dateEl && dateEl.textContent ? '<div><strong>修改时间：</strong>' + dateEl.textContent.trim() + '</div>' : '') +
            '<div><strong>路径：</strong>' + escapeHtmlText(path) + '</div>' +
            '</div>' +
            '<div class="fb-modal-actions">' +
            '<button class="fb-btn-primary" onclick="FileBase.closeModal()">确定</button>' +
            '</div></div>';
        document.body.appendChild(overlay);
        overlay.addEventListener('click', function(e) { if (e.target === overlay) self.closeModal(); });
    },

    showMoveDialog: function() {
        var items = this.getSelectedPaths();
        if (items.length === 0) {
            showToast('请至少选择一个文件或文件夹', 'error');
            return;
        }
        var self = this;
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal">';
        h += '<h3>移动到</h3>';
        h += '<p style="color:#666;font-size:12px">已选择 ' + items.length + ' 个项目</p>';
        h += '<div class="fb-move-tree" style="max-height:300px;overflow-y:auto;border:1px solid #e1e4e8;border-radius:4px;padding:8px;margin:8px 0">';
        h += '<div class="fb-tree-node"><div class="fb-tree-label active" onclick="FileBase._selectMoveDest(\'\', this)" data-dest="">📂 / (根目录)</div></div>';
        h += this._renderMoveTree(this.fbCategoryTree, 0);
        h += '</div>';
        h += '<div style="color:#666;font-size:12px;margin:4px 0">目标: <span id="fb-move-dest-label">根目录</span></div>';
        h += '<div class="fb-modal-actions">';
        h += '<button class="fb-btn-primary" onclick="FileBase.doMove()">移动</button>';
        h += '<button class="fb-btn-cancel" onclick="FileBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        this.fbMoveDest = '';
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'fb-modal-overlay') self.closeModal(); });
    },

    _renderMoveTree: function(nodes, depth) {
        var h = '';
        var ml = depth * 12 + 8;
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            var hasChildren = n.children && n.children.length > 0;
            h += '<div class="fb-tree-node">';
            h += '<div class="fb-tree-label" style="padding-left:' + ml + 'px" onclick="FileBase._selectMoveDest(\'' + (n.path || '').replace(/'/g, "\\'") + '\', this)" data-dest="' + (n.path || '') + '">📁 ' + escapeHtmlText(n.name) + '</div>';
            if (hasChildren) {
                h += '<div style="display:block">';
                h += this._renderMoveTree(n.children, depth + 1);
                h += '</div>';
            }
            h += '</div>';
        }
        return h;
    },

    _selectMoveDest: function(dest, el) {
        this.fbMoveDest = dest;
        var labels = document.querySelectorAll('#fb-modal-overlay .fb-tree-label');
        for (var i = 0; i < labels.length; i++) labels[i].classList.remove('active');
        el.classList.add('active');
        var label = document.getElementById('fb-move-dest-label');
        if (label) label.textContent = dest || '根目录';
    },

    doMove: async function() {
        var items = this.getSelectedPaths();
        if (items.length === 0) return;
        var sources = [];
        for (var i = 0; i < items.length; i++) sources.push(items[i].path);
        var dest = this.fbMoveDest || '';

        var undoItems = [];
        for (var i = 0; i < sources.length; i++) undoItems.push({oldPath: sources[i], name: sources[i].split('/').pop()});
        this._pushUndo({type: 'move', items: undoItems, dest: dest});

        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/move', 'PUT', { sources: sources, dest: dest });
        this.closeModal();
        if (res.success) {
            if (res.errors && res.errors.length > 0) {
                showToast('成功移动 ' + res.moved + ' 个，失败: ' + res.errors.join(', '), 'error');
            }
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            showToast(res.message || '移动失败', 'error');
        }
    },

    handleFileClick: function(path) {
        this.openFile(path);
    },

    dblClickFile: function(event) {
        var row = event.target.closest('.fb-file-row');
        if (!row) return;
        var path = row.getAttribute('data-local-path');
        var isDir = row.classList.contains('fb-local-dir');
        if (isDir) {
            if (path) this.navigateSubdir(path);
        } else {
            if (path) this.openFile(path);
        }
    },

    handleRowClick: function(event) {
        var row = event.target.closest('.fb-file-row');
        if (!row) return;
        // 如果该行正在重命名中，不执行任何文件打开操作
        if (row.querySelector('.fb-inline-rename-input')) return;
        var rowIndex = parseInt(row.getAttribute('data-row-index'), 10);

        if (!event.ctrlKey && !event.metaKey && !event.shiftKey) {
            var fileNameEl = event.target.closest('.fb-file-name');
            if (fileNameEl) {
                var path = row.getAttribute('data-local-path');
                if (this._openingPath === path) return;
                this._openingPath = path;
                var self = this;
                setTimeout(function() { self._openingPath = null; }, 500);
                if (row.classList.contains('fb-local-dir')) {
                    this.navigateSubdir(path);
                } else {
                    this.openFile(path);
                }
                return;
            }
        }

        if (event.ctrlKey || event.metaKey) {
            row.classList.toggle('selected');
        } else if (event.shiftKey && this._lastClickedIndex !== null) {
            var rows = document.querySelectorAll('#fb-file-body .fb-file-row');
            var start = Math.min(this._lastClickedIndex, rowIndex);
            var end = Math.max(this._lastClickedIndex, rowIndex);
            this._clearSelection();
            for (var i = start; i <= end; i++) {
                if (rows[i]) rows[i].classList.add('selected');
            }
        } else {
            if (!row.classList.contains('selected')) {
                this._clearSelection();
            }
            row.classList.add('selected');
        }
        this._lastClickedIndex = rowIndex;
    },

    _clearSelection: function() {
        var rows = document.querySelectorAll('#fb-file-body .fb-file-row.selected');
        for (var i = 0; i < rows.length; i++) {
            rows[i].classList.remove('selected');
        }
    },

    _initFileBodyEvents: function() {
        if (this._fbBodyEventsBound) return;
        this._fbBodyEventsBound = true;

        var body = document.getElementById('fb-file-body');
        if (!body) return;

        body.addEventListener('click', function(e) {
            if (FileBase._rubberBandJustEnded) {
                FileBase._rubberBandJustEnded = false;
                return;
            }
            if (e.target.closest('.fb-file-actions') || e.target.closest('a')) return;
            var row = e.target.closest('.fb-file-row');
            if (row) {
                FileBase.handleRowClick(e);
            } else {
                FileBase._clearSelection();
                FileBase._lastClickedIndex = null;
            }
        });
        body.addEventListener('mousedown', function(e) {
            FileBase._startRubberBand(e);
        });
        body.addEventListener('dblclick', function(e) {
            FileBase.dblClickFile(e);
        });

        document.addEventListener('keydown', function(e) {
            if (e.ctrlKey && e.key === 'a') {
                var fbBody = document.getElementById('fb-file-body');
                if (fbBody) {
                    e.preventDefault();
                    FileBase.toggleSelectAll();
                }
            }
            if (e.ctrlKey && e.key === 'z' && !e.shiftKey) {
                var fbBody = document.getElementById('fb-file-body');
                if (fbBody) {
                    e.preventDefault();
                    FileBase._performUndo();
                }
            }
        });
        this._initDragDrop();
    },

    _rubberBandActive: false,

    _startRubberBand: function(e) {
        if (e.button !== 0) return;
        if (e.target.closest('.fb-file-row') || e.target.closest('a') || e.target.closest('.fb-file-actions')) return;
        this._clearSelection();
        this._lastClickedIndex = null;
        this._rubberBandStartX = e.clientX;
        this._rubberBandStartY = e.clientY;
        this._rubberBandActive = true;

        var band = document.createElement('div');
        band.className = 'fb-rubber-band';
        band.style.left = e.clientX + 'px';
        band.style.top = e.clientY + 'px';
        band.style.width = '0px';
        band.style.height = '0px';
        document.body.appendChild(band);
        this._rubberBandEl = band;

        var self = this;
        this._rubberBandMoveHandler = function(ev) { self._moveRubberBand(ev); };
        this._rubberBandEndHandler = function(ev) { self._endRubberBand(ev); };
        document.addEventListener('mousemove', this._rubberBandMoveHandler);
        document.addEventListener('mouseup', this._rubberBandEndHandler);
    },

    _moveRubberBand: function(e) {
        if (!this._rubberBandActive || !this._rubberBandEl) return;
        var x1 = Math.min(this._rubberBandStartX, e.clientX);
        var y1 = Math.min(this._rubberBandStartY, e.clientY);
        var x2 = Math.max(this._rubberBandStartX, e.clientX);
        var y2 = Math.max(this._rubberBandStartY, e.clientY);

        this._rubberBandEl.style.left = x1 + 'px';
        this._rubberBandEl.style.top = y1 + 'px';
        this._rubberBandEl.style.width = (x2 - x1) + 'px';
        this._rubberBandEl.style.height = (y2 - y1) + 'px';

        var rows = document.querySelectorAll('#fb-file-body .fb-file-row');
        for (var i = 0; i < rows.length; i++) {
            var rect = rows[i].getBoundingClientRect();
            if (rect.left < x2 && rect.right > x1 && rect.top < y2 && rect.bottom > y1) {
                if (!rows[i].classList.contains('selected')) {
                    rows[i].classList.add('selected');
                }
            } else {
                rows[i].classList.remove('selected');
            }
        }
    },

    _endRubberBand: function(e) {
        if (!this._rubberBandActive) return;
        this._rubberBandActive = false;
        this._rubberBandJustEnded = true;
        var self = this;
        setTimeout(function() { self._rubberBandJustEnded = false; }, 0);
        if (this._rubberBandEl) {
            this._rubberBandEl.remove();
            this._rubberBandEl = null;
        }
        document.removeEventListener('mousemove', this._rubberBandMoveHandler);
        document.removeEventListener('mouseup', this._rubberBandEndHandler);
        this._rubberBandMoveHandler = null;
        this._rubberBandEndHandler = null;

        var rows = document.querySelectorAll('#fb-file-body .fb-file-row.selected');
        if (rows.length > 0) {
            var lastSelected = rows[rows.length - 1];
            this._lastClickedIndex = parseInt(lastSelected.getAttribute('data-row-index'), 10);
        }
    },

    /* ──────────── Drag & Drop 拖拽系统 ──────────── */

    _initDragDrop: function() {
        var body = document.getElementById('fb-file-body');
        if (!body) return;
        var self = this;

        body.addEventListener('dragstart', function(e) { self._onDragStart(e); });
        body.addEventListener('dragenter', function(e) { self._onDragEnter(e); });
        body.addEventListener('dragover', function(e) { self._onDragOver(e); });
        body.addEventListener('dragleave', function(e) { self._onDragLeave(e); });
        body.addEventListener('drop', function(e) { self._onDrop(e); });
        body.addEventListener('dragend', function(e) { self._onDragEnd(e); });

        var treeContent = document.getElementById('fb-tree-content');
        if (treeContent) {
            treeContent.addEventListener('dragover', function(e) { self._onTreeDragOver(e); });
            treeContent.addEventListener('dragleave', function(e) { self._onTreeDragLeave(e); });
            treeContent.addEventListener('drop', function(e) { self._onTreeDrop(e); });
        }
    },

    _onDragStart: function(e) {
        var row = e.target.closest('.fb-file-row');
        if (!row) { e.preventDefault(); return; }
        if (!row.classList.contains('selected')) {
            this._clearSelection();
            row.classList.add('selected');
            this._lastClickedIndex = parseInt(row.getAttribute('data-row-index'), 10);
        }
        var selected = document.querySelectorAll('#fb-file-body .fb-file-row.selected');
        var paths = [];
        for (var i = 0; i < selected.length; i++) {
            var p = selected[i].getAttribute('data-local-path');
            if (p) paths.push(p);
        }
        this._draggedPaths = paths;
        try { e.dataTransfer.setData('text/plain', JSON.stringify(paths)); } catch(ex) {}
        e.dataTransfer.effectAllowed = 'all';
    },

    _onDragEnter: function(e) {
    },

    _hasExternalFiles: function(e) {
        return e.dataTransfer && e.dataTransfer.types &&
            Array.prototype.indexOf.call(e.dataTransfer.types, 'Files') >= 0;
    },

    _onDragOver: function(e) {
        var folderRow = e.target.closest('.fb-file-row.fb-local-dir');
        if (folderRow) {
            e.preventDefault();
            e.dataTransfer.dropEffect = e.ctrlKey ? 'copy' : 'move';
            folderRow.classList.add('fb-drop-target');
            return;
        }
        if (this._hasExternalFiles(e)) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        }
    },

    _onDragLeave: function(e) {
        var target = e.target.closest('.fb-file-row');
        if (target) target.classList.remove('fb-drop-target');
    },

    _onDrop: function(e) {
        e.preventDefault();
        this._clearDragHighlights();

        if (this._hasExternalFiles(e)) {
            this._uploadDroppedFiles(e.dataTransfer);
            this._draggedPaths = null;
            return;
        }
        var sources = this._draggedPaths;
        this._draggedPaths = null;
        if (!sources || sources.length === 0) return;
        var targetRow = e.target.closest('.fb-file-row.fb-local-dir');
        if (!targetRow) return;
        if (targetRow.classList.contains('selected')) return;
        var destPath = targetRow.getAttribute('data-local-path') || '';
        this._doMoveOrCopy(sources, destPath, !!e.ctrlKey);
    },

    _onDragEnd: function(e) {
        this._clearDragHighlights();
        this._draggedPaths = null;
    },

    _clearDragHighlights: function() {
        var els = document.querySelectorAll('.fb-drop-target, .fb-dragging');
        for (var i = 0; i < els.length; i++) els[i].classList.remove('fb-drop-target', 'fb-dragging');
    },

    /* ── Tree panel drag targets ── */

    _onTreeDragOver: function(e) {
        var label = e.target.closest('.fb-tree-label');
        if (!label) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = e.ctrlKey ? 'copy' : 'move';
        label.classList.add('fb-drop-target');

        var treeNode = label.parentElement;
        if (!label.classList.contains('active')) {
            var sub = treeNode ? treeNode.querySelector('.fb-tree-sub') : null;
            if (sub && sub.style.display === 'none' && !this._treeExpandTimer) {
                var self = this;
                this._treeExpandTimer = setTimeout(function() {
                    sub.style.display = '';
                    self._treeExpandTimer = null;
                }, 500);
            }
        }
    },

    _onTreeDragLeave: function(e) {
        var label = e.target.closest('.fb-tree-label');
        if (label) label.classList.remove('fb-drop-target');
        if (this._treeExpandTimer) {
            clearTimeout(this._treeExpandTimer);
            this._treeExpandTimer = null;
        }
    },

    _onTreeDrop: function(e) {
        e.preventDefault();
        this._hideUploadOverlay();
        this._clearDragHighlights();
        var sources = this._draggedPaths;
        this._draggedPaths = null;
        if (!sources || sources.length === 0) return;
        var label = e.target.closest('.fb-tree-label');
        if (!label) return;
        var destPath = label.getAttribute('data-local-path') || '';
        this._doMoveOrCopy(sources, destPath, !!e.ctrlKey);
    },

    /* ── Dropped file upload ── */

    _uploadDroppedFiles: function(dataTransfer) {
        var self = this;
        var allFiles = [];
        var totalProcessed = 0;

        function traverseEntries(entries, parentPath, callback) {
            var count = entries.length;
            var done = 0;
            if (count === 0) { callback(); return; }

            entries.forEach(function(entry) {
                if (entry.isFile) {
                    entry.file(function(file) {
                        allFiles.push({ file: file, relativePath: parentPath + file.name });
                        done++;
                        if (done === count) callback();
                    }, function() {
                        done++;
                        if (done === count) callback();
                    });
                } else if (entry.isDirectory) {
                    var reader = entry.createReader();
                    reader.readEntries(function(entries) {
                        var newParentPath = parentPath + entry.name + '/';
                        traverseEntries(entries, newParentPath, function() {
                            done++;
                            if (done === count) callback();
                        });
                    }, function() {
                        done++;
                        if (done === count) callback();
                    });
                } else {
                    done++;
                    if (done === count) callback();
                }
            });
        }

        if (dataTransfer.items && dataTransfer.items.length > 0) {
            var entries = [];
            for (var i = 0; i < dataTransfer.items.length; i++) {
                var item = dataTransfer.items[i];
                if (item.kind === 'file') {
                    var entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
                    if (entry) entries.push(entry);
                }
            }

            if (entries.length > 0) {
                traverseEntries(entries, '', function() {
                    self._sendFilesToServer(allFiles);
                });
                return;
            }
        }

        // fallback: no items, use files directly
        if (dataTransfer.files && dataTransfer.files.length > 0) {
            var fileList = [];
            for (var j = 0; j < dataTransfer.files.length; j++) {
                fileList.push({ file: dataTransfer.files[j], relativePath: dataTransfer.files[j].name });
            }
            self._sendFilesToServer(fileList);
        }
    },

    _sendFilesToServer: function(fileEntries) {
        if (fileEntries.length === 0) return;
        var formData = new FormData();
        for (var i = 0; i < fileEntries.length; i++) {
            var entry = fileEntries[i];
            if (entry.relativePath) {
                formData.append('files', entry.file, entry.relativePath);
            } else {
                formData.append('files', entry.file);
            }
        }
        var subdir = this.fbLocalCurrentSubdir || '';
        var url = '/api/fb/' + this.currentFbId + '/local-files?subdir=' + encodeURIComponent(subdir);
        var self = this;
        fetch(url, { method: 'POST', body: formData }).then(function(r) { return r.json(); }).then(function(res) {
            if (res.success) {
                showToast('上传成功 ' + (res.uploaded || []).length + ' 个文件');
                self.fbCategoryTree = null;
                self.fbTreeLoaded = false;
                self.renderDetail();
            } else {
                showToast(res.message || '上传失败', 'error');
            }
        });
    },

    _doMoveOrCopy: function(sources, dest, isCopy) {
        var self = this;
        var action = isCopy ? 'copy' : 'move';
        var httpMethod = isCopy ? 'POST' : 'PUT';
        var apiUrl = '/api/fb/' + this.currentFbId + '/local-files/' + action;
        this.api(apiUrl, httpMethod, { sources: sources, dest: dest }).then(function(res) {
            if (res.success) {
                showToast(isCopy ? '复制成功' : '移动成功');
                self.fbCategoryTree = null;
                self.fbTreeLoaded = false;
                self.renderDetail();
            } else {
                showToast(res.message || (isCopy ? '复制' : '移动') + '失败', 'error');
            }
        });
    },

    openFile: function(relPath) {
        var ext = relPath.split('.').pop().toLowerCase();
        
        // 远程文件库 → 使用Web预览
        if (this.fbIsRemote) {
            if (ext === 'md' || ext === 'txt' || ext === 'markdown') {
                this.openMarkdownEditor(relPath);
            } else if (['docx', 'pptx', 'ppt', 'xlsx', 'xls'].includes(ext)) {
                this.openFilePreview(relPath);
            } else if (ext === 'pdf') {
                this.openPdfPreview(relPath);
            } else if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) {
                this.openImagePreview(relPath);
            } else {
                this.openFilePreview(relPath);
            }
            return;
        }

        // PDF 始终使用Web预览，不调用本地软件
        if (ext === 'pdf') {
            this.openPdfPreview(relPath);
            return;
        }
        
        // 本地文件库 → 调用本地软件打开
        var fileName = relPath.split('/').pop();
        var url = '/api/fb/' + this.currentFbId + '/local-files/open-with-app?path=' + encodeURIComponent(relPath);
        fetch(url, { method: 'GET' })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (!data.success) {
                    showToast(data.message || '打开失败', 'error');
                }
            })
            .catch(function(e) {
                showToast('打开失败: ' + e.message, 'error');
            });
    },
    
    openFilePreview: async function(relPath) {
        var self = this;
        var fileName = relPath.split('/').pop();
        
        var overlay = document.createElement('div');
        overlay.className = 'fb-docx-preview-overlay';
        overlay.innerHTML = 
            '<div class="fb-docx-preview-container">' +
            '<div class="fb-docx-preview-header">' +
            '<span>📄 ' + escapeHtmlText(fileName) + '</span>' +
            '<button onclick="FileBase._closeDocxPreview()">✖</button>' +
            '</div>' +
            '<div class="fb-docx-preview-content" id="fb-docx-preview-content">' +
            '<div style="text-align: center; padding: 40px; color: #999;">' +
            '<div style="font-size: 48px; margin-bottom: 12px;">📄</div>' +
            '<div>正在加载预览...</div>' +
            '</div>' +
            '</div>' +
            '</div>';
        document.body.appendChild(overlay);
        
        try {
            var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/preview?path=' + encodeURIComponent(relPath), 'GET');
            var contentEl = document.getElementById('fb-docx-preview-content');
            if (res.success) {
                var html = res.markdown || '<div style="text-align: center; padding: 40px; color: #999;">文件内容为空</div>';
                if (res.markdown) {
                    try {
                        await window._ensureMarked();
                        html = marked.parse(res.markdown);
                    } catch (e) {}
                }
                contentEl.innerHTML = html;
            } else {
                contentEl.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">预览失败: ' + (res.message || '未知错误') + '</div>';
            }
        } catch (e) {
            var contentEl = document.getElementById('fb-docx-preview-content');
            contentEl.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">预览失败: ' + e.message + '</div>';
        }
    },
    
    _closeDocxPreview: function() {
        var overlay = document.querySelector('.fb-docx-preview-overlay');
        if (overlay) {
            overlay.remove();
        }
    },
    
    openPdfPreview: function(relPath) {
        var fileName = relPath.split('/').pop();
        var fileUrl = '/api/fb/' + this.currentFbId + '/local-files/open?path=' + encodeURIComponent(relPath);
        
        var overlay = document.createElement('div');
        overlay.className = 'fb-docx-preview-overlay';
        overlay.innerHTML = 
            '<div class="fb-docx-preview-container">' +
            '<div class="fb-docx-preview-header">' +
            '<span>📄 ' + escapeHtmlText(fileName) + '</span>' +
            '<button onclick="FileBase._closeDocxPreview()">✖</button>' +
            '</div>' +
            '<div class="fb-docx-preview-content" style="padding:0">' +
            '<iframe src="' + fileUrl + '" style="width:100%;height:100%;min-height:500px;border:none;" title="' + escapeHtmlText(fileName) + '"></iframe>' +
            '</div>' +
            '</div>';
        document.body.appendChild(overlay);
    },
    
    openImagePreview: function(relPath) {
        var fileName = relPath.split('/').pop();
        var fileUrl = '/api/fb/' + this.currentFbId + '/local-files/open?path=' + encodeURIComponent(relPath);
        
        var overlay = document.createElement('div');
        overlay.className = 'fb-docx-preview-overlay';
        overlay.innerHTML = 
            '<div class="fb-docx-preview-container">' +
            '<div class="fb-docx-preview-header">' +
            '<span>🖼️ ' + escapeHtmlText(fileName) + '</span>' +
            '<button onclick="FileBase._closeDocxPreview()">✖</button>' +
            '</div>' +
            '<div class="fb-docx-preview-content" style="padding:16px;text-align:center;background:#f8f9fa;">' +
            '<img src="' + fileUrl + '" alt="' + escapeHtmlText(fileName) + '" style="max-width:100%;max-height:70vh;object-contain;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.1);">' +
            '</div>' +
            '</div>';
        document.body.appendChild(overlay);
    },

    openMarkdownEditor: async function(relPath) {
        var self = this;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/content?path=' + encodeURIComponent(relPath), 'GET');
        var content = res.success ? (res.content || '') : '';
        var fileName = relPath.split('/').pop();

        var overlay = document.createElement('div');
        overlay.className = 'fb-md-editor-overlay';
        overlay.id = 'fb-md-editor-overlay';
        overlay.innerHTML =
            '<div class="fb-md-editor-container">' +
            '<div class="fb-md-editor-header">' +
            '<span class="fb-md-editor-title">📝 ' + escapeHtmlText(fileName) + '</span>' +
            '<div class="fb-md-editor-actions">' +
            '<button class="fb-md-btn-save" onclick="FileBase._saveMdContent()">保存</button>' +
            '<button class="fb-md-btn-close" onclick="FileBase._closeMdEditor()">关闭</button>' +
            '</div></div>' +
            '<div id="fb-wysiwyg-editor"><div style="padding:20px;color:#999;">正在加载编辑器...</div></div>' +
            '</div>';
        document.body.appendChild(overlay);

        this.fbMdEditorRelPath = relPath;

        try {
            await window._ensureQuill();
            await window._ensureMarked();
        } catch (e) {
            document.getElementById('fb-wysiwyg-editor').innerHTML = '<div style="padding:20px;color:#999;">编辑器加载失败，请检查网络连接</div>';
            return;
        }

        var editorEl = document.getElementById('fb-wysiwyg-editor');
        editorEl.innerHTML = '';
        var quill = new Quill(editorEl, {
            theme: 'snow',
            placeholder: '开始编写...',
            modules: {
                toolbar: [
                    [{ 'header': [1, 2, 3, false] }],
                    ['bold', 'italic', 'underline', 'strike'],
                    [{ 'color': [] }, { 'background': [] }],
                    [{ 'align': [] }],
                    ['blockquote', { 'list': 'ordered' }, { 'list': 'bullet' }],
                    ['link', 'image'],
                    ['clean']
                ]
            }
        });

        if (content) {
            var html = marked.parse(content);
            quill.clipboard.dangerouslyPasteHTML(html);
        }

        this.fbMdEditorInstance = quill;

        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) self._closeMdEditor();
        });
    },

    _saveMdContent: async function() {
        var content = '';
        if (this.fbMdEditorInstance && typeof this.fbMdEditorInstance.root !== 'undefined') {
            var html = this.fbMdEditorInstance.root.innerHTML;
            try {
                await window._ensureTurndown();
                var turndownService = new TurndownService({
                    headingStyle: 'atx',
                    bulletListMarker: '-',
                    codeBlockStyle: 'fenced'
                });
                turndownService.addRule('strikethrough', {
                    filter: ['s', 'del'],
                    replacement: function(content) { return '~~' + content + '~~'; }
                });
                content = turndownService.turndown(html);
            } catch (e) {
                content = html;
            }
        }

        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/content', 'PUT', {
            path: this.fbMdEditorRelPath,
            content: content
        });

        if (res.success) {
            this._closeMdEditor();
            this.renderDetail();
        } else {
            showToast(res.message || '保存失败', 'error');
        }
    },

    _closeMdEditor: function() {
        this.fbMdEditorInstance = null;
        this.fbMdEditorRelPath = null;
        var overlay = document.getElementById('fb-md-editor-overlay');
        if (overlay) overlay.remove();
    },

    setSort: async function(field) {
        if (this.currentSort.field === field) {
            this.currentSort.asc = !this.currentSort.asc;
        } else {
            this.currentSort.field = field;
            this.currentSort.asc = false;
        }
        await this.loadFiles();
    },

    toggleTreePane: function() {
        var body = document.querySelector('.fb-explorer-body');
        if (!body) return;
        body.classList.toggle('collapsed');
        this._lsSet('fb_tree_collapsed', body.classList.contains('collapsed') ? '1' : '0');
    },

    initTreeResize: function() {
        var handle = document.getElementById('fb-tree-resize-handle');
        var pane = document.getElementById('fb-tree-pane');
        if (!handle || !pane) return;

        var saved = this._lsGet('fb_tree_width');
        if (saved) { pane.style.width = saved + 'px'; }

        var self = this;
        var startX, startW;

        handle.addEventListener('mousedown', function(e) {
            e.preventDefault();
            startX = e.clientX;
            startW = pane.offsetWidth;
            document.body.classList.add('fb-resizing');
            handle.classList.add('active');
        });

        document.addEventListener('mousemove', function(e) {
            if (!startW) return;
            var dx = e.clientX - startX;
            var newW = Math.max(80, Math.min(500, startW + dx));
            pane.style.width = newW + 'px';
        });

        document.addEventListener('mouseup', function() {
            if (startW) {
                self._lsSet('fb_tree_width', pane.offsetWidth);
                startW = null;
                document.body.classList.remove('fb-resizing');
                handle.classList.remove('active');
            }
        });
    },

    initColumnResize: function() {
        var ths = document.querySelectorAll('#fb-file-content .fb-file-table thead th');
        for (var i = 0; i < ths.length - 1; i++) {
            var th = ths[i];
            if (th.querySelector('.fb-col-resizer')) continue;
            var resizer = document.createElement('div');
            resizer.className = 'fb-col-resizer';
            resizer.setAttribute('data-col-index', i);
            th.style.position = 'relative';
            th.appendChild(resizer);

            resizer.addEventListener('mousedown', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var thEl = this.parentElement;
                var startX = e.clientX;
                var startW = thEl.offsetWidth;
                document.body.classList.add('fb-resizing');
                document.body.style.cursor = 'col-resize';

                function onMove(ev) {
                    if (!startW) return;
                    var dx = ev.clientX - startX;
                    var newW = Math.max(30, startW + dx);
                    thEl.style.width = newW + 'px';
                    thEl.style.minWidth = newW + 'px';
                }
                function onUp() {
                    startW = null;
                    document.body.classList.remove('fb-resizing');
                    document.body.style.cursor = '';
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onUp);
                }
                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onUp);
            });
        }
    },

    _displayLocalPath: function() {
        return this.fbDisplayPath || this.fbLocalPath || '';
    },

    showSettings: async function() {
        var self = this;
        var sharedRes = await this.api('/api/fb/' + this.currentFbId + '/shared-nodes', 'GET');
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal">';
        h += '<h3>⚙ 文件库设置</h3>';

        h += '<h4>🌐 P2P 共享节点</h4>';
        if (sharedRes.success && sharedRes.nodes && sharedRes.nodes.length > 0) {
            h += '<table class="fb-member-table"><thead><tr><th>节点名称</th><th>地址</th><th>权限</th><th>操作</th></tr></thead><tbody>';
            for (var si = 0; si < sharedRes.nodes.length; si++) {
                var sn = sharedRes.nodes[si];
                h += '<tr><td>' + escapeHtmlText(sn.node_name || sn.node_id.slice(0, 12)) + '</td>';
                h += '<td style="font-size:11px;color:#888">' + escapeHtmlText(sn.node_addr) + '</td>';
                h += '<td>' + (sn.permission === 'manage' ? '管理' : sn.permission === 'edit' ? '编辑' : '查看') + '</td>';
                h += '<td><button class="fb-btn-remove" onclick="FileBase._revokeShareNode(\'' + self.currentFbId + '\',\'' + sn.node_id.replace(/'/g, "\\'") + '\')">撤销共享</button></td></tr>';
            }
            h += '</tbody></table>';
        } else {
            h += '<div style="font-size:13px;color:#888;padding:6px 0;margin-bottom:12px">尚未共享给其他 P2P 节点</div>';
        }

        h += '<div class="fb-modal-actions"><button class="fb-btn-cancel" onclick="FileBase.closeModal()">关闭</button></div>';
        h += '</div></div>';
        document.body.insertAdjacentHTML('beforeend', h);

        // 异步加载 agent 开关状态
        (async function() {
            var agentRes = await FileBase.api('/api/fb/' + self.currentFbId + '/agent-settings', 'GET');
            if (agentRes.success) {
                var checked = agentRes.agent_enabled === 1 || agentRes.agent_enabled === null || agentRes.agent_enabled === undefined;
                var toggleHtml = '' +
'<div class="fb-agent-toggle" style="margin:12px 0;padding:10px 0;border-top:1px solid #ddd;display:flex;align-items:center;justify-content:space-between">' +
'    <div>' +
'        <div style="font-weight:600;font-size:14px">🤖 AI 助手访问</div>' +
'        <div style="font-size:12px;color:#888;margin-top:2px">允许 AI 助手读取和编辑此文件库中的文件</div>' +
'    </div>' +
'    <label style="position:relative;display:inline-block;width:44px;height:24px;cursor:pointer">' +
'        <input type="checkbox" id="fb-agent-toggle-input" ' + (checked ? 'checked' : '') + ' onchange="FileBase._toggleAgentAccess(\'' + self.currentFbId + '\', this.checked)" style="opacity:0;width:0;height:0">' +
'        <span class="toggle-slider" style="position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background-color:#ccc;transition:0.3s;border-radius:24px"></span>' +
'    </label>' +
'</div>';
                var existingToggle = document.querySelector('.fb-modal .fb-agent-toggle');
                if (existingToggle) {
                    existingToggle.outerHTML = toggleHtml;
                } else {
                    var p2pHeading = document.querySelector('.fb-modal h4');
                    if (p2pHeading) {
                        p2pHeading.insertAdjacentHTML('beforebegin', toggleHtml);
                    }
                }
            }
        })();

        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'fb-modal-overlay') self.closeModal(); });
    },

    closeModal: function() {
        var ov = document.getElementById('fb-modal-overlay');
        if (ov) ov.remove();
    },

    _toggleAgentAccess: async function(fbId, enabled) {
        var res = await this.api('/api/fb/' + fbId + '/agent-settings', 'PUT', { agent_enabled: enabled });
        if (res.success) {
            showToast('AI 助手访问已' + (enabled ? '开启' : '关闭'), 'success');
        } else {
            showToast(res.message || '设置失败', 'error');
            // 恢复开关状态
            var cb = document.getElementById('fb-agent-toggle-input');
            if (cb) cb.checked = !enabled;
        }
    },

    _revokeShareNode: async function(fbId, nodeId) {
        if (!(await showConfirm('确定要撤销对该节点的共享吗？'))) return;
        var res = await this.api('/api/fb/' + fbId + '/shared-nodes/' + encodeURIComponent(nodeId), 'DELETE');
        if (res.success) {
            showToast('共享已撤销', 'success');
            this.closeModal();
            await this.showSettings();
        } else {
            showToast(res.message || '撤销失败', 'error');
        }
    },

    _deleteKbAct: async function() {
        if (!(await showConfirm('确定要删除此文件库吗？'))) return;
        var res = await this.api('/api/fb/' + this.currentFbId, 'DELETE');
        if (res.success) { this.closeModal(); this.currentFbId = null; await this.renderKbList(); }
        else showToast(res.message, 'error');
    },

    showUserManage: async function() {
        await this.refreshAuthRole();
        await this.refreshUserCache();
        var users = JSON.parse(this._lsGet('fb_user_list') || '[]');
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal">';
        h += '<h3>👥 用户管理</h3>';
        h += '<table class="fb-member-table"><thead><tr><th>用户名</th><th>全局角色</th></tr></thead><tbody>';
        for (var i = 0; i < users.length; i++) {
            var u = users[i];
            var isSelf = (u.user_id === window.authUserId);
            h += '<tr' + (isSelf ? ' style="background:#f0f8ff"' : '') + '><td>' + escapeHtmlText(u.username) + (isSelf ? ' <span style="color:#999;font-size:11px">(当前)</span>' : '') + '</td>';
            h += '<td><select' + (isSelf ? ' disabled' : '') + ' onchange="FileBase._updateUserRole(\'' + u.user_id + '\', this.value)">';
            h += '<option value="admin"' + (u.role==='admin'?' selected':'') + '>管理员</option>';
            h += '<option value="editor"' + (u.role==='editor'?' selected':'') + '>编辑者</option>';
            h += '<option value="viewer"' + (u.role==='viewer'?' selected':'') + '>阅读者</option>';
            h += '</select></td></tr>';
        }
        h += '</tbody></table>';
        h += '<p style="font-size:12px;color:#999;margin:6px 0 0">注：当前用户不可修改自身角色（防止误操作），可由其他管理员调整</p>';
        h += '<div class="fb-modal-actions"><button class="fb-btn-cancel" onclick="FileBase.closeModal()">关闭</button></div>';
        h += '</div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        var self = this;
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'fb-modal-overlay') self.closeModal(); });
    },

    _updateUserRole: async function(uid, role) {
        var res = await this.api('/api/users/' + uid + '/role', 'PUT', { role: role });
        if (res.success) await this.refreshUserCache();
        else showToast(res.message, 'error');
    },

    search: async function() {
        var qEl = document.getElementById('fb-search-input');
        var q = qEl ? qEl.value.trim() : '';
        if (!q) return;

        var res = await this.api('/api/fb/search?q=' + encodeURIComponent(q), 'GET');
        var h = '<h3>🔍: ' + escapeHtmlText(q) + '</h3>';
        h += '<button onclick="FileBase.init()" style="margin-bottom:8px">← 返回</button>';
        if (res.success && res.results && res.results.length > 0) {
            h += '<table class="fb-file-table"><thead><tr><th>文件库</th><th>文件名</th><th>匹配</th><th>操作</th></tr></thead><tbody>';
            for (var i = 0; i < res.results.length; i++) {
                var r = res.results[i];
                if (!r.rel_path && !r.filebase_type) continue;
                var dirPath = r.rel_path ? r.rel_path.replace(/\\/g, '/').replace(/\/[^\/]+$/, '') : '';
                var clickAction = 'FileBase._openFromSearch(\'' + r.fb_id + '\',\'' + escapeHtmlText(r.fb_name) + '\',\'' + escapeHtmlText(dirPath) + '\')';
                var downloadUrl = '/api/fb/' + r.fb_id + '/local-files/download?path=' + encodeURIComponent(r.rel_path || r.document_id);
                h += '<tr>';
                h += '<td>' + escapeHtmlText(r.fb_name) + '</td>';
                h += '<td><span class="fb-file-name" onclick="' + clickAction + '">' + escapeHtmlText(r.filename) + '</span></td>';
                h += '<td>' + (r.match_type === 'filename' ? '文件名' : '内容') + '</td>';
                h += '<td><a href="' + downloadUrl + '" target="_blank">下载</a></td>';
                h += '</tr>';
            }
            h += '</tbody></table>';
        } else {
            h += '<div class="fb-empty">未找到匹配结果</div>';
        }
        document.getElementById('content-view').innerHTML = h;
    },

    _openFromSearch: async function(kbId, kbName, subdir) {
        this.currentFbId = kbId;
        this.fbCurrentPermission = 'view';
        this.fbPermMask = 1;
        this.fbIsRemote = true;  // 搜索结果打开的文件库视为远程
        this.selectedDocs = {};
        this.fbName = kbName;
        this.fbLocalPath = '';
        this.fbLocalCurrentSubdir = subdir || '';
        this.currentPath = [{ id: kbId, name: kbName, type: 'kb' }];
        if (subdir) {
            var parts = subdir.split('/');
            for (var i = 0; i < parts.length; i++) {
                this.currentPath.push({ id: parts[i], name: parts[i], type: 'category' });
            }
        }
        this.currentSort = { field: 'mtime', asc: false };

        this._lsSet('docflow_current_fb_id', kbId);
        this._lsSet('docflow_current_fb_permission', 'view');
        this._lsSet('docflow_current_fb_name', kbName);
        this._lsSet('docflow_current_fb_local_path', '');
        this._lsSet('docflow_current_fb_display_path', '');

        await this.renderDetail();
    },

    showTrash: async function() {
        this.closeModal();
        var self = this;

        var res = await this.api('/api/fb/trash-list', 'GET');
        var fbItems = res.success ? (res.items || []) : [];

        var fileItems = [];
        if (this.currentFbId) {
            var fileRes = await this.api('/api/fb/' + this.currentFbId + '/local-files/trash-items', 'GET');
            fileItems = fileRes.success ? (fileRes.items || []) : [];
        }

        var allItems = [];
        for (var i = 0; i < fileItems.length; i++) {
            fileItems[i]._isFileItem = true;
            allItems.push(fileItems[i]);
        }
        for (var i = 0; i < fbItems.length; i++) {
            fbItems[i]._isFileItem = false;
            allItems.push(fbItems[i]);
        }
        allItems.sort(function(a, b) { return b.mtime - a.mtime; });

        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal" style="max-width:580px">';
        h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">';
        h += '<h3 style="margin:0">回收站</h3>';
        h += '<button onclick="FileBase.closeModal()" style="border:none;background:none;font-size:20px;cursor:pointer;color:#999;padding:0;line-height:1">✖</button>';
        h += '</div>';

        if (allItems.length === 0) {
            h += '<div style="text-align:center;padding:40px 0;color:#bbb;font-size:14px">回收站为空</div>';
        } else {
            h += '<div style="max-height:55vh;overflow-y:auto;margin:0 -24px;padding:0 24px">';
            for (var i = 0; i < allItems.length; i++) {
                var it = allItems[i];
                var escName = it.name.replace(/'/g, "\\'");
                var displayName = it.original_path || it.name;
                var restoreFn = it._isFileItem ? 'FileBase.restoreFileTrashItem' : 'FileBase.restoreTrashItem';
                var deleteFn = it._isFileItem ? 'FileBase.deleteFileTrashItem' : 'FileBase.deleteTrashItem';
                h += '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #f0f0f0">';
                h += '<div style="min-width:0;flex:1;font-size:13px">';
                h += '<span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + escapeHtmlText(displayName) + '</span>';
                h += '<span style="font-size:11px;color:#888;margin-left:8px">' + (it.size !== undefined ? formatFileSize(it.size) + ' · ' : '') + new Date(it.mtime * 1000).toLocaleString('zh-CN') + '</span>';
                h += '</div>';
                h += '<div style="display:flex;gap:6px;flex-shrink:0;margin-left:8px">';
                h += '<button onclick="' + restoreFn + '(\'' + escName + '\')" style="padding:3px 10px;border:1px solid #28a745;background:#fff;color:#28a745;border-radius:4px;cursor:pointer;font-size:12px">恢复</button>';
                h += '<button onclick="' + deleteFn + '(\'' + escName + '\')" style="padding:3px 10px;border:1px solid #ddd;background:#fff;color:#999;border-radius:4px;cursor:pointer;font-size:11px;transition:all 0.15s" onmouseover="this.style.color=\'#dc3545\';this.style.borderColor=\'#dc3545\'" onmouseout="this.style.color=\'#999\';this.style.borderColor=\'#ddd\'">彻底删除</button>';
                h += '</div></div>';
            }
            h += '</div>';
        }

        h += '<div class="fb-modal-actions">';
        h += '<button class="fb-btn-cancel" onclick="FileBase.closeModal()">关闭</button>';
        h += '<button class="fb-btn-primary" onclick="FileBase.clearTrash()">清空</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'fb-modal-overlay') self.closeModal(); });
    },

    restoreTrashItem: async function(name) {
        var res = await this.api('/api/fb/trash-restore', 'POST', { name: name });
        if (res.success) {
            showToast('已恢复', 'success');
            await this.showTrash();
        } else {
            showToast(res.message || '恢复失败', 'error');
        }
    },

    deleteTrashItem: async function(name) {
        if (!(await showConfirm('确定彻底删除 "' + name + '" 吗？此操作不可恢复！'))) return;
        var url = '/api/fb/trash-item?name=' + encodeURIComponent(name);
        await fetch(url, { method: 'DELETE' });
        await this.showTrash();
    },

    clearTrash: async function() {
        if (!(await showConfirm('确定清空回收站吗？此操作不可恢复！'))) return;
        await this.api('/api/fb/trash', 'DELETE');
        await this.showTrash();
    },

    restoreFileTrashItem: async function(name) {
        if (!this.currentFbId) return;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/trash-restore', 'POST', { name: name });
        if (res.success) {
            showToast('已恢复', 'success');
            await this.showTrash();
        } else {
            showToast(res.message || '恢复失败', 'error');
        }
    },

    deleteFileTrashItem: async function(name) {
        if (!this.currentFbId) return;
        if (!(await showConfirm('确定彻底删除 "' + name + '" 吗？此操作不可恢复！'))) return;
        var url = '/api/fb/' + this.currentFbId + '/local-files/trash-item?name=' + encodeURIComponent(name);
        var res = await fetch(url, { method: 'DELETE' }).then(function(r) { return r.json(); }).catch(function() { return { success: false }; });
        if (res.success) {
            await this.showTrash();
        } else {
            showToast(res.message || '删除失败', 'error');
        }
    },

    // ─────────────────── P2P: 节点发现与在线节点展示 ───────────────────

    _p2pPollingTimer: null,

    initNodePolling: function() {
        if (this._p2pPollingTimer) return;
        this.refreshDiscoveredNodes();
        var self = this;
        this._p2pPollingTimer = setInterval(function() {
            self.refreshDiscoveredNodes();
        }, 10000);
    },

    stopNodePolling: function() {
        if (this._p2pPollingTimer) {
            clearInterval(this._p2pPollingTimer);
            this._p2pPollingTimer = null;
        }
    },

    refreshDiscoveredNodes: async function() {
        try {
            var res = await this.api('/api/fb/p2p/discovered-nodes', 'GET');
            if (res.success) {
                this._cachedDiscoveredNodes = res.nodes || [];
                this._renderOnlineNodes();
            }
        } catch (e) {
            // silently fail
        }
    },

    _renderOnlineNodes: function() {
        var container = document.getElementById('fb-online-nodes');
        if (!container) return;
        var nodes = this._cachedDiscoveredNodes || [];
        if (nodes.length === 0) {
            container.innerHTML = '<span class="fb-p2p-indicator fb-p2p-offline" title="无在线节点">◉</span>';
        } else {
            container.innerHTML = '<span class="fb-p2p-indicator fb-p2p-online" onclick="FileBase._toggleNodeDropdown(event)" title="' + nodes.length + ' 个在线节点，点击查看">◉</span>';
        }
    },

    _toggleNodeDropdown: function(event) {
        event.stopPropagation();
        this.hideContextMenu();
        var existing = document.getElementById('fb-p2p-dropdown');
        if (existing) {
            existing.remove();
            return;
        }
        this._renderNodeDropdown(event.currentTarget);
    },

    _renderNodeDropdown: function(anchor) {
        var nodes = this._cachedDiscoveredNodes || [];
        var rect = anchor.getBoundingClientRect();
        var h = '<div class="fb-context-menu" id="fb-p2p-dropdown" style="top:' + (rect.bottom + 4) + 'px;left:' + Math.max(4, rect.left) + 'px;min-width:200px">';
        h += '<div style="padding:4px 10px;font-size:11px;color:#888;border-bottom:1px solid #eee">在线节点 (' + nodes.length + ')</div>';
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            var addr = n.addr || (n.host + ':' + n.port);
            h += '<div class="fb-menu-item" style="cursor:default;font-size:12px">';
            h += '<span class="fb-p2p-dot"></span>';
            h += '<span style="font-weight:500">' + escapeHtmlText(n.display_name || n.node_id.slice(0, 8)) + '</span>';
            h += '<span style="color:#999;font-size:11px;margin-left:auto">' + escapeHtmlText(addr) + '</span>';
            h += '</div>';
        }
        h += '</div>';
        document.body.insertAdjacentHTML('beforeend', h);

        var self = this;
        var closeHandler = function(e) {
            var dd = document.getElementById('fb-p2p-dropdown');
            if (dd && !dd.contains(e.target) && e.target !== anchor) {
                dd.remove();
                document.removeEventListener('click', closeHandler, true);
            }
        };
        setTimeout(function() {
            document.addEventListener('click', closeHandler, true);
        }, 0);

        // 窗口滚动时关闭
        var scrollHandler = function() {
            var dd = document.getElementById('fb-p2p-dropdown');
            if (dd) dd.remove();
            window.removeEventListener('scroll', scrollHandler, true);
        };
        window.addEventListener('scroll', scrollHandler, true);
    },

    // ─────────────────── P2P: 节点设置对话框 ───────────────────

    showP2PSettings: function() {
        var self = this;
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal" style="max-width:460px">';
        h += '<h3>⚙️ P2P 节点设置</h3>';
        h += '<div id="fb-p2p-settings-body"><div style="text-align:center;padding:20px;color:#999">加载中...</div></div>';
        h += '<div class="fb-modal-actions">';
        h += '<button class="fb-btn-primary" onclick="FileBase._saveP2PSettings()">保存</button>';
        h += '<button class="fb-btn-cancel" onclick="FileBase.closeModal()">关闭</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) {
            if (e.target.id === 'fb-modal-overlay') self.closeModal();
        });
        this._loadP2PSettingsForm();
    },

    _loadP2PSettingsForm: async function() {
        var body = document.getElementById('fb-p2p-settings-body');
        if (!body) return;
        try {
            var res = await this.api('/api/fb/p2p/node', 'GET');
            if (!res.success) {
                body.innerHTML = '<div style="text-align:center;padding:20px;color:#999">无法加载节点信息</div>';
                return;
            }
            body.innerHTML =
                '<div style="margin-bottom:12px">' +
                '<label style="display:block;font-size:12px;color:#888;margin-bottom:4px">节点 ID（只读）</label>' +
                '<input type="text" value="' + escapeHtmlText(res.node_id) + '" readonly style="width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:12px;background:#f5f5f5;box-sizing:border-box;color:#888">' +
                '</div>' +
                '<div style="margin-bottom:12px">' +
                '<label style="display:block;font-size:12px;color:#888;margin-bottom:4px">显示名称</label>' +
                '<input type="text" id="fb-p2p-name" value="' + escapeHtmlText(res.display_name) + '" style="width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px;box-sizing:border-box">' +
                '</div>' +
                '<div style="margin-bottom:12px">' +
                '<label style="display:block;font-size:12px;color:#888;margin-bottom:4px">P2P 监听端口</label>' +
                '<input type="number" id="fb-p2p-port" value="' + res.port + '" min="1024" max="65535" style="width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px;box-sizing:border-box">' +
                '</div>' +
                '<div style="font-size:12px;color:#999;background:#f8f9fa;padding:10px;border-radius:4px">' +
                '💡 修改名称或端口后，P2P 发现服务会自动重启以应用新配置。端口修改需要重启应用才能生效。' +
                '</div>';
        } catch (e) {
            body.innerHTML = '<div style="text-align:center;padding:20px;color:#999">加载失败: ' + e.message + '</div>';
        }
    },

    _saveP2PSettings: async function() {
        var name = (document.getElementById('fb-p2p-name').value || '').trim();
        var port = parseInt(document.getElementById('fb-p2p-port').value, 10);
        if (!name) { showToast('请输入显示名称', 'error'); return; }
        if (isNaN(port) || port < 1024 || port > 65535) { showToast('端口号范围 1024-65535', 'error'); return; }

        var res = await this.api('/api/fb/p2p/node', 'PUT', {
            display_name: name,
            port: port
        });
        if (res.success) {
            showToast('配置已更新', 'success');
            this.closeModal();
        } else {
            showToast(res.message || '保存失败', 'error');
        }
    },

    // ─────────────────── P2P: 文件库共享对话框 ───────────────────

    showShareDialog: function(fbId, fbName) {
        var self = this;
        var nodes = this._cachedDiscoveredNodes || [];
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal" style="max-width:480px">';
        h += '<h3>🔗 共享文件库</h3>';
        h += '<p style="font-size:13px;color:#666;margin-bottom:12px">选择要共享的节点和权限：<strong>' + escapeHtmlText(fbName) + '</strong></p>';

        if (nodes.length === 0) {
            h += '<div style="text-align:center;padding:20px;color:#999;background:#f8f9fa;border-radius:6px">';
            h += '<div style="font-size:32px;margin-bottom:8px">🌐</div>';
            h += '<div>未发现其他在线节点</div>';
            h += '<div style="font-size:11px;color:#bbb;margin-top:4px">请确保其他 DocFlow 节点已在同一局域网启动</div>';
            h += '</div>';
        } else {
            h += '<div style="margin-bottom:10px">';
            h += '<label style="display:block;font-size:12px;color:#888;margin-bottom:4px">选择节点</label>';
            h += '<div class="fb-share-node-list" style="max-height:220px;overflow-y:auto;border:1px solid #e1e4e8;border-radius:4px;padding:6px">';
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                var addr = n.addr || (n.host + ':' + n.port);
                h += '<label class="fb-share-node-item" style="display:flex;align-items:center;gap:8px;padding:6px 8px;cursor:pointer;border-radius:4px;transition:background 0.1s">';
                h += '<input type="checkbox" class="fb-share-node-chk" data-node-id="' + escapeHtmlText(n.node_id) + '" data-node-name="' + escapeHtmlText(n.display_name || '') + '" data-node-addr="' + escapeHtmlText(addr) + '">';
                h += '<span class="fb-p2p-dot"></span>';
                h += '<strong>' + escapeHtmlText(n.display_name || n.node_id.slice(0, 8)) + '</strong>';
                h += '<span style="color:#999;font-size:11px;margin-left:auto">' + escapeHtmlText(addr) + '</span>';
                h += '</label>';
            }
            h += '</div>';
            h += '</div>';
            h += '<div style="margin-bottom:10px">';
            h += '<label style="display:block;font-size:12px;color:#888;margin-bottom:4px">权限级别</label>';
            h += '<select id="fb-share-perm" style="width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px">';
            h += '<option value="view">查看（可浏览和下载文件）</option>';
            h += '<option value="edit" selected>编辑（可修改文件）</option>';
            h += '<option value="manage">管理（可管理文件库）</option>';
            h += '</select>';
            h += '</div>';
            h += '<div style="display:flex;gap:8px;margin-bottom:4px">';
            h += '<button class="fb-share-all-btn" onclick="FileBase._selectAllShareNodes()">全选</button>';
            h += '<button class="fb-share-all-btn" onclick="FileBase._deselectAllShareNodes()">取消全选</button>';
            h += '</div>';
        }

        h += '<div class="fb-modal-actions">';
        if (nodes.length > 0) {
            h += '<button class="fb-btn-primary" onclick="FileBase._doShare(\'' + fbId.replace(/'/g, "\\'") + '\')">🔗 共享</button>';
            h += '<button class="fb-btn-primary" onclick="FileBase._doShareAll(\'' + fbId.replace(/'/g, "\\'") + '\')" title="共享给所有在线节点">📡 共享给全部</button>';
        }
        h += '<button class="fb-btn-cancel" onclick="FileBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) {
            if (e.target.id === 'fb-modal-overlay') self.closeModal();
        });
    },

    _selectAllShareNodes: function() {
        var chks = document.querySelectorAll('.fb-share-node-chk');
        for (var i = 0; i < chks.length; i++) chks[i].checked = true;
    },

    _deselectAllShareNodes: function() {
        var chks = document.querySelectorAll('.fb-share-node-chk');
        for (var i = 0; i < chks.length; i++) chks[i].checked = false;
    },

    _doShare: async function(fbId) {
        var chks = document.querySelectorAll('.fb-share-node-chk:checked');
        var nodes = [];
        for (var i = 0; i < chks.length; i++) {
            nodes.push({
                node_id: chks[i].getAttribute('data-node-id'),
                display_name: chks[i].getAttribute('data-node-name'),
                addr: chks[i].getAttribute('data-node-addr')
            });
        }
        if (nodes.length === 0) {
            showToast('请至少选择一个节点', 'error');
            return;
        }
        var perm = document.getElementById('fb-share-perm').value;
        this.closeModal();
        var res = await this.api('/api/fb/' + fbId + '/share', 'POST', {
            nodes: nodes,
            permission: perm
        });
        if (res.success) {
            showToast(res.message || '共享成功', 'success');
        } else {
            showToast(res.message || '共享失败', 'error');
        }
    },

    _doShareAll: async function(fbId) {
        var nodes = this._cachedDiscoveredNodes || [];
        if (nodes.length === 0) {
            showToast('没有在线节点', 'error');
            return;
        }
        var perm = document.getElementById('fb-share-perm').value;
        this.closeModal();
        var shareNodes = [];
        for (var i = 0; i < nodes.length; i++) {
            var addr = nodes[i].addr || (nodes[i].host + ':' + nodes[i].port);
            shareNodes.push({
                node_id: nodes[i].node_id,
                display_name: nodes[i].display_name || '',
                addr: addr
            });
        }
        var res = await this.api('/api/fb/share-batch', 'POST', {
            fb_id: fbId,
            permission: perm,
            all_nodes: shareNodes
        });
        if (res.success) {
            showToast(res.message || '共享成功', 'success');
        } else {
            showToast(res.message || '共享失败', 'error');
        }
    },

    getFileIcon: function(ext) {
        var e = (ext || '').toLowerCase();
        var cls = 'fb-file-icon-file fb-icon-other', label = (e.replace('.', '') || '?').substring(0, 3).toUpperCase();
        if (e === '.doc' || e === '.docx') { cls = 'fb-file-icon-file fb-icon-doc'; label = 'W'; }
        else if (e === '.xls' || e === '.xlsx') { cls = 'fb-file-icon-file fb-icon-xls'; label = 'X'; }
        else if (e === '.ppt' || e === '.pptx') { cls = 'fb-file-icon-file fb-icon-ppt'; label = 'P'; }
        else if (e === '.pdf') { cls = 'fb-file-icon-file fb-icon-pdf'; label = 'P'; }
        else if (e === '.md') { cls = 'fb-file-icon-file fb-icon-md'; label = 'M'; }
        else if (e === '.txt') { cls = 'fb-file-icon-file fb-icon-txt'; label = 'T'; }
        else if (e === '.html' || e === '.htm') { cls = 'fb-file-icon-file fb-icon-html'; label = 'H'; }
        else if (/^\.(jpe?g|png|gif|svg|bmp|webp|ico)$/i.test(e)) { cls = 'fb-file-icon-file fb-icon-img'; label = 'Pic'; }
        else if (/^\.(zip|rar|7z|tar|gz)$/i.test(e)) { cls = 'fb-file-icon-file fb-icon-zip'; label = 'Z'; }
        else if (e === '.py') { cls = 'fb-file-icon-file fb-icon-py'; label = 'Py'; }
        else if (e === '.js') { cls = 'fb-file-icon-file fb-icon-js'; label = 'JS'; }
        else if (e === '.css') { cls = 'fb-file-icon-file fb-icon-css'; label = 'C'; }
        else if (e === '.json') { cls = 'fb-file-icon-file fb-icon-json'; label = '{'; }
        else if (e === '.xml') { cls = 'fb-file-icon-file fb-icon-xml'; label = 'X'; }
        else if (/^\.(mp3|wav)$/i.test(e)) { cls = 'fb-file-icon-file fb-icon-audio'; label = '♪'; }
        else if (/^\.(mp4|avi|mov)$/i.test(e)) { cls = 'fb-file-icon-file fb-icon-video'; label = '▶'; }
        return '<span class="' + cls + '">' + label + '</span>';
    },

    formatSize: function(bytes) {
        if (!bytes) return '0 B';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    },

    formatDate: function(ts) {
        return new Date(ts * 1000).toLocaleString('zh-CN');
    },

    // ──────────── 文件锁管理 ────────────

    showLockManager: async function() {
        var self = this;
        var fbId = this.currentFbId;
        if (!fbId) { showToast('未打开文件库', 'error'); return; }

        // 获取当前所有锁
        var res = await this.api('/api/fb/' + fbId + '/locks', 'GET');
        var locks = res.success ? (res.locks || []) : [];

        var h = '<div id="fb-modal-overlay" class="fb-modal-overlay">';
        h += '<div class="fb-modal" style="max-width:500px">';
        h += '<h3>🔒 文件锁管理</h3>';
        h += '<div style="margin-bottom:12px;font-size:13px;color:#666">锁定文件后，其他用户无法编辑/删除/重命名被锁定的文件</div>';

        // 当前锁列表
        h += '<div style="margin-bottom:12px">';
        h += '<div style="font-size:13px;font-weight:600;color:#333;margin-bottom:6px">当前锁定 (' + locks.length + ')</div>';
        if (locks.length === 0) {
            h += '<div style="padding:12px;color:#999;font-size:12px;background:#f8f9fa;border-radius:4px">暂无锁定</div>';
        } else {
            h += '<div style="max-height:200px;overflow-y:auto;border:1px solid #e1e4e8;border-radius:4px">';
            for (var i = 0; i < locks.length; i++) {
                var l = locks[i];
                var isSelf = l.locked_by === window.authUserId;
                h += '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 10px;border-bottom:1px solid #f0f0f0">';
                h += '<div>';
                h += '<span style="font-size:13px;color:#333">' + escapeHtmlText(l.path) + '</span>';
                h += '<span style="font-size:11px;color:#999;margin-left:8px">' + (isSelf ? '（我锁定的）' : '由 ' + escapeHtmlText(l.locked_by_short) + ' 锁定') + '</span>';
                h += '</div>';
                if (isSelf || this.hasPerm(this.PERM_MANAGE)) {
                    h += '<button class="fb-btn-remove" onclick="FileBase._doUnlock(\'' + escapeHtmlText(l.path) + '\')">解锁</button>';
                }
                h += '</div>';
            }
            h += '</div>';
        }
        h += '</div>';

        // 锁定新文件
        h += '<div style="margin-bottom:12px;padding-top:8px;border-top:1px solid #eee">';
        h += '<div style="font-size:13px;font-weight:600;color:#333;margin-bottom:6px">锁定新文件</div>';
        h += '<div style="display:flex;gap:8px">';
        h += '<input type="text" id="fb-lock-path" placeholder="输入相对路径，如 folder/file.txt" style="flex:1;padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px">';
        h += '<button class="fb-btn-primary" onclick="FileBase._doLock()">锁定</button>';
        h += '</div>';
        h += '<div style="margin-top:6px;font-size:11px;color:#999">支持锁定文件夹，锁定的目录下所有文件自动继承锁定状态</div>';
        h += '</div>';

        h += '<div class="fb-modal-actions">';
        h += '<button class="fb-btn-cancel" onclick="FileBase.closeModal()">关闭</button>';
        h += '</div></div></div>';

        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) {
            if (e.target.id === 'fb-modal-overlay') self.closeModal();
        });
        var pathInput = document.getElementById('fb-lock-path');
        if (pathInput) pathInput.focus();
    },

    _doLock: async function() {
        var fbId = this.currentFbId;
        var path = document.getElementById('fb-lock-path');
        if (!path || !path.value.trim()) { showToast('请输入文件路径', 'error'); return; }
        var res = await this.api('/api/fb/' + fbId + '/locks', 'POST', { path: path.value.trim() });
        if (res.success) {
            showToast(res.message || '锁定成功', 'success');
            this.closeModal();
            this.showLockManager();
        } else {
            showToast(res.message || '锁定失败', 'error');
        }
    },

    _doUnlock: async function(path) {
        if (!confirm('确定要解锁 "' + path + '" 吗？')) return;
        var fbId = this.currentFbId;
        var res = await this.api('/api/fb/' + fbId + '/locks?path=' + encodeURIComponent(path), 'DELETE');
        if (res.success) {
            showToast(res.message || '解锁成功', 'success');
            this.closeModal();
            this.showLockManager();
        } else {
            showToast(res.message || '解锁失败', 'error');
        }
    },
};

function escapeHtmlText(text) {
    if (!text) return '';
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB', 'TB'];
    var i = Math.floor(Math.log(bytes) / Math.log(1024));
    if (i >= units.length) i = units.length - 1;
    return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}
