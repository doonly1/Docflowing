import os
import subprocess
from doc_process import doc_to_docx, find_libreoffice, libreoffice_install_hint
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing


def _convert_single_pdf_docx2pdf(file_path):
    """使用 docx2pdf（win32com）转换单个文件"""
    from docx2pdf import convert
    convert(file_path)
    return file_path, True


def _convert_single_pdf_libreoffice(file_path, lo_cmd):
    """使用 LibreOffice 转换单个文件"""
    workdir = os.path.dirname(file_path)
    cmd = [lo_cmd, '--headless', '--convert-to', 'pdf', '--outdir', workdir, file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return file_path, True
    else:
        print(f"  LibreOffice 转换失败: {file_path} - {result.stderr.strip()}")
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

    # 检测可用的转换方式
    use_docx2pdf = False
    try:
        from docx2pdf import convert  # noqa: F401
        use_docx2pdf = True
    except ImportError:
        pass

    lo_cmd = find_libreoffice() if not use_docx2pdf else None

    if not use_docx2pdf and not lo_cmd:
        print('错误：无法转换PDF — 需要 Microsoft Word (docx2pdf) 或 LibreOffice')
        print(libreoffice_install_hint())
        return

    if use_docx2pdf:
        print('使用 docx2pdf (Word COM) 转换...')
    else:
        print(f'使用 LibreOffice 转换: {lo_cmd}')

    # 使用多进程并行转换
    success_count = 0
    fail_count = 0
    max_workers = min(multiprocessing.cpu_count(), len(docx_files))

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        if use_docx2pdf:
            futures = {executor.submit(_convert_single_pdf_docx2pdf, f): f for f in docx_files}
        else:
            futures = {executor.submit(_convert_single_pdf_libreoffice, f, lo_cmd): f for f in docx_files}
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
