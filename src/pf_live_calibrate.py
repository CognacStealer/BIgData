"""
Choose the decision threshold for the live model, instead of assuming 0.5.

A classifier outputs a probability; turning that into a yes/no needs a cutoff.
Spark's `prediction` column hardcodes 0.5, which is the wrong cutoff whenever
the positive class is not ~50% of the data. On this corpus bots are 23.7% of
edits, so the model rarely reaches 0.5 and predicts "human" almost always --
high ROC-AUC, useless decisions.

This sweeps the held-out test set and picks the cutoff that maximises bot-F1,
then saves it beside the model so the live scorer uses it.

  source env.sh && python src/pf_live_calibrate.py
"""
import argparse
import json
import time

import requests
from pyspark.ml import PipelineModel
from pyspark.ml.functions import vector_to_array
from pyspark.sql import functions as F

import config
from live_features import add_live_features
from spark_utils import banner, get_spark, save_metrics

MODEL_DIR = config.ROOT / "models" / "live_bot_rf"
THRESH_FILE = MODEL_DIR / "threshold.json"
URL = "https://stream.wikimedia.org/v2/stream/recentchange"
UA = "MMD-term-project/1.0 (student coursework; contact via course staff)"


def collect_live(spark, minutes):
    """Calibration set drawn from the LIVE feed.

    The model is trained on simplewiki, but the feed carries all ~900 wikis --
    Commons, Wikidata, arwiki and so on -- where bot behaviour differs. That is
    a genuine distribution shift, so the operating point has to be chosen on
    the population the model will actually score. The feed supplies its own
    `bot` flag, so this is a labelled calibration set, not training data.
    """
    rows, deadline = [], time.time() + minutes * 60
    with requests.get(URL, headers={"User-Agent": UA},
                      stream=True, timeout=60) as r:
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if time.time() > deadline:
                break
            if not line or not line.startswith("data: "):
                continue
            try:
                ev = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if ev.get("type") != "edit":
                continue
            ln = ev.get("length") or {}
            rows.append((
                time.strftime("%Y-%m-%d %H:%M:%S",
                              time.gmtime(ev.get("timestamp", 0))),
                int(ev.get("namespace") or 0), bool(ev.get("minor")),
                ev.get("comment") or "", ln.get("old"), ln.get("new"),
                ev.get("user") or "", bool(ev.get("bot"))))
            if len(rows) % 500 == 0:
                print(f"    collected {len(rows):,}", flush=True)
    print(f"  collected {len(rows):,} live edits")
    return spark.createDataFrame(
        rows, "ts string, namespace int, minor boolean, comment string, "
              "length_old long, length_new long, user string, bot boolean"
    ).withColumn("ts", F.to_timestamp("ts"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["dump", "live"], default="live",
                    help="population to calibrate the operating point on")
    ap.add_argument("--minutes", type=float, default=2.0)
    args = ap.parse_args()

    spark = get_spark("pf_live_calibrate")
    banner(f"CALIBRATE DECISION THRESHOLD ({args.source})")
    model = PipelineModel.load(str(MODEL_DIR))

    if args.source == "live":
        raw = collect_live(spark, args.minutes)
        test = add_live_features(raw)
        scored = (model.transform(test)
                  .select("label_bot", vector_to_array("probability")[1].alias("p"))
                  .cache())
        n = scored.count()
        print(f"  calibration rows: {n:,} "
              f"({100 * scored.agg(F.avg('label_bot')).collect()[0][0]:.1f}% bot)")
        return finish(spark, scored, n, args.source)

    src = (spark.read.parquet(str(config.DATA_PARQUET / "prepared"))
           .select(
               F.col("event_timestamp").alias("ts"),
               F.col("page_namespace").alias("namespace"),
               F.col("revision_minor_edit").cast("int").alias("minor"),
               F.col("event_comment").alias("comment"),
               (F.col("revision_text_bytes") - F.col("revision_text_bytes_diff"))
                   .alias("length_old"),
               F.col("revision_text_bytes").alias("length_new"),
               F.col("event_user_text").alias("user"),
               F.col("label_bot").alias("bot"),
               F.col("actor_key")))
    df = add_live_features(src)
    bucket = F.abs(F.hash(F.concat(F.col("actor_key"),
                                   F.lit(str(config.SEED))))) % 100
    test = df.withColumn("_b", bucket).filter(F.col("_b") >= 80).drop("_b")

    scored = (model.transform(test)
              .select("label_bot", vector_to_array("probability")[1].alias("p"))
              .cache())
    n = scored.count()
    print(f"  scoring {n:,} held-out rows")
    return finish(spark, scored, n, args.source)


def finish(spark, scored, n, source):
    rows = []
    for t in [i / 100 for i in range(2, 71, 2)]:
        agg = scored.agg(
            F.sum(((F.col("p") >= t) & (F.col("label_bot") == 1)).cast("int")).alias("tp"),
            F.sum(((F.col("p") >= t) & (F.col("label_bot") == 0)).cast("int")).alias("fp"),
            F.sum(((F.col("p") < t) & (F.col("label_bot") == 1)).cast("int")).alias("fn"),
        ).collect()[0]
        tp, fp, fn = agg["tp"] or 0, agg["fp"] or 0, agg["fn"] or 0
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        rows.append({"threshold": t, "precision": prec, "recall": rec, "f1": f1})
        print(f"    t={t:.2f}  precision {prec:.4f}  recall {rec:.4f}  F1 {f1:.4f}")

    best = max(rows, key=lambda r: r["f1"])
    print(f"\n  BEST threshold {best['threshold']:.2f} "
          f"-> F1 {best['f1']:.4f} (precision {best['precision']:.4f}, "
          f"recall {best['recall']:.4f})")
    at_half = next(r for r in rows if abs(r["threshold"] - 0.50) < 1e-9)
    print(f"  default 0.50 would give F1 {at_half['f1']:.4f} "
          f"(recall {at_half['recall']:.4f})")

    THRESH_FILE.write_text(json.dumps(
        {"threshold": best["threshold"], "calibrated_on": source}, indent=2))
    print(f"  saved -> {THRESH_FILE}")
    save_metrics(f"pf_live_calibrate_{source}", {
        "calibrated_on": source,
        "chosen_threshold": best["threshold"], "best": best,
        "at_default_0_5": at_half, "sweep": rows, "n_test": n})
    spark.stop()


if __name__ == "__main__":
    main()
