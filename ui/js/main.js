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
                setTimeout(function() {
                    var btn = overlay.querySelector('.custom-dialog-btn-confirm');
                    if (btn) btn.focus();
                }, 100);
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

        async function apiFetch(url, options) {
            options = options || {};
            if (!options.headers) options.headers = {};
            if (!options.headers['Content-Type']) options.headers['Content-Type'] = 'application/json';
            return await fetch(url, options);
        }

        // ==================== 远程模式（统一模式） ====================
        function updateModeUI() {
            const selectBtn = document.getElementById('selectFolderBtn');
            if (selectBtn) selectBtn.textContent = '从本地选择';
        }

        // ==================== 工具定义 ====================
        const tools = {
            to_docx: {
                name: '批量提取',
                intro: '提取选择的文档文本，生成格式化的 DOCX 文件。',
                features: [
                    '支持 PDF、DOC、DOCX、TXT、HTML、HTM、MD 格式',
                    '提取原文档文字，不保留格式',
                    '构建GB/T 9704—2012格式文档',
                    '选择或直接处理目录内所有文件'
                ]
            },
            to_index: {
                name: '构建索引',
                intro: '扫描目录及子目录，生成带超链接的 Excel 索引表。',
                features: [
                    '自动扫描所有子目录',
                    '构建超链接的 Excel 索引表',
                    '显示文件大小、修改日期',
                    '索引目录内所有文件'
                ]
            },
            to_compare: {
                name: '文档比较',
                intro: '比较用户选择的两个文档，生成带差异标注的比较结果。',
                features: [
                    '短句和字符级差异比较',
                    '差异标注（不含格式）',
                    '构建新的 DOCX 结果文档',
                    '选择目录内文件'
                ]
            },
            to_pdf: {
                name: '批量转化',
                intro: '将选择的 DOCX 文档转换为 PDF 格式。',
                features: [
                    '自动将 DOC 转换为 DOCX',
                    '保持原有格式',
                    '批量生成 PDF',
                    '选择或直接处理目录内所有文件'
                ]
            },
            to_pageNum: {
                name: '添加页码',
                intro: '为选择的 DOCX 文档另存后添加页码。',
                features: [
                    '目录内全部 DOC 转换为 DOCX',
                    '另存新文件后再处理',
                    '清除文档页脚构建页码',
                    '选择或直接处理目录内所有文件'
                ]
            },
            to_redhead: {
                name: '文档套红',
                intro: '为选择的 DOCX 文档生成红头文件，包括发文机关、文号、印章等。',
                features: [
                    '匹配配置的单位简称和代字',
                    '另存新文件后再处理',
                    '自动匹配印章并套红',
                    '选择或直接处理目录内所有文件'
                ]
            }
        };

        let currentTool = 'to_compare';

        function selectTool(tool) {
            try {
                currentTool = tool;
                document.querySelectorAll('.tool-item').forEach(item => item.classList.remove('active'));
                const toolElement = document.querySelector(`.tool-item[onclick*="'${tool}'"]`);
                if (toolElement) toolElement.classList.add('active');

                const toolInfo = tools[tool];
                if (!toolInfo) { console.error('Tool not found:', tool); return; }
                document.getElementById('toolTitle').textContent = toolInfo.name;
                document.getElementById('toolIntro').textContent = toolInfo.intro;

                let featureHtml = '<ul class="feature-list">';
                toolInfo.features.forEach(f => { featureHtml += `<li>${f}</li>`; });
                featureHtml += '</ul>';
                document.getElementById('toolIntro').innerHTML += featureHtml;

                document.getElementById('toolPanel').style.display = 'block';
                document.getElementById('result').style.display = 'none';

                var selDir = getSelectedDirectory();
                if (selDir) {
                    if (selDir.type === 'kb') {
                        loadFileList(null, tool);
                    } else {
                        loadFileList(selDir, tool);
                    }
                }
            } catch (e) {
                console.error('selectTool error:', e);
            }
        }

        function getKbInfoFromWorkdir() {
            var el = document.getElementById('workdir');
            var kbId = el ? el.getAttribute('data-fb-id') : null;
            var subdir = el ? el.getAttribute('data-fb-subdir') || '' : '';
            return { kbId: kbId, subdir: subdir, isKbMode: !!kbId };
        }

        function getSelectedDirectory() {
            var kbInfo = getKbInfoFromWorkdir();
            if (kbInfo.isKbMode) {
                return { type: 'kb', kbId: kbInfo.kbId, subdir: kbInfo.subdir };
            }
            var workdirInput = document.getElementById('workdir');
            var path = workdirInput ? workdirInput.value.trim() : '';
            if (path) {
                return { type: 'local', path: path };
            }
            return null;
        }

        // ==================== 文件列表面板（统一双列） ====================
        async function loadFileList(directory, tool) {
            if (!tool) return;
            const panel = document.getElementById('filePanel');
            const label = document.getElementById('fileLabel');
            const leftList = document.getElementById('leftList');
            const rightList = document.getElementById('rightList');

            const isIndex = (tool === 'to_index');
            const isCompare = (tool === 'to_compare');
            label.textContent = isIndex ? '📂目录文件：' : isCompare ? '👇原稿 / 终稿：' : '📂目录文件：';

            let filesData;
            const selDir = directory || getSelectedDirectory();

            if (selDir && selDir.type === 'kb') {
                let url = '/api/fb/' + selDir.kbId + '/local-files';
                let params = [];
                if (selDir.subdir) params.push('subdir=' + encodeURIComponent(selDir.subdir));
                if (tool) params.push('tool=' + encodeURIComponent(tool));
                if (params.length > 0) url += '?' + params.join('&');

                const filesRes = await apiFetch(url, { method: 'GET' });
                const kbData = await filesRes.json();

                if (!kbData.success || !kbData.files || kbData.files.length === 0) {
                    leftList.innerHTML = '<div style="padding:8px;color:#999;font-size:12px;">目录中无匹配文件</div>';
                    rightList.innerHTML = '';
                    panel.style.display = 'block';
                    return;
                }

                filesData = { success: true, files: kbData.files };
            } else if (selDir && selDir.type === 'local') {
                const body = { directory: selDir.path, tool: tool };

                const filesRes = await apiFetch('/list_files', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body)
                });
                filesData = await filesRes.json();
            } else {
                leftList.innerHTML = '<div style="padding:8px;color:#999;font-size:12px;">请先选择目录</div>';
                rightList.innerHTML = '';
                panel.style.display = 'block';
                return;
            }

            if (!filesData.success || !filesData.files || filesData.files.length === 0) {
                leftList.innerHTML = '<div style="padding:8px;color:#999;font-size:12px;">目录中无匹配文件</div>';
                rightList.innerHTML = '';
                panel.style.display = 'block';
                return;
            }

            if (isCompare) {
                const fileNames = filesData.files.map(f => f.name);
                leftList.innerHTML = fileNames.map(f => {
                    const e = f.replace(/'/g, "\\'").replace(/"/g, '\\"');
                    return `<span class="file-tag" onclick="selectRadio(this, 'orig', '${e}')">${f}</span>`;
                }).join('');
                rightList.innerHTML = fileNames.map(f => {
                    const e = f.replace(/'/g, "\\'").replace(/"/g, '\\"');
                    return `<span class="file-tag" onclick="selectRadio(this, 'final', '${e}')">${f}</span>`;
                }).join('');
            } else if (isIndex) {
                const files = filesData.files;
                const mid = Math.ceil(files.length / 2);
                leftList.innerHTML = files.slice(0, mid).map(f =>
                    `<span class="file-tag" style="cursor:default;">${f.name}</span>`
                ).join('');
                rightList.innerHTML = files.slice(mid).map(f =>
                    `<span class="file-tag" style="cursor:default;">${f.name}</span>`
                ).join('');
            } else {
                const files = filesData.files;
                const mid = Math.ceil(files.length / 2);
                leftList.innerHTML = files.slice(0, mid).map(f => {
                    const e = f.name.replace(/'/g, "\\'").replace(/"/g, '\\"');
                    return `<span class="file-tag" data-filename="${e}" onclick="toggleFileTag(this)">${f.name}</span>`;
                }).join('');
                rightList.innerHTML = files.slice(mid).map(f => {
                    const e = f.name.replace(/'/g, "\\'").replace(/"/g, '\\"');
                    return `<span class="file-tag" data-filename="${e}" onclick="toggleFileTag(this)">${f.name}</span>`;
                }).join('');
            }
            panel.style.display = 'block';
        }

        window.toggleFileTag = function(el) { el.classList.toggle('selected'); };

        window.selectRadio = function(el, group, value) {
            el.parentElement.querySelectorAll('.file-tag').forEach(tag => tag.classList.remove('selected'));
            el.classList.add('selected');
        };

        function getCheckedFiles() {
            const leftList = document.getElementById('leftList');
            const rightList = document.getElementById('rightList');
            return Array.from(leftList.querySelectorAll('.file-tag.selected'))
                        .concat(Array.from(rightList.querySelectorAll('.file-tag.selected')))
                        .map(t => t.dataset.filename);
        }

        // 切换文件列表显示
        window.toggleFileList = async function() {
            const panel = document.getElementById('fileListPanel');
            const fileList = document.getElementById('fileList');
            const selDir = getSelectedDirectory();

            if (!selDir) {
                return;
            }

            if (panel.style.display === 'none' || panel.style.display === '') {
                // 展开：获取文件列表
                let filesData;
                if (selDir.type === 'kb') {
                    let url = '/api/fb/' + selDir.kbId + '/local-files';
                    let params = [];
                    if (selDir.subdir) params.push('subdir=' + encodeURIComponent(selDir.subdir));
                    if (currentTool) params.push('tool=' + encodeURIComponent(currentTool));
                    if (params.length > 0) url += '?' + params.join('&');
                    const filesRes = await apiFetch(url, { method: 'GET' });
                    const kbData = await filesRes.json();
                    filesData = kbData;
                } else {
                    const body = { directory: selDir.path, tool: currentTool };
                    const filesRes = await apiFetch('/list_files', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(body)
                    });
                    filesData = await filesRes.json();
                }

                if (filesData && filesData.success && filesData.files) {
                    if (filesData.files.length > 0) {
                        fileList.innerHTML = filesData.files.map(f =>
                            `<span style="padding:2px 6px;background:#f0f0f0;border-radius:3px;font-size:12px;">📄 ${f.name}</span>`
                        ).join('');
                    } else {
                        fileList.innerHTML = '<span style="color:#999;font-size:12px;">目录为空</span>';
                    }
                } else {
                    fileList.innerHTML = '<span style="color:#999;font-size:12px;">获取文件列表失败</span>';
                }
                panel.style.display = 'block';
            } else {
                // 收起
                panel.style.display = 'none';
            }
        };

        window.openWorkdir = async function() {
            var selDir = getSelectedDirectory();
            if (!selDir) {
                showToast('请先选择目录', 'error');
                return;
            }
            if (selDir.type === 'kb') {
                showToast('文件库文件请在文件库中查看', 'error');
                return;
            }
            try {
                var res = await apiFetch('/open_folder', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({directory: selDir.path})
                });
                var data = await res.json();
                if (!data.success) {
                    showToast('打开目录失败: ' + (data.message || ''), 'error');
                }
            } catch (e) {
                showToast('打开目录失败: ' + e.message, 'error');
            }
        };

        // ==================== 选择本机目录 ====================
        window.selectFolder = async function() {
            try {
                const api = window.electronAPI || window.pywebview?.api;
                const path = api ? await api.selectDirectory() : null;
                if (path) {
                    const workdirInput = document.getElementById('workdir');
                    workdirInput.value = path;
                    workdirInput.removeAttribute('data-fb-id');
                    workdirInput.removeAttribute('data-fb-subdir');
                    if (currentTool) {
                        await loadFileList({type: 'local', path: path}, currentTool);
                    }
                }
            } catch (e) {
                console.error('selectDirectory error:', e);
                showToast('选择目录失败', 'error');
            }
        };

        // 下载结果（打包 ZIP）
        window.downloadResults = async function() {
            var selDir = getSelectedDirectory();
            if (!selDir) {
                showToast('请先选择目录', 'error');
                return;
            }
            if (selDir.type === 'kb') {
                showToast('请在文件库中下载文件', 'error');
                return;
            }
            try {
                var folderName = selDir.path.split(/[/\\]/).pop() || 'results';
                var body = { folder_name: folderName, directory: selDir.path };
                var response = await apiFetch('/download_results', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body)
                });
                if (response.ok) {
                    var blob = await response.blob();
                    var a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = folderName + '_处理结果.zip';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(blob);
                }
            } catch (error) {
                console.error('下载失败:', error);
            }
        };

        // ==================== 执行工具 ====================
        async function runTool() {
            const selDir = getSelectedDirectory();
            const resultDiv = document.getElementById('result');

            if (!selDir) {
                resultDiv.className = 'error';
                resultDiv.textContent = '请先选择目录';
                resultDiv.style.display = 'block';
                return;
            }

            let selectedFiles = [];
            if (currentTool === 'to_compare') {
                const origSelected = document.querySelector('#leftList .file-tag.selected');
                const finalSelected = document.querySelector('#rightList .file-tag.selected');
                if (!origSelected || !finalSelected) {
                    resultDiv.className = 'error';
                    resultDiv.textContent = '请分别选择原稿和终稿';
                    resultDiv.style.display = 'block';
                    return;
                }
                selectedFiles = [origSelected.textContent, finalSelected.textContent];
            } else {
                selectedFiles = getCheckedFiles();
            }

            resultDiv.className = 'success';
            resultDiv.innerHTML = '<pre class="output-pre" id="outputLog"></pre>';
            resultDiv.style.display = 'block';

            let response;

            if (selDir.type === 'kb') {
                const bodyData = {
                    tool: currentTool,
                    subdir: selDir.subdir
                };
                if (selectedFiles.length > 0) bodyData.files = selectedFiles;

                response = await apiFetch('/api/fb/' + selDir.kbId + '/run-tool', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(bodyData)
                });
            } else {
                const bodyData = { tool: currentTool, directory: selDir.path };
                if (selectedFiles.length > 0) bodyData.files = selectedFiles;

                response = await apiFetch('/run_tool_with_config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(bodyData)
                });
            }

            try {
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                const outputLog = document.getElementById('outputLog');
                let outputLines = [];

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const text = decoder.decode(value);
                    const lines = text.split('\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.type === 'output') {
                                    outputLines.push(data.content);
                                    outputLog.textContent = outputLines.join('\n');
                                    outputLog.scrollTop = outputLog.scrollHeight;
                                } else if (data.type === 'end') {
                                    if (!data.success) {
                                        resultDiv.className = 'error';
                                        const errorContent = data.error || outputLines.join('\n') || '执行失败';
                                        resultDiv.innerHTML = '<pre class="output-pre">' + escapeHtml(errorContent) + '</pre>';
                                    } else {
                                        outputLog.textContent += '\n\n[结束]';
                                    }
                                }
                            } catch (e) {}
                        }
                    }
                }
                loadFileList(null, currentTool);
            } catch (error) {
                resultDiv.className = 'error';
                resultDiv.innerHTML = '<pre class="output-pre">' + escapeHtml(error.message) + '</pre>';
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // ==================== 拖拽支持 ====================
        var workdirInput = document.getElementById('workdir');
        if (workdirInput) {
            workdirInput.addEventListener('dragover', function(e) { e.preventDefault(); });
            workdirInput.addEventListener('drop', function(e) { e.preventDefault(); });
        }

        // ==================== 配置管理 ====================
        let userConfig = null;

        // 打开配置弹窗
        window.openConfig = async function() {
            const modal = document.getElementById('configModal');
            modal.style.display = 'flex';
            requestAnimationFrame(() => { modal.classList.add('show'); });
            await loadUserConfig();
        };

        window.closeConfig = function() {
            const modal = document.getElementById('configModal');
            modal.classList.remove('show');
            setTimeout(() => { modal.style.display = 'none'; }, 250);
        };

        window.switchConfigTab = async function(tabName) {
            document.querySelectorAll('.config-tab').forEach(tab => tab.classList.remove('active'));
            document.querySelector(`.config-tab[onclick*="${tabName}"]`).classList.add('active');

            document.querySelectorAll('.config-section').forEach(section => section.classList.remove('active'));
            const sectionId = tabName === 'raw' ? 'rawYamlConfig' : tabName + 'Config';
            document.getElementById(sectionId).classList.add('active');

            if (tabName === 'raw') {
                if (userConfig && Object.keys(userConfig).length > 0) {
                    document.getElementById('rawYamlText').value = objectToYaml(userConfig);
                } else {
                    try {
                        const response = await apiFetch('/get_config', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({})
                        });
                        const data = await response.json();
                        if (data.success) {
                            document.getElementById('rawYamlText').value = objectToYaml(data.config);
                        }
                    } catch (e) {
                        console.log('加载配置失败:', e);
                    }
                }
            }
        };

        async function loadUserConfig() {
            const hasValidConfig = userConfig && Object.keys(userConfig).length > 0;

            if (hasValidConfig) {
                loadCompanyConfigForm(userConfig);
                if (userConfig.compare) {
                    document.getElementById('sentenceThreshold').value = userConfig.compare.sentence_similarity_threshold || 0.40;
                    document.getElementById('paragraphThreshold').value = userConfig.compare.para_similarity_threshold || 0.40;
                    document.getElementById('shortParaThreshold').value = userConfig.compare.short_para_char_threshold || 50;
                } else {
                    document.getElementById('sentenceThreshold').value = 0.40;
                    document.getElementById('paragraphThreshold').value = 0.40;
                    document.getElementById('shortParaThreshold').value = 50;
                }
                document.getElementById('rawYamlText').value = objectToYaml(userConfig);
            } else {
                await loadDefaultConfig();
            }
        }

        // 加载默认配置（从模板配置读取）
        window.loadDefaultConfig = async function() {
            try {
                const response = await apiFetch('/get_config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({})
                });
                const data = await response.json();
                if (data.success) {
                    userConfig = data.config;
                    loadCompanyConfigForm(userConfig);
                    if (userConfig.compare) {
                        document.getElementById('sentenceThreshold').value = userConfig.compare.sentence_similarity_threshold || 0.40;
                        document.getElementById('paragraphThreshold').value = userConfig.compare.para_similarity_threshold || 0.40;
                        document.getElementById('shortParaThreshold').value = userConfig.compare.short_para_char_threshold || 50;
                    }
                    document.getElementById('rawYamlText').value = objectToYaml(userConfig);
                }
            } catch (error) {
                console.error('加载配置失败:', error);
            }
        };

        function loadCompanyConfigForm(config) {
            const formDiv = document.getElementById('companyConfigForm');
            formDiv.innerHTML = '';

            const configWithoutMeta = {...config};
            delete configWithoutMeta.compare;
            delete configWithoutMeta.last_workdir;

            let formHtml = '';

            // 表头
            formHtml += `
                <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 2px; padding: 4px 8px;">
                    <div style="flex: 1; min-width: 120px; font-size: 11px; color: #888; font-weight: 500;">全称</div>
                    <div style="flex: 1; min-width: 120px; font-size: 11px; color: #888; font-weight: 500;">简称</div>
                    <div style="flex: 0 0 70px; font-size: 11px; color: #888; font-weight: 500;">代字</div>
                    <div style="flex: 1; min-width: 120px; font-size: 11px; color: #888; font-weight: 500;">印章位置</div>
                    <div style="flex: 0 0 auto; min-width: 36px;"></div>
                </div>
            `;

            for (const companyName in configWithoutMeta) {
                const companyInfo = configWithoutMeta[companyName];
                const shortNames = companyInfo.简称 || [];
                const daizi = companyInfo.代字 || '';
                const stampPath = companyInfo['印章位置'] || '';
                const escName = escapeHtml(companyName);
                const escJsName = escName.replace(/'/g, "\\'");

                formHtml += `
                    <div class="company-section" data-original-name="${escJsName}" style="margin-bottom: 6px; padding: 6px 8px; border: 1px solid #e0e0e0; border-radius: 4px; background: #f9f9f9;">
                        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                            <input type="text" data-field="name" data-original="${escJsName}"
                                   value="${escName}" title="单位全称（可直接编辑）"
                                   style="flex: 1; min-width: 120px; padding: 3px 6px; font-size: 12px; font-weight: bold; color: #333; border: 1px solid transparent; border-radius: 3px; background: transparent;"
                                   onfocus="this.style.borderColor='#ccc'; this.style.background='#fff';"
                                   onblur="this.style.borderColor='transparent'; this.style.background='transparent';">
                            <div style="flex: 1; min-width: 120px;">
                                <input type="text" data-field="shortnames" data-original="${escJsName}"
                                       value="${escapeHtml(shortNames.join(', '))}" placeholder="简称（逗号分隔）"
                                       style="width: 100%; padding: 3px 6px; font-size: 12px; border: 1px solid #ccc; border-radius: 3px;">
                            </div>
                            <div style="flex: 0 0 70px;">
                                <input type="text" data-field="daizi" data-original="${escJsName}"
                                       value="${escapeHtml(daizi)}" placeholder="代字"
                                       style="width: 100%; padding: 3px 6px; font-size: 12px; border: 1px solid #ccc; border-radius: 3px;">
                            </div>
                            <div style="flex: 1; min-width: 120px;">
                                <input type="text" data-field="stamp" data-original="${escJsName}"
                                       value="${escapeHtml(stampPath)}" placeholder="./单位名.png"
                                       style="width: 100%; padding: 3px 6px; font-size: 12px; border: 1px solid #ccc; border-radius: 3px;">
                            </div>
                            <div style="flex: 0 0 auto; min-width: 36px;">
                                <button type="button" onclick="removeCompany(this.closest('.company-section').dataset.originalName)"
                                        style="background: #dc3545; color: white; border: none; padding: 3px 6px; border-radius: 3px; font-size: 11px; cursor: pointer;">删除</button>
                            </div>
                        </div>
                    </div>
                `;
            }

            formHtml += `
                <button type="button" onclick="addNewCompany()"
                        style="width: auto; margin-top: 3px; padding: 4px 12px; background: #28a745; border: none; border-radius: 4px; color: white; font-size: 12px; cursor: pointer;">
                    + 添加新单位
                </button>
            `;

            formDiv.innerHTML = formHtml;
        }

        window.addNewCompany = function() {
            let existing = document.getElementById('newCompanyRow');
            if (existing) { existing.querySelector('input').focus(); return; }

            const formDiv = document.getElementById('companyConfigForm');
            const addBtn = formDiv.querySelector('button[onclick="addNewCompany()"]');

            const row = document.createElement('div');
            row.id = 'newCompanyRow';
            row.style.cssText = 'display:flex; gap:6px; align-items:center; margin-top:8px;';
            row.innerHTML = `
                <input type="text" id="newCompanyInput" placeholder="输入单位全称"
                       style="flex:1; padding:4px 8px; font-size:12px; border:1px solid #e94560; border-radius:3px; outline:none;">
                <button type="button" onclick="confirmNewCompany()"
                        style="padding:4px 10px; background:#28a745; border:none; border-radius:3px; color:white; font-size:12px; cursor:pointer;">确定</button>
                <button type="button" onclick="cancelNewCompany()"
                        style="padding:4px 10px; background:#6c757d; border:none; border-radius:3px; color:white; font-size:12px; cursor:pointer;">取消</button>
            `;
            addBtn.parentNode.insertBefore(row, addBtn);

            const input = row.querySelector('input');
            input.focus();
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') confirmNewCompany();
                if (e.key === 'Escape') cancelNewCompany();
            });
        };

        window.confirmNewCompany = function() {
            const input = document.getElementById('newCompanyInput');
            const companyName = input ? input.value.trim() : '';
            if (!companyName) { input.focus(); return; }

            if (!userConfig) userConfig = {};
            userConfig[companyName] = {简称: [], 代字: '', 印章位置: ''};
            loadCompanyConfigForm(userConfig);
            document.getElementById('rawYamlText').value = objectToYaml(userConfig);
            cancelNewCompany();
        };

        window.cancelNewCompany = function() {
            const row = document.getElementById('newCompanyRow');
            if (row) row.remove();
        };

        window.removeCompany = function(companyName) {
            showConfirm('确定要删除 "' + companyName + '" 的配置吗？').then(function(ok) {
                if (ok) {
                    delete userConfig[companyName];
                    loadCompanyConfigForm(userConfig);
                    document.getElementById('rawYamlText').value = objectToYaml(userConfig);
                }
            });
        };

        window.saveUserConfig = async function() {
            try {
                let updatedConfig = {};

                // YAML标签页优先
                const rawTab = document.querySelector('.config-tab[onclick*="raw"]');
                if (rawTab && rawTab.classList.contains('active')) {
                    const yamlText = document.getElementById('rawYamlText').value.trim();
                    if (!yamlText) throw new Error('YAML 配置不能为空');
                    updatedConfig = yamlToObject(yamlText);
                    if (!updatedConfig || Object.keys(updatedConfig).length === 0) {
                        throw new Error('YAML 格式不正确，请检查');
                    }
                } else {
                    const companySections = document.querySelectorAll('.company-section');
                    companySections.forEach(section => {
                        const originalName = section.dataset.originalName;
                        const nameInput = section.querySelector('input[data-field="name"]');
                        const shortnamesInput = section.querySelector('input[data-field="shortnames"]');
                        const daiziInput = section.querySelector('input[data-field="daizi"]');
                        const stampInput = section.querySelector('input[data-field="stamp"]');

                        const currentName = nameInput ? nameInput.value.trim() : originalName;
                        const shortNames = shortnamesInput.value.split(',').map(s => s.trim()).filter(s => s);

                        updatedConfig[currentName] = {
                            简称: shortNames,
                            代字: daiziInput.value.trim(),
                            印章位置: stampInput.value.trim()
                        };
                    });

                    updatedConfig.compare = {
                        sentence_similarity_threshold: parseFloat(document.getElementById('sentenceThreshold').value) || 0.40,
                        para_similarity_threshold: parseFloat(document.getElementById('paragraphThreshold').value) || 0.40,
                        short_para_char_threshold: parseInt(document.getElementById('shortParaThreshold').value) || 50
                    };
                }

                if (Object.keys(updatedConfig).length === 0) throw new Error('配置不能为空');

                userConfig = updatedConfig;

                localStorage.setItem('userConfig', JSON.stringify(userConfig));

                const saveRes = await apiFetch('/save_config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({config: userConfig})
                });
                const saveData = await saveRes.json();
                if (!saveData.success) throw new Error(saveData.message || '保存失败');

                document.getElementById('rawYamlText').value = objectToYaml(userConfig);
                closeConfig();
            } catch (error) {
                showToast('保存配置失败: ' + error.message, 'error');
            }
        };

        // YAML工具函数
        function objectToYaml(obj) {
            let yaml = '';
            for (const key in obj) {
                if (key === 'compare') {
                    yaml += 'compare:\n';
                    for (const subKey in obj[key]) {
                        yaml += `  ${subKey}: ${obj[key][subKey]}\n`;
                    }
                } else {
                    const companyInfo = obj[key];
                    if (!companyInfo || typeof companyInfo !== 'object') {
                        yaml += `${key}: ${companyInfo}\n`;
                        continue;
                    }
                    yaml += `${key}:\n`;
                    yaml += `  简称:\n`;
                    const shortNames = companyInfo['简称'];
                    if (shortNames && Array.isArray(shortNames)) {
                        for (const shortName of shortNames) {
                            yaml += `  - ${shortName}\n`;
                        }
                    }
                    yaml += `  代字: ${companyInfo['代字'] || ''}\n`;
                    if (companyInfo['印章位置']) {
                        yaml += `  印章位置: ${companyInfo['印章位置']}\n`;
                    }
                }
                yaml += '\n';
            }
            return yaml.trim();
        }

        function yamlToObject(yamlStr) {
            const result = {};
            let currentKey = null;
            let currentSubKey = null;
            let listKey = null;

            for (const rawLine of yamlStr.split('\n')) {
                const line = rawLine.replace(/#.*$/, '');
                if (!line.trim()) continue;
                const indent = line.search(/\S/);

                if (indent === 0) {
                    const match = line.match(/^(\S[\s\S]*?):\s*$/);
                    if (match) {
                        currentKey = match[1].trim();
                        result[currentKey] = {};
                        currentSubKey = null;
                        listKey = null;
                    } else {
                        const kv = line.match(/^(\S[\s\S]*?):\s*(.+)$/);
                        if (kv) {
                            currentKey = kv[1].trim();
                            result[currentKey] = parseValue(kv[2].trim());
                            currentSubKey = null;
                            listKey = null;
                        }
                    }
                } else if (indent >= 2 && currentKey) {
                    const trimmed = line.trim();
                    if (trimmed.startsWith('- ')) {
                        if (listKey && result[currentKey][listKey]) {
                            result[currentKey][listKey].push(trimmed.substring(2).trim());
                        }
                        continue;
                    }
                    const kv = trimmed.match(/^(\S[\s\S]*?):\s*(.*)$/);
                    if (kv) {
                        currentSubKey = kv[1].trim();
                        const val = kv[2].trim();
                        if (val === '') {
                            if (currentSubKey === '简称') {
                                result[currentKey][currentSubKey] = [];
                                listKey = currentSubKey;
                            } else {
                                result[currentKey][currentSubKey] = '';
                                listKey = null;
                            }
                        } else {
                            result[currentKey][currentSubKey] = parseValue(val);
                            listKey = null;
                        }
                    }
                }
            }
            return result;
        }

        function parseValue(val) {
            if (val === 'true') return true;
            if (val === 'false') return false;
            if (val === 'null' || val === '') return '';
            const num = Number(val);
            if (!isNaN(num) && val !== '') return num;
            if ((val.startsWith('"') && val.endsWith('"')) ||
                (val.startsWith("'") && val.endsWith("'"))) {
                return val.slice(1, -1);
            }
            return val;
        }

        // ==================== 关于弹窗 ====================
        // <div style="margin-top:10px;padding-top:10px;border-top:1px solid #eee;font-size:12px;color:#666;line-height:2;">
        //     <div style="display:flex;gap:6px;"><span style="width:16px;text-align:center;">🏠</span><a href="https://github.com/doonly1/" style="color:#e94560;text-decoration:none;" target="_blank">github.com/doonly1</a></div>
        // </div>
        window.showAbout = function() {
            const overlay = document.getElementById('aboutOverlay');
            overlay.style.display = 'flex';
            overlay.innerHTML = `
                <div style="background:#fff;border-radius:12px;padding:20px 24px;max-width:360px;width:85%;box-shadow:0 4px 20px rgba(0,0,0,0.1);border:1px solid rgba(0,0,0,0.08);font-size:13px;line-height:1.8;">
                    <div style="text-align:center;margin-bottom:12px;">
                        <h2 style="margin:6px 0 2px;font-size:18px;color:#1a1a2e;">文枢</h2>
                        <div style="font-size:11px;color:#999;">DocFlow · 文档工作流</div>
                    </div>

                    <div style="text-align:center;margin-top:14px;">
                        <button onclick="closeAbout()" style="padding:5px 24px;background:#e94560;color:white;border:none;border-radius:4px;font-size:13px;cursor:pointer;">确定</button>
                    </div>
                </div>
            `;
            requestAnimationFrame(() => { overlay.style.opacity = '1'; });
            overlay.addEventListener('click', function(e) { if (e.target === overlay) closeAbout(); });
        };

        window.closeAbout = function() {
            const overlay = document.getElementById('aboutOverlay');
            overlay.style.opacity = '0';
            setTimeout(() => { overlay.style.display = 'none'; overlay.innerHTML = ''; }, 250);
        };

        // ==================== 应用设置 ====================

        let appSettings = { autostart: false, close_action: 'exit' };

        window.openAppSettings = async function() {
            try {
                const response = await apiFetch('/get_app_settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({})
                });
                const data = await response.json();
                if (data.success) {
                    appSettings = data.settings;
                }
            } catch (e) {
                console.log('加载设置失败:', e);
            }

            const overlay = document.getElementById('settingsOverlay');
            overlay.style.display = 'flex';
            overlay.innerHTML = `
                <div style="background:#fff;border-radius:12px;padding:18px 20px;max-width:380px;width:85%;box-shadow:0 4px 20px rgba(0,0,0,0.1);border:1px solid rgba(0,0,0,0.08);transform:scale(0.95);transition:transform 0.25s ease;">
                    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1a2e;border-bottom:1px solid #eee;padding-bottom:8px;">应用设置</h2>

                    <div style="margin-bottom:14px;">
                        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;color:#333;">
                            <input type="checkbox" id="settingAutostart" ${appSettings.autostart ? 'checked' : ''}>
                            开机自启动
                        </label>
                        <div style="font-size:11px;color:#999;margin:4px 0 0 24px;">启动时自动运行文枢桌面版</div>
                    </div>

                    <div style="margin-bottom:16px;">
                        <div style="font-size:13px;color:#333;margin-bottom:6px;">点击关闭按钮时</div>
                        <div style="display:flex;gap:12px;">
                            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:12px;color:#555;">
                                <input type="radio" name="closeAction" value="exit" ${appSettings.close_action !== 'minimize' ? 'checked' : ''}>
                                退出应用
                            </label>
                            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:12px;color:#555;">
                                <input type="radio" name="closeAction" value="minimize" ${appSettings.close_action === 'minimize' ? 'checked' : ''}>
                                最小化到托盘
                            </label>
                        </div>
                        <div style="font-size:11px;color:#999;margin:4px 0 0 0;">最小化到托盘后可从系统托盘恢复窗口</div>
                    </div>

                    <div style="display:flex;gap:8px;justify-content:flex-end;">
                        <button onclick="closeAppSettings()" style="padding:5px 16px;background:#6c757d;color:white;border:none;border-radius:4px;font-size:13px;cursor:pointer;">取消</button>
                        <button onclick="saveAppSettings()" style="padding:5px 16px;background:#e94560;color:white;border:none;border-radius:4px;font-size:13px;cursor:pointer;">保存</button>
                    </div>
                </div>
            `;
            requestAnimationFrame(() => {
                overlay.style.opacity = '1';
                overlay.querySelector('div').style.transform = 'scale(1)';
            });
            overlay.addEventListener('click', function(e) { if (e.target === overlay) closeAppSettings(); });
        };

        window.closeAppSettings = function() {
            const overlay = document.getElementById('settingsOverlay');
            overlay.style.opacity = '0';
            overlay.querySelector('div').style.transform = 'scale(0.95)';
            setTimeout(() => { overlay.style.display = 'none'; overlay.innerHTML = ''; }, 250);
        };

        window.saveAppSettings = async function() {
            const autostart = document.getElementById('settingAutostart').checked;
            const closeAction = document.querySelector('input[name="closeAction"]:checked').value;

            const newSettings = {
                autostart: autostart,
                close_action: closeAction
            };

            try {
                const response = await apiFetch('/save_app_settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({settings: newSettings})
                });
                const data = await response.json();
                if (data.success) {
                    appSettings = newSettings;
                    closeAppSettings();
                } else {
                    showToast('保存设置失败: ' + (data.message || '未知错误'), 'error');
                }
            } catch (e) {
                showToast('保存设置失败: ' + e.message, 'error');
            }
        };

        // 链接拦截（防止在 iframe/WebView 内导航）
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a');
            if (!link) return;
            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
            e.preventDefault();
            if (window.electronAPI && window.electronAPI.openExternal) {
                window.electronAPI.openExternal(href);
            } else {
                window.open(href, '_blank');
            }
        });

        async function initApp() {
            updateModeUI();

            // 加载本地缓存配置（非阻塞）
            var savedConfig = localStorage.getItem('userConfig');
            if (savedConfig) {
                try {
                    var parsed = JSON.parse(savedConfig);
                    if (parsed && Object.keys(parsed).length > 0) {
                        userConfig = parsed;
                    }
                } catch(e) {}
            }

            // 并行加载用户信息和配置
            var [meResp, configResp] = await Promise.all([
                fetch('/api/user/me').then(function(r) { return r.json(); }).catch(function() { return { success: false }; }),
                fetch('/get_config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({})
                }).then(function(r) { return r.json(); }).catch(function() { return { success: false }; })
            ]);

            if (meResp.success) {
                updateSidebarUser(meResp.username, meResp.role || 'admin');
                window.authUsername = meResp.username;
                window.authRole = meResp.role || 'admin';
            } else {
                updateSidebarUser('本机用户', 'admin');
            }

            if (configResp.success && configResp.config) {
                userConfig = configResp.config;
                localStorage.setItem('userConfig', JSON.stringify(configResp.config));
            } else if (!userConfig) {
                userConfig = {
                    compare: {
                        sentence_similarity_threshold: 0.40,
                        para_similarity_threshold: 0.40,
                        short_para_char_threshold: 50
                    }
                };
            }

            if (currentTool) {
                var toolItems = document.querySelectorAll('.tool-item');
                for (var i = 0; i < toolItems.length; i++) toolItems[i].classList.remove('active');
                var toolEl = document.querySelector('.tool-item[onclick*="' + currentTool + '"]');
                if (toolEl) toolEl.classList.add('active');
                var toolInfo = tools[currentTool];
                if (toolInfo && document.getElementById('toolTitle')) {
                    document.getElementById('toolTitle').textContent = toolInfo.name;
                    var introEl = document.getElementById('toolIntro');
                    introEl.textContent = toolInfo.intro;
                    var featureHtml = '<ul class="feature-list">';
                    for (var j = 0; j < toolInfo.features.length; j++) {
                        featureHtml += '<li>' + toolInfo.features[j] + '</li>';
                    }
                    featureHtml += '</ul>';
                    introEl.insertAdjacentHTML('beforeend', featureHtml);
                    document.getElementById('toolPanel').style.display = 'block';
                }
            }
        }

        document.addEventListener('DOMContentLoaded', async function() {
            await initApp();
            setTimeout(function() {
                if (typeof tabManager !== 'undefined') {
                    tabManager.init();
                }
            }, 300);
        });

        function toggleSidebarMenu(e) {
    if (e) e.stopPropagation();
    var popup = document.getElementById('sidebar-popup');
    if (!popup) return;
    if (popup.style.display === 'none' || popup.style.display === '') {
        popup.style.display = 'block';
    } else {
        popup.style.display = 'none';
    }
}

