const { app, BrowserWindow, ipcMain, dialog, shell, Menu, Tray, nativeImage } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const { StringDecoder } = require('string_decoder');

// ==================== 配置 ====================
const PORT = parseInt(process.env.PORT || '5000', 10);
const IS_PACKAGED = app.isPackaged;
const DEV_MODE = process.env.DOCFLOW_DEV === '1';
const OPEN_DEVTOOLS = DEV_MODE;
const ROOT_DIR = IS_PACKAGED ? path.dirname(app.getPath('exe')) : path.join(__dirname, '..');
const APP_NAME = '文枢';

// ==================== 全局状态 ====================
let mainWindow = null;
let pythonProcess = null;
let appTray = null;
let isQuitting = false;
let closeAction = 'exit'; // 默认与后端 settings.py 一致

// ==================== Python 后端管理 ====================
function getPythonCommand() {
    if (IS_PACKAGED) {
        // 生产模式：使用 PyInstaller 编译的 exe
        const exePath = path.join(process.resourcesPath, 'backend', 'backend.exe');
        return {
            cmd: exePath,
            args: [],
            cwd: path.dirname(exePath)
        };
    }
    // 开发模式：使用系统 python
    return {
        cmd: process.platform === 'win32' ? 'python' : 'python3',
        args: ['app_server.py'],
        cwd: ROOT_DIR
    };
}

function startPythonBackend() {
    return new Promise((resolve, reject) => {
        const { cmd, args, cwd } = getPythonCommand();
        // 运行时数据目录：打包模式走 Electron userData 目录，
        // 开发模式留空让 Python 端使用项目根下的 workspaces
        const runtimeDir = IS_PACKAGED ? app.getPath('userData') : '';
        const env = {
            ...process.env,
            PORT: String(PORT),
            DOCFLOW_RUNTIME_DIR: runtimeDir
        };

        pythonProcess = spawn(cmd, args, {
            cwd,
            env: { ...env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
            stdio: ['pipe', 'pipe', 'pipe'],
            windowsHide: true
        });

        const stdoutDecoder = new StringDecoder('utf8');
        const stderrDecoder = new StringDecoder('utf8');

        pythonProcess.stdout.on('data', (data) => {
            try {
                const text = stdoutDecoder.write(data);
                const trimmed = text.trim();
                if (trimmed) console.log(`[Python] ${trimmed}`);
            } catch (e) {
                console.log(`[Python] ${data.toString().trim()}`);
            }
        });

        pythonProcess.stderr.on('data', (data) => {
            try {
                const text = stderrDecoder.write(data);
                const trimmed = text.trim();
                if (trimmed) console.error(`[Python] ${trimmed}`);
            } catch (e) {
                console.error(`[Python] ${data.toString().trim()}`);
            }
        });

        pythonProcess.on('error', (err) => {
            console.error('[Python] 启动失败:', err.message);
            reject(err);
        });

        pythonProcess.on('exit', (code, signal) => {
            console.log(`[Python] 进程退出 code=${code} signal=${signal}`);
            pythonProcess = null;
            if (!isQuitting && code !== 0) {
                dialog.showErrorBox('后端错误', `Python 后端异常退出 (code: ${code})，请重启应用。`);
            }
        });

        // 轮询等待服务就绪
        pollServer(resolve, reject);
    });
}

function pollServer(resolve, reject, attempt = 0) {
    const maxAttempts = 150; // 30s 超时
    if (attempt >= maxAttempts) {
        return reject(new Error('后端启动超时'));
    }

    const req = http.get(`http://127.0.0.1:${PORT}/api/user/me`, (res) => {
        if (res.statusCode >= 200 && res.statusCode < 400) {
            resolve();
        } else {
            setTimeout(() => pollServer(resolve, reject, attempt + 1), 200);
        }
    });
    req.on('error', () => {
        setTimeout(() => pollServer(resolve, reject, attempt + 1), 200);
    });
    req.setTimeout(500, () => {
        req.destroy();
        setTimeout(() => pollServer(resolve, reject, attempt + 1), 200);
    });
}

function startWordKeepAlive() {
    if (process.platform !== 'win32') return;
    if (IS_PACKAGED) return;  // 打包模式下无系统 python 环境

    const scriptPath = path.join(ROOT_DIR, 'tools', 'WordKeepAlive.py');
    if (!require('fs').existsSync(scriptPath)) return;

    const child = spawn('python', [scriptPath, '--silent'], {
        cwd: ROOT_DIR,
        stdio: 'ignore',
        windowsHide: true,
        shell: true
    });
    child.unref();
    console.log('[WordKeepAlive] 已启动');
}

function stopPythonBackend() {
    if (!pythonProcess) return;
    try {
        if (process.platform === 'win32') {
            spawn('taskkill', ['/pid', String(pythonProcess.pid), '/f', '/t']);
        } else {
            // 先尝试通过 process group 杀死所有子进程
            try { process.kill(-pythonProcess.pid, 'SIGTERM'); } catch (_) {}
            // 兜底：杀死父进程
            pythonProcess.kill('SIGTERM');
        }
    } catch (e) {
        console.error('[Python] 停止进程失败:', e.message);
    }
}

// ==================== 窗口创建 ====================
function createWindow() {
    mainWindow = new BrowserWindow({
        title: '文枢',
        width: 1100,
        height: 700,
        minWidth: 800,
        minHeight: 500,
        frame: false,
        icon: path.join(ROOT_DIR, 'ui', 'favicon.ico'),
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: false
        }
    });

    // 居中显示
    mainWindow.center();

    mainWindow.loadURL(`http://127.0.0.1:${PORT}`);

    // 设置 Content Security Policy（消除 Electron 安全警告）
    mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
        callback({
            responseHeaders: {
                ...details.responseHeaders,
                'Content-Security-Policy': [
                    "default-src 'self'; " +
                    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; " +
                    "style-src 'self' 'unsafe-inline' 'unsafe-eval'; " +
                    "img-src 'self' data: blob:; " +
                    "connect-src 'self'; " +
                    "font-src 'self' data:; " +
                    "object-src 'self'; " +
                    "media-src 'self' blob:; " +
                    "frame-src 'self' blob: data:"
                ]
            }
        });
    });

    // 开发模式自动打开 DevTools
    if (OPEN_DEVTOOLS) {
        mainWindow.webContents.openDevTools({ mode: 'bottom' });
    }

    mainWindow.on('maximize', () => {
        mainWindow.webContents.send('window-state-changed', { maximized: true });
    });

    mainWindow.on('unmaximize', () => {
        mainWindow.webContents.send('window-state-changed', { maximized: false });
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });

    // 关闭按钮→根据设置决定行为
    mainWindow.on('close', (event) => {
        if (!isQuitting) {
            if (closeAction === 'exit') {
                // 用户设置"退出应用"→ 真正关闭窗口
                isQuitting = true;
                // 不阻止事件，窗口正常关闭
            } else {
                // 用户设置"最小化到托盘"→ 隐藏到托盘
                event.preventDefault();
                mainWindow.hide();
            }
        }
        // isQuitting 为 true（托盘"退出"或 IPC 已设置）→ 不阻止，窗口正常关闭
    });
}

