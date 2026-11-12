"""
Render the two diagrams the Assignment 2 brief names as deliverables:

  Part A -> Spark architecture diagram  (driver, cluster manager, executors)
  Part D -> analytics workflow diagram  (Input -> RDD -> DataFrame -> Output)

Written as figures rather than ASCII so they embed in the report and the deck.

  source env.sh && python src/make_diagrams.py
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

import config

BLUE, DARK, ORANGE, GREY = "#4472C4", "#1F3864", "#ED7D31", "#767171"
FILL, FILL2 = "#DEE7F7", "#FBE5D6"


def box(ax, x, y, w, h, title, lines, fill=FILL, edge=BLUE, fs=8.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012",
                                linewidth=1.3, edgecolor=edge, facecolor=fill))
    ax.text(x + w / 2, y + h - 0.045, title, ha="center", va="top",
            fontsize=fs + 1.2, fontweight="bold", color=DARK)
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.098 - i * 0.044, ln, ha="center", va="top",
                fontsize=fs, color="#333333")


def arrow(ax, p, q, color=GREY, style="-|>"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=13,
                                 linewidth=1.3, color=color,
                                 shrinkA=2, shrinkB=2))


def architecture():
    fig, ax = plt.subplots(figsize=(10.5, 6.0))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # title first, with the boxes starting well below it
    ax.text(0.50, 0.985,
            "Spark Architecture — this project runs local[*] on 12 cores:",
            ha="center", va="top", fontsize=10.5, fontweight="bold", color=DARK)
    ax.text(0.50, 0.935, "driver and executors are threads inside one JVM",
            ha="center", va="top", fontsize=9, style="italic", color=GREY)

    box(ax, 0.28, 0.655, 0.44, 0.235, "DRIVER PROGRAM",
        ["SparkSession / SparkContext",
         "builds the DAG, splits stages at shuffles",
         "broadcasts the SVD matrix V (2048 x 24)"])

    box(ax, 0.28, 0.415, 0.44, 0.165, "CLUSTER MANAGER",
        ["Spark's built-in local scheduler",
         "(YARN / Kubernetes / Standalone on a cluster)"],
        fill=FILL2, edge=ORANGE)

    for i, x in enumerate([0.025, 0.365, 0.705]):
        box(ax, x, 0.145, 0.27, 0.205, f"EXECUTOR {i + 1}",
            ["runs tasks on partitions", "caches / persists data",
             "returns results to driver"])

    arrow(ax, (0.50, 0.655), (0.50, 0.582))
    ax.text(0.515, 0.622, "1. request resources", fontsize=8, color=GREY)
    for x in (0.16, 0.50, 0.84):
        arrow(ax, (0.50, 0.415), (x, 0.352))
    ax.text(0.695, 0.388, "2. launch executors / send tasks",
            fontsize=8, color=GREY)

    ax.add_patch(FancyBboxPatch((0.025, 0.015), 0.95, 0.085,
                                boxstyle="round,pad=0.012", linewidth=1.2,
                                edgecolor=GREY, facecolor="#F2F2F2"))
    ax.text(0.50, 0.058,
            "STORAGE   simplewiki.all-time.tsv.bz2 (951 MB)  ->  "
            "data/parquet/  ->  data/features/     (HDFS or S3 on a cluster)",
            ha="center", va="center", fontsize=8.5, color=DARK)

    fig.savefig(config.FIGURES / "spark_architecture.png", dpi=150,
                bbox_inches="tight"); plt.close(fig)
    return config.FIGURES / "spark_architecture.png"


def workflow(ing, rdd, prep, sql, clf):
    fig, ax = plt.subplots(figsize=(11.5, 4.2))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    stages = [
        (0.015, "INPUT DATA", [f"{ing['raw_rows']:,} dump rows",
                               "951 MB bz2 TSV", "78 columns"], FILL2, ORANGE),
        (0.268, "RDD PROCESSING", [f"textFile -> {rdd['num_partitions']} partitions",
                                   "map / filter / flatMap",
                                   "reduceByKey, persist"], FILL, BLUE),
        (0.521, "DATAFRAME PROCESSING", [f"{ing['columns_kept']} of 78 cols -> Parquet",
                                         f"clean -> {prep['rows_final']:,} rows",
                                         "groupBy / agg / Spark SQL"], FILL, BLUE),
        (0.774, "ANALYTICAL OUTPUT", [f"{rdd['total_comment_tokens']:,} tokens",
                                      "namespace + revert rates",
                                      f"MLlib ROC-AUC {clf:.4f}"], FILL2, ORANGE),
    ]
    for x, title, lines, fill, edge in stages:
        box(ax, x, 0.36, 0.211, 0.37, title, lines, fill=fill, edge=edge, fs=8.5)
    for x in (0.226, 0.479, 0.732):
        arrow(ax, (x, 0.545), (x + 0.040, 0.545))

    ax.text(0.5, 0.27, "every stage persists Parquet, so any stage re-runs alone",
            ha="center", fontsize=8.5, style="italic", color=GREY)
    ax.text(0.5, 0.15,
            "pb_rdd.py          p00_ingest.py -> p03_prepare.py -> pc_sql.py / "
            "p04_features.py -> p05_*.py          reports/metrics/*.json",
            ha="center", fontsize=8, color=DARK, family="monospace")
    ax.text(0.5, 0.95, "Spark Analytics Workflow (Part D)",
            ha="center", va="top", fontsize=10.5, fontweight="bold", color=DARK)
    fig.tight_layout()
    out = config.FIGURES / "spark_workflow.png"
    fig.savefig(out, dpi=150, bbox_inches="tight"); plt.close(fig)
    return out


def main():
    j = lambda n: json.loads((config.METRICS / f"{n}.json").read_text())
    ing, rdd, prep, sql = j("p00_ingest"), j("pb_rdd"), j("p03_prepare"), j("pc_sql")
    clf = j("p05_classification")
    best = clf["results"][clf["best_model"]]["roc_auc"]
    print(" ", architecture())
    print(" ", workflow(ing, rdd, prep, sql, best))


if __name__ == "__main__":
    main()
