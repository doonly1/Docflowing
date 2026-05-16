var FileBase = {

    _lsGet: function(key) { try { return localStorage.getItem(key); } catch(e) { return null; } },
    _lsSet: function(key, val) { try { localStorage.setItem(key, val); } catch(e) {} },
    _lsDel: function(key) { try { localStorage.removeItem(key); } catch(e) {} },

    currentFbId: null,
    fbCurrentPermission: null,
    selectedDocs: {},
    currentSort: { field: 'mtime', asc: false },
    currentPath: [],
    fbName: '',
    fbCanEdit: false,
    fbCanManage: false,
    fbLocalPath: '',
    fbLocalCurrentSubdir: '',
    fbCategoryTree: null,
    fbTreeLoaded: false,
    fbExpandedTreePaths: {},  // 跟踪手动展开的树节点路径
    fbDisplayPath: '',

    api: function(url, method, body) {
        var o = {
            method: method || 'GET',
            headers: { 'Authorization': 'Bearer ' + (window.authToken || ''), 'Content-Type': 'application/json' }
        };
        if (body && method !== 'GET') o.body = JSON.stringify(body);
        return fetch(url, o).then(function(r) { return r.json(); }).catch(function() { return { success: false, message: '请求失败' }; });
    },

    refreshAuthRole: async function() {
        try {
            var resp = await fetch('/api/user/me', {
                headers: { 'Authorization': 'Bearer ' + (window.authToken || '') }
            });
            var data = await resp.json();
            if (data.success && data.role) {
                window.authRole = data.role;
                window.authUserId = data.user_id;
                try { localStorage.setItem('docproc_role', data.role); } catch(e) {}
            }
        } catch (e) {
            console.warn('refreshAuthRole failed, will use cached role:', window.authRole);
        }
    },

    refreshUserCache: async function() {
        try {
            var res = await this.api('/api/users/list', 'GET');
            if (res.success) this._lsSet('fb_user_list', JSON.stringify(res.users));
        } catch (e) {}
    },

    getUserRole: function() {
        return window.authRole || 'viewer';
    },

    init: async function() {
        this.selectedDocs = {};
        this.currentSort = { field: 'mtime', asc: false };
        await this.refreshAuthRole();
        await this.refreshUserCache();
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
            this.fbLocalPath = '';
            this.currentPath = [{ id: null, name: '文件库', type: 'home' }];
            this._lsDel('docproc_current_fb_id');
            this._lsDel('docproc_current_fb_name');
            this._lsDel('docproc_current_fb_local_path');
            this._lsDel('docproc_current_fb_display_path');
            this._lsDel('docproc_current_fb_permission');
            this._lsDel('docproc_current_subdir');
            this.fbExpandedTreePaths = {};
            var role = this.getUserRole();

            var kbView = document.getElementById('content-view');
            if (!kbView) {
                console.warn('content-view not found, cannot render list');
                return;
            }

            // 重新构建整个视图
            var h = '<div class="fb-explorer">';
            h += '<div class="fb-breadcrumb"><span class="fb-bc-current">🏠 文件库</span></div>';
            h += '<div class="fb-explorer-body" style="border-radius:6px;border:1px solid #e1e4e8;background:#fff">';
            h += '<div class="fb-file-pane" style="width:100%">';
            h += '<div class="fb-file-toolbar">';
            h += '<input type="text" id="fb-search-input" placeholder="搜索文档..." onkeydown="if(event.keyCode===13) FileBase.search()">';
            h += '<button onclick="FileBase.search()">🔍 搜索</button>';
            h += '<button onclick="FileBase.showCreateRootFolder()">📁 新建文件库</button>';
            if (window.authRole === 'admin') h += '<button onclick="FileBase.showCreateNetworkRootFolder()">🌐 新建网络文件库</button>';
            h += '<span class="fb-toolbar-spacer"></span>';
            h += '<button onclick="FileBase.showTrash()">🗑️ 回收站</button>';
            h += '</div>';
            h += '<div class="fb-file-body" id="fb-grid-container" oncontextmenu="FileBase.showKbListContextMenu(event)"></div>';
            h += '</div></div></div>';
            kbView.innerHTML = h;

            var grid = document.getElementById('fb-grid-container');
            if (!grid) {
                console.warn('fb-grid-container not found');
                return;
            }

            // 显示加载中
            grid.innerHTML = '<div class="fb-empty">刷新中...</div>';

            var res = await this.api('/api/fb/list', 'GET');
            if (!res || !res.success) {
                grid.innerHTML = '<div class="fb-empty">刷新失败: ' + (res?.message || '未知错误') + '</div>';
                return;
            }

            var kbs = res.kbs || [];

            if (kbs.length === 0) {
                grid.innerHTML = '<div class="fb-empty">暂无文件库，点击上方按钮创建</div>';
                return;
            }

            var html = '<div class="fb-grid">';
            for (var i = 0; i < kbs.length; i++) {
                var kb = kbs[i];
                html += '<div class="fb-card" data-fb-id="' + kb.id + '" data-fb-permission="' + kb.permission + '" data-fb-name="' + escapeHtmlText(kb.name) + '" data-fb-type="' + (kb.filebase_type || 'local') + '" data-fb-local-path="' + escapeHtmlText(kb.local_path || '') + '" data-fb-display-path="' + escapeHtmlText(kb.display_path || '') + '" onclick="FileBase.openKb(\'' + kb.id + '\',\'' + kb.permission + '\',\'' + escapeHtmlText(kb.name) + '\',\'' + escapeHtmlText(kb.local_path || '') + '\',\'' + escapeHtmlText(kb.display_path || '') + '\')">';
                html += '<h3>📁 ' + escapeHtmlText(kb.name) + '</h3>';
                html += '<div class="fb-card-meta">' + (kb.display_path || kb.local_path || '') + '</div>';
                html += '<div class="fb-card-sync-status" id="sync-status-' + kb.id + '" data-fb-id="' + kb.id + '"></div>';
                html += '</div>';
            }
            html += '</div>';
            grid.innerHTML = html;

            // 加载所有文件库的同步状态
            for (var i = 0; i < kbs.length; i++) {
                this._loadSyncStatus(kbs[i].id);
            }
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
        this._createRootFolder('新建文件夹');
    },

    showCreateNetworkRootFolder: function() {
        var self = this;
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal" style="max-width:420px">';
        h += '<h3>🌐 新建网络文件库</h3>';
        h += '<div style="margin-bottom:12px">';
        h += '<label style="display:block;font-size:13px;color:#555;margin-bottom:4px">网络路径</label>';
        h += '<input type="text" id="fb-net-path" placeholder="如 \\\\server\\share\\folder" style="width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px;box-sizing:border-box">';
        h += '</div>';
        h += '<div class="fb-modal-actions">';
        h += '<button class="btn" onclick="FileBase._doCreateNetworkRootFolder()" style="background:#e94560;color:#fff;border:none;padding:6px 20px;border-radius:4px;cursor:pointer;font-size:13px">创建</button>';
        h += '<button class="fb-btn-cancel" onclick="FileBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'fb-modal-overlay') self.closeModal(); });
        setTimeout(function() { document.getElementById('fb-net-path').focus(); }, 100);
    },

    _doCreateNetworkRootFolder: async function() {
        var networkPath = (document.getElementById('fb-net-path').value || '').trim();
        if (!networkPath) { alert('请输入网络路径'); return; }
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
            alert(res.message || '创建失败');
        }
    },

    _createRootFolder: async function(name) {
        var self = this;
        var res = await this.api('/api/fb/create-folder', 'POST', { name: name });
        if (res.success) {
            await self.renderKbList();
        } else {
            alert(res.message || '创建失败');
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
            h += '<div class="fb-menu-item" onclick="FileBase.kbListManage(\'' + escId + '\')"><span class="icon">⚙</span> 管理</div>';
            h += '<div class="fb-menu-divider"></div>';
            h += '<div class="fb-menu-item" onclick="FileBase.toggleSync(\'' + escId + '\')"><span class="icon">☁️</span> 同步到 KB</div>';
            h += '<div class="fb-menu-item" onclick="FileBase.syncNow(\'' + escId + '\')"><span class="icon">🔄</span> 立即同步</div>';
            h += '<div class="fb-menu-item" onclick="FileBase.convertDoc(\'' + escId + '\')"><span class="icon">📄</span> doc转docx</div>';
            h += '<div class="fb-menu-divider"></div>';
            h += '<div class="fb-menu-item" onclick="FileBase.kbListRename(\'' + escId + '\',\'' + escName + '\')"><span class="icon">✏️</span> 重命名</div>';
            h += '<div class="fb-menu-item" onclick="FileBase.kbListCopy(\'' + escId + '\',\'' + escName + '\')"><span class="icon">📋</span> 复制</div>';
            h += '<div class="fb-menu-divider"></div>';
            h += '<div class="fb-menu-item" onclick="FileBase.kbListDelete(\'' + escId + '\',\'' + escName + '\')"><span class="icon">🗑️</span> 删除</div>';
        }
        return h;
    },

    toggleSync: async function(kbId) {
        this.hideContextMenu();
        try {
            var res = await this.api('/api/fb/' + kbId + '/sync-status', 'GET');
            if (!res.success) {
                alert('获取同步状态失败');
                return;
            }

            var newEnabled = !res.enabled;
            var res2 = await this.api('/api/fb/' + kbId + '/sync', 'POST', { enabled: newEnabled });
            if (res2.success) {
                await this._loadSyncStatus(kbId);
            } else {
                alert(res2.message || '操作失败');
            }
        } catch (e) {
            alert('操作失败: ' + e.message);
        }
    },

    syncNow: async function(kbId) {
        this.hideContextMenu();
        try {
            var res = await this.api('/api/fb/' + kbId + '/sync-now', 'POST');
            if (!res.success) {
                alert(res.message || '同步触发失败');
                return;
            }
            setTimeout(function() {
                FileBase._loadSyncStatus(kbId);
            }, 1000);
        } catch (e) {
            alert('同步失败: ' + e.message);
        }
    },

    convertDoc: async function(kbId) {
        this.hideContextMenu();
        try {
            await this.api('/api/fb/' + kbId + '/convert-doc', 'POST');
        } catch (e) {
            alert('转换失败: ' + e.message);
        }
    },

    kbListManage: function(kbId) {
        this.hideContextMenu();
        this.currentFbId = kbId;
        this.showSettings();
    },

    kbListRename: async function(kbId, oldName) {
        this.hideContextMenu();
        var newName = prompt('重命名文件库：', oldName);
        if (!newName || !newName.trim() || newName.trim() === oldName) return;
        var res = await this.api('/api/fb/' + kbId, 'PUT', { name: newName.trim() });
        if (res.success) {
            await this.renderKbList();
        } else {
            alert(res.message || '重命名失败');
        }
    },

    kbListCopy: async function(kbId, kbName) {
        this.hideContextMenu();
        var newName = prompt('复制文件库为：', kbName + '_副本');
        if (!newName || !newName.trim()) return;
        var res = await this.api('/api/fb/copy-folder', 'POST', {
            kb_id: kbId,
            new_name: newName.trim()
        });
        if (res.success) {
            await this.renderKbList();
        } else {
            alert(res.message || '复制失败');
        }
    },

    kbListDelete: async function(kbId, kbName) {
        this.hideContextMenu();
        if (!confirm('确定删除文件库 "' + kbName + '" 吗？')) return;
        var res = await this.api('/api/fb/' + kbId, 'DELETE');
        if (res.success) {
            await this.renderKbList();
        } else {
            alert(res.message || '删除失败');
        }
    },

    openKb: async function(kbId, permission, name, localPath, displayPath) {
        this.currentFbId = kbId;
        this.fbCurrentPermission = permission;
        this.fbCanEdit = permission === 'edit' || permission === 'manage';
        this.fbCanManage = permission === 'manage';
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

        this._lsSet('docproc_current_fb_id', kbId);
        this._lsSet('docproc_current_fb_permission', permission);
        this._lsSet('docproc_current_fb_name', name || '');
        this._lsSet('docproc_current_fb_local_path', localPath || '');
        this._lsSet('docproc_current_fb_display_path', displayPath || '');
        this._lsDel('docproc_current_subdir');

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
            h += '<div class="fb-upload-wrap">';
            h += '<button onclick="FileBase.toggleUploadMenu(event)">📤 上传</button>';
            h += '<div class="fb-upload-menu" style="display:none">';
            h += '<div class="fb-menu-item" onclick="FileBase.triggerFileUpload()"><span class="icon">📄</span> 上传文件</div>';
            h += '<div class="fb-menu-item" onclick="FileBase.triggerFolderUpload()"><span class="icon">📁</span> 上传文件夹</div>';
            h += '</div>';
            h += '</div>';
            h += '<button onclick="FileBase.showCreateFolderDialog()">📁 新建文件夹</button>';
            h += '<button onclick="FileBase.showCreateMdDialog()">📝 新建MD文件</button>';
            h += '<span class="fb-toolbar-spacer"></span>';
            h += '<input type="text" id="fb-search-input" placeholder="搜索..." onkeydown="if(event.keyCode===13) FileBase.search()">';
            h += '<button onclick="FileBase.search()">🔍</button>';
            h += '<button onclick="FileBase.downloadAction()">📥 下载</button>';
            h += '<button onclick="FileBase.showMoveDialog()">📦 移动</button>';
            h += '<button onclick="FileBase.batchDelete()">🗑️ 删除</button>';
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
            this.initTreeResize();
        }
        this.renderBreadcrumb();

        if (!this.fbTreeLoaded) {
            var res = await this.api('/api/fb/' + this.currentFbId + '/local-categories?recursive=1', 'GET');
            this.fbCategoryTree = res.success ? (res.categories || []) : [];
            this.fbTreeLoaded = true;
        }
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
        this._lsSet('docproc_current_subdir', this.fbLocalCurrentSubdir);
        await this.renderDetail();
    },

    renderCategoryTree: function() {
        var content = document.getElementById('fb-tree-content');
        if (!content) return;

        var curPathNorm = (this.fbLocalCurrentSubdir || '').replace(/\\/g, '/');
        var pathParts = curPathNorm ? ('/' + curPathNorm).replace(/\/+/g, '/') : '/';

        var h = '<div class="fb-tree-node">';
        h += '<div class="fb-tree-label' + (!curPathNorm ? ' active' : '') + '" onclick="FileBase.goToRoot()">📂 ' + (escapeHtmlText(this.fbName) || '文件库') + '</div>';
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
            h += '<div class="fb-tree-label' + (isActive ? ' active' : '') + '" style="padding-left:' + (ml + 8) + 'px" onclick="FileBase._treeLabelClick(this, \'' + (n.path || '').replace(/'/g, "\\'") + '\')">';
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
        this._lsDel('docproc_current_subdir');
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
        this._lsSet('docproc_current_subdir', this.fbLocalCurrentSubdir);
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
        h += '<th class="col-check"><input type="checkbox" id="fb-select-all" onchange="FileBase.toggleSelectAll(this)" title="全选/取消"></th>';
        h += '<th class="col-icon"></th>';
        h += '<th class="col-name" onclick="FileBase.setSort(\'name\')">名称<span class="sort-arrow">' + (sf === 'name' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-date" onclick="FileBase.setSort(\'mtime\')">修改时间<span class="sort-arrow">' + (sf === 'mtime' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-type" onclick="FileBase.setSort(\'ext\')">类型<span class="sort-arrow">' + (sf === 'ext' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-size" onclick="FileBase.setSort(\'size\')">大小<span class="sort-arrow">' + (sf === 'size' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-actions">操作</th></tr></thead><tbody>';

        for (var i = 0; i < categories.length; i++) {
            var cat = categories[i];
            var catEscPathAttr = cat.path.replace(/'/g, "\\'");
            h += '<tr class="fb-file-row fb-local-dir" data-local-path="' + catEscPathAttr + '">';
            h += '<td class="col-check"><input type="checkbox" class="fb-item-check" data-path="' + catEscPathAttr + '" data-type="dir" onclick="event.stopPropagation()"></td>';
            h += '<td class="col-icon"><span class="fb-file-icon">📁</span></td>';
            h += '<td class="col-name"><div class="fb-file-name" onclick="FileBase.navigateSubdir(\'' + cat.path.replace(/'/g, "\\'") + '\')">' + escapeHtmlText(cat.name) + '</div></td>';
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

            h += '<tr class="fb-file-row" data-local-path="' + escPath + '" data-doc-name="' + fname + '">';
            h += '<td class="col-check"><input type="checkbox" class="fb-item-check" data-path="' + escPathAttr + '" data-type="file" onclick="event.stopPropagation()"></td>';
            h += '<td class="col-icon"><span class="fb-file-icon">' + icon + '</span></td>';
            h += '<td class="col-name"><div class="fb-file-name" ondblclick="FileBase.dblClickFile(event)" onclick="event.stopPropagation()">' + fname + '<span class="fb-file-type-tag">' + ext + '</span></div></td>';
            h += '<td class="col-date"><span class="fb-file-date">' + date + '</span></td>';
            h += '<td class="col-type">' + ext + '</td>';
            h += '<td class="col-size"><span class="fb-file-size">' + size + '</span></td>';
            h += '<td class="col-actions"><span class="fb-file-actions">';
            h += '<a href="#" onclick="FileBase.triggerReplace(\'' + escPathAttr + '\');return false">替换</a>';
            h += '<a href="#" onclick="FileBase.openFile(\'' + escPath + '\');return false">打开</a>';
            h += '</span></td></tr>';
        }
        h += '</tbody></table>';
        div.innerHTML = h;
    },

    toggleSelectAll: function(el) {
        var checks = document.querySelectorAll('.fb-item-check');
        for (var i = 0; i < checks.length; i++) {
            checks[i].checked = el.checked;
        }
    },

    getSelectedPaths: function() {
        var checks = document.querySelectorAll('.fb-item-check:checked');
        var paths = [];
        for (var i = 0; i < checks.length; i++) {
            var chk = checks[i];
            paths.push({ path: chk.getAttribute('data-path'), type: chk.getAttribute('data-type') });
        }
        return paths;
    },

    downloadAction: async function() {
        var items = this.getSelectedPaths();
        if (items.length === 0) {
            alert('请至少选择一个文件或文件夹');
            return;
        }
        if (items.length === 1 && items[0].type === 'file') {
            window.open('/api/fb/' + this.currentFbId + '/local-files/download?path=' + encodeURIComponent(items[0].path) + '&token=' + encodeURIComponent(authToken), '_blank');
        } else {
            var paths = [];
            for (var i = 0; i < items.length; i++) {
                paths.push(items[i].path);
            }
            if (paths.length === 0) {
                alert('请至少选择一个文件或文件夹');
                return;
            }
            var url = '/api/fb/' + this.currentFbId + '/local-files/batch-download?token=' + encodeURIComponent(authToken);
            try {
                var resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ paths: paths })
                });
                if (!resp.ok) { alert('下载失败'); return; }
                var blob = await resp.blob();
                var a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'files.zip';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(a.href);
            } catch (e) {
                alert('下载失败');
            }
        }
    },

    batchDelete: async function() {
        var items = this.getSelectedPaths();
        if (items.length === 0) {
            alert('请至少选择一个文件或文件夹');
            return;
        }
        if (!confirm('确定删除选中的 ' + items.length + ' 个项目吗？（此操作不可恢复）')) return;
        var paths = [];
        for (var i = 0; i < items.length; i++) paths.push(items[i].path);
        var self = this;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files', 'DELETE', { paths: paths });
        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            if (res.errors && res.errors.length > 0) {
                alert('成功删除 ' + res.deleted + ' 个，失败: ' + res.errors.join(', '));
            }
            await self.renderDetail();
        } else {
            alert(res.message || '删除失败');
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

        var url = '/api/fb/' + this.currentFbId + '/local-files/replace?path=' + encodeURIComponent(relPath) + '&token=' + encodeURIComponent(authToken);
        var resp = await fetch(url, { method: 'PUT', body: formData });
        var res = await resp.json();
        fileInput.value = '';

        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            alert(res.message || '替换失败');
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
            this.fbHideUploadMenuHandler = function() { self._hideAllMenus(); };
            setTimeout(function() {
                document.addEventListener('click', self._hideUploadMenuHandler);
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
        var url = '/api/fb/' + this.currentFbId + '/local-files?subdir=' + encodeURIComponent(subdir) + '&token=' + encodeURIComponent(authToken);
        var resp = await fetch(url, { method: 'POST', body: formData });
        var res = await resp.json();
        fileInput.value = '';

        if (res.success) {
            self.fbCategoryTree = null;
            self.fbTreeLoaded = false;
            await self.renderDetail();
        } else {
            alert(res.message || '上传失败');
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
        var url = '/api/fb/' + this.currentFbId + '/local-files?subdir=' + encodeURIComponent(subdir) + '&token=' + encodeURIComponent(authToken);
        var resp = await fetch(url, { method: 'POST', body: formData });
        var res = await resp.json();
        fileInput.value = '';

        if (res.success) {
            self.fbCategoryTree = null;
            self.fbTreeLoaded = false;
            await self.renderDetail();
        } else {
            alert(res.message || '上传失败');
        }
    },

    showCreateFolderDialog: function() {
        this._createFolder('新建文件夹');
    },

    _createFolder: async function(name) {
        var self = this;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/dir', 'POST', {
            name: name,
            parent: this.fbLocalCurrentSubdir || ''
        });
        if (res.success) {
            self.fbCategoryTree = null;
            self.fbTreeLoaded = false;
            await self.renderDetail();
        } else {
            alert(res.message || '创建失败');
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
            self.fbCategoryTree = null;
            self.fbTreeLoaded = false;
            self.openMarkdownEditor(res.path);
        } else {
            alert(res.message || '创建失败');
        }
    },

    showContextMenu: function(event) {
        event.preventDefault();
        event.stopPropagation();
        this.hideContextMenu();

        var target = event.target;
        var fileRow = target.closest('.fb-file-row');

        var menu = document.createElement('div');
        menu.className = 'fb-context-menu';
        menu.id = 'fb-context-menu';
        menu.style.zIndex = '4000';

        if (fileRow) {
            var path = fileRow.getAttribute('data-local-path') || '';
            var isDir = fileRow.classList.contains('fb-local-dir');
            menu.innerHTML = this._buildFileContextMenu(path, isDir);
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
        var menu = document.getElementById('fb-context-menu');
        if (menu) menu.remove();
        if (this.fbHideContextMenuHandler) {
            document.removeEventListener('click', this.fbHideContextMenuHandler);
            this.fbHideContextMenuHandler = null;
        }
    },

    _buildFileContextMenu: function(path, isDir) {
        var escPath = path.replace(/'/g, "\\'");
        var h = '';
        h += '<div class="fb-menu-item" onclick="FileBase.contextRename(\'' + escPath + '\')"><span class="icon">✏️</span> 重命名</div>';
        h += '<div class="fb-menu-item" onclick="FileBase.contextCopyOne(\'' + escPath + '\')"><span class="icon">📋</span> 复制</div>';
        h += '<div class="fb-menu-item" onclick="FileBase.contextMoveOne(\'' + escPath + '\')"><span class="icon">📦</span> 移动</div>';
        h += '<div class="fb-menu-item" onclick="FileBase.contextDownloadOne(\'' + escPath + '\')"><span class="icon">📥</span> 下载</div>';
        h += '<div class="fb-menu-divider"></div>';
        h += '<div class="fb-menu-item" onclick="FileBase.contextDeleteOne(\'' + escPath + '\')"><span class="icon">🗑️</span> 删除</div>';
        return h;
    },

    _buildEmptyContextMenu: function() {
        var h = '<div class="fb-menu-item" onclick="FileBase.showCreateFolderDialog();FileBase.hideContextMenu()"><span class="icon">📁</span> 新建文件夹</div>' +
                '<div class="fb-menu-item" onclick="FileBase.showCreateMdDialog();FileBase.hideContextMenu()"><span class="icon">📝</span> 新建 Markdown 文件</div>';
        if (window.authRole === 'admin') {
            h += '<div class="fb-menu-divider"></div>' +
                 '<div class="fb-menu-item" onclick="FileBase.refreshKbList();FileBase.hideContextMenu()"><span class="icon">🔄</span> 刷新</div>' +
                 '<div class="fb-menu-item" onclick="FileBase.showCreateNetworkRootFolder();FileBase.hideContextMenu()"><span class="icon">🌐</span> 新建网络文件库</div>';
        } else {
            h += '<div class="fb-menu-divider"></div>' +
                 '<div class="fb-menu-item" onclick="FileBase.refreshKbList();FileBase.hideContextMenu()"><span class="icon">🔄</span> 刷新</div>';
        }
        return h;
    },

    contextRename: async function(path) {
        this.hideContextMenu();
        var oldName = path.split('/').pop();
        var newName = prompt('重命名为：', oldName);
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
            alert(res.message || '重命名失败');
        }
    },

    contextCopyOne: async function(path) {
        this.hideContextMenu();
        var self = this;
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal">';
        h += '<h3>📋 复制到</h3>';
        h += '<p style="color:#666;font-size:12px">' + escapeHtmlText(path) + '</p>';
        h += '<div class="fb-move-tree" style="max-height:300px;overflow-y:auto;border:1px solid #e1e4e8;border-radius:4px;padding:8px;margin:8px 0">';
        h += '<div class="fb-tree-node"><div class="fb-tree-label active" onclick="FileBase._selectMoveDest(\'\', this)" data-dest="">📂 / (根目录)</div></div>';
        h += this._renderMoveTree(this.fbCategoryTree, 0);
        h += '</div>';
        h += '<div style="color:#666;font-size:12px;margin:4px 0">目标: <span id="fb-move-dest-label">根目录</span></div>';
        h += '<div class="fb-modal-actions">';
        h += '<button class="btn" onclick="FileBase.doCopyOne()">复制</button>';
        h += '<button class="fb-btn-cancel" onclick="FileBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        this.fbCopySource = path;
        this.fbMoveDest = '';
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'fb-modal-overlay') self.closeModal(); });
    },

    doCopyOne: async function() {
        var src = this.fbCopySource;
        var dest = this.fbMoveDest || '';
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
            alert(res.message || '复制失败');
        }
    },

    contextMoveOne: function(path) {
        this.hideContextMenu();
        var row = document.querySelector('.fb-file-row[data-local-path="' + path.replace(/\\/g, '\\\\') + '"]');
        if (row) {
            var chk = row.querySelector('.fb-item-check');
            if (chk) chk.checked = true;
        }
        this.showMoveDialog();
    },

    contextDownloadOne: function(path) {
        this.hideContextMenu();
        window.open('/api/fb/' + this.currentFbId + '/local-files/download?path=' + encodeURIComponent(path) + '&token=' + encodeURIComponent(authToken), '_blank');
    },

    contextDeleteOne: async function(path) {
        this.hideContextMenu();
        if (!confirm('确定删除 "' + path.split('/').pop() + '" 吗？（此操作不可恢复）')) return;
        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files', 'DELETE', { paths: [path] });
        if (res.success) {
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            alert(res.message || '删除失败');
        }
    },

    showMoveDialog: function() {
        var items = this.getSelectedPaths();
        if (items.length === 0) {
            alert('请至少选择一个文件或文件夹');
            return;
        }
        var self = this;
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal">';
        h += '<h3>📦 移动到</h3>';
        h += '<p style="color:#666;font-size:12px">已选择 ' + items.length + ' 个项目</p>';
        h += '<div class="fb-move-tree" style="max-height:300px;overflow-y:auto;border:1px solid #e1e4e8;border-radius:4px;padding:8px;margin:8px 0">';
        h += '<div class="fb-tree-node"><div class="fb-tree-label active" onclick="FileBase._selectMoveDest(\'\', this)" data-dest="">📂 / (根目录)</div></div>';
        h += this._renderMoveTree(this.fbCategoryTree, 0);
        h += '</div>';
        h += '<div style="color:#666;font-size:12px;margin:4px 0">目标: <span id="fb-move-dest-label">根目录</span></div>';
        h += '<div class="fb-modal-actions">';
        h += '<button class="btn" onclick="FileBase.doMove()">移动</button>';
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

        var res = await this.api('/api/fb/' + this.currentFbId + '/local-files/move', 'PUT', { sources: sources, dest: dest });
        this.closeModal();
        if (res.success) {
            if (res.errors && res.errors.length > 0) {
                alert('成功移动 ' + res.moved + ' 个，失败: ' + res.errors.join(', '));
            }
            this.fbCategoryTree = null;
            this.fbTreeLoaded = false;
            await this.renderDetail();
        } else {
            alert(res.message || '移动失败');
        }
    },

    dblClickFile: function(event) {
        var row = event.target.closest('.fb-file-row');
        if (!row) return;
        var path = row.getAttribute('data-local-path');
        if (path) this.openFile(path);
    },

    openFile: function(relPath) {
        var ext = relPath.split('.').pop().toLowerCase();
        if (ext === 'md' || ext === 'txt' || ext === 'markdown') {
            this.openMarkdownEditor(relPath);
        } else if (['docx', 'pptx', 'ppt', 'xlsx', 'xls'].includes(ext)) {
            this.openFilePreview(relPath);
        } else if (ext === 'pdf') {
            this.openPdfPreview(relPath);
        } else if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) {
            this.openImagePreview(relPath);
        } else {
            window.open('/api/fb/' + this.currentFbId + '/local-files/open?path=' + encodeURIComponent(relPath) + '&token=' + encodeURIComponent(authToken), '_blank');
        }
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
                var html = (typeof marked !== 'undefined' && res.markdown)
                    ? marked.parse(res.markdown)
                    : (res.markdown || '<div style="text-align: center; padding: 40px; color: #999;">文件内容为空</div>');
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
        var fileUrl = '/api/fb/' + this.currentFbId + '/local-files/open?path=' + encodeURIComponent(relPath) + '&token=' + encodeURIComponent(authToken);
        
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
        var fileUrl = '/api/fb/' + this.currentFbId + '/local-files/open?path=' + encodeURIComponent(relPath) + '&token=' + encodeURIComponent(authToken);
        
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
            '<button class="fb-md-btn-save" onclick="FileBase._saveMdContent()">💾 保存</button>' +
            '<button class="fb-md-btn-close" onclick="FileBase._closeMdEditor()">✖ 关闭</button>' +
            '</div></div>' +
            '<div id="fb-wysiwyg-editor"></div>' +
            '</div>';
        document.body.appendChild(overlay);

        this.fbMdEditorRelPath = relPath;

        var editorEl = document.getElementById('fb-wysiwyg-editor');
        if (typeof Quill !== 'undefined') {
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
                var html = '';
                if (typeof marked !== 'undefined') {
                    html = marked.parse(content);
                }
                quill.clipboard.dangerouslyPasteHTML(html);
            }

            this.fbMdEditorInstance = quill;
        } else {
            editorEl.innerHTML = '<div style="padding:20px;color:#999;">编辑器加载失败，请刷新页面重试</div>';
        }

        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) self._closeMdEditor();
        });
    },

    _saveMdContent: async function() {
        var content = '';
        if (this.fbMdEditorInstance && typeof this.fbMdEditorInstance.root !== 'undefined') {
            var html = this.fbMdEditorInstance.root.innerHTML;
            if (typeof TurndownService !== 'undefined') {
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
            } else {
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
            alert(res.message || '保存失败');
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

    _displayLocalPath: function() {
        return this.fbDisplayPath || this.fbLocalPath || '';
    },

    showSettings: async function() {
        var self = this;
        var res = await this.api('/api/fb/' + this.currentFbId + '/members', 'GET');
        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal">';
        h += '<h3>⚙ 文件库设置</h3><h4>成员管理</h4>';
        if (res.success && res.members) {
            h += '<table class="fb-member-table"><thead><tr><th>用户名</th><th>权限</th><th>操作</th></tr></thead><tbody>';
            for (var i = 0; i < res.members.length; i++) {
                var m = res.members[i];
                h += '<tr><td>' + escapeHtmlText(m.username) + (m.is_owner ? ' (所有者)' : '') + '</td><td>';
                if (m.is_owner) { h += '管理'; }
                else {
                    h += '<select onchange="FileBase._updateMemberPerm(\'' + m.user_id + '\', this.value)">';
                    h += '<option value="view"' + (m.permission==='view'?' selected':'') + '>查看</option>';
                    h += '<option value="edit"' + (m.permission==='edit'?' selected':'') + '>编辑</option>';
                    h += '<option value="manage"' + (m.permission==='manage'?' selected':'') + '>管理</option>';
                    h += '</select>';
                }
                h += '</td><td>';
                if (!m.is_owner) h += '<button class="fb-btn-remove" onclick="FileBase._removeMemberAct(\'' + m.user_id + '\')">移除</button>';
                h += '</td></tr>';
            }
            h += '</tbody></table>';
        }
        h += '<div class="fb-add-member"><input type="text" id="fb-new-member" placeholder="用户名"><select id="fb-new-perm"><option value="view">查看</option><option value="edit">编辑</option><option value="manage">管理</option></select><button onclick="FileBase._addMemberAct()">添加</button></div>';
        h += '<hr style="margin:16px 0"><h4>批量设置用户权限</h4>';
        h += '<div style="display:flex;gap:8px;margin-bottom:8px">';
        h += '<select id="fb-batch-perm"><option value="view">查看</option><option value="edit">编辑</option><option value="manage">管理</option></select>';
        h += '<button onclick="FileBase._batchSetUsers()">应用到所选用户</button>';
        h += '<button onclick="FileBase._batchSetAllUsers()">应用到所有用户</button>';
        h += '</div>';
        h += '<div class="fb-batch-user-list" style="max-height:200px;overflow-y:auto;border:1px solid #e1e4e8;border-radius:4px;padding:8px">';
        var allUsers = JSON.parse(this._lsGet('fb_user_list') || '[]');
        var memberMap = {};
        if (res.success && res.members) {
            for (var j = 0; j < res.members.length; j++) {
                memberMap[res.members[j].username] = res.members[j];
            }
        }
        for (var k = 0; k < allUsers.length; k++) {
            var u = allUsers[k];
            if (u.username === authUsername) continue;
            var curPerm = memberMap[u.username] ? memberMap[u.username].permission : '';
            var checked = curPerm ? ' checked' : '';
            h += '<label style="display:flex;align-items:center;gap:6px;padding:3px 0;font-size:13px;cursor:pointer">';
            h += '<input type="checkbox" class="fb-batch-user-chk" data-username="' + escapeHtmlText(u.username) + '"' + checked + '>';
            h += escapeHtmlText(u.username) + (curPerm ? ' <span style="color:#888;font-size:11px">(' + (curPerm === 'manage' ? '管理' : curPerm === 'edit' ? '编辑' : '查看') + ')</span>' : '');
            h += '</label>';
        }
        h += '</div>';
        h += '<hr style="margin:16px 0"><h4>转让所有权</h4>';
        h += '<div class="fb-add-member"><input type="text" id="fb-transfer-user" placeholder="新所有者用户名"><button onclick="FileBase._transferAct()">转让</button></div>';
        h += '<div class="fb-modal-actions"><button class="fb-btn-cancel" onclick="FileBase.closeModal()">关闭</button></div>';
        h += '</div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'fb-modal-overlay') self.closeModal(); });
    },

    closeModal: function() {
        var ov = document.getElementById('fb-modal-overlay');
        if (ov) ov.remove();
    },

    _updateMemberPerm: async function(uid, perm) {
        await this.api('/api/fb/' + this.currentFbId + '/members/' + uid, 'PUT', { permission: perm });
    },

    _removeMemberAct: async function(uid) {
        if (!confirm('确定要移除该成员吗？')) return;
        await this.api('/api/fb/' + this.currentFbId + '/members/' + uid, 'DELETE');
        var self = this; self.closeModal(); await self.showSettings();
    },

    _addMemberAct: async function() {
        var uname = document.getElementById('fb-new-member').value.trim();
        var perm = document.getElementById('fb-new-perm').value;
        if (!uname) return;
        var res = await this.api('/api/fb/' + this.currentFbId + '/members', 'POST', { username: uname, permission: perm });
        if (res.success) { var self = this; self.closeModal(); await self.showSettings(); }
        else alert(res.message);
    },

    _batchSetUsers: async function() {
        var perm = document.getElementById('fb-batch-perm').value;
        var chks = document.querySelectorAll('.fb-batch-user-chk:checked');
        var count = 0;
        for (var i = 0; i < chks.length; i++) {
            var uname = chks[i].getAttribute('data-username');
            try {
                await this.api('/api/fb/' + this.currentFbId + '/members', 'POST', { username: uname, permission: perm });
                count++;
            } catch (e) {}
        }
        this.closeModal();
        this.showSettings();
        if (count > 0) alert('已为 ' + count + ' 个用户设置权限');
    },

    _batchSetAllUsers: async function() {
        var chks = document.querySelectorAll('.fb-batch-user-chk');
        for (var i = 0; i < chks.length; i++) chks[i].checked = true;
        await this._batchSetUsers();
    },

    _transferAct: async function() {
        var uname = document.getElementById('fb-transfer-user').value.trim();
        if (!uname) return;
        if (!confirm('确定将文件库所有权转让给 ' + uname + ' 吗？')) return;
        var users = JSON.parse(this._lsGet('fb_user_list') || '[]');
        var tid = null;
        for (var i = 0; i < users.length; i++) {
            if (users[i].username === uname) { tid = users[i].user_id; break; }
        }
        if (!tid) { alert('用户不存在'); return; }
        var res = await this.api('/api/fb/' + this.currentFbId + '/transfer', 'POST', { new_owner_id: tid });
        if (res.success) { this.closeModal(); this.currentFbId = null; await this.renderKbList(); }
        else alert(res.message);
    },

    _deleteKbAct: async function() {
        if (!confirm('确定要删除此文件库吗？')) return;
        var res = await this.api('/api/fb/' + this.currentFbId, 'DELETE');
        if (res.success) { this.closeModal(); this.currentFbId = null; await this.renderKbList(); }
        else alert(res.message);
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
        else alert(res.message);
    },

    search: async function() {
        var qEl = document.getElementById('fb-search-input');
        var q = qEl ? qEl.value.trim() : '';
        if (!q) return;

        var res = await this.api('/api/fb/search?q=' + encodeURIComponent(q), 'GET');
        var h = '<h3>🔍 搜索: ' + escapeHtmlText(q) + '</h3>';
        h += '<button onclick="FileBase.init()" style="margin-bottom:8px">← 返回</button>';
        if (res.success && res.results && res.results.length > 0) {
            h += '<table class="fb-file-table"><thead><tr><th>文件库</th><th>文件名</th><th>匹配</th><th>操作</th></tr></thead><tbody>';
            for (var i = 0; i < res.results.length; i++) {
                var r = res.results[i];
                if (!r.rel_path && !r.filebase_type) continue;
                var dirPath = r.rel_path ? r.rel_path.replace(/\\/g, '/').replace(/\/[^\/]+$/, '') : '';
                var clickAction = 'FileBase._openFromSearch(\'' + r.fb_id + '\',\'' + escapeHtmlText(r.fb_name) + '\',\'' + escapeHtmlText(dirPath) + '\')';
                var downloadUrl = '/api/fb/' + r.fb_id + '/local-files/download?path=' + encodeURIComponent(r.rel_path || r.document_id) + '&token=' + encodeURIComponent(authToken);
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
        this.fbCanEdit = false;
        this.fbCanManage = false;
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

        this._lsSet('docproc_current_fb_id', kbId);
        this._lsSet('docproc_current_fb_permission', 'view');
        this._lsSet('docproc_current_fb_name', kbName);
        this._lsSet('docproc_current_fb_local_path', '');
        this._lsSet('docproc_current_fb_display_path', '');

        await this.renderDetail();
    },

    showTrash: async function() {
        var self = this;
        var res = await this.api('/api/fb/trash-list', 'GET');
        var items = res.success ? (res.items || []) : [];

        var h = '<div class="fb-explorer"><div class="fb-breadcrumb">';
        h += '<span class="fb-bc-home" onclick="FileBase.renderKbList()">📁 文件库首页</span>';
        h += '<span class="fb-bc-sep">›</span><span class="fb-bc-current">🗑️ 回收站</span>';
        h += '</div><div class="fb-explorer-body" style="flex-direction:column;border-radius:6px;border:1px solid #e1e4e8;background:#fff">';

        if (items.length === 0) {
            h += '<div class="fb-empty">回收站为空</div>';
        } else {
            h += '<div style="display:flex;padding:8px 12px;gap:8px;border-bottom:1px solid #e1e4e8;background:#fafbfc">';
            h += '<button onclick="FileBase.clearTrash()" class="fb-btn-danger" style="padding:6px 16px;border-radius:4px;cursor:pointer;font-size:13px">🧹 清空回收站</button>';
            h += '</div>';
            h += '<div style="padding:0;overflow-y:auto;flex:1">';
            for (var i = 0; i < items.length; i++) {
                var it = items[i];
                var escName = it.name.replace(/'/g, "\\'");
                h += '<div class="fb-trash-item" style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid #f0f0f0">';
                h += '<div><strong>🗑️ ' + escapeHtmlText(it.name) + '</strong><br><small style="color:#888">' + new Date(it.mtime * 1000).toLocaleString('zh-CN') + '</small></div>';
                h += '<div style="display:flex;gap:8px">';
                h += '<button onclick="FileBase.restoreTrashItem(\'' + escName + '\')" style="padding:5px 14px;border:1px solid #28a745;background:#fff;color:#28a745;border-radius:4px;cursor:pointer;font-size:12px">↩ 恢复</button>';
                h += '<button onclick="FileBase.deleteTrashItem(\'' + escName + '\')" class="fb-btn-remove" style="padding:5px 14px;border-radius:4px;cursor:pointer;font-size:12px">彻底删除</button>';
                h += '</div></div>';
            }
            h += '</div>';
        }

        h += '</div></div>';
        document.getElementById('content-view').innerHTML = h;
    },

    restoreTrashItem: async function(name) {
        var res = await this.api('/api/fb/trash-restore', 'POST', { name: name });
        if (res.success) {
            await this.renderKbList();
        } else {
            alert(res.message || '恢复失败');
        }
    },

    deleteTrashItem: async function(name) {
        if (!confirm('确定彻底删除 "' + name + '" 吗？此操作不可恢复！')) return;
        var url = '/api/fb/trash-item?name=' + encodeURIComponent(name) + '&token=' + encodeURIComponent(authToken);
        await fetch(url, { method: 'DELETE' });
        await this.showTrash();
    },

    clearTrash: async function() {
        if (!confirm('确定清空回收站吗？此操作不可恢复！')) return;
        await this.api('/api/fb/trash', 'DELETE');
        await this.renderKbList();
    },

    getFileIcon: function(ext) {
        var e = (ext || '').toLowerCase();
        var cls = 'fb-file-icon-file fb-icon-other', label = '?';
        if (e === '.doc' || e === '.docx') { cls = 'fb-file-icon-file fb-icon-doc'; label = 'W'; }
        else if (e === '.xls' || e === '.xlsx') { cls = 'fb-file-icon-file fb-icon-xls'; label = 'X'; }
        else if (e === '.ppt' || e === '.pptx') { cls = 'fb-file-icon-file fb-icon-ppt'; label = 'P'; }
        else if (e === '.pdf') { cls = 'fb-file-icon-file fb-icon-pdf'; label = 'P'; }
        else if (e === '.md') { cls = 'fb-file-icon-file fb-icon-md'; label = 'M'; }
        else if (e === '.txt') { cls = 'fb-file-icon-file fb-icon-txt'; label = 'T'; }
        else if (e === '.html' || e === '.htm') { cls = 'fb-file-icon-file fb-icon-html'; label = 'H'; }
        else if (/^\.(jpe?g|png|gif|svg|bmp|webp|ico)$/i.test(e)) { cls = 'fb-file-icon-file fb-icon-img'; label = 'I'; }
        else if (/^\.(zip|rar|7z|tar|gz)$/i.test(e)) { cls = 'fb-file-icon-file fb-icon-zip'; label = 'Z'; }
        return '<span class="' + cls + '" style="overflow:hidden;">' + label + '</span>';
    },

    formatSize: function(bytes) {
        if (!bytes) return '0 B';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    },

    formatDate: function(ts) {
        return new Date(ts * 1000).toLocaleString('zh-CN');
    }
};

function escapeHtmlText(text) {
    if (!text) return '';
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