// ==================== 系统托盘 ====================
function createTray() {
    const iconPath = path.join(ROOT_DIR, 'ui', 'favicon.ico');
    if (!require('fs').existsSync(iconPath)) {
        console.warn('[Electron] 托盘图标文件不存在:', iconPath);
        return;
    }
    let icon = nativeImage.createFromPath(iconPath);
    // Windows 托盘要求 16x16 或 32x32，缩小后更清晰
    icon = icon.resize({ width: 16, height: 16 });

    appTray = new Tray(icon);
    appTray.setToolTip(APP_NAME);

    const contextMenu = Menu.buildFromTemplate([
        {
            label: `打开 ${APP_NAME}`,
            click: () => {
                if (mainWindow) {
                    mainWindow.show();
                    mainWindow.focus();
                }
            }
        },
        { type: 'separator' },
        {
            label: '退出',
            click: () => {
                isQuitting = true;
                app.quit();
            }
        }
    ]);

    appTray.setContextMenu(contextMenu);

    // 左键点击显示窗口
    appTray.on('click', () => {
        if (mainWindow) {
            mainWindow.isVisible() ? mainWindow.focus() : mainWindow.show();
            mainWindow.focus();
        }
    });
}

// ==================== IPC Handlers ====================

// 窗口控制
ipcMain.handle('window-minimize', () => {
    if (mainWindow) mainWindow.minimize();
});

ipcMain.handle('window-maximize', () => {
    if (mainWindow) mainWindow.maximize();
});

ipcMain.handle('window-restore', () => {
    if (mainWindow) mainWindow.restore();
});

ipcMain.handle('window-toggle-maximize', () => {
    if (mainWindow) {
        mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
    }
});

ipcMain.handle('window-is-maximized', () => {
    return mainWindow ? mainWindow.isMaximized() : false;
});

ipcMain.handle('window-close', () => {
    if (!mainWindow) return;
    if (closeAction === 'exit') {
        // 用户设置"退出应用"→ 触发窗口关闭流程
        isQuitting = true;
        mainWindow.close();
    } else {
        // 用户设置"最小化到托盘"→ 隐藏到托盘
        if (!isQuitting) mainWindow.hide();
    }
});

