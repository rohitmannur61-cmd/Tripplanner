"""
generate_docx.py
Converts DISSERTATION_REPORT.md into a properly formatted Word (.docx) document
matching the college dissertation format:
  - Font: Times New Roman 12pt
  - Line spacing: 1.5
  - Margins: Top 0.5", Bottom 0.5", Left 1", Right 0.75"
  - Header: "Trip Planner and Expense Manager | BCA VI"
  - Footer: "[College Name] | Page <N>"
"""

import re
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE_DIR = Path(__file__).parent
MD_PATH  = BASE_DIR / "DISSERTATION_REPORT.md"
OUT_PATH = BASE_DIR / "DISSERTATION_REPORT.docx"

COLLEGE_NAME = "[College Name]"

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def set_run_font(run, size_pt=12, bold=False, italic=False,
                 color=None, font_name="Times New Roman"):
    run.font.name      = font_name
    run.font.size      = Pt(size_pt)
    run.font.bold      = bold
    run.font.italic    = italic
    if color:
        run.font.color.rgb = RGBColor(*color)
    # Force the theme font to Times New Roman as well
    rPr = run._r.get_or_add_rPr()
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"),    font_name)
    rFonts.set(qn("w:hAnsi"),   font_name)
    rFonts.set(qn("w:cs"),      font_name)
    rPr.insert(0, rFonts)


def set_paragraph_format(para, space_before=0, space_after=6,
                          line_spacing=1.5, alignment=WD_ALIGN_PARAGRAPH.LEFT,
                          keep_together=False):
    pf = para.paragraph_format
    pf.space_before    = Pt(space_before)
    pf.space_after     = Pt(space_after)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing    = line_spacing
    pf.alignment       = alignment
    pf.keep_together   = keep_together


def add_paragraph(doc, text="", style=None, alignment=WD_ALIGN_PARAGRAPH.LEFT,
                  bold=False, italic=False, font_size=12, space_after=6,
                  space_before=0, color=None):
    if style:
        para = doc.add_paragraph(style=style)
    else:
        para = doc.add_paragraph()
    set_paragraph_format(para, space_before=space_before,
                         space_after=space_after, alignment=alignment)
    if text:
        run = para.add_run(text)
        set_run_font(run, size_pt=font_size, bold=bold, italic=italic,
                     color=color)
    return para


def add_heading_para(doc, text, level):
    """Add a styled heading paragraph."""
    sizes = {1: 16, 2: 14, 3: 13, 4: 12, 5: 12, 6: 12}
    colors = {
        1: (0,   76,  153),   # Deep blue
        2: (0,   76,  153),
        3: (26, 111, 122),    # Teal
        4: (26, 111, 122),
        5: (0,   0,   0),
        6: (0,   0,   0),
    }
    sz = sizes.get(level, 12)
    col = colors.get(level, (0, 0, 0))
    bold = level <= 4
    para = doc.add_paragraph()
    before = {1: 16, 2: 12, 3: 10, 4: 8, 5: 6, 6: 4}.get(level, 6)
    set_paragraph_format(para, space_before=before, space_after=4,
                         keep_together=True)
    run = para.add_run(text)
    set_run_font(run, size_pt=sz, bold=bold, color=col)
    return para


def add_page_break(doc):
    para = doc.add_paragraph()
    run  = para.add_run()
    run.add_break(docx.oxml.ns.qn and __import__(
        'docx').enum.text.WD_BREAK.PAGE)


def add_code_block(doc, lines):
    """Add a monospace-formatted code block."""
    para = doc.add_paragraph()
    set_paragraph_format(para, space_before=4, space_after=4, line_spacing=1.2)
    pPr = para._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    for side in ("top", "left", "bottom", "right"):
        bdr = OxmlElement(f"w:{side}")
        bdr.set(qn("w:val"), "single")
        bdr.set(qn("w:sz"), "4")
        bdr.set(qn("w:space"), "4")
        bdr.set(qn("w:color"), "AAAAAA")
        pBdr.append(bdr)
    pPr.append(pBdr)
    # Shading
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "F5F5F5")
    pPr.append(shd)
    run = para.add_run("\n".join(lines))
    run.font.name = "Courier New"
    run.font.size = Pt(9)
    return para


def add_table_from_rows(doc, rows):
    """rows[0] = header, rows[1:] = data rows"""
    if not rows:
        return None
    cols = len(rows[0])
    table = doc.add_table(rows=0, cols=cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r_idx, row_data in enumerate(rows):
        tr = table.add_row()
        for c_idx, cell_text in enumerate(row_data):
            cell = tr.cells[c_idx]
            cell.text = ""
            para = cell.paragraphs[0]
            run  = para.add_run(cell_text)
            is_header = (r_idx == 0)
            set_run_font(run, size_pt=10, bold=is_header)
            set_paragraph_format(para, space_before=2, space_after=2,
                                 line_spacing=1.0)
    return table


# ---------------------------------------------------------------------------
# Document sections (header/footer)
# ---------------------------------------------------------------------------

def add_header_footer(doc, section):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    # --- Header ---
    section.header_distance = Pt(20)
    header = section.header
    header.is_linked_to_previous = False
    hpara = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    hpara.clear()
    set_paragraph_format(hpara, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                         space_before=0, space_after=0, line_spacing=1.0)
    run = hpara.add_run("Trip Planner and Expense Manager  |  BCA VI")
    set_run_font(run, size_pt=9, italic=True, color=(80, 80, 80))

    # --- Footer ---
    section.footer_distance = Pt(20)
    footer = section.footer
    footer.is_linked_to_previous = False
    fpara = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    fpara.clear()
    set_paragraph_format(fpara, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                         space_before=0, space_after=0, line_spacing=1.0)
    run1 = fpara.add_run(f"{COLLEGE_NAME}  |  Page ")
    set_run_font(run1, size_pt=9, italic=True, color=(80, 80, 80))

    # Auto page number field
    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.text = "PAGE"
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "end")
    run2 = fpara.add_run()
    run2._r.append(fldChar1)
    run2._r.append(instrText)
    run2._r.append(fldChar2)
    set_run_font(run2, size_pt=9, italic=True, color=(80, 80, 80))


