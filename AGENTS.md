# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

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

# 生成本地更新清单 version.json（CI 发版时自动跑，本地调试用）
python make_update_manifest.py --file dist/Docflowing_Setup.exe --output dist/version.json --repo doonly1/Docflowing
```

> **发版前必做**：先把根目录 `version.py` 的 `APP_VERSION` 改成目标版本（语义化 `X.Y.Z`），提交后再打同名 tag（`git tag vX.Y.Z && git push origin vX.Y.Z`）。`version.py` 是全项目唯一版本源，以下位置都引用它，禁止再写死：NSIS 的 `PRODUCT_VERSION`、`DesktopAPI.getAppVersion()`、`make_update_manifest.py`、CI 的 tag 一致性校验。

## Architecture

Docflowing is a **document management desktop app** with pywebview shell + Flask backend + SQLite + P2P.

### Entry Points

| File               | Purpose                                           |
| ------------------ | ------------------------------------------------- |
| `desktop_app.py`   | **主入口** — 启动 Flask 后台线程，创建 pywebview frameless 窗口 |
| `app_server.py`    | 纯 Flask 模式（无桌面壳，用于开发/浏览器回退）                       |
| `build-desktop.py` | PyInstaller 打包脚本，生成 onedir / onefile / installer  |

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

- LLM 集成（`llm.py`），FTS5 全文搜索（`search.py`，使用内建 trigram 分词器）

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

**版本与自动更新 (Versioning & Auto-Update)**

- `version.py` — **全项目唯一版本源**（`APP_VERSION` + `UPDATE_CHANNEL` + `parse_version`/`compare_versions` 语义化比对）。`DesktopAPI.getAppVersion()`、NSIS `PRODUCT_VERSION`、`make_update_manifest.py` 全部引用它，不要写死。

- `server/updater.py` — 更新核心（Flask 蓝图 `updater_bp`，前缀 `/api/app`）：
  - 状态机：`idle → checking → available → downloading → ready →(安装后重置) idle`，失败落 `failed`
  - 后台**静默预下载**：启动后延迟 20s 检查清单，发现新版本即在后台线程断点续传下载安装包，sha256 校验通过后才提示用户安装（用户等待时间只有"安装"，没有"下载"）
  - 清单走 `DOCFLOWING_UPDATE_URL`（默认 `…/releases/latest/download/version.json`，**不**直接打 `api.github.com`，避开国内网络不稳）；含 `min_required` 强制升级、`mirror` 镜像兜底、便携版独立包
  - 应用设置键：`auto_download_update`（默认开）、`skip_update_version`（跳过某版本）

- `desktop_app.py` 的 `DesktopAPI`：
  - `installUpdate()` — **严格路径校验**（只允许执行更新目录里生成的 `.exe`，拒绝拉起任意程序）→ 脱离父进程 `detached` 拉起 NSIS 安装器并传自身 PID → 停 `WordKeepAlive` 子进程、释放单实例锁、退出
  - `quitApp()` / `getAppVersion()`

- `ui/js/updater.js` — 前端更新交互：右下角就绪提示条 + 设置面板「应用更新」卡片（版本号/状态/自动下载开关/检查/下载/安装/跳过）。首页知识库欢迎大标题现为「知识库」（`kb.js` 的 `kb-chat-greeting-title`）。

- `make_update_manifest.py` — 发版时计算安装包 `size`/`sha256`，生成 `version.json`。

**NSIS 安装器（`build-desktop.py` 生成的 `installer.nsi`）关键行为**：先 `taskkill` 传入的旧进程 PID 再整目录覆盖；`VersionCompare` 拦死降级安装（读 `$INSTDIR\VERSION`）；安装后可选自动重启应用；支持 `/SILENT` 静默安装。

### Key Architecture Decisions

1. **pywebview 替代 Electron**: 默认走系统原生标题栏（winui3 用 XAML 自绘，保留缩放/吸附）。frameless 仅是逃生门，**不再**补 `WS_THICKFRAME`（Win10 下 DWM 会残留单侧黑边，已移除）——逃生门窗口无系统缩放，详见 `desktop_window.py` 模块 docstring
2. **前后端通信**: 前端通过 `fetch()` 调用 Flask API，不使用 Electron IPC。`DesktopAPI` 仅提供窗口控制、文件对话框、OS shell 等纯桌面功能
3. **数据存储**: 开发模式写入 `%APPDATA%/Docflowing/workspaces/`，便携版写入 exe 同级的 `data/`，打包版写入 `%APPDATA%/Docflowing/`
4. **单实例锁**: 绑定 `port + 1000` 的 TCP 端口，重复启动时通知已有实例显示窗口

5. **更新机制**: 版本号唯一源 = `version.py` 的 `APP_VERSION`；发版改它 → commit → `git tag v<版本>` → push tag 触发 `release.yml`（云端 Windows 重建安装包 + 生成 `version.json` 校验和并上传）。客户端 `server/updater.py` 静默预下载安装包（后台线程 + sha256 校验），就绪后提示安装；`desktop_app.installUpdate()` 传 `/PID` 给 NSIS 让其先 taskkill 旧进程再覆盖。清单地址默认 `…/releases/latest/download/version.json`，可用 `DOCFLOWING_UPDATE_URL` 覆盖到自建 CDN。降级安装被 NSIS 拦死（读 `$INSTDIR\VERSION`）。设置键：`auto_download_update`、`skip_update_version`

## Project Structure

```
Docflowing/
├── desktop_app.py       # 主入口（桌面模式）
├── app_server.py        # 纯 Flask 入口
├── build-desktop.py     # PyInstaller 构建脚本（生成 NSIS installer.nsi）
├── make_update_manifest.py  # 发版时生成 version.json（安装包 size/sha256 清单）
├── version.py           # 全项目唯一版本源（APP_VERSION / UPDATE_CHANNEL）
├── AGENTS.md
├── README.md
├── requirements.txt
├── server/              # Flask 后端
│   ├── __init__.py      # create_app() 工厂
│   ├── auth.py
│   ├── middleware.py
│   ├── workspace.py
│   ├── settings.py
│   ├── updater.py       # 更新蓝图（清单拉取/版本比对/后台静默下载/sha256 校验）
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
│   └── fts_ext/         # FTS5 旧 simple 分词扩展（已弃用，仅随包冗余保留）
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
│       ├── kb.js        # 知识库 UI（首页欢迎标题「知识库」）
│       ├── tools.js
│       ├── updater.js   # 更新交互（就绪提示条 + 设置面板更新卡片）
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
│   ├── test_to_compare.py
│   └── test_updater.py  # 更新器：版本比对/清单解析/下载校验/状态机
└── .github/workflows/
    └── release.yml      # CI: 云端 Windows 构建安装包 + 生成 version.json 并发布 Release
