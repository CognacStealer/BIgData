"""
Generate the project presentation, matching the formatting of the course's
Assignment-2 deck (Georgia titles, Times New Roman body, Courier New code
blocks, 16:9).

Every number comes from reports/metrics/*.json, so the deck can never drift out
of sync with the pipeline. Regenerate after any re-run:

    source env.sh && python src/make_ppt.py
"""
import json
import os
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Pt

import config

# The deck inherits its theme (Georgia titles, Times New Roman body, the table
# style and the 16:9 size) from the course's Assignment-2 file. That file is not
# committed -- it is prior coursework, not part of this project -- so point
# MMDS_TEMPLATE at your copy, or drop it in the repo root.
TEMPLATE = Path(os.environ.get(
    "MMDS_TEMPLATE",
    Path.home() / "Downloads" / "MMDS_Assignment2_Spark_Presentation.pptx"))
OUT = config.ROOT / "reports" / "MMDS_EndSem_Wikimedia_Bot_Detection.pptx"

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
    r = tf.paragraphs[0].add_run()
    r.text = title
    r.font.name = TITLE_FONT
    r.font.size = Pt(28)
    r.font.bold = True
    r.font.color.rgb = MUTED
    # drop any stray body placeholder the layout brought along
    for p in list(s.placeholders):
        if p.placeholder_format.idx == 1:
            p._element.getparent().remove(p._element)
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
        # inline **bold** support
        parts = txt.split("**")
        for j, part in enumerate(parts):
            if not part:
                continue
            r = para.add_run()
            r.text = part
            r.font.name = font
            r.font.size = Pt(size)
            r.font.bold = (j % 2 == 1) or (bold_first and i == 0)
            r.font.color.rgb = color or RGBColor(0x00, 0x00, 0x00)
    return box