# ---------------------------------------------------------------------------
# Page margins
# ---------------------------------------------------------------------------

def set_margins(section):
    section.top_margin    = Inches(0.5)
    section.bottom_margin = Inches(0.5)
    section.left_margin   = Inches(1.0)
    section.right_margin  = Inches(0.75)


# ---------------------------------------------------------------------------
# Markdown parser → Word
# ---------------------------------------------------------------------------

def parse_md_to_doc(doc, md_text):
    lines = md_text.splitlines()
    i = 0

    table_rows  = []
    code_lines  = []
    in_code     = False
    in_table    = False

    def flush_table():
        nonlocal table_rows, in_table
        if table_rows:
            # Filter out separator rows (--- cells)
            data = [r for r in table_rows
                    if not all(re.match(r'^[-:]+$', c.strip()) for c in r)]
            add_table_from_rows(doc, data)
            doc.add_paragraph()  # spacer
        table_rows = []
        in_table = False

    def flush_code():
        nonlocal code_lines, in_code
        if code_lines:
            add_code_block(doc, code_lines)
        code_lines = []
        in_code = False

    while i < len(lines):
        line = lines[i]

        # Code block
        if line.startswith("```"):
            if not in_code:
                in_code = True
                code_lines = []
            else:
                flush_code()
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        # Table row
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            table_rows.append(cells)
            in_table = True
            i += 1
            continue
        elif in_table:
            flush_table()

        # Horizontal rule (---) → page break separator
        if re.match(r'^-{3,}$', line.strip()):
            doc.add_paragraph()
            i += 1
            continue

        # Headings
        m = re.match(r'^(#{1,6})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            text  = m.group(2).strip()
            add_heading_para(doc, text, level)
            i += 1
            continue

        # Bold line (standalone **text**)
        if re.match(r'^\*\*(.+)\*\*$', line.strip()):
            text = re.sub(r'\*\*', '', line.strip())
            p = doc.add_paragraph()
            set_paragraph_format(p, space_before=2, space_after=2)
            run = p.add_run(text)
            set_run_font(run, bold=True)
            i += 1
            continue

        # Blank line
        if not line.strip():
            doc.add_paragraph()
            i += 1
            continue

        # Bullet points
        if re.match(r'^[-*]\s+', line):
            text = re.sub(r'^[-*]\s+', '', line)
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # strip bold markers
            text = re.sub(r'`(.+?)`', r'\1', text)
            p = doc.add_paragraph(style="List Bullet")
            set_paragraph_format(p, space_before=0, space_after=2,
                                 line_spacing=1.5)
            run = p.add_run(text)
            set_run_font(run)
            i += 1
            continue

        # Numbered list
        if re.match(r'^\d+\.\s+', line):
            text = re.sub(r'^\d+\.\s+', '', line)
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            text = re.sub(r'`(.+?)`', r'\1', text)
            p = doc.add_paragraph(style="List Number")
            set_paragraph_format(p, space_before=0, space_after=2,
                                 line_spacing=1.5)
            run = p.add_run(text)
            set_run_font(run)
            i += 1
            continue

        # Normal paragraph — handle inline bold/italic
        text = line.strip()
        # Strip markdown link syntax for plain text
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)

        p = doc.add_paragraph()
        set_paragraph_format(p, space_before=0, space_after=4)

        # Split by bold markers
        parts = re.split(r'\*\*(.+?)\*\*', text)
        for idx, part in enumerate(parts):
            if idx % 2 == 1:  # bold
                run = p.add_run(part)
                set_run_font(run, bold=True)
            else:
                # Split by italic
                sub_parts = re.split(r'\*(.+?)\*', part)
                for sidx, spart in enumerate(sub_parts):
                    run = p.add_run(spart)
                    set_run_font(run, italic=(sidx % 2 == 1))

        i += 1

    # Flush any remaining table/code
    if in_table:
        flush_table()
    if in_code:
        flush_code()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_docx():
    import docx as _docx_module  # noqa – just to reference the module

    doc = Document()

    # Default paragraph style
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    style.paragraph_format.line_spacing      = 1.5

    section = doc.sections[0]
    set_margins(section)
    add_header_footer(doc, section)

    md_text = MD_PATH.read_text(encoding="utf-8")
    parse_md_to_doc(doc, md_text)

    doc.save(OUT_PATH)
    print(f"[DONE] Saved: {OUT_PATH}")


if __name__ == "__main__":
    build_docx()
