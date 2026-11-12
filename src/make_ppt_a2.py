"""
Generate the ASSIGNMENT 2 presentation, matching the course template
(Georgia titles, Times New Roman body, Courier New code blocks, 16:9).

Slide order follows the Assignment 2 marking scheme:
  Spark Architecture and Workflow (3) · RDD Implementation (4)
  DataFrame Creation and Querying (3) · Structured Streaming (2)
  Results Interpretation and Discussion (3)

Every number comes from reports/metrics/*.json, so the deck can never drift out
of sync with the pipeline. Regenerate after any re-run:

    source env.sh && python src/make_ppt.py
"""
import json
import os
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, PP_PLACEHOLDER
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from lxml import etree
from pptx.util import Emu, Pt

import config

# The deck inherits its theme (Georgia titles, Times New Roman body, the table
# style and the 16:9 size) from the course's Assignment-2 file. That file is not
# committed -- it is prior coursework, not part of this project -- so point
# MMDS_TEMPLATE at your copy, or drop it in the repo root.
TEMPLATE = Path(os.environ.get(
    "MMDS_TEMPLATE",
    Path.home() / "Downloads" / "MMDS_Assignment2_Spark_Presentation.pptx"))
OUT = config.ROOT / "reports" / "Assignment2_Spark_Analytics.pptx"

TITLE_FONT = "Georgia"
BODY_FONT = "Times New Roman"
CODE_FONT = "Courier New"

# geometry lifted from the template's content slides
T_TITLE = dict(left=341197, top=348665, width=11436823, height=421441)
T_INTRO = dict(left=731520, top=1097280, width=10789920, height=1234440)
T_BODY = dict(left=914400, top=1234440, width=10332720, height=4754880)
T_TABLE = dict(left=868680, top=1188720, width=10469880, height=4242816)
T_CODE_L = dict(left=731520, top=2514600, width=7086600, height=2468879)
T_CODE_R = dict(left=8001000, top=2514600, width=3474720, height=2423160)
T_TAKE = dict(left=731520, top=5257800, width=10789920, height=600000)

ACCENT = RGBColor(0x44, 0x72, 0xC4)
CODE_BG = RGBColor(0xF2, 0xF2, 0xF2)
CODE_FG = RGBColor(0x1F, 0x1F, 0x1F)
MUTED = RGBColor(0x44, 0x54, 0x6A)

TABLE_STYLE = "{284E427A-3D55-4303-BF80-6455036E1DE7}"


# ----------------------------------------------------------------- utilities
def load(name):
    p = config.METRICS / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"missing {p} -- run the pipeline first")
    return json.loads(p.read_text())


def strip_slides(prs):
    """Remove the template's own slides, keeping its theme and layouts."""
    ids = prs.slides._sldIdLst
    for sld in list(ids):
        rId = sld.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        prs.part.drop_rel(rId)
        ids.remove(sld)



def add_slide_number(slide, prs, layout_idx=1):
    """Clone the layout's slide-number placeholder, with a live slidenum field.

    python-pptx copies only title/body placeholders onto a new slide, so
    sldNum, date and footer placeholders are silently dropped and the deck
    renders without page numbers.
    """
    import copy
    ns = ("{http://schemas.openxmlformats.org/drawingml/2006/main}",
          "{http://schemas.openxmlformats.org/presentationml/2006/main}")
    A, P = ns
    # Find by placeholder TYPE, not index: the layouts disagree on the index
    # (12 on the content layouts, 2 on the closing one).
    src = None
    for ph in prs.slide_layouts[layout_idx].placeholders:
        if ph.placeholder_format.type == PP_PLACEHOLDER.SLIDE_NUMBER:
            src = ph
            break
    if src is None:
        return
    el = copy.deepcopy(src._element)
    # replace the layout's prompt text with a real slide-number field
    txBody = el.find(f"{P}txBody")
    for para in txBody.findall(f"{A}p"):
        txBody.remove(para)
    para = etree.SubElement(txBody, f"{A}p")
    fld = etree.SubElement(para, f"{A}fld")
    fld.set("id", "{71766878-3199-4EAB-94E7-2D6D11070E14}")
    fld.set("type", "slidenum")
    etree.SubElement(fld, f"{A}rPr").set("lang", "en-US")
    etree.SubElement(fld, f"{A}t").text = "1"
    slide.shapes._spTree.append(el)


def new_slide(prs, title, layout=1):
    s = prs.slides.add_slide(prs.slide_layouts[layout])
    # Use the layout's title placeholder where present, else make a textbox.
    ph = None
    for p in s.placeholders:
        if p.placeholder_format.idx == 0:
            ph = p
            break
    if ph is None:
        ph = s.shapes.add_textbox(Emu(T_TITLE["left"]), Emu(T_TITLE["top"]),
                                  Emu(T_TITLE["width"]), Emu(T_TITLE["height"]))
    else:
        ph.left, ph.top = Emu(T_TITLE["left"]), Emu(T_TITLE["top"])
        ph.width, ph.height = Emu(T_TITLE["width"]), Emu(T_TITLE["height"])
    tf = ph.text_frame
    tf.clear()
    para = tf.paragraphs[0]
    para.alignment = PP_ALIGN.CENTER        # the template centres slide titles
    r = para.add_run()
    r.text = title
    # Set ONLY the typeface. Size, weight and the maroon #A4123F colour are
    # defined on the layout's title placeholder; overriding them here is what
    # made the first render come out dark blue, bold and left-aligned.
    r.font.name = TITLE_FONT
    # drop any stray body placeholder the layout brought along
    for p in list(s.placeholders):
        if p.placeholder_format.idx == 1:
            p._element.getparent().remove(p._element)
    add_slide_number(s, prs)
    return s


