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


## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Web 服务
python server.py
```


### 配置 (config.yaml)

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

### 第三方声明

本项目使用了以下开源组件，感谢它们的作者：

| 组件 | 许可证 | 用途 |
|------|--------|------|
| [Hermes Agent](https://github.com/NousResearch/Hermes-Agent) | MIT | 知识库进化模块设计思想与代码逻辑（上下文压缩、技能审查、会话洞察、文件安全等） |
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

以上组件的原始许可证文本可在各自仓库中查看。其中 Hermes Agent 的 MIT 许可证要求如下：

> MIT License
> Copyright (c) 2025 Nous Research
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
