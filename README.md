# 公文处理工具

命令行或web服服，处理 Word 文档。

## 功能模块

| 模块 | 说明 |
|------|------|
| `doc_process.py` | 文档处理、标题/附件/日期排版 |
| `to_redhead.py` | 红头文件生成（套红、印章、文号） |
| `to_pageNum.py` | 批量添加页码 |
| `to_pdf.py` | 批量转换为 PDF |
| `to_docx.py` | 多格式转 DOCX（PDF/DOC/DOCX/TXT/HTML/MD） |
| `to_wordcloud.py` | 生成词云 |
| `to_compare.py` | Word文档比较（段落/句子/字符三级比对） |
| `float_picture.py` | 浮动图片处理 |
| `mystyle.py` | 样式定义与格式化 |
| `server.py` | Web服务器（提供文档处理在线服务） |
| `index.html` | 前端页面（文档选择与处理界面） |

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 转换文档为公文格式（支持 pdf/doc/docx/txt/html/md）
python to_docx.py                  # 处理脚本目录
python to_docx.py [目录]   # 处理指定目录

# 添加页码
python to_pageNum.py [目录]

# 生成红头文件
python to_redhead.py [目录]

# 文档比较
python to_compare.py [目录]
python to_compare.py [文件1] [文件2]

# 转PDF
python to_pdf.py [目录]

# 生成词云
python to_wordcloud.py [目录]
```

## 配置说明

配置文件位于 `config/` 目录下：

### 发文字号配置 (config.yaml)

```yaml
公司名称:
  简称:
    - 公司简称
  代字: 发文代字
  存储路径: ./output
```

### 印章图片

将公司印章图片命名后放入 `config/` 目录：
- 文件名需与 `config.yaml` 中的公司名称一致
- 格式：PNG

## 依赖

- Python 3.6+
- python-docx>=1.2.0
- pyyaml
- jieba (词云)
- wordcloud (词云)
- pywin32 (Windows Word 互操作)
- pymupdf (PDF处理)
- beautifulsoup4 (HTML处理)
