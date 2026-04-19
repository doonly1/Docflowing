import os
from docx import Document

from mystyle import my_number_style,set_page
from doc_process import doc_to_docx, save_docx
import win32com.client as win32
from win32com.client import constants


def set_page_number(file_path):
    try:
        word = win32.gencache.EnsureDispatch('Word.Application') 
    except Exception:
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

def add_page_numbers(workdir):
    print('当前工作目录：', workdir)
    doc_to_docx(workdir)
    import re
    files = [f for f in os.listdir(workdir) \
            if f.endswith('.docx') and not f.startswith("~$") \
            and not re.match(r'^\d{4}_', f)]
    
    for file in files:
        doc = Document(os.path.join(workdir, file))
        save_docx(doc, file, workdir)
    digit_files = [f for f in os.listdir(workdir) if f.endswith('.docx') and f[:4].isdigit()]

    # 对数字前缀文件添加页码
    for file in digit_files:
        print('添加页码：', file, end = '  ')
        file_path = os.path.join(workdir, file)
#        set_page_number(file_path)
        
        doc = Document(file_path)
        set_page(doc)
        my_number_style(doc)
        doc.save(file_path)
        
        set_page_number(file_path)
        print('成功。')
    try:
        word.Quit()
    except:
        pass

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        workdir = sys.argv[1]
    else:
        workdir = os.path.dirname(__file__)
    add_page_numbers(workdir)

