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
                    const e = escapeHtmlJs(f);
                    return `<span class="file-tag" onclick="selectRadio(this, 'orig', '${e}')">${f}</span>`;
                }).join('');
                rightList.innerHTML = fileNames.map(f => {
                    const e = escapeHtmlJs(f);
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
                    const e = escapeHtml(f.name);
                    return `<span class="file-tag" data-filename="${e}" onclick="toggleFileTag(this)">${f.name}</span>`;
                }).join('');
                rightList.innerHTML = files.slice(mid).map(f => {
                    const e = escapeHtml(f.name);
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
                    // 持久化最后选择的目录
                    saveLastWorkdir(path);
                }
            } catch (e) {
                console.error('selectDirectory error:', e);
                showToast('选择目录失败', 'error');
            }
        };

        /** 将 last_workdir 保存到服务端配置（非阻塞） */
        function saveLastWorkdir(dir) {
            if (!userConfig) userConfig = {};
            userConfig.last_workdir = dir;
            localStorage.setItem('userConfig', JSON.stringify(userConfig));
            // 静默保存到服务端，不阻塞 UI
            apiFetch('/save_config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({config: userConfig}),
                showError: false
            }).catch(function() {});
        }

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
                // 文档比较完成后自动打开结果文件（仅 pywebview 桌面模式）
                if (currentTool === 'to_compare' && typeof pywebview !== 'undefined') {
                    var origName = selectedFiles && selectedFiles.length > 0 ? selectedFiles[0] : '';
                    var outputName = '差异标注-' + origName;
                    try { pywebview.api.openFileWithOsApp(selDir.path + '/' + outputName); } catch (e) {}
                }
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
        var userConfig = null;

        // 打开配置弹窗
        window.openConfig = async function() {
            const modal = document.getElementById('configModal');
            modal.style.display = 'flex';
            requestAnimationFrame(() => {
                modal.classList.add('show');
                modal.addEventListener('click', function(e) {
                    if (e.target === modal) closeConfig();
                }, { once: true });
            });
            await loadUserConfig();
        };

        window.closeConfig = function() {
            const modal = document.getElementById('configModal');
            modal.classList.remove('show');
            setTimeout(() => { modal.style.display = 'none'; }, 200);
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
                const escJsName = escapeHtmlJs(companyName);

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
                        const val = obj[key][subKey];
                        if (Array.isArray(val)) {
                            yaml += `  ${subKey}: [${val.join(', ')}]\n`;
                        } else {
                            yaml += `  ${subKey}: ${val}\n`;
                        }
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
            // YAML 内联列表 [50, 30]
            if (val.startsWith('[') && val.endsWith(']')) {
                return val.slice(1, -1).split(',').map(v => {
                    const trimmed = v.trim();
                    const num = Number(trimmed);
                    return isNaN(num) || trimmed === '' ? trimmed : num;
                });
            }
            const num = Number(val);
            if (!isNaN(num) && val !== '') return num;
            if (!isNaN(num) && val !== '') return num;
            if ((val.startsWith('"') && val.endsWith('"')) ||
                (val.startsWith("'") && val.endsWith("'"))) {
                return val.slice(1, -1);
            }
            return val;
        }

        // ==================== 关于弹窗 ====================

        // 项目对外链接（集中定义，便于维护）
        var ABOUT_LINKS = {
            project: 'https://github.com/doonly1/Docflowing',
            docs: 'https://doonly1.github.io/Docflowing/',
            releases: 'https://github.com/doonly1/Docflowing/releases/latest',
            license: 'https://github.com/doonly1/Docflowing/blob/main/LICENSE'
        };

        window.showAbout = function() {
            const overlay = document.getElementById('aboutOverlay');
            overlay.style.display = 'flex';
            overlay.innerHTML = `
                <div id="about-dialog" style="background:#fff;border-radius:12px;padding:22px 26px;max-width:420px;width:88%;box-shadow:0 4px 20px rgba(0,0,0,0.1);border:1px solid rgba(0,0,0,0.08);font-size:13px;line-height:1.8;transform:scale(0.95);transition:transform 0.2s ease;">
                    <div style="text-align:center;margin-bottom:4px;">
                        <h2 style="margin:4px 0 0;font-size:20px;color:#1a1a2e;">文澜</h2>
                        <div style="font-size:11px;color:#999;">Docflowing · Document Workflow</div>
                    </div>
                    <div style="text-align:center;font-size:11px;color:#bbb;margin:2px 0 10px;">公文处理与 AI 知识管理平台 · <span id="aboutVersion">版本读取中…</span></div>
                    <div style="background:#f7f7fa;border-radius:8px;padding:10px 14px;font-size:12px;color:#555;margin-bottom:14px;">
                        文档处理工具 · 文件库 · 知识库 AI 会话 · P2P 共享。<br>
                        数据本地保存，离线可用；AI 功能需自行配置 LLM。
                    </div>
                    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px;">
                        <a href="` + ABOUT_LINKS.project + `" target="_blank" style="flex:1;min-width:160px;text-align:center;padding:7px 8px;background:#fff;border:1px solid #e94560;color:#e94560;border-radius:6px;font-size:12px;text-decoration:none;cursor:pointer;">GitHub 主页</a>
                        <a href="` + ABOUT_LINKS.docs + `" target="_blank" style="flex:1;min-width:160px;text-align:center;padding:7px 8px;background:#fff;border:1px solid #e94560;color:#e94560;border-radius:6px;font-size:12px;text-decoration:none;cursor:pointer;">在线文档</a>
                        <a href="` + ABOUT_LINKS.releases + `" target="_blank" style="flex:1;min-width:160px;text-align:center;padding:7px 8px;background:#fff;border:1px solid #e94560;color:#e94560;border-radius:6px;font-size:12px;text-decoration:none;cursor:pointer;">更新日志</a>
                        <a href="` + ABOUT_LINKS.license + `" target="_blank" style="flex:1;min-width:160px;text-align:center;padding:7px 8px;background:#fff;border:1px solid #e94560;color:#e94560;border-radius:6px;font-size:12px;text-decoration:none;cursor:pointer;">开源许可</a>
                    </div>
                    <div style="text-align:center;margin-top:4px;">
                        <button onclick="closeAbout()" style="padding:5px 28px;background:#e94560;color:white;border:none;border-radius:4px;font-size:13px;cursor:pointer;">确定</button>
                    </div>
                </div>
            `;
            requestAnimationFrame(() => {
                overlay.style.opacity = '1';
                var dialog = document.getElementById('about-dialog');
                if (dialog) dialog.style.transform = 'scale(1)';
            });
            overlay.addEventListener('click', function(e) { if (e.target === overlay) closeAbout(); });

            // 异步补版本号：优先 updater 状态里的 current_version，桌面/浏览器通用
            var verHost = document.getElementById('aboutVersion');
            (async function() {
                try {
                    var r = await apiFetch('/api/updater/status', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({}), timeout: 8000, showError: false
                    });
                    var j = await r.json();
                    var v = (j && j.status && j.status.current_version) || '';
                    if (v) verHost.textContent = 'v' + v;
                    else verHost.textContent = '';
                } catch (e) {
                    verHost.textContent = '';
                }
            })();
        };

        window.closeAbout = function() {
            const overlay = document.getElementById('aboutOverlay');
            overlay.style.opacity = '0';
            setTimeout(() => { overlay.style.display = 'none'; overlay.innerHTML = ''; }, 200);
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
                    // 同步关闭行为到 Electron 主进程
                    if (window.electronAPI && window.electronAPI.setCloseAction) {
                        window.electronAPI.setCloseAction(appSettings.close_action || 'exit');
                    }
                }
            } catch (e) {
                console.log('加载设置失败:', e);
            }

            const overlay = document.getElementById('settingsOverlay');
            overlay.style.display = 'flex';
            overlay.innerHTML = `
                <div style="background:#fff;border-radius:12px;padding:18px 20px;max-width:380px;width:85%;box-shadow:0 4px 20px rgba(0,0,0,0.1);border:1px solid rgba(0,0,0,0.08);transform:scale(0.95);transition:transform 0.2s ease;">
                    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1a2e;border-bottom:1px solid #eee;padding-bottom:8px;">应用设置</h2>

                    <div style="margin-bottom:14px;">
                        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;color:#333;">
                            <input type="checkbox" id="settingAutostart" ${appSettings.autostart ? 'checked' : ''}>
                            开机自启动
                        </label>
                        <div style="font-size:11px;color:#999;margin:4px 0 0 24px;">Automatically launches Docflowing desktop on startup</div>
                    </div>

                    <div style="margin-bottom:14px;">
                        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;color:#333;">
                            <input type="checkbox" id="settingWordKeepAlive" ${appSettings.word_keep_alive ? 'checked' : ''}>
                            Word 保活
                        </label>
                        <div style="font-size:11px;color:#999;margin:4px 0 0 24px;">保持 Word 进程常驻，提升响应速度</div>
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

                    <!-- 应用更新（内容由 updater.js 就地渲染并实时刷新） -->
                    <div id="settingsUpdateCard"></div>

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

            // 填「应用更新」卡片，并注册回调让下载进度实时刷新
            _renderUpdateCard();
            if (typeof DocflowingUpdater !== 'undefined') {
                DocflowingUpdater._settingsHook = function () { _renderUpdateCard(); };
            }
        };

        function _renderUpdateCard() {
            const host = document.getElementById('settingsUpdateCard');
            if (!host) return;
            if (typeof DocflowingUpdater === 'undefined') return;
            try {
                host.innerHTML = DocflowingUpdater.renderSettingsSection();
            } catch (e) {
                host.innerHTML = '';
            }
        }

        window.closeAppSettings = function() {
            const overlay = document.getElementById('settingsOverlay');
            overlay.style.opacity = '0';
            overlay.querySelector('div').style.transform = 'scale(0.95)';
            setTimeout(() => { overlay.style.display = 'none'; overlay.innerHTML = ''; }, 200);
            if (typeof DocflowingUpdater !== 'undefined') DocflowingUpdater._settingsHook = null;
        };

        window.saveAppSettings = async function() {
            const autostart = document.getElementById('settingAutostart').checked;
            const closeAction = document.querySelector('input[name="closeAction"]:checked').value;
            const wordKeepAlive = document.getElementById('settingWordKeepAlive').checked;

            const newSettings = {
                autostart: autostart,
                close_action: closeAction,
                word_keep_alive: wordKeepAlive
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
                    // 同步关闭行为到 Electron 主进程
                    if (window.electronAPI && window.electronAPI.setCloseAction) {
                        window.electronAPI.setCloseAction(newSettings.close_action || 'exit');
                    }
                    if (window.electronAPI && window.electronAPI.setWordKeepAlive) {
                        window.electronAPI.setWordKeepAlive(wordKeepAlive);
                    }
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
        if (typeof tabManager !== 'undefined') tabManager.openOrCreateTab('tools');
    } else {
        if (typeof tabManager !== 'undefined') tabManager.openOrCreateTab(view);
    }
}

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
    requestAnimationFrame(function() {
        modal.classList.add('show');
        modal.addEventListener('click', function(e) {
            if (e.target === modal) closeKbSelector();
        }, { once: true });
    });

    kbSelectorState.selectedKbId = null;
    kbSelectorState.selectedSubdir = '';
    kbSelectorState.currentBreadcrumbs = [];

    await loadKbSelectorList();
};

window.closeKbSelector = function() {
    var modal = document.getElementById('kbSelectorModal');
    if (!modal) return;
    modal.classList.remove('show');
    setTimeout(function() { modal.style.display = 'none'; }, 200);
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
    var clickHandler = canEdit ? ' onclick="markKbSelected(\'' + escapeHtmlJs(kb.id) + '\', event)" ondblclick="selectKbForProcessing(\'' + escapeHtmlJs(kb.id) + '\',\'' + escapeHtmlJs(kb.name) + '\',\'' + escapeHtmlJs(kb.display_path || kb.name) + '\',\'' + kb.permission + '\')"' : '';
    return '<div class="fb-selector-item' + disabledClass + selClass + '"' + clickHandler + ' title="' + title + '">📁 ' + escapeHtml(kb.name) + (kb.display_path ? '<span style="font-size:11px;color:#999;margin-left:8px;">' + escapeHtml(kb.display_path) + '</span>' : '') + '</div>';
}

window.markKbSelected = function(kbId, event) {
    kbSelectorState.selectedKbId = kbId;
    var items = document.querySelectorAll('.fb-selector-item');
    for (var i = 0; i < items.length; i++) {
        items[i].classList.remove('selected');
    }
    if (event && event.currentTarget) event.currentTarget.classList.add('selected');

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
            h += '<div class="fb-subdir-item' + selClass + '" onclick="selectKbSubdir(\'' + escapeHtmlJs(cat.path) + '\', event)" ondblclick="enterKbSubdir(\'' + escapeHtmlJs(cat.path) + '\',\'' + escapeHtmlJs(cat.name) + '\')">';
            h += '<span>📁 ' + escapeHtml(cat.name) + '</span>';
            h += '</div>';
        }
    } else {
        var rootSelected = (kbSelectorState.selectedSubdir === '');
        h += '<div class="fb-subdir-item' + (rootSelected ? ' selected' : '') + '" onclick="selectKbSubdir(\'\', event)">';
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

window.selectKbSubdir = function(subdir, event) {
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
    if (currentTool && workdirInput) loadFileList(null, currentTool);
};

// ==================== 文件库选择器 ====================