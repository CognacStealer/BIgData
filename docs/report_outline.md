# Phase 8: Final Report

> **The report is written.** It is generated from `reports/metrics/*.json` by
> `src/make_report.js` (`make report`) and lives at
> `reports/MMDS_EndSem_Report.docx` (plus a rendered `.pdf`) — **15 pages**,
> inside the recommended range. Regenerate it after any pipeline re-run so the
> numbers stay in step.
>
> The outline below is kept as the section-to-artefact map, which is still the
> useful part if you edit the document by hand.

## Outline (10–15 pages)

Each section names the artefact that supplies its numbers, so nothing has to be
invented at writing time.

| § | Section | Length | Source artefact |
|---|---|---|---|
| — | **Abstract** | ~200 words | write last; pull headline numbers from `reports/metrics/summary.json` |
| 1 | **Introduction** | 1 p | platform-integrity motivation; scale of Wikimedia editing |
| 2 | **Problem Statement** | 0.5 p | two tasks: per-edit automation classification, per-editor archetype discovery |
| 3 | **Literature Survey** | 2 p | `docs/literature_survey.md` — present as three threads, not row-by-row |
| 4 | **Dataset Description** | 1.5 p | `docs/schema_notes.md`, `reports/metrics/p00_ingest.json` (row counts, entity breakdown) |
| 5 | **Data Preprocessing** | 1.5 p | `reports/metrics/p03_prepare.json` (dedup counts, null table, label rates) |
| 6 | **Feature Engineering** | 2 p | `reports/metrics/p04_features.json`, figure `svd_spectrum.png` |
| 7 | **MLlib Model Implementation** | 1.5 p | pipeline stage diagram; `docs/leakage.md` for the split design |
| 8 | **Experimental Results** | 2.5 p | `classification_comparison.csv/.png`, `roc_pr_curves.png`, `clustering_silhouette.png`, `cluster_profiles.csv`, `cluster_composition.png` |
| 9 | **Discussion** | 1.5 p | structural-vs-full ablation; what the clusters mean; where the model fails |
| 10 | **Conclusion** | 0.5 p | |
| 11 | **References** | 0.5 p | literature table + Spark/MLlib papers |

## Writing guidance per section

**§4 Dataset Description.** Lead with the 78-vs-76 column discrepancy and how
you resolved it empirically. This is the single most credible paragraph in the
report because it shows you validated the source instead of trusting a wiki page.

**§5 Data Preprocessing.** Report the null table honestly, including the fields
where "missing" carries meaning (first-edit cadence, page-creation byte diff) and
explain the `-1` sentinel choice over `0`.

**§8 Experimental Results.** Present the structural and full feature sets side by
side for all three classifiers — that is six numbers per metric, and the gap
between the two columns is the interesting finding. For clustering, the silhouette
sweep justifies k, but the **cluster profile table is the real result**: name each
cluster in words (e.g. "metronomic high-volume bots", "burst-mode semi-automated
tools", "casual anonymous editors", "deep-dive article authors") and support each
name with the two or three features that distinguish it.

**§9 Discussion.** Say plainly where the model is weak. Likely candidates:
semi-automated human tooling (AWB, Huggle) sits between the classes; unflagged
bots are false negatives *by construction* since the label only covers flagged
accounts; and the all-time snapshot averages over two decades of changing editing
norms.

## Presentation (PPT)

The report carries no marks, the presentation does. Suggested 10–12 slides:

1. Problem and why Wikimedia (1 slide)
2. **Why not GDELT** — the deterministic-label argument (1 slide; this is your
   differentiator, most teams will not have thought about label validity)
3. Dataset and the schema-verification finding (1)
4. Pipeline architecture diagram (1)
5. Feature engineering, highlighting `e_gap_cv` cadence intuition (1–2)
6. Leakage controls and the actor-disjoint split (1)
7. Classification results, structural vs full (1–2)
8. Clustering: silhouette sweep + named archetypes (1–2)
9. Scalability (1)
10. Conclusion and limitations (1)

End on limitations rather than claims — it reads as confidence, and it pre-empts
the obvious questions.
