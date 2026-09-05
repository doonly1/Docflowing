---
layout: page
title: 快速上手
---

# 快速上手

- [回到首页](index.html) · [功能详解](features.html)

## 一、普通用户：下载安装

1. 前往 **[Releases 页面](https://github.com/doonly1/Docflowing/releases/latest)** 下载最新安装包 `Docflowing_Setup.exe`
2. 双击运行安装，安装完成后启动应用
3. 所有知识库、文件库、配置数据自动保存在用户数据目录，无需手动初始化

> 应用内置自动更新：发现新版本后会在后台静默下载，就绪后右下角提示，一键安装。

## 二、开发者：源码运行

```bash
git clone https://github.com/doonly1/Docflowing.git
cd Docflowing
pip install -r requirements.txt

# 开发模式（桌面壳 + 内嵌 Flask 后端）
python desktop_app.py

# 纯浏览器模式（无桌面壳，仅启动 Flask）
python app_server.py
```

数据目录：

| 模式 | 位置 |
|------|------|
| 开发模式 | `%APPDATA%\Docflowing\workspaces\`（Linux/macOS：`~/.docflowing`） |
| 便携版（`--portable`） | 可执行文件同级的 `data/` |
| 打包安装版 | `%APPDATA%\Docflowing\` |

设置环境变量 `DOCFLOWING_DATA_DIR` 可自定义数据目录。

## 三、配置 AI（知识库会话必需）

知识库的 AI 会话、记忆、技能功能需要 OpenAI 兼容 API：

1. 打开应用 → **知识库** → 右上角设置（或文件库选择器旁的配置入口）
2. 填入 Base URL、API Key、模型名
3. 密钥使用 Fernet 加密后写入 `config/kb_config.yaml`，不会明文落盘

## 四、常用操作

### 文档处理工具
打开**工具**标签页 → 选择工具（比对 / 转 DOCX / 转 PDF / 红头 / 页码 / 目录索引）→ 选择文件与参数 → 执行。耗时任务走 SSE 流式输出，可实时看进度。

### 文件库
文件库 = 本地目录托管：创建文件库后可浏览、上传、下载（支持 Zip 打包批量下载）、在线编辑、重命名移动。右键文件可调用文档工具或「同步到知识库」。

### 知识库
- 向 AI 提问前建议先在**知识库文件**中准备资料（Markdown），会参与全文检索
- 长期使用后 AI 会自动沉淀**记忆**与**技能**，越用越贴合你的工作习惯
- 记忆/技能可通过页面直接查看、编辑或删除

### P2P 共享（局域网）
两台机器都运行 Docflowing 且在同一局域网 → 知识库设置中开启 P2P → 节点自动互相发现 → 可共享文件库给信任节点，支持 view / edit / manage 三级权限。

## 五、常见问题（FAQ）

**Q：知识库提问没反应 / 报错？**
A：先检查 LLM 配置是否正确（Base URL/Key/模型），以及本机能否访问该 API 地址。网络代理环境下请在应用外确认连接可用。

**Q：Word 相关工具卡住或文档被占用？**
A：应用内置 WordKeepAlive 保活机制。若仍异常，关闭应用后重启再试；批量转 DOCX 需本机安装 Microsoft Word。

**Q：如何更新到最新版？**
A：右下角更新提示条一键安装；也可去 Releases 手动下载。降级安装会被安装器拦截（防止覆盖为新版本回退）。

**Q：数据会丢吗？**
A：数据全部存在本机用户数据目录（见上表），卸载应用不会删除数据目录；文件库删除先进回收站，可恢复。

**Q：非 Windows 能用吗？**
A：Linux/macOS 可运行 Flask 后端与部分功能（无桌面壳、无 Word COM），完整功能面向 Windows 10+。

## 六、问题反馈

- GitHub Issues：[doonly1/Docflowing/issues](https://github.com/doonly1/Docflowing/issues)
- 附上：版本号（关于弹窗/设置中可见）、操作步骤、报错截图或日志
