"""
Phase 4: Feature Engineering.

Produces two datasets:
  edit_level   -> one row per revision, used for CLASSIFICATION
  editor_level -> one row per actor, used for CLUSTERING

Leakage policy (this is the methodological core of the project):
  * `event_user_text`     contains names like "SchlurcherBot"  -> EXCLUDED
  * `event_user_groups`   contains the literal "bot" group that DEFINES the
                          label                                -> EXCLUDED
  * `event_user_is_bot_by` is the label itself                 -> EXCLUDED
  * revision tags whose name contains "bot" are dropped from the tag features.
  * `event_comment` IS kept. It is observable at edit time and is not derived
    from user-group membership, so it is a legitimate (if strong) predictor.
    Phase 5 trains both WITH and WITHOUT the text block so the report can
    quantify how much of the performance comes from text.

Dimensionality reduction: TF-IDF over comment tokens (2048 hashed buckets) is
reduced with a genuine truncated SVD via mllib's distributed RowMatrix.
"""
import math

import numpy as np
from pyspark import StorageLevel

from pyspark.ml.feature import HashingTF, IDF, RegexTokenizer
from pyspark.ml.linalg import Vectors, VectorUDT
from pyspark.mllib.linalg import Vectors as MLLibVectors
from pyspark.mllib.linalg.distributed import RowMatrix
from pyspark.sql import functions as F
from pyspark.sql import Window
from pyspark.sql.types import DoubleType

import config
from spark_utils import get_spark, timed, banner, save_metrics

