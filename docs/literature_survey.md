# Phase 2: Literature Survey

Comparative table. Replace/extend with the exact papers your course requires —
the rows below are the standard anchor works for this problem area, each chosen
because it maps onto a specific design decision in our pipeline.

| # | Work (author / venue, year) | Dataset | Key features | Algorithms | Evaluation metrics | What we take from it |
|---|---|---|---|---|---|---|
| 1 | Halfaker & Taraborelli — *ORES: Scaling up ML-driven quality control* (Wikimedia, 2015) | Wikipedia revisions | revision metadata, diff size, user attributes | Gradient boosting, random forest | precision/recall at operating threshold, ROC-AUC | production framing: reviewer-routing needs high precision, not raw accuracy |
| 2 | Potthast, Stein & Gerling — *Automatic Vandalism Detection in Wikipedia* (ECIR, 2008) | 940 k English Wikipedia edits | char-level and word-level diff features, comment text | logistic regression, rule baselines | precision, recall, F1 | our comment-shape features (punctuation, caps, digit ratio) |
| 3 | Adler et al. — *Wikipedia Vandalism Detection: Combining NLP, Metadata and Reputation* (CICLing, 2011) | PAN-WVC-10 | metadata + NLP + author reputation | random forest, feature-set ablation | ROC-AUC, PR-AUC | the structural-vs-full ablation design in Phase 5 |
| 4 | Davis et al. — *BotOrNot / Botometer* (WWW demo, 2016) | Twitter accounts | temporal cadence, entropy of activity, content features | random forest | ROC-AUC, class-balanced accuracy | inter-event-gap regularity as the core automation signal (`e_gap_cv`) |
| 5 | Chu et al. — *Detecting Automation of Twitter Accounts: Are You a Human, Bot, or Cyborg?* (IEEE TDSC, 2012) | 500 k Twitter accounts | inter-arrival timing, entropy, periodicity | entropy classifier + Bayesian | accuracy, FP rate | justification for treating cadence variance, not volume, as the discriminator |
| 6 | Welser et al. — *Finding Social Roles in Wikipedia* (iConference, 2011) | English Wikipedia editors | namespace distribution, edit mix | descriptive clustering | qualitative role validity | editor-archetype framing and namespace-entropy features |
| 7 | Yang et al. — *Who Does What: Editor Role Identification in Wikipedia* (ICWSM, 2016) | Wikipedia edit histories | per-editor activity profiles | k-means, mixture models | silhouette, role interpretability | k selection by silhouette plus qualitative cluster naming |
| 8 | Kumar, Spezzano & Subrahmanian — *VEWS: A Wikipedia Vandal Early Warning System* (KDD, 2015) | 33 k Wikipedia users | behavioural sequences, time between edits | SVM, random forest | accuracy, early-detection rate | per-editor (not per-edit) modelling as a complementary view |
| 9 | Zaharia et al. — *Resilient Distributed Datasets* (NSDI, 2012) | — | — | Spark RDD model | runtime scaling | Phase 7 argument for in-memory distributed processing |
| 10 | Meng et al. — *MLlib: Machine Learning in Apache Spark* (JMLR, 2016) | — | — | Spark MLlib pipelines | scalability benchmarks | Pipeline API, distributed SVD, train-only transformer fitting |

## How to use this table in the report

Group the discussion into three threads rather than walking row by row:

1. **Edit-level quality/abuse detection** (rows 1–3, 8) — establishes that
   metadata plus lightweight text beats heavy NLP at scale, and that PR-AUC
   matters more than accuracy under class imbalance.
2. **Automation detection by timing** (rows 4–5) — the cross-platform finding
   that cadence *regularity* separates machines from people. This is the direct
   motivation for `e_gap_cv`, our coefficient-of-variation feature.
3. **Unsupervised editor roles** (rows 6–7) — precedent for interpreting
   clusters as social roles, and for validating k by silhouette plus
   human-readable cluster naming.

Rows 9–10 are infrastructure citations for Phase 7.
