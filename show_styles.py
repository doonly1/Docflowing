"""
打印 docx 文件中所有样式（包括显式和隐式/潜在样式）
用法: python show_styles.py <docx文件路径>
"""

import sys
from docx import Document
from docx.enum.style import WD_STYLE_TYPE


STYLE_TYPE_MAP = {
    WD_STYLE_TYPE.PARAGRAPH: "段落",
    WD_STYLE_TYPE.CHARACTER: "字符",
    WD_STYLE_TYPE.TABLE: "表格",
    WD_STYLE_TYPE.LIST: "列表",
}


def show_all_styles(docx_path: str):
    doc = Document(docx_path)

    # ── 显式样式（document.styles 中已定义的）──
    print("=" * 70)
    print("【显式样式】document.styles")
    print("=" * 70)

    for style in doc.styles:
        stype = STYLE_TYPE_MAP.get(style.type, str(style.type))
        builtin_flag = "内置" if style.builtin else "自定义"
        hidden_flag = ", 隐藏" if style.hidden else ""
        priority = f", 优先级: {style.priority}" if style.priority is not None else ""
        print(
            f"  [{stype}] {style.name!r}  (style_id={style.style_id!r}, {builtin_flag}{hidden_flag}{priority})"
        )

    # ── 隐式/潜在样式（latent_styles，存在于模板但未显式添加到文档的内置样式）──
    print()
    print("=" * 70)
    print("【隐式/潜在样式】latent_styles")
    print("=" * 70)

    latent_styles = doc.styles.element.find(
        ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}latentStyles"
    )
    if latent_styles is None:
        print("  （未找到潜在样式定义）")
    else:
        lsd_exceptions = latent_styles.findall(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}lsdException"
        )
        if not lsd_exceptions:
            print("  （无潜在样式例外项）")
        for lsd in lsd_exceptions:
            name = lsd.get(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name",
                lsd.get("w:name", ""),
            )
            locked = lsd.get(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}locked",
                lsd.get("w:locked", "0"),
            )
            qformat = lsd.get(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}qFormat",
                lsd.get("w:qFormat", "0"),
            )
            semi_hidden = lsd.get(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}semiHidden",
                lsd.get("w:semiHidden", "0"),
            )
            ui_priority = lsd.get(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}uiPriority",
                lsd.get("w:uiPriority", ""),
            )
            flags = []
            if locked == "1":
                flags.append("锁定")
            if qformat == "1":
                flags.append("快速样式")
            if semi_hidden == "1":
                flags.append("半隐藏")
            flag_str = f"  [{', '.join(flags)}]" if flags else ""
            pri_str = f", 优先级: {ui_priority}" if ui_priority else ""
            print(f"  {name!r}{flag_str}{pri_str}")

    # ── 统计 ──
    explicit_count = len(doc.styles)
    latent_count = (
        len(lsd_exceptions)
        if latent_styles is not None
        and (
            lsd_exceptions := latent_styles.findall(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}lsdException"
            )
        )
        else 0
    )
    print()
    print("=" * 70)
    print(f"统计：显式样式 {explicit_count} 个，潜在样式例外 {latent_count} 个")
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python show_styles.py <docx文件路径>")
        sys.exit(1)
    show_all_styles(sys.argv[1])