# ---------------------------------------------------------------- edit level
def add_edit_features(df):
    ts = F.col("event_timestamp")
    cmt = F.col("event_comment")

    df = (df
        # --- temporal -------------------------------------------------------
        .withColumn("f_hour", F.hour(ts))
        .withColumn("f_dayofweek", F.dayofweek(ts))
        .withColumn("f_is_weekend", F.dayofweek(ts).isin([1, 7]).cast("double"))
        # bots run on cron -> flat 24h profile; humans sleep
        .withColumn("f_is_night", ((F.hour(ts) >= 0) & (F.hour(ts) < 6)).cast("double"))
        .withColumn("f_hour_sin", F.sin(2 * math.pi * F.hour(ts) / 24.0))
        .withColumn("f_hour_cos", F.cos(2 * math.pi * F.hour(ts) / 24.0))

        # --- edit size ------------------------------------------------------
        .withColumn("f_bytes", F.col("revision_text_bytes").cast("double"))
        .withColumn("f_bytes_diff", F.col("revision_text_bytes_diff").cast("double"))
        .withColumn("f_abs_diff", F.abs(F.col("revision_text_bytes_diff")).cast("double"))
        .withColumn("f_log_abs_diff", F.log1p(F.abs(F.col("revision_text_bytes_diff"))))
        .withColumn("f_diff_sign", F.signum(F.col("revision_text_bytes_diff")).cast("double"))
        .withColumn("f_diff_ratio",
                    F.when(F.col("revision_text_bytes") > 0,
                           F.col("revision_text_bytes_diff") /
                           F.col("revision_text_bytes")).otherwise(0.0))

        # --- cadence --------------------------------------------------------
        # -1 sentinel from Phase 3 means "first edit"; keep it distinguishable
        .withColumn("f_has_prev",
                    (F.col("event_user_seconds_since_previous_revision") >= 0).cast("double"))
        .withColumn("f_log_secs_prev",
                    F.when(F.col("event_user_seconds_since_previous_revision") >= 0,
                           F.log1p("event_user_seconds_since_previous_revision"))
                     .otherwise(0.0))
        .withColumn("f_log_user_revcount", F.log1p("event_user_revision_count"))
        .withColumn("f_log_page_revcount", F.log1p("page_revision_count"))

        # --- account --------------------------------------------------------
        .withColumn("f_account_age_days",
                    F.when(F.col("event_user_registration_timestamp").isNotNull(),
                           (ts.cast("long") -
                            F.col("event_user_registration_timestamp").cast("long")) / 86400.0)
                     .otherwise(-1.0))
        .withColumn("f_is_anon", F.col("event_user_is_anonymous").cast("double"))

        # --- page context ---------------------------------------------------
        .withColumn("f_is_content_ns", F.col("page_namespace_is_content").cast("double"))
        .withColumn("f_is_redirect", F.col("page_is_redirect").cast("double"))
        .withColumn("f_is_minor", F.col("revision_minor_edit").cast("double"))
        .withColumn("f_is_create", (F.col("revision_parent_id").isNull() |
                                    (F.col("revision_parent_id") == 0)).cast("double"))

        # --- comment structure (shape, not vocabulary) ----------------------
        .withColumn("f_cmt_len", F.length(cmt).cast("double"))
        .withColumn("f_cmt_words", F.size(F.split(F.trim(cmt), r"\s+")).cast("double"))
        .withColumn("f_cmt_has_section",
                    cmt.rlike(r"/\*.*\*/").cast("double"))
        .withColumn("f_cmt_wikilinks",
                    (F.size(F.split(cmt, r"\[\[")) - 1).cast("double"))
        .withColumn("f_cmt_urls",
                    (F.size(F.split(cmt, r"https?://")) - 1).cast("double"))
        .withColumn("f_cmt_digits",
                    F.when(F.length(cmt) > 0,
                           (F.length(cmt) - F.length(F.regexp_replace(cmt, r"[0-9]", "")))
                           / F.length(cmt)).otherwise(0.0))
        .withColumn("f_cmt_upper",
                    F.when(F.length(cmt) > 0,
                           (F.length(cmt) - F.length(F.regexp_replace(cmt, r"[A-Z]", "")))
                           / F.length(cmt)).otherwise(0.0))
        .withColumn("f_cmt_punct",
                    F.when(F.length(cmt) > 0,
                           (F.length(cmt) - F.length(F.regexp_replace(cmt, r"[^\w\s]", "")))
                           / F.length(cmt)).otherwise(0.0))
        .withColumn("f_cmt_empty", (F.length(F.trim(cmt)) == 0).cast("double"))

        # --- tags (bot-naming tags stripped to avoid leakage) ---------------
        .withColumn("f_n_tags",
                    F.when(F.length(F.trim("revision_tags")) == 0, F.lit(0.0))
                     .otherwise(F.size(F.split("revision_tags", ",")).cast("double")))
        .withColumn("f_tag_mobile", F.col("revision_tags").contains("mobile").cast("double"))
        .withColumn("f_tag_visualeditor", F.col("revision_tags").contains("visualeditor").cast("double"))
        .withColumn("f_tag_undo", F.col("revision_tags").contains("undo").cast("double"))
    )
    return df


NUMERIC_EDIT_FEATURES = [
    "f_hour", "f_dayofweek", "f_is_weekend", "f_is_night", "f_hour_sin", "f_hour_cos",
    "f_bytes", "f_bytes_diff", "f_abs_diff", "f_log_abs_diff", "f_diff_sign", "f_diff_ratio",
    "f_has_prev", "f_log_secs_prev", "f_log_user_revcount", "f_log_page_revcount",
    "f_account_age_days", "f_is_anon",
    "f_is_content_ns", "f_is_redirect", "f_is_minor", "f_is_create",
    "f_cmt_len", "f_cmt_words", "f_cmt_has_section", "f_cmt_wikilinks", "f_cmt_urls",
    "f_cmt_digits", "f_cmt_upper", "f_cmt_punct", "f_cmt_empty",
    "f_n_tags", "f_tag_mobile", "f_tag_visualeditor", "f_tag_undo",
]
CATEGORICAL_EDIT_FEATURES = ["page_namespace"]


