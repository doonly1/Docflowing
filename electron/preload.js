const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    // 窗口控制
    windowMinimize: () => ipcRenderer.invoke('window-minimize'),
    windowMaximize: () => ipcRenderer.invoke('window-maximize'),
    windowRestore: () => ipcRenderer.invoke('window-restore'),
    windowToggleMaximize: () => ipcRenderer.invoke('window-toggle-maximize'),
    windowIsMaximized: () => ipcRenderer.invoke('window-is-maximized'),
    windowClose: () => ipcRenderer.invoke('window-close'),
    windowShow: () => ipcRenderer.invoke('window-show'),

    // 窗口位置/大小
    windowGetPosition: () => ipcRenderer.invoke('window-get-position'),
    windowGetSize: () => ipcRenderer.invoke('window-get-size'),
    windowMove: (x, y) => ipcRenderer.invoke('window-move', x, y),
    windowResize: (w, h) => ipcRenderer.invoke('window-resize', w, h),

    // 原生对话框
    selectDirectory: () => ipcRenderer.invoke('select-directory'),
    saveFileAs: (suggestedName) => ipcRenderer.invoke('save-file-as', suggestedName),

    // 外部链接
    openExternal: (url) => ipcRenderer.invoke('open-external', url),

    // 应用信息
    getAppVersion: () => ipcRenderer.invoke('get-app-version'),

    // 窗口状态监听
    onWindowStateChanged: (callback) => {
        ipcRenderer.on('window-state-changed', (_event, data) => callback(data));
    },

    // 原生文件拖拽（拖拽文件到外部应用）
    startDrag: (filePaths) => {
        ipcRenderer.send('start-drag', filePaths);
    },

    // 用 OS 默认软件打开文件（自动管理窗口焦点）
    openFileWithOsApp: (absolutePath) => ipcRenderer.invoke('open-file-with-app', absolutePath)
});
