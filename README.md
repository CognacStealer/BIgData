# Detecting Automated and Anomalous Editing Behaviour on Wikimedia at Scale

**Mining of Massive Datasets — End Semester Project (30 marks)**

A PySpark / MLlib pipeline over the complete edit history of a Wikimedia project
(11.0 million edits) that does the two things the rubric requires from a single
corpus:

- **Classification** — predict whether an edit was made by an automated (bot)
  account, from edit behaviour alone.
- **Clustering** — discover editor behavioural archetypes *without* using the
  bot flag, then test whether those clusters recover the automation boundary.

---

## 1. Why this dataset

The project needs a label that is genuinely *learnable*. Wikimedia's
`event_user_is_bot_by` is derived from MediaWiki **user-group membership and the
bot-name registry** — administrative facts about an *account*, not properties of
the individual edit. Predicting it from edit behaviour is therefore real
inference.

We evaluated and rejected the obvious alternative, **GDELT 2.0**. Its natural
labels (`QuadClass`, `GoldsteinScale`) are *deterministic lookup tables keyed on
`EventCode`*: keep that column and the classifier just reproduces a lookup table;
drop it and the task becomes ill-posed. Full argument in
[docs/leakage.md](docs/leakage.md). This is the project's main differentiator —
most submissions never interrogate whether their label is valid.

## 2. Dataset

| Property | Value |
|---|---|
| Source | Wikimedia `mediawiki_history` dumps, snapshot `2026-10` |
| Wiki | `simplewiki` (Simple English Wikipedia), complete all-time history |
| Download | 951 MB bz2 TSV |
| Raw rows | **15,201,370** |
| Edit (revision) rows | **11,023,987** |
| After cleaning | **10,987,077** (0.34% dropped) |
| Columns | 78 (the official docs say 76 — see below); **31 retained** |
| Distinct editors | **780,867** (108,954 with ≥5 edits, used for clustering) |
| Labels | 23.7% bot edits; 14.1% reverted edits |
| Licence | CC0 |
| Live feed | `stream.wikimedia.org/v2/stream/recentchange` (SSE) — verified live at ~30 events/sec |

## 3. Quick start

```bash
source env.sh
make help
```

Download the data and run everything:

```bash
make data/raw/simplewiki.all-time.tsv.bz2
make all
```

Check the whole pipeline in ~2 minutes on a tiny slice of the real dump first:

```bash
make smoke
```

### Phase targets

| Command | Script | Rubric phase |
|---|---|---|
| `make ingest` | `src/p00_ingest.py` | infrastructure: bz2 TSV → Parquet |
| `make prepare` | `src/p03_prepare.py` | **Phase 3** cleaning, dedup, imputation, labels |
| `make features` | `src/p04_features.py` | **Phase 4** feature engineering + TF-IDF/SVD |
| `make classify` | `src/p05_classification.py` | **Phase 5a + 6** LR / RF / GBT |
| `make cluster` | `src/p05_clustering.py` | **Phase 5b + 6** KMeans / Bisecting / GMM |
| `make figures` | `src/p06_report.py` | **Phase 6** figures and comparison tables |
| `make stream` | `src/stream_collector.py` | live demo collector |
| `make ppt` | `src/make_ppt.py` | build the 23-slide presentation |
| `make report` | `src/make_report.js` | build the 15-page report (.docx) |

Outputs: `reports/metrics/*.json|csv` and `reports/figures/*.png`.

## Results

Run on the full corpus: **10,987,077 edits**, 23.7% bot,
14.1% reverted. Split is **actor-disjoint**
(8,619,472 train / 2,367,605 test rows, **0 shared actors**),
so every test account is unseen in training.

### Classification — `label_bot`

| Model | Features | ROC-AUC | PR-AUC | Accuracy | Bot precision | Bot recall | Bot F1 |
|---|---|---|---|---|---|---|---|
| Logistic Regression | `structural` | 0.9114 | 0.6792 | 0.8489 | 0.5375 | 0.6840 | 0.6020 |
| Random Forest | `structural` | 0.9713 | 0.8948 | 0.9219 | 0.9522 | 0.5605 | 0.7057 |
| GBT | `structural` | 0.9756 | 0.9098 | 0.9564 | 0.8648 | 0.8760 | 0.8703 |
| Logistic Regression | `full` | 0.9512 | 0.9122 | 0.9605 | 0.9348 | 0.8207 | 0.8741 |
| Random Forest **★** | `full` | 0.9759 | 0.9326 | 0.9667 | 0.9806 | 0.8171 | 0.8914 |
| GBT | `full` | 0.9655 | 0.9144 | 0.9609 | 0.9356 | 0.8229 | 0.8756 |

**Best: Random Forest on the full feature set, ROC-AUC 0.9759.**

Two findings worth stating plainly:

- **Structural behaviour alone is essentially sufficient.** GBT reaches ROC-AUC
  0.9756 with *no comment vocabulary at all* — and adding the text block
  slightly *lowers* it (0.9655). Automation is legible from behaviour, not from
  what the edit says. The hypothesis stated in Phase 1 held.
