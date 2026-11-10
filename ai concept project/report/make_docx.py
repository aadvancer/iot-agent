"""Build report.docx from report.tex so the Word and PDF versions share one source.

Usage (from this directory): python make_docx.py
Needs pandoc and python-docx. LaTeX constructs pandoc cannot convert are
pre-processed: numbered references and citations are resolved here, the
algorithm environments become formatted pseudocode, and the cover page, fonts
(Times New Roman 12 pt), margins (2.5 cm) and single line spacing are applied
with python-docx afterwards.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

HERE = Path(__file__).resolve().parent
TEX = HERE / "report.tex"
OUT = HERE / "report.docx"
FONT = "Times New Roman"


def _matching_brace(s, open_idx):
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced braces")


def _unwrap(s, command):
    """Drop `command{...}` wrappers (whose last argument is the content), keeping the content."""
    start = 0
    while (i := s.find(command, start)) != -1:
        j = i + len(command)
        if j < len(s) and s[j].isalpha():        # a longer command name, e.g. \textscale
            start = j
            continue
        if j >= len(s) or s[j] != "{":           # bare command without argument: drop the token
            s = s[:i] + s[j:]
            continue
        while True:                              # skip leading arguments until the content argument
            k = _matching_brace(s, j)
            if k + 1 < len(s) and s[k + 1] == "{":
                j = k + 1
                continue
            s = s[:i] + s[j + 1:k] + s[k + 1:]
            break
    return s


def _labels(tex):
    """Number figures, tables, algorithms and sections in order of appearance."""
    numbers, counters = {}, {"figure": 0, "table": 0, "algorithm": 0, "section": 0}
    for m in re.finditer(r"\\begin\{(figure|table|algorithm)\}|\\section\{|\\label\{([^}]+)\}", tex):
        if m.group(1):
            counters[m.group(1)] += 1
            last = m.group(1)
        elif m.group(0).startswith(r"\section"):
            counters["section"] += 1
            last = "section"
        else:
            numbers[m.group(2)] = counters[last]
    return numbers


def _algorithms(tex):
    """Plain-text pseudocode for each algorithm environment: (caption, [(depth, text, numbered)]).
    The nesting depth is taken from the source indentation (two spaces per level)."""
    keywords = {"While": ("while", "do"), "For": ("for", "do"), "If": ("if", "then"), "ElsIf": ("else if", "then")}
    out = []
    for block in re.findall(r"\\begin\{algorithm\}.*?\\end\{algorithm\}", tex, re.S):
        caption = re.search(r"\\caption\{(.*?)\}\\label", block).group(1)
        lines = []
        for raw in block.splitlines():
            m = re.match(r"( *)\\(Require|Ensure|State|While|For|If|ElsIf|Else)\b(.*)", raw)
            if not m:
                continue
            indent, kind, rest = m.groups()
            depth = len(indent) // 2
            rest = re.sub(r"\\End(If|While|For)\s*$", "", rest.strip())
            if kind in ("Require", "Ensure"):
                lines.append((0, f"{kind}: {_latex_to_text(rest)}", False))
            elif kind == "State":
                lines.append((depth, _latex_to_text(rest.replace(r"\Return", "return")), True))
            elif kind == "Else":
                lines.append((depth, "else " + _latex_to_text(rest), True))
            else:
                cond, _, tail = _split_arg(rest)
                kw, closing = keywords[kind]
                lines.append((depth, f"{kw} {_latex_to_text(cond)} {closing} {_latex_to_text(tail)}".strip(), True))
        out.append((_latex_to_text(caption), lines))
    return out


def _split_arg(s):
    s = s.strip()
    if not s.startswith("{"):
        return "", "", s
    k = _matching_brace(s, 0)
    return s[1:k], "", s[k + 1:]


SYMBOLS = {r"\gets": "←", r"\to": "→", r"\rightarrow": "→", r"\ge": "≥", r"\ne": "≠", r"\wedge": "∧",
           r"\cup": "∪", r"\emptyset": "∅", r"\in": "∈", r"\le": "≤", r"\pm": "±", r"\,": " ",
           r"\times": "×", "^3": "³", "^k": "ᵏ", "^{3}": "³"}


def _latex_to_text(s):
    s = s.replace(r"\{", "\x01").replace(r"\}", "\x02")     # keep escaped set braces
    s = re.sub(r"\\Comment\{(.*?)\}\s*$", r"   ▷ \1", s)
    for cmd in (r"\textsc", r"\mathit", r"\mathrm", r"\textbf", r"\emph", r"\texttt", r"\code"):
        s = _unwrap(s, cmd)
    for k, v in SYMBOLS.items():
        s = s.replace(k, v)
    s = s.replace("``", "“").replace("''", "”").replace("~", " ").replace("$", "")
    s = s.replace(r"\_", "_").replace(r"\{", "{").replace(r"\}", "}").replace(r"\%", "%")
    s = s.replace(r"\textbf", "").replace(r"\ ", " ").replace("--", "–")
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = s.replace("{", "").replace("}", "").replace("\x01", "{").replace("\x02", "}")
    return re.sub(r"\s+", " ", s).strip()


def preprocess(tex):
    numbers = _labels(tex)
    bib = re.findall(r"\\bibitem\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})", tex, re.S)
    cite_no = {key: i for i, (key, _) in enumerate(bib, 1)}

    body = tex[tex.index(r"\end{titlepage}") + len(r"\end{titlepage}"):tex.index(r"\begingroup")]
    algorithms = _algorithms(body)
    for i in range(len(algorithms)):
        body = re.sub(r"\\begin\{algorithm\}.*?\\end\{algorithm\}", f"\n\nALGORITHMPLACEHOLDER{i}\n\n",
                      body, count=1, flags=re.S)

    # simple inline math as Unicode text: Word equation objects are overkill and render unreliably
    body = re.sub(r"(?<!\\)\$([^$]+)\$", lambda m: _latex_to_text(m.group(1)).replace("-", "−"), body)
    body = re.sub(r"\\cite\{([^}]+)\}",
                  lambda m: "[" + ", ".join(str(cite_no[k.strip()]) for k in m.group(1).split(",")) + "]", body)
    body = re.sub(r"\\ref\{([^}]+)\}", lambda m: str(numbers[m.group(1)]), body)
    body = re.sub(r"\\label\{[^}]+\}", "", body)
    body = _unwrap(body, r"\resizebox")
    body = re.sub(r"\\multirow\{\d+\}\{\*\}\{([^}]*)\}", r"\1", body)
    body = body.replace(r"\begin{tabularx}{\linewidth}{@{}lX@{}}", r"\begin{tabular}{ll}")
    body = body.replace(r"\end{tabularx}", r"\end{tabular}")
    # spanning header cells: keep the text and pad with empty cells so every row has the full width
    body = re.sub(r"\\multicolumn\{(\d+)\}\{[^}]*\}\{(.*?)\}", lambda m: m.group(2) + " & " * (int(m.group(1)) - 1), body)
    body = re.sub(r"\\cmidrule\([^)]*\)\{[^}]*\}", "", body)
    body = body.replace(r"\checkmark", "✓")
    body = body.replace(r"\renewcommand{\code}[1]{\texttt{#1}}", "")
    body = re.sub(r"\\(setlength|renewcommand)\{[^}]*\}(\[[^\]]*\])?\{[^}]*\}", "", body)
    body = body.replace(r"\vspace{4pt}", "").replace(r"\footnotesize", "").replace(r"\small", "")
    body = body.replace(r"\code{", r"\texttt{").replace(r"\ ", " ")
    # numbered captions; pandoc drops LaTeX's automatic numbering
    for env, word in (("figure", "Figure"), ("table", "Table")):
        count = 0

        def number(m, word=word):
            nonlocal count
            count += 1
            return f"\\caption{{{word} {count}: "
        parts = re.split(rf"(\\begin\{{{env}\}}.*?\\end\{{{env}\}})", body, flags=re.S)
        for k, part in enumerate(parts):
            if part.startswith(rf"\begin{{{env}}}"):
                parts[k] = re.sub(r"\\caption\{", number, part, count=1)
        body = "".join(parts)
    # numbered section headings
    sec = 0

    def section(m):
        nonlocal sec
        sec += 1
        return f"\\section*{{{sec}  {m.group(1)}}}"
    body = re.sub(r"\\section\{(.*?)\}", section, body)

    refs = "\n\n\\section*{References}\n\n" + "\n\n".join(
        f"[{i}] " + re.sub(r"\\url\{([^}]+)\}", r"\1", text.strip()).replace(r"\'e", "é").replace("~", " ")
        .replace("--", "–") for i, (_, text) in enumerate(bib, 1))
    preamble = "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n"
    return preamble + body + refs + "\n\\end{document}\n", algorithms


def _cover(tex):
    title = re.search(r"\\LARGE\\bfseries (.*?)\\par", tex, re.S).group(1)
    title = re.sub(r"\\\\\[[^\]]*\]", " ", title).strip()
    name = re.search(r"Student name: (.*?)\\par", tex).group(1)
    sid = re.search(r"Student ID: (.*?)\\par", tex).group(1)
    return re.sub(r"\s+", " ", title), name, sid


def _set_font(run, size=None, bold=None, italic=None, mono=False):
    font = "Courier New" if mono else FONT
    run.font.name = font
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), font)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def _single(p, before=0, after=4):
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)


def _full_width(table):
    """Span the text width and let columns fit their content (pandoc writes narrow fixed widths)."""
    tblpr = table._tbl.tblPr
    for tag in ("w:tblW", "w:tblLayout"):
        for el in tblpr.findall(qn(tag)):
            tblpr.remove(el)
    tblw = OxmlElement("w:tblW")
    tblw.set(qn("w:type"), "pct")
    tblw.set(qn("w:w"), "5000")
    tblpr.append(tblw)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "autofit")
    tblpr.append(layout)
    grid = table._tbl.tblGrid
    for col in grid.findall(qn("w:gridCol")):
        col.attrib.pop(qn("w:w"), None)
    for tc in table._tbl.iter(qn("w:tc")):
        tcpr = tc.tcPr
        if tcpr is not None:
            for el in tcpr.findall(qn("w:tcW")):
                tcpr.remove(el)


def _borders(table):
    """Booktabs-like look: top/bottom rules and a rule under the header row."""
    tbl = table._tbl
    tblpr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "8")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tblpr.append(borders)
    for cell in table.rows[0].cells:
        tcpr = cell._tc.get_or_add_tcPr()
        tcb = OxmlElement("w:tcBorders")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        bottom.set(qn("w:color"), "000000")
        tcb.append(bottom)
        tcpr.append(tcb)


def postprocess(path, tex, algorithms):
    doc = Document(path)
    for section in doc.sections:
        section.page_height, section.page_width = Cm(29.7), Cm(21.0)
        for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
            setattr(section, side, Cm(2.5))

    for style in doc.styles:
        if style.type == 1 and hasattr(style, "font"):          # paragraph styles
            style.font.name = FONT
            rpr = style.element.get_or_add_rPr()
            rfonts = rpr.find(qn("w:rFonts"))
            if rfonts is None:
                rfonts = OxmlElement("w:rFonts")
                rpr.append(rfonts)
            for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                rfonts.set(qn(attr), FONT)
                rfonts.attrib.pop(qn("w:asciiTheme"), None)
                rfonts.attrib.pop(qn("w:hAnsiTheme"), None)
            if style.font.color is not None:
                style.font.color.rgb = None
    doc.styles["Normal"].font.size = Pt(12)
    for name, size in (("heading 1", 14), ("heading 2", 12)):
        for style in doc.styles:
            if style.name.lower() == name:
                style.font.size = Pt(size)
                style.font.bold = True

    # a table with two tabulars gets its caption twice from pandoc; keep the first
    seen = set()
    for p in list(doc.paragraphs):
        if p.style.name == "Table Caption":
            if p.text in seen:
                p._p.getparent().remove(p._p)
            seen.add(p.text)

    width = doc.sections[0].page_width - 2 * Cm(2.5)
    for p in doc.paragraphs:
        _single(p, after=4)
        if p.style.name.startswith("Heading"):
            _single(p, before=8, after=3)
        for run in p.runs:
            mono = run.style is not None and run.style.name == "Verbatim Char"
            if not mono:
                _set_font(run)
        if p.style.name in ("Image Caption", "Table Caption", "Caption"):
            for run in p.runs:
                run.font.size = Pt(10)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for shape in doc.inline_shapes:
        ratio = shape.height / shape.width
        shape.width = width
        shape.height = int(width * ratio)

    for table in doc.tables:
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _full_width(table)
        _borders(table)
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _single(p, after=0)
                    for run in p.runs:
                        _set_font(run, size=9)

    # algorithms
    for p in list(doc.paragraphs):
        m = re.fullmatch(r"ALGORITHMPLACEHOLDER(\d+)", p.text.strip())
        if not m:
            continue
        caption, lines = algorithms[int(m.group(1))]
        p.text = ""
        run = p.add_run(f"Algorithm {int(m.group(1)) + 1}: ")
        _set_font(run, size=10, bold=True)
        _set_font(p.add_run(caption), size=10)
        _single(p, before=6, after=2)
        anchor, number = p, 0
        for depth, text, numbered in lines:
            new = OxmlElement("w:p")
            anchor._p.addnext(new)
            from docx.text.paragraph import Paragraph
            para = Paragraph(new, anchor._parent)
            if numbered:
                number += 1
                _set_font(para.add_run(f"{number:>2}: "), size=10)
            _set_font(para.add_run(text), size=10)
            para.paragraph_format.left_indent = Cm(0.6 * depth + (0.0 if numbered else 0.0))
            _single(para, after=0)
            anchor = para
        _single(anchor, after=6)

    # cover page
    title, name, sid = _cover(tex)
    first = doc.paragraphs[0]
    cover = [("", 12, False, 120), ("The Hong Kong Polytechnic University", 16, False, 0),
             ("COMP5511 Artificial Intelligence Concepts — Final Project Report", 13, False, 12),
             (title, 20, True, 60), (f"Student name: {name}", 14, False, 60),
             (f"Student ID: {sid}", 14, False, 6), ("November 2026", 13, False, 180)]
    for text, size, bold, before in cover:
        para = first.insert_paragraph_before()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _single(para, before=before, after=0)
        if text:
            _set_font(para.add_run(text), size=size, bold=bold)
    brk = first.insert_paragraph_before()
    brk.add_run().add_break(WD_BREAK.PAGE)
    doc.save(path)


def main():
    tex = TEX.read_text(encoding="utf-8")
    body, algorithms = preprocess(tex)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "report_pandoc.tex"
        src.write_text(body, encoding="utf-8")
        resource = ":".join(str(p) for p in (HERE, HERE.parent / "iot_agent/results/figures", HERE.parent / "presentation"))
        subprocess.run(["pandoc", str(src), "-f", "latex", "-t", "docx", "-o", str(OUT),
                        f"--resource-path={resource}"], check=True)
    postprocess(OUT, tex, algorithms)
    print(f"[docx] {OUT}")


if __name__ == "__main__":
    main()