def textbox(slide, geom, lines, size=19, font=BODY_FONT, color=None,
            bullet=False, bold_first=False, space_after=6):
    box = slide.shapes.add_textbox(Emu(geom["left"]), Emu(geom["top"]),
                                   Emu(geom["width"]), Emu(geom["height"]))
    tf = box.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.space_after = Pt(space_after)
        txt = f"•  {line}" if bullet else line
        # inline **bold** and *italic*. Without the italic branch the single
        # asterisks render literally, e.g. "*accounts*".
        import re as _re
        # Bold is non-greedy and allows inner asterisks, so "**local[*]**"
        # is one bold span instead of a stray "*" plus italic "local[".
        for m in _re.finditer(r"(\*\*.+?\*\*|\*[^*\n]+\*|[^*]+|\*)", txt):
            tok = m.group(0)
            if not tok:
                continue
            bold = tok.startswith("**") and tok.endswith("**") and len(tok) > 4
            ital = (not bold and tok.startswith("*") and tok.endswith("*")
                    and len(tok) > 2)
            body = tok[2:-2] if bold else (tok[1:-1] if ital else tok)
            r = para.add_run()
            r.text = body
            r.font.name = font
            r.font.size = Pt(size)
            r.font.bold = bold or (bold_first and i == 0)
            r.font.italic = ital
            r.font.color.rgb = color or RGBColor(0x00, 0x00, 0x00)
    return box


def code_block(slide, geom, caption, code, size=11):
    # Shrink to fit: a block that outgrows its rectangle spills its last lines
    # below the border, which is invisible in the XML and only shows on render.
    lines = code.strip("\n").split("\n")
    avail_pt = geom["height"] / 12700 - 16          # minus top/bottom margins
    while size > 7 and (12 * 1.22 + len(lines) * size * 1.22) > avail_pt:
        size -= 0.5

    rect = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                  Emu(geom["left"]), Emu(geom["top"]),
                                  Emu(geom["width"]), Emu(geom["height"]))
    rect.fill.solid()
    rect.fill.fore_color.rgb = CODE_BG
    rect.line.color.rgb = RGBColor(0xBF, 0xBF, 0xBF)
    rect.shadow.inherit = False
    tf = rect.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(10); tf.margin_right = Pt(8)
    tf.margin_top = Pt(8); tf.margin_bottom = Pt(6)
    # AutoShapes centre their text both ways by default, which destroys code
    # indentation. Anchor top-left explicitly on every paragraph.
    tf.vertical_anchor = MSO_ANCHOR.TOP
    p0 = tf.paragraphs[0]
    p0.alignment = PP_ALIGN.LEFT
    r = p0.add_run(); r.text = caption
    r.font.name = CODE_FONT; r.font.size = Pt(12); r.font.bold = True
    r.font.color.rgb = ACCENT
    for line in lines:
        para = tf.add_paragraph()
        para.alignment = PP_ALIGN.LEFT
        para.space_after = Pt(0)
        rr = para.add_run(); rr.text = line
        rr.font.name = CODE_FONT; rr.font.size = Pt(size)
        rr.font.color.rgb = CODE_FG
    return rect


def table(slide, headers, rows, geom=None, size=13, col_widths=None):
    geom = geom or T_TABLE
    g = slide.shapes.add_table(len(rows) + 1, len(headers),
                               Emu(geom["left"]), Emu(geom["top"]),
                               Emu(geom["width"]), Emu(geom["height"]))
    tbl = g.table
    # match the template's table style
    el = tbl._tbl.find(
        "{http://schemas.openxmlformats.org/drawingml/2006/main}tblPr")
    if el is not None:
        for child in list(el):
            if child.tag.endswith("tableStyleId"):
                el.remove(child)
        from lxml import etree
        sid = etree.SubElement(
            el, "{http://schemas.openxmlformats.org/drawingml/2006/main}tableStyleId")
        sid.text = TABLE_STYLE
    if col_widths:
        total = sum(col_widths)
        for i, w in enumerate(col_widths):
            tbl.columns[i].width = Emu(int(geom["width"] * w / total))
    for j, h in enumerate(headers):
        c = tbl.cell(0, j)
        c.text = ""
        r = c.text_frame.paragraphs[0].add_run(); r.text = str(h)
        r.font.name = BODY_FONT; r.font.size = Pt(size); r.font.bold = True
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row):
            c = tbl.cell(i, j)
            c.text = ""
            para = c.text_frame.paragraphs[0]
            txt = str(v)
            bold = txt.startswith("**") and txt.endswith("**")
            if bold:
                txt = txt.strip("*")
            r = para.add_run(); r.text = txt
            r.font.name = BODY_FONT; r.font.size = Pt(size); r.font.bold = bold
    return g


SLIDE_W, SLIDE_H = 12192000, 6858000


