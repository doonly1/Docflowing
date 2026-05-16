var KnowledgeBase = {

    _lsGet: function(key) { try { return localStorage.getItem(key); } catch(e) { return null; } },
    _lsSet: function(key, val) { try { localStorage.setItem(key, val); } catch(e) {} },
    _lsDel: function(key) { try { localStorage.removeItem(key); } catch(e) {} },

    currentKbId: null,
    currentPermission: null,
    selectedDocs: {},
    currentSort: { field: 'mtime', asc: false },
    currentPath: [],
    kbName: '',
    canEdit: false,
    canManage: false,
    localPath: '',
    localCurrentSubdir: '',
    _categoryTree: null,
    _treeLoaded: false,
    _expandedTreePaths: {},  // 跟踪手动展开的树节点路径

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
            if (res.success) this._lsSet('kb_user_list', JSON.stringify(res.users));
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
        if (this.currentKbId) {
            await this.renderDetail();
        } else {
            await this.renderKbList();
        }
    },

    goBackToList: function() {
        this.currentKbId = null;
        this.localPath = '';
        this.renderKbList();
    },

    navigateTo: function(view) {
        if (typeof globalNavigateTo === 'function') { globalNavigateTo(view); return; }
        if (view === 'home') {
            document.getElementById('kb-view').style.display = 'none';
            document.getElementById('home-view').style.display = '';
            this.currentKbId = null;
        } else if (view === 'fb') {
            document.getElementById('home-view').style.display = 'none';
            document.getElementById('kb-view').style.display = '';
            this.init();
        }
    },

    refreshKbList: async function() {
        this.hideContextMenu();
        await this.renderKbList();
    },

    renderKbList: async function() {
        try {
            this.currentKbId = null;
            this.localPath = '';
            this.currentPath = [{ id: null, name: '文件库', type: 'home' }];
            this._lsDel('docproc_current_kb_id');
            this._lsDel('docproc_current_kb_name');
            this._lsDel('docproc_current_kb_local_path');
            this._lsDel('docproc_current_kb_display_path');
            this._lsDel('docproc_current_kb_permission');
            this._lsDel('docproc_current_subdir');
            this._expandedTreePaths = {};
            var role = this.getUserRole();

            var kbView = document.getElementById('kb-view');
            if (!kbView) {
                console.warn('kb-view not found, cannot render list');
                return;
            }

            // 重新构建整个视图
            var h = '<div class="kb-explorer">';
            h += '<div class="kb-breadcrumb"><span class="kb-bc-current">🏠 文件库</span></div>';
            h += '<div class="kb-explorer-body" style="border-radius:6px;border:1px solid #e1e4e8;background:#fff">';
            h += '<div class="kb-file-pane" style="width:100%">';
            h += '<div class="kb-file-toolbar">';
            h += '<input type="text" id="kb-search-input" placeholder="搜索文档..." onkeydown="if(event.keyCode===13) KnowledgeBase.search()">';
            h += '<button onclick="KnowledgeBase.search()">🔍 搜索</button>';
            h += '<button onclick="KnowledgeBase.showCreateRootFolder()">📁 新建文件库</button>';
            if (window.authRole === 'admin') h += '<button onclick="KnowledgeBase.showCreateNetworkRootFolder()">🌐 新建网络文件库</button>';
            h += '<span class="kb-toolbar-spacer"></span>';
            h += '<button onclick="KnowledgeBase.showTrash()">🗑️ 回收站</button>';
            h += '</div>';
            h += '<div class="kb-file-body" id="kb-grid-container" oncontextmenu="KnowledgeBase.showKbListContextMenu(event)"></div>';
            h += '</div></div></div>';
            kbView.innerHTML = h;

            var grid = document.getElementById('kb-grid-container');
            if (!grid) {
                console.warn('kb-grid-container not found');
                return;
            }

            // 显示加载中
            grid.innerHTML = '<div class="kb-empty">刷新中...</div>';

            var res = await this.api('/api/fb/list', 'GET');
            if (!res || !res.success) {
                grid.innerHTML = '<div class="kb-empty">刷新失败: ' + (res?.message || '未知错误') + '</div>';
                return;
            }

            var kbs = res.kbs || [];

            if (kbs.length === 0) {
                grid.innerHTML = '<div class="kb-empty">暂无文件库，点击上方按钮创建</div>';
                return;
            }

            var html = '<div class="kb-grid">';
            for (var i = 0; i < kbs.length; i++) {
                var kb = kbs[i];
                html += '<div class="kb-card" data-kb-id="' + kb.id + '" data-kb-permission="' + kb.permission + '" data-kb-name="' + escapeHtmlText(kb.name) + '" data-kb-type="' + (kb.filebase_type || 'local') + '" data-kb-local-path="' + escapeHtmlText(kb.local_path || '') + '" data-kb-display-path="' + escapeHtmlText(kb.display_path || '') + '" onclick="KnowledgeBase.openKb(\'' + kb.id + '\',\'' + kb.permission + '\',\'' + escapeHtmlText(kb.name) + '\',\'' + escapeHtmlText(kb.local_path || '') + '\',\'' + escapeHtmlText(kb.display_path || '') + '\')">';
                html += '<h3>📁 ' + escapeHtmlText(kb.name) + '</h3>';
                html += '<div class="kb-card-meta">' + (kb.display_path || kb.local_path || '') + '</div>';
                html += '<div class="kb-card-sync-status" id="sync-status-' + kb.id + '" data-kb-id="' + kb.id + '"></div>';
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
            var grid = document.getElementById('kb-grid-container');
            if (grid) {
                grid.innerHTML = '<div class="kb-empty">刷新出错: ' + e.message + '</div>';
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
        var h = '<div class="kb-modal-overlay" id="kb-modal-overlay"><div class="kb-modal" style="max-width:420px">';
        h += '<h3>🌐 新建网络文件库</h3>';
        h += '<div style="margin-bottom:12px">';
        h += '<label style="display:block;font-size:13px;color:#555;margin-bottom:4px">网络路径</label>';
        h += '<input type="text" id="kb-net-path" placeholder="如 \\\\server\\share\\folder" style="width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px;box-sizing:border-box">';
        h += '</div>';
        h += '<div class="kb-modal-actions">';
        h += '<button class="btn" onclick="KnowledgeBase._doCreateNetworkRootFolder()" style="background:#e94560;color:#fff;border:none;padding:6px 20px;border-radius:4px;cursor:pointer;font-size:13px">创建</button>';
        h += '<button class="kb-btn-cancel" onclick="KnowledgeBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('kb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'kb-modal-overlay') self.closeModal(); });
        setTimeout(function() { document.getElementById('kb-net-path').focus(); }, 100);
    },

    _doCreateNetworkRootFolder: async function() {
        var networkPath = (document.getElementById('kb-net-path').value || '').trim();
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
        var kbCard = target.closest('.kb-card');

        var menu = document.createElement('div');
        menu.className = 'kb-context-menu';
        menu.id = 'kb-context-menu';

        if (kbCard) {
            var kbId = kbCard.getAttribute('data-kb-id');
            var kbName = kbCard.getAttribute('data-kb-name');
            var kbPermission = kbCard.getAttribute('data-kb-permission');
            var kbLocalPath = kbCard.getAttribute('data-kb-local-path');
            var kbDisplayPath = kbCard.getAttribute('data-kb-display-path');
            menu.innerHTML = this._buildKbCardContextMenu(kbId, kbName, kbPermission, kbLocalPath, kbDisplayPath);
        } else {
            var emptyMenu = '<div class="kb-menu-item" onclick="KnowledgeBase.showCreateRootFolder();KnowledgeBase.hideContextMenu()"><span class="icon">📁</span> 新建文件库</div>';
            if (window.authRole === 'admin') {
                emptyMenu += '<div class="kb-menu-item" onclick="KnowledgeBase.showCreateNetworkRootFolder();KnowledgeBase.hideContextMenu()"><span class="icon">🌐</span> 新建网络文件库</div>';
            }
            emptyMenu += '<div class="kb-menu-divider"></div><div class="kb-menu-item" onclick="KnowledgeBase.refreshKbList()"><span class="icon">🔄</span> 刷新</div>';
            menu.innerHTML = emptyMenu;
        }

        menu.style.left = Math.min(event.clientX, window.innerWidth - 180) + 'px';
        menu.style.top = Math.min(event.clientY, window.innerHeight - 160) + 'px';
        document.body.appendChild(menu);

        this._hideContextMenuHandler = function() { KnowledgeBase.hideContextMenu(); };
        setTimeout(function() {
            document.addEventListener('click', KnowledgeBase._hideContextMenuHandler);
        }, 0);
    },

    _buildKbCardContextMenu: function(kbId, kbName, permission, localPath, displayPath) {
        var escId = kbId.replace(/'/g, "\\'");
        var escName = (kbName || '').replace(/'/g, "\\'");
        var escLocalPath = (localPath || '').replace(/'/g, "\\'");
        var escDisplayPath = (displayPath || '').replace(/'/g, "\\'");

        var h = '';
        if (permission === 'manage') {
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.kbListManage(\'' + escId + '\')"><span class="icon">⚙</span> 管理</div>';
            h += '<div class="kb-menu-divider"></div>';
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.toggleSync(\'' + escId + '\')"><span class="icon">☁️</span> 同步到 KB</div>';
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.syncNow(\'' + escId + '\')"><span class="icon">🔄</span> 立即同步</div>';
            h += '<div class="kb-menu-divider"></div>';
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.kbListRename(\'' + escId + '\',\'' + escName + '\')"><span class="icon">✏️</span> 重命名</div>';
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.kbListCopy(\'' + escId + '\',\'' + escName + '\')"><span class="icon">📋</span> 复制</div>';
            h += '<div class="kb-menu-divider"></div>';
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.kbListDelete(\'' + escId + '\',\'' + escName + '\')"><span class="icon">🗑️</span> 删除</div>';
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
            if (res.success) {
                alert('同步已触发');
            } else {
                alert(res.message || '同步失败');
            }
        } catch (e) {
            alert('同步失败: ' + e.message);
        }
    },

    kbListManage: function(kbId) {
        this.hideContextMenu();
        this.currentKbId = kbId;
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
        this.currentKbId = kbId;
        this.currentPermission = permission;
        this.canEdit = permission === 'edit' || permission === 'manage';
        this.canManage = permission === 'manage';
        this.selectedDocs = {};
        this.kbName = name || '';
        this.localPath = localPath || '';
        this.displayPath = displayPath || '';
        this.localCurrentSubdir = '';
        this.currentPath = [{ id: kbId, name: name || '未知文件库', type: 'kb' }];
        this.currentSort = { field: 'mtime', asc: false };
        this._categoryTree = null;
        this._treeLoaded = false;
        this._expandedTreePaths = {};

        this._lsSet('docproc_current_kb_id', kbId);
        this._lsSet('docproc_current_kb_permission', permission);
        this._lsSet('docproc_current_kb_name', name || '');
        this._lsSet('docproc_current_kb_local_path', localPath || '');
        this._lsSet('docproc_current_kb_display_path', displayPath || '');
        this._lsDel('docproc_current_subdir');

        await this.renderDetail();
    },

    renderDetail: async function() {
        var self = this;

        var fileContent = document.getElementById('kb-file-content');
        if (!fileContent) {
            var h = '<div class="kb-explorer">';
            h += '<div class="kb-breadcrumb" id="kb-breadcrumb"></div>';
            h += '<div class="kb-explorer-body">';
            h += '<div class="kb-file-toolbar" id="kb-file-toolbar">';
            h += '<button class="kb-tree-toggle-btn" onclick="KnowledgeBase.toggleTreePane()" title="折叠/展开"></button>';
            h += '<div class="kb-upload-wrap">';
            h += '<button onclick="KnowledgeBase.toggleUploadMenu(event)">📤 上传</button>';
            h += '<div class="kb-upload-menu" style="display:none">';
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.triggerFileUpload()"><span class="icon">📄</span> 上传文件</div>';
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.triggerFolderUpload()"><span class="icon">📁</span> 上传文件夹</div>';
            h += '</div>';
            h += '</div>';
            h += '<button onclick="KnowledgeBase.showCreateFolderDialog()">📁 新建文件夹</button>';
            h += '<button onclick="KnowledgeBase.showCreateMdDialog()">📝 新建MD文件</button>';
            h += '<span class="kb-toolbar-spacer"></span>';
            h += '<input type="text" id="kb-search-input" placeholder="搜索..." onkeydown="if(event.keyCode===13) KnowledgeBase.search()">';
            h += '<button onclick="KnowledgeBase.search()">🔍</button>';
            h += '<button onclick="KnowledgeBase.downloadAction()">📥 下载</button>';
            h += '<button onclick="KnowledgeBase.showMoveDialog()">📦 移动</button>';
            h += '<button onclick="KnowledgeBase.batchDelete()">🗑️ 删除</button>';
            h += '<input type="file" id="kb-file-upload-input" multiple style="display:none" onchange="KnowledgeBase.handleFileUpload(this)">';
            h += '<input type="file" id="kb-folder-upload-input" webkitdirectory style="display:none" onchange="KnowledgeBase.handleFolderUpload(this)">';
            h += '<input type="file" id="kb-replace-input" style="display:none" onchange="KnowledgeBase.handleReplace(this)">';
            h += '</div>';
            h += '<div class="kb-body-row">';
            h += '<div class="kb-tree-pane" id="kb-tree-pane"><div class="kb-tree-title">目录</div><div id="kb-tree-content"></div></div>';
            h += '<div class="kb-tree-resize-handle" id="kb-tree-resize-handle"></div>';
            h += '<div class="kb-file-pane" id="kb-file-pane">';
            h += '<div class="kb-file-body" id="kb-file-body" oncontextmenu="KnowledgeBase.showContextMenu(event)">';
            h += '<div id="kb-file-content"></div>';
            h += '</div></div></div></div>';

            document.getElementById('kb-view').innerHTML = h;
            if (this._lsGet('kb_tree_collapsed') === '1') {
                document.querySelector('.kb-explorer-body').classList.add('collapsed');
            }
            this.initTreeResize();
        }
        this.renderBreadcrumb();

        if (!this._treeLoaded) {
            var res = await this.api('/api/fb/' + this.currentKbId + '/local-categories?recursive=1', 'GET');
            this._categoryTree = res.success ? (res.categories || []) : [];
            this._treeLoaded = true;
        }
        this.renderCategoryTree();
        await this.loadFiles();
        this.initTreeResize();
    },

    renderBreadcrumb: function() {
        var el = document.getElementById('kb-breadcrumb');
        if (!el) return;
        var h = '<span class="kb-bc-home" onclick="KnowledgeBase.currentKbId=null;KnowledgeBase.renderKbList()">🏠 文件库</span>';
        for (var i = 0; i < this.currentPath.length; i++) {
            var p = this.currentPath[i];
            h += '<span class="kb-bc-sep">›</span>';
            if (i < this.currentPath.length - 1) {
                h += '<span class="kb-bc-item" onclick="KnowledgeBase.breadcrumbClick(' + i + ')">' + escapeHtmlText(p.name) + '</span>';
            } else {
                h += '<span class="kb-bc-current">' + escapeHtmlText(p.name) + '</span>';
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
        this.localCurrentSubdir = parts.join('/');
        this._lsSet('docproc_current_subdir', this.localCurrentSubdir);
        await this.renderDetail();
    },

    renderCategoryTree: function() {
        var content = document.getElementById('kb-tree-content');
        if (!content) return;

        var curPathNorm = (this.localCurrentSubdir || '').replace(/\\/g, '/');
        var pathParts = curPathNorm ? ('/' + curPathNorm).replace(/\/+/g, '/') : '/';

        var h = '<div class="kb-tree-node">';
        h += '<div class="kb-tree-label' + (!curPathNorm ? ' active' : '') + '" onclick="KnowledgeBase.goToRoot()">📂 ' + (escapeHtmlText(this.kbName) || '文件库') + '</div>';
        h += '</div>';

        h += this._renderTreeNodes(this._categoryTree, 0, pathParts);
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
            var shouldExpand = isInActivePath || !!this._expandedTreePaths[nodePath];
            var h2 = '';
            if (hasChildren) {
                h2 = this._renderTreeNodes(n.children, depth + 1, activePath);
            }
            h += '<div class="kb-tree-node">';
            h += '<div class="kb-tree-label' + (isActive ? ' active' : '') + '" style="padding-left:' + (ml + 8) + 'px" onclick="KnowledgeBase._treeLabelClick(this, \'' + (n.path || '').replace(/'/g, "\\'") + '\')">';
            if (hasChildren) {
                h += '<span class="kb-tree-toggle' + (shouldExpand ? ' open' : '') + '" onclick="event.stopPropagation();KnowledgeBase.toggleTreeNode(this)"></span>';
            } else {
                h += '<span class="kb-tree-toggle" style="visibility:hidden"></span>';
            }
            h += '<span class="icon">📁</span>' + escapeHtmlText(n.name);
            h += '</div>';
            if (hasChildren) {
                h += '<div class="kb-tree-children' + (shouldExpand ? ' open' : '') + '">';
                h += h2;
                h += '</div>';
            }
            h += '</div>';
        }
        return h;
    },

    _treeLabelClick: function(labelEl, path) {
        var toggleEl = labelEl.querySelector('.kb-tree-toggle');
        if (toggleEl && toggleEl.style.visibility !== 'hidden') {
            var nodePath = '/' + (path || '').replace(/\\/g, '/').replace(/\/+/g, '/');
            var isCurrentlyOpen = !!KnowledgeBase._expandedTreePaths[nodePath];
            if (isCurrentlyOpen) {
                delete KnowledgeBase._expandedTreePaths[nodePath];
            } else {
                KnowledgeBase._expandedTreePaths[nodePath] = true;
            }
        }
        KnowledgeBase.navigateSubdir(path);
    },

    toggleTreeNode: function(toggleEl) {
        var childrenDiv = toggleEl.parentElement.nextElementSibling;
        if (!childrenDiv || !childrenDiv.classList.contains('kb-tree-children')) return;
        var isOpen = childrenDiv.classList.contains('open');
        // 同步更新展开状态数据
        var labelEl = toggleEl.parentElement;
        var onclickAttr = labelEl.getAttribute('onclick') || '';
        var match = onclickAttr.match(/KnowledgeBase\._treeLabelClick\([^,]+,\s*'([^']+)'/);
        if (match) {
            var path = match[1];
            var nodePath = '/' + path.replace(/\\/g, '/').replace(/\/+/g, '/');
            if (isOpen) {
                delete KnowledgeBase._expandedTreePaths[nodePath];
            } else {
                KnowledgeBase._expandedTreePaths[nodePath] = true;
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
        this.localCurrentSubdir = '';
        this.currentSort = { field: 'mtime', asc: false };
        this.selectedDocs = {};
        this._lsDel('docproc_current_subdir');
        this.renderDetail();
    },

    navigateSubdir: function(subdir) {
        this.localCurrentSubdir = subdir || '';
        this.currentSort = { field: 'mtime', asc: false };
        this.selectedDocs = {};
        this.currentPath = [{ id: this.currentKbId, name: this.kbName || '未知文件库', type: 'kb' }];
        if (subdir) {
            var parts = subdir.replace(/\\/g, '/').split('/');
            for (var i = 0; i < parts.length; i++) {
                this.currentPath.push({ id: parts[i], name: parts[i], type: 'category' });
            }
        }
        this._lsSet('docproc_current_subdir', this.localCurrentSubdir);
        this.renderDetail();
    },

    loadFiles: async function() {
        var div = document.getElementById('kb-file-content');
        if (!div) return;
        var url = '/api/fb/' + this.currentKbId + '/local-files';
        if (this.localCurrentSubdir) url += '?subdir=' + encodeURIComponent(this.localCurrentSubdir);
        var res = await this.api(url, 'GET');

        if (!res.success || (!res.files && !res.categories)) {
            div.innerHTML = '<div class="kb-empty">此目录为空或不可访问</div>';
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
        var h = '<table class="kb-file-table"><thead><tr>';
        h += '<th class="col-check"><input type="checkbox" id="kb-select-all" onchange="KnowledgeBase.toggleSelectAll(this)" title="全选/取消"></th>';
        h += '<th class="col-icon"></th>';
        h += '<th class="col-name" onclick="KnowledgeBase.setSort(\'name\')">名称<span class="sort-arrow">' + (sf === 'name' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-date" onclick="KnowledgeBase.setSort(\'mtime\')">修改时间<span class="sort-arrow">' + (sf === 'mtime' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-type" onclick="KnowledgeBase.setSort(\'ext\')">类型<span class="sort-arrow">' + (sf === 'ext' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-size" onclick="KnowledgeBase.setSort(\'size\')">大小<span class="sort-arrow">' + (sf === 'size' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-actions">操作</th></tr></thead><tbody>';

        for (var i = 0; i < categories.length; i++) {
            var cat = categories[i];
            var catEscPathAttr = cat.path.replace(/'/g, "\\'");
            h += '<tr class="kb-file-row kb-local-dir" data-local-path="' + catEscPathAttr + '">';
            h += '<td class="col-check"><input type="checkbox" class="kb-item-check" data-path="' + catEscPathAttr + '" data-type="dir" onclick="event.stopPropagation()"></td>';
            h += '<td class="col-icon"><span class="kb-file-icon">📁</span></td>';
            h += '<td class="col-name"><div class="kb-file-name" onclick="KnowledgeBase.navigateSubdir(\'' + cat.path.replace(/'/g, "\\'") + '\')">' + escapeHtmlText(cat.name) + '</div></td>';
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

            h += '<tr class="kb-file-row" data-local-path="' + escPath + '" data-doc-name="' + fname + '">';
            h += '<td class="col-check"><input type="checkbox" class="kb-item-check" data-path="' + escPathAttr + '" data-type="file" onclick="event.stopPropagation()"></td>';
            h += '<td class="col-icon"><span class="kb-file-icon">' + icon + '</span></td>';
            h += '<td class="col-name"><div class="kb-file-name" ondblclick="KnowledgeBase.dblClickFile(event)" onclick="event.stopPropagation()">' + fname + '<span class="kb-file-type-tag">' + ext + '</span></div></td>';
            h += '<td class="col-date"><span class="kb-file-date">' + date + '</span></td>';
            h += '<td class="col-type">' + ext + '</td>';
            h += '<td class="col-size"><span class="kb-file-size">' + size + '</span></td>';
            h += '<td class="col-actions"><span class="kb-file-actions">';
            h += '<a href="#" onclick="KnowledgeBase.triggerReplace(\'' + escPathAttr + '\');return false">替换</a>';
            h += '<a href="#" onclick="KnowledgeBase.openFile(\'' + escPath + '\');return false">打开</a>';
            h += '</span></td></tr>';
        }
        h += '</tbody></table>';
        div.innerHTML = h;
    },

    toggleSelectAll: function(el) {
        var checks = document.querySelectorAll('.kb-item-check');
        for (var i = 0; i < checks.length; i++) {
            checks[i].checked = el.checked;
        }
    },

    getSelectedPaths: function() {
        var checks = document.querySelectorAll('.kb-item-check:checked');
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
            window.open('/api/fb/' + this.currentKbId + '/local-files/download?path=' + encodeURIComponent(items[0].path) + '&token=' + encodeURIComponent(authToken), '_blank');
        } else {
            var paths = [];
            for (var i = 0; i < items.length; i++) {
                paths.push(items[i].path);
            }
            if (paths.length === 0) {
                alert('请至少选择一个文件或文件夹');
                return;
            }
            var url = '/api/fb/' + this.currentKbId + '/local-files/batch-download?token=' + encodeURIComponent(authToken);
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
        var res = await this.api('/api/fb/' + this.currentKbId + '/local-files', 'DELETE', { paths: paths });
        if (res.success) {
            this._categoryTree = null;
            this._treeLoaded = false;
            if (res.errors && res.errors.length > 0) {
                alert('成功删除 ' + res.deleted + ' 个，失败: ' + res.errors.join(', '));
            }
            await self.renderDetail();
        } else {
            alert(res.message || '删除失败');
        }
    },

    triggerReplace: function(relPath) {
        this._replacePath = relPath;
        var inp = document.getElementById('kb-replace-input');
        if (inp) inp.click();
    },

    handleReplace: async function(fileInput) {
        var relPath = this._replacePath;
        if (!relPath || !fileInput.files || !fileInput.files[0]) return;
        this._replacePath = null;

        var formData = new FormData();
        formData.append('file', fileInput.files[0]);

        var url = '/api/fb/' + this.currentKbId + '/local-files/replace?path=' + encodeURIComponent(relPath) + '&token=' + encodeURIComponent(authToken);
        var resp = await fetch(url, { method: 'PUT', body: formData });
        var res = await resp.json();
        fileInput.value = '';

        if (res.success) {
            this._categoryTree = null;
            this._treeLoaded = false;
            await this.renderDetail();
        } else {
            alert(res.message || '替换失败');
        }
    },

    toggleUploadMenu: function(e) {
        e.stopPropagation();
        var menu = document.querySelector('.kb-upload-menu');
        if (!menu) return;
        var isVisible = menu.style.display === 'block';
        this._hideAllMenus();
        if (!isVisible) {
            menu.style.display = 'block';
            var self = this;
            this._hideUploadMenuHandler = function() { self._hideAllMenus(); };
            setTimeout(function() {
                document.addEventListener('click', self._hideUploadMenuHandler);
            }, 0);
        }
    },

    _hideAllMenus: function() {
        var menus = document.querySelectorAll('.kb-upload-menu');
        for (var i = 0; i < menus.length; i++) {
            menus[i].style.display = 'none';
        }
        if (this._hideUploadMenuHandler) {
            document.removeEventListener('click', this._hideUploadMenuHandler);
            this._hideUploadMenuHandler = null;
        }
    },

    triggerFileUpload: function() {
        this._hideAllMenus();
        var inp = document.getElementById('kb-file-upload-input');
        if (inp) inp.click();
    },

    triggerFolderUpload: function() {
        this._hideAllMenus();
        var inp = document.getElementById('kb-folder-upload-input');
        if (inp) inp.click();
    },

    triggerUpload: function() {
        var inp = document.getElementById('kb-file-upload-input');
        if (inp) inp.click();
    },

    handleFileUpload: async function(fileInput) {
        if (!fileInput.files || fileInput.files.length === 0) return;
        var self = this;
        var formData = new FormData();
        for (var i = 0; i < fileInput.files.length; i++) {
            formData.append('files', fileInput.files[i]);
        }

        var subdir = this.localCurrentSubdir || '';
        var url = '/api/fb/' + this.currentKbId + '/local-files?subdir=' + encodeURIComponent(subdir) + '&token=' + encodeURIComponent(authToken);
        var resp = await fetch(url, { method: 'POST', body: formData });
        var res = await resp.json();
        fileInput.value = '';

        if (res.success) {
            self._categoryTree = null;
            self._treeLoaded = false;
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

        var subdir = this.localCurrentSubdir || '';
        var url = '/api/fb/' + this.currentKbId + '/local-files?subdir=' + encodeURIComponent(subdir) + '&token=' + encodeURIComponent(authToken);
        var resp = await fetch(url, { method: 'POST', body: formData });
        var res = await resp.json();
        fileInput.value = '';

        if (res.success) {
            self._categoryTree = null;
            self._treeLoaded = false;
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
        var res = await this.api('/api/fb/' + this.currentKbId + '/local-files/dir', 'POST', {
            name: name,
            parent: this.localCurrentSubdir || ''
        });
        if (res.success) {
            self._categoryTree = null;
            self._treeLoaded = false;
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
        var res = await this.api('/api/fb/' + this.currentKbId + '/local-files/create', 'POST', {
            name: name,
            parent: this.localCurrentSubdir || ''
        });
        if (res.success) {
            self._categoryTree = null;
            self._treeLoaded = false;
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
        var fileRow = target.closest('.kb-file-row');

        var menu = document.createElement('div');
        menu.className = 'kb-context-menu';
        menu.id = 'kb-context-menu';
        menu.style.zIndex = '4000';

        if (fileRow) {
            var path = fileRow.getAttribute('data-local-path') || '';
            var isDir = fileRow.classList.contains('kb-local-dir');
            menu.innerHTML = this._buildFileContextMenu(path, isDir);
        } else {
            menu.innerHTML = this._buildEmptyContextMenu();
        }

        menu.style.left = Math.min(event.clientX, window.innerWidth - 180) + 'px';
        menu.style.top = Math.min(event.clientY, window.innerHeight - 220) + 'px';
        document.body.appendChild(menu);

        this._hideContextMenuHandler = function() { KnowledgeBase.hideContextMenu(); };
        setTimeout(function() {
            document.addEventListener('click', KnowledgeBase._hideContextMenuHandler);
        }, 0);
    },

    hideContextMenu: function() {
        var menu = document.getElementById('kb-context-menu');
        if (menu) menu.remove();
        if (this._hideContextMenuHandler) {
            document.removeEventListener('click', this._hideContextMenuHandler);
            this._hideContextMenuHandler = null;
        }
    },

    _buildFileContextMenu: function(path, isDir) {
        var escPath = path.replace(/'/g, "\\'");
        var h = '';
        h += '<div class="kb-menu-item" onclick="KnowledgeBase.contextRename(\'' + escPath + '\')"><span class="icon">✏️</span> 重命名</div>';
        h += '<div class="kb-menu-item" onclick="KnowledgeBase.contextCopyOne(\'' + escPath + '\')"><span class="icon">📋</span> 复制</div>';
        h += '<div class="kb-menu-item" onclick="KnowledgeBase.contextMoveOne(\'' + escPath + '\')"><span class="icon">📦</span> 移动</div>';
        h += '<div class="kb-menu-item" onclick="KnowledgeBase.contextDownloadOne(\'' + escPath + '\')"><span class="icon">📥</span> 下载</div>';
        h += '<div class="kb-menu-divider"></div>';
        h += '<div class="kb-menu-item" onclick="KnowledgeBase.contextDeleteOne(\'' + escPath + '\')"><span class="icon">🗑️</span> 删除</div>';
        return h;
    },

    _buildEmptyContextMenu: function() {
        var h = '<div class="kb-menu-item" onclick="KnowledgeBase.showCreateFolderDialog();KnowledgeBase.hideContextMenu()"><span class="icon">📁</span> 新建文件夹</div>' +
                '<div class="kb-menu-item" onclick="KnowledgeBase.showCreateMdDialog();KnowledgeBase.hideContextMenu()"><span class="icon">📝</span> 新建 Markdown 文件</div>';
        if (window.authRole === 'admin') {
            h += '<div class="kb-menu-divider"></div>' +
                 '<div class="kb-menu-item" onclick="KnowledgeBase.goBackToList();KnowledgeBase.hideContextMenu()"><span class="icon">🔙</span> 返回文件库列表</div>' +
                 '<div class="kb-menu-item" onclick="KnowledgeBase.showCreateNetworkRootFolder();KnowledgeBase.hideContextMenu()"><span class="icon">🌐</span> 新建网络文件库</div>';
        } else {
            h += '<div class="kb-menu-divider"></div>' +
                 '<div class="kb-menu-item" onclick="KnowledgeBase.goBackToList();KnowledgeBase.hideContextMenu()"><span class="icon">🔙</span> 返回文件库列表</div>';
        }
        return h;
    },

    contextRename: async function(path) {
        this.hideContextMenu();
        var oldName = path.split('/').pop();
        var newName = prompt('重命名为：', oldName);
        if (!newName || !newName.trim() || newName.trim() === oldName) return;
        var res = await this.api('/api/fb/' + this.currentKbId + '/local-files/rename', 'PUT', {
            path: path,
            new_name: newName.trim()
        });
        if (res.success) {
            this._categoryTree = null;
            this._treeLoaded = false;
            await this.renderDetail();
        } else {
            alert(res.message || '重命名失败');
        }
    },

    contextCopyOne: async function(path) {
        this.hideContextMenu();
        var self = this;
        var h = '<div class="kb-modal-overlay" id="kb-modal-overlay"><div class="kb-modal">';
        h += '<h3>📋 复制到</h3>';
        h += '<p style="color:#666;font-size:12px">' + escapeHtmlText(path) + '</p>';
        h += '<div class="kb-move-tree" style="max-height:300px;overflow-y:auto;border:1px solid #e1e4e8;border-radius:4px;padding:8px;margin:8px 0">';
        h += '<div class="kb-tree-node"><div class="kb-tree-label active" onclick="KnowledgeBase._selectMoveDest(\'\', this)" data-dest="">📂 / (根目录)</div></div>';
        h += this._renderMoveTree(this._categoryTree, 0);
        h += '</div>';
        h += '<div style="color:#666;font-size:12px;margin:4px 0">目标: <span id="kb-move-dest-label">根目录</span></div>';
        h += '<div class="kb-modal-actions">';
        h += '<button class="btn" onclick="KnowledgeBase.doCopyOne()">复制</button>';
        h += '<button class="kb-btn-cancel" onclick="KnowledgeBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        this._copySource = path;
        this._moveDest = '';
        document.getElementById('kb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'kb-modal-overlay') self.closeModal(); });
    },

    doCopyOne: async function() {
        var src = this._copySource;
        var dest = this._moveDest || '';
        var res = await this.api('/api/fb/' + this.currentKbId + '/local-files/copy', 'POST', {
            sources: [src],
            dest: dest
        });
        this.closeModal();
        if (res.success) {
            this._categoryTree = null;
            this._treeLoaded = false;
            await this.renderDetail();
        } else {
            alert(res.message || '复制失败');
        }
    },

    contextMoveOne: function(path) {
        this.hideContextMenu();
        var row = document.querySelector('.kb-file-row[data-local-path="' + path.replace(/\\/g, '\\\\') + '"]');
        if (row) {
            var chk = row.querySelector('.kb-item-check');
            if (chk) chk.checked = true;
        }
        this.showMoveDialog();
    },

    contextDownloadOne: function(path) {
        this.hideContextMenu();
        window.open('/api/fb/' + this.currentKbId + '/local-files/download?path=' + encodeURIComponent(path) + '&token=' + encodeURIComponent(authToken), '_blank');
    },

    contextDeleteOne: async function(path) {
        this.hideContextMenu();
        if (!confirm('确定删除 "' + path.split('/').pop() + '" 吗？（此操作不可恢复）')) return;
        var res = await this.api('/api/fb/' + this.currentKbId + '/local-files', 'DELETE', { paths: [path] });
        if (res.success) {
            this._categoryTree = null;
            this._treeLoaded = false;
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
        var h = '<div class="kb-modal-overlay" id="kb-modal-overlay"><div class="kb-modal">';
        h += '<h3>📦 移动到</h3>';
        h += '<p style="color:#666;font-size:12px">已选择 ' + items.length + ' 个项目</p>';
        h += '<div class="kb-move-tree" style="max-height:300px;overflow-y:auto;border:1px solid #e1e4e8;border-radius:4px;padding:8px;margin:8px 0">';
        h += '<div class="kb-tree-node"><div class="kb-tree-label active" onclick="KnowledgeBase._selectMoveDest(\'\', this)" data-dest="">📂 / (根目录)</div></div>';
        h += this._renderMoveTree(this._categoryTree, 0);
        h += '</div>';
        h += '<div style="color:#666;font-size:12px;margin:4px 0">目标: <span id="kb-move-dest-label">根目录</span></div>';
        h += '<div class="kb-modal-actions">';
        h += '<button class="btn" onclick="KnowledgeBase.doMove()">移动</button>';
        h += '<button class="kb-btn-cancel" onclick="KnowledgeBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        this._moveDest = '';
        document.getElementById('kb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'kb-modal-overlay') self.closeModal(); });
    },

    _renderMoveTree: function(nodes, depth) {
        var h = '';
        var ml = depth * 12 + 8;
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            var hasChildren = n.children && n.children.length > 0;
            h += '<div class="kb-tree-node">';
            h += '<div class="kb-tree-label" style="padding-left:' + ml + 'px" onclick="KnowledgeBase._selectMoveDest(\'' + (n.path || '').replace(/'/g, "\\'") + '\', this)" data-dest="' + (n.path || '') + '">📁 ' + escapeHtmlText(n.name) + '</div>';
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
        this._moveDest = dest;
        var labels = document.querySelectorAll('#kb-modal-overlay .kb-tree-label');
        for (var i = 0; i < labels.length; i++) labels[i].classList.remove('active');
        el.classList.add('active');
        var label = document.getElementById('kb-move-dest-label');
        if (label) label.textContent = dest || '根目录';
    },

    doMove: async function() {
        var items = this.getSelectedPaths();
        if (items.length === 0) return;
        var sources = [];
        for (var i = 0; i < items.length; i++) sources.push(items[i].path);
        var dest = this._moveDest || '';

        var res = await this.api('/api/fb/' + this.currentKbId + '/local-files/move', 'PUT', { sources: sources, dest: dest });
        this.closeModal();
        if (res.success) {
            if (res.errors && res.errors.length > 0) {
                alert('成功移动 ' + res.moved + ' 个，失败: ' + res.errors.join(', '));
            }
            this._categoryTree = null;
            this._treeLoaded = false;
            await this.renderDetail();
        } else {
            alert(res.message || '移动失败');
        }
    },

    dblClickFile: function(event) {
        var row = event.target.closest('.kb-file-row');
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
            window.open('/api/fb/' + this.currentKbId + '/local-files/open?path=' + encodeURIComponent(relPath) + '&token=' + encodeURIComponent(authToken), '_blank');
        }
    },
    
    openFilePreview: async function(relPath) {
        var self = this;
        var fileName = relPath.split('/').pop();
        
        var overlay = document.createElement('div');
        overlay.className = 'kb-docx-preview-overlay';
        overlay.innerHTML = 
            '<div class="kb-docx-preview-container">' +
            '<div class="kb-docx-preview-header">' +
            '<span>📄 ' + escapeHtmlText(fileName) + '</span>' +
            '<button onclick="KnowledgeBase._closeDocxPreview()">✖</button>' +
            '</div>' +
            '<div class="kb-docx-preview-content" id="kb-docx-preview-content">' +
            '<div style="text-align: center; padding: 40px; color: #999;">' +
            '<div style="font-size: 48px; margin-bottom: 12px;">📄</div>' +
            '<div>正在加载预览...</div>' +
            '</div>' +
            '</div>' +
            '</div>';
        document.body.appendChild(overlay);
        
        try {
            var res = await this.api('/api/fb/' + this.currentKbId + '/local-files/preview?path=' + encodeURIComponent(relPath), 'GET');
            var contentEl = document.getElementById('kb-docx-preview-content');
            if (res.success) {
                var html = (typeof marked !== 'undefined' && res.markdown)
                    ? marked.parse(res.markdown)
                    : (res.markdown || '<div style="text-align: center; padding: 40px; color: #999;">文件内容为空</div>');
                contentEl.innerHTML = html;
            } else {
                contentEl.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">预览失败: ' + (res.message || '未知错误') + '</div>';
            }
        } catch (e) {
            var contentEl = document.getElementById('kb-docx-preview-content');
            contentEl.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">预览失败: ' + e.message + '</div>';
        }
    },
    
    _closeDocxPreview: function() {
        var overlay = document.querySelector('.kb-docx-preview-overlay');
        if (overlay) {
            overlay.remove();
        }
    },
    
    openPdfPreview: function(relPath) {
        var fileName = relPath.split('/').pop();
        var fileUrl = '/api/fb/' + this.currentKbId + '/local-files/open?path=' + encodeURIComponent(relPath) + '&token=' + encodeURIComponent(authToken);
        
        var overlay = document.createElement('div');
        overlay.className = 'kb-docx-preview-overlay';
        overlay.innerHTML = 
            '<div class="kb-docx-preview-container">' +
            '<div class="kb-docx-preview-header">' +
            '<span>📄 ' + escapeHtmlText(fileName) + '</span>' +
            '<button onclick="KnowledgeBase._closeDocxPreview()">✖</button>' +
            '</div>' +
            '<div class="kb-docx-preview-content" style="padding:0">' +
            '<iframe src="' + fileUrl + '" style="width:100%;height:100%;min-height:500px;border:none;" title="' + escapeHtmlText(fileName) + '"></iframe>' +
            '</div>' +
            '</div>';
        document.body.appendChild(overlay);
    },
    
    openImagePreview: function(relPath) {
        var fileName = relPath.split('/').pop();
        var fileUrl = '/api/fb/' + this.currentKbId + '/local-files/open?path=' + encodeURIComponent(relPath) + '&token=' + encodeURIComponent(authToken);
        
        var overlay = document.createElement('div');
        overlay.className = 'kb-docx-preview-overlay';
        overlay.innerHTML = 
            '<div class="kb-docx-preview-container">' +
            '<div class="kb-docx-preview-header">' +
            '<span>🖼️ ' + escapeHtmlText(fileName) + '</span>' +
            '<button onclick="KnowledgeBase._closeDocxPreview()">✖</button>' +
            '</div>' +
            '<div class="kb-docx-preview-content" style="padding:16px;text-align:center;background:#f8f9fa;">' +
            '<img src="' + fileUrl + '" alt="' + escapeHtmlText(fileName) + '" style="max-width:100%;max-height:70vh;object-contain;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.1);">' +
            '</div>' +
            '</div>';
        document.body.appendChild(overlay);
    },

    openMarkdownEditor: async function(relPath) {
        var self = this;
        var res = await this.api('/api/fb/' + this.currentKbId + '/local-files/content?path=' + encodeURIComponent(relPath), 'GET');
        var content = res.success ? (res.content || '') : '';
        var fileName = relPath.split('/').pop();

        var overlay = document.createElement('div');
        overlay.className = 'kb-md-editor-overlay';
        overlay.id = 'kb-md-editor-overlay';
        overlay.innerHTML =
            '<div class="kb-md-editor-container">' +
            '<div class="kb-md-editor-header">' +
            '<span class="kb-md-editor-title">📝 ' + escapeHtmlText(fileName) + '</span>' +
            '<div class="kb-md-editor-actions">' +
            '<button class="kb-md-btn-save" onclick="KnowledgeBase._saveMdContent()">💾 保存</button>' +
            '<button class="kb-md-btn-close" onclick="KnowledgeBase._closeMdEditor()">✖ 关闭</button>' +
            '</div></div>' +
            '<div id="kb-wysiwyg-editor"></div>' +
            '</div>';
        document.body.appendChild(overlay);

        this._mdEditorRelPath = relPath;

        var editorEl = document.getElementById('kb-wysiwyg-editor');
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

            this._mdEditorInstance = quill;
        } else {
            editorEl.innerHTML = '<div style="padding:20px;color:#999;">编辑器加载失败，请刷新页面重试</div>';
        }

        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) self._closeMdEditor();
        });
    },

    _saveMdContent: async function() {
        var content = '';
        if (this._mdEditorInstance && typeof this._mdEditorInstance.root !== 'undefined') {
            var html = this._mdEditorInstance.root.innerHTML;
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

        var res = await this.api('/api/fb/' + this.currentKbId + '/local-files/content', 'PUT', {
            path: this._mdEditorRelPath,
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
        this._mdEditorInstance = null;
        this._mdEditorRelPath = null;
        var overlay = document.getElementById('kb-md-editor-overlay');
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
        var body = document.querySelector('.kb-explorer-body');
        if (!body) return;
        body.classList.toggle('collapsed');
        this._lsSet('kb_tree_collapsed', body.classList.contains('collapsed') ? '1' : '0');
    },

    initTreeResize: function() {
        var handle = document.getElementById('kb-tree-resize-handle');
        var pane = document.getElementById('kb-tree-pane');
        if (!handle || !pane) return;

        var saved = this._lsGet('kb_tree_width');
        if (saved) { pane.style.width = saved + 'px'; }

        var self = this;
        var startX, startW;

        handle.addEventListener('mousedown', function(e) {
            e.preventDefault();
            startX = e.clientX;
            startW = pane.offsetWidth;
            document.body.classList.add('kb-resizing');
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
                self._lsSet('kb_tree_width', pane.offsetWidth);
                startW = null;
                document.body.classList.remove('kb-resizing');
                handle.classList.remove('active');
            }
        });
    },

    _displayLocalPath: function() {
        return this.displayPath || this.localPath || '';
    },

    showSettings: async function() {
        var self = this;
        var res = await this.api('/api/fb/' + this.currentKbId + '/members', 'GET');
        var h = '<div class="kb-modal-overlay" id="kb-modal-overlay"><div class="kb-modal">';
        h += '<h3>⚙ 文件库设置</h3><h4>成员管理</h4>';
        if (res.success && res.members) {
            h += '<table class="kb-member-table"><thead><tr><th>用户名</th><th>权限</th><th>操作</th></tr></thead><tbody>';
            for (var i = 0; i < res.members.length; i++) {
                var m = res.members[i];
                h += '<tr><td>' + escapeHtmlText(m.username) + (m.is_owner ? ' (所有者)' : '') + '</td><td>';
                if (m.is_owner) { h += '管理'; }
                else {
                    h += '<select onchange="KnowledgeBase._updateMemberPerm(\'' + m.user_id + '\', this.value)">';
                    h += '<option value="view"' + (m.permission==='view'?' selected':'') + '>查看</option>';
                    h += '<option value="edit"' + (m.permission==='edit'?' selected':'') + '>编辑</option>';
                    h += '<option value="manage"' + (m.permission==='manage'?' selected':'') + '>管理</option>';
                    h += '</select>';
                }
                h += '</td><td>';
                if (!m.is_owner) h += '<button class="kb-btn-remove" onclick="KnowledgeBase._removeMemberAct(\'' + m.user_id + '\')">移除</button>';
                h += '</td></tr>';
            }
            h += '</tbody></table>';
        }
        h += '<div class="kb-add-member"><input type="text" id="kb-new-member" placeholder="用户名"><select id="kb-new-perm"><option value="view">查看</option><option value="edit">编辑</option><option value="manage">管理</option></select><button onclick="KnowledgeBase._addMemberAct()">添加</button></div>';
        h += '<hr style="margin:16px 0"><h4>批量设置用户权限</h4>';
        h += '<div style="display:flex;gap:8px;margin-bottom:8px">';
        h += '<select id="kb-batch-perm"><option value="view">查看</option><option value="edit">编辑</option><option value="manage">管理</option></select>';
        h += '<button onclick="KnowledgeBase._batchSetUsers()">应用到所选用户</button>';
        h += '<button onclick="KnowledgeBase._batchSetAllUsers()">应用到所有用户</button>';
        h += '</div>';
        h += '<div class="kb-batch-user-list" style="max-height:200px;overflow-y:auto;border:1px solid #e1e4e8;border-radius:4px;padding:8px">';
        var allUsers = JSON.parse(this._lsGet('kb_user_list') || '[]');
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
            h += '<input type="checkbox" class="kb-batch-user-chk" data-username="' + escapeHtmlText(u.username) + '"' + checked + '>';
            h += escapeHtmlText(u.username) + (curPerm ? ' <span style="color:#888;font-size:11px">(' + (curPerm === 'manage' ? '管理' : curPerm === 'edit' ? '编辑' : '查看') + ')</span>' : '');
            h += '</label>';
        }
        h += '</div>';
        h += '<hr style="margin:16px 0"><h4>转让所有权</h4>';
        h += '<div class="kb-add-member"><input type="text" id="kb-transfer-user" placeholder="新所有者用户名"><button onclick="KnowledgeBase._transferAct()">转让</button></div>';
        h += '<div class="kb-modal-actions"><button class="kb-btn-cancel" onclick="KnowledgeBase.closeModal()">关闭</button></div>';
        h += '</div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('kb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'kb-modal-overlay') self.closeModal(); });
    },

    closeModal: function() {
        var ov = document.getElementById('kb-modal-overlay');
        if (ov) ov.remove();
    },

    _updateMemberPerm: async function(uid, perm) {
        await this.api('/api/fb/' + this.currentKbId + '/members/' + uid, 'PUT', { permission: perm });
    },

    _removeMemberAct: async function(uid) {
        if (!confirm('确定要移除该成员吗？')) return;
        await this.api('/api/fb/' + this.currentKbId + '/members/' + uid, 'DELETE');
        var self = this; self.closeModal(); await self.showSettings();
    },

    _addMemberAct: async function() {
        var uname = document.getElementById('kb-new-member').value.trim();
        var perm = document.getElementById('kb-new-perm').value;
        if (!uname) return;
        var res = await this.api('/api/fb/' + this.currentKbId + '/members', 'POST', { username: uname, permission: perm });
        if (res.success) { var self = this; self.closeModal(); await self.showSettings(); }
        else alert(res.message);
    },

    _batchSetUsers: async function() {
        var perm = document.getElementById('kb-batch-perm').value;
        var chks = document.querySelectorAll('.kb-batch-user-chk:checked');
        var count = 0;
        for (var i = 0; i < chks.length; i++) {
            var uname = chks[i].getAttribute('data-username');
            try {
                await this.api('/api/fb/' + this.currentKbId + '/members', 'POST', { username: uname, permission: perm });
                count++;
            } catch (e) {}
        }
        this.closeModal();
        this.showSettings();
        if (count > 0) alert('已为 ' + count + ' 个用户设置权限');
    },

    _batchSetAllUsers: async function() {
        var chks = document.querySelectorAll('.kb-batch-user-chk');
        for (var i = 0; i < chks.length; i++) chks[i].checked = true;
        await this._batchSetUsers();
    },

    _transferAct: async function() {
        var uname = document.getElementById('kb-transfer-user').value.trim();
        if (!uname) return;
        if (!confirm('确定将文件库所有权转让给 ' + uname + ' 吗？')) return;
        var users = JSON.parse(this._lsGet('kb_user_list') || '[]');
        var tid = null;
        for (var i = 0; i < users.length; i++) {
            if (users[i].username === uname) { tid = users[i].user_id; break; }
        }
        if (!tid) { alert('用户不存在'); return; }
        var res = await this.api('/api/fb/' + this.currentKbId + '/transfer', 'POST', { new_owner_id: tid });
        if (res.success) { this.closeModal(); this.currentKbId = null; await this.renderKbList(); }
        else alert(res.message);
    },

    _deleteKbAct: async function() {
        if (!confirm('确定要删除此文件库吗？')) return;
        var res = await this.api('/api/fb/' + this.currentKbId, 'DELETE');
        if (res.success) { this.closeModal(); this.currentKbId = null; await this.renderKbList(); }
        else alert(res.message);
    },

    showUserManage: async function() {
        await this.refreshAuthRole();
        await this.refreshUserCache();
        var users = JSON.parse(this._lsGet('kb_user_list') || '[]');
        var h = '<div class="kb-modal-overlay" id="kb-modal-overlay"><div class="kb-modal">';
        h += '<h3>👥 用户管理</h3>';
        h += '<table class="kb-member-table"><thead><tr><th>用户名</th><th>全局角色</th></tr></thead><tbody>';
        for (var i = 0; i < users.length; i++) {
            var u = users[i];
            var isSelf = (u.user_id === window.authUserId);
            h += '<tr' + (isSelf ? ' style="background:#f0f8ff"' : '') + '><td>' + escapeHtmlText(u.username) + (isSelf ? ' <span style="color:#999;font-size:11px">(当前)</span>' : '') + '</td>';
            h += '<td><select' + (isSelf ? ' disabled' : '') + ' onchange="KnowledgeBase._updateUserRole(\'' + u.user_id + '\', this.value)">';
            h += '<option value="admin"' + (u.role==='admin'?' selected':'') + '>管理员</option>';
            h += '<option value="editor"' + (u.role==='editor'?' selected':'') + '>编辑者</option>';
            h += '<option value="viewer"' + (u.role==='viewer'?' selected':'') + '>阅读者</option>';
            h += '</select></td></tr>';
        }
        h += '</tbody></table>';
        h += '<p style="font-size:12px;color:#999;margin:6px 0 0">注：当前用户不可修改自身角色（防止误操作），可由其他管理员调整</p>';
        h += '<div class="kb-modal-actions"><button class="kb-btn-cancel" onclick="KnowledgeBase.closeModal()">关闭</button></div>';
        h += '</div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        var self = this;
        document.getElementById('kb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'kb-modal-overlay') self.closeModal(); });
    },

    _updateUserRole: async function(uid, role) {
        var res = await this.api('/api/users/' + uid + '/role', 'PUT', { role: role });
        if (res.success) await this.refreshUserCache();
        else alert(res.message);
    },

    search: async function() {
        var qEl = document.getElementById('kb-search-input');
        var q = qEl ? qEl.value.trim() : '';
        if (!q) return;

        var res = await this.api('/api/fb/search?q=' + encodeURIComponent(q), 'GET');
        var h = '<h3>🔍 搜索: ' + escapeHtmlText(q) + '</h3>';
        h += '<button onclick="KnowledgeBase.init()" style="margin-bottom:8px">← 返回</button>';
        if (res.success && res.results && res.results.length > 0) {
            h += '<table class="kb-file-table"><thead><tr><th>文件库</th><th>文件名</th><th>匹配</th><th>操作</th></tr></thead><tbody>';
            for (var i = 0; i < res.results.length; i++) {
                var r = res.results[i];
                if (!r.rel_path && !r.filebase_type) continue;
                var dirPath = r.rel_path ? r.rel_path.replace(/\\/g, '/').replace(/\/[^\/]+$/, '') : '';
                var clickAction = 'KnowledgeBase._openFromSearch(\'' + r.kb_id + '\',\'' + escapeHtmlText(r.kb_name) + '\',\'' + escapeHtmlText(dirPath) + '\')';
                var downloadUrl = '/api/fb/' + r.kb_id + '/local-files/download?path=' + encodeURIComponent(r.rel_path || r.document_id) + '&token=' + encodeURIComponent(authToken);
                h += '<tr>';
                h += '<td>' + escapeHtmlText(r.kb_name) + '</td>';
                h += '<td><span class="kb-file-name" onclick="' + clickAction + '">' + escapeHtmlText(r.filename) + '</span></td>';
                h += '<td>' + (r.match_type === 'filename' ? '文件名' : '内容') + '</td>';
                h += '<td><a href="' + downloadUrl + '" target="_blank">下载</a></td>';
                h += '</tr>';
            }
            h += '</tbody></table>';
        } else {
            h += '<div class="kb-empty">未找到匹配结果</div>';
        }
        document.getElementById('kb-view').innerHTML = h;
    },

    _openFromSearch: async function(kbId, kbName, subdir) {
        this.currentKbId = kbId;
        this.currentPermission = 'view';
        this.canEdit = false;
        this.canManage = false;
        this.selectedDocs = {};
        this.kbName = kbName;
        this.localPath = '';
        this.localCurrentSubdir = subdir || '';
        this.currentPath = [{ id: kbId, name: kbName, type: 'kb' }];
        if (subdir) {
            var parts = subdir.split('/');
            for (var i = 0; i < parts.length; i++) {
                this.currentPath.push({ id: parts[i], name: parts[i], type: 'category' });
            }
        }
        this.currentSort = { field: 'mtime', asc: false };

        this._lsSet('docproc_current_kb_id', kbId);
        this._lsSet('docproc_current_kb_permission', 'view');
        this._lsSet('docproc_current_kb_name', kbName);
        this._lsSet('docproc_current_kb_local_path', '');
        this._lsSet('docproc_current_kb_display_path', '');

        await this.renderDetail();
    },

    showTrash: async function() {
        var self = this;
        var res = await this.api('/api/fb/trash-list', 'GET');
        var items = res.success ? (res.items || []) : [];

        var h = '<div class="kb-explorer"><div class="kb-breadcrumb">';
        h += '<span class="kb-bc-home" onclick="KnowledgeBase.renderKbList()">📁 文件库首页</span>';
        h += '<span class="kb-bc-sep">›</span><span class="kb-bc-current">🗑️ 回收站</span>';
        h += '</div><div class="kb-explorer-body" style="flex-direction:column;border-radius:6px;border:1px solid #e1e4e8;background:#fff">';

        if (items.length === 0) {
            h += '<div class="kb-empty">回收站为空</div>';
        } else {
            h += '<div style="display:flex;padding:8px 12px;gap:8px;border-bottom:1px solid #e1e4e8;background:#fafbfc">';
            h += '<button onclick="KnowledgeBase.clearTrash()" class="kb-btn-danger" style="padding:6px 16px;border-radius:4px;cursor:pointer;font-size:13px">🧹 清空回收站</button>';
            h += '</div>';
            h += '<div style="padding:0;overflow-y:auto;flex:1">';
            for (var i = 0; i < items.length; i++) {
                var it = items[i];
                var escName = it.name.replace(/'/g, "\\'");
                h += '<div class="kb-trash-item" style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid #f0f0f0">';
                h += '<div><strong>🗑️ ' + escapeHtmlText(it.name) + '</strong><br><small style="color:#888">' + new Date(it.mtime * 1000).toLocaleString('zh-CN') + '</small></div>';
                h += '<div style="display:flex;gap:8px">';
                h += '<button onclick="KnowledgeBase.restoreTrashItem(\'' + escName + '\')" style="padding:5px 14px;border:1px solid #28a745;background:#fff;color:#28a745;border-radius:4px;cursor:pointer;font-size:12px">↩ 恢复</button>';
                h += '<button onclick="KnowledgeBase.deleteTrashItem(\'' + escName + '\')" class="kb-btn-remove" style="padding:5px 14px;border-radius:4px;cursor:pointer;font-size:12px">彻底删除</button>';
                h += '</div></div>';
            }
            h += '</div>';
        }

        h += '</div></div>';
        document.getElementById('kb-view').innerHTML = h;
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
        var cls = 'kb-file-icon-file kb-icon-other', label = '?';
        if (e === '.doc' || e === '.docx') { cls = 'kb-file-icon-file kb-icon-doc'; label = 'W'; }
        else if (e === '.xls' || e === '.xlsx') { cls = 'kb-file-icon-file kb-icon-xls'; label = 'X'; }
        else if (e === '.ppt' || e === '.pptx') { cls = 'kb-file-icon-file kb-icon-ppt'; label = 'P'; }
        else if (e === '.pdf') { cls = 'kb-file-icon-file kb-icon-pdf'; label = 'P'; }
        else if (e === '.md') { cls = 'kb-file-icon-file kb-icon-md'; label = 'M'; }
        else if (e === '.txt') { cls = 'kb-file-icon-file kb-icon-txt'; label = 'T'; }
        else if (e === '.html' || e === '.htm') { cls = 'kb-file-icon-file kb-icon-html'; label = 'H'; }
        else if (/^\.(jpe?g|png|gif|svg|bmp|webp|ico)$/i.test(e)) { cls = 'kb-file-icon-file kb-icon-img'; label = 'I'; }
        else if (/^\.(zip|rar|7z|tar|gz)$/i.test(e)) { cls = 'kb-file-icon-file kb-icon-zip'; label = 'Z'; }
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
