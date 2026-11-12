"""
Spark Structured Streaming over a replay of the edit history.

A producer thread writes batches of real edits as JSON files into a watch
directory; the stream reads that directory as a *file source* and processes
each batch as it lands. The file source is a genuine Structured Streaming
source -- it discovers new files per trigger, tracks offsets in a checkpoint,
and is restartable. We use it instead of a socket because a socket source is
not fault-tolerant and dies with the producer, which makes a headless run
flaky.

Two queries run against the same stream:
  1. foreachBatch -- per-batch counts and running totals (console-style output)
  2. a windowed aggregation with a watermark -- bot share per event-time window

  source env.sh && python src/pe_streaming.py --batches 20 --rows 10000
"""
import argparse
import json
import shutil
import threading
import time
from pathlib import Path

from pyspark.sql import functions as F
from pyspark.sql.types import (IntegerType, LongType, StringType, StructField,
                               StructType, TimestampType)

import config
from spark_utils import banner, get_spark, save_metrics

STREAM_IN = config.ROOT / "data" / "stream_in"
CHECKPOINT = config.ROOT / "data" / "stream_ckpt"

SCHEMA = StructType([
    StructField("revision_id", LongType()),
    StructField("event_timestamp", TimestampType()),
    StructField("page_namespace", IntegerType()),
    StructField("label_bot", IntegerType()),
    StructField("label_reverted", IntegerType()),
    StructField("revision_text_bytes_diff", LongType()),
    StructField("actor_key", StringType()),
])

STATE = {"batches": [], "running": {"rows": 0, "bot": 0, "reverted": 0}}


def producer(spark, n_batches, rows_per_batch, delay):
    """Write real edits into the watch directory, one file per batch."""
    # The prepared dataset is PARTITIONED BY label_bot, so a plain .limit()
    # reads whole partition directories and returns only label_bot=0 rows --
    # the replay then contains zero bots. Sample across all partitions first,
    # then replay in event-time order so the windowed aggregation downstream
    # sees a sensible chronology.
    need = n_batches * rows_per_batch
    base = (spark.read.parquet(str(config.DATA_PARQUET / "prepared"))
            .select(*[f.name for f in SCHEMA.fields]))
    total = base.count()
    frac = min(1.0, (need * 2.5) / total)
    src = (base.sample(False, frac, seed=config.SEED)
               .orderBy("event_timestamp")
               .limit(need))
    pdf = src.toPandas()
    print(f"  [producer] sampled {len(pdf):,} edits "
          f"({100*pdf['label_bot'].mean():.1f}% bot)", flush=True)
    STREAM_IN.mkdir(parents=True, exist_ok=True)
    for i in range(n_batches):
        chunk = pdf.iloc[i * rows_per_batch:(i + 1) * rows_per_batch]
        if chunk.empty:
            break
        tmp = STREAM_IN / f".burst_{i:03d}.tmp"
        final = STREAM_IN / f"burst_{i:03d}.json"
        chunk.to_json(tmp, orient="records", lines=True, date_format="iso")
        tmp.rename(final)          # atomic: the stream never sees a part-file
        print(f"  [producer] burst {i} ({len(chunk):,} edits)", flush=True)
        time.sleep(delay)


def per_batch(df, batch_id):
    rows = df.count()
    if rows == 0:
        return
    agg = df.agg(F.sum("label_bot").alias("bot"),
                 F.sum("label_reverted").alias("rev"),
                 F.avg("revision_text_bytes_diff").alias("avg_diff")).collect()[0]
    STATE["running"]["rows"] += rows
    STATE["running"]["bot"] += int(agg["bot"] or 0)
    STATE["running"]["reverted"] += int(agg["rev"] or 0)
    rec = {
        "batch_id": batch_id, "rows": rows,
        "bot": int(agg["bot"] or 0), "reverted": int(agg["rev"] or 0),
        "bot_rate": (agg["bot"] or 0) / rows,
        "avg_bytes_diff": float(agg["avg_diff"] or 0.0),
        "running_rows": STATE["running"]["rows"],
        "running_bot_rate": STATE["running"]["bot"] / STATE["running"]["rows"],
    }
    STATE["batches"].append(rec)
    print(f"  BATCH {batch_id}: rows={rows:,} bot={rec['bot']:,} "
          f"({100*rec['bot_rate']:.1f}%) | running bot rate "
          f"{100*rec['running_bot_rate']:.2f}%", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=int, default=20)
    ap.add_argument("--rows", type=int, default=10000)
    ap.add_argument("--delay", type=float, default=2.0)
    args = ap.parse_args()

    for d in (STREAM_IN, CHECKPOINT):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    spark = get_spark("pe_streaming")
    banner("STRUCTURED STREAMING")
    print(f"  replaying {args.batches} bursts x {args.rows:,} edits "
          f"every {args.delay}s into {STREAM_IN}")

    t = threading.Thread(target=producer,
                         args=(spark, args.batches, args.rows, args.delay),
                         daemon=True)
    t.start()

    stream = (spark.readStream
              .schema(SCHEMA)                      # explicit: no inference on a stream
              .option("maxFilesPerTrigger", 1)     # one burst per micro-batch
              .json(str(STREAM_IN)))

    q1 = (stream.writeStream
          .foreachBatch(per_batch)
          .option("checkpointLocation", str(CHECKPOINT / "q1"))
          .trigger(processingTime="2 seconds")
          .start())

    # windowed aggregation over EVENT time, with a watermark for late data
    windowed = (stream
                .withWatermark("event_timestamp", "365 days")
                .groupBy(F.window("event_timestamp", "365 days"))
                .agg(F.count("*").alias("edits"),
                     F.avg("label_bot").alias("bot_share")))
    q2 = (windowed.writeStream
          .outputMode("complete")
          .format("memory").queryName("per_window")
          .option("checkpointLocation", str(CHECKPOINT / "q2"))
          .trigger(processingTime="2 seconds")
          .start())

    t.join()
    deadline = time.time() + 60
    while time.time() < deadline:
        if (STATE["running"]["rows"] >= args.batches * args.rows
                and not q1.status["isDataAvailable"]):
            break
        time.sleep(2)
    q1.stop(); q2.stop()

    win = spark.sql(
        "SELECT date_format(window.start,'yyyy') AS yr, edits, bot_share "
        "FROM per_window ORDER BY yr").collect()
    windows = [{"year": r["yr"], "edits": r["edits"],
                "bot_share": float(r["bot_share"])} for r in win]
    print(f"\n  event-time windows produced: {len(windows)}")
    for w in windows[:6]:
        print(f"    {w['year']}: {w['edits']:,} edits, "
              f"bot share {100*w['bot_share']:.1f}%")

    save_metrics("pe_streaming", {
        "source": "file source (JSON), maxFilesPerTrigger=1",
        "trigger": "processingTime=2 seconds",
        "bursts": args.batches, "rows_per_burst": args.rows,
        "batches_processed": len(STATE["batches"]),
        "rows_processed": STATE["running"]["rows"],
        "running_bot_rate": (STATE["running"]["bot"] /
                             max(STATE["running"]["rows"], 1)),
        "running_reverted_rate": (STATE["running"]["reverted"] /
                                  max(STATE["running"]["rows"], 1)),
        "batches": STATE["batches"],
        "event_time_windows": windows,
    })
    spark.stop()


if __name__ == "__main__":
    main()
