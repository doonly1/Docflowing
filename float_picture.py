# -*- coding: utf-8 -*-
"""Word 浮动图片实现 - 图片位于页面顶层，使用 BEHIND TEXT 环绕."""

from docx.oxml import parse_xml, register_element_cls
from docx.oxml.ns import nsdecls
from docx.oxml.shape import CT_Picture
from docx.oxml.xmlchemy import BaseOxmlElement, OneAndOnlyOne

register_element_cls('wp:anchor', CT_Anchor)


class CT_Anchor(BaseOxmlElement):
    """<wp:anchor> 浮动图片容器元素."""

    extent = OneAndOnlyOne('wp:extent')
    docPr = OneAndOnlyOne('wp:docPr')
    graphic = OneAndOnlyOne('a:graphic')

    @classmethod
    def new(cls, cx, cy, shape_id, pic, pos_x, pos_y):
        """创建浮动图片 anchor 元素."""
        anchor = parse_xml(cls._anchor_xml(pos_x, pos_y))
        anchor.extent.cx = cx
        anchor.extent.cy = cy
        anchor.docPr.id = shape_id
        anchor.docPr.name = 'Picture %d' % shape_id
        anchor.graphic.graphicData.uri = (
            'http://schemas.openxmlformats.org/drawingml/2006/picture'
        )
        anchor.graphic.graphicData._insert_pic(pic)
        return anchor

    @classmethod
    def new_pic_anchor(cls, shape_id, rId, filename, cx, cy, pos_x, pos_y):
        """创建包含图片的 anchor 元素."""
        pic = CT_Picture.new(0, filename, rId, cx, cy)
        return cls.new(cx, cy, shape_id, pic, pos_x, pos_y)

    @classmethod
    def _anchor_xml(cls, pos_x, pos_y):
        return (
            '<wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" '
            'relativeHeight="0" behindDoc="1" locked="0" layoutInCell="1" allowOverlap="1" %s>'
            '<wp:simplePos x="0" y="0"/>'
            '<wp:positionH relativeFrom="page"><wp:posOffset>%d</wp:posOffset></wp:positionH>'
            '<wp:positionV relativeFrom="page"><wp:posOffset>%d</wp:posOffset></wp:positionV>'
            '<wp:extent cx="914400" cy="914400"/>'
            '<wp:wrapNone/>'
            '<wp:docPr id="666" name="unnamed"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            '<a:graphic><a:graphicData uri="URI not set"/></a:graphic>'
            '</wp:anchor>' % (nsdecls('wp', 'a', 'pic', 'r'), int(pos_x), int(pos_y))
        )


def add_float_picture(p, image_path_or_stream, width=None, height=None, pos_x=0, pos_y=0):
    """在段落 p 中添加位于页面固定位置的浮动图片.

    Args:
        p: 目标段落
        image_path_or_stream: 图片路径或流
        width: 图片宽度
        height: 图片高度
        pos_x: 相对于页面左上角的水平偏移(EMU)
        pos_y: 相对于页面左上角的垂直偏移(EMU)
    """
    run = p.add_run()
    rId, image = run.part.get_or_add_image(image_path_or_stream)
    cx, cy = image.scaled_dimensions(width, height)
    shape_id, filename = run.part.next_id, image.filename
    anchor = CT_Anchor.new_pic_anchor(shape_id, rId, filename, cx, cy, pos_x, pos_y)
    run._r.add_drawing(anchor)
