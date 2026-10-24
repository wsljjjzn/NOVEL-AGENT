"""
scripts/course_doc_helpers.py — 课程文档生成辅助工具库。
提供一致的字体、段落排版、表格渲染、代码块格式化等能力。
"""

import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn


def apply_document_styles(doc):
    """设置全局默认字体与段落间距。"""
    # 正文字体
    normal_style = doc.styles['Normal']
    normal_font = normal_style.font
    normal_font.name = 'SimSun'
    normal_font.size = Pt(10.5)  # 五号
    normal_font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    normal_style.paragraph_format.line_spacing = 1.3
    normal_style.paragraph_format.space_after = Pt(4)
    normal_style.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')

    # 页面边距设为标准公文边距 (上下2.54cm, 左右2.8cm)
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.1)
        section.right_margin = Inches(1.1)


def set_cell_background(cell, hex_color: str):
    """设置单元格背景颜色。"""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """设置单元格内边距 (单位 dxa, 20 dxa = 1 pt)。"""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'  <w:top w:w="{top}" w:type="dxa"/>'
        f'  <w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'  <w:left w:w="{left}" w:type="dxa"/>'
        f'  <w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def add_heading_1(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'SimHei'
    run.font.size = Pt(14)  # 四号
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x11, 0x18, 0x27)
    run._r.get_or_add_rPr().set(qn('w:eastAsia'), 'SimHei')
    return p


def add_heading_2(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'SimHei'
    run.font.size = Pt(12)  # 小四
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)
    run._r.get_or_add_rPr().set(qn('w:eastAsia'), 'SimHei')
    return p


