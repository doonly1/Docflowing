import os
import subprocess
from doc_process import doc_to_docx, find_libreoffice, libreoffice_install_hint
from concurrent.futures import ThreadPoolExecutor, as_completed


def _convert_single_pdf_docx2pdf(file_path):
    """使用 docx2pdf（win32com）转换单个文件（COM 线程安全）"""
    import pythoncom
    pythoncom.CoInitialize()
    try:
        from docx2pdf import convert
        convert(file_path)
        return file_path, True
    finally:
        pythoncom.CoUninitialize()


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


def convert_single_to_pdf(file_path):
    """将单个 docx 文件转换为 PDF

    自动检测可用的转换引擎（docx2pdf 或 LibreOffice）。
    """
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
        return False

    if use_docx2pdf:
        _, success = _convert_single_pdf_docx2pdf(file_path)
    else:
        print(f'使用 LibreOffice 转换: {os.path.basename(file_path)}')
        _, success = _convert_single_pdf_libreoffice(file_path, lo_cmd)
    return success


def convert_to_pdf(workdir):
    """将目录中所有 docx 文件转换为 PDF"""
    doc_to_docx(workdir)

    docx_files = [
        os.path.join(workdir, f)
        for f in os.listdir(workdir)
        if f.lower().endswith('.docx') and not f.startswith("~$")
    ]

    if not docx_files:
        print('没有找到需要转换的docx文件')
        return

    success_count = sum(1 for f in docx_files if convert_single_to_pdf(f))
    print(f'\n转换完成：成功 {success_count}，失败 {len(docx_files) - success_count}')


if __name__ == '__main__':
    import sys
    paths = sys.argv[1:] if len(sys.argv) > 1 else [os.path.dirname(__file__)]
    for path in paths:
        if os.path.isfile(path):
            convert_single_to_pdf(path)
        elif os.path.isdir(path):
            convert_to_pdf(path)