# -------------------------------------------------------------- editor level
def build_editor_features(df):
    """Aggregate per actor. This is the wide shuffle discussed in Phase 7."""
    w = Window.partitionBy("actor_key").orderBy("event_timestamp")
    df = df.withColumn(
        "gap_secs",
        F.col("event_timestamp").cast("long") -
        F.lag(F.col("event_timestamp").cast("long")).over(w)
    )

    agg = df.groupBy("actor_key").agg(
        F.count("*").alias("e_n_edits"),
        F.countDistinct("page_id").alias("e_n_pages"),
        F.countDistinct("page_namespace").alias("e_n_namespaces"),
        F.avg(F.col("f_is_minor")).alias("e_minor_ratio"),
        F.avg(F.col("f_is_content_ns")).alias("e_content_ratio"),
        F.avg(F.col("label_reverted").cast("double")).alias("e_reverted_ratio"),
        F.avg(F.col("f_is_night")).alias("e_night_ratio"),
        F.avg(F.col("f_is_weekend")).alias("e_weekend_ratio"),
        F.avg(F.col("f_cmt_len")).alias("e_cmt_len_mean"),
        F.avg(F.col("f_cmt_has_section")).alias("e_cmt_section_ratio"),
        F.avg(F.col("f_cmt_empty")).alias("e_cmt_empty_ratio"),
        F.avg(F.col("f_abs_diff")).alias("e_abs_diff_mean"),
        F.stddev(F.col("f_abs_diff")).alias("e_abs_diff_std"),
        F.expr("percentile_approx(f_abs_diff, 0.5)").alias("e_abs_diff_median"),
        F.avg(F.col("f_diff_sign")).alias("e_diff_sign_mean"),
        F.avg("gap_secs").alias("e_gap_mean"),
        F.stddev("gap_secs").alias("e_gap_std"),
        F.expr("percentile_approx(gap_secs, 0.5)").alias("e_gap_median"),
        F.min("event_timestamp").alias("e_first_edit"),
        F.max("event_timestamp").alias("e_last_edit"),
        F.countDistinct(F.to_date("event_timestamp")).alias("e_active_days"),
        F.max(F.col("label_bot")).alias("e_is_bot"),   # for cluster VALIDATION only
    )

    agg = (agg
        .withColumn("e_span_days",
                    (F.col("e_last_edit").cast("long") -
                     F.col("e_first_edit").cast("long")) / 86400.0)
        .withColumn("e_edits_per_active_day",
                    F.col("e_n_edits") / F.greatest(F.col("e_active_days"), F.lit(1)))
        .withColumn("e_pages_per_edit", F.col("e_n_pages") / F.col("e_n_edits"))
        # Coefficient of variation of inter-edit gap: the single best
        # "metronomic automation" signal. Low CV == machine-timed.
        .withColumn("e_gap_cv",
                    F.when(F.col("e_gap_mean") > 0,
                           F.col("e_gap_std") / F.col("e_gap_mean")).otherwise(-1.0))
        .withColumn("e_log_n_edits", F.log1p("e_n_edits"))
        .withColumn("e_log_gap_mean", F.log1p(F.greatest(F.col("e_gap_mean"), F.lit(0.0))))
        .fillna(0.0)
    )
    return agg


EDITOR_FEATURES = [
    "e_log_n_edits", "e_n_namespaces", "e_minor_ratio", "e_content_ratio",
    "e_reverted_ratio", "e_night_ratio", "e_weekend_ratio",
    "e_cmt_len_mean", "e_cmt_section_ratio", "e_cmt_empty_ratio",
    "e_abs_diff_mean", "e_abs_diff_median", "e_diff_sign_mean",
    "e_log_gap_mean", "e_gap_cv",
    "e_span_days", "e_active_days", "e_edits_per_active_day", "e_pages_per_edit",
]