```

## Important Notes

- 前端代码大量使用 `window.electronAPI` 调用桌面功能，这是通过 `server/__init__.py` 注入的 shim 映射到 `window.pywebview.api`，**不要直接删除或重命名**

- frameless 逃生门（`DOCFLOWING_TITLEBAR=frameless`）**不支持系统缩放**：曾经靠 `enable_frameless_resize()` 补 `WS_THICKFRAME`，但 Win10 下 DWM 会渲染单侧残留黑边，该补丁已整体删除。窗口仍可拖动（header 拖动区由服务端在逃生门模式注入）

- 测试使用 pytest，`test_pywebview.py` 覆盖了 `DesktopAPI`、Flask 集成、单实例锁等核心桌面功能

- `requirements-lock.txt` 是完全锁定的版本清单（用于 CI 构建），`requirements.txt` 是宽松范围

- `--word-keepalive` 和 `--run-tool` 是打包版 exe 的 CLI 参数，用于在后台调用文档处理工具和 Word 保活

- 前端 `index.html` 使用 CSP 限制严格，新增外部资源引用时需同步更新 CSP 头

- **FTS5 中文搜索**：`kb/wiki_fts` 与 `kb/session_db.py` 的 `messages_fts`（SCHEMA_VERSION>=4）均使用 SQLite **内建 `trigram` 分词器**（sqlite>=3.34，Python 3.12+ 自带的 3.49+ 均满足），运行时不加载任何外部扩展。`kb/fts_ext/simple.dll` 等仅作为冗余资源随包保留——旧 `simple` 分词器扩展与新版 SQLite 不兼容（加载后 tokenizer 注册失败，且存在偶发原生崩溃史），勿再恢复 `load_extension` 调用。注意：trigram 对长度 <3 的查询词无法命中（如常见 2 字中文词），`kb/search.py` / `kb/session_db.py` 会走 LIKE 兜底，属正常降级路径，不是 bug

- **版本单一来源**：版本号只在 `version.py` 的 `APP_VERSION` 定义，发版改它后必须打同名 git tag（如 `v1.0.5`）才能触发 CI 发版；CI 会校验二者一致，不一致直接失败。不要在任何文件里再写死版本号。

- **首页知识库标题**：知识库首页居中欢迎标题为「知识库」（`kb.js` 的 `kb-chat-greeting-title`），对应 `kb-chat-initial-area`（仅在初始态显示）；会话激活后该区域隐藏、`#kb-messages` 内的空状态「开始对话 / 与AI助手对话…」才出现，二者是不同显示场景，勿混淆。

