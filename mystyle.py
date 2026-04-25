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
    ('H0',        3,  'Normal', 'Normal',   '方正小标宋简体',   22, None,    0,    0,  28.95,    0,    0,    0,  'C'), 
    ('H1',        4,  'Normal', 'Normal',   '黑体',             16, None, None, None,   None, None, None, None, None), 
    ('H2',        5,  'Normal', 'Normal',   '楷体',             16, None, None, None,   None, None, None, None, None), 
    ('H3',        6,  'Normal', 'Normal',   None,               16, True, None, None,   None, None, None, None, None), 
    ('H4',        7,  'Normal', 'Normal',   None,               16, None, None, None,   None, None, None, None, None), 
    ('Apdix',     8,  'Normal', 'Normal',   None,             None, None, None, None,   None,   80, None,  -48, None),
    ('Apdix 1',   9,  'Normal', 'Normal',   None,             None, None, None, None,   None,   96, None,  -64, None),
    ('Apdix 2',  10,  'Normal', 'Normal',   None,             None, None, None, None,   None,   96, None,  -16, None),
    ('dater',    11,  'Normal', 'Normal',   None,             None, None, None, None,   None, None,   64,    0,  'R'),
    ('Sign',     12,  'Normal', 'Normal',   None,             None, None, None, None,   None, None, None,    0,  'R'),
    ('Fangsong', 13,  'Normal', 'Normal',   None,             None, None, None, None,   None, None, None,    0,  'L'),
    ('SimHei',   14,  'Normal', 'Normal',   '黑体',           None, None, None, None,   None, None, None,    0, None),
    ('KaiTi',    15,  'Normal', 'Normal',   '楷体',           None, None, None, None,   None, None, None,    0, None),
    ('Heder',    16,  'Normal', 'Heder',    '楷体',             14, None,    0,    0,      1,   16,   16,    0,  'C'),
    ('Foter',    17,  'Normal', 'Foter',    '宋体',             14, None,    0,    0,      1,   16,   16,    0,  'R'),
]

# 中文字体 → 西文用
ASCII_FONT_MAP = {
    '宋体': '宋体',
    '黑体': '黑体',
    '仿宋': '仿宋',
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
    """
    清空样式框（删除路线）：
    1. 直接从 styles.xml 中移除不需要的显式样式节点（保留 Normal 和字符/表格/列表类型的必要样式）。
    2. latentStyles 设 count=0 + defLockedState=1 + defSemiHidden=1 + defQFormat=0，
       并清空所有 lsdException。count=0 明确告诉 Word "本文档无潜在样式"，
    """
    # ── 1. 删除 styles.xml 中不需要的显式样式节点 ──
    # 必须保留的样式（删掉会导致 docx 损坏或功能异常）
    KEEP_STYLE_IDS = {
        'Normal',                  # 基础正文，必须保留
        'DefaultParagraphFont',    # 字符样式基础，必须保留
        'TableNormal',             # 表格基础样式，必须保留
        'NoList',                  # 列表基础样式，必须保留
    }
    # 同时按 w:name val 保留
    KEEP_NAMES = {
        'Normal',
        'Default Paragraph Font',
        'Normal Table',
        'No List',
    }

    styles_elem = doc.styles.element
    for style_elem in list(styles_elem.findall(qn('w:style'))):
        # 按 styleId 属性判断
        style_id = style_elem.get(qn('w:styleId'), '')
        if style_id in KEEP_STYLE_IDS:
            continue
        # 按 w:name val 判断
        name_elem = style_elem.find(qn('w:name'))
        name = name_elem.get(qn('w:val'), '') if name_elem is not None else ''
        if name in KEEP_NAMES:
            continue
        styles_elem.remove(style_elem)

    # ── 2. 处理 latentStyles：count=0 + 全局隐藏/锁定 + 清空所有 lsdException ──
    # count=0 明确告诉 Word "本文档声明 0 个潜在样式"，
    ls = styles_elem.find(qn('w:latentStyles'))
    if ls is None:
        ls = OxmlElement('w:latentStyles')
        styles_elem.append(ls)

    ls.set(qn('w:defLockedState'), '1')
    ls.set(qn('w:defSemiHidden'), '1')
    ls.set(qn('w:defUnhideWhenUsed'), '0')
    ls.set(qn('w:defQFormat'), '0')
    ls.set(qn('w:count'), '0')

    # 清空所有 lsdException，不留任何例外条目
    for exc in ls.findall(qn('w:lsdException')):
        ls.remove(exc)

    set_oringin_styles(doc)


def set_oringin_styles(doc):
    #改变Normal
    style_attr(doc.styles['Normal'], 2)
    run_fm(doc.styles['Normal'], '仿宋', 16, False)
    para_fm(doc.styles['Normal'], 0, 0, 28.95, 0, 0, 32, 'J')

    # #改变Header（页眉）：楷体14号，居中，左右缩进16磅
    # style_attr(doc.styles['Header'], 16)
    # run_fm(doc.styles['Header'], '楷体', 14, None)
    # para_fm(doc.styles['Header'], 0, 0, 1, 16, 16, 0, 'C')
    # #改变Footer（页脚）：宋体14号，左对齐，左右缩进16磅
    # style_attr(doc.styles['Footer'], 17)
    # run_fm(doc.styles['Footer'], '宋体', 14, None)
    # para_fm(doc.styles['Footer'], 0, 0, 1, 16, 16, 0, 'R')

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
        # 直接写 XML：确保段落级别的 <w:ind w:firstLine> 覆盖任何样式继承值，
        # 避免 python-docx 1.2.0 中 style-level 属性未及时同步导致的残留缩进
        elem = para_f._element
        pPr = elem.find(qn('w:pPr'))
        if pPr is None:
            pPr = OxmlElement('w:pPr')
            elem.append(pPr)
        ind = pPr.find(qn('w:ind'))
        if ind is None:
            ind = OxmlElement('w:ind')
            pPr.append(ind)
        # first_l_ind 单位为 Pt，OOXML 用 twips（1pt=20twips）
        ind.set(qn('w:firstLine'), str(int(first_l_ind * 20)))
        # 清除 firstLineChars：OOXML 规定同级别 firstLineChars 优先于 firstLine，
        # 必须同时清除才能让 firstLine="0" 真正生效（应对继承自 base style 的 firstLineChars）
        for attr in (qn('w:firstLineChars'), qn('w:hangingChars')):
            if attr in ind.attrib:
                del ind.attrib[attr]
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