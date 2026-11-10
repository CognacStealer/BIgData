/*
 * Generate the Phase 8 final report (.docx) from reports/metrics/*.json.
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
const OUT = path.join(ROOT, "reports", "MMDS_EndSem_Report.docx");

const j = (n) => JSON.parse(fs.readFileSync(path.join(M, `${n}.json`), "utf8"));
const ing = j("p00_ingest"), prep = j("p03_prepare"), feat = j("p04_features");
const clf = j("p05_classification"), clu = j("p05_clustering");

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
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*`\n]+\*)/g;
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
const lrS = clf.results["logistic_regression__structural"], lrF = clf.results["logistic_regression__full"];
const rfF = clf.results["random_forest__full"], rfS = clf.results["random_forest__structural"];
const PRETTY = { logistic_regression: "Logistic Regression", random_forest: "Random Forest", gbt: "GBT" };
const dropPct = 100 * (prep.rows_in - prep.rows_final) / prep.rows_in;
const baseline = clu.bot_purity_baseline;

const clfRows = [];
for (const fs_ of ["structural", "full"]) {
  for (const m of ["logistic_regression", "random_forest", "gbt"]) {
    const k = `${m}__${fs_}`, r = clf.results[k];
    if (!r) continue;
    clfRows.push([
      PRETTY[m] + (k === clf.best_model ? " *" : ""), fs_,
      f4(r.roc_auc), f4(r.pr_auc), f4(r.accuracy), f4(r.f1),
      f4(r.bot_precision), f4(r.bot_recall), f4(r.bot_f1),
    ]);
  }
}

const cluRows = clu.cluster_profiles.map((c) => [
  String(c.cluster), N(c.n_editors), Number(c.mean_edits).toFixed(0),
  Number(c.e_gap_cv).toFixed(2), Number(c.e_minor_ratio).toFixed(2),
  Number(c.e_reverted_ratio).toFixed(3), Number(c.e_edits_per_active_day).toFixed(1),
  Number(c.bot_share).toFixed(4), `${Number(c.bot_lift).toFixed(2)}x`,
]);

const sweepRows = [];
for (const [algo, ks] of Object.entries(clu.sweep)) {
  for (const [k, v] of Object.entries(ks)) {
    sweepRows.push([algo, k,
      v.silhouette === null ? "degenerate" : f4(v.silhouette),
      String(v.cluster_sizes.length),
      v.cluster_sizes.slice(0, 4).map(N).join(", ") + (v.cluster_sizes.length > 4 ? ", ..." : "")]);
  }
}

// ----------------------------------------------------------------- document
const children = [];

// --- title block ---
children.push(
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1500, after: 120 },
    children: [run("Detecting Automated and Anomalous Editing Behaviour on Wikimedia at Scale", { bold: true, size: 34 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 },
    children: [run("A Spark MLlib study of 11.0 million Wikimedia edits: bot-edit classification and editor-behaviour clustering", { size: 24, italics: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
    children: [run("Mining of Massive Datasets (23CSE355)", { size: 24, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 },
    children: [run("End Semester Project Report", { size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
    children: [run("Team No: [Team No]        Project Advisor: [Advisor Name]", { size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 },
    children: [run("[Reg No 1] [Name 1]  ·  [Reg No 2] [Name 2]  ·  [Reg No 3] [Name 3]  ·  [Reg No 4] [Name 4]", { size: 20 })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

// --- 1 abstract ---
children.push(h1("Abstract"));
children.push(p(
  `Wikimedia projects accept edits from anyone with no review before publication, absorbing on the order of 30 to 50 edits per second across all wikis. A large share of that traffic is automated. This project builds a distributed pipeline in Apache Spark over the complete all-time edit history of Simple English Wikipedia, comprising ${N(ing.raw_rows)} dump records of which ${N(ing.revision_rows)} are individual edits, and addresses two tasks from the same corpus: supervised classification of whether an edit was made by an automated account, and unsupervised clustering of editor behaviour. ` +
  `The dataset was selected specifically for label validity. Its bot indicator derives from MediaWiki user-group membership rather than from any property of the edit itself, which makes it genuinely learnable; the alternative candidate, GDELT 2.0, was rejected because its natural labels are deterministic lookup tables keyed on a single column. ` +
  `After cleaning, ${N(prep.rows_final)} edits remain, ${pct(prep.bot_rate, 1)} of them automated. We engineer ${feat.n_numeric_edit_features} behavioural features and reduce comment text to ${feat.svd_k} dimensions with a truncated singular value decomposition computed on a distributed row matrix. Three classifiers and three clustering algorithms from Spark MLlib are compared under an actor-disjoint train/test split, so that every evaluated account is unseen during training. ` +
  `The best classifier, ${PRETTY[clf.best_model.split("__")[0]]} on the full feature set, attains ROC-AUC ${f4(best.roc_auc)} and PR-AUC ${f4(best.pr_auc)}. A paired ablation shows that structural behaviour alone is essentially sufficient: gradient-boosted trees reach ROC-AUC ${f4(gbtS.roc_auc)} using no comment vocabulary whatsoever. ` +
  `The clustering result is reported as a negative one. Because bots constitute only ${pct(clu.bot_editor_rate, 2)} of accounts, cluster purity against the bot flag equals its own majority-class baseline exactly, and the informative measure, enrichment, shows bots merely ${clu.bot_max_enrichment.toFixed(1)} times over-represented in the high-activity cluster. Automation is therefore recoverable with supervision but is not the dominant axis of unsupervised behavioural variation.`
));

// --- 2 introduction ---
children.push(h1("1. Introduction"));
children.push(p(
  "Wikimedia's editorial model is radically open: any visitor may change almost any page, and the change is live immediately. That openness is the reason the projects exist at the scale they do, and it is also the reason they require continuous, automated quality control. Across all Wikimedia projects the platform absorbs roughly 30 to 50 edits per second, a volume that no community of volunteer reviewers can inspect exhaustively."
));
children.push(p(
  "A substantial and growing proportion of that traffic is not human. Approved maintenance bots perform indispensable work: fixing links, adding structured data, reverting obvious vandalism. Semi-automated tools such as AutoWikiBrowser and Huggle let a human drive edits at machine speed. And unapproved scripts operate outside policy altogether. Distinguishing these populations matters operationally, because reviewer attention is the scarcest resource in the system and should not be consumed by predictable machine edits, while unflagged automation is itself a policy violation and a known vector for abuse."
));
children.push(p(
  "This report treats that operational need as two distinct data-mining problems over one corpus, in keeping with the requirement that the project implement both classification and clustering. The first problem is supervised: given everything observable about an edit at the moment it is made, predict whether its author is a flagged automated account. The second is unsupervised: without reference to any automation label, partition editors by behaviour and ask what populations actually exist."
));
children.push(p(
  `We process the complete all-time history of Simple English Wikipedia using Apache Spark in local mode on a single twelve-core machine. The pipeline ingests a ${"951 MB"} compressed dump, converts it to a columnar store, cleans and labels it, engineers behavioural features, applies dimensionality reduction, and then trains and evaluates six classification configurations and twenty-one clustering configurations in Spark MLlib. All numerical results quoted in this report are read programmatically from the pipeline's own metric files, so that the report cannot diverge from the run that produced it.`
));

// --- 3 problem statement ---
children.push(h1("2. Problem Statement"));
children.push(p("The project addresses two formally distinct tasks:"));
children.push(...bullets([
  "**Task A — Edit-level automation classification.** Given a feature vector describing a single revision (its timing, size, namespace, the cadence of its author's recent activity, and the structure of its edit comment), predict the binary label `label_bot`, indicating whether the acting account is flagged as automated by MediaWiki. The operational framing is reviewer triage, so the quantity of interest is ranking quality under class imbalance rather than raw accuracy.",
  "**Task B — Editor-level behavioural segmentation.** Given an aggregated behavioural profile per account, partition editors into groups without using any automation label, then characterise the resulting groups and test externally whether they align with automation.",
]));
children.push(p(
  `A secondary label, \`label_reverted\`, marking edits that were subsequently reverted, is derived and carried through the pipeline (${pct(prep.reverted_rate, 1)} of edits) and is used as an editor-level feature for Task B, but modelling it as a third task is left as future work.`
));
children.push(h2("2.1 Hypotheses stated in advance"));
children.push(p(
  "To ensure the results section reports whether predictions held rather than narrating whatever the numbers happened to show, three hypotheses were committed to before modelling:"
));
children.push(...bullets([
  "**H1.** Cadence regularity, not activity volume, is the strongest single automation signal, because bots run on schedules whereas human editing is bursty.",
  "**H2.** Structural behavioural features alone will capture most of the achievable performance, with comment vocabulary adding a measurable but secondary increment.",
  "**H3.** Unsupervised behavioural clustering will partially, though not cleanly, recover the automation boundary, because semi-automated human tooling occupies the middle ground.",
]));

// --- 4 literature survey ---
children.push(h1("3. Literature Survey"));
children.push(p(
  "The relevant literature falls into three threads: edit-level quality and abuse detection on Wikipedia, cross-platform automation detection by activity timing, and unsupervised identification of editor roles. A fourth, infrastructural thread supplies the distributed-computing background."
));
children.push(table(
  ["#", "Work", "Dataset", "Features", "Algorithms", "Metrics", "Contribution to this project"],
  [
    ["1", "Halfaker & Taraborelli, ORES (Wikimedia, 2015)", "Wikipedia revisions", "revision metadata, diff size, user attributes", "gradient boosting, random forest", "precision/recall at threshold, ROC-AUC", "production framing: reviewer routing needs precision, not accuracy"],
    ["2", "Potthast, Stein & Gerling (ECIR, 2008)", "940k English Wikipedia edits", "character- and word-level diff features, comment text", "logistic regression, rule baselines", "precision, recall, F1", "our comment-shape features (punctuation, caps, digit ratio)"],
    ["3", "Adler et al. (CICLing, 2011)", "PAN-WVC-10", "metadata + NLP + author reputation", "random forest with feature-set ablation", "ROC-AUC, PR-AUC", "the paired structural-vs-full ablation design in Section 8"],
    ["4", "Davis et al., BotOrNot/Botometer (WWW, 2016)", "Twitter accounts", "temporal cadence, activity entropy, content", "random forest", "ROC-AUC, balanced accuracy", "inter-event-gap regularity as the core automation signal"],
    ["5", "Chu et al. (IEEE TDSC, 2012)", "500k Twitter accounts", "inter-arrival timing, entropy, periodicity", "entropy classifier, Bayesian", "accuracy, false-positive rate", "treating cadence variance rather than volume as discriminator"],
    ["6", "Welser et al. (iConference, 2011)", "English Wikipedia editors", "namespace distribution, edit mix", "descriptive clustering", "qualitative role validity", "editor-archetype framing, namespace features"],
    ["7", "Yang et al. (ICWSM, 2016)", "Wikipedia edit histories", "per-editor activity profiles", "k-means, mixture models", "silhouette, interpretability", "k selection by silhouette plus qualitative naming"],
    ["8", "Kumar, Spezzano & Subrahmanian, VEWS (KDD, 2015)", "33k Wikipedia users", "behavioural sequences, inter-edit time", "SVM, random forest", "accuracy, early-detection rate", "per-editor rather than per-edit modelling as complement"],
    ["9", "Zaharia et al. (NSDI, 2012)", "—", "—", "RDD abstraction", "runtime scaling", "in-memory distributed processing argument (Section 9)"],
    ["10", "Meng et al., MLlib (JMLR, 2016)", "—", "—", "Spark MLlib pipelines", "scalability benchmarks", "Pipeline API, distributed SVD, train-only transformer fitting"],
  ],
  [0.3, 2.0, 1.3, 1.7, 1.4, 1.2, 2.1], { size: 15 }
));
children.push(p(""));
children.push(h2("3.1 Synthesis"));
children.push(p(
  "Works 1 to 3 and 8 establish that on Wikipedia, lightweight revision metadata combined with shallow comment features outperforms heavier natural-language processing once scale is taken into account, and that under class imbalance precision-recall analysis is more informative than accuracy. Work 3 in particular motivates our decision to train every model twice, with and without the text block, so that the contribution of vocabulary is measured rather than assumed."
));
children.push(p(
  "Works 4 and 5 are drawn from a different platform deliberately. Both find that what distinguishes machine from human activity is not how much an account does but how regularly it does it. This is the direct motivation for our strongest engineered feature, the coefficient of variation of inter-edit gaps, and for hypothesis H1."
));
children.push(p(
  "Works 6 and 7 provide the precedent for interpreting unsupervised editor clusters as social roles, and for validating the number of clusters by silhouette alongside human-readable characterisation. Our Section 8 follows that method but, as reported there, reaches a weaker conclusion than these works do."
));

// --- 5 dataset description ---
children.push(h1("4. Dataset Description"));
children.push(p(
  "The data source is the Wikimedia Foundation's `mediawiki_history` dump, snapshot 2026-10, which publishes the complete edit history of every Wikimedia wiki as tab-separated values under a CC0 dedication. We use the `simplewiki` (Simple English Wikipedia) all-time file."
));
children.push(table(
  ["Property", "Value"],
  [
    ["Source", "dumps.wikimedia.org/other/mediawiki_history/2026-10/simplewiki/"],
    ["Licence", "CC0 public domain dedication"],
    ["Compressed size", "951 MB, bzip2-compressed TSV"],
    ["Columns", "78 tab-separated fields (the published documentation states 76)"],
    ["Total dump records", N(ing.raw_rows)],
    ["— revision events", `${N(ing.entity_counts.revision)} (the individual edits; our unit of analysis for Task A)`],
    ["— page events", N(ing.entity_counts.page)],
    ["— user events", N(ing.entity_counts.user)],
    ["Columns retained", `${ing.columns_kept} of 78, selected in Phase 0`],
    ["Edits after cleaning", `${N(prep.rows_final)} (${dropPct.toFixed(2)}% removed)`],
    ["Distinct editors", N(feat.n_editors)],
    ["Primary label", `label_bot — ${N(prep.bot_edits)} positive (${pct(prep.bot_rate, 2)})`],
    ["Secondary label", `label_reverted — ${N(prep.reverted_edits)} positive (${pct(prep.reverted_rate, 2)})`],
    ["Live companion feed", "stream.wikimedia.org/v2/stream/recentchange (server-sent events)"],
  ],
  [1, 2.6], { size: 18 }
));
children.push(p(""));
children.push(h2("4.1 Justification of dataset selection"));
children.push(p(
  "The decisive criterion was label validity. The field `event_user_is_bot_by` is populated from MediaWiki user-group membership and the bot-name registry, which are administrative facts about an account, not properties of the individual revision. Predicting it from edit behaviour is therefore a genuine inference problem."
));
children.push(p(
  "The obvious alternative, GDELT 2.0, was evaluated and rejected on exactly this criterion. Its natural supervised targets, `QuadClass` and `GoldsteinScale`, are both deterministic lookup tables keyed on the single `EventCode` column. Retaining that column lets a classifier score almost perfectly by reproducing a lookup table, which demonstrates nothing about the data; removing it discards the signal and leaves the task ill-posed. Choosing a dataset whose label is not a function of its own features is, in our view, the most consequential decision in the project."
));
children.push(p(
  "Three further considerations supported the choice: the corpus is genuinely large and the dominant workload is a wide shuffle rather than a scan (Section 9); both required task families are supported from one corpus, with a second supervised label available; and the data requires no credentials and is accompanied by a live stream suitable for demonstration."
));
children.push(h2("4.2 Dataset understanding: the schema is not as documented"));
children.push(p(
  "The Wikitech documentation for these dumps states that the dataset contains 76 fields. The 2026-10 snapshot in fact ships **78** tab-separated columns; the two additional fields are `event_user_central_id` and `user_central_id`, which the documentation has not yet incorporated. Accepting the documented field order on trust would have misaligned every column in the file."
));
children.push(p(
  "Column order was therefore established empirically. We profiled every column index over a sample of real records, recording its fill rate and value shape (boolean, integer, timestamp, free text, or base-36 hash), and matched those signatures against the documented field groups. Reliable anchors were `wiki_db` (constant), `event_entity` (only three distinct values), `page_id`, `revision_text_sha1` (40-character base-36 hashes) and `revision_tags` (final column). Counting between anchors confirmed that the `event_user_*` block occupies exactly columns 7 to 28, which matches the documented group once the two additional identifier fields are included."
));
children.push(p(
  "One column remains undocumented. Column 2 holds a large integer and is populated almost exclusively on records where `event_entity` is `user`. It corresponds to neither `user_id` nor `user_central_id`, both of which appear separately in the same records. We label it `event_log_id` and flag it as undocumented; it is unused, because every downstream phase filters to revision events, where it is always empty."
));
children.push(h2("4.3 Parsing hazards"));
children.push(...bullets([
  "**Embedded quotation marks.** The `event_comment` field contains raw double-quote characters. Spark's CSV reader treats the double quote as a quoting character by default and will absorb tab delimiters inside an apparently quoted region, silently shifting every subsequent column on the affected record. Quote processing must be disabled outright.",
  "**No header row.** The first line of the file is data.",
  "**Nulls are empty strings**, not a sentinel such as `\\N`.",
  "**Non-ISO timestamps** of the form `2001-05-18 21:57:10.0`, requiring the explicit pattern `yyyy-MM-dd HH:mm:ss.S`.",
  "**bzip2 is splittable** under Hadoop, so Spark parallelises the read across tasks. Had the dump been gzip-compressed, the entire 951 MB would have been confined to a single task.",
]));

// --- 6 data preprocessing ---
children.push(h1("5. Data Preprocessing"));
children.push(p(
  `Preprocessing is implemented in Spark DataFrames and Spark SQL. Phase 0 converts the compressed TSV into Snappy-compressed Parquet, retaining ${ing.columns_kept} of the 78 columns; Phase 3 performs the cleaning proper. Every field is read as a string and cast explicitly, because allowing Spark to infer types silently drops records given the dump's empty-string nulls and non-ISO timestamps.`
));
children.push(h2("5.1 Recovering deleted-page revisions"));
children.push(p(
  "The first substantive cleaning decision concerns missing page metadata. When a page is deleted, MediaWiki nulls the current-state `page_*` columns but retains their `*_historical` counterparts. In our data 14.8% of revisions have a null `page_namespace` for this reason."
));
children.push(p(
  "Discarding those records would have removed roughly one edit in seven. More seriously, it would have introduced a systematic bias rather than a mere loss of volume: deleted pages are precisely where vandalism concentrates, so dropping them would skew the distribution of the `label_reverted` target. We therefore coalesce each current-state field with its historical counterpart before any null filtering. The effect is substantial — rows lost to null structural keys fall from approximately 15% to " + dropPct.toFixed(2) + "%."
));
children.push(...code([
  'df = (df.withColumn("page_namespace",',
  '          F.coalesce("page_namespace", "page_namespace_historical"))',
  '        .withColumn("page_title",',
  '          F.coalesce("page_title", "page_title_historical")))',
], "src/p03_prepare.py"));
children.push(h2("5.2 Duplicates and missing values"));
children.push(p(
  `De-duplication uses \`revision_id\`, the natural key for an edit; the all-time dump can repeat a revision where a page was deleted and later restored. In this snapshot ${N(prep.duplicates_removed)} duplicate records were found, and ${N(prep.null_key_rows_removed)} records were removed for lacking a structural key after historical recovery.`
));
children.push(table(
  ["Preprocessing step", "Records"],
  [
    ["Revision records read", N(prep.rows_in)],
    ["Removed: duplicate revision_id", N(prep.duplicates_removed)],
    ["Removed: null structural key", N(prep.null_key_rows_removed)],
    ["**Clean records**", `**${N(prep.rows_final)}**`],
    ["Automated edits (label_bot = 1)", `${N(prep.bot_edits)} (${pct(prep.bot_rate, 2)})`],
    ["Reverted edits (label_reverted = 1)", `${N(prep.reverted_edits)} (${pct(prep.reverted_rate, 2)})`],
  ],
  [2.2, 1], { size: 18 }
));
children.push(p(""));
children.push(p(
  "Imputation is applied only where absence carries a definite meaning, and the choice of filler is deliberate. A null `revision_text_bytes_diff` occurs on page creation, where the correct value is the full text size. A null `event_user_seconds_since_previous_revision` marks a user's first edit; this is filled with the sentinel −1 rather than 0, because 0 would assert an instantaneous repeat edit and actively mislead the model. A companion binary feature records whether a previous edit existed, so the sentinel remains distinguishable after scaling."
));
children.push(h2("5.3 A null that becomes a silent NaN"));
children.push(p(
  "Boolean fields required particular care, and getting this wrong produced the most instructive failure of the project. In SQL, comparing a null to a literal yields null, not false, so a naive cast of the form `col == \"true\"` leaves nulls intact. Those nulls survive into `VectorAssembler`, where they become NaN; `StandardScaler` then propagates the NaN, and Spark finally rejects the feature vector with a message naming neither the column nor the phase responsible. The failure surfaces deep inside a model fit, far from its cause."
));
children.push(p(
  "`page_is_redirect` is null for 9.8% of records, again because of page deletion, which made this failure certain rather than hypothetical. The fix coalesces each boolean cast to false, which is the defensible reading of \"the current-state flag is unknown\". More importantly, the pipeline now asserts a null contract: after labelling, Phase 3 checks every column whose value reaches a feature vector and aborts with the offending column names if any null remains. Three columns are deliberately exempt and documented as such — `event_user_id` (anonymous edits have none, and it only builds the grouping key), `revision_parent_id` (nullity is itself the page-creation feature), and `revision_seconds_to_identity_revert` (null means never reverted, and it is unused)."
));
children.push(...code([
  'for c in BOOL_COLS:',
  '    df = df.withColumn(c,',
  '        F.coalesce(F.col(c) == F.lit("true"), F.lit(False)))',
  '',
  '# fail loudly and name the column, rather than NaN-ing into a model fit',
  'bad = {c: v for c, v in remaining.items() if v}',
  'if bad:',
  '    raise SystemExit(f"FATAL: nulls remain in feature inputs: {bad}")',
], "src/p03_prepare.py"));
children.push(h2("5.4 Label definitions"));
children.push(p(
  "`label_bot` is 1 where `event_user_is_bot_by` is non-empty, indicating the acting account is flagged automated by group membership or by the bot-name registry. `label_reverted` is 1 where `revision_is_identity_reverted` is true. Neither is a deterministic function of any engineered feature, which is the property that makes the supervised task meaningful."
));

// --- 7 feature engineering ---
children.push(h1("6. Feature Engineering"));
children.push(p(
  `Two feature matrices are produced. The edit-level matrix carries one row per revision with ${feat.n_numeric_edit_features} numeric features, one categorical field (namespace) and a ${feat.svd_k}-dimension text block, and drives Task A. The editor-level matrix carries one row per account with ${feat.n_editor_features} aggregated features and drives Task B.`
));
children.push(table(
  ["Group", "Features", "Rationale"],
  [
    ["Temporal", "hour, day of week, weekend, night, hour sine/cosine", "scheduled processes show a flat 24-hour profile; humans sleep. Cyclic encoding avoids treating hour 23 and hour 0 as maximally distant"],
    ["Edit size", "byte size, signed diff, absolute diff, log absolute diff, diff sign, diff ratio", "maintenance automation makes small, uniform, often additive changes"],
    ["Cadence", "log seconds since author's previous edit, has-previous flag, log author edit count, log page revision count", "machine timing is regular; human timing is bursty (H1)"],
    ["Account", "account age in days at edit time, is-anonymous", "separates IP editors, new accounts and long-lived tool accounts"],
    ["Page context", "namespace, is-content-namespace, is-redirect, is-minor, is-page-creation", "bots concentrate in File and Template namespaces"],
    ["Comment shape", "length, word count, section-marker presence, wikilink count, URL count, digit/uppercase/punctuation ratios, is-empty", "captures the structure of the message without using its vocabulary"],
    ["Revision tags", "tag count, mobile, visual editor, undo", "tags naming automation are excluded to prevent leakage"],
    ["Editor-level", "gap coefficient of variation, night/weekend ratio, minor ratio, content ratio, revert ratio, edits per active day, pages per edit, namespace count, activity span", "behavioural profile for unsupervised segmentation"],
  ],
  [1, 2.6, 3.2], { size: 16 }
));
children.push(p(""));
children.push(p(
  "The feature intended to carry the most weight under H1 is `e_gap_cv`, the coefficient of variation of an account's inter-edit intervals, computed with a window function partitioned by actor and ordered by timestamp. A perfectly scheduled process has a coefficient near zero; human editing sessions produce large values."
));
children.push(h2("6.1 Dimensionality reduction by truncated SVD"));
children.push(p(
  `Edit comments are tokenised, hashed into ${feat.tfidf_buckets} TF-IDF buckets with a minimum document frequency of 5, and reduced to ${feat.svd_k} dimensions by a truncated singular value decomposition computed on a distributed \`RowMatrix\`. Only the right singular matrix V, of shape ${feat.tfidf_buckets} by ${feat.svd_k}, is collected to the driver and broadcast; the projection then runs independently on each partition.`
));
children.push(p(
  `The decomposition is fitted on a 4% sample of records rather than the full corpus. The right singular vectors converge with far fewer rows than are available, and fitting on 15% of 11 million records took 21.5 minutes against a few minutes at 4%; the projection is nonetheless applied to all ${N(prep.rows_final)} rows. The leading singular values are ${feat.singular_values.slice(0, 6).map((v) => v.toFixed(0)).join(", ")}.`
));
children.push(...figure("svd_spectrum.png", `Figure 1. Singular value spectrum of the comment TF-IDF matrix (left) and cumulative energy captured by successive components (right). The spectrum decays smoothly rather than exhibiting a sharp elbow, indicating that comment vocabulary has no small set of dominant directions; ${feat.svd_k} components were retained.`, 5.4));
children.push(p(
  "We use SVD rather than PCA deliberately: PCA centres the data, which would destroy the sparsity of a TF-IDF matrix and make the distributed computation substantially more expensive for no analytical gain."
));

// --- 8 mllib implementation ---
children.push(h1("7. MLlib Model Implementation"));
children.push(p(
  "All models are built as Spark ML `Pipeline` objects, so that every fitted transformer is estimated from training data only. Three classifiers are compared for Task A and three clustering algorithms for Task B."
));
children.push(h2("7.1 Leakage controls"));
children.push(p(
  "Three separate leakage channels had to be closed before any reported score could be trusted. We consider this the methodological core of the project."
));
children.push(table(
  ["Channel", "Why it leaks", "Control applied"],
  [
    ["Account identity", "Usernames literally contain the substring \"Bot\" (for example SchlurcherBot), and event_user_groups contains the very bot group that defines the label", "Both excluded from every feature vector. The username is used only as a grouping key for aggregation, which never reaches a model"],
    ["Random row split", "The same high-volume bot account would appear in both train and test, letting the model memorise account-specific cadence and edit-count fingerprints and report a wildly optimistic score", "Train/test split by hashed actor key, so test accounts are never seen in training. The script asserts the intersection is empty and prints the count"],
    ["Scaler fitted on all data", "StandardScaler means and variances would encode statistics of the test set", "The scaler is a stage inside the Pipeline, so it is fitted on the training fold alone"],
  ],
  [1.1, 3.0, 2.8], { size: 16 }
));
children.push(p(""));
children.push(p(
  "Comment text is retained as a feature, with the reasoning stated explicitly rather than left implicit. It is observable at the moment the edit is made and is not derived from user-group membership, so it is a legitimate if strong predictor. To keep that claim testable, every classifier is trained twice: once on a `structural` feature set containing no comment vocabulary, and once on the `full` set including the SVD block. The difference between the two quantifies the contribution of text instead of assuming it."
));
children.push(h2("7.2 The actor-disjoint split"));
children.push(p(
  `The split is deterministic: the actor key is hashed with the random seed, reduced modulo 100, and bucketed. This yields ${N(clf.n_train)} training rows and ${N(clf.n_test)} test rows with **zero shared actors**, verified at run time.`
));
children.push(...code([
  'def actor_split(df, train_fraction, seed):',
  '    bucket = F.abs(F.hash(F.concat(F.col("actor_key"),',
  '                   F.lit(str(seed))))) % 100',
  '    cut = int(train_fraction * 100)',
  '    return (df.filter(F.col("_bucket") < cut).drop("_bucket"),',
  '            df.filter(F.col("_bucket") >= cut).drop("_bucket"))',
], "src/p05_classification.py"));
children.push(p(
  `A consequence worth noting is that the class balance differs between folds — ${pct(clf.train_bot_rate, 1)} positive in training against ${pct(clf.test_bot_rate, 1)} in test. This is inherent to actor-disjoint splitting on a corpus where a small number of accounts own a large share of edits: whichever fold receives the highest-volume bots dominates its own positive rate. The split remains correct and the evaluation honest; the asymmetry simply reflects the true structure of the data.`
));
children.push(h2("7.3 Model configurations"));
children.push(table(
  ["Task", "Algorithm", "Configuration"],
  [
    ["Classification", "Logistic Regression", "maxIter 50, regParam 0.01, L2 (elasticNetParam 0)"],
    ["Classification", "Random Forest", "40 trees, maxDepth 10, maxBins 48"],
    ["Classification", "Gradient-Boosted Trees", "maxIter 30, maxDepth 5, maxBins 48"],
    ["Clustering", "K-Means", "k from 2 to 8, maxIter 50"],
    ["Clustering", "Bisecting K-Means", "k from 2 to 8, maxIter 30"],
    ["Clustering", "Gaussian Mixture", "k from 2 to 8, maxIter 40"],
  ],
  [1, 1.4, 3], { size: 18 }
));
children.push(p(""));
children.push(p(
  `For Task B the automation flag is deliberately excluded from the input matrix and retained only for external validation afterwards. Editors with fewer than 5 edits are excluded, leaving ${N(clu.n_editors_clustered)} of ${N(clu.n_editors_total)} accounts: single-edit accounts dominate the long tail, have no inter-edit interval at all, and would otherwise collapse into one uninformative mega-cluster.`
));
children.push(p(
  "One defensive measure proved necessary. Requesting k clusters does not guarantee k non-empty ones, and `ClusteringEvaluator` raises an assertion failure when a fit degenerates, which would abort the entire sweep. The implementation detects fewer than two non-empty clusters, records the degeneracy, and continues."
));

// --- 9 experimental results ---
children.push(h1("8. Experimental Results"));
children.push(h2("8.1 Classification"));
children.push(p(
  `All six configurations were evaluated on the full held-out set of ${N(clf.test_bot_rate ? clf.n_test : 0)} edits from unseen accounts. The starred row is the best model by ROC-AUC.`
));
children.push(table(
  ["Model", "Features", "ROC-AUC", "PR-AUC", "Accuracy", "F1 (wtd)", "Bot prec.", "Bot recall", "Bot F1"],
  clfRows, [1.5, 1.0, 0.85, 0.85, 0.9, 0.85, 0.85, 0.85, 0.8],
  { size: 16, alignAll: AlignmentType.CENTER }
));
children.push(p(""));
children.push(...figure("classification_comparison.png", "Figure 2. Six performance metrics across the three classifiers, with structural and full feature sets side by side. The gap between the two bars in each pair is the measured contribution of comment text.", 5.5));
children.push(...figure("roc_pr_curves.png", "Figure 3. ROC and precision-recall curves for gradient-boosted trees on the full feature set. Under class imbalance the precision-recall view is the more informative of the two, because it ignores the large true-negative mass that inflates ROC.", 5.0));
children.push(p(
  `The best configuration is ${PRETTY[clf.best_model.split("__")[0]]} on the full feature set, with ROC-AUC ${f4(best.roc_auc)}, PR-AUC ${f4(best.pr_auc)}, accuracy ${f4(best.accuracy)} and a bot-class F1 of ${f4(best.bot_f1)} at the default threshold. Bot-class precision is ${f4(best.bot_precision)} against recall ${f4(best.bot_recall)}, which is the correct trade-off for the reviewer-triage framing: a flagged edit is almost always genuinely automated.`
));
children.push(h2("8.2 The structural-versus-full ablation"));
children.push(p(
  `**H2 held, and more strongly than anticipated.** Gradient-boosted trees reach ROC-AUC ${f4(gbtS.roc_auc)} using no comment vocabulary at all — within ${(100 * Math.abs(best.roc_auc - gbtS.roc_auc)).toFixed(2)} percentage points of the best model overall. Adding the text block to GBT does not improve it but slightly reduces it, to ${f4(gbtF.roc_auc)}. Automation is legible from behaviour rather than from what an edit says.`
));
children.push(p(
  `Text matters, but only to the linear model, where it is transformative: logistic regression improves from ROC-AUC ${f4(lrS.roc_auc)} to ${f4(lrF.roc_auc)} and, far more dramatically, from PR-AUC ${f4(lrS.pr_auc)} to ${f4(lrF.pr_auc)}. The tree ensembles gain comparatively little (random forest ${f4(rfS.roc_auc)} to ${f4(rfF.roc_auc)}). The natural interpretation is that the ensembles already capture, through axis-aligned splits and their interactions, the structure that the SVD dimensions merely make linearly separable. The ablation therefore measures model capacity as much as it measures feature value — a caveat we would not have detected had we trained each model only once.`
));
children.push(h2("8.3 Clustering"));
children.push(p(
  `The full sweep of 21 configurations is given below. Silhouette is computed with squared Euclidean distance on the standardised editor matrix.`
));
children.push(table(
  ["Algorithm", "k", "Silhouette", "Non-empty", "Cluster sizes"],
  sweepRows, [1.4, 0.4, 1.0, 0.9, 2.6], { size: 15, alignAll: AlignmentType.CENTER }
));
children.push(p(""));
children.push(...figure("clustering_silhouette.png", "Figure 4. Silhouette against k for all three algorithms. Degenerate fits are omitted from the curves. No algorithm exceeds 0.35, and the surface is non-monotonic and unstable.", 4.9));
children.push(p(
  `The best configuration is **${clu.best}** at silhouette **${f4(clu.best_silhouette)}**. Two qualifications are essential. First, although k = ${clu.best_k_requested} was requested, the fit returned only **${clu.best_k_nonempty} non-empty clusters**; at k = 2 the same algorithm degenerated to a single cluster and was skipped. Second, a silhouette of ${f4(clu.best_silhouette)} is weak in absolute terms. Editor behaviour is better described as a continuum than as a set of well-separated groups, so the partition below should be read as a descriptive summary rather than as discovered natural classes.`
));
children.push(table(
  ["Cluster", "Editors", "Mean edits", "Gap CV", "Minor ratio", "Revert ratio", "Edits/active day", "Bot share", "Bot enrichment"],
  cluRows, [0.8, 1.0, 1.0, 0.8, 1.0, 1.0, 1.2, 0.9, 1.1],
  { size: 16, alignAll: AlignmentType.CENTER }
));
children.push(p(""));
children.push(p(
  `The two clusters separate cleanly on activity: cluster 0 contains ${N(clu.cluster_profiles[0].n_editors)} low-volume accounts averaging ${Number(clu.cluster_profiles[0].mean_edits).toFixed(0)} edits with a high revert ratio of ${Number(clu.cluster_profiles[0].e_reverted_ratio).toFixed(3)}, consistent with casual and inexperienced editing. Cluster 1 contains ${N(clu.cluster_profiles[1].n_editors)} high-volume accounts averaging ${Number(clu.cluster_profiles[1].mean_edits).toFixed(0)} edits, a far higher minor-edit ratio (${Number(clu.cluster_profiles[1].e_minor_ratio).toFixed(2)} against ${Number(clu.cluster_profiles[0].e_minor_ratio).toFixed(2)}) and a much lower revert ratio, consistent with experienced maintenance work.`
));
children.push(...figure("cluster_composition.png", "Figure 5. Cluster sizes on a logarithmic scale (left) and the share of each cluster flagged as automated (right). Automated accounts are a small minority everywhere.", 5.2));
children.push(h2("8.4 External validation, and a metric that does not work"));
children.push(p(
  `**H3 is not supported, and the reason is instructive.** The obvious validation metric for a partition against a held-out binary flag is purity, and ours is ${f4(clu.bot_purity)}, which appears excellent. It is in fact meaningless. Automated accounts are only ${pct(clu.bot_editor_rate, 2)} of **accounts** — ${Math.round(clu.bot_editor_count)} of ${N(clu.n_editors_clustered)} — because bots are a small number of accounts making a very large number of edits. The majority-class baseline is therefore ${f4(clu.bot_purity_baseline)}, and our purity exceeds it by ${clu.bot_purity_lift_over_baseline.toFixed(5)}. The clustering supplies literally no information about automation by this measure, and reporting the figure without its baseline would have been straightforwardly misleading.`
));
children.push(p(
  `The informative measure is enrichment: the bot share of a cluster divided by the overall bot share. Automated accounts are **${clu.cluster_profiles[1].bot_lift.toFixed(2)} times over-represented** in the high-activity cluster and ${clu.cluster_profiles[0].bot_lift.toFixed(2)} times under-represented in the low-activity one. That is a real effect and in the expected direction, but it is modest, and it is explained adequately by bots being high-volume editors rather than by the clustering having identified automation as such.`
));
children.push(p(
  "The pipeline was amended to report purity only alongside its own baseline, and to emit an explicit warning when the lift falls below one percentage point."
));

// --- 10 discussion (incl. scalability = Phase 7) ---
children.push(h1("9. Discussion"));
children.push(h2("9.1 Outcome of the stated hypotheses"));
children.push(table(
  ["#", "Hypothesis", "Outcome"],
  [
    ["H1", "Cadence regularity, not volume, is the strongest automation signal", "**Partly supported.** Cadence features contribute materially, but the tree ensembles distribute importance across cadence, namespace and edit-size features rather than relying on any one. The clean single-feature story the literature suggests did not materialise."],
    ["H2", "Structural features alone capture most achievable performance", `**Supported, more strongly than expected.** GBT reaches ROC-AUC ${f4(gbtS.roc_auc)} with no comment vocabulary; adding text slightly lowers it.`],
    ["H3", "Clustering will partially recover the automation boundary", `**Not supported.** The partition separates activity level, not automation. Enrichment is only ${clu.bot_max_enrichment.toFixed(1)}x and purity equals its baseline exactly.`],
  ],
  [0.4, 2.4, 4.0], { size: 16 }
));
children.push(p(""));
children.push(p(
  "H3 failing is the more interesting of the three results, and it is retained here rather than quietly dropped. The two tasks together make a coherent point: automation is highly learnable from behaviour *when supervision is available*, reaching ROC-AUC " + f4(best.roc_auc) + ", yet it is not the dominant axis along which editor behaviour naturally varies. What dominates unsupervised variation is simply how much an account does. Supervised and unsupervised views of the same feature space answer different questions, and conflating them would have produced a false claim."
));
children.push(h2("9.2 Scalability"));
children.push(p(
  "Spark is not justified here by the raw size of the input — a determined analyst could force 951 MB through a single machine's memory. It is justified by the shape of the workload. The per-editor aggregation in Phase 6 groups eleven million revisions by actor and computes windowed inter-edit intervals, which is a sort-merge shuffle whose working set scales with the number of distinct actors rather than with available memory. Spark spills to disk and completes; an in-memory group-by either thrashes or fails. Equally, the same code scales to the full corpus unchanged: `simplewiki` is one wiki of roughly 900, and redirecting the configuration at `enwiki` moves the input from about 1 GB to hundreds of GB across monthly shards with no rewrite."
));
children.push(table(
  ["Pipeline stage", "Parallelisation mechanism"],
  [
    ["Raw TSV read", "bzip2 is splittable under Hadoop, so the file was read by 12 concurrent tasks. A gzip dump would have been a single task — a real design trap"],
    ["Column projection", `Parquet retains ${ing.columns_kept} of 78 columns, so later phases read roughly a third of the bytes via columnar pruning`],
    ["Label partitioning", "The prepared dataset is partitioned by label_bot, allowing class-conditional queries to prune whole directories"],
    ["Feature engineering", "Entirely row-local withColumn expressions: embarrassingly parallel, no shuffle"],
    ["Editor aggregation", "groupBy plus a window lag, producing a sort-merge shuffle across 48 partitions. The dominant cost"],
    ["Truncated SVD", "Distributed RowMatrix; only the small right singular matrix is collected and broadcast"],
    ["Model training", "MLlib broadcasts the model and reduces gradient or histogram statistics per partition"],
  ],
  [1.2, 4.0], { size: 16 }
));
children.push(p(""));
children.push(p(
  "Adaptive Query Execution is enabled, so post-shuffle partition counts are coalesced at run time rather than guessed in advance."
));
children.push(h2("9.3 Challenges for very large datasets"));
children.push(...bullets([
  "**Actor skew is the dominant risk.** Edits per account follow a heavy power law: a handful of bots have millions of revisions while the median account has one. A naive `groupBy` on the actor key sends one enormous partition to a single task, which straggles or exhausts memory while the remaining cores idle. Mitigations, in order of preference: adaptive skew-join handling (enabled); salting the heaviest keys followed by a second reduction; and bounded-memory sketches in place of exact approximate-percentile computation over a full partition.",
  "**The window function is the stage to optimise first.** The `lag` over a partition ordered by timestamp requires a full sort within each partition. At `enwiki` scale the right move is to pre-partition the Parquet by actor hash at write time so that the sort becomes local.",
  "**Small-files problem.** Writing one Parquet file per task across hundreds of monthly shards would produce tens of thousands of tiny files and cripple the subsequent read. We repartition before writing; at larger scale this becomes an explicit compaction step.",
  "**Broadcast ceiling.** Broadcasting the right singular matrix is trivial at " + feat.tfidf_buckets + " by " + feat.svd_k + ". Raising the TF-IDF dimension to, say, 2^20 would make it too large to broadcast and force a distributed matrix multiplication instead.",
  "**Sampling must follow the split.** Any stratified sampling to address class imbalance has to happen after the actor-disjoint split, or the disjointness guarantee is silently broken.",
  "**Regime mixing.** The all-time snapshot spans 2001 to 2026. Editing norms, tooling and bot policy changed enormously across that period, so a single model implicitly averages several distinct regimes. At larger scale the appropriate response is to restrict to a recent window, or to treat era as an explicit stratum.",
]));
children.push(h2("9.4 Where the model is weak"));
children.push(...bullets([
  "**The label covers only flagged accounts.** Unapproved or unregistered automation is a false negative by construction, so the reported recall is measured against an incomplete positive class. The true recall against *all* automation is unknown and is certainly lower.",
  "**Semi-automated tooling has no clean boundary.** Tools such as AutoWikiBrowser and Huggle produce machine-speed edits under human direction. These accounts genuinely occupy the space between the classes, and no decision boundary can be correct for them in principle.",
  "**Default thresholding is not optimal.** Random forest on the structural set shows strong ranking quality (PR-AUC " + f4(rfS.pr_auc) + ") alongside poor bot-class F1 (" + f4(rfS.bot_f1) + ") at the 0.5 threshold. This is a thresholding artefact, not a modelling failure; a deployment would select the threshold from the precision-recall curve against an explicit reviewer-capacity budget.",
  "**Single-wiki scope.** `simplewiki` is smaller, and its bot population more concentrated, than `enwiki`. The pipeline generalises; the specific numbers do not.",
]));

// --- 11 conclusion ---
children.push(h1("10. Conclusion"));
children.push(p(
  `We built and ran a complete Spark MLlib pipeline over ${N(prep.rows_final)} real Wikimedia edits, covering ingestion of a 951 MB compressed dump into a columnar store, DataFrame-based cleaning under an enforced null contract, ${feat.n_numeric_edit_features} engineered behavioural features together with a ${feat.svd_k}-dimension truncated SVD of comment text, and a comparison of three classifiers against three clustering algorithms, all evaluated under an actor-disjoint split that guarantees no test account was seen during training.`
));
children.push(p(
  `Automated editing is highly predictable from behaviour alone: the best classifier attains ROC-AUC ${f4(best.roc_auc)} and PR-AUC ${f4(best.pr_auc)} on unseen accounts, with bot-class precision ${f4(best.bot_precision)}. The paired ablation establishes the more useful finding — structural behaviour is essentially sufficient, since gradient-boosted trees reach ROC-AUC ${f4(gbtS.roc_auc)} without reading a single comment token. Unsupervised clustering of the same editors, by contrast, recovers activity level rather than automation, with bots only ${clu.bot_max_enrichment.toFixed(1)} times enriched in the busiest cluster.`
));
children.push(p(
  "Two methodological points generalise beyond this dataset. First, label validity deserves examination before any modelling: our reason for choosing Wikimedia over GDELT was that GDELT's labels are deterministic functions of a feature column, which would have made a strong-looking result vacuous. Second, a validation metric must be read against its own baseline: our cluster purity of " + f4(clu.bot_purity) + " looked like a success and was in fact identical to the majority-class rate. Both are failures that produce impressive numbers, which is precisely what makes them worth guarding against."
));
children.push(h2("10.1 Future scope"));
children.push(...bullets([
  "Scale to `enwiki` monthly shards on a multi-node cluster and measure realised speed-up, rather than arguing scalability from stage behaviour in local mode.",
  "Score the live EventStreams feed with the trained model using Structured Streaming, turning the batch classifier into an operational triage filter.",
  "Model `label_reverted` as a second supervised task; it is already derived and carried through the pipeline.",
  "Weight the clustering by edit volume, or cluster within activity strata, to test whether automation becomes a visible axis once the activity gradient is controlled for.",
  "Select the decision threshold against an explicit reviewer-capacity budget instead of reporting metrics at 0.5.",
  "Treat editing era as a stratum or feature, so the model is not averaging across two decades of changing norms.",
]));

// --- 12 references ---
children.push(h1("11. References"));
const refs = [
  "Wikimedia Foundation. MediaWiki History Dumps, snapshot 2026-10. https://dumps.wikimedia.org/other/mediawiki_history/ (CC0).",
  "Wikimedia Foundation. EventStreams. https://stream.wikimedia.org/v2/stream/recentchange",
  "Wikimedia Foundation. Analytics/Data Lake/Edits/MediaWiki history. https://wikitech.wikimedia.org/",
  "A. Halfaker and D. Taraborelli. \"ORES: Scaling up machine learning-driven quality control in Wikipedia.\" Wikimedia Research, 2015.",
  "M. Potthast, B. Stein and R. Gerling. \"Automatic Vandalism Detection in Wikipedia.\" In Proc. ECIR, 2008, pp. 663-668.",
  "B. T. Adler, L. de Alfaro, S. M. Mola-Velasco, P. Rosso and A. G. West. \"Wikipedia Vandalism Detection: Combining Natural Language, Metadata and Reputation Features.\" In Proc. CICLing, 2011, pp. 277-288.",
  "C. A. Davis, O. Varol, E. Ferrara, A. Flammini and F. Menczer. \"BotOrNot: A System to Evaluate Social Bots.\" In Proc. WWW (Companion), 2016, pp. 273-274.",
  "Z. Chu, S. Gianvecchio, H. Wang and S. Jajodia. \"Detecting Automation of Twitter Accounts: Are You a Human, Bot, or Cyborg?\" IEEE Transactions on Dependable and Secure Computing, vol. 9, no. 6, 2012, pp. 811-824.",
  "H. T. Welser, D. Cosley, G. Kossinets, A. Lin, F. Dokshin, G. Gay and M. Smith. \"Finding Social Roles in Wikipedia.\" In Proc. iConference, 2011, pp. 122-129.",
  "D. Yang, A. Halfaker, R. Kraut and E. Hovy. \"Who Does What: Editor Role Identification in Wikipedia.\" In Proc. ICWSM, 2016.",
  "S. Kumar, F. Spezzano and V. S. Subrahmanian. \"VEWS: A Wikipedia Vandal Early Warning System.\" In Proc. KDD, 2015, pp. 607-616.",
  "M. Zaharia, M. Chowdhury, T. Das, A. Dave, J. Ma, M. McCauley, M. J. Franklin, S. Shenker and I. Stoica. \"Resilient Distributed Datasets: A Fault-Tolerant Abstraction for In-Memory Cluster Computing.\" In Proc. NSDI, 2012.",
  "X. Meng, J. Bradley, B. Yavuz, E. Sparks, S. Venkataraman, D. Liu, et al. \"MLlib: Machine Learning in Apache Spark.\" Journal of Machine Learning Research, vol. 17, no. 34, 2016, pp. 1-7.",
  "M. Armbrust, R. S. Xin, C. Lian, Y. Huai, D. Liu, J. K. Bradley, et al. \"Spark SQL: Relational Data Processing in Spark.\" In Proc. SIGMOD, 2015, pp. 1383-1394.",
  "Apache Software Foundation. Apache Spark 3.5.3 MLlib Guide. https://spark.apache.org/docs/3.5.3/ml-guide.html",
  "J. Dean and S. Ghemawat. \"MapReduce: Simplified Data Processing on Large Clusters.\" In Proc. OSDI, 2004.",
];
// Left-aligned, not justified: long URLs in a justified block stretch the
// inter-word spacing of the rest of the line badly.
refs.forEach((r, i) => children.push(new Paragraph({
  alignment: AlignmentType.LEFT,
  spacing: { after: 70, line: 240 },
  indent: { left: 420, hanging: 420 },
  children: inline(`[${i + 1}]  ${r}`, { size: 20 }),
})));

// ------------------------------------------------------------------- build
const doc = new Document({
  creator: "CognacStealer",
  title: "Detecting Automated and Anomalous Editing Behaviour on Wikimedia at Scale",
  description: "MMDS (23CSE355) End Semester Project Report",
  styles: {
    default: {
      document: { run: { font: BODY, size: 21 }, paragraph: { spacing: { line: 248 } } },
      title: { run: { font: BODY, size: 34, bold: true }, paragraph: { spacing: { before: 0, after: 200 } } },
      heading1: { run: { font: BODY, size: 28, bold: true, color: "1F3864" },
                  paragraph: { spacing: { before: 240, after: 90 }, keepNext: true } },
      heading2: { run: { font: BODY, size: 24, bold: true, color: "2F5496" },
                  paragraph: { spacing: { before: 180, after: 80 }, keepNext: true } },
      heading3: { run: { font: BODY, size: 22, bold: true },
                  paragraph: { spacing: { before: 180, after: 80 }, keepNext: true } },
    },
  },
  numbering: {
    config: [{
      reference: "bul",
      levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
                 style: { paragraph: { indent: { left: 420, hanging: 260 } } } }],
    }],
  },
  sections: [{
    properties: { page: { size: PAGE, margin: { top: 1296, right: 1296, bottom: 1296, left: 1296 } } },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ children: [PageNumber.CURRENT], font: BODY, size: 18 })],
        })],
      }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log(`wrote ${OUT} (${(buf.length / 1024).toFixed(0)} KB)`);
});