- **Text only rescues the linear model** (ROC-AUC 0.9114 → 0.9512, PR-AUC
  0.6792 → 0.9122). The tree ensembles already capture the non-linear
  interactions that the SVD dimensions merely expose to a linear boundary, so
  this ablation measures model capacity as much as feature value.

Accuracy is the least informative metric here. At a 24/76 class split a model
can look strong on accuracy while ranking poorly, which is why PR-AUC and
per-class bot-F1 are reported alongside it.

### Clustering — editor archetypes

Best: **bisecting_kmeans_k3** (silhouette **0.3406**) over
108,954 editors with ≥5 edits. Note it
returned **2 non-empty clusters from
3 requested**; at k=2 the fit degenerated to a single
cluster and was skipped.

| Cluster | Editors | Mean edits | Gap CV | Minor ratio | Revert ratio | Edits/active day | Bot share | Bot enrichment |
|---|---|---|---|---|---|---|---|---|
| 0 | 82,951 | 12 | 1.73 | 0.03 | 0.396 | 7.1 | 0.0007 | 0.19× |
| 1 | 26,003 | 344 | 3.66 | 0.21 | 0.166 | 10.5 | 0.0132 | 3.58× |

**This is a negative result, and it is reported as one.** Only
**0.37% of *accounts*** are bots — they are few
accounts making very many edits. Cluster purity (0.9963)
therefore equals the majority-class baseline (0.9963)
*exactly* — a lift of +0.00000. Purity carries
no information here, and quoting it as validation would be misleading.

The informative measure is **enrichment**: bots are
**3.6× over-represented** in the high-activity
cluster. Real, but modest. The Phase 1 hypothesis that clustering would partially
recover the automation boundary is **not supported** — the clusters separate
*activity level*, not automation. Silhouette this low also says editor behaviour
is a continuum rather than a set of tidy groups, so the partition is a
descriptive summary, not a set of discovered natural classes.

### Artefacts

| File | Contents |
|---|---|
| `reports/MMDS_EndSem_Report.docx` | 15-page final report (Phase 8), generated from the metrics by `src/make_report.js` |
| `reports/MMDS_EndSem_Report.pdf` | the same report as PDF |
| `reports/MMDS_EndSem_Wikimedia_Bot_Detection.pptx` | 23-slide presentation, generated from the metrics by `src/make_ppt.py` |
| `reports/metrics/*.json` | per-phase metrics, including the full sweep |
| `reports/metrics/classification_comparison.csv` | the table above |
| `reports/metrics/cluster_profiles.csv` | per-cluster feature means |
| `reports/figures/*.png` | 5 figures: SVD spectrum, model comparison, ROC/PR, silhouette sweep, cluster composition |

## 4. Repository layout

```
BIgData/
├── env.sh                     # source this first (JAVA_HOME, PYSPARK_PYTHON)
├── Makefile                   # phase shortcuts
├── requirements.txt
├── src/
│   ├── config.py              # all paths, Spark tuning, model hyper-parameters
│   ├── schema.py              # the 78-column dump schema, verified empirically
│   ├── spark_utils.py         # session factory, timing, metric writing
│   ├── p00_ingest.py          # TSV -> Parquet
│   ├── p03_prepare.py         # Phase 3
│   ├── p04_features.py        # Phase 4
│   ├── p05_classification.py  # Phase 5a + 6
│   ├── p05_clustering.py      # Phase 5b + 6
│   ├── p06_report.py          # Phase 6
│   ├── stream_collector.py    # live EventStreams demo
│   └── run_all.py             # orchestrator
├── tests/smoke_test.py        # full pipeline on a tiny real-data fixture
├── docs/                      # see table below
├── data/                      # raw, parquet, features (git-ignored)
└── reports/figures|metrics/   # generated artefacts
```

## 5. Documentation

| Document | Covers |
|---|---|
| [docs/phase1_problem_definition.md](docs/phase1_problem_definition.md) | **Phase 1**: problem, dataset, justification, expected outcomes, stated hypotheses |
| [docs/literature_survey.md](docs/literature_survey.md) | **Phase 2**: comparative table of 10 works, grouped into three threads |
| [docs/schema_notes.md](docs/schema_notes.md) | dataset understanding: the 78-vs-76 column discrepancy and how order was verified |
| [docs/leakage.md](docs/leakage.md) | leakage controls, actor-disjoint split, the GDELT argument |
| [docs/scalability.md](docs/scalability.md) | **Phase 7**: shuffles, actor skew, small files, broadcast limits |
| [docs/report_outline.md](docs/report_outline.md) | **Phase 8**: report skeleton + PPT outline, each section mapped to an artefact |
| [docs/environment.md](docs/environment.md) | reproducibility: JDK/Python versions and two version traps |

## 6. Design decisions worth defending in the viva

1. **Actor-disjoint train/test split.** A random row split would put the same bot
   account in both train and test; the model could memorise per-account
   fingerprints (cadence, edit count) and report a wildly inflated score. We hash
   `actor_key` into disjoint buckets, so test accounts are **never seen in
   training**. The script asserts the intersection is empty and prints it.
