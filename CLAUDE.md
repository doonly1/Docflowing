# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# 开发模式运行桌面应用
python desktop_app.py

# 仅启动 Flask 后端（浏览器模式）
python app_server.py

# 运行测试（含覆盖率）
python -m pytest tests/ -v --cov=. --cov-report=term-missing

# 运行单个测试文件
python -m pytest tests/test_pywebview.py -v

# 运行单个测试用例
python -m pytest tests/test_pywebview.py::TestDesktopAPI::test_api_creation -v

# 打包（onedir 模式，默认）
python build-desktop.py

# 打包（单 exe 模式）
python build-desktop.py --onefile

# 打包（onedir + NSIS 安装包）
python build-desktop.py --installer
```

## Architecture

Docflowing is a **document management desktop app** with pywebview shell + Flask backend + SQLite + P2P.

### Entry Points

| File | Purpose |
|---|---|
| `desktop_app.py` | **主入口** — 启动 Flask 后台线程，创建 pywebview frameless 窗口 |
| `app_server.py` | 纯 Flask 模式（无桌面壳，用于开发/浏览器回退） |
| `build-desktop.py` | PyInstaller 打包脚本，生成 onedir / onefile / installer |

### Layers

**Desktop Shell** (`desktop_app.py`)
- flask 在后台线程运行，pywebview（edgechromium/WinForms）渲染前端
- frameless 窗口（无系统标题栏），自定义 CSS 拖拽区域（`-webkit-app-region: drag`）
- `DesktopAPI` 类暴露给 JS 的窗口控制、文件对话框、OS shell 操作等
- 通过 port+1000 绑定实现单实例锁，已运行时发 HTTP 信号显示已有窗口
- 系统托盘（pystray），关闭行为可配置为隐藏到托盘而非退出
- WordKeepAlive 后台进程（Windows COM，防止 Office 文档锁）

**Flask Backend** (`server/`)
- `create_app()` 工厂函数，注册所有蓝图和中间件
- `middleware.py` — 请求 ID、日志、CSP 头等
- 首页注入 pywebview shim：`window.electronAPI = window.pywebview.api`（向后兼容旧前端代码）
- CSP 由 Flask `after_request` 注入，不再依赖 Electron session

**文件库 (fb/)** — 本地文件管理系统
- `routes.py` 统一入口，将路由分派到子模块：`routes_base`（CRUD）、`routes_trash`（回收站）、`routes_files`（上传浏览）、`routes_files_ops`（下载预览）、`routes_files_edit`（编辑移动删除）、`routes_search`（FTS 搜索）、`routes_sync`、`routes_p2p`、`routes_tools`（工具栏调用）、`routes_locks`（文件锁）
- `database.py` — SQLite 存储文件元数据
- `decorators.py` — 细粒度权限校验（位掩码）

**知识库 (kb/)** — 基于 LLM 的协作知识库
- LLM 集成（`llm.py`），FTS5 全文搜索（`search.py`，通过 `fts_ext/` 扩展支持中文分词）
- 会话管理（`session_db.py`），上下文压缩（`context_compressor.py`）
- 技能系统（`skills/` — manager, curator, usage）
- 同步体系（`sync_*.py` — converters, state, subprocess, worker）
- Agent 工具定义（`agent_tools.py`、`user_tools.py`）

**P2P (p2p/)** — 点对点文件库共享
- 节点发现（zeroconf/mDNS），加密认证（cryptography），代理转发

**Frontend (ui/)** — 单页应用，所有 HTML + CSS 内联在 `index.html`
- `js/main.js` — `FileBase` 对象，核心文件库操作逻辑
- `js/fb.js` — 文件浏览器渲染
- `js/tab-manager.js` — 多标签页管理 + 原生窗口控制按钮
- `js/kb.js` + `js/kb.css` — 知识库 UI
- `js/tools.js` — 文档工具执行 UI
- 引用了 marked、Quill（富文本编辑）、Turndown（HTML→MD）、pdf.js

**Tools (`tools/`)** — 文档处理工具模块
- `to_docx.py`、`to_pdf.py`、`to_compare.py`、`to_redhead.py`（红头文件）、`to_index.py`（目录生成）、`to_pageNum.py`（页码）等
- `tool_defs.py` — 工具元数据定义
- `WordKeepAlive.py` — Windows COM 保活脚本

### Key Architecture Decisions

1. **pywebview 替代 Electron**: 默认走系统原生标题栏（winui3 用 XAML 自绘，保留缩放/吸附）。frameless 仅是逃生门，**不再**补 `WS_THICKFRAME`（Win10 下 DWM 会残留单侧黑边，已移除）——逃生门窗口无系统缩放，详见 `desktop_window.py` 模块 docstring
2. **前后端通信**: 前端通过 `fetch()` 调用 Flask API，不使用 Electron IPC。`DesktopAPI` 仅提供窗口控制、文件对话框、OS shell 等纯桌面功能
3. **数据存储**: 开发模式写入 `%APPDATA%/Docflowing/workspaces/`，便携版写入 exe 同级的 `data/`，打包版写入 `%APPDATA%/Docflowing/`
4. **单实例锁**: 绑定 `port + 1000` 的 TCP 端口，重复启动时通知已有实例显示窗口

## Project Structure

```
Docflowing/
├── desktop_app.py       # 主入口（桌面模式）
├── app_server.py        # 纯 Flask 入口
├── build-desktop.py     # PyInstaller 构建脚本
├── CLAUDE.md
├── README.md
├── requirements.txt
├── server/              # Flask 后端
│   ├── __init__.py      # create_app() 工厂
│   ├── auth.py
│   ├── middleware.py
│   ├── workspace.py
│   ├── settings.py
│   ├── runner.py
│   └── tool_runner.py
├── fb/                  # 文件库模块
│   ├── routes.py        # 路由分派入口
│   ├── routes_base.py
│   ├── routes_files*.py
│   ├── routes_trash.py
│   ├── routes_search.py
│   ├── routes_sync.py
│   ├── routes_p2p.py
│   ├── routes_tools.py
│   ├── routes_locks.py
│   ├── database.py
│   ├── decorators.py
│   └── models.py
├── kb/                  # 知识库模块
│   ├── routes.py
│   ├── routes_session.py
│   ├── routes_memory.py
│   ├── routes_insights.py
│   ├── routes_skills.py
│   ├── llm.py
│   ├── search.py
│   ├── database.py      # SQLite + FTS5
│   ├── session_db.py
│   ├── agent_tools.py
│   ├── user_tools.py
│   ├── sync_*.py
│   ├── skills/
│   │   ├── manager.py
│   │   ├── curator.py
│   │   └── usage.py
│   └── fts_ext/         # FTS5 中文分词扩展
├── p2p/                 # P2P 共享模块
│   ├── node.py
│   ├── discovery.py
│   ├── auth.py
│   ├── api.py
│   ├── proxy.py
│   └── models.py
├── ui/                  # 前端
│   ├── index.html       # 单页应用（全部 CSS + HTML 内联）
│   └── js/
│       ├── main.js      # FileBase 对象
│       ├── fb.js        # 文件浏览器
│       ├── tab-manager.js
│       ├── kb.js
│       ├── tools.js
│       └── utils.js
├── tools/               # 文档处理工具
│   ├── to_docx.py
│   ├── to_pdf.py
│   ├── to_compare.py
│   ├── to_redhead.py
│   ├── to_index.py
│   ├── to_pageNum.py
│   ├── tool_defs.py
│   ├── WordKeepAlive.py
│   └── ...
├── tests/
│   ├── test_pywebview.py
│   ├── test_auth.py
│   ├── test_llm.py
│   └── test_to_compare.py
└── .github/workflows/
    └── release.yml      # CI: 构建 onefile exe 并发布 Release