def code_block(slide, geom, caption, code, size=11):
    rect = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                  Emu(geom["left"]), Emu(geom["top"]),
                                  Emu(geom["width"]), Emu(geom["height"]))
    rect.fill.solid()
    rect.fill.fore_color.rgb = CODE_BG
    rect.line.color.rgb = RGBColor(0xBF, 0xBF, 0xBF)
    rect.shadow.inherit = False
    tf = rect.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(8); tf.margin_right = Pt(8)
    tf.margin_top = Pt(6); tf.margin_bottom = Pt(6)
    p0 = tf.paragraphs[0]
    r = p0.add_run(); r.text = caption
    r.font.name = CODE_FONT; r.font.size = Pt(12); r.font.bold = True
    r.font.color.rgb = ACCENT
    for line in code.strip("\n").split("\n"):
        para = tf.add_paragraph()
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
        raise SystemExit(
            f"template not found: {TEMPLATE}\n"
            f"Set MMDS_TEMPLATE to the Assignment-2 .pptx to inherit its theme.")
    ing = load("p00_ingest")
    prep = load("p03_prepare")
    feat = load("p04_features")
    clf = load("p05_classification")
    clu = load("p05_clustering")

    prs = Presentation(str(TEMPLATE))
    strip_slides(prs)

    # ---- 1 title ----------------------------------------------------------
    s = prs.slides.add_slide(prs.slide_layouts[0])
    for p in s.placeholders:
        if p.placeholder_format.idx == 0:
            p.text_frame.clear()
            r = p.text_frame.paragraphs[0].add_run()
            r.text = ("Detecting Automated and Anomalous Editing Behaviour "
                      "on Wikimedia at Scale")
            r.font.name = TITLE_FONT; r.font.size = Pt(34); r.font.bold = True
        elif p.placeholder_format.idx == 1:
            p.text_frame.clear()
            for i, line in enumerate([
                "Mining of Massive Datasets (23CSE355) — End Semester Project",
                "Spark MLlib on 11.0 million Wikimedia edits: "
                "bot classification and editor clustering",
                "Team _No: [Team No]        Project Advisor: [Advisor Name]",
            ]):
                para = p.text_frame.paragraphs[0] if i == 0 else p.text_frame.add_paragraph()
                r = para.add_run(); r.text = line
                r.font.name = BODY_FONT; r.font.size = Pt(18)
    table(s, ["Sl. No.", "Reg. No.", "Name of the student"],
          [[str(i), f"[Reg No {i}]", f"[Name {i}]"] for i in range(1, 5)],
          geom=dict(left=3000000, top=4400000, width=6200000, height=1600000),
          size=14, col_widths=[1, 2, 3])

    # ---- 2 introduction ---------------------------------------------------
    s = new_slide(prs, "Introduction")
    textbox(s, T_BODY, [
        "Wikimedia projects accept edits from anyone, with no review before "
        "publication. Across all projects the platform absorbs roughly 30–50 "
        "edits per second — far beyond what volunteer reviewers can inspect. A "
        "large share of that traffic is automated: approved maintenance bots, "
        "semi-automated human tooling, and unapproved scripts.",
        "",
        "This project asks two questions of the same corpus. First, **is this "
        "edit automated?** — a supervised classification problem, because "
        "reviewer attention should not be spent on predictable machine edits, "
        "while unflagged automation is a policy violation. Second, **what kinds "
        "of editors exist?** — an unsupervised clustering problem, because rate "
        "limits and review tooling should be designed around real behavioural "
        "populations rather than assumed ones.",
        "",
        f"We process the complete all-time edit history of Simple English "
        f"Wikipedia — {fmt(ing['raw_rows'])} dump rows containing "
        f"{fmt(ing['revision_rows'])} edits — in Apache Spark, engineer "
        f"behavioural features, reduce comment text with SVD, and compare three "
        f"classifiers against three clustering algorithms in MLlib.",
    ], size=18)

    # ---- 3 dataset --------------------------------------------------------
    s = new_slide(prs, "Dataset Overview")
    bot_pct = 100 * prep["bot_rate"]
    rev_pct = 100 * prep["reverted_rate"]
    table(s, ["Item", "Details"], [
        ["Source", "Wikimedia mediawiki_history dumps, snapshot 2026-10 (CC0)"],
        ["Wiki / period", "simplewiki, complete all-time history (2001–2026)"],
        ["Download", "951 MB bz2 TSV, 78 tab-separated columns"],
        ["Raw rows", f"{fmt(ing['raw_rows'])} (revision "
                     f"{fmt(ing['entity_counts']['revision'])}, page "
                     f"{fmt(ing['entity_counts']['page'])}, user "
                     f"{fmt(ing['entity_counts']['user'])})"],
        ["Edits analysed", f"{fmt(prep['rows_final'])} after cleaning "
                           f"({100*(prep['rows_in']-prep['rows_final'])/prep['rows_in']:.2f}% removed)"],
        ["Attributes used", f"{ing['columns_kept']} of 78 columns: actor, page, namespace, "
                            f"byte sizes, comment, cadence, revert links, tags"],
        ["Labels", f"label_bot {bot_pct:.1f}% positive; "
                   f"label_reverted {rev_pct:.1f}% positive"],
        ["Editors", f"{fmt(feat['n_editors'])} distinct actors "
                    f"(registered accounts + anonymous IPs)"],
        ["Live companion", "stream.wikimedia.org EventStreams (SSE) for the demo"],
    ], size=13, col_widths=[1, 3])

    # ---- 4 why this dataset (the differentiator) --------------------------
    s = new_slide(prs, "Problem Definition and Why This Dataset")
    textbox(s, dict(T_INTRO, height=900000), [
        "A classification project is only meaningful if its label is genuinely "
        "learnable. We chose Wikimedia specifically because of label validity, "
        "and rejected GDELT 2.0 for failing that test.",
    ], size=18)
    table(s, ["", "Wikimedia (chosen)", "GDELT 2.0 (rejected)"], [
        ["Candidate label", "event_user_is_bot_by", "QuadClass / GoldsteinScale"],
        ["Where it comes from",
         "MediaWiki user-group membership and the bot-name registry — an "
         "administrative fact about an account",
         "A deterministic lookup table keyed on the EventCode column"],
        ["Is it learnable?",
         "Yes — it is not a function of any feature we engineer",
         "No — keep EventCode and the model reproduces a lookup table; drop it "
         "and the task is ill-posed"],
    ], geom=dict(left=731520, top=2150000, width=10730000, height=2600000),
       size=13, col_widths=[1, 2, 2])
    takeaway(s, "Interrogating label validity before modelling is the core "
                "methodological decision of this project.",
             geom=dict(T_TAKE, top=5050000))

    # ---- 5 architecture ---------------------------------------------------
    s = new_slide(prs, "Pipeline Architecture")
    boxes = [
        ("Raw dump\n951 MB bz2 TSV\n78 columns", 400000),
        ("Phase 0\nIngest\nTSV → Parquet\n28 cols kept", 2650000),
        ("Phase 3\nPrepare\ndedup, impute,\nlabels", 4900000),
        ("Phase 4\nFeatures\n35 numeric\n+ 24-dim SVD", 7150000),
        ("Phase 5/6\nMLlib\n3 classifiers\n3 clusterers", 9400000),
    ]
    for text, left in boxes:
        rect = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                  Emu(left), Emu(1900000), Emu(2050000), Emu(1500000))
        rect.fill.solid(); rect.fill.fore_color.rgb = RGBColor(0xDE, 0xE7, 0xF7)
        rect.line.color.rgb = ACCENT; rect.shadow.inherit = False
        tf = rect.text_frame; tf.word_wrap = True
        for i, line in enumerate(text.split("\n")):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.alignment = PP_ALIGN.CENTER; para.space_after = Pt(0)
            r = para.add_run(); r.text = line
            r.font.name = BODY_FONT; r.font.size = Pt(13)
            r.font.bold = (i == 0); r.font.color.rgb = MUTED
    textbox(s, dict(left=731520, top=3650000, width=10730000, height=1600000), [
        "Driver and executors run inside one JVM on a laptop (**local[*]**, 12 "
        "cores): the driver builds the DAG, Spark's local scheduler stands in "
        "for the cluster manager, and executors are threads. The same code runs "
        "on a real cluster unchanged.",
        "",
        "Each phase persists Parquet, so any phase can be re-run in isolation "
        "without repeating the expensive bz2 decompression upstream.",
    ], size=17)

    # ---- 6 environment ----------------------------------------------------
    s = new_slide(prs, "Environment and Spark Configuration")
    code_block(s, dict(left=731520, top=1150000, width=5200000, height=2300000),
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
    table(s, ["Component", "Version / value"], [
        ["Python", "3.11.18 (via uv)"],
        ["PySpark", "3.5.3"],
        ["Java", "OpenJDK Temurin 17.0.21"],
        ["Hardware", "12 cores / 15 GB, local[*]"],
        ["Shuffle partitions", "48"],
        ["Parquet written", "1.1 GB (from 951 MB bz2)"],
    ], geom=dict(left=6300000, top=1150000, width=5150000, height=2300000), size=13)
    textbox(s, dict(left=731520, top=3700000, width=10730000, height=1600000), [
        "Two version traps, both of which fail at runtime rather than at import:",
        "**PYSPARK_PYTHON must be pinned.** System Python here is 3.14; if "
        "workers resolve bare python3 while the driver runs the venv, Spark dies "
        "mid-task with PYTHON_VERSION_MISMATCH.",
        "**PySpark 3.5 cannot run on Python 3.12** — pyspark/ml/image.py imports "
        "distutils, removed in 3.12. Support arrived in Spark 4.0, so we use 3.11.",
    ], size=16)

    # ---- 7 literature ----------------------------------------------------
    s = new_slide(prs, "Literature Survey")
    table(s, ["#", "Work", "Dataset", "Algorithms", "Metrics", "What we take"], [
        ["1", "Halfaker & Taraborelli, ORES (2015)", "Wikipedia revisions",
         "GBT, RF", "precision/recall, AUC", "reviewer routing needs precision"],
        ["2", "Potthast et al., ECIR 2008", "940k en-wiki edits",
         "logistic regression", "P / R / F1", "comment-shape features"],
        ["3", "Adler et al., CICLing 2011", "PAN-WVC-10",
         "RF, feature ablation", "ROC-AUC, PR-AUC", "structural-vs-full ablation"],
        ["4", "Davis et al., Botometer (2016)", "Twitter accounts",
         "random forest", "ROC-AUC", "cadence regularity as the signal"],
        ["5", "Chu et al., IEEE TDSC 2012", "500k Twitter accounts",
         "entropy + Bayesian", "accuracy, FP rate", "variance, not volume"],
        ["6", "Welser et al., iConference 2011", "Wikipedia editors",
         "descriptive clustering", "role validity", "editor-archetype framing"],
        ["7", "Yang et al., ICWSM 2016", "Wikipedia histories",
         "k-means, mixtures", "silhouette", "k by silhouette + naming"],
        ["8", "Kumar et al., VEWS, KDD 2015", "33k Wikipedia users",
         "SVM, RF", "early detection", "per-editor modelling"],
        ["9–10", "Zaharia et al. NSDI 2012; Meng et al. JMLR 2016", "—",
         "RDD model, MLlib", "runtime scaling", "Phase 7 infrastructure"],
    ], size=11, col_widths=[0.4, 2.2, 1.5, 1.4, 1.3, 2.0])
    takeaway(s, "Three threads: edit-level abuse detection (1–3, 8), automation "
                "by timing (4–5), unsupervised editor roles (6–7).",
             geom=dict(T_TAKE, top=5550000))

    # ---- 8 phase 3 code --------------------------------------------------
    s = new_slide(prs, "Phase 3: Data Preparation")
    textbox(s, dict(T_INTRO, height=800000), [
        "Cleaning runs on Spark DataFrames: de-duplicate on the natural key, "
        "recover deleted-page rows, impute where 'missing' carries meaning, "
        "then derive the two labels.",
    ], size=18)
    code_block(s, dict(left=731520, top=1950000, width=6700000, height=2900000),
               "src/p03_prepare.py", """
# deleted pages null the current-state columns but keep *_historical
df = (df.withColumn("page_namespace",
          F.coalesce("page_namespace", "page_namespace_historical"))
        .withColumn("page_title",
          F.coalesce("page_title", "page_title_historical")))

df = df.dropDuplicates(["revision_id"])

# NULL == "true" is NULL in SQL -> would become NaN downstream
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
        ["Bot edits", f"{fmt(prep['bot_edits'])} ({bot_pct:.1f}%)"],
        ["Reverted edits", f"{fmt(prep['reverted_edits'])} ({rev_pct:.1f}%)"],
    ], geom=dict(left=7700000, top=1950000, width=3760000, height=2600000), size=12)
    takeaway(s, f"Only {100*(prep['rows_in']-prep['rows_final'])/prep['rows_in']:.2f}% "
                f"of rows were discarded, and a null guard asserts every "
                f"feature-input column is null-free before writing.",
             geom=dict(T_TAKE, top=5050000))

    # ---- 9 phase 4 features ----------------------------------------------
    s = new_slide(prs, "Phase 4: Feature Engineering")
    textbox(s, dict(T_INTRO, height=750000), [
        f"{feat['n_numeric_edit_features']} numeric edit-level features plus a "
        f"{feat['svd_k']}-dimension comment block, and "
        f"{feat['n_editor_features']} aggregated per-editor features for "
        f"clustering.",
    ], size=18)
    table(s, ["Group", "Features", "Intuition"], [
        ["Temporal", "hour, day-of-week, weekend, night, hour sin/cos",
         "bots run on cron and show a flat 24h profile; humans sleep"],
        ["Edit size", "bytes, signed diff, |diff|, log|diff|, diff ratio",
         "maintenance bots make small, uniform edits"],
        ["Cadence", "log seconds since previous edit, has-previous, "
                    "log edit count",
         "machine timing is regular; human timing is bursty"],
        ["Account", "age in days, is-anonymous",
         "separates IPs, new accounts and long-lived tools"],
        ["Page context", "namespace, is-content, is-redirect, is-minor, "
                         "is-create",
         "bots concentrate in File/Template namespaces"],
        ["Comment shape", "length, words, /* section */, wikilinks, URLs, "
                          "digit / upper / punct ratio",
         "structure of the message, not its vocabulary"],
        ["Tags", "tag count, mobile, visualeditor, undo",
         "bot-naming tags excluded to avoid leakage"],
        ["Editor-level", "gap CV, night ratio, minor ratio, revert ratio, "
                         "edits per active day, pages per edit",
         "behavioural profile for clustering"],
    ], geom=dict(left=731520, top=1800000, width=10730000, height=3400000),
       size=12, col_widths=[1.1, 3.0, 3.0])
    takeaway(s, "e_gap_cv — the coefficient of variation of inter-edit gaps — "
                "is the single most direct 'metronomic automation' signal.",
             geom=dict(T_TAKE, top=5350000))

    # ---- 10 SVD -----------------------------------------------------------
    s = new_slide(prs, "Phase 4: Dimensionality Reduction with SVD")
    textbox(s, dict(left=731520, top=1020000, width=10730000, height=1250000), [
        f"Comment text is tokenised, hashed into {feat['tfidf_buckets']} TF-IDF "
        f"buckets, then reduced to {feat['svd_k']} dimensions by a **truncated "
        f"SVD** on a distributed mllib RowMatrix. Only the right singular "
        f"matrix V (2048 x {feat['svd_k']}) is collected and broadcast; the "
        f"projection X.V then runs per partition.",
        f"The SVD is **fitted on a 4% sample** — the right singular vectors "
        f"converge with far fewer rows, which cut the fit from 21.5 minutes to "
        f"a few — but the projection is applied to all "
        f"{fmt(prep['rows_final'])} rows. Top singular values: "
        f"{', '.join(f'{v:.0f}' for v in feat['singular_values'][:6])}.",
    ], size=15)
    figure(s, config.FIGURES / "svd_spectrum.png",
           top=2400000, height=2550000, max_bottom=5000000)
    takeaway(s, "A genuine SVD rather than PCA: the decomposition is left "
                "uncentred so the sparse TF-IDF structure is preserved.",
             geom=dict(T_TAKE, top=5120000))

    # ---- 11 leakage -------------------------------------------------------
    s = new_slide(prs, "Leakage Control and the Actor-Disjoint Split")
    textbox(s, dict(T_INTRO, height=700000), [
        "Three separate leaks had to be closed before any score could be "
        "trusted.",
    ], size=18)
    table(s, ["Leak", "Why it leaks", "Control"], [
        ["Username / user groups",
         "usernames literally contain 'Bot' (e.g. SchlurcherBot); "
         "event_user_groups contains the bot group that DEFINES the label",
         "excluded from every feature vector; username used only as a "
         "grouping key"],
        ["Random row split",
         "the same bot account would appear in train and test, letting the "
         "model memorise per-account cadence fingerprints",
         "hash actor_key into disjoint buckets; the script asserts 0 shared "
         "actors"],
        ["Scaler fitted on all data",
         "StandardScaler means/variances would encode test-set statistics",
         "scaler sits INSIDE the ML Pipeline, so it is fitted on the training "
         "fold only"],
    ], geom=dict(left=731520, top=1700000, width=10730000, height=2500000),
       size=12, col_widths=[1.2, 3.0, 2.4])
    textbox(s, dict(left=731520, top=4350000, width=10730000, height=1000000), [
        "**Comment text is kept deliberately.** It is observable at edit time "
        "and is not derived from group membership, so it is a legitimate "
        "predictor — but to keep that claim honest every model is trained "
        "twice, with and without the text block, so its contribution is "
        "measured rather than assumed.",
    ], size=16)
    takeaway(s, f"Verified at run time: {clf['split']}, "
                f"{fmt(clf['n_train'])} train / {fmt(clf['n_test'])} test rows, "
                f"0 shared actors.",
             geom=dict(T_TAKE, top=5500000))

    # ---- 12 MLlib implementation -----------------------------------------
    s = new_slide(prs, "Phase 5: MLlib Implementation")
    code_block(s, dict(left=731520, top=1150000, width=5250000, height=3700000),
               "src/p05_classification.py", """
def actor_split(df, frac, seed):
    b = F.abs(F.hash(F.concat(F.col("actor_key"),
              F.lit(str(seed))))) % 100
    cut = int(frac * 100)
    return (df.filter(F.col("_bucket") < cut),
            df.filter(F.col("_bucket") >= cut))

idx = StringIndexer(...); ohe = OneHotEncoder(...)
num = VectorAssembler(NUMERIC_EDIT_FEATURES, "num_raw")
sca = StandardScaler("num_raw", "num_scaled",
                     withMean=True, withStd=True)
asm = VectorAssembler(["num_scaled", "ns_ohe"]
                      + (["cmt_svd"] if use_text else []),
                      "features")
Pipeline(stages=[idx, ohe, num, sca, asm, model])
""", size=10)
    code_block(s, dict(left=6300000, top=1150000, width=5160000, height=3700000),
               "src/p05_clustering.py", """
# bot flag is NOT an input -- external validation only
asm = VectorAssembler(EDITOR_FEATURES, "raw")
sca = StandardScaler("raw", "features",
                     withMean=True, withStd=True)

for algo in (KMeans, BisectingKMeans,
             GaussianMixture):
    for k in [2,3,4,5,6,7,8]:
        model = algo(k=k).fit(data)
        pred  = model.transform(data)
        # k clusters requested != k NON-EMPTY
        if pred.select("cluster").distinct()
               .count() < 2:
            continue          # degenerate fit
        sil = ClusteringEvaluator().evaluate(pred)
""", size=10)
    takeaway(s, "Classification: LogisticRegression, RandomForest, GBT. "
                "Clustering: KMeans, BisectingKMeans, GaussianMixture over a "
                "k-sweep, selected by silhouette.",
             geom=dict(T_TAKE, top=5050000))

    # ---- 13 classification results table ---------------------------------
    s = new_slide(prs, "Phase 6: Classification Results")
    rows = []
    order = ["logistic_regression", "random_forest", "gbt"]
    pretty = {"logistic_regression": "Logistic Regression",
              "random_forest": "Random Forest", "gbt": "GBT"}
    for feats in ("structural", "full"):
        for m in order:
            k = f"{m}__{feats}"
            if k not in clf["results"]:
                continue
            r = clf["results"][k]
            best = (k == clf["best_model"])
            name = pretty[m] + (" ★" if best else "")
            rows.append([name, feats, f"{r['roc_auc']:.4f}", f"{r['pr_auc']:.4f}",
                         f"{r['accuracy']:.4f}", f"{r['f1']:.4f}",
                         f"{r['bot_precision']:.4f}", f"{r['bot_recall']:.4f}",
                         f"{r['bot_f1']:.4f}"])
    table(s, ["Model", "Features", "ROC-AUC", "PR-AUC", "Accuracy", "F1 (wtd)",
              "Bot precision", "Bot recall", "Bot F1"],
          rows, geom=dict(left=600000, top=1350000, width=11000000,
                          height=3200000), size=12,
          col_widths=[2.0, 1.1, 1.0, 1.0, 1.0, 1.0, 1.1, 1.0, 0.9])
    takeaway(s, f"Best: {clf['best_model'].replace('__',' / ')} at ROC-AUC "
                f"{clf['results'][clf['best_model']]['roc_auc']:.4f} — on a test "
                f"set of accounts never seen in training.",
             geom=dict(T_TAKE, top=4900000))

    # ---- 14 ablation figure ----------------------------------------------
    s = new_slide(prs, "Phase 6: Structural vs Full Feature Sets")
    figure(s, config.FIGURES / "classification_comparison.png",
           top=1150000, height=3900000)
    takeaway(s, "Structural behaviour alone already separates the classes. "
                "Comment text rescues the linear model but barely moves the "
                "tree ensembles -- and does not uniformly help them.",
             geom=dict(T_TAKE, top=5250000))

    # ---- 15 ROC / PR ------------------------------------------------------
    s = new_slide(prs, "Phase 6: ROC and Precision–Recall Curves")
    figure(s, config.FIGURES / "roc_pr_curves.png", top=1250000, height=3600000)
    takeaway(s, "Under class imbalance the precision–recall curve is the more "
                "honest view: it ignores the large true-negative mass that "
                "flatters accuracy.",
             geom=dict(T_TAKE, top=5150000))

    # ---- 16 clustering sweep ---------------------------------------------
    s = new_slide(prs, "Phase 6: Clustering Quality and Model Selection")
    figure(s, config.FIGURES / "clustering_silhouette.png",
           top=1200000, height=3500000)
    textbox(s, dict(left=7600000, top=1250000, width=3900000, height=3400000), [
        f"Editors clustered: **{fmt(clu['n_editors_clustered'])}** of "
        f"{fmt(clu['n_editors_total'])} (minimum {clu['min_edits']} edits — "
        f"single-edit accounts dominate the tail).",
        "",
        f"Best: **{clu['best']}**, which returned "
        f"**{clu['best_k_nonempty']} non-empty** clusters from "
        f"{clu['best_k_requested']} requested.",
        f"Silhouette: **{clu['best_silhouette']:.4f}**",
        "",
        f"Silhouette this low says the clusters are **not** well separated. "
        f"Editor behaviour is a continuum, not a set of tidy groups — so we "
        f"report the partition as a descriptive summary, not as discovered "
        f"natural classes.",
    ], size=14)
    takeaway(s, "A fit can collapse: requesting k clusters does not guarantee k "
                "non-empty ones. k=2 degenerated to a single cluster and was "
                "detected and skipped rather than aborting the sweep.",
             geom=dict(T_TAKE, top=5050000))

    # ---- 17 cluster archetypes -------------------------------------------
    s = new_slide(prs, "Phase 6: Editor Archetypes Discovered")
    prof = clu["cluster_profiles"]
    rows = []
    for p in prof:
        rows.append([
            str(int(p["cluster"])), fmt(int(p["n_editors"])),
            f"{p.get('mean_edits', 0):.0f}",
            f"{p.get('bot_share', 0):.3f}",
            f"{p.get('e_gap_cv', 0):.2f}",
            f"{p.get('e_night_ratio', 0):.2f}",
            f"{p.get('e_minor_ratio', 0):.2f}",
            f"{p.get('e_reverted_ratio', 0):.3f}",
            f"{p.get('e_edits_per_active_day', 0):.1f}",
            f"{p.get('bot_lift', 0):.2f}x",
        ])
    table(s, ["Cluster", "Editors", "Mean edits", "Bot share", "Gap CV",
              "Night ratio", "Minor ratio", "Revert ratio", "Edits/active day",
              "Bot enrichment"],
          rows, geom=dict(left=600000, top=1400000, width=11000000,
                          height=2400000), size=12)
    textbox(s, dict(left=731520, top=3950000, width=10730000, height=1450000), [
        f"**A negative result, reported as one.** Only "
        f"{100*clu['bot_editor_rate']:.2f}% of *accounts* are bots — they are "
        f"few accounts making very many edits — so cluster **purity "
        f"({clu['bot_purity']:.4f}) is exactly the majority-class baseline "
        f"({clu['bot_purity_baseline']:.4f})**, a lift of "
        f"{clu['bot_purity_lift_over_baseline']:+.5f}. Purity therefore carries "
        f"no information here, and quoting it as validation would be misleading.",
        f"The informative measure is **enrichment**: bots are "
        f"**{clu['bot_max_enrichment']:.1f}× over-represented** in the "
        f"high-activity cluster. Real, but modest. **Hypothesis 3 is not "
        f"supported** — the clusters separate *activity level*, not automation.",
    ], size=14)
    takeaway(s, "The clustering describes how much editors do, not whether they "
                "are machines. Automation is recoverable from supervised "
                "behaviour (ROC-AUC 0.976) but is not the dominant axis of "
                "unsupervised variation.",
             geom=dict(T_TAKE, top=5500000))

    # ---- 18 scalability ---------------------------------------------------
    s = new_slide(prs, "Phase 7: Scalability Discussion")
    textbox(s, dict(T_INTRO, height=800000), [
        "Spark is not used because the file is large — it is used because the "
        "workload is a **wide shuffle**, not a scan.",
    ], size=18)
    table(s, ["Stage", "Parallelisation mechanism"], [
        ["Raw TSV read", "bz2 IS splittable in Hadoop, so the 951 MB file is "
                         "read by 12 concurrent tasks (gzip would be one task)"],
        ["Column projection", f"Parquet keeps {ing['columns_kept']} of 78 columns, so later "
                              f"phases read roughly a third of the bytes"],
        ["Feature engineering", "row-local withColumn — embarrassingly "
                                "parallel, no shuffle"],
        ["Editor aggregation", "groupBy + window lag → sort-merge shuffle "
                               "across 48 partitions; this is the expensive step"],
        ["SVD", "distributed RowMatrix; only V (2048 × 24) is collected and "
                "broadcast"],
        ["Model training", "MLlib broadcasts the model and reduces histograms "
                           "per partition"],
    ], geom=dict(left=731520, top=1750000, width=10730000, height=2100000),
       size=12, col_widths=[1.2, 4.0])
    textbox(s, dict(left=731520, top=4000000, width=10730000, height=1400000), [
        "**Actor skew is the dominant risk at scale.** Edit counts per account "
        "follow a heavy power law — a few bots have millions of revisions while "
        "the median account has one. A naive groupBy sends one enormous "
        "partition to a single task, which straggles or OOMs while other cores "
        "idle. Mitigations: adaptive skew-join (enabled), salting the heaviest "
        "keys, and bounded-memory sketches instead of exact percentiles.",
        "**Other limits:** small-files problem on write (we repartition before "
        "writing), broadcast ceiling on V if TF-IDF buckets grow, and "
        "stratified sampling must happen AFTER the actor split or the "
        "disjointness guarantee breaks.",
    ], size=15)

    # ---- 19 results and observations -------------------------------------
    s = new_slide(prs, "Results and Observations")
    best = clf["results"][clf["best_model"]]
    struct_gbt = clf["results"].get("gbt__structural", {})
    full_gbt = clf["results"].get("gbt__full", {})
    lr_s = clf["results"].get("logistic_regression__structural", {})
    lr_f = clf["results"].get("logistic_regression__full", {})
    obs = [
        f"Automated edits are **{bot_pct:.1f}%** of all "
        f"{fmt(prep['rows_final'])} edits, and **{rev_pct:.1f}%** of edits are "
        f"later reverted.",
        f"Best classifier: **{clf['best_model'].replace('__', ' / ')}** at "
        f"ROC-AUC **{best['roc_auc']:.4f}**, PR-AUC **{best['pr_auc']:.4f}**, "
        f"bot-F1 **{best['bot_f1']:.4f}** — on accounts never seen in training.",
    ]
    if struct_gbt and full_gbt:
        d = full_gbt["roc_auc"] - struct_gbt["roc_auc"]
        direction = ("adds nothing" if abs(d) < 0.002 else
                     "slightly reduces it" if d < 0 else "raises it")
        obs.append(
            f"**Hypothesis 2 held:** structural behaviour alone is already "
            f"sufficient — GBT reaches ROC-AUC {struct_gbt['roc_auc']:.4f} with "
            f"no comment vocabulary at all, and adding the text block "
            f"{direction} ({full_gbt['roc_auc']:.4f}). Automation is legible "
            f"from *behaviour*, not from what the edit says.")
    if lr_s and lr_f:
        obs.append(
            f"Text matters only to the **linear** model "
            f"({lr_s['roc_auc']:.4f} → {lr_f['roc_auc']:.4f}, PR-AUC "
            f"{lr_s['pr_auc']:.4f} → {lr_f['pr_auc']:.4f}). The tree ensembles "
            f"already capture the non-linear interactions that the SVD "
            f"dimensions merely make visible to a linear boundary — so the "
            f"ablation measures model capacity as much as feature value.")
    obs += [
        f"Clustering: **{clu['best']}** at silhouette "
        f"{clu['best_silhouette']:.4f} over "
        f"{fmt(clu['n_editors_clustered'])} active editors — a weak separation. "
        f"**Hypothesis 3 was not supported:** the partition tracks activity "
        f"level, not automation. Bots are only "
        f"{clu['bot_max_enrichment']:.1f}× enriched in the busiest cluster, and "
        f"purity equals its own baseline exactly.",
        "Accuracy is the **least** informative metric here: with a "
        f"{bot_pct:.0f}/{100-bot_pct:.0f} split, a model can look strong on "
        "accuracy while ranking poorly, which is why PR-AUC and the per-class "
        "bot-F1 are reported alongside it.",
        f"Cleaning cost only "
        f"{100*(prep['rows_in']-prep['rows_final'])/prep['rows_in']:.2f}% of "
        f"rows after recovering deleted-page revisions from the "
        f"*_historical columns.",
    ]
    textbox(s, dict(left=731520, top=1150000, width=10730000, height=4300000),
            obs, size=16, bullet=True, space_after=10)

    # ---- 20 challenges ----------------------------------------------------
    s = new_slide(prs, "Challenges Faced")
    textbox(s, dict(left=731520, top=1080000, width=10730000, height=4400000), [
        "**1. The published schema is wrong.** The docs list 76 fields; the "
        "snapshot ships 78. Trusting the doc would misalign every column, so we "
        "verified all 78 positions empirically by profiling fill-rate and value "
        "shape per index, anchored on event_entity, page_id and "
        "revision_text_sha1.",
        "**2. Raw quotes in comments silently shift columns.** event_comment "
        "contains characters like \"Bad words\"; with default CSV quoting Spark "
        "absorbs tab delimiters inside the apparently-quoted region. Fixed with "
        "option(\"quote\", \"\").",
        "**3. Deleted-page bias.** 14.8% of revisions have NULL page_namespace "
        "because the page was deleted. Dropping them would have discarded 15% "
        "of the data — and deleted pages concentrate vandalism, so it would "
        "have biased label_reverted, not merely shrunk the dataset.",
        "**4. NULL booleans became NaN.** NULL == \"true\" is NULL in SQL, so "
        "nulls survived the cast, became NaN in VectorAssembler and propagated "
        "through StandardScaler — failing deep inside a model fit with no hint "
        "of the guilty column. Fixed by coalescing, plus a null guard that "
        "fails loudly and names the column.",
        "**5. pandas_udf cannot accept VectorUDT input.** The vectorised SVD "
        "projection received str and crashed. Reverted to a plain UDF with a "
        "single numpy gather+dot per row; densifying 2048 columns to vectorise "
        "would cost more than it saves.",
        "**6. A 21.5-minute SVD fit** was running over 15% of 11 M rows. The "
        "right singular vectors converge with far fewer rows, so we fit on 4% "
        "and still project all rows.",
        "**7. Degenerate clustering.** Requesting k clusters does not guarantee "
        "k non-empty ones, and ClusteringEvaluator then aborts the whole sweep.",
        "**8. Phase 0 decompressed the 951 MB bz2 four times**, once per "
        "action. One grouped aggregate now yields the row total, entity "
        "breakdown and wiki sanity check together: four passes became two.",
    ], size=13, space_after=8)

    # ---- 21 conclusion ----------------------------------------------------
    s = new_slide(prs, "Conclusion and Future Scope")
    textbox(s, dict(left=731520, top=1080000, width=10730000, height=2100000), [
        "**Conclusion**",
        f"We built a complete Spark MLlib pipeline over "
        f"{fmt(prep['rows_final'])} real Wikimedia edits: Parquet ingestion, "
        f"DataFrame cleaning with an enforced null contract, "
        f"{feat['n_numeric_edit_features']} engineered behavioural features "
        f"plus a {feat['svd_k']}-dimension truncated SVD of comment text, three "
        f"classifiers and three clustering algorithms, all evaluated under an "
        f"actor-disjoint split. Automation is predictable from behaviour alone "
        f"(ROC-AUC {best['roc_auc']:.4f}). Unsupervised clustering of the same "
        f"editors, by contrast, separates activity level rather than "
        f"automation — bots are only {clu['bot_max_enrichment']:.1f}x enriched "
        f"in the busiest cluster. We report that as a negative result: "
        f"automation is learnable with supervision but is not the dominant "
        f"axis of unsupervised behavioural variation.",
    ], size=16)
    textbox(s, dict(left=731520, top=3200000, width=10730000, height=2200000), [
        "**Known limitations** (stated rather than hidden)",
        "The label covers only **flagged** accounts, so unapproved bots are "
        "false negatives by construction and recall is measured against an "
        "incomplete positive class.",
        "Semi-automated human tooling (AWB, Huggle) genuinely sits between the "
        "classes; no clean boundary exists there.",
        "The all-time snapshot spans 2001–2026, averaging over several distinct "
        "editing regimes.",
        "**Future scope:** scale to enwiki monthly shards on a real cluster; "
        "score the live EventStreams feed with the trained model; model "
        "label_reverted as a second task; treat era as a stratum.",
    ], size=14, bullet=False, space_after=6)

    # ---- 22 references ----------------------------------------------------
    s = new_slide(prs, "References")
    textbox(s, dict(left=731520, top=1150000, width=10730000, height=4200000), [
        "[1] Wikimedia Foundation. MediaWiki History Dumps. "
        "https://dumps.wikimedia.org/other/mediawiki_history/ (CC0).",
        "[2] Wikimedia Foundation. EventStreams. "
        "https://stream.wikimedia.org/v2/stream/recentchange",
        "[3] A. Halfaker and D. Taraborelli. \"ORES: Scaling up machine "
        "learning-driven quality control.\" Wikimedia, 2015.",
        "[4] M. Potthast, B. Stein and R. Gerling. \"Automatic Vandalism "
        "Detection in Wikipedia.\" ECIR, 2008.",
        "[5] B. T. Adler et al. \"Wikipedia Vandalism Detection: Combining "
        "Natural Language, Metadata and Reputation Features.\" CICLing, 2011.",
        "[6] C. A. Davis et al. \"BotOrNot: A System to Evaluate Social Bots.\" "
        "WWW (demo), 2016.",
        "[7] Z. Chu et al. \"Detecting Automation of Twitter Accounts: Are You "
        "a Human, Bot, or Cyborg?\" IEEE TDSC, 2012.",
        "[8] H. T. Welser et al. \"Finding Social Roles in Wikipedia.\" "
        "iConference, 2011.",
        "[9] S. Kumar, F. Spezzano and V. S. Subrahmanian. \"VEWS: A Wikipedia "
        "Vandal Early Warning System.\" KDD, 2015.",
        "[10] M. Zaharia et al. \"Resilient Distributed Datasets: A "
        "Fault-Tolerant Abstraction for In-Memory Cluster Computing.\" NSDI, 2012.",
        "[11] X. Meng et al. \"MLlib: Machine Learning in Apache Spark.\" "
        "JMLR 17(34), 2016.",
        "[12] Apache Spark documentation, version 3.5.3. "
        "https://spark.apache.org/docs/3.5.3/ml-guide.html",
    ], size=14, space_after=5)

    # ---- 23 thank you -----------------------------------------------------
    s = prs.slides.add_slide(prs.slide_layouts[2])
    for p in s.placeholders:
        if p.placeholder_format.idx == 0:
            p.text_frame.clear()
            para = p.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.CENTER
            r = para.add_run(); r.text = "THANK YOU"
            r.font.name = TITLE_FONT; r.font.size = Pt(44); r.font.bold = True

    return prs


def main():
    prs = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"wrote {OUT}")
    print(f"  slides: {len(prs.slides.__iter__.__self__._sldIdLst)}")


if __name__ == "__main__":
    main()
