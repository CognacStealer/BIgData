"""
LIVE DEMO: classify real Wikimedia edits as they happen.

A producer thread holds an SSE connection to the Wikimedia Recent Changes feed
and rotates completed JSON files into a watch directory. Spark Structured
Streaming reads that directory as a file source and, inside foreachBatch,
applies the saved PipelineModel to every arriving edit.

Because the feed carries its own `bot` flag, each prediction is scored against
ground truth the instant it is made, and a running accuracy is displayed.

  source env.sh && python src/pf_live_demo.py --minutes 3
"""
import argparse
import json
import shutil
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import requests
from pyspark.ml import PipelineModel
from pyspark.ml.functions import vector_to_array
from pyspark.sql import functions as F
from pyspark.sql.types import (BooleanType, LongType, StringType, StructField,
                               StructType)

import config
from live_features import add_live_features
from spark_utils import get_spark

URL = "https://stream.wikimedia.org/v2/stream/recentchange"
UA = "MMD-term-project/1.0 (student coursework; contact via course staff)"
MODEL_DIR = config.ROOT / "models" / "live_bot_rf"
THRESH_FILE = MODEL_DIR / "threshold.json"
WATCH = config.ROOT / "data" / "live_in"
CKPT = config.ROOT / "data" / "live_ckpt"

SCHEMA = StructType([
    StructField("ts", StringType()), StructField("namespace", LongType()),
    StructField("minor", BooleanType()), StructField("comment", StringType()),
    StructField("length_old", LongType()), StructField("length_new", LongType()),
    StructField("user", StringType()), StructField("bot", BooleanType()),
    StructField("wiki", StringType()), StructField("title", StringType()),
])

C = {"g": "\033[92m", "r": "\033[91m", "y": "\033[93m", "b": "\033[94m",
     "d": "\033[90m", "B": "\033[1m", "0": "\033[0m"}
STATE = {"n": 0, "correct": 0, "cm": Counter(), "batches": 0, "stop": False}


def rule(ch="─", n=100):
    return C["d"] + ch * n + C["0"]


def producer(minutes, per_file, delay):
    """Hold the SSE connection; rotate completed JSON files into WATCH."""
    deadline = time.time() + minutes * 60
    buf, fileno = [], 0
    try:
        with requests.get(URL, headers={"User-Agent": UA},
                          stream=True, timeout=60) as r:
            r.raise_for_status()
            print(f"{C['g']}  [feed] connected to {URL}{C['0']}", flush=True)
            for line in r.iter_lines(decode_unicode=True):
                if time.time() > deadline or STATE["stop"]:
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
                buf.append({
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S",
                                        time.gmtime(ev.get("timestamp", 0))),
                    "namespace": ev.get("namespace"),
                    "minor": bool(ev.get("minor")),
                    "comment": ev.get("comment") or "",
                    "length_old": ln.get("old"), "length_new": ln.get("new"),
                    "user": ev.get("user") or "", "bot": bool(ev.get("bot")),
                    "wiki": ev.get("wiki") or "", "title": ev.get("title") or "",
                })
                if len(buf) >= per_file:
                    tmp = WATCH / f".b{fileno:04d}.tmp"
                    tmp.write_text("\n".join(json.dumps(x, ensure_ascii=False)
                                             for x in buf), encoding="utf8")
                    tmp.rename(WATCH / f"b{fileno:04d}.json")  # atomic
                    print(f"{C['d']}  [feed] rotated batch {fileno} "
                          f"({len(buf)} edits){C['0']}", flush=True)
                    buf, fileno = [], fileno + 1
                    time.sleep(delay)
    except Exception as e:
        print(f"{C['r']}  [feed] stopped: {e}{C['0']}", flush=True)
    STATE["stop"] = True


def load_threshold():
    """Spark's `prediction` column hardcodes 0.5, which is the wrong cutoff for
    a 23.7%-positive class -- it makes the model answer "human" to everything.
    Use the F1-optimal cutoff chosen by src/pf_live_calibrate.py."""
    if THRESH_FILE.exists():
        return float(json.loads(THRESH_FILE.read_text())["threshold"])
    print(f"{C['y']}  [warn] no threshold.json; falling back to 0.5 "
          f"(run: make live-calibrate){C['0']}", flush=True)
    return 0.5