// 接收前端传来的关闭行为设置
ipcMain.handle('set-close-action', (_event, action) => {
    if (action === 'exit' || action === 'minimize') {
        closeAction = action;
        console.log('[Electron] 关闭行为已更新:', closeAction);
    }
});

// 从托盘恢复窗口（给前端用的「关闭按钮→隐藏」反馈
ipcMain.handle('window-show', () => {
    if (mainWindow) {
        mainWindow.show();
        mainWindow.focus();
    }
});

// 窗口位置/大小（兼容现有前端代码，Electron frameless 下不常用）
ipcMain.handle('window-get-position', () => {
    if (!mainWindow) return { x: 0, y: 0 };
    const [x, y] = mainWindow.getPosition();
    return { x, y };
});

ipcMain.handle('window-get-size', () => {
    if (!mainWindow) return { width: 1100, height: 700 };
    const [width, height] = mainWindow.getSize();
    return { width, height };
});

ipcMain.handle('window-move', (_event, x, y) => {
    if (mainWindow) mainWindow.setPosition(x, y);
});

ipcMain.handle('window-resize', (_event, width, height) => {
    if (mainWindow) mainWindow.setSize(width, height);
});

// 原生对话框
ipcMain.handle('select-directory', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openDirectory']
    });
    return result.canceled ? '' : result.filePaths[0];
});

ipcMain.handle('save-file-as', async (_event, suggestedName) => {
    const result = await dialog.showSaveDialog(mainWindow, {
        defaultPath: suggestedName || '文件'
    });
    return result.canceled ? '' : result.filePath;
});

// 外部链接
ipcMain.handle('open-external', async (_event, url) => {
    if (typeof url === 'string' && (url.startsWith('http://') || url.startsWith('https://'))) {
        await shell.openExternal(url);
    }
});

// 应用信息
ipcMain.handle('get-app-version', () => {
    return app.getVersion();
});

// 原生文件拖拽（拖拽文件到外部应用）
// 注意：不可与 HTML5 内部拖拽同时使用（Electron startDrag 会接管整个拖拽流程）
ipcMain.on('start-drag', (event, filePaths) => {
    if (!filePaths || filePaths.length === 0) return;
    try {
        var dragIcon = nativeImage.createFromPath(path.join(ROOT_DIR, 'ui', 'favicon.ico'));
        dragIcon = dragIcon.resize({ width: 16, height: 16 });
        event.sender.startDrag({
            files: filePaths,
            icon: dragIcon
        });
    } catch (e) {
        console.error('[start-drag] error:', e.message);
    }
});

// 用 OS 默认软件打开文件（自动管理窗口焦点）
ipcMain.handle('open-file-with-app', async (_event, absolutePath) => {
    const { shell } = require('electron');
    try {
        const error = await shell.openPath(absolutePath);
        if (error) {
            console.error('[Electron] shell.openPath error:', error);
            return { success: false, message: error };
        }
        return { success: true };
    } catch (e) {
        console.error('[Electron] shell.openPath exception:', e.message);
        return { success: false, message: e.message };
    }
});

// 在 OS 文件管理器中定位并选中文件
ipcMain.handle('show-item-in-folder', async (_event, absolutePath) => {
    const { shell } = require('electron');
    try {
        shell.showItemInFolder(absolutePath);
        return { success: true };
    } catch (e) {
        console.error('[Electron] shell.showItemInFolder exception:', e.message);
        return { success: false, message: e.message };
    }
});

// ==================== 单实例锁（防止重复启动） ====================
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
    app.quit();
} else {
    app.on('second-instance', () => {
        if (mainWindow) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.show();
            mainWindow.focus();
        }
    });
}

// ==================== 应用生命周期 ====================
app.whenReady().then(async () => {
    try {
        console.log('[Electron] 正在启动 Python 后端...');
        await startPythonBackend();
        console.log('[Electron] Python 后端就绪');
        startWordKeepAlive();
        createWindow();
        createTray();
        console.log('[Electron] 系统托盘已创建');
    } catch (err) {
        console.error('[Electron] 启动失败:', err.message);
        dialog.showErrorBox('启动失败', `无法启动后端服务：${err.message}`);
        app.quit();
    }
});

// 所有窗口关闭时：macOS 保持运行，其他平台退出
app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (mainWindow === null && pythonProcess) {
        createWindow();
    }
});

app.on('before-quit', () => {
    isQuitting = true;
    if (appTray) {
        appTray.destroy();
        appTray = null;
    }
    stopPythonBackend();
});
