import os
import re
from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

from mystyle import my_number_style, set_page
from doc_process import doc_to_docx, save_docx


def _make_page_field():
    """构造 "第 X 页" PAGE 域的 XML 片段（python-docx 无高层 API，直接拼 XML）。"""
    # w:fldChar begin / instrText PAGE / fldChar separate / placeholder / fldChar end
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    return parse_xml(
        '<w:r %s>'
        '<w:fldChar w:fldCharType="begin"/>'
        '<w:instrText xml:space="preserve"> PAGE </w:instrText>'
        '<w:fldChar w:fldCharType="separate"/>'
        '<w:t xml:space="preserve"> 1 </w:t>'
        '<w:fldChar w:fldCharType="end"/>'
        '</w:r>' % w
    )


def _make_text_run(text):
    """构造纯文本 run 的 XML 片段。"""
    return parse_xml('<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:t xml:space="preserve">%s</w:t></w:r>' % text)


def set_page_number(doc):
    """
    用 python-docx 替代 win32 COM，在所有 section 的 footer 末尾追加
    "- 页 -" 域。
    只需在第一个 section 的 footer 添加，其余节通过 is_linked_to_previous 自动继承。
    """
    section = doc.sections[0]
    footer = section.footer

    # 确保 footer 有段落可承接内容
    if not footer.paragraphs:
        footer.add_paragraph()
    para = footer.paragraphs[0]

    # 应用 page number 样式（字体、字号、右对齐等）
    try:
        para.style = doc.styles['page number']
    except Exception:
<<<<<<< HEAD
        word = win32.Dispatch('Word.Application')
    word.Visible = 0
    # Word COM 要求绝对路径
    file_path = os.path.abspath(file_path)
    doc = word.Documents.Open(file_path)
    
    # 使用动态方式获取常量
    wdHeaderFooterPrimary = constants.__dict__.get('wdHeaderFooterPrimary', 1)
    
    for wd_section in doc.Sections:
        try:
            wd_section.Footers(wdHeaderFooterPrimary).PageNumbers.Add(PageNumberAlignment=2)
            wd_section.Footers(wdHeaderFooterPrimary).PageNumbers.NumberStyle = 57
        except Exception as e:
            # 备用方案：直接通过索引访问
            try:
                wd_section.Footers(1).PageNumbers.Add(PageNumberAlignment=2)
                wd_section.Footers(1).PageNumbers.NumberStyle = 57
            except Exception as e2:
                print(f"  页码设置失败: {e2}")
    doc.Save()
    doc.Close()
=======
        pass

    # 如果段落已有内容，先加空格分隔
    if para.text:
        para.add_run('  ')

    # "- 1 -" 格式
    para._p.append(_make_text_run('- '))
    para._p.append(_make_page_field())
    para._p.append(_make_text_run(' -'))

>>>>>>> libreoffice

def add_page_numbers(workdir):
    print('当前工作目录：', workdir)
    doc_to_docx(workdir)
    files = [f for f in os.listdir(workdir)
            if f.endswith('.docx') and not f.startswith("~$")
            and not re.match(r'^\d{4}_', f)]

    for file in files:
        doc = Document(os.path.join(workdir, file))
        save_docx(doc, file, workdir)
    digit_files = [f for f in os.listdir(workdir)
                   if f.endswith('.docx') and f[:4].isdigit()]

    # 对数字前缀文件添加页码
    for file in digit_files:
        print('添加页码：', file, end='  ')
        file_path = os.path.join(workdir, file)

        doc = Document(file_path)
        set_page(doc)
        my_number_style(doc)
        set_page_number(doc)
        doc.save(file_path)
        print('成功。')

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        workdir = sys.argv[1]
    else:
        workdir = os.path.dirname(__file__)
    add_page_numbers(workdir)