2. **Every model trained twice** — `structural` (no comment vocabulary) vs
   `full` (+ 24-dim comment SVD) — so the contribution of text is *measured*,
   not assumed.
3. **Scaler fitted inside the Pipeline**, hence on the training fold only.
   Fitting it on the full dataset before splitting is a classic subtle leak.
4. **The bot flag is excluded from clustering inputs** and used only afterwards
   as external validation.
5. **Quote parsing disabled on the TSV read.** `event_comment` contains raw `"`
   characters; with default CSV quoting Spark absorbs tab delimiters inside an
   apparently-quoted region and silently shifts every later column.

## 7. Problems found and fixed along the way

These are documented because they are the substance of the engineering work, and
each one would have quietly corrupted the results.

| # | Problem | Fix |
|---|---|---|
| 1 | **The published schema is wrong.** Docs say 76 fields; the snapshot ships 78. Column order taken on trust would misalign every field. | Verified all 78 positions empirically by profiling fill-rate and value shape per index; anchored on `event_entity`, `page_id`, `revision_text_sha1`. See `docs/schema_notes.md`. |
| 2 | **Deleted-page bias.** 14.8% of revisions have NULL `page_namespace` because the page was later deleted. Dropping them loses 15% of data — and deleted pages are exactly where vandalism concentrates, so it would bias `label_reverted`. | Coalesce from the `*_historical` columns, which survive deletion. Row loss fell from ~15% to **0.34%**. |
| 3 | **NULL booleans became NaN.** `NULL == "true"` is NULL in SQL, so nulls survived the cast, became NaN in `VectorAssembler`, and `StandardScaler` propagated NaN until Spark rejected the vector — failing deep inside a model fit with no hint of the culprit column. | Coalesce boolean casts to `False`, plus an explicit **null guard** in Phase 3 that fails loudly and names the offending columns. |
| 4 | **`pandas_udf` cannot accept `VectorUDT` input.** The vectorised SVD projection received `str` and crashed (`'str' object has no attribute 'indices'`). Spark's Arrow path has no UDT support here. | Reverted to a plain UDF but with a single numpy gather + dot per row instead of a nested Python loop. Densifying 2048 columns to vectorise would cost far more than it saves. |
| 5 | **SVD fit took 21.5 minutes.** `computeSVD` was running over 15% of 11M rows. | The right singular vectors converge with far fewer rows; sample 4% and materialise it first so the tokenize→hash→IDF chain isn't recomputed. |
| 6 | **`VectorAssembler` can't size a UDF output.** `Can not infer column lengths with handleInvalid="keep"`. | Declare the width with `VectorSizeHint`. |
| 7 | **Degenerate clustering.** Asking for *k* clusters doesn't guarantee *k* **non-empty** ones; `ClusteringEvaluator` then aborts the whole sweep. | Detect `<2` non-empty clusters, record the degeneracy, and continue the sweep. |
| 8 | **Phase 0 decompressed the 951 MB bz2 four times** — once per action (`count`, `distinct`, `groupBy`, `write`). | One grouped aggregate yields row total, entity breakdown and the wiki sanity check together. Four passes → two. |
| 9 | **Block-buffered logs.** Progress was invisible until a process exited. | Line-buffered stdout in `spark_utils`, `python -u` in the orchestrator. |

## 8. Environment

Built on Ubuntu 26.04 **without root**: both the JDK and Python live in the
user's home directory.

| Component | Version | Note |
|---|---|---|
| OpenJDK | Temurin 17.0.21 (`~/.local/jdk`) | installed from the Adoptium API, since `apt` needs sudo |
| Python | 3.11.18 (via `uv`) | **not** system 3.14, **not** 3.12 |
| PySpark | 3.5.3 | `local[*]`, 12 cores / 15 GB |

Two traps, both covered in [docs/environment.md](docs/environment.md):

- `PYSPARK_PYTHON` **must** be pinned, or workers pick up system Python 3.14 and
  Spark dies at *task* time with `PYTHON_VERSION_MISMATCH`.
- **PySpark 3.5 cannot run on Python 3.12** — `pyspark/ml/image.py` imports the
  removed `distutils`. Python 3.12 support arrived in Spark 4.0.

## 9. Known limitations

Stated plainly, because they are the obvious viva questions:

- **The label only covers *flagged* accounts.** Unapproved bots are false
  negatives by construction, so recall is measured against an incomplete
  positive class.
- **Semi-automated human tooling** (AWB, Huggle) genuinely sits between the
  classes; no clean decision boundary exists there.
- **The all-time snapshot spans 2001–2026.** Editing norms and tooling changed
  enormously; a single model implicitly averages over several distinct regimes.
- **One wiki.** `simplewiki` is not representative of `enwiki`; the pipeline
  scales unchanged, but the *findings* are specific to this project.
- **Default 0.5 threshold is wrong under imbalance.** Random Forest shows strong
  ranking quality (high PR-AUC) with poor F1 at 0.5, which is a thresholding
  artefact rather than a modelling failure — see the results discussion.
