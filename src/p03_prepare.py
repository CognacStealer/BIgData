"""
Phase 3: Data Preparation.

Covers the rubric items: missing values, duplicates, categorical encoding
(deferred to the ML Pipeline so it is fitted on train only), normalisation
(ditto), attribute selection.

Also defines the two supervised LABELS:
  label_bot     : event_user_is_bot_by is non-empty  -> this edit was made by a
                  flagged automated account. Ground truth comes from MediaWiki
                  user-group membership / bot-name registry, NOT from anything
                  we engineer, so it is a legitimate target.
  label_reverted: revision_is_identity_reverted      -> this edit was later
                  reverted (a proxy for low-quality / abusive editing).
"""
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, LongType, TimestampType

import config
from spark_utils import get_spark, timed, banner, save_metrics

BOOL_COLS = [
    "page_namespace_is_content", "page_is_redirect",
    "revision_minor_edit", "revision_is_identity_reverted",
    "revision_is_identity_revert", "event_user_is_anonymous",
]
LONG_COLS = [
    "event_user_id", "event_user_revision_count",
    "event_user_seconds_since_previous_revision",
    "page_id", "page_revision_count", "revision_id", "revision_parent_id",
    "revision_text_bytes", "revision_text_bytes_diff",
    "revision_seconds_to_identity_revert",
]
TS_COLS = ["event_timestamp", "event_user_registration_timestamp"]


def cast_types(df):
    # NOTE on the boolean coalesce: `NULL == "true"` is NULL in SQL, so a plain
    # comparison leaves nulls in place. Those nulls become NaN once
    # VectorAssembler runs, and StandardScaler then propagates the NaN into
    # every row's feature vector, which Spark rejects outright with
    # "Vector values MUST NOT be NaN or Infinity".
    #
    # Null here means "the current-state flag is unknown", overwhelmingly
    # because the page was deleted (page_is_redirect is ~9.8% null). Treating
    # that as False is the defensible reading: "not known to be a redirect /
    # minor / reverted". It is recorded here rather than silently patched
    # downstream so the imputation is visible in the report.
    for c in BOOL_COLS:
        df = df.withColumn(c, F.coalesce(F.col(c) == F.lit("true"), F.lit(False)))
    for c in LONG_COLS:
        df = df.withColumn(c, F.col(c).cast(LongType()))
    for c in TS_COLS:
        # dump format: "2001-05-18 21:57:10.0"
        df = df.withColumn(c, F.to_timestamp(c, "yyyy-MM-dd HH:mm:ss.S"))
    df = df.withColumn("page_namespace", F.col("page_namespace").cast(IntegerType()))
    return df


