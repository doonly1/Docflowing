function escapeJsForHtmlAttr(str) {
    if (str === undefined || str === null) return '';
    return String(str)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r')
        .replace(/\t/g, '\\t')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// ==================== 侧边栏折叠 ====================
function toggleSidebarCollapse() {
    document.body.classList.toggle('sidebar-collapsed');
    // 重新渲染标签栏以更新折叠按钮图标
    if (typeof tabManager !== 'undefined') tabManager._renderBar();
    localStorage.setItem('docflow_sidebar_collapsed', document.body.classList.contains('sidebar-collapsed') ? '1' : '0');
}

// ==================== 窗口控制（Electron IPC） ====================

function windowMinimize() {
    if (window.electronAPI) window.electronAPI.windowMinimize();
}

function windowMaximizeRestore() {
    if (window.electronAPI) window.electronAPI.windowToggleMaximize();
}

function windowClose() {
    if (window.electronAPI) window.electronAPI.windowClose();
}

// ==================== Tab Manager - 浏览器风格多标签页 ====================
window.tabManager = {
    tabs: [],
    nextId: 1,
    activeTabId: null,

    init: function() {
        // 恢复侧边栏状态
        if (localStorage.getItem('docflow_sidebar_collapsed') === '1') {
            document.body.classList.add('sidebar-collapsed');
        }
        // 应用启动时创建 home 标签（KB 会话）
        this.createTab('home');
        // 更新 sidebar 高亮
        this._updateSidebar('home');
    },

    _getTabIcon: function(type) {
        switch (type) {
            case 'home':
                return '<span class="tab-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg></span>';
            case 'chat':
                return '<span class="tab-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></span>';
            case 'fb':
                return '<span class="tab-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></span>';
            case 'tools':
                return '<span class="tab-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8z"/><polyline points="15 2 15 8 21 8"/></svg></span>';
            default:
                return '';
        }
    },

    _getTabTitle: function(tab) {
        switch (tab.type) {
            case 'home': return '首页';
            case 'chat': return tab.state.chatName || '会话';
            case 'fb': return tab.state.fbName || '文件库';
            case 'tools': return tab.state.toolName || '工具';
            default: return tab.type;
        }
    },

    _updateSidebar: function(type) {
        var navItems = document.querySelectorAll('.sidebar-nav-item');
        for (var i = 0; i < navItems.length; i++) navItems[i].classList.remove('active');
        var navItem = document.querySelector('.sidebar-nav-item[data-view="' + type + '"]');
        if (navItem) navItem.classList.add('active');
    },

    createTab: function(type, forceNew) {
        // 非 home 标签：forceNew=false 时复用同类型无标识标签
        if (!forceNew && type !== 'home') {
            for (var i = 0; i < this.tabs.length; i++) {
                if (this.tabs[i].type === type && !this.tabs[i]._identified) {
                    this.switchTab(this.tabs[i].id);
                    return this.tabs[i];
                }
            }
        }

        var id = 't' + (this.nextId++);
        var tab = { id: id, type: type, state: {}, _identified: false };
        this.tabs.push(tab);
        this.switchTab(id);
        this._renderBar();
        return tab;
    },

    openOrCreateTab: function(type, forceNew) {
        if (type === 'home') {
            var existing = this._findByType('home');
            if (existing) { this.switchTab(existing.id); return; }
            this.createTab('home');
            return;
        }
        if (forceNew) { this.createTab(type, true); return; }
        // 复用同类型无标识标签
        for (var i = 0; i < this.tabs.length; i++) {
            if (this.tabs[i].type === type && !this.tabs[i]._identified) {
                this.switchTab(this.tabs[i].id);
                return;
            }
        }
        this.createTab(type, false);
    },

    // 首页标签→会话标签：发送第一条消息后，标签名变为消息内容
    convertHomeToChat: function(sessionId, title) {
        var tab = this._findById(this.activeTabId);
        if (!tab || tab.type !== 'home') return;
        tab.type = 'chat';
        tab.state = {
            sessionId: sessionId,
            chatName: title.length > 20 ? title.substring(0, 20) + '...' : title
        };
        tab._identified = true;
        this._renderBar();
    },

    switchTab: function(id) {
        // 点击已激活标签时忽略，避免刷新抖动
        if (id === this.activeTabId) return;

        // 保存当前标签状态
        if (this.activeTabId) this._saveTabState(this.activeTabId);

        this.activeTabId = id;
        this._renderBar();
        this._renderContent(id);
    },

    closeTab: function(id) {
        var idx = -1;
        for (var i = 0; i < this.tabs.length; i++) {
            if (this.tabs[i].id === id) { idx = i; break; }
        }
        if (idx === -1) return;

        this.tabs.splice(idx, 1);

        if (this.tabs.length === 0) {
            this.createTab('home');
            return;
        }

        if (this.activeTabId === id) {
            var newIdx = Math.min(idx, this.tabs.length - 1);
            this.switchTab(this.tabs[newIdx].id);
        } else {
            this._renderBar();
        }
    },

    _findByType: function(type) {
        for (var i = 0; i < this.tabs.length; i++) {
            if (this.tabs[i].type === type) return this.tabs[i];
        }
        return null;
    },

    _saveTabState: function(id) {
        var tab = this._findById(id);
        if (!tab) return;
        switch (tab.type) {
            case 'home':
                // home 标签：无需保存 sessionId（只有初次渲染才需要）
                tab.state = {};
                break;
            case 'chat':
                tab.state = {
                    sessionId: typeof WikiKnowledge !== 'undefined' ? WikiKnowledge.sessionId : null,
                    chatName: tab.state.chatName || ''
                };
                // 离开 chat 标签时清空本地消息（流仍在后台继续，最终存到服务端）
                if (typeof WikiKnowledge !== 'undefined') {
                    WikiKnowledge.messages = [];
                }
                break;
            case 'fb':
                if (typeof FileBase !== 'undefined') {
                    // 保护：当 FileBase 在列表态（currentFbId===null）且 tab 已有有效状态时，不覆盖
                    if (FileBase.currentFbId !== null || !tab.state.fbId) {
                        tab.state = {
                            fbId: FileBase.currentFbId,
                            fbName: FileBase.fbName || '',
                            fbLocalPath: FileBase.fbLocalPath || '',
                            fbDisplayPath: FileBase.fbDisplayPath || '',
                            fbPermission: FileBase.fbCurrentPermission || '',
                            fbSubdir: FileBase.fbLocalCurrentSubdir || '',
                            fbCurrentPath: FileBase.currentPath ? JSON.parse(JSON.stringify(FileBase.currentPath)) : []
                        };
                    }
                }
                break;
            case 'tools':
                var workdirEl = document.getElementById('workdir');
                var selDir = getSelectedDirectory();
                tab.state = {
                    currentTool: currentTool || 'to_compare',
                    workdirValue: workdirEl ? workdirEl.value : '',
                    fbId: workdirEl ? workdirEl.getAttribute('data-fb-id') : null,
                    fbSubdir: workdirEl ? workdirEl.getAttribute('data-fb-subdir') : '',
                    selectedFiles: getCheckedFiles()
                };
                break;
        }
    },

    _findById: function(id) {
        for (var i = 0; i < this.tabs.length; i++) {
            if (this.tabs[i].id === id) return this.tabs[i];
        }
        return null;
    },

    _renderBar: function() {
        var left = document.getElementById('header-left');
        var center = document.getElementById('header-center');
        var right = document.getElementById('header-right');
        if (!left || !center || !right) return;

        left.innerHTML = '<button class="tab-collapse-btn" onclick="toggleSidebarCollapse()" title="折叠/展开侧边栏"></button>';

        var centerHtml = '';
        for (var i = 0; i < this.tabs.length; i++) {
            var t = this.tabs[i];
            var isActive = t.id === this.activeTabId;
            var cls = 'tab-item' + (isActive ? ' active' : '');
            var closeBtn = '<span class="tab-close" onclick="event.stopPropagation();tabManager.closeTab(\'' + escapeJsForHtmlAttr(t.id) + '\')">✕</span>';
            centerHtml += '<div class="' + cls + '" onclick="tabManager.switchTab(\'' + escapeJsForHtmlAttr(t.id) + '\')" title="' + this._getTabTitle(t) + '">' +
                this._getTabIcon(t.type) +
                '<span>' + this._getTabTitle(t) + '</span>' +
                closeBtn +
                '</div>';
        }
        centerHtml += '<button class="tab-add-btn" onclick="tabManager.createTab(\'home\')" title="新建标签页">+</button>';
        center.innerHTML = centerHtml;

        right.innerHTML =
            '<button class="tab-win-btn" onclick="windowMinimize()" title="最小化">' +
            '<svg width="12" height="12" viewBox="0 0 12 12"><line x1="2" y1="6" x2="10" y2="6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></button>' +
            '<button class="tab-win-btn" onclick="windowMaximizeRestore()" title="最大化">' +
            '<svg width="12" height="12" viewBox="0 0 12 12"><rect x="2" y="2" width="8" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.2"/></svg></button>' +
            '<button class="tab-win-btn tab-win-close" onclick="windowClose()" title="关闭">' +
            '<svg width="12" height="12" viewBox="0 0 12 12"><line x1="2" y1="2" x2="10" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><line x1="10" y1="2" x2="2" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></button>';
    },

    _renderContent: async function(id) {
        var tab = this._findById(id);
        if (!tab) return;

        var mc = document.getElementById('main-content');
        if (!mc) return;
        mc.innerHTML = '';

        this._updateSidebar(tab.type === 'home' ? 'home' : tab.type);

        switch (tab.type) {
            case 'home': this._renderHome(tab, mc); break;
            case 'chat': this._renderChat(tab, mc); break;
            case 'fb': await this._renderFb(tab, mc); break;
            case 'tools': this._renderTools(tab, mc); break;
        }
    },

    _renderHome: function(tab, container) {
        // 渲染 KB 会话界面作为首页
        var contentDiv = document.createElement('div');
        contentDiv.id = 'content-view';
        contentDiv.style.cssText = 'height:100%;min-height:400px;display:flex;flex-direction:column;';
        container.appendChild(contentDiv);

        var self = this;
            var loadKb = function() {
                if (typeof WikiKnowledge !== 'undefined') {
                    // 清空消息，避免历史消息残留
                    WikiKnowledge.messages = [];
                    if (tab.state && tab.state.sessionId) {
                        sessionStorage.setItem('kb_session_id', tab.state.sessionId);
                    } else {
                        sessionStorage.removeItem('kb_session_id');
                        WikiKnowledge.sessionId = null;
                    }
                    WikiKnowledge.init();
                }
            };
        if (typeof WikiKnowledge !== 'undefined') {
            loadKb();
        } else {
            _loadScript('js/kb.js', function() {
                setTimeout(loadKb, 200);
            });
        }
    },

    _renderChat: function(tab, container) {
        // 会话标签：与首页相同，渲染 KB 会话界面
        this._renderHome(tab, container);
    },

    _renderFb: async function(tab, container) {
        var contentDiv = document.createElement('div');
        contentDiv.id = 'content-view';
        contentDiv.style.cssText = 'height:100%;min-height:400px;display:flex;flex-direction:column;';
        container.appendChild(contentDiv);

        // 恢复 FB 状态
        if (tab.state && tab.state.fbId) {
            localStorage.setItem('docflow_current_fb_id', tab.state.fbId);
            localStorage.setItem('docflow_current_fb_name', tab.state.fbName || '');
            localStorage.setItem('docflow_current_fb_local_path', tab.state.fbLocalPath || '');
            localStorage.setItem('docflow_current_fb_display_path', tab.state.fbDisplayPath || '');
            localStorage.setItem('docflow_current_fb_permission', tab.state.fbPermission || 'view');
            localStorage.setItem('docflow_current_subdir', tab.state.fbSubdir || '');
        } else {
            localStorage.removeItem('docflow_current_fb_id');
            localStorage.removeItem('docflow_current_subdir');
        }

        var self = this;
        _loadScript('js/fb.js', function() {
            if (typeof FileBase !== 'undefined') {
                if (tab.state && tab.state.fbId) {
                    FileBase.currentFbId = tab.state.fbId;
                    FileBase.fbName = tab.state.fbName || '';
                    FileBase.fbLocalPath = tab.state.fbLocalPath || '';
                    FileBase.fbDisplayPath = tab.state.fbDisplayPath || '';
                    FileBase.fbCurrentPermission = tab.state.fbPermission || 'view';
                    FileBase.fbCanEdit = tab.state.fbPermission === 'edit' || tab.state.fbPermission === 'manage';
                    FileBase.fbCanManage = tab.state.fbPermission === 'manage';
                    FileBase.fbLocalCurrentSubdir = tab.state.fbSubdir || '';
                    FileBase.fbCategoryTree = null;
                    FileBase.fbTreeLoaded = false;
                    if (tab.state.fbCurrentPath && tab.state.fbCurrentPath.length > 0) {
                        FileBase.currentPath = JSON.parse(JSON.stringify(tab.state.fbCurrentPath));
                    }
                    FileBase.init();
                } else {
                    // 检查 localStorage 中是否有定位信息（如从知识库右键"定位到文件库"进入）
                    var storedFbId = localStorage.getItem('docflow_current_fb_id');
                    if (storedFbId) {
                        // 从文件库列表 API 获取文件库信息
                        fetch('/api/fb/list').then(function(resp) { return resp.json(); }).then(function(data) {
                            if (data.success && data.kbs) {
                                var kb = data.kbs.find(function(k) { return k.id === storedFbId; });
                                if (kb) {
                                    FileBase.currentFbId = kb.id;
                                    FileBase.fbName = kb.name || '';
                                    FileBase.fbLocalPath = kb.local_path || '';
                                    FileBase.fbDisplayPath = kb.display_path || '';
                                    FileBase.fbCurrentPermission = kb.permission || 'view';
                                    FileBase.fbCanEdit = kb.permission === 'edit' || kb.permission === 'manage';
                                    FileBase.fbCanManage = kb.permission === 'manage';
                                    FileBase.fbLocalCurrentSubdir = localStorage.getItem('docflow_current_subdir') || '';
                                    FileBase.fbCategoryTree = null;
                                    FileBase.fbTreeLoaded = false;
                                } else {
                                    FileBase.currentFbId = null;
                                    FileBase.fbName = '';
                                    FileBase.fbLocalPath = '';
                                    FileBase.fbDisplayPath = '';
                                    FileBase.fbCurrentPermission = 'view';
                                    FileBase.fbCanEdit = false;
                                    FileBase.fbCanManage = false;
                                    FileBase.fbLocalCurrentSubdir = '';
                                }
                            } else {
                                FileBase.currentFbId = null;
                                FileBase.fbName = '';
                                FileBase.fbLocalPath = '';
                                FileBase.fbDisplayPath = '';
                                FileBase.fbCurrentPermission = 'view';
                                FileBase.fbCanEdit = false;
                                FileBase.fbCanManage = false;
                                FileBase.fbLocalCurrentSubdir = '';
                            }
                            FileBase.init();
                        }).catch(function(e) {
                            console.error('[FB] Failed to restore fb state from localStorage:', e);
                            FileBase.currentFbId = null;
                            FileBase.fbName = '';
                            FileBase.fbLocalPath = '';
                            FileBase.fbDisplayPath = '';
                            FileBase.fbCurrentPermission = 'view';
                            FileBase.fbCanEdit = false;
                            FileBase.fbCanManage = false;
                            FileBase.fbLocalCurrentSubdir = '';
                            FileBase.init();
                        });
                    } else {
                        FileBase.currentFbId = null;
                        FileBase.fbName = '';
                        FileBase.fbLocalPath = '';
                        FileBase.fbDisplayPath = '';
                        FileBase.fbCurrentPermission = 'view';
                        FileBase.fbCanEdit = false;
                        FileBase.fbCanManage = false;
                        FileBase.fbLocalCurrentSubdir = '';
                        FileBase.init();
                    }
                }
            }
        });
    },

    _renderTools: function(tab, container) {
        // 渲染工具页面
        container.innerHTML =
            '<div class="container" id="tools-view">' +
            '<div class="card">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #e94560;padding-bottom:6px;margin-bottom:10px">' +
            '<h2 style="margin:0;border:none;padding:0">选择功能</h2>' +
            '<button onclick="openConfig()" title="配置" style="background:none;border:none;cursor:pointer;color:#888;padding:4px 6px;border-radius:4px;display:flex;align-items:center" onmouseover="this.style.background=\'#e5e5e5\'" onmouseout="this.style.background=\'none\'">' +
            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>' +
            '</button></div>' +
            '<div class="tools-grid">' +
            '<div class="tool-item" onclick="selectTool(\'to_docx\')">' +
            '<div class="icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#2b5797" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg></div>' +
            '<div class="name">批量提取</div><div class="desc">PDF/TXT → DOCX</div></div>' +
            '<div class="tool-item" onclick="selectTool(\'to_index\')">' +
            '<div class="icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#217346" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="3" x2="9" y2="21"/></svg></div>' +
            '<div class="name">构建索引</div><div class="desc">目录 → Excel索引表</div></div>' +
            '<div class="tool-item" onclick="selectTool(\'to_compare\')">' +
            '<div class="icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#d24726" stroke-width="1.5"><rect x="2" y="4" width="9" height="16" rx="1"/><rect x="13" y="4" width="9" height="16" rx="1"/><line x1="7" y1="9" x2="7" y2="16"/><line x1="18" y1="8" x2="18" y2="14"/></svg></div>' +
            '<div class="name">文档比较</div><div class="desc">对比"原稿"和"终稿"</div></div>' +
            '<div class="tool-item" onclick="selectTool(\'to_pdf\')">' +
            '<div class="icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#b30b00" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><text x="12" y="18" text-anchor="middle" font-size="7" font-weight="bold" fill="#b30b00">PDF</text></svg></div>' +
            '<div class="name">批量转化</div><div class="desc">DOCX → PDF</div></div>' +
            '<div class="tool-item" onclick="selectTool(\'to_pageNum\')">' +
            '<div class="icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#563d7c" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><text x="12" y="18" text-anchor="middle" font-size="8" font-weight="bold" fill="#563d7c">#</text></svg></div>' +
            '<div class="name">添加页码</div><div class="desc">批量添加页码</div></div>' +
            '<div class="tool-item" onclick="selectTool(\'to_redhead\')">' +
            '<div class="icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#e94560" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/><circle cx="12" cy="12" r="4" fill="#e94560" fill-opacity="0.2"/></svg></div>' +
            '<div class="name">文件套红</div><div class="desc">生成红头文件</div></div>' +
            '</div></div>' +
            '<div class="card" id="toolPanel" style="display:none">' +
            '<h2 id="toolTitle">功能名称</h2>' +
            '<div class="form-group" id="folderSelectGroup">' +
            '<div style="display:flex;gap:8px">' +
            '<input type="text" id="workdir" placeholder="选择本机目录或从文件库选择" readonly style="flex:1">' +
            '<button type="button" class="btn" id="selectFolderBtn" style="width:auto;padding:8px 12px" onclick="selectFolder()">本机选择</button>' +
            '<button type="button" class="btn" id="selectFromKbBtn" style="width:auto;padding:8px 12px" onclick="showKbSelector()">文件库</button>' +
            '</div></div>' +
            '<div id="filePanel" style="display:none">' +
            '<div style="margin-bottom:5px"><label id="fileLabel" style="margin:0">👇目录文件：</label></div>' +
            '<div class="file-row"><div id="leftList" class="file-list" style="flex:1"></div><div id="rightList" class="file-list" style="flex:1"></div></div>' +
            '</div>' +
            '<div style="display:flex;gap:8px;align-items:center">' +
            '<button class="btn" id="showFileListBtn" onclick="toggleFileList()" style="width:auto;padding:10px 16px;white-space:nowrap">📂 查看</button>' +
            '<button class="btn" id="openDirBtn" onclick="openWorkdir()" style="width:auto;padding:10px 16px;white-space:nowrap">📁 打开</button>' +
            '<button class="btn" onclick="runTool()" style="flex:1">执行</button></div>' +
            '<div id="fileListPanel" style="display:none;margin-top:8px"><div id="fileList" style="display:flex;flex-wrap:wrap;gap:4px"></div></div>' +
            '<p class="intro" id="toolIntro" style="margin-top:10px"></p></div>' +
            '<div id="result"></div></div>';

        // 恢复工具状态
        var savedTool = (tab.state && tab.state.currentTool) || 'to_compare';
        if (tab.state && tab.state.workdirValue) {
            var wd = document.getElementById('workdir');
            if (wd) {
                wd.value = tab.state.workdirValue;
                if (tab.state.fbId) {
                    wd.setAttribute('data-fb-id', tab.state.fbId);
                    wd.setAttribute('data-fb-subdir', tab.state.fbSubdir || '');
                }
            }
        }
        // 无 tab 状态时，从持久化配置恢复 last_workdir
        if (!tab.state || !tab.state.workdirValue) {
            var wd = document.getElementById('workdir');
            if (wd && typeof window.userConfig !== 'undefined' && window.userConfig && window.userConfig.last_workdir) {
                wd.value = window.userConfig.last_workdir;
                wd.removeAttribute('data-fb-id');
                wd.removeAttribute('data-fb-subdir');
            }
        }
        // 从右键菜单带入文件库路径
        var preselect = window._toolsPreselect;
        window._toolsPreselect = null;
        if (preselect && !tab.state.workdirValue) {
            var wd = document.getElementById('workdir');
            if (wd && preselect.type === 'kb' && preselect.kbId) {
                wd.value = preselect.name + (preselect.subdir ? '/' + preselect.subdir : '');
                wd.setAttribute('data-fb-id', preselect.kbId);
                wd.setAttribute('data-fb-subdir', preselect.subdir || '');
            }
        }
        selectTool(savedTool);

        // 绑定拖拽支持
        var wd = document.getElementById('workdir');
        if (wd) {
            wd.addEventListener('dragover', function(e) { e.preventDefault(); });
            wd.addEventListener('drop', function(e) { e.preventDefault(); });
        }
    },

    // ==================== 会话管理弹窗 ====================

    showSessions: async function() {
        var self = this;
        // 关闭可能存在的旧弹窗
        var oldOv = document.getElementById('fb-modal-overlay');
        if (oldOv) oldOv.remove();

        try {
            var resp = await apiFetch('/api/kb/sessions?limit=50', { method: 'GET' });
            var data = await resp.json();
        } catch (e) {
            showToast('加载历史会话失败', 'error');
            return;
        }

        var h = '<div class="fb-modal-overlay" id="fb-modal-overlay"><div class="fb-modal" style="max-width:580px">';
        h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">';
        h += '<h3 style="margin:0">历史会话</h3>';
        h += '<button onclick="tabManager.closeSessionsModal()" style="border:none;background:none;font-size:20px;cursor:pointer;color:#999;padding:0;line-height:1">✖</button>';
        h += '</div>';

        if (!data.success || !data.sessions || data.sessions.length === 0) {
            h += '<div style="text-align:center;padding:40px 0;color:#bbb;font-size:14px">暂无会话</div>';
        } else {
            h += '<div style="max-height:55vh;overflow-y:auto;margin:0 -24px;padding:0 24px">';
            for (var i = 0; i < data.sessions.length; i++) {
                var s = data.sessions[i];
                var isActive = (typeof WikiKnowledge !== 'undefined') && s.id === WikiKnowledge.sessionId;
                var timeStr = '';
                if (s.last_active) {
                    var d = new Date(s.last_active * 1000);
                    timeStr = d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
                }
                var escId = escapeJsForHtmlAttr(s.id);
                h += '<div style="display:flex;align-items:center;padding:8px 0;border-bottom:1px solid #f0f0f0;cursor:pointer" onclick="tabManager._onSessionClick(\'' + escId + '\')">';
                h += '<span style="margin-right:8px">💬</span>';
                h += '<div style="min-width:0;flex:1;font-size:13px">';
                h += '<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:' + (isActive ? '600' : '400') + '">' + (typeof WikiKnowledge !== 'undefined' ? WikiKnowledge._escapeHtml(s.title || '新对话') : s.title || '新对话') + '</div>';
                h += '<div style="font-size:11px;color:#888;margin-top:2px">' + timeStr + '</div>';
                h += '</div>';
                h += '<button onclick="event.stopPropagation(); tabManager._onDeleteSession(\'' + escId + '\')" style="padding:3px 10px;border:1px solid #ddd;background:#fff;color:#999;border-radius:4px;cursor:pointer;font-size:11px;transition:all 0.15s" onmouseover="this.style.color=\'#dc3545\';this.style.borderColor=\'#dc3545\'" onmouseout="this.style.color=\'#999\';this.style.borderColor=\'#ddd\'">删除</button>';
                h += '</div>';
            }
            h += '</div>';
        }

        h += '<div class="fb-modal-actions">';
        h += '<button class="fb-btn-cancel" onclick="tabManager.closeSessionsModal()">关闭</button>';
        h += '<button class="fb-btn-primary" onclick="tabManager._onClearAllSessions()">清除所有会话</button>';
        h += '</div></div></div>';

        document.body.insertAdjacentHTML('beforeend', h);
        requestAnimationFrame(function() { document.getElementById('fb-modal-overlay').classList.add('show'); });
        document.getElementById('fb-modal-overlay').addEventListener('click', function(e) {
            if (e.target.id === 'fb-modal-overlay') tabManager.closeSessionsModal();
        });
    },

    closeSessionsModal: function() {
        var ov = document.getElementById('fb-modal-overlay');
        if (ov) {
            ov.classList.remove('show');
            setTimeout(function() { if (ov.parentNode) ov.remove(); }, 200);
        }
    },

    _onSessionClick: function(sessionId) {
        if (typeof WikiKnowledge !== 'undefined') {
            WikiKnowledge.switchSession(sessionId);
            navigateTo('home');
        }
    },

    _onDeleteSession: function(sessionId) {
        var self = this;
        if (typeof WikiKnowledge !== 'undefined' && WikiKnowledge.sessionId === sessionId) {
            WikiKnowledge.sessionId = null;
            WikiKnowledge._saveSessionId();
            WikiKnowledge.messages = [];
        }
        apiFetch('/api/kb/session/' + sessionId, { method: 'DELETE' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                self.showSessions();
            } else {
                showToast('删除失败', 'error');
            }
        }).catch(function() {
            showToast('删除失败', 'error');
        });
    },

    _onClearAllSessions: function() {
        var self = this;
        showConfirm('确定要清除所有会话吗？此操作不可恢复！').then(function(ok) {
            if (!ok) return;
            apiFetch('/api/kb/sessions', { method: 'DELETE' }).then(function(resp) {
                return resp.json();
            }).then(function(data) {
                if (data.success) {
                    if (typeof WikiKnowledge !== 'undefined') {
                        WikiKnowledge.sessionId = null;
                        WikiKnowledge._saveSessionId();
                        WikiKnowledge.messages = [];
                        if (typeof WikiKnowledge._switchToInitial === 'function') {
                            WikiKnowledge._switchToInitial();
                        }
                    }
                    self.closeSessionsModal();
                } else {
                    showToast('清除失败', 'error');
                }
            }).catch(function() {
                showToast('清除失败', 'error');
            });
        });
    },

    _refreshSessionList: function() {
        var overlay = document.getElementById('fb-modal-overlay');
        if (overlay) {
            this.showSessions();
        }
    }
};