def make_handler(model, show, thresh):
    def handle(batch_df, batch_id):
        if batch_df.rdd.isEmpty():
            return
        feats = add_live_features(batch_df)
        scored = (model.transform(feats)
                  .withColumn("p_bot", vector_to_array("probability")[1])
                  .withColumn("pred_bot", (F.col("p_bot") >= thresh).cast("int"))
                  .select("wiki", "title", "user", "comment", "bot",
                          "pred_bot", "p_bot")
                  .collect())
        STATE["batches"] += 1
        print(rule())
        print(f"{C['B']}  MICRO-BATCH {STATE['batches']}  "
              f"— {len(scored)} live edits scored{C['0']}")
        print(rule())
        for r in scored[:show]:
            truth, pred = bool(r["bot"]), bool(int(r["pred_bot"]))
            ok = truth == pred
            STATE["n"] += 1
            STATE["correct"] += int(ok)
            STATE["cm"][(truth, pred)] += 1
            mark = f"{C['g']}✓{C['0']}" if ok else f"{C['r']}✗{C['0']}"
            plabel = f"{C['y']}BOT  {C['0']}" if pred else f"{C['b']}HUMAN{C['0']}"
            tlabel = "bot" if truth else "human"
            print(f"  {mark} predict {plabel} p={r['p_bot']:.3f}  "
                  f"actual={tlabel:<5} {C['d']}{r['wiki'][:12]:<12}"
                  f"{(r['user'] or '')[:18]:<18} {(r['title'] or '')[:34]}{C['0']}")
        for r in scored[show:]:          # count the rest without printing
            truth, pred = bool(r["bot"]), bool(int(r["pred_bot"]))
            STATE["n"] += 1
            STATE["correct"] += int(truth == pred)
            STATE["cm"][(truth, pred)] += 1
        acc = STATE["correct"] / max(STATE["n"], 1)
        print(f"{C['B']}  running: {STATE['n']:,} edits classified | "
              f"accuracy {100*acc:.1f}%{C['0']}", flush=True)
    return handle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--per-file", type=int, default=25)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--show", type=int, default=8, help="rows printed per batch")
    args = ap.parse_args()

    if not MODEL_DIR.exists():
        sys.exit(f"no saved model at {MODEL_DIR}\nRun: make live-train")

    for d in (WATCH, CKPT):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    spark = get_spark("pf_live_demo")
    print()
    print(rule("═"))
    print(f"{C['B']}  LIVE BOT CLASSIFICATION — Wikimedia EventStreams{C['0']}")
    print(rule("═"))
    print(f"  model   : {MODEL_DIR}")
    print(f"  source  : {URL}")
    print(f"  duration: {args.minutes:g} min   batch size: {args.per_file} edits")
    print(rule("═"), flush=True)

    model = PipelineModel.load(str(MODEL_DIR))
    thresh = load_threshold()
    print(f"  decision threshold: {thresh:.2f}  "
          f"{C['d']}(F1-optimal, not the 0.5 default){C['0']}")
    print(rule("═"), flush=True)

    t = threading.Thread(target=producer,
                         args=(args.minutes, args.per_file, args.delay),
                         daemon=True)
    t.start()

    q = (spark.readStream.schema(SCHEMA)
         .option("maxFilesPerTrigger", 1).json(str(WATCH))
         .writeStream.foreachBatch(make_handler(model, args.show, thresh))
         .option("checkpointLocation", str(CKPT))
         .trigger(processingTime="2 seconds").start())

    t.join()
    deadline = time.time() + 20
    while time.time() < deadline and q.status["isDataAvailable"]:
        time.sleep(2)
    q.stop()

    n = max(STATE["n"], 1)
    tp, fp = STATE["cm"][(True, True)], STATE["cm"][(False, True)]
    fn, tn = STATE["cm"][(True, False)], STATE["cm"][(False, False)]
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    print()
    print(rule("═"))
    print(f"{C['B']}  FINAL — {STATE['n']:,} live edits classified in "
          f"{STATE['batches']} micro-batches{C['0']}")
    print(rule("═"))
    print(f"  accuracy        {100*STATE['correct']/n:6.2f}%")
    print(f"  bot precision   {100*prec:6.2f}%     bot recall {100*rec:6.2f}%")
    print(f"  confusion       TP {tp:<5} FP {fp:<5} FN {fn:<5} TN {tn}")
    print(rule("═"))
    print(flush=True)
    spark.stop()


if __name__ == "__main__":
    main()
