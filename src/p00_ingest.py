"""
Phase 0 (infrastructure): convert the raw bz2 TSV dump into partitioned Parquet.

Why this step exists at all (Phase 7 material):
  * bz2 TSV is row-oriented; every query must decompress and parse all 78
    columns. Parquet is columnar + predicate-pushdown friendly, so the later
    phases read only the ~28 columns they need.
  * bz2 IS splittable in Hadoop, so this conversion itself parallelises; gzip
    would have forced a single task.

Two subtleties that silently corrupt the data if you get them wrong:
  1. `event_comment` contains raw double quotes (e.g. '"Bad words"'). Spark's
     CSV reader treats `"` as a quote char by default and will swallow tabs
     inside a "quoted" region, shifting every later column. We disable quoting.
  2. The dump has NO header row and uses "" for null.
"""
import sys

from pyspark.sql import functions as F

import config
import schema
from spark_utils import get_spark, timed, banner, save_metrics


def read_raw(spark):
    return (
        spark.read
        .option("sep", "\t")
        .option("header", "false")
        .option("quote", "")           # critical: see docstring note 1
        .option("escape", "")
        .option("multiLine", "false")
        .option("mode", "PERMISSIVE")
        .option("nullValue", "")
        .schema(schema.RAW_SCHEMA)
        .csv(str(config.RAW_TSV))
    )


def main():
    spark = get_spark("p00_ingest")
    banner("PHASE 0: raw TSV -> Parquet")

    raw = read_raw(spark)

    # bz2 decompression dominates this phase, so minimise passes over the raw
    # file. ONE grouped aggregate yields the row total, the entity breakdown
    # AND the wiki_db sanity check together; a second pass does the write.
    # (Counting, then distinct(), then groupBy(), then writing would decompress
    # ~950 MB four separate times.)
    with timed("profile raw (single pass)"):
        prof = (raw.groupBy("wiki_db", "event_entity").count()
                   .orderBy(F.desc("count")).collect())

    total = sum(r["count"] for r in prof)
    wikis = sorted({r["wiki_db"] for r in prof})
    print(f"  raw rows: {total:,}")
    print(f"  wiki_db distinct: {wikis}")
    if wikis != [config.WIKI]:
        sys.exit(f"FATAL: wiki_db parse looks wrong: {wikis}")

    entity_counts = {}
    for r in prof:
        entity_counts[r["event_entity"]] = entity_counts.get(r["event_entity"], 0) + r["count"]
    print("  event_entity breakdown:")
    for k, v in sorted(entity_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {str(k):>10}: {v:,}")

    # Keep only revision events (the actual edits) and project to needed cols.
    revisions = (
        raw.filter(F.col("event_entity") == "revision")
           .select(*schema.REVISION_COLUMNS)
    )

    with timed("write parquet"):
        (revisions
            .repartition(48)
            .write.mode("overwrite")
            .option("compression", "snappy")
            .parquet(str(config.REVISIONS_PARQUET)))

    # Cheap: reads Parquet metadata, not the raw TSV.
    out_rows = spark.read.parquet(str(config.REVISIONS_PARQUET)).count()
    print(f"  revision rows written: {out_rows:,}")

    save_metrics("p00_ingest", {
        "wiki": config.WIKI,
        "snapshot": config.SNAPSHOT,
        "raw_rows": total,
        "entity_counts": entity_counts,
        "revision_rows": out_rows,
        "columns_kept": len(schema.REVISION_COLUMNS),
    })
    spark.stop()


if __name__ == "__main__":
    main()