def add_heading_3(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'SimHei'
    run.font.size = Pt(10.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x37, 0x41, 0x51)
    run._r.get_or_add_rPr().set(qn('w:eastAsia'), 'SimHei')
    return p


def add_body_p(doc, text: str, bold_prefix: str = "", indent: bool = True):
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.3
    p.paragraph_format.space_after = Pt(4)
    if indent:
        p.paragraph_format.first_line_indent = Pt(21)  # 首行缩进两字符
    if bold_prefix:
        r_prefix = p.add_run(bold_prefix)
        r_prefix.font.name = 'SimSun'
        r_prefix.font.size = Pt(10.5)
        r_prefix.font.bold = True
        r_prefix._r.get_or_add_rPr().set(qn('w:eastAsia'), 'SimSun')
    run = p.add_run(text)
    run.font.name = 'SimSun'
    run.font.size = Pt(10.5)
    run._r.get_or_add_rPr().set(qn('w:eastAsia'), 'SimSun')
    return p


def add_callout(doc, text: str, title: str = "【要点提示】"):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    set_cell_background(cell, "F0F9FF")
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)

    # 边框设置浅蓝实线
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'  <w:top w:val="none"/>'
        f'  <w:left w:val="single" w:sz="24" w:space="0" w:color="0284C7"/>'
        f'  <w:bottom w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    cell._tc.get_or_add_tcPr().append(borders)

    p = cell.paragraphs[0]
    p.paragraph_format.line_spacing = 1.25
    r_title = p.add_run(title + " ")
    r_title.font.name = 'SimHei'
    r_title.font.bold = True
    r_title.font.size = Pt(10)
    r_title.font.color.rgb = RGBColor(0x03, 0x69, 0xA1)

    r_text = p.add_run(text)
    r_text.font.name = 'SimSun'
    r_text.font.size = Pt(10)
    r_text.font.color.rgb = RGBColor(0x0C, 0x4A, 0x6E)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_code_block(doc, code: str, title: str = ""):
    """插入优雅的高亮代码块表格。"""
    if title:
        p_title = doc.add_paragraph()
        p_title.paragraph_format.space_before = Pt(6)
        p_title.paragraph_format.space_after = Pt(2)
        r = p_title.add_run(f"代码片段：{title}")
        r.font.name = 'SimHei'
        r.font.size = Pt(9.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0x4B, 0x55, 0x63)

    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    set_cell_background(cell, "F8FAFC")
    set_cell_margins(cell, top=120, bottom=120, left=180, right=180)

    # 边框设置细实线
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'  <w:top w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        f'  <w:left w:val="single" w:sz="18" w:space="0" w:color="3B82F6"/>'
        f'  <w:bottom w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        f'  <w:right w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        f'</w:tcBorders>'
    )
    cell._tc.get_or_add_tcPr().append(borders)

    lines = code.strip().splitlines()
    for i, line in enumerate(lines):
        if i == 0:
            p = cell.paragraphs[0]
        else:
            p = cell.add_paragraph()
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        run = p.add_run(line)
        run.font.name = 'Consolas'
        run.font.size = Pt(9.0)
        run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def add_styled_table(doc, headers: list[str], rows: list[list[str]], col_widths: list[float] = None):
    """插入带表头底色、居中与边框的规范三线/网格表。"""
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # 表头行
    hdr_cells = table.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].text = title
        set_cell_background(hdr_cells[i], "F1F5F9")
        set_cell_margins(hdr_cells[i], top=120, bottom=120, left=140, right=140)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.line_spacing = 1.15
        run = p.runs[0]
        run.font.name = 'SimHei'
        run.font.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # 数据行
    for r_idx, row_data in enumerate(rows):
        row_cells = table.rows[r_idx + 1].cells
        bg_color = "FFFFFF" if r_idx % 2 == 0 else "F8FAFC"
        for c_idx, val in enumerate(row_data):
            row_cells[c_idx].text = str(val)
            set_cell_background(row_cells[c_idx], bg_color)
            set_cell_margins(row_cells[c_idx], top=80, bottom=80, left=120, right=120)
            p = row_cells[c_idx].paragraphs[0]
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(1)
            # 数字或短内容居中，长段落靠左
            if len(str(val)) <= 8 and '\n' not in str(val):
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            if p.runs:
                run = p.runs[0]
                run.font.name = 'SimSun'
                run.font.size = Pt(9.5)

    # 边框
    for row in table.rows:
        for cell in row.cells:
            borders = parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                f'  <w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                f'  <w:left w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
                f'  <w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                f'  <w:right w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
                f'</w:tcBorders>'
            )
            cell._tc.get_or_add_tcPr().append(borders)

    # 列宽
    if col_widths and len(col_widths) == len(headers):
        for row in table.rows:
            for idx, width in enumerate(col_widths):
                row.cells[idx].width = Inches(width)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def add_cover(doc, doc_type: str, project_title: str):
    """生成完全对齐模板的封面。"""
    p_main = doc.add_paragraph()
    p_main.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_main.paragraph_format.space_before = Pt(36)
    p_main.paragraph_format.space_after = Pt(12)
    r_main = p_main.add_run("《计算机系统项目综合实践》")
    r_main.font.name = 'SimHei'
    r_main.font.size = Pt(22)  # 二号
    r_main.font.bold = True
    r_main.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_after = Pt(48)
    r_sub = p_sub.add_run(doc_type)
    r_sub.font.name = 'SimHei'
    r_sub.font.size = Pt(18)  # 小二
    r_sub.font.bold = True
    r_sub.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

    # 信息块
    info_lines = [
        ("项 目 题 目：", project_title),
        ("组        长：", "班级：计科2101班    学号：2021001001    姓名：鞠兆楠"),
        ("贡献百分比：", "100% (主导系统总体架构设计、领域状态机引擎研发与测试落地)"),
        ("组      员1：", "班级：计科2101班    学号：2021001002    姓名：组员一（协助前端交互与数据测试）"),
        ("贡献百分比：", "0% (单人独立完成项目全栈研发，组员信息备选)"),
        ("组      员2：", "班级：计科2101班    学号：2021001003    姓名：组员二（协助文档校对与测试用例验证）"),
        ("贡献百分比：", "0% (单人独立完成项目全栈研发，组员信息备选)"),
        ("日        期：", "2024 年 10 月 24 日"),
    ]

    table = doc.add_table(rows=len(info_lines), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (label, val) in enumerate(info_lines):
        cell_lbl, cell_val = table.rows[i].cells
        cell_lbl.width = Inches(1.5)
        cell_val.width = Inches(4.5)

        p_lbl = cell_lbl.paragraphs[0]
        p_lbl.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_lbl.paragraph_format.line_spacing = 1.3
        p_lbl.paragraph_format.space_after = Pt(4)
        r_lbl = p_lbl.add_run(label)
        r_lbl.font.name = 'SimHei'
        r_lbl.font.size = Pt(11)
        r_lbl.font.bold = True

        p_val = cell_val.paragraphs[0]
        p_val.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p_val.paragraph_format.line_spacing = 1.3
        p_val.paragraph_format.space_after = Pt(4)
        r_val = p_val.add_run(val)
        r_val.font.name = 'SimSun'
        r_val.font.size = Pt(11)
        r_val.font.underline = True if "题目" in label else False

    doc.add_page_break()
