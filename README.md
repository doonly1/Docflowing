# DocFlow · 文枢

> DocFlow——Document Workflow，公文处理与 AI 知识管理平台。

DocFlow（文枢）是一个面向公文处理的 **桌面应用 + 工具集**，深度整合传统文档处理与 AI 驱动的知识管理，包括：知识库 Wiki、对话式 AI 助手、持久记忆系统、智能技能管理、使用洞察分析等。

基于 P2P 节点共享，局域网内多台机器可互相发现并共享文件库。

---

## 快速开始

### 安装依赖

```bash
# Python 后端依赖
pip install -r requirements.txt

# Node.js 前端依赖
npm install
```

### 开发模式（推荐）

```bash
# 1. 启动 Python 后端
python app_server.py

# 2. 另开终端，启动 Electron 桌面壳
npm run dev
```

默认打开一个 1100×700 的无边框窗口，自动居中显示。开发模式下会自动打开 DevTools。

### 生产构建

```bash
# 完整构建（编译 Python 后端 + 打包 Electron 安装包）
npm run dist:win
```

输出在 `release/` 目录下，生成 NSIS 安装包 `文枢-Setup-1.0.0.exe`。

## 下载安装

### 普通用户（无需编程环境）

1. 前往 **[Releases](https://github.com/doonly1/DocFlow/releases)** 页面
2. 找到最新版本，下载 `文枢-Setup-x.x.x.exe`
3. 双击运行安装程序
   - 可选择安装目录（默认 `C:\Program Files\文枢`）
   - 自动创建桌面快捷方式
4. 安装完成后，双击桌面图标启动
   - 首次启动会自动在安装目录下创建 `workspaces/` 数据文件夹
   - 所有知识库、文件库、配置数据均保存在此目录

> **注意**：安装包包含编译好的 Python 后端（约 60MB），首次启动无需额外配置。

### 开发者

```bash
# 克隆仓库
git clone https://github.com/doonly1/DocFlow.git
cd DocFlow

# 安装依赖
pip install -r requirements.txt
npm install

# 开发模式
python app_server.py       # 终端1：启动后端
npm run dev                # 终端2：启动 Electron

# 生产打包
npm run dist:win           # 输出到 release/ 目录
```

### 自动发布流程

推送 `v*` 标签到 GitHub 时，Actions 会自动构建并上传安装包：

```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## 功能模块

### 📄 文档处理工具集（`tools/`）

| 工具 | 功能 | 技术要点 |
|------|------|----------|
| `to_compare.py` | 文档比对 | 三级 diff（段落/句子/字符），红蓝高亮标记 |
| `to_redhead.py` | 红头文件生成 | 套红标题、浮动印章、发文代字/文号 |
| `to_docx.py` | 多格式转 DOCX | 支持 PDF/DOC/DOCX/TXT/HTML/MD |
| `to_pdf.py` | 批量转 PDF | LibreOffice / win32com 双引擎 |
| `to_pageNum.py` | 批量添加页码 | DOCX XML 级 PAGE 域操作 |
| `to_index.py` | 目录索引生成 | 扫描目录输出 Excel |
| `mystyle.py` | 公文样式库 | 符合中文公文规范的样式定义 |
| `doc_process.py` | 文档基础库 | 标题解析、附件处理、日期排版、格式转换 |

### 🗂️ 文件库管理（`fb/`）

- **文件库 CRUD**：创建本地文件库、复制、重命名、删除（移入回收站）
- **回收站**：列出、恢复、永久删除
- **文件操作**：上传、下载（Zip 打包）、批量下载、在线编辑/预览、重命名、移动、复制、创建目录
- **工具集成**：SSE 流式执行文档处理工具，按工具类型过滤
- **KB 同步**：文件库→知识库自动增量同步（FTS5 索引，不落盘 .md 文件）
- **格式转换**：批量 .doc → .docx 转换

### 🧠 知识库系统（`kb/`）

AI 核心模块，融合 Hermes Agent，实现记忆与技能的自主进化。

| 子系统 | 路由模块 | 功能 |
|--------|----------|------|
| **文件管理** | `routes.py` | Markdown 文件 CRUD、目录树浏览、FTS5 全文搜索 |
| **对话会话** | `routes_session.py` + `session_db.py` | 创建/查询会话、消息追加、自动标题生成、90 天保留 |
| **持久记忆** | `routes_memory.py` + `memory.py` | 系统笔记（2200 字符）/ 用户画像（1375 字符），安全扫描 |
| **技能管理** | `routes_skills.py` + `skills/` | 技能 CRUD、文件关联、使用统计、生命周期（active→stale→archived） |
| **技能审查** | `skills/curator.py` | LLM 驱动自动合并与归档同类技能 |
| **上下文压缩** | `context_compressor.py` | Token 超阈值自动摘要，保留首尾关键消息 |
| **自动提取** | `auto_extract.py` | 对话分析，自动提取记忆和技能 |
| **洞察分析** | `routes_insights.py` + `insights.py` | 使用数据概览、活跃模式、热门会话统计 |
| **LLM 配置** | `config.py` | OpenAI 兼容 API，Fernet 加密存储密钥 |
| **同步管理** | `sync_worker.py` + `sync_converters.py` | 文件库→KB 自动同步，增量同步（mtime），并发控制，多格式转 Markdown（markitdown） |

### 🔐 认证

单用户桌面版，本机 localhost 自动放行。P2P 层使用 Ed25519 签名验证节点身份。

### 🌐 P2P 节点共享

- **发现**：基于 zeroconf (mDNS) 自动发现局域网节点
- **认证**：Ed25519 签名 + TrustStore 信任管理
- **共享**：文件库可共享给信任节点，支持 view/edit/manage 三级权限

---

## 项目结构

```
├── electron/                    # Electron 桌面壳
│   ├── main.js                  # 主进程（窗口管理、后端进程启动）
│   ├── preload.js               # 预加载脚本（安全上下文桥接）
│   ├── build-backend.py         # 后端 PyInstaller 打包脚本
│   └── copy-libs.js             # 构建时复制依赖
├── server/                      # Flask 后端服务核心
│   ├── __init__.py              # App 工厂、P2P 初始化（后台线程）、全局错误处理
│   ├── auth.py                  # 本机 localhost 自动放行（30 行）
│   ├── middleware.py            # 请求 ID 中间件
│   ├── runner.py                # 工具脚本 SSE 流式执行
│   ├── settings.py              # 用户配置持久化
│   └── workspace.py             # 工作区管理、文件上传/下载
├── fb/                          # 文件库管理
│   ├── models.py                # 数据库模型 / 表结构
│   ├── routes_base.py           # 文件库 CRUD（创建/删除/重命名/回收站）
│   ├── routes_files.py          # 文件操作（上传/下载/重命名/移动）
│   ├── routes_files_edit.py     # 文件编辑/删除（移入回收站）
│   ├── routes_files_ops.py      # 文件批量操作（复制/移动/替换）
│   ├── routes_trash.py          # 回收站列表/恢复/清空
│   ├── routes_locks.py          # 文件锁管理
│   ├── routes_search.py         # 文件搜索
│   ├── routes_tools.py          # 工具集成（SSE 流式执行）
│   ├── routes_sync.py           # KB 同步管理
│   ├── routes_p2p.py            # P2P 远程文件操作
│   ├── routes.py                # 路由汇总导入
│   ├── decorators.py            # 权限装饰器
│   └── database.py              # 文件库数据库
├── kb/                          # 知识库系统（进化 Wiki）
│   ├── routes.py                # 核心 API（文件 CRUD、搜索、权限）
│   ├── routes_session.py        # 会话管理 API
│   ├── routes_memory.py         # 持久记忆 API
│   ├── routes_insights.py       # 洞察分析 API
│   ├── routes_skills.py         # 技能管理 API
│   ├── config.py                # LLM 配置加载与密钥加密
│   ├── database.py              # 知识库数据库（FTS5）
│   ├── models.py                # 库表模型
│   ├── session_db.py            # 会话消息数据库
│   ├── search.py                # FTS5 全文搜索
│   ├── sync_converters.py       # 同步文件格式转换器（策略模式）
│   ├── sync_worker.py           # 文件库→KB 后台同步线程
│   ├── memory.py                # 持久记忆存储（安全扫描）
│   ├── llm.py                   # LLM 调用（OpenAI 兼容）
│   ├── context_compressor.py    # 上下文压缩
│   ├── context_fence.py         # 记忆上下文 fence 标签
│   ├── file_safety.py           # 文件写入安全路径
│   ├── file_lock.py             # 跨平台文件锁
│   ├── auto_extract.py          # 对话自动提取记忆/技能
│   ├── insights.py              # 使用数据洞察分析引擎
│   ├── tools.py                 # LLM Function Calling 工具定义
│   └── skills/                  # 技能管理子系统
│       ├── manager.py           # 技能 CRUD
│       ├── curator.py           # 技能审查器（合并与归档）
│       └── usage.py             # 技能使用统计
├── tools/                       # 文档处理命令行脚本
│   ├── doc_process.py           # 文档基础处理
│   ├── mystyle.py               # 公文样式库
│   ├── to_compare.py            # 文档比对（77KB 最大模块）
│   ├── to_docx.py               # 多格式转 DOCX
│   ├── to_redhead.py            # 红头文件生成
│   ├── to_index.py              # 目录索引
│   ├── to_pageNum.py            # 批量添加页码
│   ├── to_pdf.py                # 批量转 PDF
│   ├── float_picture.py         # 浮动图片处理
│   ├── load_config.py           # 配置加载器
│   └── logging_config.py        # 日志配置
├── p2p/                         # P2P 节点发现与认证
│   ├── node.py                  # 节点身份管理（Ed25519 密钥对）
│   ├── discovery.py             # zeroconf mDNS 服务发现
│   ├── auth.py                  # 签名验证装饰器
│   ├── api.py                   # P2P 远程文件操作 API
│   ├── models.py                # TrustStore + RemoteFilebaseStore
│   └── proxy.py                 # P2P 请求代理转发
├── ui/                          # 前端 SPA（按需加载）
│   ├── index.html               # 主页面
│   ├── js/
│   │   ├── main.js              # 核心逻辑 + 工具页
│   │   ├── fb.js / fb.css       # 文件库管理器（按需加载）
│   │   └── kb.js / kb.css       # 知识库聊天/文件浏览（按需加载）
│   └── lib/                     # 第三方前端库
│       ├── marked/              # Markdown 渲染
│       ├── quill/               # 富文本编辑器
│       └── turndown/            # HTML 转 Markdown
├── tests/                       # 测试
├── requirements.txt             # Python 依赖
└── README.md                    # 本文件
```

---

## 数据存储

```
workspaces/
├── data/
│   ├── fb/fb.db                # 文件库数据库
│   └── kb/                     # 知识库
│       ├── wiki.db             # 知识库 FTS 数据库
│       ├── state.db            # 会话消息数据库
│       ├── memories/           # 持久记忆文件
│       └── skills/             # 技能文件
├── config/                     # 用户配置
│   ├── user_config.yaml        # 公文/工具配置（从代码默认值生成）
│   ├── kb_config.yaml          # 知识库 LLM 配置（含加密密钥）
│   ├── p2p_node.yaml           # P2P 节点身份（自动生成）
└── trash/                      # 回收站
```

---

## 配置

默认值内置于代码中，首次运行自动生成到 `workspaces/config/`。通过 Web UI 修改配置后持久化保存。

- **公文配置**：`server/settings.py` `_DEFAULT_DOC_CONFIG` → `workspaces/config/user_config.yaml`
- **知识库配置**：`kb/config.py` `_DEFAULT_KB_CONFIG` → `workspaces/config/kb_config.yaml`（含加密 LLM 密钥）
- **P2P 节点身份**：`workspaces/config/p2p_node.yaml`（自动生成）

---

## 环境要求

- **Python** 3.9+
- **Windows**：完整功能（DOC 转换 / PDF 转换需 Microsoft Word）
- **Linux/macOS**：除 win32com 依赖功能外皆可使用

## 版权声明

Copyright © 2026 doonly1. Licensed under the AGPL-3.0 (see [LICENSE](./LICENSE)).

### 第三方声明

本项目使用了以下开源组件，感谢作者：

| 组件 | 许可证 | 用途 |
|------|--------|------|
| [Hermes Agent](https://github.com/NousResearch/Hermes-Agent) | MIT | 知识库模块代码逻辑（上下文压缩、技能审查、会话洞察、文件安全等） |
| [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | 系统级技能（诊断、TDD、原型设计、代码审查等） |
| [zeroconf](https://github.com/jstasiak/python-zeroconf) | LGPL-2.1 | P2P 节点 mDNS 发现 |
| [Quill](https://github.com/slab/quill) | BSD-3-Clause | 富文本编辑器 |
| [Turndown](https://github.com/mixmark-io/turndown) | MIT | HTML 转 Markdown |
| [Marked.js](https://github.com/markedjs/marked) | MIT | Markdown 渲染 |
| [Flask](https://github.com/pallets/flask) | BSD-3-Clause | Web 框架 |
| [python-docx](https://github.com/python-openxml/python-docx) | MIT | Word 文档处理 |
| [openpyxl](https://github.com/theorchard/openpyxl) | MIT | Excel 文档处理 |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | MIT | PDF 文本提取 |
| [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) | MIT | HTML 解析 |
| [PyYAML](https://github.com/yaml/pyyaml) | MIT | YAML 解析 |
| [Flask-CORS](https://github.com/corydolphin/flask-cors) | MIT | 跨域请求支持 |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 / BSD | API 密钥加密存储 |
| [markitdown](https://github.com/microsoft/markitdown) | MIT | 文档格式转换（PDF/DOCX/PPTX/XLSX 等） |
| [requests](https://github.com/psf/requests) | Apache-2.0 | LLM API 调用、网页抓取 |
| [pywin32](https://github.com/mhammond/pywin32) | PSF | Windows COM 支持（Word 文档转换，可选） |
| [docx2pdf](https://github.com/AlJohri/docx2pdf) | MIT | DOCX 转 PDF（可选） |

以上组件的原始许可证文本可在各自仓库中查看。
