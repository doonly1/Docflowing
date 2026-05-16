var WikiKnowledge = {
    messages: [],
    isLoading: false,
    sessionId: null,
    memoryUsage: null,

    init: function() {
        if (!document.getElementById('kb-messages')) {
            this._renderView();
            // 从 sessionStorage 恢复会话
            var savedId = sessionStorage.getItem('kb_session_id');
            if (savedId) {
                this._restoreSession(savedId);
            }
        }
        this._loadMemoryUsage();
    },

    _restoreSession: function(sessionId) {
        var self = this;
        self.sessionId = sessionId;
        apiFetch('/api/kb/session/' + sessionId, { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success && data.messages) {
                for (var i = 0; i < data.messages.length; i++) {
                    var m = data.messages[i];
                    var d = new Date(m.timestamp * 1000);
                    // 从非LLM的消息内容中提取 ## 标题，重建参考来源
                    var sources = [];
                    if (m.role === 'assistant' && m.content) {
                        var titleRegex = /^##\s+(.+)$/gm;
                        var match;
                        while ((match = titleRegex.exec(m.content)) !== null) {
                            var title = match[1].trim();
                            if (title) {
                                sources.push({ title: title, path: '' });
                            }
                        }
                    }
                    self.messages.push({
                        role: m.role,
                        content: m.content,
                        sources: sources.length > 0 ? sources : undefined,
                        time: d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
                    });
                }
                self._switchToActive();
                self._renderMessages();
            } else {
                // 会话已失效，清除存储
                sessionStorage.removeItem('kb_session_id');
                self.sessionId = null;
            }
        }).catch(function(e) {
            console.error('恢复会话失败:', e);
            sessionStorage.removeItem('kb_session_id');
            self.sessionId = null;
        });
    },

    _saveSessionId: function() {
        if (this.sessionId) {
            sessionStorage.setItem('kb_session_id', this.sessionId);
        } else {
            sessionStorage.removeItem('kb_session_id');
        }
    },

    _loadMemoryUsage: function() {
        var self = this;
        apiFetch('/api/kb/memory/prompt', { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success && data.usage_info) {
                self.memoryUsage = data.usage_info;
            }
        }).catch(function(e) {
            console.error('加载记忆使用情况失败:', e);
        });
    },

    sendMessage: function() {
        var inputEl = document.getElementById('kb-input');
        if (!inputEl) return;

        var content = inputEl.value.trim();
        if (!content || this.isLoading) return;

        var self = this;
        if (!this.sessionId) {
            this._createSession(function() {
                self._sendMessageInternal(content);
            });
            return;
        }
        this._sendMessageInternal(content);
    },

    _sendMessageInternal: function(content) {
        this._switchToActive();
        this.messages.push({
            role: 'user',
            content: content,
            time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
        });

        var inputEl = document.getElementById('kb-input');
        if (inputEl) {
            inputEl.value = '';
            inputEl.style.height = 'auto';
        }

        this._renderMessages();
        this._recordMessage('user', content);
        this._getAIResponse(content);
    },

    _createSession: function(callback) {
        var self = this;
        apiFetch('/api/kb/session/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                self.sessionId = data.session_id;
                self._saveSessionId();
            }
            if (callback) callback();
        }).catch(function(e) {
            console.error('创建会话失败:', e);
        });
    },

    _renderView: function() {
        var viewEl = document.getElementById('content-view');
        if (!viewEl) return;

        viewEl.innerHTML =
            '<div class="kb-chat-container" id="kb-container">' +
                // 右上角图标按钮
                '<div class="kb-chat-header-actions">' +
                    '<button onclick="WikiKnowledge.newSession()" title="新建会话" class="kb-header-btn primary">➕</button>' +
                    '<button onclick="WikiKnowledge.showSessions()" title="历史会话" class="kb-header-btn">💬</button>' +
                    '<button onclick="WikiKnowledge.showLLMSettings()" title="LLM 设置" class="kb-header-btn">⚙️</button>' +
                    '<div class="kb-header-more-wrapper">' +
                        '<button onclick="WikiKnowledge.toggleMoreMenu(event)" title="更多" class="kb-header-btn">···</button>' +
                        '<div class="kb-header-more-dropdown" id="kb-header-more-dropdown" style="display:none">' +
                            '<div class="kb-header-more-item" onclick="WikiKnowledge.showMemory();WikiKnowledge.toggleMoreMenu(event)">🧠 持久化记忆</div>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                // 头部（初始隐藏，对话后显示）
                '<div class="kb-chat-header" id="kb-header" style="display:none">' +
                '</div>' +
                // 消息区（初始隐藏）
                '<div class="kb-chat-messages" id="kb-messages" style="display:none">' +
                    '<div class="kb-chat-empty" id="kb-empty-state">' +
                        '<div class="icon">💬</div>' +
                        '<div class="title">开始对话</div>' +
                        '<div class="desc">与AI助手对话，它将基于记忆与技能持续进化</div>' +
                    '</div>' +
                '</div>' +
                // 初始居中区（移除快捷按钮）
                '<div class="kb-chat-initial-area" id="kb-initial-area">' +
                    '<div class="kb-chat-greeting-title">开始会话</div>' +
                    '<div class="kb-chat-greeting-desc">输入消息，检索与会话</div>' +
                '</div>' +
                // 输入区（始终在底部）
                '<div class="kb-chat-input-area">' +
                    '<div class="kb-chat-input-wrapper">' +
                        '<textarea id="kb-input" rows="1" placeholder="输入消息，开始对话..." onkeydown="WikiKnowledge.handleKeyDown(event)" oninput="WikiKnowledge.autoResize(this)"></textarea>' +
                        '<div class="kb-chat-input-actions">' +
                            '<button class="kb-chat-send-btn" onclick="WikiKnowledge.sendMessage()" title="发送">' +
                                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2L15 22L11 13L2 9L22 2Z"/></svg>' +
                            '</button>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="kb-sidebar-overlay" id="kb-sidebar-overlay" onclick="WikiKnowledge.closeSidebar()"></div>' +
            '<div class="kb-sidebar" id="kb-sidebar">' +
                '<div class="kb-sidebar-header">' +
                    '<h4 id="kb-sidebar-title">面板</h4>' +
                    '<button onclick="WikiKnowledge.closeSidebar()">&times;</button>' +
                '</div>' +
                '<div class="kb-sidebar-content" id="kb-sidebar-content"></div>' +
            '</div>';

        // 点击页面其他地方关闭更多下拉菜单
        if (!window._kbHeaderClickHandler) {
            window._kbHeaderClickHandler = true;
            document.addEventListener('click', function(e) {
                var dropdown = document.getElementById('kb-header-more-dropdown');
                if (!dropdown || dropdown.style.display === 'none') return;
                var wrapper = dropdown.closest('.kb-header-more-wrapper');
                if (wrapper && !wrapper.contains(e.target)) {
                    dropdown.style.display = 'none';
                }
            });
        }
    },

    _switchToActive: function() {
        var initialArea = document.getElementById('kb-initial-area');
        var header = document.getElementById('kb-header');
        var messages = document.getElementById('kb-messages');
        if (!initialArea) return;
        initialArea.style.display = 'none';
        if (header) header.style.display = '';
        if (messages) messages.style.display = 'flex';
    },

    _switchToInitial: function() {
        var initialArea = document.getElementById('kb-initial-area');
        var header = document.getElementById('kb-header');
        var messages = document.getElementById('kb-messages');
        if (!initialArea) return;
        initialArea.style.display = 'flex';
        if (header) header.style.display = 'none';
        if (messages) messages.style.display = 'none';
    },

    handleKeyDown: function(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendMessage();
        }
    },

    autoResize: function(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    },

    _getAIResponse: function(query) {
        var self = this;
        this.isLoading = true;

        var typingHtml =
            '<div class="kb-chat-message assistant" id="kb-typing">' +
                '<div class="kb-chat-message-avatar">🤖</div>' +
                '<div class="kb-chat-message-content">' +
                    '<div class="kb-chat-message-bubble">' +
                        '<div class="kb-chat-typing">' +
                            '<span>正在思考</span>' +
                            '<div class="kb-chat-typing-dots">' +
                                '<span></span><span></span><span></span>' +
                            '</div>' +
                        '</div>' +
                        '<div class="kb-chat-stop-btn-wrapper" style="margin-top:8px;text-align:center;">' +
                            '<button class="kb-chat-stop-btn" onclick="WikiKnowledge.stopResponse()" title="停止响应">' +
                                '<svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>' +
                                ' 停止' +
                            '</button>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>';

        var messagesEl = document.getElementById('kb-messages');
        if (messagesEl) {
            messagesEl.insertAdjacentHTML('beforeend', typingHtml);
            self._scrollToBottom();
        }

        var bodyData = { query: query, max_chars: 4000 };
        if (self.sessionId) {
            bodyData.session_id = self.sessionId;
        }

        apiFetch('/api/kb/agent/context', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyData)
        }).then(function(resp) {
            // 检查响应状态
            if (!resp.ok) {
                throw new Error('服务器错误: ' + resp.status);
            }
            // 检查响应类型
            var contentType = resp.headers.get('content-type');
            if (!contentType || contentType.indexOf('application/json') === -1) {
                return resp.text().then(function(text) {
                    throw new Error('服务器返回了非JSON响应: ' + text.substring(0, 100));
                });
            }
            return resp.json();
        }).then(function(data) {
            var typingEl = document.getElementById('kb-typing');
            if (typingEl) typingEl.remove();

            var answer = '';
            var interrupted = data.interrupted || false;
            if (data.success && data.context) {
                answer = self._generateAnswer(query, data.context, data.sources || [], data.llm_used);
            } else if (interrupted) {
                answer = data.context || '(已中断)';
            } else {
                answer = data.message || '';
            }

            if (data.session_id) {
                self.sessionId = data.session_id;
            }
            if (data.memory_usage) {
                self.memoryUsage = data.memory_usage;
            }

            self.messages.push({
                role: 'assistant',
                content: answer,
                sources: data.sources || [],
                interrupted: interrupted,
                time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
            });

            self._recordMessage('assistant', answer);
            self._renderMessages();
            self.isLoading = false;
        }).catch(function(e) {
            var typingEl = document.getElementById('kb-typing');
            if (typingEl) typingEl.remove();

            self.messages.push({
                role: 'assistant',
                content: '抱歉，发生了错误: ' + e.message + '。请稍后重试。',
                time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
            });

            self._renderMessages();
            self.isLoading = false;
        });
    },

    stopResponse: function() {
        var self = this;
        if (!self.sessionId) return;
        apiFetch('/api/kb/agent/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: self.sessionId })
        }).then(function(data) {
            console.log('停止信号已发送:', data);
        }).catch(function(e) {
            console.error('停止请求失败:', e);
        });
    },

    _recordMessage: function(role, content) {
        if (!this.sessionId) return;
        apiFetch('/api/kb/session/' + this.sessionId + '/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                role: role,
                content: content,
            })
        }).catch(function(e) {
            console.error('记录消息失败:', e);
        });
    },

    _generateAnswer: function(query, context, sources, llmUsed) {
        return context;
    },

    _renderMessages: function() {
        var messagesEl = document.getElementById('kb-messages');
        var emptyEl = document.getElementById('kb-empty-state');
        if (!messagesEl) return;

        this._allSources = [];

        if (this.messages.length === 0) {
            if (emptyEl) emptyEl.style.display = 'flex';
            return;
        }

        if (emptyEl) emptyEl.style.display = 'none';

        var html = '';
        for (var i = 0; i < this.messages.length; i++) {
            var msg = this.messages[i];
            var avatar = msg.role === 'user' ? '👤' : '🤖';
            var roleClass = msg.role;

            html +=
                '<div class="kb-chat-message ' + roleClass + '">' +
                    '<div class="kb-chat-message-avatar">' + avatar + '</div>' +
                    '<div class="kb-chat-message-content">' +
                        '<div class="kb-chat-message-bubble' + (msg.interrupted ? ' interrupted' : '') + '">' +
                            this._formatContent(msg.content) +
                            (msg.interrupted ? '<div class="kb-chat-interrupted-badge">⏹ 已中断</div>' : '') +
                        '</div>';

            if (msg.sources && msg.sources.length > 0) {
                html += '<div class="kb-chat-sources">' +
                    '<div class="kb-chat-sources-title">📚 参考来源</div>';
                for (var j = 0; j < msg.sources.length; j++) {
                    var src = msg.sources[j];
                    var srcIdx = this._allSources.length;
                    this._allSources.push(src);
                    html += '<div class="kb-chat-source-item">' +
                        '<span class="icon">📄</span>' +
                        '<a href="#" onclick="WikiKnowledge.viewSource(' + srcIdx + ');return false;">' + (src.title || src.path) + '</a>' +
                    '</div>';
                }
                html += '</div>';
            }

            html += '<div class="kb-chat-message-time">' + msg.time + '</div>' +
                    '</div>' +
                '</div>';
        }

        messagesEl.innerHTML = html;
        this._scrollToBottom();
    },

    _formatContent: function(content) {
        if (!content) return '';
        var escaped = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        escaped = escaped.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
        escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
        escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        // 转换 ## / ### 标题（需在 \n→<br> 之前处理）
        escaped = escaped.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>');
        escaped = escaped.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>');
        escaped = escaped.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>');
        escaped = escaped.replace(/\n/g, '<br>');

        // 恢复高亮标签，使 <mark> 被渲染为 HTML 元素
        escaped = escaped.replace(/&lt;mark&gt;/g, '<mark>').replace(/&lt;\/mark&gt;/g, '</mark>');

        return escaped;
    },

    _scrollToBottom: function() {
        var messagesEl = document.getElementById('kb-messages');
        if (messagesEl) {
            setTimeout(function() {
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }, 50);
        }
    },

    clearChat: function() {
        if (this.messages.length === 0) return;
        if (!confirm('确定要清空当前对话吗？')) return;

        if (this.sessionId) {
            apiFetch('/api/kb/session/' + this.sessionId, { method: 'DELETE' })
                .catch(function(e) { console.error('删除会话失败:', e); });
            this.sessionId = null;
            this._saveSessionId();
        }

        this.messages = [];
        this._renderMessages();

        var emptyEl = document.getElementById('kb-empty-state');
        if (emptyEl) emptyEl.style.display = 'flex';
    },

    newSession: function() {
        var self = this;
        this.closeSidebar();
        apiFetch('/api/kb/session/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                self.sessionId = data.session_id;
                self._saveSessionId();
            }
        }).catch(function(e) {
            console.error('创建会话失败:', e);
        });

        this.messages = [];
        this._switchToInitial();
    },

    viewSource: function(index) {
        var src = this._allSources[index];
        if (!src || !src.path) return;
        var fileName = src.path.split('/').pop();
        var ext = fileName.split('.').pop().toLowerCase();

        if (ext === 'docx') {
            this._previewDocxFile(src);
        } else if (ext === 'md' || ext === 'txt') {
            this._previewTextFile(src);
        } else if (ext === 'pdf') {
            this._previewPdfFile(src);
        } else if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) {
            this._previewImageFile(src);
        } else {
            if (src.fb_id && src.fb_path) {
                window.open('/api/fb/' + src.fb_id + '/local-files/open?path=' + encodeURIComponent(src.fb_path) + '&token=' + encodeURIComponent(authToken), '_blank');
            } else {
                window.open('/api/kb/files/' + encodeURIComponent(src.path) + '?token=' + encodeURIComponent(authToken), '_blank');
            }
        }
    },
    
    _previewDocxFile: async function(src) {
        var fileName = (src.fb_path || src.path).split('/').pop();
        var kbId = src.fb_id || (window.FileBase && FileBase.currentFbId) || 'default';
        var filePath = src.fb_path || src.path;
        
        var overlay = document.createElement('div');
        overlay.className = 'fb-docx-preview-overlay';
        overlay.innerHTML = 
            '<div class="fb-docx-preview-container">' +
            '<div class="fb-docx-preview-header">' +
            '<span>📄 ' + escapeHtmlText(fileName) + '</span>' +
            '<button onclick="WikiKnowledge._closePreview()">✖</button>' +
            '</div>' +
            '<div class="fb-docx-preview-content" id="preview-content">' +
            '<div style="text-align: center; padding: 40px; color: #999;">' +
            '<div style="font-size: 48px; margin-bottom: 12px;">📄</div>' +
            '<div>正在加载预览...</div>' +
            '</div>' +
            '</div>' +
            '</div>';
        document.body.appendChild(overlay);
        
        try {
            var res = await apiFetch('/api/fb/' + kbId + '/local-files/docx-preview?path=' + encodeURIComponent(filePath), { method: 'GET' });
            var data = await res.json();
            var contentEl = document.getElementById('preview-content');
            if (data.success) {
                contentEl.innerHTML = data.html || '<div style="text-align: center; padding: 40px; color: #999;">文件内容为空</div>';
            } else {
                contentEl.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">预览失败: ' + (data.message || '未知错误') + '</div>';
            }
        } catch (e) {
            var contentEl = document.getElementById('preview-content');
            contentEl.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">预览失败: ' + e.message + '</div>';
        }
    },
    
    _previewTextFile: async function(src) {
        var fileName = (src.fb_path || src.path).split('/').pop();
        var kbId = src.fb_id || (window.FileBase && FileBase.currentFbId) || 'default';
        var filePath = src.fb_path || src.path;
        
        var overlay = document.createElement('div');
        overlay.className = 'fb-docx-preview-overlay';
        overlay.innerHTML = 
            '<div class="fb-docx-preview-container">' +
            '<div class="fb-docx-preview-header">' +
            '<span>📄 ' + escapeHtmlText(fileName) + '</span>' +
            '<button onclick="WikiKnowledge._closePreview()">✖</button>' +
            '</div>' +
            '<div class="fb-docx-preview-content" id="preview-content">' +
            '<div style="text-align: center; padding: 40px; color: #999;">' +
            '<div style="font-size: 48px; margin-bottom: 12px;">📄</div>' +
            '<div>正在加载预览...</div>' +
            '</div>' +
            '</div>' +
            '</div>';
        document.body.appendChild(overlay);
        
        try {
            var apiUrl = src.fb_id
                ? '/api/fb/' + kbId + '/local-files/content?path=' + encodeURIComponent(filePath)
                : '/api/kb/files/' + encodeURIComponent(src.path);
            var res = await apiFetch(apiUrl, { method: 'GET' });
            var data = await res.json();
            var contentEl = document.getElementById('preview-content');
            if (data.success) {
                var content = escapeHtmlText(data.content || '');
                if (data.file_type === '.md') {
                    content = marked.parse(content);
                } else {
                    content = '<pre style="white-space: pre-wrap; word-break: break-all; font-family: monospace; font-size: 13px;">' + content + '</pre>';
                }
                contentEl.innerHTML = content || '<div style="text-align: center; padding: 40px; color: #999;">文件内容为空</div>';
            } else {
                contentEl.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">预览失败: ' + (data.message || '未知错误') + '</div>';
            }
        } catch (e) {
            var contentEl = document.getElementById('preview-content');
            contentEl.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">预览失败: ' + e.message + '</div>';
        }
    },
    
    _closePreview: function() {
        var overlay = document.querySelector('.fb-docx-preview-overlay');
        if (overlay) {
            overlay.remove();
        }
    },
    
    _previewPdfFile: function(src) {
        var fileName = (src.fb_path || src.path).split('/').pop();
        var kbId = src.fb_id || (window.FileBase && FileBase.currentFbId) || 'default';
        var filePath = src.fb_path || src.path;
        var fileUrl = '/api/fb/' + kbId + '/local-files/open?path=' + encodeURIComponent(filePath) + '&token=' + encodeURIComponent(authToken);
        
        var overlay = document.createElement('div');
        overlay.className = 'fb-docx-preview-overlay';
        overlay.innerHTML = 
            '<div class="fb-docx-preview-container">' +
            '<div class="fb-docx-preview-header">' +
            '<span>📄 ' + escapeHtmlText(fileName) + '</span>' +
            '<button onclick="WikiKnowledge._closePreview()">✖</button>' +
            '</div>' +
            '<div class="fb-docx-preview-content" style="padding:0">' +
            '<iframe src="' + fileUrl + '" style="width:100%;height:100%;min-height:500px;border:none;" title="' + escapeHtmlText(fileName) + '"></iframe>' +
            '</div>' +
            '</div>';
        document.body.appendChild(overlay);
    },
    
    _previewImageFile: function(src) {
        var fileName = (src.fb_path || src.path).split('/').pop();
        var kbId = src.fb_id || (window.FileBase && FileBase.currentFbId) || 'default';
        var filePath = src.fb_path || src.path;
        var fileUrl = '/api/fb/' + kbId + '/local-files/open?path=' + encodeURIComponent(filePath) + '&token=' + encodeURIComponent(authToken);
        
        var overlay = document.createElement('div');
        overlay.className = 'fb-docx-preview-overlay';
        overlay.innerHTML = 
            '<div class="fb-docx-preview-container">' +
            '<div class="fb-docx-preview-header">' +
            '<span>🖼️ ' + escapeHtmlText(fileName) + '</span>' +
            '<button onclick="WikiKnowledge._closePreview()">✖</button>' +
            '</div>' +
            '<div class="fb-docx-preview-content" style="padding:16px;text-align:center;background:#f8f9fa;">' +
            '<img src="' + fileUrl + '" alt="' + escapeHtmlText(fileName) + '" style="max-width:100%;max-height:70vh;object-contain;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.1);">' +
            '</div>' +
            '</div>';
        document.body.appendChild(overlay);
    },

    openSidebar: function(title, contentHtml) {
        var sidebar = document.getElementById('kb-sidebar');
        var overlay = document.getElementById('kb-sidebar-overlay');
        var titleEl = document.getElementById('kb-sidebar-title');
        var contentEl = document.getElementById('kb-sidebar-content');
        if (titleEl) titleEl.textContent = title;
        if (contentEl) contentEl.innerHTML = contentHtml;
        if (sidebar) sidebar.classList.add('open');
        if (overlay) overlay.classList.add('show');
    },

    closeSidebar: function() {
        var sidebar = document.getElementById('kb-sidebar');
        var overlay = document.getElementById('kb-sidebar-overlay');
        if (sidebar) sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('show');
    },

    toggleMoreMenu: function(e) {
        if (e) e.stopPropagation();
        var dropdown = document.getElementById('kb-header-more-dropdown');
        if (!dropdown) return;
        if (dropdown.style.display === 'none' || dropdown.style.display === '') {
            dropdown.style.display = 'block';
        } else {
            dropdown.style.display = 'none';
        }
    },

    showSessions: function() {
        var self = this;
        apiFetch('/api/kb/sessions?limit=50', { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (!data.success) {
                self.openSidebar('历史会话', '<div style="padding: 20px; text-align: center; color: #c00;">加载失败</div>');
                return;
            }

            var html = '<div style="padding: 12px 12px 0;">' +
            '</div>';

            if (!data.sessions || data.sessions.length === 0) {
                html += '<div style="padding: 40px 20px; text-align: center; color: #999;">暂无会话</div>';
            } else {
                for (var i = 0; i < data.sessions.length; i++) {
                    var s = data.sessions[i];
                    var isActive = s.id === self.sessionId;
                    var timeStr = '';
                    if (s.last_active) {
                        var d = new Date(s.last_active * 1000);
                        timeStr = d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
                    }
                    html += '<div class="kb-session-item' + (isActive ? ' active' : '') + '" onclick="WikiKnowledge.switchSession(\'' + s.id.replace(/'/g, "\\'") + '\')">' +
                        '<span class="icon">💬</span>' +
                        '<div style="flex: 1; min-width: 0;">' +
                            '<div class="title">' + self._escapeHtml(s.title || '新对话') + '</div>' +
                            '<div class="preview">' + self._escapeHtml(s.preview || '') + '</div>' +
                            '<div class="time">' + timeStr + '</div>' +
                        '</div>' +
                        '<button class="kb-session-delete-btn" onclick="event.stopPropagation(); WikiKnowledge.deleteSession(\'' + s.id.replace(/'/g, "\\'") + '\')" title="删除会话">🗑️</button>' +
                    '</div>';
                }
                html += '<div style="padding: 12px; border-top: 1px solid #eee; margin-top: 8px;">' +
                    '<button onclick="WikiKnowledge.clearAllSessions()" style="width:100%;padding:8px;border:1px solid #e74c3c;border-radius:6px;background:#fff;color:#e74c3c;cursor:pointer;font-size:13px;">🗑️ 清除所有会话</button>' +
                '</div>';
            }
            self.openSidebar('历史会话', html);
        }).catch(function(e) {
            self.openSidebar('历史会话', '<div style="padding: 20px; text-align: center; color: #c00;">加载失败: ' + self._escapeHtml(e.message) + '</div>');
        });
    },

    switchSession: function(sessionId) {
        this.sessionId = sessionId;
        this._saveSessionId();
        this.messages = [];
        this._switchToActive();
        var self = this;

        apiFetch('/api/kb/session/' + sessionId, { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success && data.messages) {
                for (var i = 0; i < data.messages.length; i++) {
                    var m = data.messages[i];
                    var d = new Date(m.timestamp * 1000);
                    self.messages.push({
                        role: m.role,
                        content: m.content,
                        time: d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
                    });
                }
                self._renderMessages();
            }
        }).catch(function(e) {
            console.error('加载会话失败:', e);
        });

        this.closeSidebar();
    },

    deleteSession: function(sessionId) {

        var self = this;
        apiFetch('/api/kb/session/' + sessionId, { method: 'DELETE' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                if (self.sessionId === sessionId) {
                    self.sessionId = null;
                    self._saveSessionId();
                    self.messages = [];
                    self._switchToInitial();
                    self._renderMessages();
                }
                self.showSessions();
            } else {
                alert('删除失败: ' + (data.error || '未知错误'));
            }
        }).catch(function(e) {
            alert('删除失败: ' + e.message);
        });
    },

    clearAllSessions: function() {
        if (!confirm('确定要清除所有会话吗？此操作不可恢复！')) return;

        var self = this;
        apiFetch('/api/kb/sessions', { method: 'DELETE' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                self.sessionId = null;
                self._saveSessionId();
                self.messages = [];
                self._switchToInitial();
                self._renderMessages();
                self.closeSidebar();
            } else {
                alert('清除失败: ' + (data.error || '未知错误'));
            }
        }).catch(function(e) {
            alert('清除失败: ' + e.message);
        });
    },

    showMemory: function() {
        var self = this;
        apiFetch('/api/kb/memory', { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (!data.success) {
                self.openSidebar('持久化记忆', '<div style="padding: 20px; text-align: center; color: #c00;">加载失败</div>');
                return;
            }

            var usage = data.usage_info || {};
            var memUsage = usage.memory || {};
            var userUsage = usage.user || {};

            var html = '<div class="kb-memory-usage">' +
                '<div class="kb-memory-usage-item">' +
                    '<div class="label">环境笔记 (MEMORY)</div>' +
                    '<div class="bar"><div class="bar-fill" style="width: ' + memUsage.pct + '%"></div></div>' +
                    '<div class="value">' + memUsage.current + ' / ' + memUsage.limit + ' 字符</div>' +
                '</div>' +
                '<div class="kb-memory-usage-item">' +
                    '<div class="label">用户画像 (USER)</div>' +
                    '<div class="bar"><div class="bar-fill" style="width: ' + userUsage.pct + '%"></div></div>' +
                    '<div class="value">' + userUsage.current + ' / ' + userUsage.limit + ' 字符</div>' +
                '</div>' +
            '</div>';

            html += '<h5 style="margin: 12px 0 8px; color: #666;">📝 环境笔记</h5>';
            if (data.memory && data.memory.memory && data.memory.memory.entries.length > 0) {
                for (var i = 0; i < data.memory.memory.entries.length; i++) {
                    html += '<div class="kb-memory-entry">' +
                        '<div class="target">MEMORY</div>' +
                        self._escapeHtml(data.memory.memory.entries[i]) +
                    '</div>';
                }
            } else {
                html += '<div style="padding: 12px; color: #999; font-size: 13px;">暂无笔记</div>';
            }

            html += '<h5 style="margin: 16px 0 8px; color: #666;">👤 用户画像</h5>';
            if (data.memory && data.memory.user && data.memory.user.entries.length > 0) {
                for (var i = 0; i < data.memory.user.entries.length; i++) {
                    html += '<div class="kb-memory-entry">' +
                        '<div class="target">USER</div>' +
                        self._escapeHtml(data.memory.user.entries[i]) +
                    '</div>';
                }
            } else {
                html += '<div style="padding: 12px; color: #999; font-size: 13px;">暂无画像</div>';
            }

            html += '<div class="kb-sidebar-input-area">' +
                '<select id="kb-memory-target" style="width: 100%; padding: 8px; border: 1px solid #e8e8e8; border-radius: 8px; margin-bottom: 8px; font-size: 13px;">' +
                    '<option value="memory">添加到环境笔记</option>' +
                    '<option value="user">添加到用户画像</option>' +
                '</select>' +
                '<textarea id="kb-memory-input" rows="3" placeholder="输入新的记忆条目..."></textarea>' +
                '<button onclick="WikiKnowledge.addMemory()">添加记忆</button>' +
            '</div>';

            self.openSidebar('🧠 持久化记忆', html);
        }).catch(function(e) {
            self.openSidebar('持久化记忆', '<div style="padding: 20px; text-align: center; color: #c00;">加载失败: ' + self._escapeHtml(e.message) + '</div>');
        });
    },

    addMemory: function() {
        var targetEl = document.getElementById('kb-memory-target');
        var inputEl = document.getElementById('kb-memory-input');
        if (!inputEl || !targetEl) return;

        var content = inputEl.value.trim();
        var target = targetEl.value;
        if (!content) return;

        var self = this;
        apiFetch('/api/kb/memory/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target: target, content: content })
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                inputEl.value = '';
                self._loadMemoryUsage();
                self.showMemory();
            } else {
                alert(data.error || '添加失败');
            }
        }).catch(function(e) {
            alert('添加失败: ' + e.message);
        });
    },

    showSkills: function() {
        var self = this;
        apiFetch('/api/kb/skills', { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (!data.success) {
                self.openSidebar('技能库', '<div style="padding: 20px; text-align: center; color: #c00;">加载失败</div>');
                return;
            }

            var html = '';
            if (!data.skills || data.skills.length === 0) {
                html = '<div style="padding: 40px 20px; text-align: center; color: #999;">暂无技能</div>';
            } else {
                for (var i = 0; i < data.skills.length; i++) {
                    var skill = data.skills[i];
                    var fm = skill.frontmatter || {};
                    var usage = skill.usage || {};
                    var stateClass = (usage.state || 'active');
                    var stateLabel = stateClass === 'active' ? '活跃' : stateClass === 'stale' ? '过期' : '已归档';

                    html += '<div class="kb-skill-item">' +
                        '<div class="name">' + self._escapeHtml(fm.name || skill.name) + '</div>' +
                        (fm.category ? '<div class="category">' + self._escapeHtml(fm.category) + '</div>' : '') +
                        '<div class="stats">' +
                            '<span>📈 使用 ' + (usage.use_count || 0) + ' 次</span>' +
                            '<span>👁 查看 ' + (usage.view_count || 0) + ' 次</span>' +
                        '</div>' +
                        '<div style="margin-top: 6px;"><span class="kb-skill-item state ' + stateClass + '">' + stateLabel + '</span></div>' +
                    '</div>';
                }
            }

            html += '<div class="kb-sidebar-input-area">' +
                '<textarea id="kb-skill-input" rows="5" placeholder="输入技能内容 (SKILL.md 格式)...\n\n---\nname: my-skill\ncategory: general\n---\n# 技能名称\n## 描述\n..."></textarea>' +
                '<button onclick="WikiKnowledge.createSkill()">创建技能</button>' +
            '</div>';

            self.openSidebar('📚 技能库', html);
        }).catch(function(e) {
            self.openSidebar('技能库', '<div style="padding: 20px; text-align: center; color: #c00;">加载失败: ' + self._escapeHtml(e.message) + '</div>');
        });
    },

    createSkill: function() {
        var inputEl = document.getElementById('kb-skill-input');
        if (!inputEl) return;

        var content = inputEl.value.trim();
        if (!content) return;

        var nameMatch = content.match(/^---\s*\n.*?name:\s*(\S+)/ms);
        var name = nameMatch ? nameMatch[1] : '';
        if (!name) {
            alert('技能内容必须包含 name 字段在前置元数据中');
            return;
        }

        var catMatch = content.match(/^---\s*\n.*?category:\s*(\S+)/ms);
        var category = catMatch ? catMatch[1] : null;

        var self = this;
        apiFetch('/api/kb/skills/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, content: content, category: category, created_by: 'user' })
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                inputEl.value = '';
                self.showSkills();
            } else {
                alert(data.error || '创建失败');
            }
        }).catch(function(e) {
            alert('创建失败: ' + e.message);
        });
    },

    _escapeHtml: function(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },

    // ==================== LLM 设置 ====================

    LLM_PROVIDERS: [
        { name: 'OpenAI', base_url: 'https://api.openai.com/v1', models: [] },
        { name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', models: [] },
        { name: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1', models: [] },
        { name: '硅基流动', base_url: 'https://api.siliconflow.cn/v1', models: [] },
        { name: '阿里百炼', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: [] },
        { name: 'Moonshot', base_url: 'https://api.moonshot.cn/v1', models: [] },
        { name: 'Groq', base_url: 'https://api.groq.com/openai/v1', models: [] },
        { name: '智谱', base_url: 'https://open.bigmodel.cn/api/paas/v4', models: [] },
        { name: '自定义', base_url: '', models: [] },
    ],

    showLLMSettings: function() {
        var self = this;
        apiFetch('/api/kb/llm-config', { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (!data.success) {
                self.openSidebar('LLM 设置', '<div style="padding: 20px; text-align: center; color: #c00;">加载配置失败</div>');
                return;
            }
            self._renderLLMSettings(data.config || {});
        }).catch(function(e) {
            self.openSidebar('LLM 设置', '<div style="padding: 20px; text-align: center; color: #c00;">加载失败: ' + self._escapeHtml(e.message) + '</div>');
        });
    },

    _renderLLMSettings: function(config) {
        var self = this;
        var enabled = config.enabled ? 'checked' : '';
        var apiKey = config.api_key || '';
        var baseUrl = config.base_url || '';
        var model = config.model || '';
        var temperature = config.temperature !== undefined ? config.temperature : 0.7;
        var maxTokens = config.max_tokens !== undefined ? config.max_tokens : 4096;

        // 根据 base_url 匹配提供商
        var matchedProvider = '';
        for (var i = 0; i < this.LLM_PROVIDERS.length; i++) {
            var p = this.LLM_PROVIDERS[i];
            if (p.base_url && baseUrl.indexOf(p.base_url) >= 0) {
                matchedProvider = p.name;
                break;
            }
        }

        var providerOptions = '';
        for (var i = 0; i < this.LLM_PROVIDERS.length; i++) {
            var p = this.LLM_PROVIDERS[i];
            var selected = (p.name === matchedProvider) ? 'selected' : '';
            providerOptions += '<option value="' + self._escapeHtml(p.name) + '" data-base_url="' + self._escapeHtml(p.base_url) + '" ' + selected + '>' + self._escapeHtml(p.name) + '</option>';
        }

        // 生成模型选项
        var modelOptions = '';
        if (matchedProvider) {
            var provider = null;
            for (var i = 0; i < this.LLM_PROVIDERS.length; i++) {
                if (this.LLM_PROVIDERS[i].name === matchedProvider) {
                    provider = this.LLM_PROVIDERS[i];
                    break;
                }
            }
            if (provider && provider.models.length > 0) {
                modelOptions += '<option value="">-- 选择模型 --</option>';
                for (var i = 0; i < provider.models.length; i++) {
                    var m = provider.models[i];
                    var sel = (m === model) ? 'selected' : '';
                    modelOptions += '<option value="' + self._escapeHtml(m) + '" ' + sel + '>' + self._escapeHtml(m) + '</option>';
                }
            }
        }
        if (!modelOptions) {
            modelOptions = '<option value="">-- 手动输入 --</option>';
        }

        var html =
            '<div style="padding: 16px;">' +
                '<div class="kb-settings-section">' +
                    '<label class="kb-settings-label">启用 LLM</label>' +
                    '<label class="kb-settings-toggle">' +
                        '<input type="checkbox" id="kb-llm-enabled" ' + enabled + '>' +
                        '<span class="kb-settings-toggle-slider"></span>' +
                    '</label>' +
                '</div>' +

                '<div class="kb-settings-section">' +
                    '<label class="kb-settings-label">模型提供商</label>' +
                    '<select id="kb-llm-provider" onchange="WikiKnowledge._onProviderChange()" style="width:100%;padding:8px;border:1px solid #d9d9d9;border-radius:6px;font-size:13px;">' +
                        providerOptions +
                    '</select>' +
                '</div>' +

                '<div class="kb-settings-section">' +
                    '<label class="kb-settings-label">API 地址</label>' +
                    '<input id="kb-llm-base-url" type="text" value="' + self._escapeHtml(baseUrl) + '" placeholder="https://api.openai.com/v1" style="width:100%;padding:8px;border:1px solid #d9d9d9;border-radius:6px;font-size:13px;box-sizing:border-box;">' +
                '</div>' +

                '<div class="kb-settings-section">' +
                    '<label class="kb-settings-label">API Key</label>' +
                    '<div style="display:flex;gap:8px;">' +
                        '<input id="kb-llm-api-key" type="text" value="' + self._escapeHtml(apiKey) + '" placeholder="sk-..." style="flex:1;padding:8px;border:1px solid #d9d9d9;border-radius:6px;font-size:13px;font-family:monospace;">' +
                        '<button onclick="WikiKnowledge._toggleApiKeyVisibility()" style="padding:8px 10px;border:1px solid #d9d9d9;border-radius:6px;background:#fff;cursor:pointer;font-size:14px;" title="切换可见性">👁</button>' +
                    '</div>' +
                '</div>' +

                '<div class="kb-settings-section">' +
                    '<label class="kb-settings-label">模型</label>' +
                    '<div style="display:flex;gap:8px;margin-bottom:8px;">' +
                        '<select id="kb-llm-model-select" onchange="WikiKnowledge._onModelSelectChange()" style="flex:1;padding:8px;border:1px solid #d9d9d9;border-radius:6px;font-size:13px;">' +
                            '<option value="">-- 手动输入 --</option>' +
                        '</select>' +
                        '<button onclick="WikiKnowledge._fetchModels()" id="kb-llm-fetch-models" style="padding:8px 12px;border:1px solid #4a90d9;border-radius:6px;background:white;color:#4a90d9;cursor:pointer;font-size:12px;white-space:nowrap;">🔄 获取列表</button>' +
                    '</div>' +
                    '<input id="kb-llm-model-input" type="text" value="' + self._escapeHtml(model) + '" placeholder="输入模型名称，如: gpt-4o-mini" style="width:100%;padding:8px;border:1px solid #d9d9d9;border-radius:6px;font-size:13px;box-sizing:border-box;">' +
                    '<div id="kb-llm-model-status" style="margin-top:4px;font-size:11px;color:#999;"></div>' +
                '</div>' +

                '<div class="kb-settings-section">' +
                    '<label class="kb-settings-label">温度: <span id="kb-llm-temp-value">' + temperature + '</span></label>' +
                    '<input id="kb-llm-temperature" type="range" min="0" max="2" step="0.1" value="' + temperature + '" oninput="WikiKnowledge._updateTempValue(this.value)" style="width:100%;">' +
                    '<div style="display:flex;justify-content:space-between;font-size:11px;color:#999;"><span>精确 (0)</span><span>创意 (2)</span></div>' +
                '</div>' +

                '<div class="kb-settings-section">' +
                    '<label class="kb-settings-label">最大 Token</label>' +
                    '<input id="kb-llm-max-tokens" type="number" value="' + maxTokens + '" min="1" max="131072" style="width:100%;padding:8px;border:1px solid #d9d9d9;border-radius:6px;font-size:13px;box-sizing:border-box;">' +
                '</div>' +

                '<div style="display:flex;gap:8px;margin-top:20px;">' +
                    '<button onclick="WikiKnowledge.testLLMConnection()" id="kb-llm-test-btn" style="flex:1;padding:10px;border:1px solid #4a90d9;border-radius:8px;background:white;color:#4a90d9;cursor:pointer;font-size:13px;">🔌 测试连接</button>' +
                    '<button onclick="WikiKnowledge.saveLLMConfig()" id="kb-llm-save-btn" style="flex:1;padding:10px;border:none;border-radius:8px;background:#4a90d9;color:white;cursor:pointer;font-size:13px;">💾 保存设置</button>' +
                '</div>' +
                '<div id="kb-llm-status" style="margin-top:12px;font-size:13px;text-align:center;"></div>' +
            '</div>';

        self.openSidebar('⚙️ LLM 设置', html);
    },

    _onProviderChange: function() {
        var providerSelect = document.getElementById('kb-llm-provider');
        var baseUrlInput = document.getElementById('kb-llm-base-url');
        var modelSelect = document.getElementById('kb-llm-model-select');
        var modelInput = document.getElementById('kb-llm-model-input');
        if (!providerSelect || !baseUrlInput) return;

        var name = providerSelect.value;
        for (var i = 0; i < this.LLM_PROVIDERS.length; i++) {
            var p = this.LLM_PROVIDERS[i];
            if (p.name === name) {
                baseUrlInput.value = p.base_url;
                // 清空模型下拉
                modelSelect.innerHTML = '<option value="">-- 手动输入 --</option>';
                modelSelect.style.display = '';
                modelInput.style.display = 'none';
                modelInput.value = '';

                // 自动获取模型列表
                if (p.base_url) {
                    this._fetchModels();
                }
                break;
            }
        }
    },

    _fetchModels: function() {
        var baseUrlInput = document.getElementById('kb-llm-base-url');
        var apiKeyInput = document.getElementById('kb-llm-api-key');
        var modelSelect = document.getElementById('kb-llm-model-select');
        var modelInput = document.getElementById('kb-llm-model-input');
        var statusDiv = document.getElementById('kb-llm-model-status');
        var fetchBtn = document.getElementById('kb-llm-fetch-models');

        if (!baseUrlInput || !baseUrlInput.value.trim()) {
            alert('请先填写 API 地址');
            return;
        }

        var baseUrl = baseUrlInput.value.trim();
        var apiKey = apiKeyInput ? apiKeyInput.value.trim() : '';

        // 显示加载状态
        if (fetchBtn) {
            fetchBtn.disabled = true;
            fetchBtn.textContent = '⏳ 获取中...';
        }
        if (statusDiv) {
            statusDiv.style.color = '#999';
            statusDiv.textContent = '正在获取模型列表...';
        }

        var self = this;
        // 使用原生 fetch，不发送认证头，避免 401 触发退出登录
        var reqBody = JSON.stringify({ base_url: baseUrl, api_key: apiKey });
        console.log('[DEBUG] _fetchModels 请求:', reqBody);
        fetch('/api/kb/llm-models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: reqBody
        }).then(function(resp) {
            console.log('[DEBUG] _fetchModels 响应状态:', resp.status);
            if (!resp.ok) {
                return resp.json().then(function(data) {
                    console.log('[DEBUG] _fetchModels 错误响应:', data);
                    throw new Error(data.message || 'HTTP ' + resp.status);
                }).catch(function(err) {
                    if (err.message && err.message.startsWith('[DEBUG]')) throw err;
                    throw new Error('HTTP ' + resp.status);
                });
            }
            return resp.json();
        }).then(function(data) {
            if (data.success && data.models && data.models.length > 0) {
                // 更新模型下拉列表
                var opts = '<option value="">-- 选择模型 --</option>';
                for (var i = 0; i < data.models.length; i++) {
                    opts += '<option value="' + self._escapeHtml(data.models[i]) + '">' + self._escapeHtml(data.models[i]) + '</option>';
                }
                modelSelect.innerHTML = opts;
                modelSelect.style.display = '';
                if (modelInput) modelInput.style.display = 'none';

                if (statusDiv) {
                    statusDiv.style.color = '#52c41a';
                    statusDiv.textContent = '✓ 成功获取 ' + data.models.length + ' 个模型';
                }
            } else {
                // 获取失败，允许手动输入
                modelSelect.style.display = 'none';
                if (modelInput) modelInput.style.display = '';
                if (statusDiv) {
                    statusDiv.style.color = '#faad14';
                    statusDiv.textContent = '获取失败: ' + (data.message || '未知错误') + '，请手动输入模型名称';
                }
            }
        }).catch(function(e) {
            // 获取失败，允许手动输入
            modelSelect.style.display = 'none';
            if (modelInput) modelInput.style.display = '';
            if (statusDiv) {
                statusDiv.style.color = '#f5222d';
                statusDiv.textContent = '获取失败: ' + e.message + '，请手动输入模型名称';
            }
        }).finally(function() {
            // 恢复按钮状态
            if (fetchBtn) {
                fetchBtn.disabled = false;
                fetchBtn.textContent = '🔄 获取列表';
            }
        });
    },

    _onModelSelectChange: function() {
        var select = document.getElementById('kb-llm-model-select');
        var input = document.getElementById('kb-llm-model-input');
        if (select && input) {
            input.value = select.value;
        }
    },

    _toggleApiKeyVisibility: function() {
        var input = document.getElementById('kb-llm-api-key');
        if (input) {
            input.type = (input.type === 'password') ? 'text' : 'password';
        }
    },

    _updateTempValue: function(val) {
        var span = document.getElementById('kb-llm-temp-value');
        if (span) span.textContent = val;
    },

    testLLMConnection: function() {
        var self = this;
        var btn = document.getElementById('kb-llm-test-btn');
        var statusEl = document.getElementById('kb-llm-status');
        if (!btn || !statusEl) return;

        btn.disabled = true;
        btn.textContent = '⏳ 测试中...';
        statusEl.innerHTML = '<span style="color:#999;">正在测试连接...</span>';

        var llm = self._collectLLMFormData();
        if (!llm.api_key || !llm.base_url || !llm.model) {
            statusEl.innerHTML = '<span style="color:#c00;">请先填写 API Key、API 地址和模型名称</span>';
            btn.disabled = false;
            btn.textContent = '🔌 测试连接';
            return;
        }

        apiFetch('/api/kb/llm-test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ llm: llm })
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                statusEl.innerHTML = '<span style="color:#090;">✓ ' + self._escapeHtml(data.message) + '</span>';
            } else {
                statusEl.innerHTML = '<span style="color:#c00;">✗ ' + self._escapeHtml(data.message) + '</span>';
            }
        }).catch(function(e) {
            statusEl.innerHTML = '<span style="color:#c00;">请求失败: ' + self._escapeHtml(e.message) + '</span>';
        }).finally(function() {
            btn.disabled = false;
            btn.textContent = '🔌 测试连接';
        });
    },

    saveLLMConfig: function() {
        var self = this;
        var btn = document.getElementById('kb-llm-save-btn');
        var statusEl = document.getElementById('kb-llm-status');
        if (!btn || !statusEl) return;

        btn.disabled = true;
        btn.textContent = '⏳ 保存中...';
        statusEl.innerHTML = '';

        var llm = self._collectLLMFormData();

        apiFetch('/api/kb/llm-config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ llm: llm })
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success) {
                statusEl.innerHTML = '<span style="color:#090;">✓ 配置已保存！</span>';
                // 刷新 LLM 可用状态
                self._checkLLMStatus();
            } else {
                statusEl.innerHTML = '<span style="color:#c00;">✗ ' + self._escapeHtml(data.message) + '</span>';
            }
        }).catch(function(e) {
            statusEl.innerHTML = '<span style="color:#c00;">保存失败: ' + self._escapeHtml(e.message) + '</span>';
        }).finally(function() {
            btn.disabled = false;
            btn.textContent = '💾 保存设置';
        });
    },

    _collectLLMFormData: function() {
        return {
            enabled: document.getElementById('kb-llm-enabled') ? document.getElementById('kb-llm-enabled').checked : false,
            base_url: document.getElementById('kb-llm-base-url') ? document.getElementById('kb-llm-base-url').value.trim() : '',
            api_key: document.getElementById('kb-llm-api-key') ? document.getElementById('kb-llm-api-key').value.trim() : '',
            model: document.getElementById('kb-llm-model-input') ? document.getElementById('kb-llm-model-input').value.trim() : '',
            temperature: document.getElementById('kb-llm-temperature') ? parseFloat(document.getElementById('kb-llm-temperature').value) : 0.7,
            max_tokens: document.getElementById('kb-llm-max-tokens') ? parseInt(document.getElementById('kb-llm-max-tokens').value) || 4096 : 4096,
        };
    },

    _checkLLMStatus: function() {
        // 刷新后重新检查 LLM 可用性（下次对话时会自动检查）
    }
};

function escapeHtmlForWiki(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
