# DocProc · 文枢

> DocProc——Document Process，公文处理工具集。

## 功能模块

| 模块 | 说明 |
|------|------|
| `to_compare.py` | 文档比对（段落/句子/字符三级 diff，红蓝高亮） |
| `to_redhead.py` | 红头文件生成（套红、印章、文号） |
| `to_docx.py` | 多格式转 DOCX（PDF/DOC/DOCX/TXT/HTML/MD） |
| `to_pageNum.py` | 批量添加页码 |
| `to_pdf.py` | 批量转换为 PDF |
| `to_index.py` | 生成目录索引 |
| `float_picture.py` | 浮动图片处理 |
| `mystyle.py` | 样式定义与格式化 |
| `doc_process.py` | 文档处理基础库（标题/附件/日期排版） |
| `server.py` | Web 服务器（Flask，提供文档处理在线服务） |
| `index.html` | 前端页面 |

## 文档比对（to_compare.py）

三级比对架构，从粗到细：

```
段落级匹配 → 句子级匹配 → 字符级 diff
```

### 标记规则

| 标记 | 颜色 | 删除线 | 含义 |
|------|------|--------|------|
| 红色 | RGB(255,0,0) | 无 | 新增内容 |
| 蓝色 | RGB(0,0,255) | ✓ | 删除内容 |

### 支持的比对场景

| 场景 | 处理方式 |
|------|---------|
| 纯新增段落 | 整段红色 |
| 纯删除段落 | 整段蓝色+删除线 |
| 段落内字符修改 | 字符级 diff 精确标记 |
| 段落内句子互换 | 逆序对检测，原位蓝删 + 新位红增 |
| 段落顺序调整 | 段落级逆序对检测，原位蓝删占位 + 新位保留内部差异 |
| 多段落合并为一 | 拼接合并检测，内部走句子/字符级 diff |
| 一段落拆分为多 | 拆分检测，按终稿段落边界切割 diff |
| 中英文标点混用 | 统一支持中英文逗号、句号、叹号、问号、分号、冒号分句 |

### 匹配阈值设置

`config/config.yaml` 中的 `compare` 段：

```yaml
compare:
  sentence_similarity_threshold: 0.40  # 句子相似度阈值（低于此值直接标新增+删除）
  para_similarity_threshold: 0.40      # 段落相似度阈值
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 文档比对
python to_compare.py                          # 处理脚本所在目录，交互选择文件
python to_compare.py [目录]                    # 指定目录，交互选择文件
python to_compare.py [原稿.docx] [终稿.docx]   # 直接指定两个文件

# 转换文档为公文格式（支持 pdf/doc/docx/txt/html/md）
python to_docx.py                  # 处理脚本目录
python to_docx.py [目录]           # 处理指定目录

# 添加页码
python to_pageNum.py [目录]

# 生成红头文件
python to_redhead.py [目录]

# 转 PDF
python to_pdf.py [目录]

# 生成目录索引
python to_index.py [目录]

# 启动 Web 服务
python server.py
```

## 配置说明

服务端配置文件位于 `config/` 目录下 
用户端自动创建`~/.config/doc_tool/config.yaml`

### 发文字号与印章配置 (config.yaml)

```yaml
公司名称:
  简称:
    - 公司简称
  代字: 发文代字
  印章位置: ./config/公司名称.png

compare:
  sentence_similarity_threshold: 0.40
  para_similarity_threshold: 0.40

last_workdir: ""
```

### 印章图片

将印章图片放入“印章位置”对应的目录：
- 文件名需与 `config.yaml` 中配置的公司名称一致
- 格式：PNG

## 项目结构

```
├── config/
│   └── config.yaml          # 配置文件
├── doc_process.py           # 文档处理基础库
├── float_picture.py         # 浮动图片处理
├── index.html               # 前端页面
├── mystyle.py               # 样式定义
├── server.py                # Web 服务器
├── to_compare.py            # 文档比对
├── to_docx.py               # 格式转换
├── to_index.py              # 目录索引
├── to_pageNum.py            # 页码添加
├── to_pdf.py                # PDF 转换
└── to_redhead.py            # 红头文件生成
```

## 环境要求

- Python 3.6+
- Windows（pywin32 依赖 Windows COM 接口，`to_docx.py` 的 DOC 转换和 `to_pdf.py` 需要 Microsoft Word）
- Linux/macOS 可使用除 DOC 转换和 PDF 转换外的功能

## 版权声明

Copyright © 2026 doonly1. All rights reserved.

DocProc（文枢）——本项目源码仅供学习参考，未经授权禁止商用、修改、分发。
