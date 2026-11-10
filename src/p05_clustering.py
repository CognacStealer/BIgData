"""
Phase 5b + 6: MLlib Clustering on editor behaviour profiles.

Compares KMeans, BisectingKMeans and GaussianMixture over a k sweep, selects k
by silhouette, then CHARACTERISES the winning clusters -- the interpretation is
the deliverable, not the silhouette number.

The bot flag (`e_is_bot`) is deliberately NOT a clustering input. It is used
only afterwards, as external validation: if an unsupervised partition of pure
behaviour features recovers the automation boundary, that is strong evidence
the engineered features capture real structure.
"""
import pandas as pd
from pyspark.ml import Pipeline
from pyspark.ml.clustering import BisectingKMeans, GaussianMixture, KMeans
from pyspark.ml.evaluation import ClusteringEvaluator
from pyspark.ml.feature import StandardScaler, VectorAssembler
from pyspark.sql import functions as F

import config
from p04_features import EDITOR_FEATURES
from spark_utils import banner, get_spark, save_metrics, timed

# Editors with a single edit have no inter-edit gap and dominate the long tail;
# they would form one meaningless mega-cluster. Require a minimum activity.
MIN_EDITS = 5


def prep(df):
    asm = VectorAssembler(inputCols=EDITOR_FEATURES, outputCol="raw",
                          handleInvalid="keep")
    sca = StandardScaler(inputCol="raw", outputCol="features",
                         withMean=True, withStd=True)
    return Pipeline(stages=[asm, sca]).fit(df).transform(df).cache()


