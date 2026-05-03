// ==================== 全局错误捕获 ====================
        window.addEventListener('error', function(e) {
            console.error('[GLOBAL ERROR]', e.message, 'at', e.filename, ':', e.lineno);
        });
        window.addEventListener('unhandledrejection', function(e) {
            console.error('[UNHANDLED REJECTION]', e.reason);
        });

        // ==================== Token 管理 ====================
        let authToken = localStorage.getItem('docproc_token');
        let authUsername = localStorage.getItem('docproc_username');

        function getToken() {
            return authToken;
        }

        function setAuth(token, username) {
            authToken = token;
            authUsername = username;
            localStorage.setItem('docproc_token', token);
            localStorage.setItem('docproc_username', username);
            document.getElementById('authOverlay').style.display = 'none';
            document.getElementById('userInfo').textContent = '👤 ' + username;
            initApp();
        }

        function clearAuth() {
            authToken = null;
            authUsername = null;
            localStorage.removeItem('docproc_token');
            localStorage.removeItem('docproc_username');
            localStorage.removeItem('docproc_client_id');
            localStorage.removeItem('workdir');
            document.getElementById('authOverlay').style.display = 'flex';
            document.getElementById('userInfo').textContent = '';
        }

        function apiHeaders() {
            return {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + (authToken || '')
            };
        }

        async function apiFetch(url, options) {
            options = options || {};
            if (!options.headers) options.headers = {};
            options.headers['Authorization'] = 'Bearer ' + (authToken || '');
            var resp = await fetch(url, options);
            if (resp.status === 401) {
                clearAuth();
                throw new Error('登录已过期，请重新登录');
            }
            return resp;
        }

        // ==================== 认证处理 ====================
        let authMode = 'login';

        window.handleAuth = async function() {
            const username = document.getElementById('authUsername').value.trim();
            const password = document.getElementById('authPassword').value.trim();
            const errorDiv = document.getElementById('authError');
            const btn = document.getElementById('authSubmitBtn');

            if (!username || !password) {
                errorDiv.textContent = '请填写用户名和密码';
                errorDiv.style.display = 'block';
                return;
            }

            btn.disabled = true;
            btn.textContent = authMode === 'register' ? '注册中...' : '登录中...';
            errorDiv.style.display = 'none';

            try {
                const url = authMode === 'register' ? '/api/register' : '/api/login';
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password})
                });
                const data = await response.json();

                if (data.success) {
                    setAuth(data.token, data.username);
                    document.getElementById('authPassword').value = '';
                } else {
                    errorDiv.textContent = data.message || '操作失败';
                    errorDiv.style.display = 'block';
                }
            } catch (e) {
                errorDiv.textContent = '网络错误: ' + e.message;
                errorDiv.style.display = 'block';
            }

            btn.disabled = false;
            btn.textContent = authMode === 'register' ? '注册' : '登录';
        };

        window.toggleAuthMode = function() {
            authMode = authMode === 'login' ? 'register' : 'login';
            document.getElementById('authTitle').textContent = authMode === 'register' ? '注册' : '登录';
            document.getElementById('authSubmitBtn').textContent = authMode === 'register' ? '注册' : '登录';
            document.getElementById('authSwitchText').textContent = authMode === 'register' ? '已有账号？' : '没有账号？';
            document.getElementById('authSwitchLink').textContent = authMode === 'register' ? '立即登录' : '立即注册';
            document.getElementById('authError').style.display = 'none';
        };

        window.handleLogout = async function() {
            if (!confirm('确定要退出登录吗？')) return;

            try {
                await apiFetch('/api/logout', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({})
                });
            } catch (e) {}

            clearAuth();
            document.getElementById('authOverlay').style.display = 'flex';
        };

        document.getElementById('authPassword').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') handleAuth();
        });

        // ==================== 远程/本地模式检测 ====================
        function isRemoteMode() {
            const hostname = window.location.hostname;
            return hostname !== 'localhost' && hostname !== '127.0.0.1';
        }

        function updateModeUI() {
            const remote = isRemoteMode();
            const selectBtn = document.getElementById('selectFolderBtn');
            const remoteGroup = document.getElementById('remoteUploadGroup');
            const openBtn = document.getElementById('openDirBtn');
            const downloadBtn = document.getElementById('downloadBtn');

            if (remote) {
                selectBtn.textContent = '选择文件夹';
                remoteGroup.style.display = 'block';
                openBtn.style.display = 'none';
                downloadBtn.style.display = 'inline-block';
            } else {
                selectBtn.textContent = '选择文件夹';
                remoteGroup.style.display = 'none';
                openBtn.style.display = 'inline-block';
                downloadBtn.style.display = 'none';
            }
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

        let currentTool = '';

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

                const workdir = document.getElementById('workdir').value.trim();
                if (workdir) loadFileList(workdir, tool);
            } catch (e) {
                console.error('selectTool error:', e);
            }
        }

        // ==================== 文件列表面板（统一双列） ====================
        async function loadFileList(workdir, tool) {
            if (!tool) return;
            const panel = document.getElementById('filePanel');
            const label = document.getElementById('fileLabel');
            const leftList = document.getElementById('leftList');
            const rightList = document.getElementById('rightList');

            const isIndex = (tool === 'to_index');
            const isCompare = (tool === 'to_compare');
            label.textContent = isIndex ? '📂目录文件：' : isCompare ? '👇原稿 / 终稿：' : '📂目录文件：';

            const body = isRemoteMode()
                ? {tool}
                : {workdir, tool};

            const filesRes = await apiFetch('/list_files', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });
            const filesData = await filesRes.json();

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

        // 清理工作区文件
        window.clearWorkspace = async function() {
            if (isRemoteMode()) {
                if (!confirm('确定要清理所有文件吗？清理后不可恢复。')) return;
                try {
                    const res = await apiFetch('/clear_workspace', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({})
                    });
                    const data = await res.json();
                    if (data.success) {
                        // 刷新文件列表
                        await loadFileList(null, currentTool);
                    } else {
                        alert('清理失败: ' + (data.message || ''));
                    }
                } catch (e) {
                    alert('清理失败: ' + e.message);
                }
            } else {
                // 本地模式确认提示
                if (!confirm('确定要清空当前目录中的输出文件吗？原始文件不受影响。')) return;
                alert('本地模式请手动删除文件。');
            }
        };

        // 打开工作目录（本地模式） / 查看文件（远程模式）
        window.openWorkdir = async function() {
            if (isRemoteMode()) {
                downloadResults(); // 远程模式：打开=下载
                return;
            }
            const workdir = document.getElementById('workdir').value.trim();
            if (!workdir) { alert('请先选择工作目录'); return; }
            await fetch('/open_folder', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({path: workdir})
            });
        };

        // ==================== 选择文件夹 / 上传 ====================
        window.selectFolder = async function() {
            if (isRemoteMode()) {
                // 远程模式：触发浏览器文件夹选择
                document.getElementById('folderInput').click();
            } else {
                // 本地模式：服务端 tkinter 对话框
                await selectLocalFolder();
            }
        };

        async function selectLocalFolder() {
            try {
                const response = await fetch('/select_folder', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    const workdir = data.path;
                    document.getElementById('workdir').value = workdir;
                    localStorage.setItem('workdir', workdir);

                    apiFetch('/save_workdir', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({workdir})
                    });

                    if (currentTool) await loadFileList(workdir, currentTool);
                }
            } catch (error) {
                console.error('选择文件夹失败:', error);
            }
        }

        // 远程模式：上传文件夹中的所有文件（或构建索引时仅上传元数据）
        async function handleRemoteUpload(event) {
            const files = event.target.files;
            if (!files || files.length === 0) return;

            const progress = document.getElementById('uploadProgress');
            progress.style.display = 'block';
            progress.innerHTML = '正在处理...';

            // 构建索引模式：只上传元数据，不上传文件内容
            if (currentTool === 'to_index') {
                await handleIndexMetadataOnly(files, progress);
                return;
            }

            progress.innerHTML = '正在上传 <span id="uploadCount">0</span> 个文件...';

            const extensions = {
                'to_docx': ['.pdf', '.doc', '.docx', '.txt', '.html', '.htm', '.md'],
                'to_compare': ['.docx', '.doc'],
                'to_pdf': ['.docx', '.doc'],
                'to_pageNum': ['.docx', '.doc'],
                'to_redhead': ['.docx']
            };
            const allowedExt = extensions[currentTool] || ['.docx'];

            const formData = new FormData();
            let uploadCount = 0;
            for (const file of files) {
                const ext = '.' + file.name.split('.').pop().toLowerCase();
                if (allowedExt.length === 0 || allowedExt.includes(ext)) {
                    formData.append('files', file);
                    uploadCount++;
                }
            }

            if (uploadCount === 0) {
                progress.innerHTML = '<span style="color: #dc3545;">✗ 没有支持的文件类型</span>';
                setTimeout(() => { progress.style.display = 'none'; }, 3000);
                return;
            }

            formData.append('tool', currentTool);
            formData.append('token', authToken);

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 60000);

            try {
                const response = await fetch('/upload_files', {
                    method: 'POST',
                    headers: {'Authorization': 'Bearer ' + (authToken || '')},
                    body: formData,
                    signal: controller.signal
                });
                clearTimeout(timeoutId);

                if (!response.ok) {
                    throw new Error('服务器返回状态码: ' + response.status);
                }
                const data = await response.json();
                if (data.success) {
                    progress.innerHTML = `<span style="color: #28a745;">✓ 上传完成 ${data.file_count} 个文件</span>`;
                    await loadFileList(null, currentTool);
                    setTimeout(() => { progress.style.display = 'none'; }, 3000);
                } else {
                    throw new Error(data.message || '上传失败');
                }
            } catch (error) {
                clearTimeout(timeoutId);
                let msg = error.message;
                if (error.name === 'AbortError') {
                    msg = '上传超时（60秒），文件太多或太大，请分批上传';
                }
                progress.innerHTML = `<span style="color: #dc3545;">✗ 上传失败: ${msg}</span>`;
                console.error('Upload error:', error);
            }
        }

        // 构建索引专用：只上传元数据，不上传文件内容
        async function handleIndexMetadataOnly(files, progress) {
            progress.innerHTML = '正在提取文件信息...';

            // 提取文件夹名称（从第一个文件的 webkitRelativePath 获取）
            let folderName = 'unknown';
            const metadataList = [];
            
            for (const file of files) {
                // 获取相对路径（如 "folderName/sub/file.docx"）
                const relativePath = file.webkitRelativePath || file.name;
                const pathParts = relativePath.split('/');
                
                // 第一层为文件夹名
                if (pathParts.length > 1 && folderName === 'unknown') {
                    folderName = pathParts[0];
                }

                // 提取元数据（不读取文件内容）
                metadataList.push({
                    name: pathParts[pathParts.length - 1],
                    path: relativePath,
                    size: file.size,
                    lastModified: file.lastModified
                });
            }

            if (metadataList.length === 0) {
                progress.innerHTML = '<span style="color: #dc3545;">✗ 未找到文件</span>';
                setTimeout(() => { progress.style.display = 'none'; }, 3000);
                return;
            }

            progress.innerHTML = `正在索引 ${metadataList.length} 个文件...`;

            try {
                const response = await apiFetch('/build_index_from_metadata', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        metadata: metadataList,
                        folder_name: folderName
                    })
                });

                const data = await response.json();
                if (data.success) {
                    progress.innerHTML = `<span style="color: #28a745;">✓ 索引完成，共 ${data.file_count} 个文件</span>`;
                    // 刷新文件列表以显示生成的索引文件
                    await loadFileList(null, currentTool);
                    setTimeout(() => { progress.style.display = 'none'; }, 3000);
                } else {
                    throw new Error(data.message || '索引生成失败');
                }
            } catch (error) {
                progress.innerHTML = `<span style="color: #dc3545;">✗ 索引失败: ${error.message}</span>`;
                console.error('Index error:', error);
            }
        }

        // 下载结果（打包 ZIP）
        window.downloadResults = async function() {
            var folderName = document.getElementById('workdir').value.trim() || 'results';
            try {
                var response = await apiFetch('/download_results', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({folder_name: folderName})
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
            const workdir = document.getElementById('workdir').value.trim();
            const resultDiv = document.getElementById('result');

            if (!isRemoteMode() && !workdir) {
                resultDiv.className = 'error';
                resultDiv.textContent = '请选择工作目录';
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

            const userConfig = getUserConfig();
            const bodyData = {
                tool: currentTool
            };
            if (isRemoteMode()) {
                // token will be in header
            } else {
                bodyData.workdir = workdir;
            }
            if (selectedFiles.length > 0) bodyData.files = selectedFiles;
            if (userConfig) bodyData.userConfig = userConfig;

            try {
                const response = await apiFetch('/run_tool_with_config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(bodyData)
                });

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
                // 刷新文件列表
                if (workdir) loadFileList(workdir, currentTool);
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
        const workdirInput = document.getElementById('workdir');
        workdirInput.addEventListener('dragover', function(e) { e.preventDefault(); });
        workdirInput.addEventListener('drop', function(e) { e.preventDefault(); });

        // ==================== 配置管理 ====================
        let userConfig = null;
        let isUsingUserConfig = false;

        async function initConfig() {
            document.getElementById('useUserConfig').checked = true;

            const savedConfig = localStorage.getItem('userConfig');
            if (savedConfig) {
                try {
                    const parsed = JSON.parse(savedConfig);
                    if (parsed && (Object.keys(parsed).length > 0)) {
                        userConfig = parsed;
                        isUsingUserConfig = true;
                    } else {
                        userConfig = null;
                    }
                } catch (e) {
                    userConfig = null;
                }
            }

            try {
                const response = await apiFetch('/get_config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({})
                });
                const data = await response.json();
                if (data.success && data.config) {
                    userConfig = data.config;
                    if (userConfig.last_workdir) delete userConfig.last_workdir;
                    isUsingUserConfig = true;
                    localStorage.setItem('userConfig', JSON.stringify(userConfig));

                    if (data.config.last_workdir) {
                        document.getElementById('workdir').value = data.config.last_workdir;
                        localStorage.setItem('workdir', data.config.last_workdir);
                        if (currentTool) loadFileList(data.config.last_workdir, currentTool);
                    }
                }
            } catch (e) {
                console.log('从后端加载配置失败:', e);
                if (!userConfig) {
                    userConfig = {
                        compare: {
                            sentence_similarity_threshold: 0.40,
                            para_similarity_threshold: 0.40,
                            short_para_char_threshold: 50
                        }
                    };
                    isUsingUserConfig = true;
                }
            }
        }

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

        window.toggleUserConfig = function() {
            isUsingUserConfig = document.getElementById('useUserConfig').checked;
            if (!isUsingUserConfig) {
                userConfig = null;
                localStorage.removeItem('userConfig');
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
                    if (userConfig.last_workdir) delete userConfig.last_workdir;
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
            if (confirm(`确定要删除 "${companyName}" 的配置吗？`)) {
                delete userConfig[companyName];
                loadCompanyConfigForm(userConfig);
                document.getElementById('rawYamlText').value = objectToYaml(userConfig);
            }
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
                isUsingUserConfig = true;
                document.getElementById('useUserConfig').checked = true;

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
                alert('保存配置失败: ' + error.message);
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
                } else if (key === 'last_workdir') {
                    continue;
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

        window.getUserConfig = function() {
            if (isUsingUserConfig && userConfig) return userConfig;
            return null;
        };

        // ==================== 关于弹窗 ====================
        window.showAbout = function() {
            const overlay = document.getElementById('aboutOverlay');
            overlay.style.display = 'flex';
            overlay.innerHTML = `
                <div style="background:#fff;border-radius:12px;padding:20px 24px;max-width:360px;width:85%;box-shadow:0 4px 20px rgba(0,0,0,0.1);border:1px solid rgba(0,0,0,0.08);font-size:13px;line-height:1.8;">
                    <div style="text-align:center;margin-bottom:12px;">
                        <h2 style="margin:6px 0 2px;font-size:18px;color:#1a1a2e;">文枢</h2>
                        <div style="font-size:11px;color:#999;">DocProc · 文档处理工具集</div>
                    </div>
                    <div style="color:#444;font-size:12px;line-height:2;">
                        <div>批量提取 · 文件索引 · 文档比较</div>
                        <div>批量转化 · 添加页码 · 文件套红</div>
                    </div>
                    <div style="margin-top:10px;padding-top:10px;border-top:1px solid #eee;font-size:12px;color:#666;line-height:2;">
                        <div style="display:flex;gap:6px;"><span style="width:16px;text-align:center;">🏠</span><a href="https://github.com/doonly1/DocProc" style="color:#e94560;text-decoration:none;" target="_blank">github.com/doonly1/DocProc</a></div>
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

        // 链接拦截（防止在 iframe/WebView 内导航）
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a');
            if (!link) return;
            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
            e.preventDefault();
            window.open(href, '_blank');
        });

        async function initApp() {
            updateModeUI();
            selectTool('to_compare');

            const savedPath = localStorage.getItem('workdir');
            if (savedPath) {
                document.getElementById('workdir').value = savedPath;
            }

            await initConfig();

            if (isRemoteMode()) {
                document.getElementById('workdir').value = (authUsername || 'default').slice(0, 8) + '/workdir';
            }
        }

        document.addEventListener('DOMContentLoaded', async function() {
            if (authToken) {
                document.getElementById('authOverlay').style.display = 'none';
                document.getElementById('userInfo').textContent = '👤 ' + (authUsername || '');
                initApp();
            } else {
                document.getElementById('authOverlay').style.display = 'flex';
                document.getElementById('authUsername').focus();
            }
        });

function navigateTo(view) {
    document.querySelectorAll('.sidebar-nav-item').forEach(function(el) {
        el.classList.remove('active');
    });
    var navItem = document.querySelector('.sidebar-nav-item[data-view="' + view + '"]');
    if (navItem) navItem.classList.add('active');

    var kbView = document.getElementById('kb-view');
    var homeView = document.getElementById('home-view');

    if (view === 'home') {
        if (kbView) kbView.style.display = 'none';
        if (homeView) homeView.style.display = '';
        if (typeof KnowledgeBase !== 'undefined') KnowledgeBase.currentKbId = null;
    } else if (view === 'kb') {
        if (!authToken) { alert('请先登录'); return; }
        if (homeView) homeView.style.display = 'none';
        if (kbView) kbView.style.display = '';
        if (typeof KnowledgeBase !== 'undefined') KnowledgeBase.init();
    } else if (view === 'config') {
        if (typeof openConfig !== 'undefined') openConfig();
    } else if (view === 'about') {
        if (typeof showAbout !== 'undefined') showAbout();
    }
}