def main():
    spark = get_spark("p03_prepare")
    banner("PHASE 3: Data Preparation")

    df = spark.read.parquet(str(config.REVISIONS_PARQUET))
    n0 = df.count()
    print(f"  input revision rows: {n0:,}")

    # Recover deleted-page rows BEFORE any null-key filtering. When a page is
    # deleted, MediaWiki nulls the current-state page_* columns but keeps the
    # *_historical ones. Dropping those rows would silently discard ~15% of all
    # revisions -- and deleted pages are exactly where vandalism concentrates,
    # so the loss would bias `label_reverted`, not just shrink the data.
    df = (df
          .withColumn("page_namespace",
                      F.coalesce("page_namespace", "page_namespace_historical"))
          .withColumn("page_title",
                      F.coalesce("page_title", "page_title_historical"))
          .withColumn("page_namespace_is_content",
                      F.coalesce("page_namespace_is_content",
                                 "page_namespace_is_content_historical"))
          .drop("page_namespace_historical", "page_title_historical",
                "page_namespace_is_content_historical"))

    df = cast_types(df)

    # ---- 1. duplicates -----------------------------------------------------
    # revision_id is the natural key for an edit. The all-time dump can repeat
    # a revision when a page was deleted and undeleted.
    with timed("deduplicate on revision_id"):
        df = df.dropDuplicates(["revision_id"])
        n1 = df.count()
    print(f"  after dedup: {n1:,}  (removed {n0 - n1:,})")

    # ---- 2. missing values -------------------------------------------------
    key_cols = ["revision_id", "event_timestamp", "page_id", "page_namespace"]
    null_report = df.select([
        F.sum(F.col(c).isNull().cast("int")).alias(c)
        for c in df.columns
    ]).collect()[0].asDict()
    print("  null counts (non-zero only):")
    for c, v in sorted(null_report.items(), key=lambda kv: -kv[1]):
        if v:
            print(f"    {c:<46} {v:,} ({100*v/n1:.2f}%)")

    # Drop rows missing a structural key -- without these the row is unusable.
    df = df.dropna(subset=key_cols)
    n2 = df.count()
    print(f"  after dropping rows with null keys: {n2:,} (removed {n1 - n2:,})")

    # Impute the numeric fields where "missing" has a defined meaning:
    #   - text_bytes_diff null on page creation -> equals full text size
    #   - seconds_since_previous_revision null on a user's first edit -> -1
    #     sentinel (NOT 0, which would mean "instantaneous" and mislead the model)
    df = (df
          .withColumn("revision_text_bytes",
                      F.coalesce("revision_text_bytes", F.lit(0)))
          .withColumn("revision_text_bytes_diff",
                      F.coalesce("revision_text_bytes_diff", "revision_text_bytes"))
          .withColumn("event_user_seconds_since_previous_revision",
                      F.coalesce("event_user_seconds_since_previous_revision",
                                 F.lit(-1)))
          .withColumn("event_user_revision_count",
                      F.coalesce("event_user_revision_count", F.lit(0)))
          .withColumn("page_revision_count",
                      F.coalesce("page_revision_count", F.lit(0)))
          .withColumn("event_comment", F.coalesce("event_comment", F.lit("")))
          .withColumn("revision_tags", F.coalesce("revision_tags", F.lit("")))
          )

    # ---- 3. labels ---------------------------------------------------------
    df = (df
          .withColumn("label_bot",
                      (F.col("event_user_is_bot_by").isNotNull() &
                       (F.length(F.trim("event_user_is_bot_by")) > 0)).cast("int"))
          .withColumn("label_reverted",
                      F.col("revision_is_identity_reverted").cast("int"))
          )

    # ---- 4. actor identity (for Phase 4 editor aggregation) ----------------
    # Anonymous edits have no user_id; use the IP text as the actor key.
    # NOTE: event_user_text is leaky as a *feature* but is legitimate as a
    # grouping key, which never reaches the model.
    df = df.withColumn(
        "actor_key",
        F.when(F.col("event_user_id").isNotNull() & (F.col("event_user_id") > 0),
               F.concat(F.lit("u:"), F.col("event_user_id").cast("string")))
         .otherwise(F.concat(F.lit("ip:"), F.coalesce("event_user_text", F.lit("?"))))
    )

    # Guard: every column that feeds a feature vector must be null-free by now.
    # Without this, a null silently becomes NaN inside StandardScaler and the
    # failure surfaces much later, deep in a model fit, with no indication of
    # which column was responsible.
    # Only the columns whose VALUE lands in a feature vector. Three columns are
    # deliberately left nullable and are excluded here:
    #   event_user_id          -> only builds actor_key (anonymous edits have none)
    #   revision_parent_id     -> f_is_create tests isNull() ON PURPOSE
    #   revision_seconds_to_identity_revert -> null means "never reverted"; unused
    # event_user_registration_timestamp is likewise nullable (anonymous users)
    # and is guarded at use site by a when(isNotNull) branch.
    feature_inputs = BOOL_COLS + [
        "revision_text_bytes", "revision_text_bytes_diff",
        "event_user_seconds_since_previous_revision", "event_user_revision_count",
        "page_revision_count", "page_namespace", "event_comment",
        "revision_tags", "label_bot", "label_reverted",
    ]
    remaining = df.select([
        F.sum(F.col(c).isNull().cast("int")).alias(c) for c in feature_inputs
    ]).collect()[0].asDict()
    bad = {c: v for c, v in remaining.items() if v}
    if bad:
        raise SystemExit(f"FATAL: nulls remain in feature inputs: {bad}")
    print("  null guard passed: all feature-input columns are null-free")

    with timed("write prepared parquet"):
        (df.write.mode("overwrite")
           .partitionBy("label_bot")
           .option("compression", "snappy")
           .parquet(str(config.DATA_PARQUET / "prepared")))

    # ---- 5. report ---------------------------------------------------------
    lab = df.groupBy("label_bot", "label_reverted").count().orderBy("label_bot", "label_reverted").collect()
    print("  label cross-tab (label_bot, label_reverted, count):")
    for r in lab:
        print(f"    bot={r['label_bot']} reverted={r['label_reverted']}: {r['count']:,}")

    bots = df.filter("label_bot = 1").count()
    revs = df.filter("label_reverted = 1").count()
    print(f"\n  bot edits      : {bots:,} ({100*bots/n2:.2f}%)")
    print(f"  reverted edits : {revs:,} ({100*revs/n2:.2f}%)")

    save_metrics("p03_prepare", {
        "rows_in": n0, "rows_after_dedup": n1, "rows_final": n2,
        "duplicates_removed": n0 - n1, "null_key_rows_removed": n1 - n2,
        "null_counts": {k: v for k, v in null_report.items() if v},
        "bot_edits": bots, "bot_rate": bots / n2,
        "reverted_edits": revs, "reverted_rate": revs / n2,
        "label_crosstab": [r.asDict() for r in lab],
    })
    spark.stop()


if __name__ == "__main__":
    main()
