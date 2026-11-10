"""Central configuration. Every phase imports paths from here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_RAW      = ROOT / "data" / "raw"
DATA_PARQUET  = ROOT / "data" / "parquet"
DATA_FEATURES = ROOT / "data" / "features"
REPORTS       = ROOT / "reports"
FIGURES       = REPORTS / "figures"
METRICS       = REPORTS / "metrics"

WIKI = "simplewiki"
SNAPSHOT = "2026-10"
RAW_TSV = DATA_RAW / f"{WIKI}.all-time.tsv.bz2"

# Phase 3 output: cleaned revision events
REVISIONS_PARQUET = DATA_PARQUET / "revisions"
# Phase 4 outputs
EDIT_FEATURES   = DATA_FEATURES / "edit_level"
EDITOR_FEATURES = DATA_FEATURES / "editor_level"

# --- Spark tuning for a single 12-core / 14 GB box -------------------------
SPARK_CONF = {
    "spark.driver.memory": "6g",
    "spark.driver.maxResultSize": "1g",
    "spark.sql.shuffle.partitions": "48",      # ~4x cores
    "spark.sql.adaptive.enabled": "true",
    "spark.sql.adaptive.coalescePartitions.enabled": "true",
    "spark.sql.adaptive.skewJoin.enabled": "true",   # hyperactive bots skew
    "spark.serializer": "org.apache.spark.serializer.KryoSerializer",
    "spark.local.dir": str(ROOT / "data" / "spark-tmp"),
}
MASTER = "local[*]"

# --- Modelling -------------------------------------------------------------
SEED = 42
TRAIN_FRACTION = 0.8
# Fraction of the TRAIN split actually fed to the learners. The test split is
# always evaluated in full, so metrics stay honest. Tree ensembles on tens of
# millions of rows are pass-bound; 1.0 is correct for a final run, a smaller
# value makes iteration bearable. Override with env TRAIN_SAMPLE.
import os as _os
TRAIN_SAMPLE = float(_os.environ.get("TRAIN_SAMPLE", "1.0"))
SVD_K = 24                 # rank for TF-IDF truncated SVD (Phase 4)
SVD_SAMPLE_FRACTION = 0.04 # rows sampled to FIT the SVD (projection uses all)
TFIDF_FEATURES = 2048      # HashingTF buckets
KMEANS_K_RANGE = [2, 3, 4, 5, 6, 7, 8]

# Features that must NEVER enter a model: they leak the label.
# `event_user_text` contains strings like "SchlurcherBot"; `event_user_groups`
# literally contains the "bot" group that defines the label.
LEAKY_COLUMNS = [
    "event_user_text", "event_user_text_historical",
    "event_user_groups", "event_user_groups_historical",
    "event_user_is_bot_by", "event_user_is_bot_by_historical",
    "user_is_bot_by", "user_is_bot_by_historical",
    "user_groups", "user_groups_historical",
]

for _p in (DATA_RAW, DATA_PARQUET, DATA_FEATURES, FIGURES, METRICS,
           ROOT / "data" / "spark-tmp"):
    _p.mkdir(parents=True, exist_ok=True)
