import os
from docx2pdf import convert
from doc_process import doc_to_docx
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

def convert_single_pdf(file_path):
    """转换单个PDF文件"""
    try:
        convert(file_path)
        return file_path, True
    except Exception as e:
        print(f"  转换失败: {file_path} - {e}")
        return file_path, False

def convert_to_pdf(workdir):
    doc_to_docx(workdir)
    
    # 收集所有需要转换的 docx 文件
    docx_files = [
        os.path.join(workdir, f) 
        for f in os.listdir(workdir) 
        if f.endswith('.docx') and not f.startswith("~$")
    ]
    
    if not docx_files:
        print('没有找到需要转换的docx文件')
        return
    
    # 使用多进程并行转换
    success_count = 0
    fail_count = 0
    max_workers = multiprocessing.cpu_count()
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(convert_single_pdf, f): f for f in docx_files}
        for future in as_completed(futures):
            _, success = future.result()
            if success:
                success_count += 1
            else:
                fail_count += 1
    
    print(f'\n转换完成：成功 {success_count}，失败 {fail_count}')
    

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        workdir = sys.argv[1]
    else:
        workdir = os.path.dirname(__file__)
    convert_to_pdf(workdir)
