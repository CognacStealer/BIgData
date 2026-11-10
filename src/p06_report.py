"""
Phase 6: consolidate metrics into the tables and figures the report needs.
Reads only the JSON/parquet artefacts produced by earlier phases.
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config
from spark_utils import banner


def load(name):
    p = config.METRICS / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def fig_classification(m):
    rows = []
    for key, r in m["results"].items():
        model, feat = key.split("__")
        rows.append({"model": model, "features": feat, **r})
    df = pd.DataFrame(rows)
    df.to_csv(config.METRICS / "classification_comparison.csv", index=False)

    metrics = ["roc_auc", "pr_auc", "accuracy", "f1", "bot_precision", "bot_recall"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, met in zip(axes.ravel(), metrics):
        piv = df.pivot(index="model", columns="features", values=met)
        piv.plot(kind="bar", ax=ax, rot=20, legend=(met == "roc_auc"))
        ax.set_title(met); ax.set_ylim(0, 1.02); ax.grid(axis="y", alpha=.3)
        ax.set_xlabel("")
    fig.suptitle("Phase 6: classification model comparison (label_bot)")
    fig.tight_layout()
    fig.savefig(config.FIGURES / "classification_comparison.png", dpi=130)
    plt.close(fig)
    return df


def fig_roc():
    try:
        import pyarrow.parquet as pq
        t = pq.read_table(str(config.DATA_FEATURES / "roc_input")).to_pandas()
    except Exception as e:
        print(f"  (skipping ROC figure: {e})")
        return
    from sklearn.metrics import (precision_recall_curve, roc_curve, auc,
                                 average_precision_score)
    y, s = t["label_bot"].values, t["p_bot"].values
    fpr, tpr, _ = roc_curve(y, s)
    pr, rc, _ = precision_recall_curve(y, s)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
    ax[0].plot(fpr, tpr, lw=2, label=f"AUC={auc(fpr,tpr):.4f}")
    ax[0].plot([0, 1], [0, 1], "k--", lw=1)
    ax[0].set(xlabel="FPR", ylabel="TPR", title="ROC — GBT (full features)")
    ax[0].legend(); ax[0].grid(alpha=.3)
    ax[1].plot(rc, pr, lw=2, label=f"AP={average_precision_score(y,s):.4f}")
    ax[1].set(xlabel="Recall", ylabel="Precision", title="Precision–Recall")
    ax[1].legend(); ax[1].grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(config.FIGURES / "roc_pr_curves.png", dpi=130)
    plt.close(fig)


def fig_clustering(m):
    sweep = m["sweep"]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for algo, ks in sweep.items():
        # degenerate fits store silhouette=None; drop them from the curve
        pts = [(int(k), ks[k]["silhouette"]) for k in ks
               if ks[k].get("silhouette") is not None]
        if not pts:
            continue
        pts.sort()
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", label=algo)
    ax.set(xlabel="k", ylabel="silhouette",
           title="Phase 6: clustering quality vs k")
    ax.legend(); ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(config.FIGURES / "clustering_silhouette.png", dpi=130)
    plt.close(fig)

    prof = pd.DataFrame(m["cluster_profiles"])
    if not prof.empty:
        fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
        ax[0].bar(prof["cluster"].astype(str), prof["n_editors"])
        ax[0].set(title="cluster sizes", xlabel="cluster", ylabel="editors")
        ax[0].set_yscale("log")
        ax[1].bar(prof["cluster"].astype(str), prof["bot_share"], color="darkorange")
        ax[1].set(title="bot share per cluster (external validation)",
                  xlabel="cluster", ylabel="share flagged bot", ylim=(0, 1))
        for a in ax: a.grid(axis="y", alpha=.3)
        fig.tight_layout()
        fig.savefig(config.FIGURES / "cluster_composition.png", dpi=130)
        plt.close(fig)


def fig_svd(m):
    s = np.array(m["singular_values"], dtype=float)
    energy = np.cumsum(s ** 2) / (s ** 2).sum()
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].plot(range(1, len(s) + 1), s, marker="o")
    ax[0].set(title="SVD singular values (comment TF-IDF)",
              xlabel="component", ylabel="σ")
    ax[1].plot(range(1, len(s) + 1), energy, marker="o", color="green")
    ax[1].set(title="cumulative energy captured", xlabel="component",
              ylabel="fraction", ylim=(0, 1.02))
    for a in ax: a.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(config.FIGURES / "svd_spectrum.png", dpi=130)
    plt.close(fig)


def main():
    banner("PHASE 6: consolidated results")
    summary = {}

    ing, prep = load("p00_ingest"), load("p03_prepare")
    feat = load("p04_features")
    clf, clu = load("p05_classification"), load("p05_clustering")

    if prep:
        print(f"  dataset: {prep['rows_final']:,} edits | "
              f"bot rate {100*prep['bot_rate']:.2f}% | "
              f"revert rate {100*prep['reverted_rate']:.2f}%")
        summary["dataset"] = prep
    if feat:
        fig_svd(feat)
        print(f"  features: {feat['n_numeric_edit_features']} numeric + "
              f"{feat['svd_k']} SVD dims | {feat['n_editors']:,} editors")
    if clf:
        df = fig_classification(clf)
        fig_roc()
        print("\n  classification results:")
        print(df[["model", "features", "roc_auc", "pr_auc", "accuracy",
                  "f1", "bot_precision", "bot_recall"]]
              .sort_values("roc_auc", ascending=False).to_string(index=False))
        summary["best_classifier"] = clf["best_model"]
    if clu:
        fig_clustering(clu)
        print(f"\n  clustering best: {clu['best']} "
              f"silhouette={clu['best_silhouette']:.4f} "
              f"purity={clu['bot_purity']:.4f}")
        summary["best_clustering"] = clu["best"]

    (config.METRICS / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n  figures -> {config.FIGURES}")
    print(f"  tables  -> {config.METRICS}")


if __name__ == "__main__":
    main()
