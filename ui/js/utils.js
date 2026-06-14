// ==================== 全局错误捕获 ====================
        window.addEventListener('error', function(e) {
            console.error('[GLOBAL ERROR]', e.message, 'at', e.filename, ':', e.lineno);
        });
        window.addEventListener('unhandledrejection', function(e) {
            console.error('[UNHANDLED REJECTION]', e.reason);
        });

        // ==================== 自定义弹窗工具 ====================
        function _escapeDialog(str) {
            var d = document.createElement('div');
            d.textContent = str || '';
            return d.innerHTML;
        }

        function showToast(message, type) {
            type = type || 'info';
            var toast = document.createElement('div');
            toast.className = 'custom-toast custom-toast-' + type;
            toast.textContent = message;
            document.body.appendChild(toast);
            requestAnimationFrame(function() { toast.classList.add('show'); });
            setTimeout(function() {
                toast.classList.remove('show');
                setTimeout(function() { if (toast.parentNode) toast.remove(); }, 300);
            }, 3000);
        }

        function showConfirm(message) {
            return new Promise(function(resolve) {
                var overlay = document.createElement('div');
                overlay.className = 'custom-dialog-overlay';
                overlay.innerHTML =
                    '<div class="custom-dialog">' +
                    '<div class="custom-dialog-message">' + _escapeDialog(message) + '</div>' +
                    '<div class="custom-dialog-actions">' +
                    '<button class="custom-dialog-btn custom-dialog-btn-cancel">取消</button>' +
                    '<button class="custom-dialog-btn custom-dialog-btn-confirm">确定</button>' +
                    '</div></div>';
                document.body.appendChild(overlay);
                requestAnimationFrame(function() { overlay.classList.add('show'); });

                function closeAndResolve(value) {
                    overlay.classList.remove('show');
                    setTimeout(function() { if (overlay.parentNode) overlay.remove(); resolve(value); }, 200);
                }
                overlay.querySelector('.custom-dialog-btn-confirm').onclick = function() { closeAndResolve(true); };
                overlay.querySelector('.custom-dialog-btn-cancel').onclick = function() { closeAndResolve(false); };
                overlay.addEventListener('click', function(e) { if (e.target === overlay) closeAndResolve(false); });
                requestAnimationFrame(function() {
                    requestAnimationFrame(function() {
                        var btn = overlay.querySelector('.custom-dialog-btn-confirm');
                        if (btn) btn.focus();
                    });
                });
            });
        }

        function showPrompt(message, defaultValue) {
            return new Promise(function(resolve) {
                defaultValue = defaultValue || '';
                var overlay = document.createElement('div');
                overlay.className = 'custom-dialog-overlay';
                overlay.innerHTML =
                    '<div class="custom-dialog">' +
                    '<div class="custom-dialog-message">' + _escapeDialog(message) + '</div>' +
                    '<input type="text" class="custom-dialog-input" value="' + _escapeDialog(defaultValue) + '">' +
                    '<div class="custom-dialog-actions">' +
                    '<button class="custom-dialog-btn custom-dialog-btn-cancel">取消</button>' +
                    '<button class="custom-dialog-btn custom-dialog-btn-confirm">确定</button>' +
                    '</div></div>';
                document.body.appendChild(overlay);
                requestAnimationFrame(function() { overlay.classList.add('show'); });
                var input = overlay.querySelector('.custom-dialog-input');
                input.focus();
                input.select();
                function closeAndResolve(value) {
                    overlay.classList.remove('show');
                    setTimeout(function() { if (overlay.parentNode) overlay.remove(); resolve(value); }, 200);
                }
                overlay.querySelector('.custom-dialog-btn-confirm').onclick = function() { closeAndResolve(input.value.trim() || null); };
                overlay.querySelector('.custom-dialog-btn-cancel').onclick = function() { closeAndResolve(null); };
                overlay.addEventListener('click', function(e) { if (e.target === overlay) closeAndResolve(null); });
                input.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') { closeAndResolve(input.value.trim() || null); }
                    if (e.key === 'Escape') { closeAndResolve(null); }
                });
            });
        }

        // ==================== 用户信息 ====================

        function updateSidebarUser(username, role) {
            var el = document.getElementById('sidebar-user-icon');
            var nd = document.getElementById('sidebar-user-name-display');
            if (!el) return;
            if (username) {
                var initial = username.charAt(0).toUpperCase();
                el.innerHTML = '<div class="sidebar-avatar">' + initial + '</div><div class="sidebar-username">' + username + '</div>';
                if (nd) nd.textContent = username;
            } else {
                el.innerHTML = '<div class="sidebar-avatar">👤</div><div class="sidebar-username">未登录</div>';
                if (nd) nd.textContent = '未登录';
            }
        }

        // ==================== 按需加载脚本 ====================
        var _loadedScripts = {};

        function _loadScript(url, callback) {
            if (_loadedScripts[url]) { if (callback) callback(); return; }
            var s = document.createElement('script');
            s.src = url;
            s.onload = function() { _loadedScripts[url] = true; if (callback) callback(); };
            s.onerror = function() { console.error('Failed to load', url); };
            document.head.appendChild(s);
        }

        /**
         * 增强版 apiFetch — 统一超时、错误处理、响应解析
         * @param {string} url - 请求地址
         * @param {object} [options] - fetch 选项
         * @param {number} [options.timeout=30000] - 超时毫秒数，0=不超时
         * @param {boolean} [options.parseJson=false] - 是否自动解析 JSON（开启后返回解析后的对象而非 Response）
         * @param {boolean} [options.showError=true] - 失败时是否自动弹错误提示
         * @returns {Promise<object|Response>}
         */
        async function apiFetch(url, options) {
            options = options || {};
            if (!options.headers) options.headers = {};
            if (!options.headers['Content-Type']) options.headers['Content-Type'] = 'application/json';

            var timeout = options.timeout !== undefined ? options.timeout : 30000;
            var parseJson = options.parseJson === true;
            var showError = options.showError !== false;
            var controller = null;

            if (timeout > 0) {
                controller = new AbortController();
                options.signal = controller.signal;
                setTimeout(function() { controller.abort(); }, timeout);
            }

            try {
                var response = await fetch(url, options);
                if (!response.ok) {
                    var errMsg = '请求失败 (' + response.status + ' ' + response.statusText + ')';
                    if (showError) showToast(errMsg, 'error');
                    throw new Error(errMsg);
                }
                if (!parseJson) return response;
                var data = await response.json();
                if (data && data.success === false && showError) {
                    showToast(data.message || '操作失败', 'error');
                }
                return data;
            } catch (e) {
                if (e.name === 'AbortError') {
                    var msg = '请求超时，请检查网络连接';
                    if (showError) showToast(msg, 'error');
                    throw new Error(msg);
                }
                if (showError && !e.message.startsWith('请求失败')) {
                    showToast('网络错误: ' + e.message, 'error');
                }
                throw e;
            }
        }

        /**
         * GET 快捷方法
         */
        async function apiGet(url, options) {
            return apiFetch(url, Object.assign({ method: 'GET' }, options || {}));
        }

        /**
         * POST 快捷方法（自动序列化 JSON body）
         */
        async function apiPost(url, body, options) {
            options = options || {};
            if (body !== undefined && body !== null) {
                options.body = JSON.stringify(body);
            }
            options.method = 'POST';
            return apiFetch(url, options);
        }

        /**
         * 为异步操作添加按钮加载状态管理
         * @param {Promise|Function} task - 异步任务或返回 Promise 的函数
         * @param {HTMLElement|string} el - 按钮元素或其 id，操作期间自动禁用
         * @param {string} [loadingText] - 禁用时显示的文本
         * @returns {Promise} 任务结果
         */
        async function withLoading(task, el, loadingText) {
            var target = typeof el === 'string' ? document.getElementById(el) : el;
            var originalText = null;
            if (target && target.tagName === 'BUTTON') {
                originalText = target.textContent;
                target.disabled = true;
                if (loadingText) target.textContent = loadingText;
            }
            try {
                return await (typeof task === 'function' ? task() : task);
            } finally {
                if (target && target.tagName === 'BUTTON') {
                    target.disabled = false;
                    if (loadingText && originalText !== null) target.textContent = originalText;
                }
            }
        }
