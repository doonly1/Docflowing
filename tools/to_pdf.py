import os
import subprocess
from doc_process import doc_to_docx, find_libreoffice, libreoffice_install_hint
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


def _convert_single_pdf_docx2pdf(file_path):
    """使用 docx2pdf（Word COM）转换单个 docx → PDF

    docx2pdf 0.1.8 在转换成功后的 word.Quit() 阶段可能因 Word 进程已断开
    抛 COMException(-2147023170) / AttributeError，导致「PDF 已生成却被判失败」。
    这里以 PDF 产物为准：convert 抛异常但 PDF 已产出 → 仍算成功，仅记日志。
    另预删旧 PDF，避免 SaveAs 覆盖已存在文件时弹出确认框导致挂起。
    """
    import pythoncom
    import os
    pythoncom.CoInitialize()
    pdf_path = os.path.splitext(file_path)[0] + '.pdf'
    try:
        # 先删旧 PDF：docx2pdf 未关 DisplayAlerts，覆盖已存在文件会弹确认框挂起
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        from docx2pdf import convert
        convert(file_path)
    except Exception as e:
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            logger.warning('  docx2pdf 收尾异常但 PDF 已生成(忽略): %s - %r', file_path, e)
        else:
            logger.error('  docx2pdf 转换失败: %s - %r', file_path, e)
            return file_path, False
    finally:
        pythoncom.CoUninitialize()
    ok = os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
    if not ok:
        logger.error('  docx2pdf 未产出 PDF: %s', file_path)
    return file_path, ok


def _convert_single_pdf_libreoffice(file_path, lo_cmd):
    """使用 LibreOffice 转换单个文件（以 PDF 产物为准）"""
    workdir = os.path.dirname(file_path)
    cmd = [lo_cmd, '--headless', '--convert-to', 'pdf', '--outdir', workdir, file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    pdf_path = os.path.splitext(file_path)[0] + '.pdf'
    ok = result.returncode == 0 and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
    if not ok:
        logger.error("  LibreOffice 转换失败: %s - %s", file_path, result.stderr.strip())
        return file_path, False
    return file_path, True


def convert_single_to_pdf(file_path):
    """将单个 docx 文件转换为 PDF

    自动检测可用的转换引擎（docx2pdf / LibreOffice）。
    每文件输出「开始/完成」日志，供前端 output log 流式展示进度。
    """
    use_docx2pdf = False
    try:
        import docx2pdf  # noqa: F401
        use_docx2pdf = True
    except ImportError:
        pass

    lo_cmd = find_libreoffice() if not use_docx2pdf else None

    if not use_docx2pdf and not lo_cmd:
        logger.error('错误：无法转换PDF — 需要 Microsoft Word (docx2pdf) 或 LibreOffice')
        logger.error(libreoffice_install_hint())
        return False

    base = os.path.basename(file_path)
    if use_docx2pdf:
        logger.info('  转换中(Word): %s', base)
        _, success = _convert_single_pdf_docx2pdf(file_path)
    else:
        logger.info('  转换中(LibreOffice): %s', base)
        _, success = _convert_single_pdf_libreoffice(file_path, lo_cmd)

    if success:
        logger.info('  完成: %s.pdf', os.path.splitext(base)[0])
        # 上报产物路径，供前端完成后自动打开
        print(f"[[OPEN]]{os.path.splitext(file_path)[0]}.pdf")
    else:
        logger.error('  失败: %s', base)
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
        logger.warning('没有找到需要转换的docx文件')
        return

    success_count = sum(1 for f in docx_files if convert_single_to_pdf(f))
    logger.info('\n转换完成：成功 %s，失败 %s', success_count, len(docx_files) - success_count)


if __name__ == '__main__':
    import sys
    paths = sys.argv[1:] if len(sys.argv) > 1 else [os.path.dirname(__file__)]
    for path in paths:
        if os.path.isfile(path):
            convert_single_to_pdf(path)
        elif os.path.isdir(path):
            convert_to_pdf(path)