def main():
    spark = get_spark("p05_clustering")
    banner("PHASE 5b + 6: Clustering (editor behaviour)")

    df = spark.read.parquet(str(config.EDITOR_FEATURES))
    n_all = df.count()
    df = df.filter(F.col("e_n_edits") >= MIN_EDITS)
    n = df.count()
    print(f"  editors: {n_all:,} total -> {n:,} with >= {MIN_EDITS} edits")

    data = prep(df)
    ev = ClusteringEvaluator(featuresCol="features", predictionCol="cluster",
                             metricName="silhouette",
                             distanceMeasure="squaredEuclidean")

    sweep = {}
    best = (None, -2.0, None)      # (name_k, silhouette, model)
    algos = {
        "kmeans": lambda k: KMeans(k=k, seed=config.SEED, featuresCol="features",
                                   predictionCol="cluster", maxIter=50),
        "bisecting_kmeans": lambda k: BisectingKMeans(
            k=k, seed=config.SEED, featuresCol="features",
            predictionCol="cluster", maxIter=30),
        "gaussian_mixture": lambda k: GaussianMixture(
            k=k, seed=config.SEED, featuresCol="features",
            predictionCol="cluster", maxIter=40),
    }

    for aname, factory in algos.items():
        sweep[aname] = {}
        for k in config.KMEANS_K_RANGE:
            with timed(f"{aname} k={k}"):
                model = factory(k).fit(data)
                pred = model.transform(data)
                counts = pred.groupBy("cluster").count().collect()
                sizes = sorted([r["count"] for r in counts], reverse=True)
                # A fit can collapse: asking for k clusters does not guarantee k
                # NON-EMPTY ones, and ClusteringEvaluator then dies with
                # "Number of clusters must be greater than one". Record the
                # degeneracy instead of losing the whole sweep to it.
                if len(counts) < 2:
                    sweep[aname][k] = {"silhouette": None, "cluster_sizes": sizes,
                                       "note": "degenerate: <2 non-empty clusters"}
                    print(f"    DEGENERATE (collapsed to {len(counts)} cluster)"
                          f" - skipped")
                    continue
                sil = float(ev.evaluate(pred))
            sweep[aname][k] = {"silhouette": sil, "cluster_sizes": sizes}
            print(f"    silhouette={sil:.4f}  sizes={sizes}")
            if sil > best[1]:
                best = (f"{aname}_k{k}", sil, model)

    best_name, best_sil, best_model = best
    if best_model is None:
        raise SystemExit("FATAL: every clustering fit degenerated; "
                         "check MIN_EDITS and the feature matrix")
    print(f"\n  BEST: {best_name}  silhouette={best_sil:.4f}")

    pred = best_model.transform(data)

    # ---- cluster characterisation (the interpretable deliverable) ---------
    profile = (pred.groupBy("cluster")
               .agg(F.count("*").alias("n_editors"),
                    *[F.round(F.avg(c), 3).alias(c) for c in EDITOR_FEATURES],
                    F.round(F.avg("e_is_bot"), 4).alias("bot_share"),
                    F.round(F.avg("e_n_edits"), 1).alias("mean_edits"))
               .orderBy("cluster"))
    pdf = profile.toPandas()
    pdf.to_csv(config.METRICS / "cluster_profiles.csv", index=False)
    print("\n  cluster profiles (key columns):")
    cols = ["cluster", "n_editors", "mean_edits", "bot_share", "e_gap_cv",
            "e_night_ratio", "e_minor_ratio", "e_reverted_ratio",
            "e_edits_per_active_day", "e_cmt_section_ratio"]
    with pd.option_context("display.width", 200, "display.max_columns", 50):
        print(pdf[[c for c in cols if c in pdf.columns]].to_string(index=False))

    # ---- external validation, done honestly -------------------------------
    # Purity is USELESS here and we report it only next to its own baseline.
    # Bots are a tiny fraction of ACCOUNTS (they are few accounts making many
    # edits), so the majority class alone already scores ~0.996 and any
    # partition whatsoever matches it. Reporting purity on its own would be
    # straightforwardly misleading.
    #
    # The informative quantity is ENRICHMENT: per-cluster bot share divided by
    # the overall bot share. Lift > 1 means bots concentrate in that cluster.
    tot = int(pdf["n_editors"].sum())
    n_bot_editors = float((pdf["n_editors"] * pdf["bot_share"]).sum())
    baseline = n_bot_editors / tot
    purity = float((pdf["n_editors"] *
                    pdf["bot_share"].combine(1 - pdf["bot_share"], max)).sum() / tot)
    pdf["bot_lift"] = (pdf["bot_share"] / baseline).round(2) if baseline else 0.0
    max_lift = float(pdf["bot_lift"].max())

    print(f"\n  bot editors: {n_bot_editors:.0f} of {tot:,} accounts "
          f"({100*baseline:.4f}%)")
    print(f"  purity {purity:.4f} vs majority-class baseline {1-baseline:.4f} "
          f"-> lift over baseline {purity-(1-baseline):+.5f}")
    print(f"  per-cluster bot enrichment: "
          f"{', '.join(f'c{int(r.cluster)}={r.bot_lift}x' for r in pdf.itertuples())}")
    print(f"  max enrichment: {max_lift:.2f}x")
    if purity - (1 - baseline) < 0.01:
        print("  NOTE: purity carries no information here; use the lift above.")

    pred.select("actor_key", "cluster", "e_is_bot", "e_n_edits") \
        .write.mode("overwrite").parquet(str(config.DATA_FEATURES / "editor_clusters"))

    save_metrics("p05_clustering", {
        "n_editors_total": n_all, "n_editors_clustered": n,
        "min_edits": MIN_EDITS,
        "features_used": EDITOR_FEATURES,
        "sweep": sweep,
        "best": best_name, "best_silhouette": best_sil,
        # A fit asked for k clusters may return fewer non-empty ones, so the
        # k in `best` is the REQUESTED k. Record what was actually produced.
        "best_k_requested": int(best_name.rsplit("_k", 1)[1]),
        "best_k_nonempty": int(len(pdf)),
        "bot_editor_count": n_bot_editors,
        "bot_editor_rate": baseline,
        "bot_purity": purity,
        "bot_purity_baseline": 1 - baseline,
        "bot_purity_lift_over_baseline": purity - (1 - baseline),
        "bot_max_enrichment": max_lift,
        "cluster_profiles": pdf.to_dict(orient="records"),
    })
    spark.stop()


if __name__ == "__main__":
    main()