# ---------------------------------------------------------------------- SVD
def comment_svd(df, k, n_features, seed):
    """TF-IDF over comment tokens -> truncated SVD (distributed RowMatrix)."""
    tok = RegexTokenizer(inputCol="event_comment", outputCol="cmt_tokens",
                         pattern=r"[^\p{L}\p{N}]+", minTokenLength=2, toLowercase=True)
    htf = HashingTF(inputCol="cmt_tokens", outputCol="cmt_tf", numFeatures=n_features)
    idf = IDF(inputCol="cmt_tf", outputCol="cmt_tfidf", minDocFreq=5)

    d = tok.transform(df)
    d = htf.transform(d)
    idf_model = idf.fit(d)
    d = idf_model.transform(d)

    # Fit the SVD on a sample. computeSVD builds a 2048x2048 Gramian and
    # eigendecomposes it locally, so the right singular vectors converge with
    # far fewer rows than the full 11 M; sampling here is the difference
    # between a ~20 min and a ~3 min fit. Materialise the sample first so the
    # tokenize -> hash -> IDF chain is not recomputed during the SVD.
    sample = (d.select("cmt_tfidf")
               .sample(False, config.SVD_SAMPLE_FRACTION, seed=seed)
               .persist(StorageLevel.MEMORY_AND_DISK))
    n_sample = sample.count()
    print(f"  SVD fit on {n_sample:,} sampled rows")
    rows = sample.rdd.map(lambda r: MLLibVectors.fromML(r["cmt_tfidf"]))
    mat = RowMatrix(rows)
    svd = mat.computeSVD(k, computeU=False)
    V = svd.V.toArray()            # n_features x k
    sing = svd.s.toArray()
    sample.unpersist()

    bcast = d.sparkSession.sparkContext.broadcast(V)

    # Projection X @ V, one row at a time but with a single numpy gather+dot
    # per row rather than a nested Python loop over (nonzeros x k).
    #
    # NOTE: this deliberately is NOT a pandas_udf. Spark's Arrow path does not
    # support VectorUDT as a pandas_udf *input* -- the column arrives as str and
    # fails with "'str' object has no attribute 'indices'". Vectorising here
    # would require densifying 2048 columns per row, which costs far more than
    # the Python call overhead it saves.
    def project(v):
        arr = bcast.value
        idx = getattr(v, "indices", None)
        if idx is None:                        # dense input
            return Vectors.dense(np.asarray(v.toArray()).dot(arr))
        if len(idx) == 0:
            return Vectors.dense(np.zeros(arr.shape[1]))
        return Vectors.dense(arr[idx].T.dot(v.values))

    project_udf = F.udf(project, VectorUDT())
    d = d.withColumn("cmt_svd", project_udf("cmt_tfidf"))
    return d, idf_model, sing


def main():
    spark = get_spark("p04_features")
    banner("PHASE 4: Feature Engineering")

    df = spark.read.parquet(str(config.DATA_PARQUET / "prepared"))
    print(f"  rows in: {df.count():,}")

    with timed("edit-level features"):
        edits = add_edit_features(df)

    with timed("comment TF-IDF + SVD"):
        edits, idf_model, sing = comment_svd(
            edits, config.SVD_K, config.TFIDF_FEATURES, config.SEED)
        total_energy = float((sing ** 2).sum())
        print(f"  top singular values: {[round(float(x),3) for x in sing[:8]]}")

    keep = (["revision_id", "actor_key", "label_bot", "label_reverted",
             "event_timestamp", "cmt_svd"]
            + NUMERIC_EDIT_FEATURES + CATEGORICAL_EDIT_FEATURES)
    with timed("write edit-level features"):
        (edits.select(*keep)
              .write.mode("overwrite").option("compression", "snappy")
              .parquet(str(config.EDIT_FEATURES)))

    with timed("editor-level aggregation"):
        editors = build_editor_features(edits)
        (editors.write.mode("overwrite").option("compression", "snappy")
                .parquet(str(config.EDITOR_FEATURES)))
        n_editors = spark.read.parquet(str(config.EDITOR_FEATURES)).count()
    print(f"  editors: {n_editors:,}")

    save_metrics("p04_features", {
        "n_numeric_edit_features": len(NUMERIC_EDIT_FEATURES),
        "n_editor_features": len(EDITOR_FEATURES),
        "svd_k": config.SVD_K,
        "tfidf_buckets": config.TFIDF_FEATURES,
        "singular_values": [float(x) for x in sing],
        "svd_energy_captured": total_energy,
        "n_editors": n_editors,
        "edit_feature_names": NUMERIC_EDIT_FEATURES,
        "editor_feature_names": EDITOR_FEATURES,
    })
    spark.stop()


if __name__ == "__main__":
    main()
