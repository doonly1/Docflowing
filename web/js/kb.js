var WikiKnowledge = {
    messages: [],
    isLoading: false,
    wikiName: 'AI助手',
    sessionId: null,
    memoryUsage: null,

    init: function() {
        this._renderView();
        this._loadInfo();
        this._loadMemoryUsage();
    },

    _loadInfo: function() {
        var self = this;
        apiFetch('/api/kb/info', { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (data.success && data.info) {
                self.wikiName = data.info.name || 'AI助手';
                var titleEl = document.getElementById('kb-chat-title');
                if (titleEl) titleEl.textContent = self.wikiName;
            }
        }).catch(function(e) {
            console.error('加载知识库信息失败:', e);
        });
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
            }
            if (callback) callback();
        }).catch(function(e) {
            console.error('创建会话失败:', e);
        });
    },

    _renderView: function() {
        var viewEl = document.getElementById('kb-view');
        if (!viewEl) return;

        viewEl.innerHTML =
            '<div class="kb-chat-container">' +
                '<div class="kb-chat-header">' +
                    '<div class="kb-chat-header-title">' +
                        '<span class="icon">✨</span>' +
                        '<h3 id="kb-chat-title">AI助手</h3>' +
                    '</div>' +
                    '<div class="kb-chat-header-actions">' +
                        '<button onclick="WikiKnowledge.newSession()" title="新建会话">➕ 新对话</button>' +
                        '<button onclick="WikiKnowledge.showSessions()" title="历史会话">💬 会话</button>' +
                        '<button onclick="WikiKnowledge.showMemory()" title="持久化记忆">🧠 记忆</button>' +
                        '<button onclick="WikiKnowledge.showSkills()" title="技能库">📚 技能</button>' +
                    '</div>' +
                '</div>' +
                '<div class="kb-chat-messages" id="kb-messages">' +
                    '<div class="kb-chat-empty" id="kb-empty-state">' +
                        '<div class="icon">💬</div>' +
                        '<div class="title">开始对话</div>' +
                        '<div class="desc">与AI助手对话，它将基于记忆与技能持续进化</div>' +
                    '</div>' +
                '</div>' +
                '<div class="kb-chat-input-area">' +
                    '<div class="kb-chat-input-wrapper">' +
                        '<textarea id="kb-input" rows="1" placeholder="输入消息，与AI助手对话..." onkeydown="WikiKnowledge.handleKeyDown(event)" oninput="WikiKnowledge.autoResize(this)"></textarea>' +
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
            return resp.json();
        }).then(function(data) {
            var typingEl = document.getElementById('kb-typing');
            if (typingEl) typingEl.remove();

            var answer = '';
            if (data.success && data.context) {
                answer = self._generateAnswer(query, data.context, data.sources || []);
            } else {
                answer = '抱歉，我在知识库中没有找到相关信息。您可以尝试换一种问法，或者向知识库中添加更多内容。';
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

    _generateAnswer: function(query, context, sources) {
        var answer = '根据您的知识库内容，我找到了相关信息：\n\n';
        answer += context;
        return answer;
    },

    _renderMessages: function() {
        var messagesEl = document.getElementById('kb-messages');
        var emptyEl = document.getElementById('kb-empty-state');
        if (!messagesEl) return;

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
                        '<div class="kb-chat-message-bubble">' +
                            this._formatContent(msg.content) +
                        '</div>';

            if (msg.sources && msg.sources.length > 0) {
                html += '<div class="kb-chat-sources">' +
                    '<div class="kb-chat-sources-title">📚 参考来源</div>';
                for (var j = 0; j < msg.sources.length; j++) {
                    var src = msg.sources[j];
                    html += '<div class="kb-chat-source-item">' +
                        '<span class="icon">📄</span>' +
                        '<a href="#" onclick="WikiKnowledge.viewSource(\'' + (src.path || '').replace(/'/g, "\\'") + '\');return false;">' + (src.title || src.path) + '</a>' +
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
        escaped = escaped.replace(/\n/g, '<br>');

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
        }

        this.messages = [];
        this._renderMessages();

        var emptyEl = document.getElementById('kb-empty-state');
        if (emptyEl) emptyEl.style.display = 'flex';
    },

    newSession: function() {
        this.sessionId = null;
        this.messages = [];
        this._renderMessages();

        var emptyEl = document.getElementById('kb-empty-state');
        if (emptyEl) emptyEl.style.display = 'flex';
    },

    viewSource: function(path) {
        if (!path) return;
        var fileName = path.split('/').pop().replace('.md', '');
        alert('查看文件: ' + fileName + '\n路径: ' + path);
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

    showSessions: function() {
        var self = this;
        apiFetch('/api/kb/sessions?limit=50', { method: 'GET' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            if (!data.success) {
                self.openSidebar('历史会话', '<div style="padding: 20px; text-align: center; color: #c00;">加载失败</div>');
                return;
            }

            var html = '<div style="padding: 12px; border-bottom: 1px solid #eee;">' +
                '<button onclick="WikiKnowledge.newSession(); WikiKnowledge.closeSidebar();" style="width: 100%; padding: 10px; background: #4a90d9; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px;">➕ 新建会话</button>' +
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
                    '</div>';
                }
            }
            self.openSidebar('历史会话', html);
        }).catch(function(e) {
            self.openSidebar('历史会话', '<div style="padding: 20px; text-align: center; color: #c00;">加载失败: ' + self._escapeHtml(e.message) + '</div>');
        });
    },

    switchSession: function(sessionId) {
        this.sessionId = sessionId;
        this.messages = [];
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
    }
};

function escapeHtmlForWiki(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
