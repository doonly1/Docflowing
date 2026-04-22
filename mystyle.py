from docx.shared import Cm, Pt, RGBColor
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
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
    ('H0',        3,  'Normal', 'Normal',   '方正小标宋简体',   22, None,    0,    0,  28.95,    0,    0,    0,  'C'),  # 已改用内置 Title
    ('H1',        4,  'Normal', 'Normal',   '黑体',             16, None, None, None,   None, None, None, None, None),  # 已改用内置 Heading 1
    ('H2',        5,  'Normal', 'Normal',   '楷体',             16, None, None, None,   None, None, None, None, None),  # 已改用内置 Heading 2
    ('H3',        6,  'Normal', 'Normal',   None,               16, True, None, None,   None, None, None, None, None),  # 已改用内置 Heading 3
    ('H4',        7,  'Normal', 'Normal',   None,               16, None, None, None,   None, None, None, None, None),  # 已改用内置 Heading 4
    ('Apdix',     8,  'Normal', 'Normal',   None,             None, None, None, None,   None,   80, None,  -48, None),
    ('Apdix 1',   9,  'Normal', 'Normal',   None,             None, None, None, None,   None,   96, None,  -64, None),
    ('Apdix 2',  10,  'Normal', 'Normal',   None,             None, None, None, None,   None,   96, None,  -16, None),
    ('dater',    11,  'Normal', 'Normal',   None,             None, None, None, None,   None, None,   64,    0,  'R'),
    ('Sign',     12,  'Normal', 'Normal',   None,             None, None, None, None,   None, None, None,    0,  'R'),
    ('Fangsong', 13,  'Normal', 'Normal',   None,             None, None, None, None,   None, None, None,    0,  'L'),
    ('SimHei',   14,  'Normal', 'Normal',   '黑体',           None, None, None, None,   None, None, None,    0, None),
    ('KaiTi',    15,  'Normal', 'Normal',   '楷体',           None, None, None, None,   None, None, None,    0, None),
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
    # 先具现化 Header/Footer（它们来自 latentStyles，删除 latentStyles 后会消失）
    # 访问属性即可触发 python-docx 将其 XML 写入 styles 元素
    for name in ('Header', 'Footer'):
        try:
            _s = doc.styles[name]
        except Exception as e:
            print(f"Style {name} not found: {e}")
            pass
    # 保留的样式：注意 w:name 值 header/footer/heading 是小写，Title/Normal 是首字母大写
    keep = {'Normal', 'Default Paragraph Font', 'header', 'footer'}
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

    # Default Paragraph Font 设为隐藏
    try:
        dpf = doc.styles['Default Paragraph Font']
        dpf.hidden = True
        dpf.unhide_when_used = False
    except Exception:
        pass
    set_some_styles(doc)


def _ensure_style(doc, name, priority):
    """确保样式存在，不存在则创建。Header/Footer 可能只在 latentStyles 中。"""
    try:
        return doc.styles[name]
    except KeyError:
        style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style_attr(style, priority)
        style.base_style = doc.styles['Normal']
        style.next_paragraph_style = doc.styles[name]
        return style


def set_some_styles(doc):
    _ensure_style(doc, 'Header', 16)
    _ensure_style(doc, 'Footer', 17)
    #改变Normal
    style_attr(doc.styles['Normal'], 2)
    run_fm(doc.styles['Normal'], '仿宋', 16, False)
    para_fm(doc.styles['Normal'], 0, 0, 28.95, 0, 0, 32, 'J')
    #改变Header（页眉）：楷体14号，居中，左右缩进16磅
    style_attr(doc.styles['Header'], 16)
    run_fm(doc.styles['Header'], '楷体', 14, None)
    para_fm(doc.styles['Header'], 0, 0, 1, 16, 16, 0, 'C')
    #改变Footer（页脚）：宋体14号，左对齐，左右缩进16磅
    style_attr(doc.styles['Footer'], 17)
    run_fm(doc.styles['Footer'], '宋体', 14, None)
    para_fm(doc.styles['Footer'], 0, 0, 1, 16, 16, 0, 'R')

    # #改变Title（标题）：方正小标宋简体22号，居中，不加粗（覆盖内置默认bold）
    # style_attr(doc.styles['Title'], 3)
    # run_fm(doc.styles['Title'], '方正小标宋简体', 22, False)
    # para_fm(doc.styles['Title'], 0, 0, 28.95, 0, 0, 0, 'C')
    # #改变Heading 1（一级标题）：黑体16号，不加粗（覆盖内置默认bold）
    # style_attr(doc.styles['Heading 1'], 4)
    # run_fm(doc.styles['Heading 1'], '黑体', 16, False)
    # para_fm(doc.styles['Heading 1'], None, None, None, None, None, None, None)
    # #改变Heading 2（二级标题）：楷体16号，不加粗（覆盖内置默认bold）
    # style_attr(doc.styles['Heading 2'], 5)
    # run_fm(doc.styles['Heading 2'], '楷体', 16, False)
    # para_fm(doc.styles['Heading 2'], None, None, None, None, None, None, None)
    # #改变Heading 3（三级标题）：16号加粗
    # style_attr(doc.styles['Heading 3'], 6)
    # run_fm(doc.styles['Heading 3'], None, 16, True)
    # para_fm(doc.styles['Heading 3'], None, None, None, None, None, None, None)
    # #改变Heading 4（四级标题）：16号，不加粗（覆盖内置默认bold）
    # style_attr(doc.styles['Heading 4'], 7)
    # run_fm(doc.styles['Heading 4'], None, 16, False)
    # para_fm(doc.styles['Heading 4'], None, None, None, None, None, None, None)
    

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
    # 取消"对齐到网格"
    # para_f._element 对样式来说是 w:style，对段落来说是 w:p，都需要在内部找/创建 w:pPr
    elem = para_f._element
    if elem is not None:
        pPr = elem.find(qn('w:pPr'))
        if pPr is None:
            pPr = OxmlElement('w:pPr')
            elem.append(pPr)
        snap = pPr.find(qn('w:snapToGrid'))
        if snap is None:
            snap = OxmlElement('w:snapToGrid')
            pPr.append(snap)
        snap.set(qn('w:val'), '0')
        # 取消"如果定义了文档网格，则自动调整右缩进"
        adj = pPr.find(qn('w:adjustRightInd'))
        if adj is None:
            adj = OxmlElement('w:adjustRightInd')
            pPr.append(adj)
        adj.set(qn('w:val'), '0')


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