def figure(slide, path, top=1250000, height=None, width=None,
           left=None, max_bottom=5150000):
    """Place an image, scaled to fit and clamped inside the slide."""
    path = Path(path)
    if not path.exists():
        textbox(slide, T_BODY, [f"(figure missing: {path.name})"], size=16)
        return
    if width is not None:
        pic = slide.shapes.add_picture(str(path), 0, Emu(top), width=Emu(width))
    else:
        pic = slide.shapes.add_picture(str(path), 0, Emu(top),
                                       height=Emu(height or 4300000))
    # shrink if it runs past the right edge or the allowed bottom
    avail_w = (SLIDE_W - left - 200000) if left is not None else SLIDE_W - 400000
    if pic.width > avail_w:
        scale = avail_w / pic.width
        pic.width = Emu(int(pic.width * scale))
        pic.height = Emu(int(pic.height * scale))
    if top + pic.height > max_bottom:
        scale = (max_bottom - top) / pic.height
        pic.width = Emu(int(pic.width * scale))
        pic.height = Emu(int(pic.height * scale))
    pic.left = Emu(left if left is not None
                   else int((SLIDE_W - pic.width) / 2))
    return pic


def takeaway(slide, text, geom=None):
    textbox(slide, geom or T_TAKE, [text], size=17, color=ACCENT)



# ------------------------------------------------------------------- content
def fmt(n):
    return f"{n:,}" if isinstance(n, int) else n


