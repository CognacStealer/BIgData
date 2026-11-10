# Phase 7: Scalability Discussion

## Why Spark was used

The honest answer is **not** "the file is too big for RAM" — the simplewiki
snapshot is ~1 GB compressed and a determined pandas user could force it. Spark
earns its place for three concrete reasons:

1. **The workload is a wide shuffle, not a scan.** The per-editor aggregation in
   Phase 4 groups tens of millions of revisions by `actor_key` and computes
   windowed inter-edit gaps (`lag` over a partition ordered by timestamp). This
   is a sort-merge shuffle whose working set is proportional to the number of
   distinct actors, not to available memory. Spark spills to disk and completes;
   an in-memory groupby either thrashes or dies.
2. **The same code scales to the full corpus unchanged.** simplewiki is one wiki
   of ~900. Pointing `config.WIKI` at `enwiki` moves the input from ~1 GB to
   hundreds of GB across monthly shards, with no pipeline rewrite — only
   partition counts and cluster size change.
3. **MLlib keeps training distributed.** The truncated SVD in Phase 4 runs on a
   distributed `RowMatrix`; the GBT and k-means fits parallelise across
   partitions. Collecting features to a single machine to use scikit-learn would
   reintroduce exactly the bottleneck we are supposed to be removing.

## How distributed processing improves scalability here

| Pipeline stage | Parallelisation mechanism |
|---|---|
| Raw TSV read | bz2 **is splittable** in Hadoop, so the 1 GB file is read by many concurrent tasks. (A gzip dump would have been a single task — a real design trap.) |
| Column projection | Phase 0 writes Parquet and keeps 28 of 78 columns, so later phases read ~⅓ of the bytes via columnar pruning. |
| Label partitioning | `prepared/` is partitioned by `label_bot`, so class-conditional queries prune whole directories. |
| Feature engineering | Fully row-local (`withColumn`) → embarrassingly parallel, no shuffle. |
| Editor aggregation | `groupBy` + window → sort-merge shuffle across 48 partitions. |
| SVD | Distributed `RowMatrix.computeSVD`; only the small right-singular matrix `V` (2048 × 24) is collected and broadcast. |
| Model training | MLlib iterative fits broadcast the model and reduce gradients/statistics per partition. |

Adaptive Query Execution is enabled (`spark.sql.adaptive.enabled`), so
post-shuffle partitions are coalesced at runtime rather than guessed up front.

## Potential challenges for very large datasets

**Actor skew is the dominant risk.** Edit counts per account follow a heavy power
law: a handful of bots have millions of revisions while the median account has
one. A naive `groupBy("actor_key")` sends one enormous partition to a single
task, which straggles and can OOM while 47 cores idle. Mitigations, in order of
preference:
* `spark.sql.adaptive.skewJoin.enabled` (on) — splits detected skewed partitions;
* salting the grouping key for the heaviest actors, then a second reduce;
* computing cadence statistics with bounded-memory sketches rather than exact
  `percentile_approx` over a full partition.

**The window function is the expensive step.** `lag` over
`partitionBy(actor_key).orderBy(event_timestamp)` requires a full sort within
each partition. At enwiki scale this is the stage to optimise first — ideally by
pre-partitioning the Parquet by actor-hash at write time so the sort is local.

**Small-files problem.** Writing one Parquet file per task across hundreds of
monthly shards produces tens of thousands of tiny files and cripples the next
read. We `repartition(48)` before writing; at larger scale this becomes an
explicit compaction step.

**Broadcast limits.** Broadcasting `V` is fine at 2048 × 24 floats. Raising
`TFIDF_FEATURES` to, say, 2²⁰ would make `V` too large to broadcast and would
force a distributed matrix multiply instead.

**Class imbalance interacts with partitioning.** Bot edits are a large minority
here, but at the scale of individual wikis the reverted-edit label is rare
(low single-digit %). Stratified sampling must happen *after* the actor-disjoint
split, or the split guarantee is broken.

**Cost of the all-time snapshot.** The `all-time` file mixes 2001-era edits with
2026 edits. Editor behaviour and tooling changed enormously across that span, so
a model trained on the whole history is implicitly averaging over several
distinct regimes. For very large runs, restrict to a recent window
(the per-month shards exist for larger wikis) and treat era as a feature or a
stratum rather than ignoring it.
