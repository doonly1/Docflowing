var WikiKnowledge = {
    currentFile: null,
    currentPath: null,
    currentFolder: '',
    easyMDE: null,
    wikiName: '我的知识库',

    init: function() {
        this._renderView();
        this._loadInfo();
        this._renderTree();
    },

    _loadInfo: function() {
        var self = this;
        apiFetch('/api/kb/info', { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success && data.info) {
                self.wikiName = data.info.name || '我的知识库';
            }
        }).catch(function(e) {
            console.error('加载知识库信息失败:', e);
        });
    },

    _renderView: function() {
        var viewEl = document.getElementById('kb-view');
        if (!viewEl) return;

        viewEl.innerHTML = '';
        viewEl.innerHTML =
            '<div class="wiki-container">' +
                '<div class="wiki-main">' +
                    '<div class="wiki-sidebar">' +
                        '<div class="wiki-sidebar-header">' +
                            '<h3 id="wiki-sidebar-title">📖 知识库</h3>' +
                            '<div class="wiki-sidebar-actions">' +
                                '<button onclick="WikiKnowledge.showNewFolderInput()" title="新建文件夹">📁+</button>' +
                                '<button onclick="WikiKnowledge.showNewFileInput()" title="新建文件">📄+</button>' +
                            '</div>' +
                        '</div>' +
                        '<div id="wiki-new-container"></div>' +
                        '<div class="wiki-tree" id="wiki-tree"></div>' +
                    '</div>' +
                    '<div class="wiki-editor-area">' +
                        '<div class="wiki-editor-toolbar" id="wiki-toolbar" style="display:none;">' +
                            '<span class="filename" id="wiki-filename"></span>' +
                            '<button onclick="WikiKnowledge.saveFile()" class="primary">保存</button>' +
                            '<button onclick="WikiKnowledge.togglePreview()">预览</button>' +
                            '<button onclick="WikiKnowledge.deleteCurrentFile()" style="color:#c00;">删除</button>' +
                        '</div>' +
                        '<div class="wiki-editor-wrapper" id="wiki-editor-wrapper">' +
                            '<div class="wiki-empty-state" id="wiki-empty">' +
                                '<div class="icon">📝</div>' +
                                '<div>选择左侧文件开始编辑，或新建文件</div>' +
                            '</div>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                '<div class="wiki-search-bar">' +
                    '<input type="text" id="wiki-search-input" placeholder="搜索知识库内容..." onkeydown="if(event.key===\'Enter\')WikiKnowledge.search()">' +
                    '<button onclick="WikiKnowledge.search()">搜索</button>' +
                '</div>' +
                '<div class="wiki-search-results" id="wiki-search-results"></div>' +
            '</div>';
    },

    _renderTree: function() {
        var self = this;
        var treeEl = document.getElementById('wiki-tree');
        if (!treeEl) return;

        treeEl.innerHTML = '<div style="padding:20px;text-align:center;color:#999;">加载中...</div>';

        apiFetch('/api/kb/files', { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (!data.success) {
                treeEl.innerHTML = '<div style="padding:20px;text-align:center;color:#c00;">加载失败</div>';
                return;
            }

            var html = '';

            if (data.folders && data.folders.length > 0) {
                for (var i = 0; i < data.folders.length; i++) {
                    var folder = data.folders[i];
                    html += self._renderFolderItem(folder);
                }
            }

            if (data.files && data.files.length > 0) {
                for (var i = 0; i < data.files.length; i++) {
                    var file = data.files[i];
                    html += self._renderFileItem(file);
                }
            }

            if (!data.folders || data.folders.length === 0 && (!data.files || data.files.length === 0)) {
                html = '<div style="padding:20px;text-align:center;color:#999;font-size:13px;">空空如也，点击 + 新建</div>';
            }

            treeEl.innerHTML = html;
        }).catch(function(e) {
            treeEl.innerHTML = '<div style="padding:20px;text-align:center;color:#c00;">加载失败: ' + e.message + '</div>';
        });
    },

    _renderFolderItem: function(folder) {
        var self = this;
        var isActive = (self.currentFolder === folder.path);
        var activeClass = isActive ? ' active' : '';
        return '<div class="wiki-tree-item folder' + activeClass + '" onclick="WikiKnowledge.enterFolder(\'' + folder.path.replace(/'/g, "\\'") + '\')" oncontextmenu="WikiKnowledge.showFolderMenu(event, \'' + folder.path.replace(/'/g, "\\'") + '\', \'' + folder.name.replace(/'/g, "\\'") + '\')">' +
            '<span class="icon">📁</span>' +
            '<span class="name">' + escapeHtmlForWiki(folder.name) + '</span>' +
        '</div>';
    },

    _renderFileItem: function(file) {
        var isActive = (self.currentPath === file.path);
        var activeClass = isActive ? ' active' : '';
        return '<div class="wiki-tree-item' + activeClass + '" onclick="WikiKnowledge.openFile(\'' + file.path.replace(/'/g, "\\'") + '\')">' +
            '<span class="icon">📄</span>' +
            '<span class="name">' + escapeHtmlForWiki(file.name) + '</span>' +
        '</div>';
    },

    enterFolder: function(folderPath) {
        this.currentFolder = folderPath;
        this._renderTree();

        var self = this;
        apiFetch('/api/kb/files?subdir=' + encodeURIComponent(folderPath), { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (!data.success) return;
            var treeEl = document.getElementById('wiki-tree');
            if (!treeEl) return;
            var html = '';
            if (data.folders && data.folders.length > 0) {
                for (var i = 0; i < data.folders.length; i++) {
                    html += self._renderFolderItem(data.folders[i]);
                }
            }
            if (data.files && data.files.length > 0) {
                for (var i = 0; i < data.files.length; i++) {
                    html += self._renderFileItem(data.files[i]);
                }
            }
            if (!html) {
                html = '<div style="padding:20px;text-align:center;color:#999;font-size:13px;">空文件夹</div>';
            }
            treeEl.innerHTML = html;
        }).catch(function(e) {
            console.error('加载文件夹失败:', e);
        });
    },

    openFile: function(filePath) {
        var self = this;
        self.currentFile = filePath;
        self.currentPath = filePath;

        apiFetch('/api/kb/files/' + filePath, { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (!data.success) {
                alert('打开文件失败: ' + (data.message || '未知错误'));
                return;
            }

            self._showEditor(data.content, filePath);
            self._renderTree();
        }).catch(function(e) {
            alert('打开文件失败: ' + e.message);
        });
    },

    _showEditor: function(content, filePath) {
        var wrapper = document.getElementById('wiki-editor-wrapper');
        var toolbar = document.getElementById('wiki-toolbar');
        var filename = document.getElementById('wiki-filename');
        var emptyState = document.getElementById('wiki-empty');

        if (!wrapper || !toolbar) return;

        toolbar.style.display = 'flex';
        if (emptyState) emptyState.style.display = 'none';

        if (filename) {
            filename.textContent = filePath;
            filename.title = filePath;
        }

        if (this.easyMDE) {
            this.easyMDE.toTextArea();
            this.easyMDE = null;
        }

        var existingTextarea = wrapper.querySelector('textarea');
        if (existingTextarea) existingTextarea.remove();

        var textarea = document.createElement('textarea');
        textarea.id = 'wiki-editor-textarea';
        textarea.value = content || '';
        wrapper.appendChild(textarea);

        this.easyMDE = new EasyMDE({
            element: textarea,
            spellChecker: false,
            autosave: {
                enabled: false
            },
            toolbar: ['bold', 'italic', 'heading', '|', 'quote', 'unordered-list', 'ordered-list', '|', 'link', 'image', '|', 'preview', 'side-by-side', 'fullscreen', '|', 'guide'],
            previewRender: function(plainText) {
                return marked.parse(plainText);
            },
            status: false
        });
    },

    saveFile: function() {
        var self = this;
        if (!self.currentFile) {
            alert('请先选择或创建一个文件');
            return;
        }

        if (!self.easyMDE) return;

        var content = self.easyMDE.value();

        apiFetch('/api/kb/files/' + self.currentFile, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: content })
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                alert('文件已保存');
            } else {
                alert('保存失败: ' + (data.message || '未知错误'));
            }
        }).catch(function(e) {
            alert('保存失败: ' + e.message);
        });
    },

    togglePreview: function() {
        if (this.easyMDE) {
            this.easyMDE.togglePreview();
        }
    },

    deleteCurrentFile: function() {
        var self = this;
        if (!self.currentFile) return;
        if (!confirm('确定要删除此文件吗？')) return;

        apiFetch('/api/kb/files/' + self.currentFile, {
            method: 'DELETE'
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                self.currentFile = null;
                self.currentPath = null;
                self._showEmptyEditor();
                self._renderTree();
            } else {
                alert('删除失败: ' + (data.message || '未知错误'));
            }
        }).catch(function(e) {
            alert('删除失败: ' + e.message);
        });
    },

    _showEmptyEditor: function() {
        var wrapper = document.getElementById('wiki-editor-wrapper');
        var toolbar = document.getElementById('wiki-toolbar');
        var emptyState = document.getElementById('wiki-empty');

        if (this.easyMDE) {
            this.easyMDE.toTextArea();
            this.easyMDE = null;
        }

        if (toolbar) toolbar.style.display = 'none';
        if (emptyState) emptyState.style.display = 'flex';

        var existingTextarea = wrapper ? wrapper.querySelector('textarea') : null;
        if (existingTextarea) existingTextarea.remove();
    },

    showNewFolderInput: function() {
        var container = document.getElementById('wiki-new-container');
        if (!container) return;
        container.innerHTML =
            '<div class="wiki-new-input">' +
                '<input type="text" id="wiki-new-name" placeholder="文件夹名称" onkeydown="if(event.key===\'Enter\')WikiKnowledge.createFolder()">' +
                '<button onclick="WikiKnowledge.createFolder()">确定</button>' +
                '<button class="cancel" onclick="WikiKnowledge.cancelNew()">取消</button>' +
            '</div>';
        document.getElementById('wiki-new-name').focus();
    },

    showNewFileInput: function() {
        var container = document.getElementById('wiki-new-container');
        if (!container) return;
        container.innerHTML =
            '<div class="wiki-new-input">' +
                '<input type="text" id="wiki-new-name" placeholder="文件名称（自动添加 .md）" onkeydown="if(event.key===\'Enter\')WikiKnowledge.createFile()">' +
                '<button onclick="WikiKnowledge.createFile()">确定</button>' +
                '<button class="cancel" onclick="WikiKnowledge.cancelNew()">取消</button>' +
            '</div>';
        document.getElementById('wiki-new-name').focus();
    },

    cancelNew: function() {
        var container = document.getElementById('wiki-new-container');
        if (container) container.innerHTML = '';
    },

    createFolder: function() {
        var self = this;
        var input = document.getElementById('wiki-new-name');
        if (!input) return;
        var name = input.value.trim();
        if (!name) { alert('名称不能为空'); return; }

        apiFetch('/api/kb/folders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, parent: self.currentFolder || '' })
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                self.cancelNew();
                self._renderTree();
            } else {
                alert('创建失败: ' + (data.message || '未知错误'));
            }
        }).catch(function(e) {
            alert('创建失败: ' + e.message);
        });
    },

    createFile: function() {
        var self = this;
        var input = document.getElementById('wiki-new-name');
        if (!input) return;
        var name = input.value.trim();
        if (!name) { alert('名称不能为空'); return; }

        var filePath = name;
        if (!filePath.toLowerCase().endsWith('.md')) {
            filePath = filePath + '.md';
        }

        if (self.currentFolder) {
            filePath = self.currentFolder + '/' + filePath;
        }

        apiFetch('/api/kb/files/' + filePath, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: '# ' + name.replace(/\.md$/i, '') + '\n\n' })
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                self.cancelNew();
                self._renderTree();
                self.openFile(filePath);
            } else {
                alert('创建失败: ' + (data.message || '未知错误'));
            }
        }).catch(function(e) {
            alert('创建失败: ' + e.message);
        });
    },

    search: function() {
        var self = this;
        var input = document.getElementById('wiki-search-input');
        var resultsDiv = document.getElementById('wiki-search-results');
        if (!input || !resultsDiv) return;

        var q = input.value.trim();
        if (!q) {
            resultsDiv.classList.remove('show');
            resultsDiv.innerHTML = '';
            return;
        }

        resultsDiv.innerHTML = '<div style="padding:12px;text-align:center;color:#999;">搜索中...</div>';
        resultsDiv.classList.add('show');

        apiFetch('/api/kb/search?q=' + encodeURIComponent(q), { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (!data.success || !data.results || data.results.length === 0) {
                resultsDiv.innerHTML = '<div style="padding:12px;text-align:center;color:#999;">未找到匹配内容</div>';
                return;
            }

            var html = '';
            for (var i = 0; i < data.results.length; i++) {
                var r = data.results[i];
                html += '<div class="wiki-search-result-item" onclick="WikiKnowledge.openFile(\'' + (r.path || '').replace(/'/g, "\\'") + '\')">' +
                    '<div class="title">' + (r.title || r.path) + '</div>' +
                    '<div class="snippet">' + (r.content_snippet || '') + '</div>' +
                '</div>';
            }
            resultsDiv.innerHTML = html;
        }).catch(function(e) {
            resultsDiv.innerHTML = '<div style="padding:12px;text-align:center;color:#c00;">搜索失败</div>';
        });
    }
};

function escapeHtmlForWiki(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
