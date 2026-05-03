var KnowledgeBase = {
    currentKbId: null,
    currentPermission: null,
    currentCategory: null,
    currentDocId: null,
    currentDocName: null,
    selectedDocs: {},
    _mde: null,
    _modalOverlay: null,
    _viewCache: null,

    init: function() {
        this.renderList();
    },

    api: function(url, method, body) {
        var self = this;
        return new Promise(function(resolve) {
            var options = {
                method: method || 'GET',
                headers: {
                    'Authorization': 'Bearer ' + (authToken || ''),
                    'Content-Type': 'application/json'
                }
            };
            if (body && method !== 'GET') {
                options.body = JSON.stringify(body);
            }
            fetch(url, options).then(function(r) { return r.json(); })
                .then(resolve)
                .catch(function() { resolve({ success: false, message: '网络错误' }); });
        });
    },

    uploadApi: function(url, formData) {
        var self = this;
        return new Promise(function(resolve) {
            fetch(url, {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + (authToken || '') },
                body: formData
            }).then(function(r) { return r.json(); })
              .then(resolve)
              .catch(function() { resolve({ success: false, message: '网络错误' }); });
        });
    },

    putUploadApi: function(url, formData) {
        var self = this;
        return new Promise(function(resolve) {
            fetch(url, {
                method: 'PUT',
                headers: { 'Authorization': 'Bearer ' + (authToken || '') },
                body: formData
            }).then(function(r) { return r.json(); })
              .then(resolve)
              .catch(function() { resolve({ success: false, message: '网络错误' }); });
        });
    },

    showView: function(html, title) {
        var container = document.querySelector('.container');
        var kbView = document.getElementById('kb-view');
        if (container) container.style.display = 'none';
        if (kbView) {
            kbView.classList.remove('kb-hidden');
            kbView.innerHTML = html;
        }
        document.title = title ? title + ' - 文枢' : '文枢';
    },

    hideView: function() {
        var container = document.querySelector('.container');
        var kbView = document.getElementById('kb-view');
        if (kbView) {
            kbView.classList.add('kb-hidden');
            kbView.innerHTML = '';
        }
        if (container) container.style.display = '';
    },

    getUserRole: function() {
        var users = JSON.parse(localStorage.getItem('kb_user_list') || '[]');
        for (var i = 0; i < users.length; i++) {
            if (users[i].username === authUsername) return users[i].role;
        }
        return 'viewer';
    },

    refreshUserCache: async function() {
        var res = await this.api('/api/users/list', 'GET');
        if (res.success) {
            localStorage.setItem('kb_user_list', JSON.stringify(res.users));
        }
    },

    renderList: async function() {
        this.currentKbId = null;
        this.currentMode = 'list';
        await this.refreshUserCache();
        var role = this.getUserRole();

        var html = '<h2 style="margin-bottom:16px">📚 知识库</h2>';
        html += '<div class="kb-topbar">';
        html += '<input type="text" id="kb-search-input" placeholder="搜索文档..." onkeydown="if(event.keyCode===13) KnowledgeBase.search()">';
        html += '<button onclick="KnowledgeBase.search()">搜索</button>';
        if (role === 'admin') {
            html += '<button class="kb-btn-gray" onclick="KnowledgeBase.showUserManage()">👥 用户管理</button>';
        }
        html += '<button class="kb-btn-gray" onclick="KnowledgeBase.hideView()">返回主页</button>';
        html += '</div>';
        html += '<div style="margin-bottom:12px"><button onclick="KnowledgeBase.showCreateKb()">+ 新建知识库</button></div>';
        html += '<div class="kb-grid" id="kb-grid"><div class="kb-empty">加载中...</div></div>';

        this.showView(html, '知识库');
        var res = await this.api('/api/kb/list', 'GET');
        var grid = document.getElementById('kb-grid');
        if (!grid) return;

        if (!res.success || !res.kbs || res.kbs.length === 0) {
            grid.innerHTML = '<div class="kb-empty">暂无知识库，点击上方按钮创建</div>';
            return;
        }

        var h = '';
        for (var i = 0; i < res.kbs.length; i++) {
            var kb = res.kbs[i];
            h += '<div class="kb-card" onclick="KnowledgeBase.openKb(\'' + kb.id + '\',\'' + kb.permission + '\')">';
            h += '<h3>' + escapeHtml(kb.name) + '</h3>';
            h += '<div class="kb-card-info">' + kb.document_count + ' 个文档</div>';
            var cls = kb.permission === 'manage' ? 'manage' : (kb.permission === 'edit' ? 'edit' : 'view');
            var label = kb.permission === 'manage' ? '管理' : (kb.permission === 'edit' ? '编辑' : '查看');
            h += '<span class="kb-card-role ' + cls + '">' + label + '</span>';
            h += '</div>';
        }
        grid.innerHTML = h;
    },

    openKb: async function(kbId, permission) {
        this.currentKbId = kbId;
        this.currentPermission = permission;
        this.currentCategory = null;
        this.selectedDocs = {};
        await this.renderDetail();
    },

    renderDetail: async function() {
        var perm = this.currentPermission;
        var canEdit = perm === 'edit' || perm === 'manage';
        var canManage = perm === 'manage';

        var html = '<h2 style="margin-bottom:12px">📁 知识库</h2>';
        html += '<div class="kb-topbar">';
        html += '<button class="kb-back-btn" onclick="KnowledgeBase.renderList()">← 返回</button>';
        html += '<input type="text" id="kb-search-input" placeholder="在当前知识库中搜索..." onkeydown="if(event.keyCode===13) KnowledgeBase.search()">';
        html += '<button onclick="KnowledgeBase.search()">搜索</button>';
        if (canManage) html += '<button onclick="KnowledgeBase.showSettings()">⚙ 设置</button>';
        html += '</div>';
        html += '<div class="kb-main">';
        html += '<div class="kb-sidebar" id="kb-sidebar"><h3>📁 分类</h3></div>';
        html += '<div class="kb-content">';
        html += '<div class="kb-actions" id="kb-actions">';
        if (canEdit) {
            html += '<button onclick="document.getElementById(\'kb-upload-input\').click()">📤 上传文件</button>';
            html += '<button onclick="KnowledgeBase.createMarkdown()">📝 新建 Markdown</button>';
            html += '<button onclick="KnowledgeBase.showCreateCategory()">📂 新建分类</button>';
            html += '<input type="file" id="kb-upload-input" style="display:none" onchange="KnowledgeBase.handleUpload(this)">';
            html += '<input type="file" id="kb-replace-input" style="display:none" onchange="KnowledgeBase.handleReplace(this)">';
        }
        html += '<button class="kb-btn-outline" onclick="KnowledgeBase.downloadSelected()">⬇ 批量下载</button>';
        if (canEdit) html += '<button class="kb-btn-gray" onclick="KnowledgeBase.deleteSelected()">🗑 删除选中</button>';
        html += '</div>';
        if (canEdit) {
            html += '<div id="kb-upload-drop" class="kb-upload-zone">拖拽文件到此处上传</div>';
        }
        html += '<div id="kb-doc-list"><div class="kb-empty">加载中...</div></div>';
        html += '</div></div>';

        this.showView(html, '知识库详情');

        if (canEdit) {
            var self = this;
            var drop = document.getElementById('kb-upload-drop');
            if (drop) {
                drop.addEventListener('dragover', function(e) { e.preventDefault(); drop.classList.add('dragover'); });
                drop.addEventListener('dragleave', function() { drop.classList.remove('dragover'); });
                drop.addEventListener('drop', function(e) {
                    e.preventDefault();
                    drop.classList.remove('dragover');
                    self.uploadFiles(e.dataTransfer.files);
                });
            }
        }

        await this.loadCategories();
        await this.loadDocuments();
    },

    loadCategories: async function() {
        var sidebar = document.getElementById('kb-sidebar');
        if (!sidebar) return;
        var res = await this.api('/api/kb/' + this.currentKbId + '/categories', 'GET');
        var html = '<h3>📁 分类</h3>';
        html += '<div class="kb-tree-item' + (!this.currentCategory ? ' active' : '') + '" onclick="KnowledgeBase.filterByCategory(null)">📄 全部文档</div>';
        if (res.success && res.categories) {
            html += this.buildCategoryTree(res.categories, 0);
        }
        html += '<div style="margin-top:12px"><button onclick="KnowledgeBase.renderList()">📚 所有知识库</button></div>';
        sidebar.innerHTML = html;
    },

    buildCategoryTree: function(cats, depth) {
        var html = '';
        var indent = '&nbsp;&nbsp;'.repeat(depth);
        for (var i = 0; i < cats.length; i++) {
            var c = cats[i];
            html += '<div class="kb-tree-item' + (this.currentCategory === c.id ? ' active' : '') + '" onclick="KnowledgeBase.filterByCategory(\'' + c.id + '\')">' + indent + '📁 ' + escapeHtml(c.name) + '</div>';
            if (c.children && c.children.length > 0) {
                html += this.buildCategoryTree(c.children, depth + 1);
            }
        }
        return html;
    },

    filterByCategory: async function(catId) {
        this.currentCategory = catId || null;
        await this.loadCategories();
        await this.loadDocuments(catId);
    },

    loadDocuments: async function(catId) {
        var list = document.getElementById('kb-doc-list');
        if (!list) return;
        var url = '/api/kb/' + this.currentKbId + '/documents';
        if (catId) url += '?category_id=' + catId;
        var res = await this.api(url, 'GET');

        if (!res.success || !res.documents || res.documents.length === 0) {
            list.innerHTML = '<div class="kb-empty">暂无文档</div>';
            return;
        }

        var self = this;
        var html = '<table class="kb-doc-table"><thead><tr>';
        html += '<th><input type="checkbox" onchange="KnowledgeBase.toggleAll(this)"></th>';
        html += '<th>文件名</th><th>大小</th><th>修改时间</th><th>操作</th></tr></thead><tbody>';

        for (var i = 0; i < res.documents.length; i++) {
            var d = res.documents[i];
            var size = d.file_size < 1024 ? d.file_size + ' B' :
                (d.file_size < 1048576 ? (d.file_size / 1024).toFixed(1) + ' KB' :
                (d.file_size / 1048576).toFixed(1) + ' MB');
            var date = new Date(d.updated_at * 1000).toLocaleString('zh-CN');
            var typeLabel = (d.file_type || '').replace('.', '').toUpperCase();
            var checked = self.selectedDocs[d.id] ? ' checked' : '';

            html += '<tr>';
            html += '<td><input type="checkbox" ' + checked + ' onchange="KnowledgeBase.toggleDoc(\'' + d.id + '\', this)"></td>';
            html += '<td><span class="kb-doc-name" onclick="KnowledgeBase.previewOrEdit(\'' + d.id + '\',\'' + (d.file_type||'') + '\',\'' + escapeHtml(d.filename).replace(/'/g,"\\'") + '\')">' + escapeHtml(d.filename) + '</span> <span class="kb-tag">' + typeLabel + '</span></td>';
            html += '<td>' + size + '</td>';
            html += '<td>' + date + '</td>';
            html += '<td>';
            html += '<a href="#" onclick="KnowledgeBase.downloadDoc(\'' + d.id + '\');return false">下载</a>';
            if (self.currentPermission === 'edit' || self.currentPermission === 'manage') {
                html += ' | <a href="#" onclick="KnowledgeBase.triggerReplace(\'' + d.id + '\');return false">替换</a>';
                html += ' | <a href="#" onclick="KnowledgeBase.deleteDoc(\'' + d.id + '\');return false">删除</a>';
            }
            html += '</td></tr>';
        }
        html += '</tbody></table>';
        list.innerHTML = html;
    },

    previewOrEdit: function(docId, fileType, filename) {
        var ext = (fileType || '').toLowerCase();
        if (ext === '.md' && (this.currentPermission === 'edit' || this.currentPermission === 'manage')) {
            this.openEditor(docId, filename);
        } else if (ext === '.pdf') {
            this.previewPdf(docId);
        } else if (ext === '.md' || ext === '.txt' || ext === '.html' || ext === '.htm') {
            this.previewText(docId, ext);
        } else {
            this.downloadDoc(docId);
        }
    },

    previewPdf: function(docId) {
        var url = '/api/kb/' + this.currentKbId + '/documents/' + docId + '/download?token=' + encodeURIComponent(authToken);
        var html = '<h2>📄 PDF 预览</h2>';
        html += '<div class="kb-topbar"><button class="kb-back-btn" onclick="KnowledgeBase.renderDetail()">← 返回</button></div>';
        html += '<iframe class="kb-preview-frame" src="' + url + '"></iframe>';
        this.showView(html, 'PDF 预览');
    },

    previewText: async function(docId, ext) {
        var res = await this.api('/api/kb/' + this.currentKbId + '/documents/' + docId + '/content', 'GET');
        var html = '<h2>📝 预览</h2>';
        html += '<div class="kb-topbar"><button class="kb-back-btn" onclick="KnowledgeBase.renderDetail()">← 返回</button></div>';
        if (res.success) {
            if (ext === '.md' && typeof marked !== 'undefined') {
                html += '<div class="kb-preview-markdown">' + marked.parse(res.content) + '</div>';
            } else {
                html += '<div class="kb-preview-text">' + escapeHtml(res.content) + '</div>';
            }
        } else {
            html += '<div class="kb-empty">无法预览</div>';
        }
        this.showView(html, '预览');
    },

    downloadDoc: function(docId) {
        window.open('/api/kb/' + this.currentKbId + '/documents/' + docId + '/download?token=' + encodeURIComponent(authToken), '_blank');
    },

    openEditor: function(docId, filename) {
        this.currentDocId = docId;
        this.currentDocName = filename || 'Untitled.md';
        this.renderEditor();
    },

    renderEditor: async function() {
        var self = this;
        var html = '<h2>📝 编辑</h2>';
        html += '<div class="kb-editor-toolbar">';
        html += '<button class="kb-btn-cancel" onclick="KnowledgeBase.renderDetail()">← 返回</button>';
        html += '<input type="text" id="kb-editor-filename" value="' + escapeHtml(this.currentDocName || '') + '">';
        html += '<button onclick="KnowledgeBase.saveEditor()">💾 保存</button>';
        html += '<span class="kb-status" id="kb-editor-status"></span>';
        html += '</div>';
        html += '<div class="kb-editor-wrap"><div class="kb-editor-body"><textarea id="kb-editor-textarea"></textarea></div></div>';

        this.showView(html, '编辑 - ' + (this.currentDocName || ''));

        var res = await this.api('/api/kb/' + this.currentKbId + '/documents/' + this.currentDocId + '/content', 'GET');
        var ta = document.getElementById('kb-editor-textarea');
        if (!ta) return;
        var content = res.success ? res.content : '';

        if (typeof EasyMDE !== 'undefined') {
            this._mde = new EasyMDE({
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

        document.addEventListener('keydown', this._editorKeyHandler = function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                self.saveEditor();
            }
        });
    },

    saveEditor: async function() {
        var content = this._mde ? this._mde.value() : '';
        if (!content && !this._mde) {
            var ta = document.getElementById('kb-editor-textarea');
            if (ta) content = ta.value;
        }

        var filenameEl = document.getElementById('kb-editor-filename');
        var newName = filenameEl ? filenameEl.value.trim() : this.currentDocName;

        var statusEl = document.getElementById('kb-editor-status');
        if (statusEl) statusEl.textContent = '保存中...';

        await this.api('/api/kb/' + this.currentKbId + '/documents/' + this.currentDocId + '/content', 'PUT', { content: content });

        if (newName !== this.currentDocName) {
            await this.api('/api/kb/' + this.currentKbId + '/documents/' + this.currentDocId, 'PUT', { filename: newName });
            this.currentDocName = newName;
        }

        if (statusEl) {
            statusEl.textContent = '已保存';
            setTimeout(function() { if (statusEl) statusEl.textContent = ''; }, 2000);
        }
    },

    handleUpload: async function(input) {
        await this.uploadFiles(input.files);
        input.value = '';
    },

    uploadFiles: async function(files) {
        if (!files || files.length === 0) return;
        var formData = new FormData();
        formData.append('file', files[0]);
        if (this.currentCategory) formData.append('category_id', this.currentCategory);
        var res = await this.uploadApi('/api/kb/' + this.currentKbId + '/documents', formData);
        if (res.success) {
            await this.loadDocuments(this.currentCategory);
        } else {
            alert(res.message || '上传失败');
        }
    },

    triggerReplace: function(docId) {
        this._replaceDocId = docId;
        document.getElementById('kb-replace-input').click();
    },

    handleReplace: async function(input) {
        if (!this._replaceDocId || !input.files || input.files.length === 0) return;
        var formData = new FormData();
        formData.append('file', input.files[0]);
        var res = await this.putUploadApi('/api/kb/' + this.currentKbId + '/documents/' + this._replaceDocId + '/replace', formData);
        this._replaceDocId = null;
        input.value = '';
        if (res.success) {
            await this.loadDocuments(this.currentCategory);
        } else {
            alert(res.message || '替换失败');
        }
    },

    createMarkdown: function() {
        var name = prompt('请输入 Markdown 文件名（不含扩展名）:');
        if (!name) return;
        if (!name.endsWith('.md')) name += '.md';
        this._createEmptyFile(name, '');
    },

    _createEmptyFile: async function(filename, content) {
        var formData = new FormData();
        var blob = new Blob([content || ''], { type: 'text/plain' });
        formData.append('file', blob, filename);
        if (this.currentCategory) formData.append('category_id', this.currentCategory);
        var res = await this.uploadApi('/api/kb/' + this.currentKbId + '/documents', formData);
        if (res.success && filename.endsWith('.md')) {
            this.openEditor(res.document.id, filename);
        }
        if (res.success) {
            await this.loadDocuments(this.currentCategory);
        }
    },

    showCreateCategory: async function() {
        var name = prompt('请输入分类名称:');
        if (!name) return;
        var res = await this.api('/api/kb/' + this.currentKbId + '/categories', 'POST',
            { name: name, parent_id: this.currentCategory || '' });
        if (res.success) await this.loadCategories();
    },

    deleteDoc: async function(docId) {
        if (!confirm('确定要删除此文档吗？')) return;
        var res = await this.api('/api/kb/' + this.currentKbId + '/documents/' + docId, 'DELETE');
        if (res.success) {
            delete this.selectedDocs[docId];
            await this.loadDocuments(this.currentCategory);
        }
    },

    deleteSelected: async function() {
        var ids = Object.keys(this.selectedDocs);
        if (ids.length === 0) { alert('请先选择文档'); return; }
        if (!confirm('确定要删除选中的 ' + ids.length + ' 个文档吗？')) return;
        for (var i = 0; i < ids.length; i++) {
            await this.api('/api/kb/' + this.currentKbId + '/documents/' + ids[i], 'DELETE');
            delete this.selectedDocs[ids[i]];
        }
        await this.loadDocuments(this.currentCategory);
    },

    toggleDoc: function(docId, cb) {
        if (cb.checked) this.selectedDocs[docId] = true;
        else delete this.selectedDocs[docId];
    },

    toggleAll: function(cb) {
        this.selectedDocs = {};
        if (cb.checked) {
            var checks = document.querySelectorAll('.kb-doc-table tbody input[type="checkbox"]');
            for (var i = 0; i < checks.length; i++) checks[i].checked = true;
        }
    },

    downloadSelected: function() {
        var ids = Object.keys(this.selectedDocs);
        if (ids.length === 0) { alert('请先选择文档'); return; }
        if (ids.length === 1) { this.downloadDoc(ids[0]); return; }
        for (var i = 0; i < ids.length; i++) this.downloadDoc(ids[i]);
    },

    showCreateKb: async function() {
        var name = prompt('请输入知识库名称:');
        if (!name) return;
        var res = await this.api('/api/kb/list', 'POST', { name: name });
        if (res.success) {
            if (this.currentMode === 'list') {
                var grid = document.getElementById('kb-grid');
                if (grid) await this.renderList();
            }
        } else {
            alert(res.message || '创建失败');
        }
    },

    showSettings: async function() {
        var res = await this.api('/api/kb/' + this.currentKbId + '/members', 'GET');
        var html = '<div class="kb-modal-overlay" id="kb-modal-overlay"><div class="kb-modal">';
        html += '<h3>⚙ 知识库设置</h3>';
        html += '<h4>成员管理</h4>';
        if (res.success && res.members) {
            html += '<table class="kb-member-table"><thead><tr><th>用户名</th><th>权限</th><th>操作</th></tr></thead><tbody>';
            for (var i = 0; i < res.members.length; i++) {
                var m = res.members[i];
                html += '<tr>';
                html += '<td>' + escapeHtml(m.username) + (m.is_owner ? ' (所有者)' : '') + '</td>';
                html += '<td>';
                if (m.is_owner) {
                    html += '管理';
                } else {
                    html += '<select onchange="KnowledgeBase.updateMember(\'' + m.user_id + '\', this.value)">';
                    html += '<option value="view"' + (m.permission==='view'?' selected':'') + '>查看</option>';
                    html += '<option value="edit"' + (m.permission==='edit'?' selected':'') + '>编辑</option>';
                    html += '<option value="manage"' + (m.permission==='manage'?' selected':'') + '>管理</option>';
                    html += '</select>';
                }
                html += '</td><td>';
                if (!m.is_owner) html += '<button class="kb-remove-btn" onclick="KnowledgeBase.removeMember(\'' + m.user_id + '\')">移除</button>';
                html += '</td></tr>';
            }
            html += '</tbody></table>';
        }
        html += '<div class="kb-add-member">';
        html += '<input type="text" id="kb-new-member" placeholder="用户名">';
        html += '<select id="kb-new-perm"><option value="view">查看</option><option value="edit">编辑</option><option value="manage">管理</option></select>';
        html += '<button onclick="KnowledgeBase.addMember()">添加</button></div>';
        html += '<hr style="margin:16px 0"><h4>转让所有权</h4>';
        html += '<div class="kb-add-member"><input type="text" id="kb-transfer-user" placeholder="新所有者用户名"><button onclick="KnowledgeBase.transferOwnership()">转让</button></div>';
        html += '<hr style="margin:16px 0"><button class="kb-danger-btn" onclick="KnowledgeBase.deleteKb()">删除知识库</button>';
        html += '<div class="kb-modal-actions"><button class="kb-btn-cancel" onclick="KnowledgeBase.closeModal()">关闭</button></div>';
        html += '</div></div>';

        this._modalOverlay = document.createElement('div');
        this._modalOverlay.innerHTML = html;
        document.body.appendChild(this._modalOverlay.firstElementChild);

        var overlay = document.getElementById('kb-modal-overlay');
        if (overlay) {
            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) KnowledgeBase.closeModal();
            });
        }
    },

    closeModal: function() {
        var overlay = document.getElementById('kb-modal-overlay');
        if (overlay) overlay.remove();
        this._modalOverlay = null;
    },

    addMember: async function() {
        var username = document.getElementById('kb-new-member').value.trim();
        var perm = document.getElementById('kb-new-perm').value;
        if (!username) return;
        var res = await this.api('/api/kb/' + this.currentKbId + '/members', 'POST',
            { username: username, permission: perm });
        if (res.success) { this.closeModal(); await this.showSettings(); }
        else alert(res.message);
    },

    updateMember: async function(userId, perm) {
        await this.api('/api/kb/' + this.currentKbId + '/members/' + userId, 'PUT', { permission: perm });
    },

    removeMember: async function(userId) {
        if (!confirm('确定要移除该成员吗？')) return;
        var res = await this.api('/api/kb/' + this.currentKbId + '/members/' + userId, 'DELETE');
        if (res.success) { this.closeModal(); await this.showSettings(); }
    },

    transferOwnership: async function() {
        var username = document.getElementById('kb-transfer-user').value.trim();
        if (!username) return;
        if (!confirm('确定将知识库所有权转让给 ' + username + ' 吗？')) return;
        var users = JSON.parse(localStorage.getItem('kb_user_list') || '[]');
        var targetId = null;
        for (var i = 0; i < users.length; i++) {
            if (users[i].username === username) { targetId = users[i].user_id; break; }
        }
        if (!targetId) { alert('用户不存在'); return; }
        var res = await this.api('/api/kb/' + this.currentKbId + '/transfer', 'POST', { new_owner_id: targetId });
        if (res.success) {
            this.closeModal();
            await this.renderList();
        } else {
            alert(res.message);
        }
    },

    deleteKb: async function() {
        if (!confirm('确定要删除此知识库及其所有文档吗？此操作不可恢复！')) return;
        var res = await this.api('/api/kb/' + this.currentKbId, 'DELETE');
        if (res.success) { this.closeModal(); await this.renderList(); }
        else alert(res.message);
    },

    showUserManage: async function() {
        await this.refreshUserCache();
        var users = JSON.parse(localStorage.getItem('kb_user_list') || '[]');
        var html = '<div class="kb-modal-overlay" id="kb-modal-overlay"><div class="kb-modal">';
        html += '<h3>👥 用户管理</h3>';
        html += '<table class="kb-member-table"><thead><tr><th>用户名</th><th>全局角色</th></tr></thead><tbody>';
        for (var i = 0; i < users.length; i++) {
            var u = users[i];
            html += '<tr><td>' + escapeHtml(u.username) + '</td>';
            html += '<td><select onchange="KnowledgeBase.updateUserRole(\'' + u.user_id + '\', this.value)">';
            html += '<option value="admin"' + (u.role==='admin'?' selected':'') + '>管理员</option>';
            html += '<option value="editor"' + (u.role==='editor'?' selected':'') + '>编辑者</option>';
            html += '<option value="viewer"' + (u.role==='viewer'?' selected':'') + '>阅读者</option>';
            html += '</select></td></tr>';
        }
        html += '</tbody></table>';
        html += '<div class="kb-modal-actions"><button class="kb-btn-cancel" onclick="KnowledgeBase.closeModal()">关闭</button></div>';
        html += '</div></div>';

        this._modalOverlay = document.createElement('div');
        this._modalOverlay.innerHTML = html;
        document.body.appendChild(this._modalOverlay.firstElementChild);

        var overlay = document.getElementById('kb-modal-overlay');
        if (overlay) {
            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) KnowledgeBase.closeModal();
            });
        }
    },

    updateUserRole: async function(userId, role) {
        var res = await this.api('/api/users/' + userId + '/role', 'PUT', { role: role });
        if (res.success) {
            await this.refreshUserCache();
        } else {
            alert(res.message);
        }
    },

    search: async function() {
        var qEl = document.getElementById('kb-search-input');
        var q = qEl ? qEl.value.trim() : '';
        if (!q) return;

        var res = await this.api('/api/kb/search?q=' + encodeURIComponent(q), 'GET');
        var html = '<h2>🔍 搜索结果</h2>';
        html += '<div class="kb-topbar">';
        html += '<button class="kb-back-btn" onclick="KnowledgeBase.renderList()">← 返回</button>';
        html += '搜索: <strong>' + escapeHtml(q) + '</strong></div>';

        if (res.success && res.results && res.results.length > 0) {
            html += '<table class="kb-doc-table"><thead><tr><th>知识库</th><th>文件名</th><th>匹配</th><th>操作</th></tr></thead><tbody>';
            for (var i = 0; i < res.results.length; i++) {
                var r = res.results[i];
                html += '<tr>';
                html += '<td>' + escapeHtml(r.kb_name) + '</td>';
                html += '<td><span class="kb-doc-name" onclick="KnowledgeBase.openKb(\'' + r.kb_id + '\',\'view\')">' + escapeHtml(r.filename) + '</span></td>';
                html += '<td>' + (r.match_type === 'filename' ? '文件名' : '内容') + '</td>';
                html += '<td><a href="#" onclick="KnowledgeBase.currentKbId=\'' + r.kb_id + '\';KnowledgeBase.downloadDoc(\'' + r.document_id + '\');return false">下载</a></td>';
                html += '</tr>';
            }
            html += '</tbody></table>';
        } else {
            html += '<div class="kb-empty">未找到匹配结果</div>';
        }
        this.showView(html, '搜索结果: ' + q);
    }
};

function openKB() {
    if (!authToken) { alert('请先登录'); return; }
    KnowledgeBase.init();
}
