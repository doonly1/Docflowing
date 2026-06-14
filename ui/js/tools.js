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
