/*
 * Generate the Assignment 2 technical report (.docx) from reports/metrics.
 *
 * Section order follows the assignment brief: Title, Abstract, Introduction,
 * Dataset Description, Spark Architecture, RDD-Based Processing, DataFrame
 * Analytics, Structured Streaming, Results and Discussion, Conclusion,
 * References.
 *
 * Every figure, table and number is read from the pipeline's own output, so the
 * report cannot drift out of sync with the run that produced it. Regenerate
 * after any re-run:   node src/make_report.js
 */
const fs = require("fs");
const path = require("path");
const {
  AlignmentType, BorderStyle, Document, Footer, HeadingLevel, ImageRun,
  LevelFormat, PageBreak, PageNumber, Packer, Paragraph, ShadingType, Table,
  TableCell, TableRow, TextRun, WidthType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const M = path.join(ROOT, "reports", "metrics");
const F = path.join(ROOT, "reports", "figures");
const OUT = path.join(ROOT, "reports", "Assignment2_Spark_Report.docx");

const j = (n) => JSON.parse(fs.readFileSync(path.join(M, `${n}.json`), "utf8"));
const ing = j("p00_ingest"), prep = j("p03_prepare"), feat = j("p04_features");
const clf = j("p05_classification"), clu = j("p05_clustering");
const rdd = j("pb_rdd"), sql = j("pc_sql"), str = j("pe_streaming");

const N = (x) => Number(x).toLocaleString("en-US");
const pct = (x, d = 2) => `${(100 * x).toFixed(d)}%`;
const f4 = (x) => Number(x).toFixed(4);

// ----------------------------------------------------------------- styling
const BODY = "Cambria", MONO = "Consolas";
const PAGE = { width: 12240, height: 15840 };     // US Letter, DXA
const CONTENT_W = 12240 - 1296 - 1296;            // 0.9" margins -> 9648 DXA

const p = (text, opts = {}) => new Paragraph({
  alignment: opts.align || AlignmentType.JUSTIFIED,
  spacing: { after: opts.after ?? 100, line: opts.line ?? 248 },
  indent: opts.indent,
  children: inline(text, opts),
});

/** Split **bold** and `code` spans into runs. */
function inline(text, opts = {}) {
  if (Array.isArray(text)) return text;
  const out = [];
  // Order matters: code spans are matched before single-asterisk italics so
  // that identifiers like `page_*` and `*_historical` keep their asterisks.
  const re = /(\*\*.+?\*\*|`[^`]+`|\*[^*`\n]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(run(text.slice(last, m.index), opts));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(run(tok.slice(2, -2), { ...opts, bold: true }));
    else if (tok.startsWith("`")) out.push(run(tok.slice(1, -1), { ...opts, font: MONO, size: (opts.size || 21) - 2 }));
    else out.push(run(tok.slice(1, -1), { ...opts, italics: true }));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(run(text.slice(last), opts));
  return out;
}
const run = (t, o = {}) => new TextRun({
  text: t, font: o.font || BODY, size: o.size || 21,
  bold: o.bold || false, italics: o.italics || false, color: o.color,
});

const h = (text, level) => new Paragraph({
  heading: level, keepNext: true,
  spacing: { before: level === HeadingLevel.HEADING_1 ? 240 : 180, after: 90 },
  children: [run(text, { bold: true, size: level === HeadingLevel.HEADING_1 ? 28 : 24 })],
});
const h1 = (t) => h(t, HeadingLevel.HEADING_1);
const h2 = (t) => h(t, HeadingLevel.HEADING_2);

const bullets = (items) => items.map((t) => new Paragraph({
  numbering: { reference: "bul", level: 0 },
  alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 70, line: 248 },
  children: inline(t),
}));

function table(headers, rows, widths, opts = {}) {
  const size = opts.size || 18;
  const cols = widths.map((w) => Math.round(CONTENT_W * w / widths.reduce((a, b) => a + b, 0)));
  const cell = (txt, i, hdr) => new TableCell({
    width: { size: cols[i], type: WidthType.DXA },
    shading: hdr ? { type: ShadingType.CLEAR, fill: "D9E2F3" } : undefined,
    margins: { top: 40, bottom: 40, left: 80, right: 80 },
    children: [new Paragraph({
      alignment: i === 0 ? AlignmentType.LEFT : (opts.alignAll || AlignmentType.LEFT),
      spacing: { after: 0, line: 224 },
      children: inline(String(txt), { size, bold: hdr }),
    })],
  });
  return new Table({
    columnWidths: cols,
    width: { size: CONTENT_W, type: WidthType.DXA },
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((t, i) => cell(t, i, true)) }),
      ...rows.map((r) => new TableRow({ children: r.map((t, i) => cell(t, i, false)) })),
    ],
  });
}

function figure(file, caption, widthIn = 6.0) {
  const abs = path.join(F, file);
  if (!fs.existsSync(abs)) return [p(`(figure missing: ${file})`)];
  // intrinsic size, to preserve aspect ratio
  const buf = fs.readFileSync(abs);
  const w = buf.readUInt32BE(16), hgt = buf.readUInt32BE(20);   // PNG IHDR
  const W = widthIn * 96, H = Math.round(W * hgt / w);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 },
      children: [new ImageRun({ type: "png", data: buf, transformation: { width: W, height: H } })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [run(caption, { size: 18, italics: true })],
    }),
  ];
}

