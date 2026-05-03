var KnowledgeBase = {

    currentKbId: null,
    currentPermission: null,
    currentCategory: null,
    currentDocId: null,
    currentDocName: null,
    selectedDocs: {},
    _mde: null,
    _modalOverlay: null,
    _contextMenu: null,
    _lastClickedDoc: null,
    currentSort: { field: 'updated_at', asc: false },
    currentPath: [],
    categoryTreeData: [],
    kbName: '',
    canEdit: false,
    canManage: false,

    api: function(url, method, body) {
        var o = {
            method: method || 'GET',
            headers: { 'Authorization': 'Bearer ' + (authToken || ''), 'Content-Type': 'application/json' }
        };
        if (body && method !== 'GET') o.body = JSON.stringify(body);
        return fetch(url, o).then(function(r) { return r.json(); }).catch(function() { return { success: false, message: '请求失败' }; });
    },

    uploadApi: function(url, formData) {
        return fetch(url, { method: 'POST', headers: { 'Authorization': 'Bearer ' + (authToken || '') }, body: formData })
            .then(function(r) { return r.json(); }).catch(function() { return { success: false, message: '请求失败' }; });
    },

    putUploadApi: function(url, formData) {
        return fetch(url, { method: 'PUT', headers: { 'Authorization': 'Bearer ' + (authToken || '') }, body: formData })
            .then(function(r) { return r.json(); }).catch(function() { return { success: false, message: '请求失败' }; });
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
        this._lastClickedDoc = null;
        this.currentSort = { field: 'updated_at', asc: false };
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
        this.currentPath = [{ id: null, name: '知识库', type: 'home' }];
        var role = this.getUserRole();

        var h = '<div class="kb-explorer">';
        h += '<div class="kb-breadcrumb"><span class="kb-bc-current">🏠 知识库</span></div>';
        h += '<div class="kb-explorer-body">';
        h += '<div class="kb-tree-pane"><div class="kb-tree-title">知识库列表</div></div>';
        h += '<div class="kb-file-pane">';
        h += '<div class="kb-file-toolbar">';
        h += '<input type="text" id="kb-search-input" placeholder="搜索文档..." onkeydown="if(event.keyCode===13) KnowledgeBase.search()">';
        h += '<button onclick="KnowledgeBase.search()">🔍 搜索</button>';
        if (role === 'admin') h += '<button onclick="KnowledgeBase.showUserManage()">👥 用户</button>';
        h += '<span class="kb-toolbar-spacer"></span>';
        h += '<button class="kb-btn-primary" onclick="KnowledgeBase.showCreateKb()">+ 新建知识库</button>';
        h += '</div>';
        h += '<div class="kb-file-body" id="kb-grid-container"><div class="kb-empty">加载中...</div></div>';
        h += '</div></div></div>';

        document.getElementById('kb-view').innerHTML = h;
        var res = await this.api('/api/kb/list', 'GET');
        var grid = document.getElementById('kb-grid-container');
        if (!grid) return;

        if (!res.success || !res.kbs || res.kbs.length === 0) {
            grid.innerHTML = '<div class="kb-empty">暂无知识库，点击上方按钮创建</div>';
            return;
        }

        var html = '<div class="kb-grid">';
        for (var i = 0; i < res.kbs.length; i++) {
            var kb = res.kbs[i];
            var cls = kb.permission === 'manage' ? 'kb-badge-manage' : (kb.permission === 'edit' ? 'kb-badge-edit' : 'kb-badge-view');
            var label = kb.permission === 'manage' ? '管理' : (kb.permission === 'edit' ? '编辑' : '查看');
            html += '<div class="kb-card" onclick="KnowledgeBase.openKb(\'' + kb.id + '\',\'' + kb.permission + '\',\'' + escapeHtmlText(kb.name) + '\')">';
            html += '<h3>📚 ' + escapeHtmlText(kb.name) + '</h3>';
            html += '<div class="kb-card-meta">' + kb.document_count + ' 个文档</div>';
            html += '<span class="kb-badge ' + cls + '">' + label + '</span>';
            html += '</div>';
        }
        html += '</div>';
        grid.innerHTML = html;
    },

    openKb: async function(kbId, permission, name) {
        this.currentKbId = kbId;
        this.currentPermission = permission;
        this.canEdit = permission === 'edit' || permission === 'manage';
        this.canManage = permission === 'manage';
        this.currentCategory = null;
        this.selectedDocs = {};
        this.kbName = name || '';
        this.currentPath = [{ id: kbId, name: name || '未知知识库', type: 'kb' }];
        this.currentSort = { field: 'updated_at', asc: false };
        await this.renderDetail();
    },

    renderDetail: async function() {
        var self = this;

        var h = '<div class="kb-explorer">';
        h += '<div class="kb-breadcrumb" id="kb-breadcrumb"></div>';
        h += '<div class="kb-explorer-body">';
        h += '<div class="kb-tree-pane" id="kb-tree-pane"><div class="kb-tree-title">目录</div></div>';
        h += '<div class="kb-file-pane" id="kb-file-pane">';
        h += '<div class="kb-file-toolbar" id="kb-file-toolbar">';
        if (this.canEdit) {
            h += '<button onclick="document.getElementById(\'kb-upload-input\').click()">📤 上传</button>';
            h += '<button onclick="KnowledgeBase.createMarkdown()">📝 新建MD</button>';
            h += '<button onclick="KnowledgeBase.showCreateCategory()">📂 新建文件夹</button>';
            h += '<input type="file" id="kb-upload-input" style="display:none" onchange="KnowledgeBase.handleUpload(this)">';
            h += '<input type="file" id="kb-replace-input" style="display:none" onchange="KnowledgeBase.handleReplace(this)">';
        }
        h += '<input type="text" id="kb-search-input" placeholder="在当前知识库中搜索..." onkeydown="if(event.keyCode===13) KnowledgeBase.search()">';
        h += '<button onclick="KnowledgeBase.search()">🔍</button>';
        h += '<span class="kb-toolbar-spacer"></span>';
        if (this.canEdit) {
            h += '<button onclick="KnowledgeBase.deleteSelected()">🗑 删除选中</button>';
        }
        if (this.canManage) h += '<button onclick="KnowledgeBase.showSettings()">⚙ 设置</button>';
        h += '</div>';
        h += '<div class="kb-file-body" id="kb-file-body">';
        h += '<div class="kb-upload-drop" id="kb-upload-drop">📁 拖拽文件到此处上传</div>';
        h += '<div id="kb-file-content"><div class="kb-empty">加载中...</div></div>';
        h += '</div></div></div></div>';

        document.getElementById('kb-view').innerHTML = h;
        this.renderBreadcrumb();

        setTimeout(async function() {
            await self.loadCategories();
            await self.loadDocuments();
            self.setupDragDrop();
            self.setupContextMenu();
        }, 50);
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
        var last = this.currentPath[this.currentPath.length - 1];
        if (last.type === 'category') {
            this.currentCategory = last.id;
        } else {
            this.currentCategory = null;
        }
        await this.renderDetail();
    },

    loadCategories: async function() {
        var self = this;
        var pane = document.getElementById('kb-tree-pane');
        if (!pane) return;
        var res = await this.api('/api/kb/' + this.currentKbId + '/categories', 'GET');

        this.categoryTreeData = res.success ? res.categories : [];

        var h = '<div class="kb-tree-title">目录</div>';
        h += '<div class="kb-tree-node">';
        h += '<div class="kb-tree-label' + (!this.currentCategory ? ' active' : '') + '" onclick="KnowledgeBase.goToRoot()">📂 全部文件</div>';
        h += '</div>';
        if (this.categoryTreeData.length > 0) {
            h += this.renderTreeNodes(this.categoryTreeData, 0);
        }
        h += '<div style="padding:12px 10px"><button onclick="KnowledgeBase.currentKbId=null;KnowledgeBase.renderKbList()">📚 所有知识库</button></div>';
        pane.innerHTML = h;
    },

    renderTreeNodes: function(nodes, depth) {
        var h = '';
        var ml = depth * 12;
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            var hasChildren = n.children && n.children.length > 0;
            var isActive = this.currentCategory === n.id;
            h += '<div class="kb-tree-node">';
            h += '<div class="kb-tree-label' + (isActive ? ' active' : '') + '" style="padding-left:' + (ml + 8) + 'px" onclick="KnowledgeBase.filterByCategory(\'' + n.id + '\',\'' + escapeHtmlText(n.name) + '\')">';
            if (hasChildren) {
                h += '<span class="kb-tree-toggle" onclick="event.stopPropagation();KnowledgeBase.toggleTreeNode(this)">▶</span>';
            } else {
                h += '<span class="kb-tree-toggle" style="visibility:hidden">▶</span>';
            }
            h += '<span class="icon">📁</span>' + escapeHtmlText(n.name);
            h += '</div>';
            if (hasChildren) {
                h += '<div class="kb-tree-children" style="display:block">';
                h += this.renderTreeNodes(n.children, depth + 1);
                h += '</div>';
            }
            h += '</div>';
        }
        return h;
    },

    toggleTreeNode: function(el) {
        var node = el.closest('.kb-tree-node');
        var children = node.querySelector('.kb-tree-children');
        if (children) {
            if (children.classList.contains('open') || children.style.display === 'block') {
                children.classList.remove('open');
                children.style.display = 'none';
                el.textContent = '▶';
            } else {
                children.classList.add('open');
                children.style.display = 'block';
                el.textContent = '▼';
            }
        }
    },

    goToRoot: async function() {
        this.currentCategory = null;
        this.currentPath = [{ id: this.currentKbId, name: this.kbName || '未知知识库', type: 'kb' }];
        this.currentSort = { field: 'updated_at', asc: false };
        await this.renderDetail();
    },

    filterByCategory: async function(catId, catName) {
        this.currentCategory = catId;
        this.currentSort = { field: 'updated_at', asc: false };
        var existing = -1;
        for (var i = 0; i < this.currentPath.length; i++) {
            if (this.currentPath[i].id === catId) { existing = i; break; }
        }
        if (existing >= 0) {
            this.currentPath = this.currentPath.slice(0, existing + 1);
        } else {
            this.currentPath.push({ id: catId, name: catName, type: 'category' });
        }
        this.selectedDocs = {};
        await this.renderDetail();
    },

    loadDocuments: async function() {
        var div = document.getElementById('kb-file-content');
        if (!div) return;
        var url = '/api/kb/' + this.currentKbId + '/documents';
        if (this.currentCategory) url += '?category_id=' + this.currentCategory;
        var res = await this.api(url, 'GET');

        if (!res.success || !res.documents || res.documents.length === 0) {
            div.innerHTML = '<div class="kb-empty">此目录为空</div>';
            return;
        }

        var docs = res.documents;
        var sf = this.currentSort.field;
        var sa = this.currentSort.asc;
        docs.sort(function(a, b) {
            var va = a[sf], vb = b[sf];
            if (sf === 'original_name') {
                va = (va || '').toLowerCase(); vb = (vb || '').toLowerCase();
                return sa ? va.localeCompare(vb) : vb.localeCompare(va);
            }
            if (va < vb) return sa ? -1 : 1;
            if (va > vb) return sa ? 1 : -1;
            return 0;
        });

        var self = this;
        var h = '<table class="kb-file-table"><thead><tr>';
        h += '<th class="col-cb"><input type="checkbox" onchange="KnowledgeBase.toggleAll(this)"></th>';
        h += '<th class="col-icon"></th>';
        h += '<th class="col-name" onclick="KnowledgeBase.setSort(\'original_name\')">名称<span class="sort-arrow">' + (sf === 'original_name' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-date" onclick="KnowledgeBase.setSort(\'updated_at\')">修改时间<span class="sort-arrow">' + (sf === 'updated_at' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-type" onclick="KnowledgeBase.setSort(\'file_type\')">类型<span class="sort-arrow">' + (sf === 'file_type' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-size" onclick="KnowledgeBase.setSort(\'file_size\')">大小<span class="sort-arrow">' + (sf === 'file_size' ? (sa ? '▲' : '▼') : '') + '</span></th>';
        h += '<th class="col-actions">操作</th></tr></thead><tbody>';

        for (var i = 0; i < docs.length; i++) {
            var d = docs[i];
            var icon = self.getFileIcon(d.file_type || '');
            var ext = (d.file_type || '').replace('.', '').toUpperCase();
            var size = self.formatSize(d.file_size);
            var date = self.formatDate(d.updated_at);
            var sel = self.selectedDocs[d.id] ? ' selected' : '';
            var chk = self.selectedDocs[d.id] ? ' checked' : '';
            var fname = escapeHtmlText(d.filename);
            var escName = fname.replace(/'/g, "\\'").replace(/"/g, '&quot;');

            h += '<tr class="kb-file-row' + sel + '" data-doc-id="' + d.id + '" data-doc-type="' + (d.file_type || '') + '" data-doc-name="' + fname + '">';
            h += '<td class="col-cb"><input type="checkbox" class="kb-doc-checkbox"' + chk + ' onchange="KnowledgeBase.toggleDoc(\'' + d.id + '\', this)"></td>';
            h += '<td class="col-icon"><span class="kb-file-icon">' + icon + '</span></td>';
            h += '<td class="col-name"><div class="kb-file-name" ondblclick="KnowledgeBase.dblClickDoc(\'' + d.id + '\',\'' + (d.file_type || '') + '\',\'' + escName + '\')" onclick="KnowledgeBase.clickDoc(\'' + d.id + '\', event)">' + fname + '<span class="kb-file-type-tag">' + ext + '</span></div></td>';
            h += '<td class="col-date"><span class="kb-file-date">' + date + '</span></td>';
            h += '<td class="col-type">' + ext + '</td>';
            h += '<td class="col-size"><span class="kb-file-size">' + size + '</span></td>';
            h += '<td class="col-actions"><span class="kb-file-actions">';
            h += '<a href="#download" onclick="KnowledgeBase.downloadDoc(\'' + d.id + '\');return false">下载</a>';
            if (self.canEdit) h += '<a href="#replace" onclick="KnowledgeBase.triggerReplace(\'' + d.id + '\');return false">替换</a>';
            h += '</span></td></tr>';
        }
        h += '</tbody></table>';
        div.innerHTML = h;
    },

    setSort: async function(field) {
        if (this.currentSort.field === field) {
            this.currentSort.asc = !this.currentSort.asc;
        } else {
            this.currentSort.field = field;
            this.currentSort.asc = false;
        }
        await this.loadDocuments();
    },

    clickDoc: function(docId, event) {
        if (event.shiftKey && this._lastClickedDoc) {
            var rows = document.querySelectorAll('.kb-file-row');
            var start = -1, end = -1;
            for (var i = 0; i < rows.length; i++) {
                if (rows[i].getAttribute('data-doc-id') === this._lastClickedDoc) start = i;
                if (rows[i].getAttribute('data-doc-id') === docId) end = i;
            }
            if (start >= 0 && end >= 0) {
                var lo = Math.min(start, end), hi = Math.max(start, end);
                for (var j = lo; j <= hi; j++) {
                    var rid = rows[j].getAttribute('data-doc-id');
                    this.selectedDocs[rid] = true;
                    rows[j].classList.add('selected');
                    var cb = rows[j].querySelector('.kb-doc-checkbox');
                    if (cb) cb.checked = true;
                }
                return;
            }
        }
        if (event.ctrlKey || event.metaKey) {
            if (this.selectedDocs[docId]) {
                delete this.selectedDocs[docId];
            } else {
                this.selectedDocs[docId] = true;
            }
        } else {
            this.selectedDocs = {};
            this.selectedDocs[docId] = true;
        }
        this._lastClickedDoc = docId;
        this.refreshRowSelection();
    },

    dblClickDoc: function(docId, fileType, filename) {
        var ext = (fileType || '').toLowerCase();
        if (ext === '.md' && this.canEdit) this.openEditor(docId, filename);
        else if (ext === '.pdf') this.previewPdf(docId);
        else if (ext === '.md' || ext === '.txt' || ext === '.html' || ext === '.htm') this.previewText(docId, ext);
        else this.downloadDoc(docId);
    },

    refreshRowSelection: function() {
        var rows = document.querySelectorAll('.kb-file-row');
        for (var i = 0; i < rows.length; i++) {
            var rid = rows[i].getAttribute('data-doc-id');
            var cb = rows[i].querySelector('.kb-doc-checkbox');
            if (this.selectedDocs[rid]) {
                rows[i].classList.add('selected');
                if (cb) cb.checked = true;
            } else {
                rows[i].classList.remove('selected');
                if (cb) cb.checked = false;
            }
        }
    },

    toggleDoc: function(docId, cb) {
        if (cb.checked) { this.selectedDocs[docId] = true; }
        else { delete this.selectedDocs[docId]; }
        this._lastClickedDoc = docId;
        this.refreshRowSelection();
    },

    toggleAll: function(cb) {
        this.selectedDocs = {};
        if (cb.checked) {
            var rows = document.querySelectorAll('.kb-file-row');
            for (var i = 0; i < rows.length; i++) {
                this.selectedDocs[rows[i].getAttribute('data-doc-id')] = true;
            }
        }
        this.refreshRowSelection();
    },

    downloadDoc: function(docId) {
        window.open('/api/kb/' + this.currentKbId + '/documents/' + docId + '/download?token=' + encodeURIComponent(authToken), '_blank');
    },

    deleteDoc: async function(docId) {
        if (!confirm('确定要删除此文档吗？')) return;
        await this.api('/api/kb/' + this.currentKbId + '/documents/' + docId, 'DELETE');
        delete this.selectedDocs[docId];
        await this.loadDocuments();
    },

    deleteSelected: async function() {
        var ids = Object.keys(this.selectedDocs);
        if (ids.length === 0) { alert('请先选择文档'); return; }
        if (!confirm('确定要删除选中的 ' + ids.length + ' 个文档吗？')) return;
        for (var i = 0; i < ids.length; i++) {
            await this.api('/api/kb/' + this.currentKbId + '/documents/' + ids[i], 'DELETE');
        }
        this.selectedDocs = {};
        await this.loadDocuments();
    },

    handleUpload: async function(input) {
        if (!input.files || input.files.length === 0) return;
        var fd = new FormData();
        fd.append('file', input.files[0]);
        if (this.currentCategory) fd.append('category_id', this.currentCategory);
        var res = await this.uploadApi('/api/kb/' + this.currentKbId + '/documents', fd);
        input.value = '';
        if (res.success) await this.loadDocuments();
        else alert(res.message || '上传失败');
    },

    triggerReplace: function(docId) {
        this._replaceDocId = docId;
        document.getElementById('kb-replace-input').click();
    },

    handleReplace: async function(input) {
        if (!this._replaceDocId || !input.files || input.files.length === 0) return;
        var fd = new FormData();
        fd.append('file', input.files[0]);
        var res = await this.putUploadApi('/api/kb/' + this.currentKbId + '/documents/' + this._replaceDocId + '/replace', fd);
        this._replaceDocId = null;
        input.value = '';
        if (res.success) await this.loadDocuments();
        else alert(res.message || '替换失败');
    },

    createMarkdown: function() {
        var name = prompt('请输入文件名（不含扩展名）:');
        if (!name) return;
        if (!name.endsWith('.md')) name += '.md';
        this._createEmptyFile(name, '');
    },

    showCreateCategory: async function() {
        var name = prompt('请输入文件夹名称:');
        if (!name) return;
        var res = await this.api('/api/kb/' + this.currentKbId + '/categories', 'POST',
            { name: name, parent_id: this.currentCategory || '' });
        if (res.success) await this.loadCategories();
        else alert(res.message);
    },

    _createEmptyFile: async function(filename, content) {
        var fd = new FormData();
        var blob = new Blob([content || ''], { type: 'text/plain' });
        fd.append('file', blob, filename);
        if (this.currentCategory) fd.append('category_id', this.currentCategory);
        var res = await this.uploadApi('/api/kb/' + this.currentKbId + '/documents', fd);
        if (res.success) {
            await this.loadDocuments();
            if (filename.endsWith('.md')) this.openEditor(res.document.id, filename);
        }
    },

    openEditor: function(docId, filename) {
        this.currentDocId = docId;
        this.currentDocName = filename || 'Untitled.md';
        this.renderEditor();
    },

    renderEditor: async function() {
        var self = this;
        var h = '<div class="kb-editor-toolbar">';
        h += '<button class="kb-btn-cancel" onclick="KnowledgeBase.renderDetail()">← 返回</button>';
        h += '<input type="text" id="kb-editor-filename" value="' + escapeHtmlText(this.currentDocName || '') + '">';
        h += '<button onclick="KnowledgeBase.saveEditor()">💾 保存 (Ctrl+S)</button>';
        h += '<span class="kb-editor-status" id="kb-editor-status"></span>';
        h += '</div>';
        h += '<div class="kb-editor-body"><textarea id="kb-editor-textarea"></textarea></div>';

        document.getElementById('kb-view').innerHTML = h;

        var res = await this.api('/api/kb/' + this.currentKbId + '/documents/' + this.currentDocId + '/content', 'GET');
        var content = res.success ? res.content : '';

        setTimeout(function() {
            var ta = document.getElementById('kb-editor-textarea');
            if (!ta) return;
            if (typeof EasyMDE !== 'undefined') {
                self._mde = new EasyMDE({
                    element: ta,
                    spellChecker: false,
                    autosave: { enabled: false },
                    placeholder: '在此编辑 Markdown...',
                    initialValue: content,
                    toolbar: ['bold', 'italic', 'heading', '|', 'quote', 'unordered-list', 'ordered-list', '|', 'link', 'image', '|', 'preview', 'side-by-side', 'fullscreen', '|', 'guide']
                });
            } else {
                ta.value = content;
            }
        }, 100);

        document.addEventListener('keydown', this._editorKeyHandler = function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); self.saveEditor(); }
        });
    },

    saveEditor: async function() {
        var content = this._mde ? this._mde.value() : '';
        if (!content && !this._mde) {
            var ta = document.getElementById('kb-editor-textarea');
            if (ta) content = ta.value;
        }
        var fnEl = document.getElementById('kb-editor-filename');
        var newName = fnEl ? fnEl.value.trim() : this.currentDocName;
        var stEl = document.getElementById('kb-editor-status');
        if (stEl) stEl.textContent = '保存中...';

        await this.api('/api/kb/' + this.currentKbId + '/documents/' + this.currentDocId + '/content', 'PUT', { content: content });
        if (newName !== this.currentDocName) {
            await this.api('/api/kb/' + this.currentKbId + '/documents/' + this.currentDocId, 'PUT', { filename: newName });
            this.currentDocName = newName;
        }
        if (stEl) { stEl.textContent = '✓ 已保存'; setTimeout(function() { if (stEl) stEl.textContent = ''; }, 2000); }
    },

    previewPdf: function(docId) {
        var url = '/api/kb/' + this.currentKbId + '/documents/' + docId + '/download?token=' + encodeURIComponent(authToken);
        var h = '<h3>📄 PDF 预览</h3><button onclick="KnowledgeBase.renderDetail()" style="margin-bottom:6px">← 返回</button>';
        h += '<iframe class="kb-preview-frame" src="' + url + '"></iframe>';
        document.getElementById('kb-view').innerHTML = h;
    },

    previewText: async function(docId, ext) {
        var res = await this.api('/api/kb/' + this.currentKbId + '/documents/' + docId + '/content', 'GET');
        var h = '<h3>📝 预览</h3><button onclick="KnowledgeBase.renderDetail()" style="margin-bottom:6px">← 返回</button>';
        if (res.success) {
            if (ext === '.md' && typeof marked !== 'undefined') {
                h += '<div class="kb-preview-markdown">' + marked.parse(res.content) + '</div>';
            } else {
                h += '<div class="kb-preview-text">' + escapeHtmlText(res.content) + '</div>';
            }
        } else {
            h += '<div class="kb-empty">无法预览此文件</div>';
        }
        document.getElementById('kb-view').innerHTML = h;
    },

    setupDragDrop: function() {
        var self = this;
        var drop = document.getElementById('kb-upload-drop');
        var body = document.getElementById('kb-file-body');
        if (!body || !this.canEdit) return;

        body.addEventListener('dragover', function(e) { e.preventDefault(); if (drop) drop.classList.add('active'); });
        body.addEventListener('dragleave', function() { if (drop) drop.classList.remove('active'); });
        body.addEventListener('drop', function(e) {
            e.preventDefault();
            if (drop) drop.classList.remove('active');
            if (e.dataTransfer.files.length > 0) self.uploadDropFiles(e.dataTransfer.files);
        });
    },

    uploadDropFiles: async function(files) {
        for (var i = 0; i < files.length; i++) {
            var fd = new FormData();
            fd.append('file', files[i]);
            if (this.currentCategory) fd.append('category_id', this.currentCategory);
            await this.uploadApi('/api/kb/' + this.currentKbId + '/documents', fd);
        }
        await this.loadDocuments();
    },

    setupContextMenu: function() {
        var self = this;
        var fileBody = document.getElementById('kb-file-body');
        if (!fileBody) return;

        fileBody.oncontextmenu = function(e) {
            var row = e.target.closest('.kb-file-row');
            if (row) {
                var docId = row.getAttribute('data-doc-id');
                if (docId && !self.selectedDocs[docId]) {
                    self.selectedDocs = {};
                    self.selectedDocs[docId] = true;
                    self.refreshRowSelection();
                }
                self.showFileContextMenu(e.clientX, e.clientY);
            } else {
                self.showBlankContextMenu(e.clientX, e.clientY);
            }
            e.preventDefault();
        };

        document.addEventListener('click', function() {
            if (self._contextMenu) { self._contextMenu.remove(); self._contextMenu = null; }
        });
    },

    showFileContextMenu: function(x, y) {
        if (this._contextMenu) this._contextMenu.remove();
        var ids = Object.keys(this.selectedDocs);
        var multi = ids.length > 1;
        var menu = document.createElement('div');
        menu.className = 'kb-context-menu';
        menu.style.left = x + 'px';
        menu.style.top = y + 'px';

        var h = '';
        if (!multi) {
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.dblClickDoc(\'' + ids[0] + '\',KnowledgeBase.getSelectedDocType(\'' + ids[0] + '\'),KnowledgeBase.getSelectedDocName(\'' + ids[0] + '\'));KnowledgeBase.hideContextMenu()"><span class="icon">📖</span>打开</div>';
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.downloadDoc(\'' + ids[0] + '\');KnowledgeBase.hideContextMenu()"><span class="icon">⬇</span>下载</div>';
            if (this.canEdit) {
                h += '<div class="kb-menu-item" onclick="KnowledgeBase.triggerReplace(\'' + ids[0] + '\');KnowledgeBase.hideContextMenu()"><span class="icon">🔄</span>替换上传</div>';
                h += '<div class="kb-menu-divider"></div>';
                h += '<div class="kb-menu-item" onclick="var n=prompt(\'新文件名:\',KnowledgeBase.getSelectedDocName(\'' + ids[0] + '\'));if(n){KnowledgeBase.api(\'/api/kb/\'+KnowledgeBase.currentKbId+\'/documents/\'+\'' + ids[0] + '\',\'PUT\',{filename:n}).then(function(){KnowledgeBase.loadDocuments()})};KnowledgeBase.hideContextMenu()"><span class="icon">✏️</span>重命名</div>';
                h += '<div class="kb-menu-divider"></div>';
                h += '<div class="kb-menu-item" onclick="KnowledgeBase.deleteDoc(\'' + ids[0] + '\');KnowledgeBase.hideContextMenu()"><span class="icon">🗑</span>删除</div>';
            }
        } else {
            h += '<div class="kb-menu-item" onclick="KnowledgeBase.batchDownload();KnowledgeBase.hideContextMenu()"><span class="icon">📥</span>批量下载 (' + ids.length + '个)</div>';
            if (this.canEdit) {
                h += '<div class="kb-menu-divider"></div>';
                h += '<div class="kb-menu-item" onclick="KnowledgeBase.deleteSelected();KnowledgeBase.hideContextMenu()"><span class="icon">🗑</span>批量删除 (' + ids.length + '个)</div>';
            }
        }

        menu.innerHTML = h;
        document.body.appendChild(menu);
        this._contextMenu = menu;
    },

    showBlankContextMenu: function(x, y) {
        if (this._contextMenu) this._contextMenu.remove();
        if (!this.canEdit) return;
        var menu = document.createElement('div');
        menu.className = 'kb-context-menu';
        menu.style.left = x + 'px';
        menu.style.top = y + 'px';
        var h = '<div class="kb-menu-item" onclick="document.getElementById(\'kb-upload-input\').click();KnowledgeBase.hideContextMenu()"><span class="icon">📤</span>上传文件</div>';
        h += '<div class="kb-menu-item" onclick="KnowledgeBase.createMarkdown();KnowledgeBase.hideContextMenu()"><span class="icon">📝</span>新建 Markdown</div>';
        h += '<div class="kb-menu-item" onclick="KnowledgeBase.showCreateCategory();KnowledgeBase.hideContextMenu()"><span class="icon">📂</span>新建文件夹</div>';
        menu.innerHTML = h;
        document.body.appendChild(menu);
        this._contextMenu = menu;
    },

    hideContextMenu: function() {
        if (this._contextMenu) { this._contextMenu.remove(); this._contextMenu = null; }
    },

    getSelectedDocType: function(docId) {
        var row = document.querySelector('.kb-file-row[data-doc-id="' + docId + '"]');
        return row ? row.getAttribute('data-doc-type') : '';
    },

    getSelectedDocName: function(docId) {
        var row = document.querySelector('.kb-file-row[data-doc-id="' + docId + '"]');
        return row ? row.getAttribute('data-doc-name') : '';
    },

    batchDownload: function() {
        var ids = Object.keys(this.selectedDocs);
        for (var i = 0; i < ids.length; i++) this.downloadDoc(ids[i]);
    },

    showCreateKb: async function() {
        var name = prompt('请输入知识库名称:');
        if (!name) return;
        var res = await this.api('/api/kb/list', 'POST', { name: name });
        if (res.success) {
            await this.renderKbList();
        } else {
            alert(res.message || '创建失败');
        }
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
        if (!confirm('确定要删除此知识库及其所有文档吗？此操作不可恢复！')) return;
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
                h += '<tr>';
                h += '<td>' + escapeHtmlText(r.kb_name) + '</td>';
                h += '<td><span class="kb-file-name" onclick="KnowledgeBase.openKb(\'' + r.kb_id + '\',\'view\',\'' + escapeHtmlText(r.kb_name) + '\')">' + escapeHtmlText(r.filename) + '</span></td>';
                h += '<td>' + (r.match_type === 'filename' ? '文件名' : '内容') + '</td>';
                h += '<td><a href="#" onclick="KnowledgeBase.currentKbId=\'' + r.kb_id + '\';KnowledgeBase.downloadDoc(\'' + r.document_id + '\');return false">下载</a></td>';
                h += '</tr>';
            }
            h += '</tbody></table>';
        } else {
            h += '<div class="kb-empty">未找到匹配结果</div>';
        }
        document.getElementById('kb-view').innerHTML = h;
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
