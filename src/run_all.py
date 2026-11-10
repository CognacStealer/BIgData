"""Run every phase in order. `python src/run_all.py [--from N]`"""
import argparse
import subprocess
import sys
from pathlib import Path

PHASES = [
    ("p00_ingest",        "Phase 0: TSV -> Parquet"),
    ("p03_prepare",       "Phase 3: Data preparation"),
    ("p04_features",      "Phase 4: Feature engineering + SVD"),
    ("p05_classification","Phase 5a: Classification"),
    ("p05_clustering",    "Phase 5b: Clustering"),
    ("p06_report",        "Phase 6: Figures and tables"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0, help="index to start from")
    ap.add_argument("--only", type=str, default=None)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    todo = PHASES[args.start:]
    if args.only:
        todo = [p for p in PHASES if p[0] == args.only]

    for mod, desc in todo:
        print(f"\n### {desc}  ({mod})", flush=True)
        # -u: unbuffered, so progress is visible when output is redirected to a log
        rc = subprocess.call([sys.executable, "-u", str(root / f"{mod}.py")])
        if rc != 0:
            sys.exit(f"FAILED at {mod} (exit {rc})")
    print("\nAll phases complete.")

if __name__ == "__main__":
    main()
