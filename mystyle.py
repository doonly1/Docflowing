from docx.shared import Cm, Pt, RGBColor
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
import itertools

# 对齐方式映射
ALIGN_MAP = {
    'L': WD_PARAGRAPH_ALIGNMENT.LEFT,
    'R': WD_PARAGRAPH_ALIGNMENT.RIGHT,
    'C': WD_PARAGRAPH_ALIGNMENT.CENTER,
    'J': WD_PARAGRAPH_ALIGNMENT.JUSTIFY,
}

# 样式定义表：(样式名, priority, 字体, 字号, 段前, 段后, 行距, 左缩进, 右缩进, 首行缩进, 对齐)
STYLE_DEFS = [
    ('Norm',      2,  '仿宋',           16, 0, 0, 28.95,  0, 0,  32, 'J'),
    ('unindent',  1,  '仿宋',           16, 0, 0, 28.95,  0, 0,   0, 'L'),
    ('Tit',       3,  '方正小标宋简体',  22, 0, 0, 28.95,  0, 0,   0, 'C'),
    ('H1',        4,  '黑体',           16, 0, 0, 28.95,  0, 0,  32, 'J'),
    ('H2',        5,  '楷体',           16, 0, 0, 28.95,  0, 0,  32, 'J'),
    ('H3',        6,  '仿宋',           16, 0, 0, 28.95,  0, 0,  32, 'J'),
    ('H4',       21,  '仿宋',           16, 0, 0, 28.95,  0, 0,  32, 'J'),
    ('Apdix',     9,  '仿宋',           16, 0, 0, 28.95, 80, 0, -48, 'J'),
    ('Apdix 1',  10,  '仿宋',           16, 0, 0, 28.95, 96, 0, -64, 'J'),
    ('Apdix 2',  11,  '仿宋',           16, 0, 0, 28.95, 96, 0, -16, 'J'),
    ('Blackbody',12,  '黑体',           16, 0, 0, 28.95,  0, 0,   0, 'J'),
    ('Regular',  17,  '楷体',           16, 0, 0, 28.95,  0, 0,   0, 'J'),
    ('heder',    15,  '楷体',           14, 0, 0,     1, 16, 16,   0, 'C'),
    ('foter',    16,  '宋体',           14, 0, 0,     1, 16, 16,   0, 'L'),
    ('dater',    13,  '仿宋',           16, 0, 0, 28.95,  0, 64,   0, 'R'),
    ('Sign',     14,  '仿宋',           16, 0, 0, 28.95,  0, 0,    0, 'R'),
]

# 固有样式
ORIGIN_STYLES = [
    ('Normal',    2,  '仿宋',           16, 0, 0, 28.95,  0, 0,  32, 'J'),
    ('Title',     3,  '方正小标宋简体',  22, 0, 0, 28.95,  0, 0,   0, 'C'),
    ('Heading 1', 4,  '黑体',           16, 0, 0, 28.95,  0, 0,  32, 'J'),
    ('Heading 2', 5,  '楷体',           16, 0, 0, 28.95,  0, 0,  32, 'J'),
    ('Heading 3', 6,  '仿宋',           16, 0, 0, 28.95,  0, 0,  32, 'J'),
    ('Heading 4', 21, '仿宋',           16, 0, 0, 28.95,  0, 0,  32, 'J')    
]

# 中文字体名 → ASCII 字体名映射
ASCII_FONT_MAP = {
    '宋体': 'SimSun',
    '黑体': 'SimHei',
    '仿宋': 'Times New Roman',
    '楷体': 'KaiTi',
    '方正小标宋简体': 'FZXiaoBiaoSong-B05S',
}


