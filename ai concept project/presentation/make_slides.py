"""Build the presentation deck on the PolyU tutorial template.

Usage (from this directory): python make_slides.py [--template polyu_template.pptx]
Writes AI_Agent_IoT_presentation.pptx. The cover, content and closing slides are
cloned from the template (PolyU logo, red title bar, diagonal bands), all
tutorial slides are removed, and the content is drawn with native shapes so it
stays editable. Every number comes from iot_agent/results/comparison.md.
"""
import argparse
import copy
import re
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Cm, Pt

HERE = Path(__file__).resolve().parent
FIGURES = HERE.parent / "iot_agent" / "results" / "figures"
OUT = HERE / "AI_Agent_IoT_presentation.pptx"

RED = RGBColor(0xC0, 0x00, 0x00)
DARK = RGBColor(0x26, 0x26, 0x26)
GREY = RGBColor(0x76, 0x71, 0x71)
LIGHT = RGBColor(0xD0, 0xCE, 0xCE)
PALE = RGBColor(0xF4, 0xF2, 0xF2)
PINK = RGBColor(0xFB, 0xE9, 0xE9)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
FONT = "Times New Roman"

# template slides used as masters (0-based): cover, section/closing, content
COVER, SECTION, CONTENT = 0, 3, 5


# ------------------------------------------------------------------ template plumbing
def clone_slide(prs, src):
    """Append a copy of `src` (all shapes, images re-linked) and return it."""
    new = prs.slides.add_slide(src.slide_layout)
    for shp in list(new.shapes):
        shp._element.getparent().remove(shp._element)
    for shp in src.shapes:
        el = copy.deepcopy(shp._element)
        for node in el.iter():
            for attr in (qn("r:embed"), qn("r:link"), qn("r:id")):
                rid = node.get(attr)
                if rid and rid in src.part.rels:
                    rel = src.part.rels[rid]
                    node.set(attr, new.part.relate_to(rel._target, rel.reltype))
        new.shapes._spTree.insert_element_before(el, "p:extLst")
    return new


def drop_template_slides(prs, keep_from):
    """Remove the tutorial's own slides (the first `keep_from` slides)."""
    sld_ids = prs.slides._sldIdLst
    for sld in list(sld_ids)[:keep_from]:
        prs.part.drop_rel(sld.rId)
        sld_ids.remove(sld)


def shape(slide, name):
    return next(s for s in slide.shapes if s.name == name)


def remove(slide, name):
    el = shape(slide, name)._element
    el.getparent().remove(el)


def set_paragraph(paragraph, text, size=None, bold=None, color=None):
    """Replace the text of a template paragraph but keep its first run's formatting."""
    runs = paragraph.runs
    first = runs[0]
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    first.text = text
    if size:
        first.font.size = Pt(size)
    if bold is not None:
        first.font.bold = bold
    if color is not None:
        first.font.color.rgb = color


