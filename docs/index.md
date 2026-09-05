---
layout: page
title: Docflowing · 文澜
---

Docflowing(文澜)是面向公文处理与知识管理的桌面应用,整合**文档处理工具、文件库、知识库 AI 会话、P2P 共享**四大模块。基于 pywebview 桌面壳 + Python Flask 后端 + Vanilla JS 前端,轻量、可离线使用,Windows 全功能支持。

<p align="center">
  <img src="screenshots/home.png" alt="文澜主界面" width="720">
</p>

## 快速入口

- 💾 [下载安装](https://github.com/doonly1/Docflowing/releases/latest) —— 最新版安装包
- 🚀 [快速上手](guide.html) —— 安装、使用与常见问题
- 🧩 [功能详解](features.html) —— 工具集 / 文件库 / 知识库 / P2P 介绍
- 📄 [项目主页](https://github.com/doonly1/Docflowing) —— 源码、Issue 与 Release

## 核心亮点

| 模块 | 能做什么 |
|------|----------|
| 📄 **文档处理工具集** | 文档比对（三级 diff 红蓝标注）、红头文件生成、多格式转 DOCX/PDF、批量加页码、目录索引生成 |
| 🗂️ **文件库管理** | 文件库 CRUD、回收站、批量上传下载、在线编辑预览、工具流式执行、文件库→知识库自动同步 |
| 🧠 **知识库系统** | AI 对话会话、FTS5 全文搜索、持久记忆、技能管理与自动进化、上下文压缩、洞察分析 |
| 🌐 **P2P 共享** | 局域网节点自动发现（mDNS）、Ed25519 签名认证、文件库多级权限共享 |

> AI 功能需自行配置 OpenAI 兼容的 LLM API（知识库 → LLM 设置），密钥在本地加密存储。

<p align="center">
  <img src="screenshots/tools.png" alt="文档工具 - 比对" width="720">
</p>

## 许可证

Copyright © 2026 doonly1. Licensed under the **AGPL-3.0**（详见 [LICENSE](https://github.com/doonly1/Docflowing/blob/main/LICENSE)）。
