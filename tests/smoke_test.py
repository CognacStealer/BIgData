"""
End-to-end smoke test on a tiny slice of the real dump.

Runs Phases 3 -> 4 -> 5a -> 5b -> 6 against a few thousand real revisions in a
throwaway directory, so logic errors surface in seconds instead of after an
hour on the full corpus. Uses the real dump file, just a truncated read.

  source env.sh && python tests/smoke_test.py
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config

# --- redirect every output path into a sandbox -----------------------------
SANDBOX = ROOT / "data" / "_smoke"
if SANDBOX.exists():
    shutil.rmtree(SANDBOX)
for name in ("DATA_PARQUET", "DATA_FEATURES"):
    setattr(config, name, SANDBOX / name.lower())
config.METRICS = SANDBOX / "metrics"
config.FIGURES = SANDBOX / "figures"
config.REVISIONS_PARQUET = config.DATA_PARQUET / "revisions"
config.EDIT_FEATURES = config.DATA_FEATURES / "edit_level"
config.EDITOR_FEATURES = config.DATA_FEATURES / "editor_level"
for p in (config.DATA_PARQUET, config.DATA_FEATURES, config.METRICS, config.FIGURES):
    p.mkdir(parents=True, exist_ok=True)

# Smaller everything, so the run is quick but exercises the same code paths.
config.SVD_K = 6
config.TFIDF_FEATURES = 256
config.KMEANS_K_RANGE = [2, 3]
config.SPARK_CONF["spark.sql.shuffle.partitions"] = "4"
config.SPARK_CONF["spark.driver.memory"] = "2g"
config.MASTER = "local[2]"
config.TRAIN_SAMPLE = 1.0

import schema
from spark_utils import get_spark, banner

N_ROWS = 60000


def build_fixture():
    """Read the first N rows of the real dump into the sandbox as Parquet."""
    import bz2 as _bz2
    tmp = SANDBOX / "sample.tsv"
    kept = 0
    with _bz2.open(config.RAW_TSV, "rt", encoding="utf8", errors="replace") as fh, \
         tmp.open("w", encoding="utf8") as out:
        for line in fh:
            out.write(line)
            kept += 1
            if kept >= N_ROWS:
                break
    print(f"  fixture: {kept:,} raw lines -> {tmp}")

    spark = get_spark("smoke_fixture")
    raw = (spark.read.option("sep", "\t").option("header", "false")
           .option("quote", "").option("escape", "")
           .option("nullValue", "").schema(schema.RAW_SCHEMA).csv(str(tmp)))
    from pyspark.sql import functions as F
    rev = raw.filter(F.col("event_entity") == "revision").select(*schema.REVISION_COLUMNS)
    n = rev.count()
    print(f"  revision rows in fixture: {n:,}")
    assert n > 1000, f"fixture too small ({n}); widen N_ROWS"
    rev.write.mode("overwrite").parquet(str(config.REVISIONS_PARQUET))
    spark.stop()


def main():
    banner("SMOKE TEST (tiny fixture, real data)")
    build_fixture()

    for mod_name in ("p03_prepare", "p04_features",
                     "p05_classification", "p05_clustering", "p06_report"):
        banner(f"smoke: {mod_name}")
        mod = __import__(mod_name)
        mod.main()

    print("\nSMOKE TEST PASSED")
    print(f"  artefacts under {SANDBOX}")


if __name__ == "__main__":
    main()