def set_title(slide, text, size=36):
    title = next(s for s in slide.shapes if s.is_placeholder)
    title.width = Cm(21.6)
    tf = title.text_frame
    for p in list(tf.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    set_paragraph(tf.paragraphs[0], text, size=size)


# ------------------------------------------------------------------ drawing helpers
def _font(run, size, bold=False, color=DARK, italic=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:cs", "a:ea"):
        el = rpr.find(qn(tag))
        if el is None:
            el = etree.SubElement(rpr, qn(tag))
        el.set("typeface", FONT)


def _rich(paragraph, text, size, color=DARK, bold=False):
    """Inline markup: **bold**, [[red bold]]."""
    for part in re.split(r"(\*\*.*?\*\*|\[\[.*?\]\])", text):
        if not part:
            continue
        if part.startswith("**"):
            _font(paragraph.add_run(), size, True, color)
            paragraph.runs[-1].text = part[2:-2]
        elif part.startswith("[["):
            _font(paragraph.add_run(), size, True, RED)
            paragraph.runs[-1].text = part[2:-2]
        else:
            _font(paragraph.add_run(), size, bold, color)
            paragraph.runs[-1].text = part


def _bullet(paragraph, level, char="•"):
    ppr = paragraph._p.get_or_add_pPr()
    indent = 0.55 + 0.75 * level
    ppr.set("marL", str(int(Cm(indent))))
    ppr.set("indent", str(int(-Cm(0.5))))
    for tag in ("a:buNone", "a:buChar", "a:buFont"):
        for el in ppr.findall(qn(tag)):
            ppr.remove(el)
    bufont = etree.SubElement(ppr, qn("a:buFont"))
    bufont.set("typeface", "Arial")
    buchar = etree.SubElement(ppr, qn("a:buChar"))
    buchar.set("char", char)


def bullets(slide, x, y, w, h, items, size=20, space=6):
    """items: [(level, text)] ; level 0 is bold like the template's first-level bullets."""
    tb = slide.shapes.add_textbox(Cm(x), Cm(y), Cm(w), Cm(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, (level, text) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        _bullet(p, level)
        p.space_before = Pt(space if level == 0 or i == 0 else 2)
        lvl_size = size if level == 0 else size - 2
        _rich(p, text, lvl_size, bold=(level == 0))
    return tb


def text(slide, x, y, w, h, content, size=18, bold=False, color=DARK, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, italic=False):
    tb = slide.shapes.add_textbox(Cm(x), Cm(y), Cm(w), Cm(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, line in enumerate(content.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        _rich(p, line, size, color, bold)
        if italic:
            for r in p.runs:
                r.font.italic = True
    return tb


def _plain(shp):
    """Drop the theme style reference (shadow/effect); fill, line and text colours are set explicitly."""
    style = shp._element.find(qn("p:style"))
    if style is not None:
        shp._element.remove(style)
    return shp


def box(slide, x, y, w, h, content, fill=PALE, line=None, size=16, bold=False, color=DARK,
        align=PP_ALIGN.CENTER, shape_type=MSO_SHAPE.RECTANGLE, anchor=MSO_ANCHOR.MIDDLE, margin=0.25):
    shp = _plain(slide.shapes.add_shape(shape_type, Cm(x), Cm(y), Cm(w), Cm(h)))
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(1.25)
    tf = shp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, Cm(margin))
    for i, line_text in enumerate(content.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        _rich(p, line_text, size, color, bold)
    return shp


def accent_box(slide, x, y, w, h, content, size=17):
    """Pale box with a red left bar, the template's emphasis style."""
    box(slide, x, y, w, h, content, fill=PALE, size=size, align=PP_ALIGN.LEFT, margin=0.45)
    bar = _plain(slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(x), Cm(y), Cm(0.18), Cm(h)))
    bar.fill.solid()
    bar.fill.fore_color.rgb = RED
    bar.line.fill.background()


def arrow(slide, x1, y1, x2, y2, color=GREY, width=2.0):
    con = _plain(slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Cm(x1), Cm(y1), Cm(x2), Cm(y2)))
    con.line.color.rgb = color
    con.line.width = Pt(width)
    tail = etree.SubElement(con.line._get_or_add_ln(), qn("a:tailEnd"))
    tail.set("type", "triangle")
    return con


def line(slide, x1, y1, x2, y2, color=LIGHT, width=1.5):
    con = _plain(slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Cm(x1), Cm(y1), Cm(x2), Cm(y2)))
    con.line.color.rgb = color
    con.line.width = Pt(width)
    return con


def table(slide, x, y, w, rows, col_w, size=15, row_h=0.85, bold_rows=(), red_rows=(), header=True):
    """Clean table: dark-red header, light rule-like body, highlighted rows for our system."""
    n_rows, n_cols = len(rows), len(rows[0])
    gt = slide.shapes.add_table(n_rows, n_cols, Cm(x), Cm(y), Cm(w), Cm(row_h * n_rows))
    tbl = gt.table
    tbl_pr = gt._element.graphic.graphicData.tbl.tblPr
    for attr in ("bandRow", "firstRow"):
        tbl_pr.set(attr, "0")
    style = tbl_pr.find(qn("a:tableStyleId"))
    if style is not None:
        style.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"   # "No Style, Table Grid" -> overridden below
    total = sum(col_w)
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Cm(w * cw / total)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Cm(row_h)
        for j, value in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = cell.margin_right = Cm(0.15)
            cell.margin_top = cell.margin_bottom = Cm(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            is_header = header and i == 0
            cell.fill.solid()
            cell.fill.fore_color.rgb = RED if is_header else (PINK if i in red_rows else (WHITE if i % 2 else PALE))
            tf = cell.text_frame
            tf.word_wrap = True
            color = WHITE if is_header else (RED if i in red_rows else DARK)
            for k, part in enumerate(str(value).split("\n")):
                p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
                p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
                _rich(p, part, size, color, bold=is_header or i in bold_rows or i in red_rows)
            _cell_border(cell)
    return gt


def _cell_border(cell, color="D0CECE"):
    tcpr = cell._tc.get_or_add_tcPr()
    for edge in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        ln = etree.SubElement(tcpr, qn(edge))
        ln.set("w", "6350")
        fill = etree.SubElement(ln, qn("a:solidFill"))
        clr = etree.SubElement(fill, qn("a:srgbClr"))
        clr.set("val", color)


def picture(slide, path, x, y, w=None, h=None):
    kw = {}
    if w:
        kw["width"] = Cm(w)
    if h:
        kw["height"] = Cm(h)
    return slide.shapes.add_picture(str(path), Cm(x), Cm(y), **kw)


def page_number(slide, n):
    text(slide, 31.6, 18.0, 1.6, 0.8, str(n), size=12, color=GREY, align=PP_ALIGN.RIGHT)


def notes(slide, content):
    slide.notes_slide.notes_text_frame.text = content.strip()


# ------------------------------------------------------------------ slides
def cover(prs, tpl):
    s = clone_slide(prs, tpl.slides[COVER])
    title = shape(s, "object 2")
    title.left, title.width = Cm(1.9), Cm(30)
    paras = title.text_frame.paragraphs
    set_paragraph(paras[0], "AI Agent for Smart Security IoT Systems", size=44)
    set_paragraph(paras[1], "COMP5511 Artificial Intelligence Concepts — Final Project Presentation", size=20)
    who = shape(s, "object 7").text_frame.paragraphs
    set_paragraph(who[0], "Zhang Chi")
    set_paragraph(who[1], "Student ID: 25064822g")
    set_paragraph(who[2], "November 2026")
    notes(s, """
Good morning. My project is an AI agent for smart security IoT systems: a copilot that helps frontline
support staff diagnose faults and decide which tickets really need an FAE engineer.""")
    return s


def content(prs, tpl, title, n):
    s = clone_slide(prs, tpl.slides[CONTENT])
    remove(s, "object 2")
    set_title(s, title)
    page_number(s, n)
    return s


def slide_problem(prs, tpl, n):
    s = content(prs, tpl, "Problem and Motivation", n)
    bullets(s, 1.4, 3.4, 18.2, 10.5, [
        (0, "Gateway-centric (master–slave) IoT"),
        (1, "Cameras and sensors work only through one base station"),
        (0, "Most tickets are interaction faults"),
        (1, "pairing, weak link, firmware protocol, blocked uplink — not broken hardware"),
        (0, "Frontline staff have no standard procedure"),
        (1, "trivial tickets are escalated to scarce FAE engineers"),
        (1, "real protocol / batch faults get buried and resolved late"),
    ], size=21)
    # topology sketch: one master, four slaves, cloud uplink
    box(s, 24.0, 3.6, 5.6, 1.3, "Cloud / App", fill=WHITE, line=LIGHT, size=16)
    box(s, 23.6, 6.7, 6.4, 1.6, "**Base station**\n(master)", fill=RED, color=WHITE, size=16)
    arrow(s, 26.8, 6.7, 26.8, 4.9, color=GREY)
    for i, (label, cx) in enumerate([("Camera", 21.0), ("Door\nsensor", 24.6), ("Motion\nsensor", 28.2),
                                     ("Camera", 31.6)]):
        box(s, cx - 1.5, 10.6, 3.0, 1.6, label, fill=PALE, line=LIGHT, size=14)
        line(s, 26.8, 8.3, cx, 10.6, color=GREY, width=1.5)
    text(s, 20.2, 12.4, 12.6, 0.9, "every peripheral depends on the master", size=14, color=GREY,
         align=PP_ALIGN.CENTER, italic=True)
    accent_box(s, 1.4, 14.3, 31.0, 3.2,
               "**Goal:** diagnose the root cause, then either [[close at frontline (L1)]] with repair steps "
               "and a reply template, or [[escalate to an FAE (L2)]] with a complete ticket.\n"
               "**Users:** frontline support staff (primary) · FAE engineers (receive fewer, better tickets)",
               size=18)
    notes(s, """
In a gateway-centric system every camera and sensor talks only through the base station. During my internship
most tickets were interaction faults between the base and its peripherals, not broken hardware. Frontline staff
had no standard procedure, so simple tickets went to FAE engineers while real protocol or batch faults were buried.
The task is therefore diagnosis plus triage: close at frontline (L1) or escalate with a complete ticket (L2).""")


def slide_architecture(prs, tpl, n):
    s = content(prs, tpl, "Approach: Agent Architecture", n)
    picture(s, HERE / "architecture.png", 2.3, 3.35, w=29.2)
    notes(s, """
Four components. (1) The topology planner collects console evidence in maintenance order: base station, binding
table, link quality, firmware, peripheral, and skips everything below the base if the base is down. (2) Structured
memory keeps confirmed facts in typed slots and blocks repeated queries and fruitless KB searches. (3) The LLM loop,
built with LangGraph and DeepSeek, chooses one tool per step: a console query, a KB search, a question or an action
for the customer, or the final diagnosis. (4) Triage: hard rules R1–R5 from the support policy can only raise the
tier to L2. The LLM never sees the raw transcript, only the memory snapshot plus rule hints.""")


def slide_method(prs, tpl, n):
    s = content(prs, tpl, "Method: Evidence Order and Triage", n)
    text(s, 1.4, 3.3, 20, 0.9, "**Topology planner** — deterministic, no LLM call", size=19)
    stages = [("S1", "Base station"), ("S2", "Binding / capacity"), ("S3", "Link quality"),
              ("S4", "Firmware / protocol"), ("S5", "Peripheral")]
    for i, (sid, label) in enumerate(stages):
        box(s, 1.4 + i * 6.25, 4.4, 6.5, 1.9, f"**{sid}**\n{label}", fill=RED if i == 0 else PALE,
            color=WHITE if i == 0 else DARK, size=15, shape_type=MSO_SHAPE.CHEVRON if i else MSO_SHAPE.PENTAGON)
    text(s, 1.4, 6.45, 31, 0.9, "If the base station is down, S2–S5 are pruned: every peripheral only mirrors the "
         "master's failure.", size=16, color=GREY, italic=True)

    text(s, 1.4, 7.6, 18, 0.9, "**Algorithm: ClassifyTier** (rules can only escalate)", size=19)
    algo = [
        "t ← taxonomy[y].tier ;   R ← ∅",
        "if ≥ 2 bound devices lost within 300 s (or E-610), base online  →  R1",
        "if protocol mismatch and (OTA failed or no OTA path)  →  R2",
        "if t = L1 and the standard fix for y was performed and failed  →  R3",
        "if app device list ≠ base binding table  →  R4",
        "if customer: reset ∧ device next to base ∧ still failing  →  R5",
        "if R ≠ ∅ then t ← L2 ;   return t, R",
    ]
    box(s, 1.4, 8.6, 19.6, 8.6, "\n".join(f"{i + 1}:  {l}" for i, l in enumerate(algo)), fill=PALE,
        size=17, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, margin=0.5)
    accent_box(s, 21.8, 8.6, 10.6, 8.6,
               "**Why this design?**\n\n"
               "• Order = how an FAE debugs a master–slave system\n"
               "• Typed memory: no repeated questions, focused prompt\n"
               "• Every L2 ticket cites a policy rule → auditable\n"
               "• LLM does what rules cannot: read complaints, decide what to ask",
               size=16)
    notes(s, """
The planner encodes how an engineer debugs a master–slave system, so the LLM does not have to rediscover it each
session. The triage step takes the tier from the taxonomy and lets five policy rules raise it to L2: a batch loss,
a protocol mismatch after a failed OTA, a failed standard fix, an app/base binding mismatch, and a device that still
fails next to the base after a reset. Because rules can only escalate, every L2 ticket cites the clause and evidence.""")


def slide_data(prs, tpl, n):
    s = content(prs, tpl, "Data and Baselines", n)
    text(s, 1.4, 3.3, 14, 0.9, "**52 labelled support cases** (synthetic)", size=19)
    table(s, 1.4, 4.4, 14.4, [
        ["", "Core", "Challenge"],
        ["Cases", "40", "12"],
        ["Root-cause labels", "12", "11"],
        ["L1 / L2", "24 / 16", "6 / 6"],
        ["Easy / med. / hard", "5 / 22 / 13", "0 / 0 / 12"],
        ["Devices per home", "6.7", "6.3"],
        ["Log lines per case", "8.2", "5.5"],
    ], [1.7, 1, 1], size=15, row_h=0.95)
    bullets(s, 1.4, 11.3, 14.6, 6.4, [
        (0, "Distractors in every case"),
        (1, "wrong self-diagnosis, healthy devices, noisy logs"),
        (0, "Challenge set breaks shortcuts"),
        (1, "3 stale console readings · 9 misleading complaints"),
    ], size=17, space=4)

    text(s, 17.2, 3.3, 15, 0.9, "**Baselines** — each removes part of the design", size=19)
    table(s, 17.2, 4.4, 15.3, [
        ["System", "Console", "Dialogue", "Planner\n+ memory", "Rules", "LLM"],
        ["Vanilla LLM", "✗", "✗", "✗", "✗", "✓"],
        ["Vanilla RAG", "✗ (+KB)", "✗", "✗", "✗", "✓"],
        ["Rules only", "✓", "✗", "✓", "✓", "✗"],
        ["ReAct", "✓", "✓", "✗", "✗", "✓"],
        ["Ours", "✓", "✓", "✓", "✓", "✓"],
    ], [1.7, 1.2, 1.1, 1.6, 0.9, 0.8], size=14, row_h=0.95, red_rows=(5,))
    accent_box(s, 17.2, 10.6, 15.3, 3.3,
               "**+ 4 ablations:** no planner · no rule hints · no structured memory · no rule override\n"
               "**ReAct** has the same tools, budget (15 steps) and action judge as ours", size=16)
    text(s, 17.2, 14.4, 15.3, 3.0, "Metrics: root-cause & tier accuracy, escalation precision/recall, customer "
         "rounds, tokens, time, usability (LLM judge 1–5); Wilson CI, McNemar test, 3 repeated runs.",
         size=15, color=GREY)
    notes(s, """
There is no public dataset for this, so I built 52 labelled cases: 40 core cases and a 12-case challenge set.
Every case has distractors such as a wrong self-diagnosis in the complaint. The core set turned out to be solvable
by shortcuts, so each challenge case breaks one: three have stale console readings that only the customer can
correct, nine have misleading complaints. Each baseline removes one part of the design; ReAct has exactly the same
tools as my agent, so it isolates the planner, memory and rules.""")


def slide_results(prs, tpl, n):
    s = content(prs, tpl, "Results: Where Rules Fail", n)
    text(s, 1.4, 3.3, 31, 0.9, "Rules alone solve **46 / 52** → focus on the **6 cases they cannot solve** and on "
         "**pass³** (correct in all 3 runs)", size=18)
    picture(s, FIGURES / "hard_vs_easy.png", 1.6, 4.5, w=30.6)
    accent_box(s, 1.4, 14.6, 10.0, 3.2,
               "**Hard cases → LLM irreplaceable**\nrules [[0 / 6]]; every LLM system ≥ 4 / 6", size=15)
    accent_box(s, 11.85, 14.6, 10.0, 3.2,
               "**Stale console (C041, C050)**\nonly agents that ask the customer win:\nReAct 3 / 6 runs, ours [[5 / 6]]",
               size=15)
    accent_box(s, 22.3, 14.6, 10.1, 3.2,
               "**Easy cases → structure needed**\npass³: ReAct 41 / 46, ours [[46 / 46]]", size=15)
    notes(s, """
Overall accuracy is not the right lens here: rules alone, with no LLM, already solve 46 of the 52 cases. So I look
at the six cases the rules cannot solve, and at pass-three, whether a system is correct in all three runs.
On the hard cases rules score zero by construction, and every system with an LLM solves at least four of six:
the LLM is irreplaceable there. Four of these cases only need reading the complaint; the two stale-console cases
need asking the customer, and there only the tool-using agents succeed: ReAct in three of six runs, mine in five.
On the 46 easy cases the picture flips: ReAct is correct in all three runs on only 41, my agent on all 46.
The LLM is needed for the exceptions, and the deterministic structure is what makes it reliable on the routine.""")


def slide_example(prs, tpl, n):
    s = content(prs, tpl, "Example: Why Dialogue Matters (C041)", n)
    steps = [
        ("Complaint", "“Garage camera offline — signal must be weak. Can I buy a repeater?”"),
        ("Console", "RSSI −83 dBm\n→ looks like WEAK_SIGNAL"),
        ("Agent notices", "log: RSSI recorded 2 days ago at the old location → asks customer"),
        ("Customer", "LED dark after reset and re-plugging the adapter"),
    ]
    for i, (head, body) in enumerate(steps):
        x = 1.4 + i * 8.05
        box(s, x, 3.6, 6.9, 1.1, f"**{head}**", fill=RED if i == 2 else GREY, color=WHITE, size=17)
        box(s, x, 4.7, 6.9, 4.4, body, fill=PALE, size=16, anchor=MSO_ANCHOR.MIDDLE)
        if i < 3:
            arrow(s, x + 6.95, 6.4, x + 8.0, 6.4, color=RED, width=2.5)
    box(s, 1.4, 9.8, 31.1, 1.4, "Diagnosis: **HW_FAULT_SUSPECTED → escalate to FAE (L2)** — a weak signal "
        "would not make the LED go dark", fill=PINK, color=DARK, size=18)
    table(s, 1.4, 12.0, 31.1, [
        ["System", "Prediction", "Correct?", "Why"],
        ["Vanilla LLM", "WEAK_SIGNAL / L1", "✗", "follows the customer's self-diagnosis"],
        ["Rules only", "WEAK_SIGNAL / L1", "✗", "trusts the stale console reading"],
        ["ReAct", "HW_FAULT_SUSPECTED / L2", "✓", "asks the customer"],
        ["Ours", "HW_FAULT_SUSPECTED / L2", "✓", "asks the customer"],
    ], [1.3, 2.0, 0.8, 2.6], size=15, row_h=1.0, red_rows=(4,))
    notes(s, """
A challenge case. The customer is sure the signal is weak, and the console agrees: minus 83 dBm. Rules and the
complaint-only LLM answer weak signal, frontline. My agent sees in the log that this reading is two days old, asks
the customer, and learns the LED stays dark even after a reset and re-plugging, which a weak signal cannot explain.
It escalates a suspected hardware fault, which is correct.""")


def slide_ablation(prs, tpl, n):
    s = content(prs, tpl, "Ablations and Error Analysis", n)
    table(s, 1.4, 3.5, 18.6, [
        ["Variant", "Core cause / tier", "Unneeded / missed", "Tokens"],
        ["Full agent", "100% / 100%", "0 / 0", "17.2k"],
        ["– topology planner", "98% / 98%", "0 / 1", "28.6k"],
        ["– rule hints", "98% / 95%", "2 / 0", "20.4k"],
        ["– structured memory", "100% / 100%", "0 / 0", "18.0k"],
        ["– rule tier override", "100% / 100%", "0 / 0", "17.2k"],
    ], [1.9, 1.5, 1.4, 0.9], size=15, row_h=1.05, red_rows=(1,))
    bullets(s, 1.4, 10.2, 18.6, 7.6, [
        (0, "Planner → cost"),
        (1, "−40% tokens and LLM calls; challenge acc. 83% without it"),
        (0, "Rule hints → fewer unneeded escalations"),
        (0, "Memory / override → no accuracy change here"),
        (1, "override only rescued one tier in a repeated run (C050)"),
    ], size=17, space=4)
    accent_box(s, 21.0, 3.5, 11.4, 6.6,
               "**Failure we fixed — C045 (ghost binding)**\n"
               "Agent re-phrased search_kb 13× until its budget ran out.\n"
               "Fix: KB-search stop + hint order + missing KB section\n"
               "→ solved with 1 search, [[10k instead of 31k tokens]]", size=15)
    accent_box(s, 21.0, 10.5, 11.4, 6.3,
               "**Remaining weakness — C008 (repeat run)**\n"
               "Rule R3 trusts an LLM action judge.\n"
               "A misjudged customer reply caused one unneeded escalation.\n"
               "→ ask staff to confirm before escalating on R3 alone", size=15)
    notes(s, """
Removing one component at a time: the planner mainly saves cost, about 40 percent of the tokens. Rule hints prevent
unneeded escalations. Removing memory or the override does not change accuracy on these cases, which I report
honestly. One failure I found and fixed: in C045 the agent kept rephrasing knowledge-base searches until the budget
ran out; a search stop, better hint order and a missing KB section fixed it. The remaining weakness is rule R3,
which depends on an LLM judge.""")


def slide_conclusion(prs, tpl, n):
    s = content(prs, tpl, "Limitations and Takeaways", n)
    text(s, 1.4, 3.3, 15, 0.9, "**Limitations**", size=21, color=RED)
    bullets(s, 1.4, 4.2, 15.2, 12.5, [
        (0, "Synthetic data"),
        (1, "labels, rules and policy share one author → rules alone solve 46/52; 95% CI of a perfect run [91%, 100%]"),
        (0, "Usability judged by an LLM"),
        (1, "blind human rating sheet prepared"),
        (0, "Simulated customer"),
        (1, "real customers are vaguer"),
        (0, "Next step: real anonymised tickets"),
    ], size=18, space=4)
    text(s, 17.6, 3.3, 15, 0.9, "**Takeaways**", size=21, color=RED)
    accent_box(s, 17.6, 4.4, 14.8, 7.0,
               "**The LLM is irreplaceable on hard cases**\n"
               "rules solve 0 of the 6 cases they miss; only agents that ask the customer solve stale-console "
               "cases\n\n"
               "**Structure makes the LLM reliable**\n"
               "planner + rule hints: correct in [[every run]] on the 46 easy cases (ReAct 41)", size=16)
    accent_box(s, 17.6, 11.9, 14.8, 4.8,
               "Evaluate agents on the **cases rules cannot solve** and with **passᵏ**, not on average accuracy "
               "— on a rule-easy benchmark every system looks good.", size=16)
    notes(s, """
Limitations: the data is synthetic and the rules and labels share one author, so the perfect score should be read
with care; usability is judged by an LLM; the customer is simulated. Takeaway: for a narrow but structured domain,
encode the structure deterministically and let the LLM handle language and questions. That gave a more accurate and
clearly more stable agent than a general tool-use loop, at a moderate cost. In short: the LLM handles the
exceptions, the structure handles the routine.""")


def slide_thanks(prs, tpl):
    s = clone_slide(prs, tpl.slides[SECTION])
    title = next(sh for sh in s.shapes if sh.is_placeholder)
    set_paragraph(title.text_frame.paragraphs[0], "Thank You!  Questions?", size=60)
    text(s, 2.0, 11.6, 28, 1.2, "Code, data and full results: iot_agent/ · README.md · results/comparison.md",
         size=18, color=GREY)
    notes(s, "Thank you. I am happy to take questions.")


def slide_backup(prs, tpl, n):
    s = content(prs, tpl, "Backup: Overall Accuracy", n)
    table(s, 1.4, 3.5, 31.1, [
        ["System", "Root cause\ncore / challenge", "Tier\ncore / challenge", "Tokens / case\ncore / chall.",
         "McNemar p vs ours\ncore / challenge"],
        ["Vanilla LLM", "85% / 25%", "88% / 50%", "0.9k / 0.9k", "0.031 / 0.004"],
        ["Vanilla RAG", "85% / 33%", "88% / 58%", "1.3k / 1.2k", "0.031 / 0.008"],
        ["Rules only (no LLM)", "92% / 75%", "92% / 75%", "0 / 0", "0.250 / 0.250"],
        ["ReAct (3 runs)", "94.2 ± 1.4 / 91.7 ± 0.0", "96.7 ± 1.4 / 91.7 ± 0.0", "14.9k / 12.6k", "0.250 / 1.000"],
        ["Ours (3 runs)", "100.0 ± 0.0 / 97.2 ± 4.8", "99.2 ± 1.4 / 100.0 ± 0.0", "17.2k / 24.5k", "—"],
    ], [1.6, 2.0, 2.0, 1.4, 1.6], size=15, row_h=1.3, red_rows=(5,))
    text(s, 1.4, 11.6, 31, 5.5,
         "• Baselines: one run; tool-using agents: mean ± s.d. over 3 runs; McNemar on run 1\n"
         "• A perfect run is still uncertain: 95% Wilson CI [91%, 100%] (40 core), [76%, 100%] (12 challenge)\n"
         "• Usability (LLM judge, 1–5): ours 3.92 vs ReAct 3.05 (core)\n"
         "• Q: Why LangGraph, not openJiuwen? Runs locally; SQLite checkpoints pause the graph while staff relay a reply\n"
         "• Q: Cost? ~17k tokens and ~22 s model time per core case (thinking mode off)", size=16)
    notes(s, "Backup slide: overall accuracy, significance tests, platform choice and cost, for questions.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, default=HERE / "polyu_template.pptx")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    tpl = Presentation(str(a.template))
    prs = Presentation(str(a.template))       # same file: layouts, master and theme are kept
    n_template = len(prs.slides)
    tpl = prs                                  # clone from the slides of the same package

    cover(prs, tpl)
    builders = [slide_problem, slide_architecture, slide_method, slide_data, slide_results, slide_example,
                slide_ablation, slide_conclusion]
    for i, build in enumerate(builders, start=2):
        build(prs, tpl, i)
    slide_thanks(prs, tpl)
    slide_backup(prs, tpl, len(builders) + 3)
    drop_template_slides(prs, n_template)
    prs.save(str(a.out))
    print(f"[slides] {len(prs.slides)} slides -> {a.out}")


if __name__ == "__main__":
    main()
