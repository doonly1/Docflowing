# DocProc · 文枢

> DocProc——Document Process，公文处理与 AI 知识管理平台。

DocProc（文枢）是一个面向公文处理的 **Web 应用 + 工具集**，深度整合传统文档处理与 AI 驱动的知识管理，包括：知识库 Wiki、对话式 AI 助手、持久记忆系统、智能技能管理、使用洞察分析等。

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Web 服务
python app.py
# 默认访问 http://localhost:5000
```

首次启动会自动创建管理员账号（`admin` / UUID 后 6 位），可在控制台日志中查看。

### Docker 部署

```bash
docker-compose up -d
```

### Railway 部署

已内置 `railway.toml`，可直接关联 GitHub 仓库一键部署。

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

- **文件库 CRUD**：创建本地/网络文件库，复制、重命名、删除（移入回收站）、转让所有权
- **回收站**：列出、恢复、永久删除回收站项目
- **文件操作**：上传、下载（Zip 打包）、批量下载、在线编辑/预览、重命名、移动、复制、创建目录
- **权限管理**：view / edit / manage 三级权限，支持共享，成员增删改
- **工具集成**：SSE 流式执行文档处理工具，按工具类型过滤
- **KB 同步**：文件库→知识库自动增量同步，支持手动触发
- **格式转换**：批量 .doc → .docx 转换

### 🧠 知识库系统（`kb/`）— 进化知识库（Evolving Wiki）

AI 核心模块，灵感源自 Hermes Agent，实现记忆与技能的自主进化。

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
| **同步管理** | `sync_worker.py` + `sync_converters.py` | 文件库→KB 自动同步，增量同步（mtime），并发控制，多格式转 Markdown |

### 🔐 认证与权限

- Token-based Bearer 认证
- 角色系统：`admin` / `editor` / `viewer`
- 首次部署自动创建管理员
- 支持注册、登录、退出、改密码、用户角色管理

---

## 项目结构

```
├── config/                     # 配置文件
│   ├── config.yaml             # 公司信息、比对参数
│   └── kb_config.yaml          # 知识库系统配置（LLM、记忆、技能）
├── server/                     # Flask 后端服务核心
│   ├── __init__.py             # App 工厂、静态文件服务、全局错误处理
│   ├── auth.py                 # Token 认证、用户管理、活跃时间
│   ├── middleware.py           # 请求 ID 中间件
│   ├── runner.py               # 工具脚本 SSE 流式执行
│   ├── settings.py             # 用户配置持久化
│   └── workspace.py            # 工作区管理、文件上传/下载
├── fb/                         # 文件库管理
│   ├── models.py               # 数据库模型 / 表结构
│   └── routes.py               # 文件库 CRUD、回收站、文件操作、权限、工具执行、KB 同步
├── kb/                         # 知识库系统（进化 Wiki）
│   ├── routes.py               # 核心 API（文件 CRUD、搜索、权限）
│   ├── routes_session.py       # 会话管理 API
│   ├── routes_memory.py        # 持久记忆 API
│   ├── routes_insights.py      # 洞察分析 API
│   ├── routes_skills.py        # 技能管理 API
│   ├── config.py               # LLM 配置加载与密钥加密
│   ├── database.py             # 知识库数据库（FTS5）
│   ├── models.py               # 库表模型
│   ├── session_db.py           # 会话消息数据库
│   ├── search.py               # FTS5 全文搜索
│   ├── sync_converters.py      # 同步文件格式转换器（策略模式）
│   ├── sync_worker.py          # 文件库→KB 后台同步线程
│   ├── memory.py               # 持久记忆存储（安全扫描）
│   ├── llm.py                  # LLM 调用（OpenAI 兼容）
│   ├── context_compressor.py   # 上下文压缩
│   ├── context_fence.py        # 记忆上下文 fence 标签
│   ├── file_safety.py          # 文件写入安全路径
│   ├── file_lock.py            # 跨平台文件锁
│   ├── auto_extract.py         # 对话自动提取记忆/技能
│   ├── insights.py             # 使用数据洞察分析引擎
│   ├── tools.py                # LLM Function Calling 工具定义
│   └── skills/                 # 技能管理子系统
│       ├── manager.py          # 技能 CRUD
│       ├── curator.py          # 技能审查器（合并与归档）
│       └── usage.py            # 技能使用统计
├── tools/                      # 文档处理命令行脚本
│   ├── doc_process.py          # 文档基础处理
│   ├── mystyle.py              # 公文样式库
│   ├── to_compare.py           # 文档比对（77KB 最大模块）
│   ├── to_docx.py              # 多格式转 DOCX
│   ├── to_redhead.py           # 红头文件生成
│   ├── to_index.py             # 目录索引
│   ├── to_pageNum.py           # 批量添加页码
│   ├── to_pdf.py               # 批量转 PDF
│   ├── float_picture.py        # 浮动图片处理
│   ├── load_config.py          # 配置加载器
│   └── logging_config.py       # 日志配置
├── ui/                         # 前端 SPA
│   ├── index.html              # 主页面
│   └── js/
│       ├── fb.js / fb.css       # 文件库管理器前端
│       └── kb.js / kb.css       # 知识库聊天/文件浏览
├── docker-compose.yml           # Docker 编排
├── Dockerfile                   # Docker 构建
├── requirements.txt             # Python 依赖
├── railway.toml                 # Railway 部署配置
└── README.md                    # 本文件（包含第三方声明）
```

---

## 数据存储

```
workspaces/
├── data/                           # 全局数据
│   ├── auth/users.json             # 用户信息（含 last_active）
│   ├── auth/tokens.json            # Token 映射
│   └── fb/fb.db                   # 文件库数据库
├── {user_id}/                      # 用户独立存储
│   ├── config/                     # 用户配置（含加密 LLM 密钥）
│   ├── workdir/                    # 工作区文件
│   └── kb/                         # 知识库
│       ├── wiki.db                 # 知识库 FTS 数据库
│       ├── data/state.db           # 会话消息数据库
│       ├── memories/               # 持久记忆文件
│       └── skills/                 # 技能文件
```

---

## 配置

### 公文配置（`config/config.yaml`）

```yaml
公司名称:
  简称:
    - 公司简称
  代字: 发文代字
  印章位置: ./config/公司名称.png
compare:
  sentence_similarity_threshold: 0.40
  para_similarity_threshold: 0.40
```

### 知识库配置（`config/kb_config.yaml`）

- LLM 端点、模型、温度等
- 搜索/记忆/会话限制
- 技能生命周期与审查间隔

配置加载优先级：环境变量 `USER_CONFIG_PATH` → `./config/config.yaml`（项目模板）

---

## 环境要求

- **Python** 3.9+
- **Windows**：完整功能（DOC 转换 / PDF 转换需 Microsoft Word）
- **Linux/macOS**：除 win32com 依赖功能外皆可使用
- **Docker**：可选择 Docker 部署（内置 LibreOffice 与中文字体）

## 版权声明

Copyright © 2026 doonly1. All rights reserved.

DocProc（文枢）——本项目源码仅供学习参考，未经授权禁止商用、修改、分发。

### 第三方声明

本项目使用了以下开源组件，感谢作者：

| 组件 | 许可证 | 用途 |
|------|--------|------|
| [Hermes Agent](https://github.com/NousResearch/Hermes-Agent) | MIT | 知识库模块代码逻辑（上下文压缩、技能审查、会话洞察、文件安全等） |
| [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | 系统级技能（诊断、TDD、原型设计、代码审查等） |
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
