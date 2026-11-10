"""Shared Spark session factory and small helpers."""
# Force line-buffered stdout: these scripts are usually run with output
# redirected to a log file, where Python would otherwise block-buffer and show
# nothing until the process exits. (Run with `python -u` for the same effect.)
import sys as _sys
try:
    _sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass
import json
import time
from contextlib import contextmanager

from pyspark.sql import SparkSession

import config


def get_spark(app_name: str) -> SparkSession:
    builder = SparkSession.builder.master(config.MASTER).appName(app_name)
    for k, v in config.SPARK_CONF.items():
        builder = builder.config(k, v)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark


@contextmanager
def timed(label: str):
    t0 = time.time()
    print(f"[{label}] start", flush=True)
    yield
    print(f"[{label}] done in {time.time() - t0:.1f}s", flush=True)


def save_metrics(name: str, payload: dict) -> None:
    out = config.METRICS / f"{name}.json"
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  -> wrote {out}")


def banner(text: str) -> None:
    print("\n" + "=" * 72 + f"\n{text}\n" + "=" * 72, flush=True)
