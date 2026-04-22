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


# 样式定义表：(样式名, priority, base_style, next_style, 字体, 字号, 加粗, 段前, 段后, 行距, 左缩进, 右缩进, 首行缩进, 对齐)
# None 表示继承 base_style，不显式设置
STYLE_DEFS = [
    ('H0',        3,  'Normal', 'Normal',   '方正小标宋简体',   22, None,    0,    0,  28.95,    0,    0,    0,  'C'),
    ('unindent',  1,  'Normal', 'Normal',   None,             None, None, None, None,   None, None, None,    0,  'L'),
    ('H1',        4,  'Normal', 'Normal',   '黑体',             16, None, None, None,   None, None, None, None, None),
    ('H2',        5,  'Normal', 'Normal',   '楷体',             16, None, None, None,   None, None, None, None, None),
    ('H3',        6,  'Normal', 'Normal',   None,               16, True, None, None,   None, None, None, None, None),
    ('H4',        7,  'Normal', 'Normal',   None,               16, None, None, None,   None, None, None, None, None),
    ('Apdix',     9,  'Normal', 'Normal',   None,             None, None, None, None,   None,   80, None,  -48, None),
    ('Apdix 1',  10,  'Normal', 'Normal',   None,             None, None, None, None,   None,   96, None,  -64, None),
    ('Apdix 2',  11,  'Normal', 'Normal',   None,             None, None, None, None,   None,   96, None,  -16, None),
    ('dater',    12,  'Normal', 'Normal',   None,             None, None, None, None,   None, None,   64,    0,  'R'),
    ('Sign',     13,  'Normal', 'Normal',   None,             None, None, None, None,   None, None, None,    0,  'R'),
    ('SimHei',   14,  'Normal', 'Normal',   '黑体',           None, None, None, None,   None, None, None,    0, None),
    ('KaiTi',    15,  'Normal', 'Normal',   '楷体',           None, None, None, None,   None, None, None,    0, None),
    ('heder',    16,  'Normal', 'heder',    '楷体',             14, None,    0,    0,      1,   16,   16,    0,  'C'),
    ('foter',    17,  'Normal', 'foter',    '宋体',             14, None,    0,    0,      1,   16,   16,    0,  'L')
]


# 中文字体 → 西文用
ASCII_FONT_MAP = {
    '宋体': '宋体',
    '黑体': '黑体',
    '仿宋': 'Times New Roman',
    '楷体': '楷体',
    '方正小标宋简体': '方正小标宋简体',
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
    #删除原有样式
    keep = {'Normal', 'Default Paragraph Font', 'page number'}
    styles_elem = doc.styles.element
    to_remove = []
    for style_elem in styles_elem.findall(qn('w:style')):
        name_elem = style_elem.find(qn('w:name'))
        name = name_elem.get(qn('w:val')) if name_elem is not None else ''
        if name in keep:
            continue
        to_remove.append(style_elem)
    for elem in to_remove:
        styles_elem.remove(elem)
    #删除潜藏样式（latentStyles）
    ls = styles_elem.find(qn('w:latentStyles'))
    if ls is not None:
        styles_elem.remove(ls)
    #改变Normal
    style_attr(doc.styles['Normal'], 2)
    run_fm(doc.styles['Normal'], '仿宋', 16, False)
    para_fm(doc.styles['Normal'], 0, 0, 28.95, 0, 0, 32, 'J')

def add_my_styles(doc):
    for name, priority, base, next_st, *_ in STYLE_DEFS:
        try:
            add_style(doc, name, priority, base_style_name=base, next_style_name=next_st)
        except Exception:
            pass

    for name, priority, base, next_st, font, size, bold, spc_bef, spc_af, line_spc, left_ind, right_ind, first_l_ind, align in STYLE_DEFS:
        try:
            run_fm(doc.styles[name], font, size, bold)
            para_fm(doc.styles[name],
                    spc_bef, spc_af, line_spc, left_ind, right_ind, first_l_ind, align)
        except Exception:
            pass


def add_style(doc, style_name, priority, hidden=True, quick=True, base_style_name='Normal', next_style_name='Normal'):
    styles = doc.styles
    style = styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
    style_attr(style, priority)
    style.base_style = styles[base_style_name]
    style.next_paragraph_style = styles[next_style_name]


def style_attr(style, priority):
    style.hidden = False
    style.unhide_when_used = False
    style.quick_style = True
    style.priority = priority
    style.locked = False


def para_fm(para_name, spc_bef, spc_af, line_spc, left_ind, right_ind, first_l_ind, align):
    para_f = getattr(para_name, 'paragraph_format', para_name)
    if spc_bef is not None:
        para_f.space_before = Pt(spc_bef)
    if spc_af is not None:
        para_f.space_after = Pt(spc_af)
    if line_spc is not None:
        para_f.line_spacing = Pt(line_spc) if line_spc > 3 else line_spc
    if left_ind is not None:
        para_f.left_indent = Pt(left_ind)
    if right_ind is not None:
        para_f.right_indent = Pt(right_ind)
    if first_l_ind is not None:
        para_f.first_line_indent = Pt(first_l_ind)
    if align is not None:
        para_f.alignment = ALIGN_MAP[align]
    para_f.widow_control = False
    para_f.keep_with_next = False
    para_f.page_break_before = False
    para_f.keep_together = False


def run_fm(run, font_type=None, font_size=None, bold=None, r=None, g=None, b=None):
    font3 = run.font
    if font_type is not None:
        font_name = ASCII_FONT_MAP.get(font_type, 'Times New Roman')
        font3.name = font_name
        font3.element.rPr.rFonts.set(qn('w:eastAsia'), font_type)
    if font_size is not None:
        font3.size = Pt(font_size)
    if bold is not None:
        font3.bold = bold
    if r is not None and g is not None and b is not None:
        font3.color.rgb = RGBColor(r, g, b)
    font3.snap_to_grid = False


def my_number_style(doc):
    done = False
    for src in [doc.styles, doc.styles.latent_styles]:
        try:
            run_fm(src['page number'], '宋体', 14)
            para_fm(src['page number'], 0, 0, 1, 14, 14, 0, 'R')
            style_attr(src['page number'], 20)
            done = True
            break
        except Exception:
            continue

    if not done:
        add_style(doc, 'page number', 20)
        run_fm(doc.styles['page number'], '宋体', 14)
        para_fm(doc.styles['page number'], 0, 0, 1, 14, 14, 0, 'R')