function toggleUserMenu(e) {
    if (e) e.stopPropagation();
    var popup = document.getElementById('sidebar-user-popup');
    if (!popup) return;
    if (popup.style.display === 'none' || popup.style.display === '') {
        popup.style.display = 'block';
    } else {
        popup.style.display = 'none';
    }
}

document.addEventListener('click', function(e) {
    var popup = document.getElementById('sidebar-popup');
    var btn = document.getElementById('sidebar-more-btn');
    if (popup && popup.style.display === 'block') {
        if (!popup.contains(e.target) && !btn.contains(e.target)) {
            popup.style.display = 'none';
        }
    }
    var upopup = document.getElementById('sidebar-user-popup');
    var ubtn = document.getElementById('sidebar-user-icon');
    if (upopup && upopup.style.display === 'block') {
        if (!upopup.contains(e.target) && !ubtn.contains(e.target)) {
            upopup.style.display = 'none';
        }
    }
});

function navigateTo(view) {
    if (view === 'config') {
        if (typeof openConfig !== 'undefined') openConfig();
    } else if (view === 'about') {
        if (typeof showAbout !== 'undefined') showAbout();
    } else if (view === 'tools') {
        if (typeof tabManager !== 'undefined') tabManager.createTab('tools', true);
    } else {
        if (typeof tabManager !== 'undefined') tabManager.openOrCreateTab(view);
    }
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
                return '<span class="tab-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg></span>';
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
        if (type === 'home') { this.createTab('home'); return; }
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
            case 'chat':
                tab.state = {
                    sessionId: typeof WikiKnowledge !== 'undefined' ? WikiKnowledge.sessionId : null,
                    chatName: tab.state.chatName || ''
                };
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
                    currentTool: currentTool || 'to_docx',
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
            var closeBtn = '<span class="tab-close" onclick="event.stopPropagation();tabManager.closeTab(\'' + t.id + '\')">✕</span>';
            centerHtml += '<div class="' + cls + '" onclick="tabManager.switchTab(\'' + t.id + '\')" title="' + this._getTabTitle(t) + '">' +
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

    _renderContent: function(id) {
        var tab = this._findById(id);
        if (!tab) return;

        var mc = document.getElementById('main-content');
        if (!mc) return;
        mc.innerHTML = '';

        this._updateSidebar(tab.type === 'home' ? 'home' : tab.type);

        switch (tab.type) {
            case 'home': this._renderHome(tab, mc); break;
            case 'chat': this._renderChat(tab, mc); break;
            case 'fb': this._renderFb(tab, mc); break;
            case 'tools': this._renderTools(tab, mc); break;
        }
    },

    _renderHome: function(tab, container) {
        // 渲染 KB 会话界面作为首页
        var contentDiv = document.createElement('div');
        contentDiv.id = 'content-view';
        contentDiv.style.cssText = 'height:100%;min-height:400px;';
        container.appendChild(contentDiv);

        var self = this;
        var loadKb = function() {
            if (typeof WikiKnowledge !== 'undefined') {
                // 先恢复/清除会话 ID，再初始化 KB
                if (tab.state && tab.state.sessionId) {
                    sessionStorage.setItem('kb_session_id', tab.state.sessionId);
                } else {
                    sessionStorage.removeItem('kb_session_id');
                    WikiKnowledge.sessionId = null;
                    WikiKnowledge.messages = [];
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

    _renderFb: function(tab, container) {
        var contentDiv = document.createElement('div');
        contentDiv.id = 'content-view';
        contentDiv.style.cssText = 'height:100%;min-height:400px;';
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
            }
        });
    },

    _renderTools: function(tab, container) {
        // 渲染工具页面（原首页内容）
        container.innerHTML =
            '<div class="container" id="tools-view">' +
            '<div class="card">' +
            '<h2>选择功能</h2>' +
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
        var savedTool = (tab.state && tab.state.currentTool) || 'to_docx';
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
    }
};

// ==================== 文件库选择器 ====================

var kbSelectorState = {
    kbList: [],
    selectedKbId: null,
    selectedKbName: '',
    selectedDisplayPath: '',
    selectedKbPermission: '',
    selectedSubdir: '',
    currentBreadcrumbs: []
};

window.showKbSelector = async function() {
    var modal = document.getElementById('kbSelectorModal');
    if (!modal) return;
    modal.style.display = 'flex';
    requestAnimationFrame(function() { modal.classList.add('show'); });

    kbSelectorState.selectedKbId = null;
    kbSelectorState.selectedSubdir = '';
    kbSelectorState.currentBreadcrumbs = [];

    await loadKbSelectorList();
};

window.closeKbSelector = function() {
    var modal = document.getElementById('kbSelectorModal');
    if (!modal) return;
    modal.classList.remove('show');
    setTimeout(function() { modal.style.display = 'none'; }, 250);
};

async function loadKbSelectorList() {
    var listDiv = document.getElementById('kbSelectorList');
    if (!listDiv) return;
    listDiv.innerHTML = '<div style="text-align:center;padding:20px;">加载中...</div>';

    try {
        var resp = await apiFetch('/api/fb/list', { method: 'GET' });
        var data = await resp.json();

        if (!data.success || !data.kbs || data.kbs.length === 0) {
            listDiv.innerHTML = '<div style="text-align:center;padding:20px;color:#999;">暂无文件库</div>';
            return;
        }

        kbSelectorState.kbList = data.kbs || [];
        renderKbSelector();
    } catch (e) {
        listDiv.innerHTML = '<div style="text-align:center;padding:20px;color:#dc3545;">加载失败: ' + e.message + '</div>';
    }
}

function renderKbBreadcrumb() {
    var bcDiv = document.getElementById('kbSelectorBreadcrumb');
    if (!bcDiv) return;

    var h = '<a onclick="backToKbList()">文件库</a>';
    for (var i = 0; i < kbSelectorState.currentBreadcrumbs.length; i++) {
        var crumb = kbSelectorState.currentBreadcrumbs[i];
        var isLast = (i === kbSelectorState.currentBreadcrumbs.length - 1);
        h += '<span> / </span>';
        if (isLast) {
            h += '<span class="active">' + escapeHtml(crumb.name) + '</span>';
        } else {
            h += '<a onclick="navigateKbBreadcrumb(' + i + ')">' + escapeHtml(crumb.name) + '</a>';
        }
    }
    bcDiv.innerHTML = h;
}

function renderKbSelector() {
    var listDiv = document.getElementById('kbSelectorList');
    if (!listDiv) return;

    kbSelectorState.currentBreadcrumbs = [];
    renderKbBreadcrumb();

    var h = '';

    if (kbSelectorState.selectedKbId) {
        h += '<div style="text-align:center;padding:20px;color:#999;">加载中...</div>';
    } else {
        var allKbs = kbSelectorState.kbList || [];
        for (var i = 0; i < allKbs.length; i++) {
            h += renderKbSelectorItem(allKbs[i]);
        }
        if (allKbs.length === 0) {
            h += '<div style="text-align:center;padding:20px;color:#999;">暂无文件库</div>';
        }
    }

    listDiv.innerHTML = h;
}

function renderKbSelectorItem(kb) {
    var canEdit = (kb.permission === 'edit' || kb.permission === 'manage');
    var disabledClass = canEdit ? '' : ' disabled';
    var title = canEdit ? (kb.name + ' (' + (kb.permission === 'manage' ? '管理' : '编辑') + ')') : (kb.name + ' (只读)');
    var selClass = (kbSelectorState.selectedKbId === kb.id) ? ' selected' : '';
    var clickHandler = canEdit ? ' onclick="markKbSelected(\'' + kb.id.replace(/'/g, "\\'") + '\')" ondblclick="selectKbForProcessing(\'' + kb.id.replace(/'/g, "\\'") + '\',\'' + escapeHtmlJs(kb.name) + '\',\'' + escapeHtmlJs(kb.display_path || kb.name) + '\',\'' + kb.permission + '\')"' : '';
    return '<div class="fb-selector-item' + disabledClass + selClass + '"' + clickHandler + ' title="' + title + '">📁 ' + escapeHtml(kb.name) + (kb.display_path ? '<span style="font-size:11px;color:#999;margin-left:8px;">' + escapeHtml(kb.display_path) + '</span>' : '') + '</div>';
}

window.markKbSelected = function(kbId) {
    kbSelectorState.selectedKbId = kbId;
    var items = document.querySelectorAll('.fb-selector-item');
    for (var i = 0; i < items.length; i++) {
        items[i].classList.remove('selected');
    }
    event.currentTarget.classList.add('selected');

    // 同步更新显示路径
    var allKbs = kbSelectorState.kbList || [];
    for (var i = 0; i < allKbs.length; i++) {
        if (allKbs[i].id === kbId) {
            kbSelectorState.selectedKbName = allKbs[i].name;
            kbSelectorState.selectedDisplayPath = allKbs[i].display_path || allKbs[i].name;
            kbSelectorState.selectedKbPermission = allKbs[i].permission;
            break;
        }
    }
    _updateWorkdirFromKbState();
};

function escapeHtmlJs(str) {
    if (!str) return '';
    return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

window.selectKbForProcessing = async function(kbId, kbName, displayPath, permission) {
    kbSelectorState.selectedKbId = kbId;
    kbSelectorState.selectedKbName = kbName;
    kbSelectorState.selectedDisplayPath = displayPath;
    kbSelectorState.selectedKbPermission = permission;
    kbSelectorState.selectedSubdir = '';
    kbSelectorState.currentBreadcrumbs = [{ name: kbName, subdir: '' }];

    _updateWorkdirFromKbState();
    await loadKbSubdirs('');
};

async function loadKbSubdirs(subdir) {
    kbSelectorState.selectedSubdir = subdir;

    if (!subdir) {
        kbSelectorState.currentBreadcrumbs = [{ name: kbSelectorState.selectedKbName, subdir: '' }];
    }

    var listDiv = document.getElementById('kbSelectorList');
    if (!listDiv) return;

    try {
        var url = '/api/fb/' + kbSelectorState.selectedKbId + '/local-files';
        if (subdir) url += '?subdir=' + encodeURIComponent(subdir);

        var resp = await apiFetch(url, { method: 'GET' });
        var data = await resp.json();

        if (!data.success) {
            listDiv.innerHTML = '<div style="text-align:center;padding:20px;color:#dc3545;">' + (data.message || '加载失败') + '</div>';
            return;
        }

        var categories = data.categories || [];
        renderKbSubdirView(categories);
    } catch (e) {
        listDiv.innerHTML = '<div style="text-align:center;padding:20px;color:#dc3545;">加载失败: ' + e.message + '</div>';
    }
}

function renderKbSubdirView(categories) {
    var listDiv = document.getElementById('kbSelectorList');
    if (!listDiv) return;

    renderKbBreadcrumb();

    var h = '';

    if (categories.length > 0) {
        for (var i = 0; i < categories.length; i++) {
            var cat = categories[i];
            var selClass = (kbSelectorState.selectedSubdir === cat.path) ? ' selected' : '';
            h += '<div class="fb-subdir-item' + selClass + '" onclick="selectKbSubdir(\'' + cat.path.replace(/'/g, "\\'") + '\')" ondblclick="enterKbSubdir(\'' + cat.path.replace(/'/g, "\\'") + '\',\'' + escapeHtmlJs(cat.name) + '\')">';
            h += '<span>📁 ' + escapeHtml(cat.name) + '</span>';
            h += '</div>';
        }
    } else {
        var rootSelected = (kbSelectorState.selectedSubdir === '');
        h += '<div class="fb-subdir-item' + (rootSelected ? ' selected' : '') + '" onclick="selectKbSubdir(\'\')">';
        h += '<span>📂 根目录</span>';
        h += '</div>';
    }

    listDiv.innerHTML = h;
}

window.backToKbList = function() {
    kbSelectorState.selectedKbId = null;
    kbSelectorState.selectedKbName = '';
    kbSelectorState.selectedSubdir = '';
    kbSelectorState.currentBreadcrumbs = [];
    renderKbSelector();
};

window.enterKbSubdir = function(subdir, name) {
    var exists = false;
    for (var i = 0; i < kbSelectorState.currentBreadcrumbs.length; i++) {
        if (kbSelectorState.currentBreadcrumbs[i].subdir === subdir) {
            exists = true;
            break;
        }
    }
    if (!exists) {
        kbSelectorState.currentBreadcrumbs.push({ name: name, subdir: subdir });
    }
    kbSelectorState.selectedSubdir = subdir;
    loadKbSubdirs(subdir);
};

window.selectKbSubdir = function(subdir) {
    kbSelectorState.selectedSubdir = subdir || '';

    if (subdir) {
        var parts = subdir.split('/');
        kbSelectorState.currentBreadcrumbs = [{ name: kbSelectorState.selectedKbName, subdir: '' }];
        for (var i = 0; i < parts.length; i++) {
            kbSelectorState.currentBreadcrumbs.push({ name: parts[i], subdir: parts.slice(0, i + 1).join('/') });
        }
    } else {
        kbSelectorState.currentBreadcrumbs = [{ name: kbSelectorState.selectedKbName, subdir: '' }];
    }

    renderKbBreadcrumb();
    _updateWorkdirFromKbState();

    var items = document.querySelectorAll('.fb-subdir-item');
    for (var i = 0; i < items.length; i++) {
        items[i].classList.remove('selected');
    }
    var target = event && event.currentTarget;
    if (target) target.classList.add('selected');
};

window.navigateKbBreadcrumb = async function(index) {
    var crumb = kbSelectorState.currentBreadcrumbs[index];
    kbSelectorState.currentBreadcrumbs = kbSelectorState.currentBreadcrumbs.slice(0, index + 1);
    kbSelectorState.selectedSubdir = crumb.subdir || '';
    await loadKbSubdirs(kbSelectorState.selectedSubdir);
};

// 实时更新输入框显示当前文件库选择路径
function _updateWorkdirFromKbState() {
    if (!kbSelectorState.selectedKbId) return;
    var displayText = kbSelectorState.selectedDisplayPath;
    if (kbSelectorState.selectedSubdir) {
        displayText += '/' + kbSelectorState.selectedSubdir;
    }
    var workdirInput = document.getElementById('workdir');
    workdirInput.value = displayText;
    workdirInput.setAttribute('data-fb-id', kbSelectorState.selectedKbId);
    workdirInput.setAttribute('data-fb-subdir', kbSelectorState.selectedSubdir);
}

window.confirmKbSelection = function() {
    if (!kbSelectorState.selectedKbId) {
        showToast('请先选择一个文件库', 'error');
        return;
    }

    _updateWorkdirFromKbState();

    closeKbSelector();

    var workdirInput = document.getElementById('workdir');
    if (currentTool && workdirInput) loadFileList(workdirInput.value, currentTool);
};

// ==================== 文件库选择器 ====================