```

## Important Notes

- 前端代码大量使用 `window.electronAPI` 调用桌面功能，这是通过 `server/__init__.py` 注入的 shim 映射到 `window.pywebview.api`，**不要直接删除或重命名**
- frameless 逃生门（`DOCFLOWING_TITLEBAR=frameless`）**不支持系统缩放**：曾经靠 `enable_frameless_resize()` 补 `WS_THICKFRAME`，但 Win10 下 DWM 会渲染单侧残留黑边，该补丁已整体删除。窗口仍可拖动（header 拖动区由服务端在逃生门模式注入）
- 测试使用 pytest，`test_pywebview.py` 覆盖了 `DesktopAPI`、Flask 集成、单实例锁等核心桌面功能
- `requirements-lock.txt` 是完全锁定的版本清单（用于 CI 构建），`requirements.txt` 是宽松范围
- `--word-keepalive` 和 `--run-tool` 是打包版 exe 的 CLI 参数，用于在后台调用文档处理工具和 Word 保活
- 前端 `index.html` 使用 CSP 限制严格，新增外部资源引用时需同步更新 CSP 头
- **FTS5 中文搜索**：`kb/wiki_fts` 使用 `simple` tokenizer（通过 `kb/fts_ext/simple.dll` 扩展），支持正确的中文分词。**每个 SQLite 连接必须单独加载扩展**——`kb/database.py` 的 `init_db()` 会自动调用 `_load_simple_extension(conn)`，不要加进程级缓存跳过。如果扩展 DLL 不存在或加载失败，FTS 表无法使用
