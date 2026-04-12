# -*- coding: utf-8 -*-
"""
文档转Word工具
支持 PDF、DOC、DOCX、TXT、HTML、MD 等格式提取文本，生成公文格式DOCX
"""

import os
import re


def extract_text_from_pdf(file_path):
    """从PDF提取文本"""
    import pdfplumber
    full_text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if not page_text:
                continue
            lines = page_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # 过滤页码
                if re.match(r'^-?\d+-?$', line):
                    continue
                if re.match(r'^第\s*\d+\s*页$', line):
                    continue
                if line.isdigit() and len(line) <= 3:
                    continue
                if '版权所有' in line or '翻印必究' in line:
                    continue
                full_text += line + '\n'
    return full_text.strip()


def extract_text_from_docx(file_path):
    """从DOCX提取文本"""
    from docx import Document
    doc = Document(file_path)
    return '\n'.join(para.text for para in doc.paragraphs if para.text.strip())


def extract_text_from_doc(file_path):
    """从DOC提取文本（转为DOCX后提取）"""
    from doc_process import doc_to_docx
    workdir = os.path.dirname(file_path)
    # 先转换为docx
    doc_to_docx(workdir)
    # 重新查找转换后的docx文件
    basename = os.path.splitext(os.path.basename(file_path))[0]
    docx_path = os.path.join(workdir, basename + '.docx')
    if os.path.exists(docx_path):
        return extract_text_from_docx(docx_path)
    return ""


def extract_text_from_txt(file_path):
    """从TXT提取文本"""
    encodings = ['utf-8', 'gbk', 'gb2312']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read().strip()
        except UnicodeDecodeError:
            continue
    return ""


def extract_text_from_html(file_path):
    """从HTML提取文本"""
    from bs4 import BeautifulSoup
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    # 移除script和style标签
    for tag in soup(['script', 'style']):
        tag.decompose()
    text = soup.get_text()
    # 清理多余空白
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return '\n'.join(lines)


def extract_text_from_md(file_path):
    """从Markdown提取文本（去除标记）"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    # 移除代码块
    content = re.sub(r'```[\s\S]*?```', '', content)
    # 移除行内代码
    content = re.sub(r'`[^`]+`', '', content)
    # 移除图片
    content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
    # 移除链接，保留文字
    content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)
    # 移除标题标记
    content = re.sub(r'^#{1,6}\s+', '', content, flags=re.MULTILINE)
    # 移除粗体斜体标记
    content = re.sub(r'[*_]{1,3}([^*_]+)[*_]{1,3}', r'\1', content)
    # 移除引用标记
    content = re.sub(r'^>\s*', '', content, flags=re.MULTILINE)
    # 移除列表标记
    content = re.sub(r'^[\s]*[-*+]\s+', '', content, flags=re.MULTILINE)
    content = re.sub(r'^[\s]*\d+\.\s+', '', content, flags=re.MULTILINE)
    # 清理多余空白
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return '\n'.join(lines)


def extract_text(file_path):
    """根据文件扩展名提取文本"""
    ext = os.path.splitext(file_path)[1].lower()
    filename = os.path.basename(file_path)
    
    # 跳过临时文件
    if filename.startswith('~$'):
        return None
    
    extractors = {
        '.pdf': extract_text_from_pdf,
        '.docx': extract_text_from_docx,
        '.doc': extract_text_from_doc,
        '.txt': extract_text_from_txt,
        '.html': extract_text_from_html,
        '.htm': extract_text_from_html,
        '.md': extract_text_from_md,
    }
    
    if ext not in extractors:
        return None
    
    try:
        print(f"正在提取: {filename}")
        return extractors[ext](file_path)
    except Exception as e:
        print(f"  提取失败: {e}")
        return None


def generate_docx(text, workdir=None, filename=None):
    """生成公文文档
    
    Args:
        text: 文档文本内容
        workdir: 保存目录，默认为None（当前目录）
        filename: 输出文件名（不含扩展名），默认为None（从文本第一行提取）
    """
    import re
    from docx import Document
    from doc_process import (
        clear_styles, add_my_styles, my_number_style, set_page,
        set_headings, set_appendix, set_date, save_docx
    )
    
    if workdir is None:
        workdir = os.getcwd()
    
    doc = Document()
    clear_styles(doc)
    add_my_styles(doc)
    my_number_style(doc)
    set_page(doc)

    for line in text.splitlines():
        doc.add_paragraph(line)
    
    # 清理文件名中的非法字符
    if filename is None:
        first_line = text.splitlines()[0] if text.splitlines() else "未命名"
        filename = re.sub(r'[\\/:*?"<>|]', '_', first_line)
    
    set_headings(doc)
    set_appendix(doc)
    set_date(doc)
    save_docx(doc, f"{filename}.docx", workdir)


def convert_folder(workdir):
    """转换文件夹中的所有支持的文档"""
    supported_ext = ('.pdf', '.docx', '.doc', '.txt', '.html', '.htm', '.md')
    
    files = [f for f in os.listdir(workdir) 
             if os.path.splitext(f)[1].lower() in supported_ext]
    
    # 跳过带4位数下划线前缀的docx文件（避免重复处理）
    original_count = len(files)
    files = [f for f in files if not (
        os.path.splitext(f)[1].lower() == '.docx' and 
        re.match(r'^\d{4}_', f)
    )]
    skipped = original_count - len(files)
    if skipped > 0:
        print(f"已跳过 {skipped} 个带4位数前缀的docx文件（避免重复处理）")
    
    if not files:
        print("未找到支持的文档文件 (pdf/doc/docx/txt/html/md)")
        return
    
    success_count = 0
    
    for filename in files:
        file_path = os.path.join(workdir, filename)
        text = extract_text(file_path)
        if text:
            # 从原始文件名获取（去除扩展名）
            base_name = os.path.splitext(filename)[0]
            generate_docx(text, workdir, base_name)
            success_count += 1
        print()
    
    print(f"{'='*50}")
    print(f"转换完成: 成功 {success_count}, 失败 {len(files) - success_count}")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        workdir = sys.argv[1]
    else:
        workdir = os.path.dirname(__file__)
    
    if os.path.isdir(workdir):
        convert_folder(workdir)
    else:
        generate_docx(workdir)