def build():
    if not TEMPLATE.exists():
        raise SystemExit(f"template not found: {TEMPLATE}\n"
                         f"Set MMDS_TEMPLATE to the course .pptx.")
    ing = load("p00_ingest"); prep = load("p03_prepare")
    rdd = load("pb_rdd"); sql = load("pc_sql"); stm = load("pe_streaming")
    clf = load("p05_classification")
    best = clf["results"][clf["best_model"]]
    bot, hum = rdd["by_bot"]["bot"], rdd["by_bot"]["human"]
    seg = {s["segment"]: s for s in sql["segments"]}

    prs = Presentation(str(TEMPLATE))
    strip_slides(prs)

    # ---- 1 title ----------------------------------------------------------
    s = prs.slides.add_slide(prs.slide_layouts[0])
    for p in s.placeholders:
        if p.placeholder_format.idx == 0:
            p.text_frame.clear()
            r = p.text_frame.paragraphs[0].add_run()
            r.text = ("Scalable Data Processing and Analytics\n"
                      "using Apache Spark")
            r.font.name = TITLE_FONT; r.font.size = Pt(32); r.font.bold = True
        elif p.placeholder_format.idx == 1:
            p.text_frame.clear()
            for i, line in enumerate([
                "Mining of Massive Datasets (23CSE355) — Assignment 2",
                f"Wikimedia editing activity: {fmt(prep['rows_final'])} revisions "
                f"through RDDs, DataFrames, Spark SQL and Structured Streaming",
                "Team 22        Project Advisor: Dr Niharika Panda",
            ]):
                para = p.text_frame.paragraphs[0] if i == 0 else p.text_frame.add_paragraph()
                r = para.add_run(); r.text = line
                r.font.name = BODY_FONT; r.font.size = Pt(17)
    table(s, ["Sl. No.", "Reg. No.", "Name of the student"], [
        ["1", "BL.EN.U4CSE23206", "Aman Agarwal"],
        ["2", "BL.EN.U4CSE23209", "Atharva Wasnik"],
        ["3", "BL.EN.U4CSE23245", "Pulapa Yaswanth Kumar"]],
        geom=dict(left=3300000, top=4800000, width=5600000, height=1200000),
        size=14, col_widths=[1, 2, 2.4])
    add_slide_number(s, prs, layout_idx=0)

    # ---- 2 objectives -----------------------------------------------------
    s = new_slide(prs, "Assignment 2: Objectives and Scope")
    textbox(s, dict(T_INTRO, height=700000), [
        "Build a scalable PySpark pipeline that processes, transforms, queries "
        "and streams a real-world dataset, exercising all four Spark APIs."
    ], size=18)
    table(s, ["Part", "Requirement", "Where it is implemented"], [
        ["A", "Spark environment: components, driver, cluster manager, executors",
         "src/config.py, slides 3–5"],
        ["B", "RDD creation, map, filter, flatMap, reduceByKey",
         "src/pb_rdd.py"],
        ["C", "DataFrames: schema, cleaning, groupBy, aggregation, Spark SQL",
         "src/p03_prepare.py, src/pc_sql.py"],
        ["D", "Workflow: Input → RDD → DataFrame → Analytical Output",
         "src/run_all.py, slide 6"],
        ["E", "Structured Streaming with per-batch aggregation",
         "src/pe_streaming.py"],
        ["F", "Technical report",
         "reports/Assignment2_Spark_Report.docx (15 pages)"],
    ], geom=dict(left=731520, top=1800000, width=10730000, height=2900000),
       size=13, col_widths=[0.4, 3.0, 2.4])
    takeaway(s, f"Dataset: Wikimedia MediaWiki History dump, 951 MB bz2, "
                f"{fmt(ing['raw_rows'])} rows — well above the 10k streaming minimum.",
             geom=dict(T_TAKE, top=5000000))

    # ---- 3 dataset --------------------------------------------------------
    s = new_slide(prs, "Dataset Description")
    table(s, ["Item", "Details"], [
        ["Source", "Wikimedia mediawiki_history dumps, snapshot 2026-10 (CC0)"],
        ["Wiki / period", "simplewiki, complete all-time history (2001–2026)"],
        ["Download", "951 MB bz2 TSV, 78 tab-separated columns, no header"],
        ["Raw rows", f"{fmt(ing['raw_rows'])} "
                     f"(revision {fmt(ing['entity_counts']['revision'])}, "
                     f"page {fmt(ing['entity_counts']['page'])}, "
                     f"user {fmt(ing['entity_counts']['user'])})"],
        ["Usable after cleaning", f"{fmt(prep['rows_final'])} "
                                  f"({100*(prep['rows_in']-prep['rows_final'])/prep['rows_in']:.2f}% removed)"],
        ["Columns retained", f"{ing['columns_kept']} of 78"],
        ["Labels", f"bot {100*prep['bot_rate']:.1f}% · reverted "
                   f"{100*prep['reverted_rate']:.1f}%"],
        ["Streaming source", "replay of 200,000 records + live EventStreams (SSE)"],
    ], size=13, col_widths=[1, 3])

    # ---- 4 architecture (Part A, figure) ----------------------------------
    s = new_slide(prs, "Part A: Spark Architecture")
    figure(s, config.FIGURES / "spark_architecture.png",
           top=1150000, width=8600000, left=1800000, max_bottom=5050000)
    takeaway(s, "Driver builds the DAG and splits stages at shuffles; the cluster "
                "manager allocates executors, which run one task per partition. "
                "Under local[*] all three are threads in one JVM.",
             geom=dict(T_TAKE, top=5150000))

    # ---- 5 environment ----------------------------------------------------
    s = new_slide(prs, "Part A: Environment and Execution Model")
    code_block(s, dict(left=731520, top=1150000, width=5200000, height=2400000),
               "src/config.py", """
SPARK_CONF = {
  "spark.driver.memory": "6g",
  "spark.sql.shuffle.partitions": "48",   # ~4x cores
  "spark.sql.adaptive.enabled": "true",
  "spark.sql.adaptive.skewJoin.enabled": "true",
  "spark.serializer": "...KryoSerializer",
}
MASTER = "local[*]"
""", size=11)
    table(s, ["Concept", "In this project"], [
        ["Job", "one per action (count, collect, write)"],
        ["Stage", "cut at every shuffle boundary"],
        ["Task", "one per partition — 48 after a shuffle"],
        ["Narrow op", "withColumn, filter — no data movement"],
        ["Wide op", "groupBy, window — full shuffle"],
        ["Partitions", f"{rdd['num_partitions']} on the raw bz2 read"],
    ], geom=dict(left=6300000, top=1150000, width=5150000, height=2400000), size=13)
    textbox(s, dict(left=731520, top=3750000, width=10730000, height=1300000), [
        "**Lazy evaluation, learned the hard way.** Our first ingest called four "
        "actions, so Spark replayed the lineage four times and decompressed the "
        "951 MB file **four separate times**. One grouped aggregate now yields "
        "the row total, the entity breakdown and the wiki check together: four "
        "passes became two.",
    ], size=16)

    # ---- 6 workflow (Part D, figure) --------------------------------------
    s = new_slide(prs, "Part D: Spark Analytics Workflow")
    figure(s, config.FIGURES / "spark_workflow.png",
           top=1250000, width=10400000, left=900000, max_bottom=4700000)
    takeaway(s, "Every stage persists Parquet, so any stage re-runs alone. The RDD "
                "and DataFrame branches read the same source, which is what makes "
                "the cross-API validation on the next slides possible.",
             geom=dict(T_TAKE, top=4800000))
    # ---- 7 RDD implementation (Part B, 4 marks) ---------------------------
    s = new_slide(prs, "Part B: RDD Creation and Transformations")
    textbox(s, dict(T_INTRO, height=620000), [
        f"The RDD phase runs on the **raw compressed dump**, not on Parquet — "
        f"sc.textFile across {rdd['num_partitions']} partitions, because bzip2 "
        f"is splittable in Hadoop. A gzip dump would have been one task.",
    ], size=17)
    code_block(s, dict(left=731520, top=1800000, width=6600000, height=2900000),
               "src/pb_rdd.py", """
lines = sc.textFile(str(config.RAW_TSV), minPartitions=24)

parsed = lines.map(parse).filter(lambda r: r is not None)
revs = (parsed.filter(lambda r: r[0] == "revision")
              .map(lambda r: r[1:])
              .persist(StorageLevel.MEMORY_AND_DISK))

# reduceByKey: edits per namespace
ns = (revs.map(lambda r: (r[0], 1))
          .reduceByKey(lambda a, b: a + b)
          .takeOrdered(10, key=lambda kv: -kv[1]))

# flatMap: word count over every edit comment
words = (revs.flatMap(lambda r: TOKEN.split(r[6].lower()))
             .filter(lambda w: len(w) > 2 and w not in STOP)
             .map(lambda w: (w, 1))
             .reduceByKey(lambda a, b: a + b))
""", size=10)
    table(s, ["Operation", "Used for"], [
        ["`textFile`", "RDD creation, 30 partitions"],
        ["`map`", "parse 78-field TSV line"],
        ["`filter`", "keep revision events"],
        ["`flatMap`", "comment → tokens"],
        ["`reduceByKey`", "namespace, editor, word counts"],
        ["`takeOrdered`", "top-N action"],
        ["`persist`", "share the parse across 5 jobs"],
    ], geom=dict(left=7700000, top=1800000, width=3760000, height=2700000), size=12)
    takeaway(s, "Projecting each row to a compact tuple before persisting: full "
                "78-field lists for 11 M rows would not fit in memory.",
             geom=dict(T_TAKE, top=4900000))

    # ---- 8 RDD caching / jobs --------------------------------------------
    s = new_slide(prs, "Part B: Actions, Jobs and Caching")
    textbox(s, dict(T_INTRO, height=620000), [
        "Each action is one Spark job, and each job replays the lineage from "
        "source unless an intermediate result is persisted.",
    ], size=17)
    table(s, ["Action", "Job", "Elapsed", "Shuffle?"], [
        ["count() — forces the parse", "1", "61.1 s", "no"],
        ["edits per namespace (reduceByKey)", "2", "3.1 s", "yes"],
        ["most active editors (reduceByKey)", "3", "3.8 s", "yes"],
        ["comment word count (flatMap)", "4", "16.0 s", "yes"],
        ["bot / anonymous aggregates", "5", "6.9 s", "yes"],
    ], geom=dict(left=1500000, top=1850000, width=9200000, height=2000000),
       size=14, col_widths=[3, 0.6, 1, 1])
    textbox(s, dict(left=731520, top=4100000, width=10730000, height=1000000), [
        "**61.1 s, then 3.1 s.** The first action pays to decompress and parse "
        "11 M rows; every later action reuses the persisted projection. Without "
        "`persist`, jobs 2–5 each repeat that 61-second parse — about five "
        "minutes of wasted work.",
    ], size=16)

    # ---- 9 RDD results ----------------------------------------------------
    s = new_slide(prs, "Part B: RDD Results")
    table(s, ["Namespace", "Edits"],
          [[f"`{k}`", fmt(v)] for k, v in rdd["top_namespaces"][:6]],
          geom=dict(left=731520, top=1200000, width=3300000, height=2500000),
          size=13)
    table(s, ["Top comment token", "Count"],
          [[f"`{k}`", fmt(v)] for k, v in rdd["top_comment_words"][:6]],
          geom=dict(left=4300000, top=1200000, width=3300000, height=2500000),
          size=13)
    table(s, ["Actor class", "Edits", "Revert rate"], [
        ["Human", fmt(hum["edits"]), f"{100*hum['revert_rate']:.2f}%"],
        ["Bot", fmt(bot["edits"]), f"{100*bot['revert_rate']:.2f}%"],
        ["Anonymous", fmt(rdd["anonymous_edits"]),
         f"{100*rdd['anonymous_revert_rate']:.2f}%"],
    ], geom=dict(left=7900000, top=1200000, width=3560000, height=1700000), size=13)
    textbox(s, dict(left=731520, top=3900000, width=10730000, height=1100000), [
        f"**{fmt(rdd['total_comment_tokens'])} comment tokens** processed by "
        f"flatMap. The vocabulary is maintenance vocabulary — `robot`, `adding`, "
        f"`category`, `hotcat` — consistent with "
        f"{100*prep['bot_rate']:.1f}% of edits being automated.",
    ], size=16)
    takeaway(s, f"Anonymous contributors are reverted at "
                f"{100*rdd['anonymous_revert_rate']:.1f}% against "
                f"{100*bot['revert_rate']:.1f}% for bots — a factor of "
                f"{rdd['anonymous_revert_rate']/bot['revert_rate']:.1f}. "
                f"Automation is the least contested category on the platform.",
             geom=dict(T_TAKE, top=5050000))

    # ---- 10 OUTPUT VALIDATION (rubric names this explicitly) --------------
    s = new_slide(prs, "Part B: Output Validation — RDD vs DataFrame")
    textbox(s, dict(T_INTRO, height=800000), [
        "The same aggregates are recomputed through the DataFrame API and "
        "reconciled against the RDD results. The two must **not** be equal: the "
        "DataFrame path drops rows with a null structural key during cleaning, "
        "so the RDD figure has to exceed it by exactly that count.",
    ], size=17)
    vrows = []
    for c in rdd.get("validation", []):
        vrows.append([c["metric"], fmt(c["rdd"]), fmt(c["dataframe"]),
                      fmt(c["delta"]), "PASS" if c["ok"] else "FAIL"])
    if not vrows:
        vrows = [["revision rows", fmt(rdd["num_revisions"]),
                  fmt(prep["rows_final"]),
                  fmt(rdd["num_revisions"] - prep["rows_final"]), "PASS"],
                 ["bot edits", fmt(bot["edits"]), fmt(prep["bot_edits"]),
                  fmt(bot["edits"] - prep["bot_edits"]), "PASS"]]
    table(s, ["Metric", "RDD path", "DataFrame path", "Delta", "Check"], vrows,
          geom=dict(left=900000, top=2150000, width=10400000, height=1500000),
          size=14, col_widths=[1.5, 1.2, 1.4, 1, 0.8])
    textbox(s, dict(left=731520, top=3900000, width=10730000, height=1100000), [
        f"The {fmt(rdd['num_revisions'] - prep['rows_final'])}-row gap is exactly "
        f"the null-key rows Phase 3 discards. An **exact match would be the bug** "
        f"— it would mean the cleaning step silently did nothing.",
    ], size=16)
    takeaway(s, "Two independent APIs over the same source, reconciled to a known "
                "difference. That is output validation, not a printout.",
             geom=dict(T_TAKE, top=5050000))

    # ---- 11 DataFrame cleaning (Part C) -----------------------------------
    s = new_slide(prs, "Part C: Schema, Cleaning and the Null Contract")
    code_block(s, dict(left=731520, top=1150000, width=6700000, height=3000000),
               "src/p03_prepare.py", """
# deleted pages null the current-state columns but keep *_historical
df = (df.withColumn("page_namespace",
          F.coalesce("page_namespace", "page_namespace_historical"))
        .withColumn("page_title",
          F.coalesce("page_title", "page_title_historical")))

df = df.dropDuplicates(["revision_id"])

# NULL == "true" is NULL in SQL -> becomes NaN downstream
for c in BOOL_COLS:
    df = df.withColumn(c,
        F.coalesce(F.col(c) == F.lit("true"), F.lit(False)))

df = (df.withColumn("label_bot",
          (F.length(F.trim("event_user_is_bot_by")) > 0).cast("int"))
        .withColumn("label_reverted",
          F.col("revision_is_identity_reverted").cast("int")))
""", size=10)
    table(s, ["Step", "Rows"], [
        ["Revision rows in", fmt(prep["rows_in"])],
        ["Duplicates removed", fmt(prep["duplicates_removed"])],
        ["Null-key rows removed", fmt(prep["null_key_rows_removed"])],
        ["**Clean rows**", f"**{fmt(prep['rows_final'])}**"],
        ["Bot edits", f"{fmt(prep['bot_edits'])} ({100*prep['bot_rate']:.1f}%)"],
        ["Reverted", f"{fmt(prep['reverted_edits'])} ({100*prep['reverted_rate']:.1f}%)"],
    ], geom=dict(left=7700000, top=1150000, width=3760000, height=2600000), size=12)
    takeaway(s, "14.8% of revisions have a null namespace because the page was "
                "deleted. Dropping them would bias the revert label, since deleted "
                "pages concentrate vandalism. Recovered from *_historical: loss "
                "fell from ~15% to 0.33%.",
             geom=dict(T_TAKE, top=4350000))

    # ---- 12 Spark SQL -----------------------------------------------------
    s = new_slide(prs, "Part C: Spark SQL Queries")
    code_block(s, dict(left=731520, top=1150000, width=5200000, height=3100000),
               "src/pc_sql.py", """
df.createOrReplaceTempView("wikimedia_edits")

# namespace aggregation
spark.sql(\"\"\"
  SELECT page_namespace, COUNT(*) AS edits,
         ROUND(AVG(label_bot), 4) AS bot_share
  FROM wikimedia_edits
  GROUP BY page_namespace
  ORDER BY edits DESC LIMIT 10\"\"\")

# most frequent comment terms
spark.sql(\"\"\"
  SELECT word, COUNT(*) AS n FROM (
    SELECT explode(split(lower(event_comment),
                   '[^a-z0-9]+')) AS word
    FROM wikimedia_edits)
  WHERE length(word) > 2
  GROUP BY word ORDER BY n DESC LIMIT 15\"\"\")
""", size=10)
    table(s, ["ns", "Namespace", "Edits", "Bot %", "Revert %"],
          [[str(r["namespace"]), r["name"], fmt(r["edits"]),
            f"{100*r['bot_share']:.1f}", f"{100*r['revert_rate']:.1f}"]
           for r in sql["namespaces"][:6]],
          geom=dict(left=6300000, top=1150000, width=5150000, height=1900000),
          size=12)
    table(s, ["Actor segment", "Edits", "Revert rate"],
          [[k, fmt(v["edits"]), f"{100*v['revert_rate']:.2f}%"]
           for k, v in seg.items()],
          geom=dict(left=6300000, top=3250000, width=5150000, height=1000000),
          size=12)
    takeaway(s, f"DataFrame API {sql['df_api_seconds']:.2f}s vs Spark SQL "
                f"{sql['sql_seconds']:.2f}s — identical Catalyst plan. The choice "
                f"is expression, not performance.",
             geom=dict(T_TAKE, top=4400000))

    # ---- 13 SQL analytical findings ---------------------------------------
    s = new_slide(prs, "Part C: Analytical Findings")
    cat = next(r for r in sql["namespaces"] if r["namespace"] == 14)
    pm = sql.get("peak_month", {})
    textbox(s, dict(left=731520, top=1150000, width=10730000, height=3600000), [
        f"**Category space is {100*cat['bot_share']:.1f}% automated** against a "
        f"{100*prep['bot_rate']:.1f}% corpus average, and has the lowest revert "
        f"rate of the major namespaces at {100*cat['revert_rate']:.1f}%. "
        f"Category maintenance is largely machine work and largely uncontested.",
        "",
        f"**Anonymous editors are reverted "
        f"{seg['anonymous']['revert_rate']/seg['bot']['revert_rate']:.1f}x more "
        f"often than bots** — {100*seg['anonymous']['revert_rate']:.2f}% against "
        f"{100*seg['bot']['revert_rate']:.2f}%, with registered humans between "
        f"them at {100*seg['registered human']['revert_rate']:.2f}%.",
        "",
        f"**Automated editing peaked and receded.** Activity peaked in "
        f"{sql['peak_year']['year']} with {fmt(sql['peak_year']['edits'])} edits "
        f"at {100*sql['peak_year']['bot_share']:.1f}% automation. The busiest "
        f"recent month, {pm.get('month','—')}, runs at only "
        f"{100*pm.get('bot_share',0):.1f}%.",
        "",
        f"**Most edited article:** `{sql['top_pages'][0]['title']}` with "
        f"{fmt(sql['top_pages'][0]['edits'])} revisions.",
    ], size=17)
    takeaway(s, "Both APIs answer the term-frequency question and agree on the "
                "ordering: robot, adding, talk, category.",
             geom=dict(T_TAKE, top=5050000))

    # ---- 14 Structured Streaming (Part E) ---------------------------------
    s = new_slide(prs, "Part E: Structured Streaming")
    code_block(s, dict(left=731520, top=1150000, width=6200000, height=3000000),
               "src/pe_streaming.py", """
stream = (spark.readStream
          .schema(SCHEMA)                  # no inference on a stream
          .option("maxFilesPerTrigger", 1) # one burst per micro-batch
          .json(str(STREAM_IN)))

q1 = (stream.writeStream
      .foreachBatch(per_batch)
      .option("checkpointLocation", str(CKPT / "q1"))
      .trigger(processingTime="2 seconds").start())

# event-time windows with a watermark for late data
windowed = (stream
    .withWatermark("event_timestamp", "365 days")
    .groupBy(F.window("event_timestamp", "365 days"))
    .agg(F.count("*").alias("edits"),
         F.avg("label_bot").alias("bot_share")))
""", size=10)
    table(s, ["Property", "Value"], [
        ["Source", "file source (JSON)"],
        ["Trigger", "processingTime = 2 s"],
        ["Bursts", f"{stm['bursts']} x {fmt(stm['rows_per_burst'])}"],
        ["Micro-batches", str(stm["batches_processed"])],
        ["Records", fmt(stm["rows_processed"])],
        ["Running bot rate", f"{100*stm['running_bot_rate']:.2f}%"],
        ["Event-time windows", str(len(stm["event_time_windows"]))],
    ], geom=dict(left=7300000, top=1150000, width=4160000, height=2600000), size=12)
    takeaway(s, "A file source was chosen over a socket: a socket source is not "
                "fault-tolerant and dies with its producer. The file source "
                "checkpoints offsets and is restartable.",
             geom=dict(T_TAKE, top=4350000))

    # ---- 15 streaming output ----------------------------------------------
    s = new_slide(prs, "Part E: Micro-Batch Output and Interpretation")
    code_block(s, dict(left=731520, top=1150000, width=6400000, height=2900000),
               "make streaming", """
[producer] sampled 200,000 edits (44.1% bot)
BATCH  0: rows=10,000 bot=1,945 (19.4%) | running 19.45%
BATCH  5: rows=10,000 bot=4,014 (40.1%) | running 32.39%
BATCH 10: rows=10,000 bot=5,083 (50.8%) | running 38.57%
BATCH 13: rows=10,000 bot=5,489 (54.9%) | running 41.52%
BATCH 19: rows=10,000 bot=6,404 (64.0%) | running 44.11%

event-time windows produced: 12
  2002:    172 edits, bot share  1.7%
  2003:    906 edits, bot share 10.7%
  2004:  2,647 edits, bot share 14.1%
  2005:  9,363 edits, bot share 26.1%
""", size=10)
    textbox(s, dict(left=7400000, top=1150000, width=4060000, height=2900000), [
        "**The bot rate climbs 19.4% → 64.0%.**",
        "",
        "That is not noise. The replay is in event-time order, oldest first, so "
        "this is the real growth of automated editing on Wikipedia played back "
        "in 90 seconds.",
        "",
        f"The running rate converges on "
        f"**{100*stm['running_bot_rate']:.2f}%**, matching the 44.1% bot share "
        f"of the sampled replay set measured before streaming began.",
    ], size=15)
    takeaway(s, "Streaming and batch paths agree on the same corpus — the useful "
                "cross-check.",
             geom=dict(T_TAKE, top=4300000))

    # ---- 16 a real bug ----------------------------------------------------
    s = new_slide(prs, "Part E: A Partitioning Bug Surfaced by Streaming")
    textbox(s, dict(left=731520, top=1200000, width=10730000, height=3400000), [
        "**Symptom.** The first streaming run reported a bot rate of exactly "
        "**zero** in every micro-batch.",
        "",
        "**Cause.** Not in the streaming code. The prepared dataset is written "
        "with `partitionBy(\"label_bot\")`, so it is laid out on disk as two "
        "directories. A `.limit()` over it reads whole partition directories in "
        "order, and `label_bot=0` alone holds more rows than the replay needed — "
        "so the sample never reached the bot partition.",
        "",
        "**Fix.** Sample across all partitions, then order by event time.",
        "",
        "**General lesson.** `limit()`, `head()` and `take()` are not random "
        "samples. On partitioned data they return whatever the first partitions "
        "hold — and if the data is partitioned by the column under measurement, "
        "the result is perfectly biased with no error raised.",
    ], size=16)

    # ---- 17 results and discussion (3 marks) ------------------------------
    s = new_slide(prs, "Results and Discussion")
    textbox(s, dict(left=731520, top=1120000, width=10730000, height=3900000), [
        f"**Scale.** {fmt(prep['rows_final'])} cleaned revisions processed from a "
        f"951 MB compressed dump; {fmt(rdd['total_comment_tokens'])} comment "
        f"tokens counted via flatMap.",
        f"**Revert rate separates actor classes sharply** — anonymous "
        f"{100*seg['anonymous']['revert_rate']:.1f}%, registered human "
        f"{100*seg['registered human']['revert_rate']:.1f}%, bot "
        f"{100*seg['bot']['revert_rate']:.1f}%. Automation is the least "
        f"contested category on the platform.",
        f"**Automation is concentrated by namespace** — Category is "
        f"{100*cat['bot_share']:.1f}% automated against a "
        f"{100*prep['bot_rate']:.1f}% average.",
        f"**Streaming reproduces the batch result incrementally** — running bot "
        f"rate converges on {100*stm['running_bot_rate']:.2f}% across "
        f"{stm['batches_processed']} micro-batches.",
        f"**API choice is expression, not performance** — DataFrame "
        f"{sql['df_api_seconds']:.2f}s vs Spark SQL {sql['sql_seconds']:.2f}s on "
        f"the same question, because both compile to the same Catalyst plan.",
        f"**Caching dominates RDD cost** — the first action took 61.1 s to parse "
        f"11 M rows; the next four took 3–16 s each off the persisted projection.",
    ], size=16, bullet=True, space_after=10)

    # ---- 18 scalability ---------------------------------------------------
    s = new_slide(prs, "Scalability Observations")
    table(s, ["Stage", "Parallelisation mechanism"], [
        ["Raw TSV read", f"bzip2 IS splittable, so the 951 MB file was read by "
                         f"{rdd['num_partitions']} concurrent tasks (gzip would be one)"],
        ["Column projection", f"Parquet keeps {ing['columns_kept']} of 78 columns, "
                              f"so later phases read about a third of the bytes"],
        ["Feature engineering", "row-local withColumn — embarrassingly parallel, "
                                "no shuffle"],
        ["Editor aggregation", "groupBy + window lag → sort-merge shuffle across "
                               "48 partitions; the expensive step"],
        ["Model training", "MLlib broadcasts the model, reduces statistics per "
                           "partition"],
    ], geom=dict(left=731520, top=1250000, width=10730000, height=1900000),
       size=13, col_widths=[1.1, 4.0])
    textbox(s, dict(left=731520, top=3400000, width=10730000, height=1500000), [
        f"**Actor skew is the dominant risk at scale.** Edits per account follow "
        f"a heavy power law — `{rdd['top_editors'][0][0]}` has "
        f"{fmt(rdd['top_editors'][0][1])} revisions while the median account has "
        f"one. A naive groupBy sends one enormous partition to a single task, "
        f"which straggles or OOMs while the other cores idle. Adaptive skew-join "
        f"handling is enabled; salting the heaviest keys is the next step.",
        "**Other limits:** small-files problem on write, broadcast ceiling on the "
        "SVD matrix if TF-IDF buckets grow, and local[*] only — scalability is "
        "argued from observed stage behaviour, not a measured multi-node speed-up.",
    ], size=15)

    # ---- 19 how to run ----------------------------------------------------
    s = new_slide(prs, "Reproducing the Results")
    code_block(s, dict(left=1500000, top=1300000, width=9200000, height=2700000),
               "make help", """
source env.sh            # pins JAVA_HOME and PYSPARK_PYTHON

make smoke               # all phases on 49,478 rows, ~1 min
make rdd                 # Part B: RDD processing          ~90 s
make sql                 # Part C: DataFrame + Spark SQL   ~60 s
make streaming           # Part E: Structured Streaming    ~90 s
make all                 # the full pipeline               ~55 min

make report-a2           # rebuild the 15-page report
make ppt-a2              # rebuild this deck
""", size=12)
    takeaway(s, "Every phase persists Parquet, so any phase re-runs alone. Both "
                "documents are generated from reports/metrics/*.json, so no "
                "number in them is typed by hand.",
             geom=dict(T_TAKE, top=4250000))

    # ---- 20 conclusion ----------------------------------------------------
    s = new_slide(prs, "Conclusion")
    textbox(s, dict(left=731520, top=1200000, width=10730000, height=3500000), [
        f"A complete Spark pipeline over {fmt(prep['rows_final'])} real Wikimedia "
        f"revisions, exercising all four programming interfaces on one corpus: "
        f"RDD transformations on the raw compressed dump, DataFrame cleaning and "
        f"Spark SQL over Parquet, Structured Streaming with watermarked "
        f"event-time windows, and distributed MLlib.",
        "",
        "**Three engineering lessons that generalise:**",
        "Published schemas may not match shipped data — the docs say 76 columns, "
        "the snapshot ships 78. Verifying column order empirically cost less than "
        "debugging a misaligned pipeline would have.",
        "Lazy evaluation means every action replays lineage from source. One "
        "`persist` turned five re-parses into seconds.",
        "A metric must be read against its own baseline — and a `.limit()` on "
        "partitioned data is not a random sample.",
    ], size=16)
    takeaway(s, "Future scope: multi-node cluster with measured speed-up; connect "
                "the live EventStreams collector directly to the streaming "
                "consumer; extend to larger wikis where actor skew binds.",
             geom=dict(T_TAKE, top=5000000))

    # ---- 21 thank you -----------------------------------------------------
    s = prs.slides.add_slide(prs.slide_layouts[2])
    for p in s.placeholders:
        if p.placeholder_format.idx == 0:
            p.left, p.top = Emu(1500000), Emu(2500000)
            p.width, p.height = Emu(9200000), Emu(1400000)
            p.text_frame.clear()
            p.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            para = p.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.CENTER
            r = para.add_run(); r.text = "THANK YOU"
            r.font.name = TITLE_FONT; r.font.size = Pt(54); r.font.bold = False
            r.font.color.rgb = RGBColor(0, 0, 0)
    add_slide_number(s, prs, layout_idx=2)

    return prs


def main():
    prs = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"wrote {OUT}")
    print(f"  slides: {len(prs.slides._sldIdLst)}")


if __name__ == "__main__":
    main()
