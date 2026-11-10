"""
Live EventStreams collector -- for the PRESENTATION demo (not the batch pipeline).

Connects to the Wikimedia recentchange SSE firehose and appends newline-JSON.
Useful for showing the trained model scoring edits as they happen.

  python src/stream_collector.py --minutes 5 --out data/raw/live.jsonl
"""
import argparse
import json
import time
from pathlib import Path

import requests

URL = "https://stream.wikimedia.org/v2/stream/recentchange"
UA = "MMD-term-project/1.0 (student coursework; contact via course staff)"

KEEP = ("wiki", "type", "namespace", "title", "comment", "timestamp",
        "user", "bot", "minor", "patrolled", "server_name")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=2.0)
    ap.add_argument("--out", default="data/raw/live.jsonl")
    ap.add_argument("--wiki", default=None, help="filter to one wiki, e.g. simplewiki")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + args.minutes * 60
    n = kept = 0

    with requests.get(URL, headers={"User-Agent": UA}, stream=True, timeout=60) as r:
        r.raise_for_status()
        with out.open("w") as fh:
            for line in r.iter_lines(decode_unicode=True):
                if time.time() > deadline:
                    break
                if not line or not line.startswith("data: "):
                    continue
                n += 1
                try:
                    ev = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if args.wiki and ev.get("wiki") != args.wiki:
                    continue
                rec = {k: ev.get(k) for k in KEEP}
                rec["length_old"] = (ev.get("length") or {}).get("old")
                rec["length_new"] = (ev.get("length") or {}).get("new")
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                kept += 1
                if kept % 500 == 0:
                    print(f"  {kept:,} kept / {n:,} seen", flush=True)

    print(f"done: {kept:,} events -> {out}")


if __name__ == "__main__":
    main()
