var KnowledgeBase = {

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

    api: function(url, method, body) {
        var o = {
            method: method || 'GET',
            headers: { 'Authorization': 'Bearer ' + (authToken || ''), 'Content-Type': 'application/json' }
        };
        if (body && method !== 'GET') o.body = JSON.stringify(body);
        return fetch(url, o).then(function(r) { return r.json(); }).catch(function() { return { success: false, message: '请求失败' }; });
    },

    refreshUserCache: async function() {
        try {
            var res = await this.api('/api/users/list', 'GET');
            if (res.success) localStorage.setItem('kb_user_list', JSON.stringify(res.users));
        } catch (e) {}
    },

    getUserRole: function() {
        var users = JSON.parse(localStorage.getItem('kb_user_list') || '[]');
        for (var i = 0; i < users.length; i++) {
            if (users[i].username === authUsername) return users[i].role;
        }
        return 'viewer';
    },

    init: async function() {
        this.selectedDocs = {};
        this.currentSort = { field: 'mtime', asc: false };
        await this.refreshUserCache();
        if (this.currentKbId) {
            await this.renderDetail();
        } else {
            await this.renderKbList();
        }
    },

    navigateTo: function(view) {
        if (typeof globalNavigateTo === 'function') { globalNavigateTo(view); return; }
        if (view === 'home') {
            document.getElementById('kb-view').style.display = 'none';
            document.getElementById('home-view').style.display = '';
            this.currentKbId = null;
        } else if (view === 'kb') {
            document.getElementById('home-view').style.display = 'none';
            document.getElementById('kb-view').style.display = '';
            this.init();
        }
    },

    renderKbList: async function() {
        this.currentKbId = null;
        this.localPath = '';
        this.currentPath = [{ id: null, name: '知识库', type: 'home' }];
        var role = this.getUserRole();

        var h = '<div class="kb-explorer">';
        h += '<div class="kb-breadcrumb"><span class="kb-bc-current">🏠 知识库</span></div>';
        h += '<div class="kb-explorer-body" style="border-radius:6px;border:1px solid #e1e4e8;background:#fff">';
        h += '<div class="kb-file-pane" style="width:100%">';
        h += '<div class="kb-file-toolbar">';
        h += '<input type="text" id="kb-search-input" placeholder="搜索文档..." onkeydown="if(event.keyCode===13) KnowledgeBase.search()">';
        h += '<button onclick="KnowledgeBase.search()">🔍 搜索</button>';
        if (role === 'admin') h += '<button onclick="KnowledgeBase.showUserManage()">👥 用户</button>';
        h += '<span class="kb-toolbar-spacer"></span>';
        h += '<button class="kb-btn-primary" onclick="KnowledgeBase.showCreateKb()">📁 新建知识库</button>';
        h += '</div>';
        h += '<div class="kb-file-body" id="kb-grid-container"><div class="kb-empty">加载中...</div></div>';
        h += '</div></div></div>';

        document.getElementById('kb-view').innerHTML = h;
        var res = await this.api('/api/kb/list', 'GET');
        var grid = document.getElementById('kb-grid-container');
        if (!grid) return;

        var kbs = [];
        if (res.success && res.kbs) {
            for (var i = 0; i < res.kbs.length; i++) {
                if (res.kbs[i].kb_type === 'local') kbs.push(res.kbs[i]);
            }
        }

        if (kbs.length === 0) {
            grid.innerHTML = '<div class="kb-empty">暂无知识库，点击上方按钮创建</div>';
            return;
        }

        var html = '<div class="kb-grid">';
        for (var i = 0; i < kbs.length; i++) {
            var kb = kbs[i];
            var cls = kb.permission === 'manage' ? 'kb-badge-manage' : (kb.permission === 'edit' ? 'kb-badge-edit' : 'kb-badge-view');
            var label = kb.permission === 'manage' ? '管理' : (kb.permission === 'edit' ? '编辑' : '查看');
            html += '<div class="kb-card" onclick="KnowledgeBase.openKb(\'' + kb.id + '\',\'' + kb.permission + '\',\'' + escapeHtmlText(kb.name) + '\',\'' + escapeHtmlText(kb.local_path || '') + '\')">';
            html += '<h3>📁 ' + escapeHtmlText(kb.name) + '</h3>';
            html += '<div class="kb-card-meta">' + (kb.local_path || '') + '</div>';
            html += '<span class="kb-badge ' + cls + '">' + label + '</span>';
            html += '</div>';
        }
        html += '</div>';
        grid.innerHTML = html;
    },

    openKb: async function(kbId, permission, name, localPath) {
        this.currentKbId = kbId;
        this.currentPermission = permission;
        this.canEdit = permission === 'edit' || permission === 'manage';
        this.canManage = permission === 'manage';
        this.selectedDocs = {};
        this.kbName = name || '';
        this.localPath = localPath || '';
        this.localCurrentSubdir = '';
        this.currentPath = [{ id: kbId, name: name || '未知知识库', type: 'kb' }];
        this.currentSort = { field: 'mtime', asc: false };
        this._categoryTree = null;
        this._treeLoaded = false;
        await this.renderDetail();
    },

    renderDetail: async function() {
        var self = this;

        var h = '<div class="kb-explorer">';
        h += '<div class="kb-breadcrumb" id="kb-breadcrumb"></div>';
        h += '<div class="kb-explorer-body">';
        h += '<div class="kb-tree-pane" id="kb-tree-pane"><button class="kb-tree-toggle-btn" onclick="KnowledgeBase.toggleTreePane()" title="折叠/展开">◀</button><div class="kb-tree-title">目录</div></div>';
        h += '<div class="kb-file-pane" id="kb-file-pane">';
        h += '<div class="kb-file-toolbar" id="kb-file-toolbar">';
        h += '<span style="color:#888;font-size:12px">📁 ' + escapeHtmlText(this.localPath || '') + '</span>';
        h += '<span class="kb-toolbar-spacer"></span>';
        h += '<input type="text" id="kb-search-input" placeholder="在当前知识库中搜索..." onkeydown="if(event.keyCode===13) KnowledgeBase.search()">';
        h += '<button onclick="KnowledgeBase.search()">🔍</button>';
        if (this.canManage) h += '<button onclick="KnowledgeBase.showSettings()">⚙ 设置</button>';
        h += '</div>';
        h += '<div class="kb-file-body" id="kb-file-body">';
        h += '<div id="kb-file-content"><div class="kb-empty">加载中...</div></div>';
        h += '</div></div></div></div>';

        document.getElementById('kb-view').innerHTML = h;
        this.renderBreadcrumb();

        if (!this._treeLoaded) {
            var res = await this.api('/api/kb/' + this.currentKbId + '/local-categories?recursive=1', 'GET');
            this._categoryTree = res.success ? (res.categories || []) : [];
            this._treeLoaded = true;
        }
        this.renderCategoryTree();
        await this.loadFiles();
    },

    renderBreadcrumb: function() {
        var el = document.getElementById('kb-breadcrumb');
        if (!el) return;
        var h = '<span class="kb-bc-home" onclick="KnowledgeBase.currentKbId=null;KnowledgeBase.renderKbList()">🏠 知识库</span>';
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
        await this.renderDetail();
    },

    renderCategoryTree: function() {
        var pane = document.getElementById('kb-tree-pane');
        if (!pane) return;

        var curPathNorm = (this.localCurrentSubdir || '').replace(/\\/g, '/');
        var pathParts = curPathNorm ? ('/' + curPathNorm).replace(/\/+/g, '/') : '/';

        var h = '<div class="kb-tree-title">目录</div>';
        h += '<div class="kb-tree-node">';
        h += '<div class="kb-tree-label' + (!curPathNorm ? ' active' : '') + '" onclick="KnowledgeBase.goToRoot()">📂 全部文件</div>';
        h += '</div>';

        h += this._renderTreeNodes(this._categoryTree, 0, pathParts);
        pane.innerHTML = h;
    },

    _renderTreeNodes: function(nodes, depth, activePath) {
        var h = '';
        var ml = depth * 12;
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            var hasChildren = n.children && n.children.length > 0;
            var nodePath = '/' + (n.path || '').replace(/\\/g, '/').replace(/\/+/g, '/');
            var isActive = activePath === nodePath;
            var h2 = '';
            if (hasChildren) {
                h2 = this._renderTreeNodes(n.children, depth + 1, activePath);
            }
            h += '<div class="kb-tree-node">';
            h += '<div class="kb-tree-label' + (isActive ? ' active' : '') + '" style="padding-left:' + (ml + 8) + 'px" onclick="KnowledgeBase.navigateSubdir(\'' + (n.path || '').replace(/'/g, "\\'") + '\')">';
            if (hasChildren) {
                h += '<span class="kb-tree-toggle" style="visibility:hidden">▶</span>';
            } else {
                h += '<span class="kb-tree-toggle" style="visibility:hidden">▶</span>';
            }
            h += '<span class="icon">📁</span>' + escapeHtmlText(n.name);
            h += '</div>';
            if (hasChildren) {
                h += '<div class="kb-tree-children" style="display:block">';
                h += h2;
                h += '</div>';
            }
            h += '</div>';
        }
        return h;
    },

    goToRoot: function() {
        this.localCurrentSubdir = '';
        this.currentSort = { field: 'mtime', asc: false };
        this.selectedDocs = {};
        this.renderDetail();
    },

    navigateSubdir: function(subdir) {
        this.localCurrentSubdir = subdir || '';
        this.currentSort = { field: 'mtime', asc: false };
        this.selectedDocs = {};
        this.currentPath = [{ id: this.currentKbId, name: this.kbName || '未知知识库', type: 'kb' }];
        if (subdir) {
            var parts = subdir.replace(/\\/g, '/').split('/');
            for (var i = 0; i < parts.length; i++) {
                this.currentPath.push({ id: parts[i], name: parts[i], type: 'category' });
            }
        }
        this.renderDetail();
    },

    loadFiles: async function() {
        var div = document.getElementById('kb-file-content');
        if (!div) return;
        var url = '/api/kb/' + this.currentKbId + '/local-files';
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
        h += '<th class="col-icon"></th>';
        h += '<th class="col-name" onclick="KnowledgeBase.setSort(\'name\')">名称<span class="sort-arrow">' + (sf === 'name' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-date" onclick="KnowledgeBase.setSort(\'mtime\')">修改时间<span class="sort-arrow">' + (sf === 'mtime' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-type" onclick="KnowledgeBase.setSort(\'ext\')">类型<span class="sort-arrow">' + (sf === 'ext' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-size" onclick="KnowledgeBase.setSort(\'size\')">大小<span class="sort-arrow">' + (sf === 'size' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-actions">操作</th></tr></thead><tbody>';

        for (var i = 0; i < categories.length; i++) {
            var cat = categories[i];
            h += '<tr class="kb-file-row kb-local-dir" onclick="KnowledgeBase.navigateSubdir(\'' + cat.path.replace(/'/g, "\\'") + '\')" style="cursor:pointer">';
            h += '<td class="col-icon"><span class="kb-file-icon">📁</span></td>';
            h += '<td class="col-name"><div class="kb-file-name">' + escapeHtmlText(cat.name) + '</div></td>';
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

            h += '<tr class="kb-file-row" data-local-path="' + escPath + '" data-doc-name="' + fname + '">';
            h += '<td class="col-icon"><span class="kb-file-icon">' + icon + '</span></td>';
            h += '<td class="col-name"><div class="kb-file-name" ondblclick="KnowledgeBase.dblClickFile(event)" onclick="event.stopPropagation()">' + fname + '<span class="kb-file-type-tag">' + ext + '</span></div></td>';
            h += '<td class="col-date"><span class="kb-file-date">' + date + '</span></td>';
            h += '<td class="col-type">' + ext + '</td>';
            h += '<td class="col-size"><span class="kb-file-size">' + size + '</span></td>';
            h += '<td class="col-actions"><span class="kb-file-actions">';
            h += '<a href="' + url.replace('local-files', 'local-files/download') + '&path=' + encodeURIComponent(f.path) + '&token=' + encodeURIComponent(authToken) + '" onclick="event.stopPropagation()">下载</a>';
            h += '<a href="#" onclick="KnowledgeBase.openFile(\'' + escPath + '\');return false">打开</a>';
            h += '</span></td></tr>';
        }
        h += '</tbody></table>';
        div.innerHTML = h;
    },

    dblClickFile: function(event) {
        var row = event.target.closest('.kb-file-row');
        if (!row) return;
        var path = row.getAttribute('data-local-path');
        if (path) this.openFile(path);
    },

    openFile: function(relPath) {
        this.api('/api/kb/' + this.currentKbId + '/local-files/open?path=' + encodeURIComponent(relPath), 'GET');
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
        var pane = document.getElementById('kb-tree-pane');
        if (!pane) return;
        var btn = pane.querySelector('.kb-tree-toggle-btn');
        if (pane.classList.contains('collapsed')) {
            pane.classList.remove('collapsed');
            if (btn) btn.textContent = '◀';
        } else {
            pane.classList.add('collapsed');
            if (btn) btn.textContent = '▶';
        }
    },

    showCreateKb: async function() {
        var self = this;
        var h = '<div class="kb-modal-overlay" id="kb-modal-overlay"><div class="kb-modal">';
        h += '<h3>📁 新建知识库</h3>';
        h += '<div class="form-group"><label>知识库名称</label><input type="text" id="kb-local-name" placeholder="输入名称"></div>';
        h += '<div class="form-group"><label>本地目录路径（绝对路径）</label>';
        h += '<div style="display:flex;gap:8px"><input type="text" id="kb-local-path" placeholder="例如: D:\\文档库" style="flex:1">';
        h += '<button class="btn" onclick="KnowledgeBase._pickFolder()" style="width:auto;padding:8px 12px">选择...</button></div></div>';
        h += '<div class="kb-modal-actions">';
        h += '<button class="btn" onclick="KnowledgeBase._createAct()">创建</button>';
        h += '<button class="kb-btn-cancel" onclick="KnowledgeBase.closeModal()">取消</button>';
        h += '</div></div></div>';
        document.body.insertAdjacentHTML('beforeend', h);
        document.getElementById('kb-modal-overlay').addEventListener('click', function(e) { if (e.target.id === 'kb-modal-overlay') self.closeModal(); });
    },

    _pickFolder: async function() {
        var res = await this.api('/select_folder', 'POST');
        if (res.success && res.path) {
            document.getElementById('kb-local-path').value = res.path;
        }
    },

    _createAct: async function() {
        var name = document.getElementById('kb-local-name').value.trim();
        var localPath = document.getElementById('kb-local-path').value.trim();
        if (!name) { alert('请输入知识库名称'); return; }
        if (!localPath) { alert('请指定本地目录路径'); return; }
        var res = await this.api('/api/kb/list', 'POST', { name: name, kb_type: 'local', local_path: localPath });
        if (res.success) { this.closeModal(); await this.renderKbList(); }
        else alert(res.message || '创建失败');
    },

    showSettings: async function() {
        var self = this;
        var res = await this.api('/api/kb/' + this.currentKbId + '/members', 'GET');
        var h = '<div class="kb-modal-overlay" id="kb-modal-overlay"><div class="kb-modal">';
        h += '<h3>⚙ 知识库设置</h3><h4>成员管理</h4>';
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
        h += '<hr style="margin:16px 0"><h4>转让所有权</h4>';
        h += '<div class="kb-add-member"><input type="text" id="kb-transfer-user" placeholder="新所有者用户名"><button onclick="KnowledgeBase._transferAct()">转让</button></div>';
        h += '<hr style="margin:16px 0"><button class="kb-btn-danger" onclick="KnowledgeBase._deleteKbAct()">删除知识库</button>';
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
        await this.api('/api/kb/' + this.currentKbId + '/members/' + uid, 'PUT', { permission: perm });
    },

    _removeMemberAct: async function(uid) {
        if (!confirm('确定要移除该成员吗？')) return;
        await this.api('/api/kb/' + this.currentKbId + '/members/' + uid, 'DELETE');
        var self = this; self.closeModal(); await self.showSettings();
    },

    _addMemberAct: async function() {
        var uname = document.getElementById('kb-new-member').value.trim();
        var perm = document.getElementById('kb-new-perm').value;
        if (!uname) return;
        var res = await this.api('/api/kb/' + this.currentKbId + '/members', 'POST', { username: uname, permission: perm });
        if (res.success) { var self = this; self.closeModal(); await self.showSettings(); }
        else alert(res.message);
    },

    _transferAct: async function() {
        var uname = document.getElementById('kb-transfer-user').value.trim();
        if (!uname) return;
        if (!confirm('确定将知识库所有权转让给 ' + uname + ' 吗？')) return;
        var users = JSON.parse(localStorage.getItem('kb_user_list') || '[]');
        var tid = null;
        for (var i = 0; i < users.length; i++) {
            if (users[i].username === uname) { tid = users[i].user_id; break; }
        }
        if (!tid) { alert('用户不存在'); return; }
        var res = await this.api('/api/kb/' + this.currentKbId + '/transfer', 'POST', { new_owner_id: tid });
        if (res.success) { this.closeModal(); this.currentKbId = null; await this.renderKbList(); }
        else alert(res.message);
    },

    _deleteKbAct: async function() {
        if (!confirm('确定要删除此知识库吗？（不会删除本地文件）')) return;
        var res = await this.api('/api/kb/' + this.currentKbId, 'DELETE');
        if (res.success) { this.closeModal(); this.currentKbId = null; await this.renderKbList(); }
        else alert(res.message);
    },

    showUserManage: async function() {
        await this.refreshUserCache();
        var users = JSON.parse(localStorage.getItem('kb_user_list') || '[]');
        var h = '<div class="kb-modal-overlay" id="kb-modal-overlay"><div class="kb-modal">';
        h += '<h3>👥 用户管理</h3>';
        h += '<table class="kb-member-table"><thead><tr><th>用户名</th><th>全局角色</th></tr></thead><tbody>';
        for (var i = 0; i < users.length; i++) {
            var u = users[i];
            h += '<tr><td>' + escapeHtmlText(u.username) + '</td>';
            h += '<td><select onchange="KnowledgeBase._updateUserRole(\'' + u.user_id + '\', this.value)">';
            h += '<option value="admin"' + (u.role==='admin'?' selected':'') + '>管理员</option>';
            h += '<option value="editor"' + (u.role==='editor'?' selected':'') + '>编辑者</option>';
            h += '<option value="viewer"' + (u.role==='viewer'?' selected':'') + '>阅读者</option>';
            h += '</select></td></tr>';
        }
        h += '</tbody></table>';
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

        var res = await this.api('/api/kb/search?q=' + encodeURIComponent(q), 'GET');
        var h = '<h3>🔍 搜索: ' + escapeHtmlText(q) + '</h3>';
        h += '<button onclick="KnowledgeBase.init()" style="margin-bottom:8px">← 返回</button>';
        if (res.success && res.results && res.results.length > 0) {
            h += '<table class="kb-file-table"><thead><tr><th>知识库</th><th>文件名</th><th>匹配</th><th>操作</th></tr></thead><tbody>';
            for (var i = 0; i < res.results.length; i++) {
                var r = res.results[i];
                if (!r.rel_path && !r.kb_type) continue;
                var dirPath = r.rel_path ? r.rel_path.replace(/\\/g, '/').replace(/\/[^\/]+$/, '') : '';
                var clickAction = 'KnowledgeBase._openFromSearch(\'' + r.kb_id + '\',\'' + escapeHtmlText(r.kb_name) + '\',\'' + escapeHtmlText(dirPath) + '\')';
                var downloadUrl = '/api/kb/' + r.kb_id + '/local-files/download?path=' + encodeURIComponent(r.rel_path || r.document_id) + '&token=' + encodeURIComponent(authToken);
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
        await this.renderDetail();
    },

    getFileIcon: function(ext) {
        var e = (ext || '').toLowerCase();
        if (e === '.docx' || e === '.doc') return '📄';
        if (e === '.xlsx' || e === '.xls') return '📊';
        if (e === '.pptx' || e === '.ppt') return '📽️';
        if (e === '.pdf') return '📕';
        if (e === '.md') return '📝';
        if (e === '.txt') return '📃';
        if (e === '.html' || e === '.htm') return '🌐';
        return '📎';
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