def set_page(doc):
    for sec in doc.sections:
        sec.left_margin = Cm(2.8)
        sec.right_margin = Cm(2.6)
        sec.top_margin = Cm(3.7)
        sec.bottom_margin = Cm(3.5)
        sec.gutter = Cm(0)
        sec.header_distance = Cm(2)
        sec.footer_distance = Cm(2.5)

        doc.settings.odd_and_even_pages_header_footer = False
        for hdr in (sec.header, sec.even_page_header):
            hdr.is_linked_to_previous = True
        for ftr in (sec.footer, sec.even_page_footer):
            ftr.is_linked_to_previous = True


def clear_styles(doc):
    #删除冗余样式
    for style in itertools.chain(doc.styles, doc.styles.latent_styles):
        style_attr(style, style.priority)
        if style.name not in ['Normal', 'page number']:
            try:
                style.quick_style = False
                style.delete()
            except Exception:
                print('未删除：', style.name)

def change_origin_styles(doc):
    #改变原始样式
    for name, priority, font, size, spc_bef, spc_af, line_spc, left_ind, right_ind, first_l_ind, align in ORIGIN_STYLES:
        for styles in [doc.styles, doc.styles.latent_styles]:
            try:
                run_fm(styles[name], font, size)
                para_fm(styles[name],
                        spc_bef, spc_af, line_spc, left_ind, right_ind, first_l_ind, align)
            except Exception:
                pass

def add_my_styles(doc):
    for name, priority, *_ in STYLE_DEFS:
        try:
            add_style(doc, name, priority)
        except Exception:
            pass

    for name, priority, font, size, spc_bef, spc_af, line_spc, left_ind, right_ind, first_l_ind, align in STYLE_DEFS:
        try:
            run_fm(doc.styles[name], font, size)
            para_fm(doc.styles[name],
                    spc_bef, spc_af, line_spc, left_ind, right_ind, first_l_ind, align)
        except Exception:
            pass


def style_attr(style, priority):
    style.hidden = False
    style.unhide_when_used = False
    style.quick_style = True
    style.priority = priority
    style.locked = False


def para_fm(para_name, spc_bef, spc_af, line_spc, left_ind, right_ind, first_l_ind, align):
    para_f = getattr(para_name, 'paragraph_format', para_name)
    para_f.space_before = Pt(spc_bef)
    para_f.space_after = Pt(spc_af)
    para_f.line_spacing = Pt(line_spc) if line_spc > 3 else line_spc
    para_f.left_indent = Pt(left_ind)
    para_f.right_indent = Pt(right_ind)
    para_f.first_line_indent = Pt(first_l_ind)
    para_f.alignment = ALIGN_MAP[align]
    para_f.widow_control = False
    para_f.keep_with_next = False
    para_f.page_break_before = False
    para_f.keep_together = False


def run_fm(run, font_type='仿宋', font_size=16, r=0, g=0, b=0):
    font3 = run.font
    font_name = ASCII_FONT_MAP.get(font_type, 'Times New Roman')
    font3.name = font_name
    font3.element.rPr.rFonts.set(qn('w:eastAsia'), font_type)
    font3.size = Pt(font_size)
    font3.color.rgb = RGBColor(r, g, b)
    font3.snap_to_grid = False


def add_style(doc, style_name, priority, hidden=True, quick=True):
    styles = doc.styles
    style = styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
    style.hidden = hidden
    style.unhide_when_used = False
    style.quick_style = quick
    style.priority = priority
    style.base_style = styles['Normal']


def my_number_style(doc):
    done = False
    for src in [doc.styles, doc.styles.latent_styles]:
        try:
<<<<<<< HEAD
            s = src['page number']
            run_fm(s, '宋体', 14)
            style_attr(s, 20)
=======
            run_fm(src['page number'], '宋体', 14)
            para_fm(src['page number'], 0, 0, 1, 14, 14, 0, 'R')
            style_attr(src['page number'], 20)
>>>>>>> libreoffice
            done = True
            break
        except Exception:
            continue

    if not done:
        add_style(doc, 'page number', 20)
        run_fm(doc.styles['page number'], '宋体', 14)
        para_fm(doc.styles['page number'], 0, 0, 1, 14, 14, 0, 'R')
