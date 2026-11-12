"""
Feature builder shared by the live-model trainer and the live scorer.

CRITICAL: training and serving MUST build features from the same code. If the
trainer and the scorer each define their own version, they drift apart and the
model silently scores garbage at serve time. Both import this module.

The feature set is deliberately restricted to what the Wikimedia EventStreams
SSE feed actually carries:

    timestamp  namespace  minor  comment  length_old  length_new  user  bot

The batch model in p05_classification.py uses richer columns -- per-user
cadence, page revision counts, account age, revision tags -- none of which the
live feed sends. Those features cannot be computed for an arriving event, so a
separate, smaller model is trained here rather than pretending the batch model
can be served live.
"""
import math

from pyspark.sql import functions as F

# canonical column names every caller must supply
LIVE_COLUMNS = ["ts", "namespace", "minor", "comment",
                "length_old", "length_new", "user", "bot"]

FEATURES = [
    "f_hour", "f_dayofweek", "f_is_weekend", "f_is_night",
    "f_hour_sin", "f_hour_cos",
    "f_bytes", "f_bytes_diff", "f_abs_diff", "f_log_abs_diff",
    "f_diff_sign", "f_diff_ratio", "f_is_create",
    "f_is_minor", "f_is_anon", "f_is_content_ns",
    "f_cmt_len", "f_cmt_words", "f_cmt_has_section", "f_cmt_wikilinks",
    "f_cmt_urls", "f_cmt_digits", "f_cmt_upper", "f_cmt_punct", "f_cmt_empty",
]
CATEGORICAL = ["namespace_str"]

# an anonymous edit is credited to an IP literal rather than a username
IPV4 = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
IPV6 = r"^[0-9A-Fa-f:]+:[0-9A-Fa-f:]*$"


def add_live_features(df):
    """Build FEATURES from a DataFrame carrying LIVE_COLUMNS."""
    ts = F.col("ts")
    cmt = F.coalesce(F.col("comment"), F.lit(""))
    new = F.coalesce(F.col("length_new").cast("double"), F.lit(0.0))
    old = F.coalesce(F.col("length_old").cast("double"), F.lit(0.0))
    diff = new - old

    return (df
        .withColumn("f_hour", F.hour(ts).cast("double"))
        .withColumn("f_dayofweek", F.dayofweek(ts).cast("double"))
        .withColumn("f_is_weekend", F.dayofweek(ts).isin([1, 7]).cast("double"))
        .withColumn("f_is_night", ((F.hour(ts) >= 0) & (F.hour(ts) < 6)).cast("double"))
        .withColumn("f_hour_sin", F.sin(2 * math.pi * F.hour(ts) / 24.0))
        .withColumn("f_hour_cos", F.cos(2 * math.pi * F.hour(ts) / 24.0))

        .withColumn("f_bytes", new)
        .withColumn("f_bytes_diff", diff)
        .withColumn("f_abs_diff", F.abs(diff))
        .withColumn("f_log_abs_diff", F.log1p(F.abs(diff)))
        .withColumn("f_diff_sign", F.signum(diff))
        .withColumn("f_diff_ratio", F.when(new > 0, diff / new).otherwise(0.0))
        # the feed reports length_old = 0 (or null) on a page creation
        .withColumn("f_is_create", (old <= 0).cast("double"))

        .withColumn("f_is_minor", F.coalesce(F.col("minor").cast("double"), F.lit(0.0)))
        .withColumn("f_is_anon",
                    (F.col("user").rlike(IPV4) | F.col("user").rlike(IPV6)).cast("double"))
        .withColumn("f_is_content_ns", (F.col("namespace") == 0).cast("double"))

        .withColumn("f_cmt_len", F.length(cmt).cast("double"))
        .withColumn("f_cmt_words", F.size(F.split(F.trim(cmt), r"\s+")).cast("double"))
        .withColumn("f_cmt_has_section", cmt.rlike(r"/\*.*\*/").cast("double"))
        .withColumn("f_cmt_wikilinks", (F.size(F.split(cmt, r"\[\[")) - 1).cast("double"))
        .withColumn("f_cmt_urls", (F.size(F.split(cmt, r"https?://")) - 1).cast("double"))
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

        .withColumn("namespace_str",
                    F.coalesce(F.col("namespace").cast("string"), F.lit("?")))
        .withColumn("label_bot", F.col("bot").cast("int"))
        .fillna(0.0, subset=FEATURES)
    )