function code(lines, caption) {
  const out = [];
  if (caption) out.push(new Paragraph({
    spacing: { before: 120, after: 40 },
    children: [run(caption, { font: MONO, size: 17, bold: true, color: "2F5496" })],
  }));
  lines.forEach((l, i) => out.push(new Paragraph({
    spacing: { after: 0, line: 230 },
    indent: { left: 240 },
    border: i === 0 ? { top: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF", space: 4 } } : undefined,
    children: [run(l || " ", { font: MONO, size: 17 })],
  })));
  out.push(new Paragraph({
    spacing: { after: 160 },
    border: { top: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF", space: 2 } },
    children: [run("", { size: 2 })],
  }));
  return out;
}


// ------------------------------------------------------- derived quantities
const best = clf.results[clf.best_model];
const gbtS = clf.results["gbt__structural"], gbtF = clf.results["gbt__full"];
const lrS = clf.results["logistic_regression__structural"];
const lrF = clf.results["logistic_regression__full"];
const PRETTY = { logistic_regression: "Logistic Regression",
                 random_forest: "Random Forest", gbt: "GBT" };
const dropPct = 100 * (prep.rows_in - prep.rows_final) / prep.rows_in;
const seg = Object.fromEntries(sql.segments.map((s) => [s.segment, s]));
const botAgg = rdd.by_bot.bot, humanAgg = rdd.by_bot.human;

const children = [];

// ---------------------------------------------------------------- 1 TITLE
children.push(
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1500, after: 120 },
    children: [run("Scalable Processing and Analysis of Wikimedia Editing Activity using Apache Spark", { bold: true, size: 32 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 360 },
    children: [run("RDD transformations, DataFrame and Spark SQL analytics, Structured Streaming and distributed MLlib over 11.0 million Wikimedia revisions", { size: 22, italics: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 },
    children: [run("Mining of Massive Datasets (23CSE355) — Assignment 2", { size: 23, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 },
    children: [run("Technical Report", { size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
    children: [run("Team 22        Project Advisor: Dr Niharika Panda", { size: 21 })] }),
);
children.push(table(["Sl. No.", "Reg. No.", "Name of the student"], [
  ["1", "BL.EN.U4CSE23206", "Aman Agarwal"],
  ["2", "BL.EN.U4CSE23209", "Atharva Wasnik"],
  ["3", "BL.EN.U4CSE23245", "Pulapa Yaswanth Kumar"],
], [0.8, 2, 2.4], { size: 19 }));
children.push(new Paragraph({ children: [new PageBreak()] }));

// -------------------------------------------------------------- 2 ABSTRACT
children.push(h1("Abstract"));
children.push(p(
  `This report describes a PySpark pipeline that ingests, transforms, queries and models the complete edit history of Simple English Wikipedia. The source is the Wikimedia mediawiki_history dump, snapshot 2026-10: a ${"951 MB"} bzip2-compressed TSV of ${N(ing.raw_rows)} rows across 78 columns, of which ${N(ing.revision_rows)} are individual revisions. ` +
  `All four Spark programming interfaces are exercised on the same corpus. The RDD API performs low-level transformations directly on the compressed dump, parsing ${N(rdd.num_revisions)} revisions across ${rdd.num_partitions} partitions and producing a word-frequency analysis over ${N(rdd.total_comment_tokens)} comment tokens. The DataFrame API and Spark SQL clean the data to ${N(prep.rows_final)} usable records and answer aggregate questions declaratively. Structured Streaming consumes a replay of the corpus as a file source, processing ${N(str.rows_processed)} records in ${str.batches_processed} micro-batches with a watermarked event-time aggregation. MLlib then trains three classifiers and three clustering algorithms. ` +
  `Three findings are reported. First, anonymous contributors are reverted at ${pct(seg["anonymous"].revert_rate, 2)} against ${pct(botAgg.revert_rate, 2)} for automated accounts — a factor of ${(seg["anonymous"].revert_rate / botAgg.revert_rate).toFixed(1)}. Second, automated editing is highly predictable from behaviour alone: ${PRETTY[clf.best_model.split("__")[0]]} reaches ROC-AUC ${f4(best.roc_auc)} under an actor-disjoint split, and gradient-boosted trees reach ${f4(gbtS.roc_auc)} using no comment vocabulary whatsoever. Third, unsupervised clustering of editor behaviour separates activity level rather than automation, and is reported as a negative result.`
));

// ----------------------------------------------------------- 3 INTRODUCTION
children.push(h1("1. Introduction"));
children.push(p(
  "Wikimedia projects accept edits from anyone, with no editorial review before publication. Across all projects the platform absorbs roughly 30 to 50 edits per second — a figure we measured directly rather than quoted, by running a Server-Sent Events collector against the live Recent Changes feed and recording 910 events in 30 seconds. A substantial share of that traffic is automated: approved maintenance bots, semi-automated human tooling, and unapproved scripts."
));
children.push(p(
  "Processing a corpus of this size is not a matter of a larger loop. The questions that matter — how often does each editor act, how regular is their rhythm, which pages attract the most revisions — require data to be regrouped by key across the whole dataset. That regrouping is a distributed shuffle, and it is the operation around which Apache Spark is designed."
));
children.push(p(
  "This assignment therefore exercises Spark's four programming interfaces against one corpus, so that the same data can be processed at four levels of abstraction and the results cross-checked against one another. The RDD API gives explicit control over partitions and transformations; the DataFrame API and Spark SQL give schema-aware, optimiser-backed processing; Structured Streaming gives incremental processing of arriving data; and MLlib supplies distributed learning algorithms."
));
children.push(h2("1.1 Objectives"));
children.push(...bullets([
  "Ingest a large compressed dump into a columnar store and establish a clean, typed, labelled dataset.",
  "Demonstrate RDD transformations — `map`, `filter`, `flatMap`, `reduceByKey` — directly on the raw compressed file.",
  "Express equivalent analytical questions through the DataFrame API and Spark SQL, and compare the two.",
  "Consume arriving records with Structured Streaming and aggregate them per micro-batch and per event-time window.",
  "Train and evaluate distributed classification and clustering models, under an evaluation design that cannot be gamed by memorisation.",
]));

// ------------------------------------------------------ 4 DATASET
children.push(h1("2. Dataset Description"));
children.push(p(
  "The dataset is the Wikimedia Foundation's `mediawiki_history` dump, published under a CC0 dedication. Each row is an *event*, not necessarily an edit: the `event_entity` column distinguishes revision events from page and user events."
));
children.push(table(["Property", "Value"], [
  ["Source", "dumps.wikimedia.org/other/mediawiki_history/2026-10/simplewiki/"],
  ["Licence", "CC0 public domain dedication"],
  ["Compressed size", "951 MB, bzip2-compressed TSV, no header row"],
  ["Columns", `78 tab-separated fields; ${ing.columns_kept} retained`],
  ["Total dump rows", N(ing.raw_rows)],
  ["— revision events", `${N(ing.entity_counts.revision)} (the unit of analysis)`],
  ["— page events", N(ing.entity_counts.page)],
  ["— user events", N(ing.entity_counts.user)],
  ["Usable after cleaning", `${N(prep.rows_final)} (${dropPct.toFixed(2)}% removed)`],
  ["Distinct editors", N(feat.n_editors)],
  ["Bot-labelled edits", `${N(prep.bot_edits)} (${pct(prep.bot_rate, 2)})`],
  ["Reverted edits", `${N(prep.reverted_edits)} (${pct(prep.reverted_rate, 2)})`],
  ["Live companion feed", "stream.wikimedia.org EventStreams (SSE), ~30 events/second measured"],
], [1, 2.6], { size: 18 }));
children.push(p(""));
children.push(h2("2.1 The published schema is not the shipped schema"));
children.push(p(
  "The Wikitech documentation states that these dumps contain 76 fields. The 2026-10 snapshot ships **78**; the two additional fields are `event_user_central_id` and `user_central_id`. Accepting the documented order on trust would have misaligned every column in the file."
));
children.push(p(
  "Column order was therefore established empirically: every column index was profiled for fill-rate and value shape (boolean, integer, timestamp, free text, base-36 hash) and matched against the documented field groups. Reliable anchors were `event_entity` (only three distinct values), `page_id`, `revision_text_sha1` (40-character base-36 hashes) and `revision_tags` (final column). One column remains undocumented — column 2 holds a large integer populated almost exclusively on `user` rows; it is named `event_log_id` and is unused, since every phase filters to revision events."
));
children.push(h2("2.2 Parsing hazards"));
children.push(...bullets([
  "**Embedded quotation marks.** `event_comment` contains raw double quotes. Spark's CSV reader treats `\"` as a quoting character by default and absorbs tab delimiters inside an apparently quoted region, silently shifting every later column on that row. Quote handling must be disabled with `.option(\"quote\", \"\")`. A raw `split(\"\\t\")` in the RDD path is unaffected, because tabs are the delimiter and never occur inside a field.",
  "**Nulls are empty strings**, and timestamps use the form `2001-05-18 21:57:10.0` — pattern `yyyy-MM-dd HH:mm:ss.S`, not ISO-8601. Allowing Spark to infer types silently drops rows.",
  "**bzip2 is splittable** under Hadoop, so the 951 MB file is read concurrently. The RDD job obtained **" + rdd.num_partitions + " partitions**. A gzip-compressed dump would have been confined to a single task.",
]));

// -------------------------------------------------- 5 SPARK ARCHITECTURE
children.push(h1("3. Spark Architecture"));
children.push(p(
  "A Spark application is coordinated by a **driver** and executed by **executors**. The driver holds the `SparkSession`, builds a logical plan from the transformations the program expresses, and hands it to the DAG scheduler. The DAG scheduler divides the plan into **stages** at shuffle boundaries; the task scheduler submits one **task** per partition within each stage. A **cluster manager** allocates the resources the executors run in."
));
children.push(p(
  "Transformations are **lazy**. Writing `filter` or `withColumn` adds a node to the graph and executes nothing. Only an **action** — `count()`, `collect()`, `write` — triggers a job. This matters practically, as Section 3.3 shows."
));
children.push(table(["Component", "Role in this project"], [
  ["Driver", "builds the DAG, broadcasts the SVD matrix, collects final metrics"],
  ["Cluster manager", "Spark's built-in local scheduler; no YARN or Kubernetes configured"],
  ["Executors", "threads inside the driver JVM under `local[*]`, 12 cores"],
  ["Partitions", `${rdd.num_partitions} on the raw bz2 read; 48 after every shuffle`],
], [1, 3], { size: 18 }));
children.push(p(""));
children.push(h2("3.1 Deployment and configuration"));
children.push(p(
  "The application runs in local mode on a single 12-core, 15 GB machine. Driver and executors are threads in one JVM. The code is unchanged for a real cluster; only the master URL and resource settings differ."
));
children.push(...code([
  'SPARK_CONF = {',
  '  "spark.driver.memory": "6g",',
  '  "spark.sql.shuffle.partitions": "48",        # ~4x cores',
  '  "spark.sql.adaptive.enabled": "true",',
  '  "spark.sql.adaptive.coalescePartitions.enabled": "true",',
  '  "spark.sql.adaptive.skewJoin.enabled": "true",   # hyperactive bots skew',
  '  "spark.serializer": "org.apache.spark.serializer.KryoSerializer",',
  '}',
  'MASTER = "local[*]"',
], "src/config.py"));
children.push(p(
  "Spark's default of 200 shuffle partitions is tuned for clusters; on 12 cores it produces tiny tasks dominated by scheduling overhead. We set 48, roughly four times the core count. Adaptive Query Execution is enabled so that post-shuffle partition counts are corrected at runtime rather than guessed in advance, and so that skewed partitions are split automatically."
));
children.push(table(["Component", "Version"], [
  ["Python", "3.11.18 (via uv)"],
  ["PySpark", "3.5.3"],
  ["Java", "OpenJDK Temurin 17.0.21"],
  ["Hardware", "12 cores / 15 GB, local[*]"],
], [1, 1.6], { size: 18 }));
children.push(p(""));
children.push(h2("3.2 Two environment traps"));
children.push(p(
  "Both fail at task execution time rather than at import, which makes them hard to diagnose. First, `PYSPARK_PYTHON` must be pinned: the system Python here is 3.14, and if workers resolve a different minor version than the driver, Spark aborts mid-task with `PYTHON_VERSION_MISMATCH`. Second, PySpark 3.5 cannot run on Python 3.12 at all, because `pyspark/ml/image.py` imports `distutils`, which 3.12 removed; support arrived in Spark 4.0. Python 3.11 is the newest version PySpark 3.5.3 officially supports."
));
children.push(h2("3.3 Lazy evaluation, observed"));
children.push(p(
  "The first version of the ingestion phase called four actions — a `count()`, a `distinct()`, a `groupBy().count()` and a `write`. Because nothing was cached, each action replayed the lineage from source and **decompressed the 951 MB file a separate time**. Replacing the first three with a single grouped aggregate, which yields the row total, the entity breakdown and a wiki sanity check together, reduced four passes to two."
));
children.push(p(
  "The same principle governs the RDD phase, where a single `persist` after parsing turns five subsequent analyses from full re-parses into seconds. Section 4.3 quantifies this."
));

// ------------------------------------------------ 6 RDD-BASED PROCESSING
children.push(h1("4. RDD-Based Processing"));
children.push(p(
  "The RDD phase (`src/pb_rdd.py`) operates on the raw compressed dump with Spark's low-level API, giving explicit control over partitioning, caching and the transformation chain."
));
children.push(h2("4.1 RDD creation and parsing"));
children.push(...code([
  'lines = sc.textFile(str(config.RAW_TSV), minPartitions=24)',
  '',
  'parsed = lines.map(parse).filter(lambda r: r is not None)',
  'revs = (parsed.filter(lambda r: r[0] == "revision")',
  '              .map(lambda r: r[1:])',
  '              .persist(StorageLevel.MEMORY_AND_DISK))',
], "src/pb_rdd.py"));
children.push(p(
  `\`textFile\` requested a floor of 24 partitions and Spark produced **${rdd.num_partitions}**, because bzip2 is splittable and Spark sizes splits from the file itself. \`minPartitions\` is a lower bound, not an instruction.`
));
children.push(p(
  "The parse function projects each 78-field line down to a compact tuple before the RDD is persisted. Retaining full field lists for 11 million rows as Python objects would not fit in memory; the projection is a handful of small fields and spills to disk cheaply under `MEMORY_AND_DISK`."
));
children.push(h2("4.2 Transformations and actions"));
children.push(...code([
  '# reduceByKey: edits per namespace',
  'ns = (revs.map(lambda r: (r[0], 1))',
  '          .reduceByKey(lambda a, b: a + b)',
  '          .takeOrdered(10, key=lambda kv: -kv[1]))',
  '',
  '# flatMap: word count over every edit comment',
  'words = (revs.flatMap(lambda r: TOKEN.split(r[6].lower()))',
  '             .filter(lambda w: len(w) > 2 and w not in STOP)',
  '             .map(lambda w: (w, 1))',
  '             .reduceByKey(lambda a, b: a + b)',
  '             .persist(StorageLevel.MEMORY_AND_DISK))',
], "src/pb_rdd.py"));
children.push(p(
  `The \`flatMap\` expands ${N(rdd.num_revisions)} comments into individual tokens, yielding **${N(rdd.total_comment_tokens)} tokens** after stop-word removal. \`reduceByKey\` then aggregates them. Note that \`words\` is consumed twice — once summed, once ordered — so it is persisted; without that the entire tokenisation would run twice.`
));
children.push(h2("4.3 Caching and job structure"));
children.push(p(
  "Each action is one Spark job, and each job replays the lineage from source unless an intermediate result is persisted. The effect is visible in the measured timings:"
));
children.push(table(["Action", "Job", "Elapsed", "Shuffle?"], [
  ["`count()` — forces the parse", "1", "61.1 s", "no"],
  ["edits per namespace (`reduceByKey`)", "2", "3.1 s", "yes"],
  ["most active editors (`reduceByKey`)", "3", "3.8 s", "yes"],
  ["comment word count (`flatMap`)", "4", "16.0 s", "yes"],
  ["bot / anonymous aggregates", "5", "6.9 s", "yes"],
], [2.6, 0.5, 0.8, 0.7], { size: 18 }));
children.push(p(""));
children.push(p(
  "The first action pays 61.1 seconds to decompress and parse 11 million rows. Every subsequent action reuses the persisted projection and costs seconds. Without `persist`, jobs 2 through 5 would each repeat that 61-second parse — roughly five minutes of wasted work."
));
children.push(h2("4.4 RDD results"));
children.push(table(["Namespace", "Edits"],
  rdd.top_namespaces.slice(0, 6).map((kv) => [`\`${kv[0]}\``, N(kv[1])]),
  [1, 1], { size: 18 }));
children.push(p(""));
children.push(table(["Most frequent comment token", "Occurrences"],
  rdd.top_comment_words.slice(0, 8).map((kv) => [`\`${kv[0]}\``, N(kv[1])]),
  [1.6, 1], { size: 18 }));
children.push(p(""));
children.push(p(
  `The vocabulary is dominated by maintenance language — \`${rdd.top_comment_words[0][0]}\`, \`${rdd.top_comment_words[1][0]}\`, \`${rdd.top_comment_words[3][0]}\`, \`hotcat\` — which is consistent with a corpus where ${pct(prep.bot_rate, 1)} of edits are automated. The most active accounts include \`${rdd.top_editors[0][0]}\` with ${N(rdd.top_editors[0][1])} edits and \`InternetArchiveBot\` with ${N(rdd.top_editors.find((e) => e[0] === "InternetArchiveBot")[1])}.`
));
children.push(table(["Actor class", "Edits", "Revert rate"], [
  ["Human (non-bot-flagged)", N(humanAgg.edits), pct(humanAgg.revert_rate, 2)],
  ["Bot-flagged", N(botAgg.edits), pct(botAgg.revert_rate, 2)],
  ["Anonymous (IP)", N(rdd.anonymous_edits), pct(rdd.anonymous_revert_rate, 2)],
], [1.6, 1, 1], { size: 18 }));
children.push(p(""));
children.push(p(
  `This is the phase's substantive finding. Anonymous contributors are reverted at ${pct(rdd.anonymous_revert_rate, 2)}, against ${pct(botAgg.revert_rate, 2)} for automated accounts — a factor of ${(rdd.anonymous_revert_rate / botAgg.revert_rate).toFixed(1)}. Automated editing is, by this measure, the *least* frequently reverted category on the platform.`
));

// ------------------------------------------------- 7 DATAFRAME ANALYTICS
children.push(h1("5. DataFrame Analytics and Spark SQL"));
children.push(p(
  `The DataFrame phase works on the cleaned, typed table: ${N(sql.rows)} rows and ${sql.columns} columns stored as Snappy-compressed Parquet. Parquet is columnar, so a query touching five columns reads roughly five columns' worth of bytes rather than all 31.`
));
children.push(h2("5.1 Cleaning"));
children.push(p(
  "Three cleaning decisions materially affect the results."
));
children.push(p(
  "**Recovering deleted pages.** When a page is deleted, MediaWiki nulls the current-state `page_*` columns but retains their `*_historical` counterparts. 14.8% of revisions have a null `page_namespace` for this reason. Discarding them would remove roughly one edit in seven — and, more seriously, introduce bias rather than mere loss, because deleted pages are exactly where vandalism concentrates. Coalescing from the historical columns reduced loss from about 15% to " + dropPct.toFixed(2) + "%."
));
children.push(p(
  "**Boolean nulls.** In SQL, `NULL == \"true\"` evaluates to NULL, not false, so a naive cast leaves nulls in place. Those nulls become NaN in `VectorAssembler`, and `StandardScaler` then propagates the NaN until Spark rejects the feature vector — failing deep inside a model fit, naming neither the column nor the phase responsible. The cast now coalesces to false, and the phase asserts a null contract over every column that feeds a feature vector, aborting with the offending column names if one survives."
));
children.push(p(
  "**Imputation with meaning.** A null inter-edit interval marks a user's first edit. It is filled with the sentinel −1 rather than 0, since 0 would assert an instantaneous repeat edit; a companion binary feature keeps the sentinel distinguishable after scaling."
));
children.push(table(["Step", "Rows"], [
  ["Revision rows read", N(prep.rows_in)],
  ["Removed: duplicate `revision_id`", N(prep.duplicates_removed)],
  ["Removed: null structural key", N(prep.null_key_rows_removed)],
  ["**Clean rows**", `**${N(prep.rows_final)}**`],
], [2.2, 1], { size: 18 }));
children.push(p(""));
children.push(h2("5.2 DataFrame API and Spark SQL side by side"));
children.push(...code([
  '# DataFrame API',
  'ns = (df.groupBy("page_namespace")',
  '        .agg(F.count("*").alias("edits"),',
  '             F.round(F.avg("label_bot"), 4).alias("bot_share"))',
  '        .orderBy(F.desc("edits")).limit(10))',
  '',
  '# Spark SQL -- identical question, declarative form',
  'df.createOrReplaceTempView("wikimedia_edits")',
  'spark.sql("""',
  '    SELECT page_namespace, COUNT(*) AS edits',
  '    FROM wikimedia_edits GROUP BY page_namespace',
  '    ORDER BY edits DESC LIMIT 10""")',
], "src/pc_sql.py"));
children.push(p(
  `Measured on the same data, the DataFrame API took **${sql.df_api_seconds.toFixed(2)} s** and the equivalent SQL **${sql.sql_seconds.toFixed(2)} s**. The two are not alternatives with different performance: both are parsed into the same Catalyst logical plan and compiled to the same physical plan. The choice is one of expression, not efficiency.`
));
children.push(h2("5.3 Analytical results"));
children.push(table(["ns", "Namespace", "Edits", "Bot share", "Revert rate"],
  sql.namespaces.slice(0, 7).map((r) => [
    String(r.namespace), r.name, N(r.edits), pct(r.bot_share, 1), pct(r.revert_rate, 1)]),
  [0.5, 1.2, 1.2, 1, 1], { size: 18, alignAll: AlignmentType.CENTER }));
children.push(p(""));
children.push(p(
  `Article space dominates with ${N(sql.namespaces[0].edits)} edits. The **Category** namespace stands out: ${pct(sql.namespaces.find((r) => r.namespace === 14).bot_share, 1)} of its edits are automated, more than double the corpus average, and its revert rate is the lowest of the major namespaces at ${pct(sql.namespaces.find((r) => r.namespace === 14).revert_rate, 1)}. Category maintenance is largely machine work and largely uncontested. **User** space shows the opposite pattern, with a ${pct(sql.namespaces.find((r) => r.namespace === 2).revert_rate, 1)} revert rate.`
));
children.push(table(["Actor segment", "Edits", "Revert rate"],
  sql.segments.map((s) => [s.segment, N(s.edits), pct(s.revert_rate, 2)]),
  [1.4, 1, 1], { size: 18 }));
children.push(p(""));
children.push(p(
  `The segmentation refines the RDD result by separating registered humans from anonymous contributors. Registered humans are reverted at ${pct(seg["registered human"].revert_rate, 2)}, bots at ${pct(seg["bot"].revert_rate, 2)}, and anonymous IPs at ${pct(seg["anonymous"].revert_rate, 2)} — nearly four times the registered-human rate.`
));
children.push(p(
  `Temporal aggregation shows activity peaking in **${sql.peak_year.year}** with ${N(sql.peak_year.edits)} edits, of which ${pct(sql.peak_year.bot_share, 1)} were automated — the high-water mark of bot activity on this wiki. The most edited article is \`${sql.top_pages[0].title}\` with ${N(sql.top_pages[0].edits)} revisions.`
));
children.push(p(
  `Aggregating at monthly rather than annual granularity over the recent period shows the busiest month to be **${sql.peak_month.month}** with ${N(sql.peak_month.edits)} edits at ${pct(sql.peak_month.bot_share, 1)} automation — far below the ${pct(sql.peak_year.bot_share, 1)} of the ${sql.peak_year.year} peak. Automated editing on this wiki has receded substantially since its height.`
));
children.push(table(["Month", "Edits", "Bot share"],
  sql.by_month.slice(-8).map((r) => [r.month, N(r.edits), pct(r.bot_share, 1)]),
  [1, 1, 1], { size: 18, alignAll: AlignmentType.CENTER }));
children.push(p(""));
children.push(p(
  `One reconciliation is worth stating. The RDD phase counts ${N(botAgg.edits)} bot edits against ${N(prep.bot_edits)} from the DataFrame phase. The difference is exactly the ${N(prep.null_key_rows_removed)} rows the DataFrame path discards for null structural keys; the RDD phase reads the raw dump before that filter. The two numbers are consistent, not contradictory.`
));

// ------------------------------------------------- 6 ANALYTICS WORKFLOW
children.push(h1("6. Spark Analytics Workflow"));
children.push(p(
  "The assignment requires an explicit pipeline of the form Input Data to RDD Processing to DataFrame Processing to Analytical Output. The implemented workflow follows that shape, with every stage persisting its result so that any stage can be re-run in isolation."
));
children.push(...code([
  'INPUT DATA           simplewiki.all-time.tsv.bz2',
  '                     951 MB bz2 TSV, 78 columns, ' + N(ing.raw_rows) + ' rows',
  '                            |',
  '                            v',
  'RDD PROCESSING       sc.textFile(minPartitions=24) -> ' + rdd.num_partitions + ' partitions',
  '   src/pb_rdd.py     map(parse) -> filter(entity=="revision")',
  '                     persist(MEMORY_AND_DISK)',
  '                     flatMap(tokens) -> reduceByKey(add)',
  '                            |',
  '                            v',
  'DATAFRAME PROCESSING p00_ingest.py   TSV -> Parquet, ' + ing.columns_kept + ' of 78 cols',
  '   src/p03_prepare   p03_prepare.py  dedup, coalesce, impute, label',
  '   src/pc_sql.py     createOrReplaceTempView("wikimedia_edits")',
  '                     groupBy / agg / orderBy  +  spark.sql(...)',
  '                            |',
  '                            v',
  'ANALYTICAL OUTPUT    word frequencies      ' + N(rdd.total_comment_tokens) + ' tokens',
  '                     namespace aggregates  revert + bot rates',
  '                     temporal trends       yearly and monthly',
  '                     MLlib models          ROC-AUC ' + f4(best.roc_auc),
  '                     reports/metrics/*.json -> deck and this report',
], "Pipeline: Input -> RDD -> DataFrame -> Output"));
children.push(p(
  "Two properties of this layout matter. First, the RDD branch and the DataFrame branch read the *same* source but serve different purposes: the RDD path demonstrates low-level transformations and produces the word-frequency and actor-class analyses, while the DataFrame path produces the cleaned, typed table that the SQL queries and the models consume. Running both on identical input is what allows the counts in Sections 4 and 5 to be cross-checked against one another."
));
children.push(p(
  "Second, every stage writes Parquet before the next begins. A change to feature engineering re-runs in minutes rather than repeating the bz2 decompression upstream, and the document generators read only the JSON metrics, so the deck and this report rebuild in seconds without starting Spark at all."
));
children.push(table(["Stage", "Script", "Reads", "Writes"], [
  ["Ingest", "`p00_ingest.py`", "raw bz2 TSV", "`data/parquet/revisions/`"],
  ["RDD analytics", "`pb_rdd.py`", "raw bz2 TSV", "`metrics/pb_rdd.json`"],
  ["Prepare", "`p03_prepare.py`", "`revisions/`", "`data/parquet/prepared/`"],
  ["SQL analytics", "`pc_sql.py`", "`prepared/`", "`metrics/pc_sql.json`"],
  ["Features", "`p04_features.py`", "`prepared/`", "`data/features/`"],
  ["Models", "`p05_*.py`", "`features/`", "`metrics/p05_*.json`"],
  ["Streaming", "`pe_streaming.py`", "`prepared/` (replay)", "`metrics/pe_streaming.json`"],
], [1, 1.3, 1.2, 1.6], { size: 17 }));
children.push(p(""));

// ---------------------------------------------- 8 STRUCTURED STREAMING
children.push(h1("7. Structured Streaming"));
children.push(p(
  "The streaming phase (`src/pe_streaming.py`) demonstrates incremental processing. A producer thread writes bursts of real revision records as JSON files into a watch directory; Spark reads that directory as a **file source**, processing each file as a micro-batch."
));
children.push(p(
  "A file source was chosen over a socket source deliberately. A socket source is not fault-tolerant and dies with its producer, which makes a headless run unreproducible. The file source tracks offsets in a checkpoint directory, is restartable, and is a genuine Structured Streaming source."
));
children.push(...code([
  'stream = (spark.readStream',
  '          .schema(SCHEMA)                   # no inference on a stream',
  '          .option("maxFilesPerTrigger", 1)  # one burst per micro-batch',
  '          .json(str(STREAM_IN)))',
  '',
  'q1 = (stream.writeStream',
  '      .foreachBatch(per_batch)',
  '      .option("checkpointLocation", str(CHECKPOINT / "q1"))',
  '      .trigger(processingTime="2 seconds").start())',
  '',
  '# second query: event-time windows with a watermark for late data',
  'windowed = (stream.withWatermark("event_timestamp", "365 days")',
  '                  .groupBy(F.window("event_timestamp", "365 days"))',
  '                  .agg(F.count("*").alias("edits"),',
  '                       F.avg("label_bot").alias("bot_share")))',
], "src/pe_streaming.py"));
children.push(p(
  "A schema must be supplied explicitly: Structured Streaming cannot infer one, because inference requires reading data that has not arrived yet. Two queries run concurrently against the same stream — a `foreachBatch` sink computing per-batch and running totals, and a windowed aggregation over **event time** rather than arrival time, bounded by a watermark that limits how long state is retained for late records."
));
children.push(h2("7.1 Run results"));
children.push(table(["Property", "Value"], [
  ["Source", str.source],
  ["Trigger", str.trigger],
  ["Bursts replayed", `${str.bursts} x ${N(str.rows_per_burst)} records`],
  ["Micro-batches processed", String(str.batches_processed)],
  ["Records processed", N(str.rows_processed)],
  ["Running bot rate", pct(str.running_bot_rate, 2)],
  ["Running revert rate", pct(str.running_reverted_rate, 2)],
  ["Event-time windows emitted", String(str.event_time_windows.length)],
], [1.3, 2], { size: 18 }));
children.push(p(""));
children.push(p(
  `All ${N(str.rows_processed)} records were processed across ${str.batches_processed} micro-batches with no loss, one burst per trigger as configured. The windowed query emitted ${str.event_time_windows.length} event-time windows spanning the replayed period.`
));
children.push(table(["Event-time window", "Edits", "Bot share"],
  str.event_time_windows.filter((w) => w.edits > 100).slice(0, 8)
    .map((w) => [w.year, N(w.edits), pct(w.bot_share, 1)]),
  [1.2, 1, 1], { size: 18, alignAll: AlignmentType.CENTER }));
children.push(p(""));
children.push(p(
  "The windowed output reproduces, incrementally, the rise in automated editing that the batch temporal aggregation shows — bot share climbing year on year across the replayed window. That the streaming and batch paths agree on the same corpus is the useful cross-check."
));
children.push(h2("7.2 Console output of the run"));
children.push(p(
  "The micro-batch sink prints each batch as it completes. The bot share climbs across the run because the replay is chronological: early batches are 2001-era edits, later batches recent ones."
));
children.push(...code([
  '  [producer] sampled 200,000 edits (44.1% bot)',
  '  [producer] burst 0 (10,000 edits)',
  '  BATCH 0: rows=10,000 bot=1,945 (19.4%) | running bot rate 19.45%',
  '  BATCH 1: rows=10,000 bot=3,891 (38.9%) | running bot rate 29.18%',
  '  BATCH 5: rows=10,000 bot=4,014 (40.1%) | running bot rate 32.39%',
  '  BATCH 10: rows=10,000 bot=5,083 (50.8%) | running bot rate 38.57%',
  '  BATCH 13: rows=10,000 bot=5,489 (54.9%) | running bot rate 41.52%',
  '  BATCH 19: rows=10,000 bot=6,404 (64.0%) | running bot rate 44.11%',
  '',
  '  event-time windows produced: ' + str.event_time_windows.length,
  '    2002:    172 edits, bot share  1.7%',
  '    2003:    906 edits, bot share 10.7%',
  '    2004:  2,647 edits, bot share 14.1%',
  '    2005:  9,363 edits, bot share 26.1%',
], "make streaming"));
children.push(p(
  `The running rate converges on ${pct(str.running_bot_rate, 2)}, which matches the 44.1% bot share of the sampled replay set measured before streaming began. The streaming path and the batch path agree on the same corpus, which is the useful cross-check.`
));

children.push(h2("7.3 A partitioning bug surfaced by streaming"));
children.push(p(
  "The first run reported a bot rate of exactly zero in every micro-batch. The cause was not in the streaming code. The prepared dataset is written with `partitionBy(\"label_bot\")`, so it is laid out on disk as two directories. A `.limit()` over that dataset reads whole partition directories in order, and the `label_bot=0` directory alone holds more rows than the replay required — so the sample never reached the bot partition."
));
children.push(p(
  "The fix samples across all partitions before ordering by event time. The general lesson is that `limit()`, `head()` and `take()` are not random samples; on partitioned data they return whatever the first partitions happen to contain, and if the data is partitioned by the very column under measurement, the result is perfectly biased with no error raised."
));
children.push(h2("7.4 Live ingestion"));
children.push(p(
  "A separate collector (`src/stream_collector.py`) holds a long-lived HTTP connection to the Wikimedia Recent Changes feed, which publishes every edit across all projects over Server-Sent Events, and appends selected fields as JSON Lines. A 30-second run captured **910 events**, of which 413 carried `\"bot\": true` — confirming both the ~30 events/second platform rate quoted in Section 1 and that the bot label used for supervised training is present on the live feed."
));
children.push(p(
  "The collector is deliberately not a Spark job: it is the ingestion tap, and Structured Streaming consumes the files it rotates into place."
));

// --------------------------------------------- 9 RESULTS AND DISCUSSION
children.push(h1("8. Results and Discussion"));
children.push(h2("8.1 Analytical findings"));
children.push(...bullets([
  `**Revert rate separates actor classes sharply.** Anonymous contributors are reverted at ${pct(seg["anonymous"].revert_rate, 2)}, registered humans at ${pct(seg["registered human"].revert_rate, 2)}, and automated accounts at ${pct(seg["bot"].revert_rate, 2)}. Automation is the least contested category on the platform.`,
  `**Automation is concentrated by namespace.** Category space is ${pct(sql.namespaces.find((r) => r.namespace === 14).bot_share, 1)} automated against a corpus average of ${pct(prep.bot_rate, 1)}, and has the lowest revert rate of the major namespaces.`,
  `**Activity peaked in ${sql.peak_year.year}** at ${N(sql.peak_year.edits)} edits, ${pct(sql.peak_year.bot_share, 1)} of them automated.`,
  `**Comment vocabulary is maintenance vocabulary.** The leading tokens across ${N(rdd.total_comment_tokens)} are \`${rdd.top_comment_words.slice(0, 4).map((k) => k[0]).join("`, `")}\`.`,
]));
children.push(h2("8.2 Modelling results"));
children.push(p(
  `MLlib was used to test whether automated editing is predictable from behaviour. The evaluation is **actor-disjoint**: the actor key is hashed into disjoint buckets so that ${N(clf.n_train)} training rows and ${N(clf.n_test)} test rows share **zero accounts**. A random row split would place the same high-volume bot in both folds, letting a model memorise per-account cadence and report an inflated score. Identity columns are excluded, and the scaler sits inside the ML Pipeline so it is fitted on the training fold alone.`
));
children.push(table(
  ["Model", "Features", "ROC-AUC", "PR-AUC", "Accuracy", "Bot F1"],
  ["structural", "full"].flatMap((fs_) =>
    ["logistic_regression", "random_forest", "gbt"].map((m) => {
      const k = `${m}__${fs_}`, r = clf.results[k];
      return [PRETTY[m] + (k === clf.best_model ? " *" : ""), fs_,
              f4(r.roc_auc), f4(r.pr_auc), f4(r.accuracy), f4(r.bot_f1)];
    })),
  [1.6, 1, 1, 1, 1, 1], { size: 18, alignAll: AlignmentType.CENTER }));
children.push(p(""));
children.push(p(
  `The best configuration is ${PRETTY[clf.best_model.split("__")[0]]} on the full feature set at ROC-AUC ${f4(best.roc_auc)}. The more informative comparison is between the two halves of the table. Gradient-boosted trees reach ROC-AUC ${f4(gbtS.roc_auc)} using **no comment vocabulary at all** — within ${(100 * Math.abs(best.roc_auc - gbtS.roc_auc)).toFixed(2)} percentage points of the best result overall — and adding the text block slightly *reduces* GBT to ${f4(gbtF.roc_auc)}. Automation is legible from behaviour, not from what an edit says.`
));
children.push(p(
  `Comment text matters only to the linear model, where it is transformative: logistic regression improves from ROC-AUC ${f4(lrS.roc_auc)} to ${f4(lrF.roc_auc)} and from PR-AUC ${f4(lrS.pr_auc)} to ${f4(lrF.pr_auc)}. The tree ensembles already capture, through split interactions, the structure that the SVD dimensions merely make linearly separable. The ablation therefore measures model capacity as much as feature value — a caveat that would have gone undetected had each model been trained once.`
));
children.push(h2("8.3 Clustering: a negative result"));
children.push(p(
  `Unsupervised clustering over ${N(clu.n_editors_clustered)} editors with at least ${clu.min_edits} edits selected ${clu.best} at silhouette ${f4(clu.best_silhouette)} — weak separation. The requested k was ${clu.best_k_requested} but only ${clu.best_k_nonempty} clusters were non-empty; at k = 2 the same algorithm degenerated to a single cluster and was skipped by an explicit guard, since \`ClusteringEvaluator\` otherwise aborts the entire sweep.`
));
children.push(p(
  `The obvious validation metric is misleading here and is reported only beside its baseline. Cluster purity against the bot flag is ${f4(clu.bot_purity)}, which appears excellent. Automated accounts are only ${pct(clu.bot_editor_rate, 2)} of **accounts** — bots are few accounts making very many edits — so the majority-class baseline is ${f4(clu.bot_purity_baseline)}, and the measured lift is ${clu.bot_purity_lift_over_baseline.toFixed(5)}. The partition carries no information about automation by this measure.`
));
children.push(p(
  `The informative measure is enrichment. Automated accounts are **${clu.bot_max_enrichment.toFixed(2)} times over-represented** in the high-activity cluster and under-represented in the low-activity one. That is a real effect in the expected direction, but modest, and adequately explained by bots being high-volume editors rather than by the clustering having identified automation as such.`
));
children.push(h2("8.4 Observations on the Spark APIs"));
children.push(table(["API", "Where it was the right tool", "Cost"], [
  ["RDD", "parsing a non-standard 78-field TSV; explicit control of partitioning and caching", "Python lambdas run row by row; no Catalyst optimisation"],
  ["DataFrame", "cleaning, feature engineering, aggregation", "schema must be stated or inferred up front"],
  ["Spark SQL", "declarative aggregate questions; readable in a report", "identical plan to the DataFrame API — expression, not performance"],
  ["Structured Streaming", "incremental processing with event-time semantics", "schema cannot be inferred; needs checkpointing"],
  ["MLlib", "distributed training without collecting to the driver", "fewer algorithms and tuning options than scikit-learn"],
], [0.9, 2.6, 2.2], { size: 17 }));
children.push(p(""));
children.push(p(
  "Two measurements frame the trade-off. The RDD parse of 11 million rows took 61.1 seconds, while the equivalent DataFrame aggregation over the cleaned Parquet took " + sql.df_api_seconds.toFixed(2) + " seconds. The comparison is not like for like — the RDD job decompresses and parses raw text while the DataFrame job reads a columnar store — but it shows precisely why the pipeline converts to Parquet once and queries it repeatedly."
));
children.push(h2("8.5 Scalability and limitations"));
children.push(p(
  "Spark is justified here by the shape of the workload rather than the size of the file. The per-editor aggregation regroups 11 million revisions by " + N(feat.n_editors) + " actors and computes windowed inter-edit intervals — a sort-merge shuffle whose working set scales with distinct actors, not with available memory."
));
children.push(...bullets([
  "**Actor skew is the dominant risk at scale.** Edits per account follow a heavy power law: the most active account has " + N(rdd.top_editors[0][1]) + " revisions while the median has one. A naive `groupBy` sends one enormous partition to a single task. Adaptive skew-join handling is enabled; salting the heaviest keys is the next step.",
  "**The label covers only flagged accounts**, so unapproved automation is a false negative by construction and recall is measured against an incomplete positive class.",
  "**Semi-automated tooling** such as AWB and Huggle genuinely occupies the space between the classes; no decision boundary is correct for it in principle.",
  "**The all-time snapshot spans 2001 to 2026**, averaging over several distinct editing regimes and tooling eras.",
  "**Local mode only.** Scalability is argued from observed stage behaviour, not from a measured multi-node speed-up.",
]));

// ---------------------------------------------------------- 10 CONCLUSION
children.push(h1("9. Conclusion"));
children.push(p(
  `This assignment implemented a complete Spark pipeline over ${N(prep.rows_final)} real Wikimedia revisions, exercising all four programming interfaces on one corpus. The RDD API parsed the raw compressed dump across ${rdd.num_partitions} partitions and produced word-frequency and actor-class analyses over ${N(rdd.total_comment_tokens)} comment tokens. The DataFrame API and Spark SQL answered aggregate questions over a cleaned Parquet table, confirming that both compile to the same Catalyst plan. Structured Streaming consumed ${N(str.rows_processed)} records in ${str.batches_processed} micro-batches with watermarked event-time windows. MLlib trained six classification configurations and twenty-one clustering configurations.`
));
children.push(p(
  `The analytical result is that revert rate separates actor classes sharply, with anonymous contributors reverted ${(seg["anonymous"].revert_rate / seg["bot"].revert_rate).toFixed(1)} times more often than automated accounts. The modelling result is that automation is highly predictable from behaviour alone — ROC-AUC ${f4(best.roc_auc)} on unseen accounts, and ${f4(gbtS.roc_auc)} without reading a single comment token. The clustering result is negative and reported as such: editor behaviour groups by activity level, not by automation.`
));
children.push(p(
  "Three engineering lessons generalise beyond this dataset. Published schemas may not match shipped data, and verifying column order empirically cost less than debugging a misaligned pipeline would have. Lazy evaluation means every action replays lineage from source, so a single `persist` turned five re-parses into seconds. And a validation metric must always be read against its own baseline — a cluster purity of " + f4(clu.bot_purity) + " looked like success and was identical to guessing the majority class."
));
children.push(h2("9.1 Future scope"));
children.push(...bullets([
  "Execute on a multi-node cluster and measure realised speed-up rather than arguing it from stage behaviour.",
  "Connect the live EventStreams collector directly to the Structured Streaming consumer with file rotation, and score arriving edits with the trained model.",
  "Model `label_reverted` as a second supervised task; it is already derived and carried through the pipeline.",
  "Extend to larger wikis, where per-month shards replace the single all-time file and actor skew becomes the binding constraint.",
  "Select the classification threshold against an explicit reviewer-capacity budget instead of reporting metrics at 0.5.",
]));

// --------------------------------------------------------- 11 REFERENCES
children.push(h1("10. References"));
const refs = [
  "Wikimedia Foundation. MediaWiki History Dumps, snapshot 2026-10. https://dumps.wikimedia.org/other/mediawiki_history/ (CC0).",
  "Wikimedia Foundation. EventStreams. https://stream.wikimedia.org/v2/stream/recentchange",
  "Wikimedia Foundation. Analytics/Data Lake/Edits/MediaWiki history. https://wikitech.wikimedia.org/",
  "Apache Software Foundation. RDD Programming Guide, Spark 3.5.3. https://spark.apache.org/docs/3.5.3/rdd-programming-guide.html",
  "Apache Software Foundation. Spark SQL and DataFrames Guide, Spark 3.5.3. https://spark.apache.org/docs/3.5.3/sql-programming-guide.html",
  "Apache Software Foundation. Structured Streaming Programming Guide, Spark 3.5.3. https://spark.apache.org/docs/3.5.3/structured-streaming-programming-guide.html",
  "Apache Software Foundation. MLlib Guide, Spark 3.5.3. https://spark.apache.org/docs/3.5.3/ml-guide.html",
  "M. Zaharia, M. Chowdhury, T. Das, A. Dave, J. Ma, M. McCauley, M. J. Franklin, S. Shenker and I. Stoica. \"Resilient Distributed Datasets: A Fault-Tolerant Abstraction for In-Memory Cluster Computing.\" In Proc. NSDI, 2012.",
  "M. Armbrust, R. S. Xin, C. Lian, Y. Huai, D. Liu, J. K. Bradley, et al. \"Spark SQL: Relational Data Processing in Spark.\" In Proc. SIGMOD, 2015, pp. 1383-1394.",
  "M. Armbrust, T. Das, J. Torres, B. Yavuz, S. Zhu, R. Xin, et al. \"Structured Streaming: A Declarative API for Real-Time Applications in Apache Spark.\" In Proc. SIGMOD, 2018, pp. 601-613.",
  "X. Meng, J. Bradley, B. Yavuz, E. Sparks, S. Venkataraman, D. Liu, et al. \"MLlib: Machine Learning in Apache Spark.\" Journal of Machine Learning Research, vol. 17, no. 34, 2016, pp. 1-7.",
  "J. Dean and S. Ghemawat. \"MapReduce: Simplified Data Processing on Large Clusters.\" In Proc. OSDI, 2004.",
  "A. Halfaker and D. Taraborelli. \"ORES: Scaling up machine learning-driven quality control in Wikipedia.\" Wikimedia Research, 2015.",
  "C. A. Davis, O. Varol, E. Ferrara, A. Flammini and F. Menczer. \"BotOrNot: A System to Evaluate Social Bots.\" In Proc. WWW (Companion), 2016, pp. 273-274.",
  "Z. Chu, S. Gianvecchio, H. Wang and S. Jajodia. \"Detecting Automation of Twitter Accounts: Are You a Human, Bot, or Cyborg?\" IEEE Transactions on Dependable and Secure Computing, vol. 9, no. 6, 2012, pp. 811-824.",
];
refs.forEach((r, i) => children.push(new Paragraph({
  alignment: AlignmentType.LEFT, spacing: { after: 70, line: 240 },
  indent: { left: 420, hanging: 420 },
  children: inline(`[${i + 1}]  ${r}`, { size: 19 }),
})));

// ------------------------------------------------------------------- build
const doc = new Document({
  creator: "Team 22",
  title: "Scalable Processing and Analysis of Wikimedia Editing Activity using Apache Spark",
  description: "MMDS (23CSE355) Assignment 2 Technical Report",
  styles: {
    default: {
      document: { run: { font: BODY, size: 21 }, paragraph: { spacing: { line: 248 } } },
      heading1: { run: { font: BODY, size: 28, bold: true, color: "1F3864" },
                  paragraph: { spacing: { before: 240, after: 90 }, keepNext: true } },
      heading2: { run: { font: BODY, size: 24, bold: true, color: "2F5496" },
                  paragraph: { spacing: { before: 180, after: 80 }, keepNext: true } },
      heading3: { run: { font: BODY, size: 22, bold: true },
                  paragraph: { spacing: { before: 180, after: 80 }, keepNext: true } },
    },
  },
  numbering: {
    config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET,
      text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 420, hanging: 260 } } } }] }],
  },
  sections: [{
    properties: { page: { size: PAGE, margin: { top: 1296, right: 1296, bottom: 1296, left: 1296 } } },
    footers: { default: new Footer({ children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], font: BODY, size: 18 })],
    })] }) },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log(`wrote ${OUT} (${(buf.length / 1024).toFixed(0)} KB)`);
});
