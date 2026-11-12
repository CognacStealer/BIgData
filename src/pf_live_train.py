"""
Train a LIVE-SERVABLE bot classifier and save it to disk.

p05_classification.py trains and discards its models -- it answers "how well
can this be predicted?", not "give me something to deploy". This phase saves a
fitted PipelineModel so src/pf_live_demo.py can score arriving edits.

The model is trained on exactly the 25 features that the EventStreams feed can
supply (see src/live_features.py), and on the same actor-disjoint split
discipline as the batch work, so the reported score is not inflated by an
account appearing in both folds.

  source env.sh && python src/pf_live_train.py
"""
from pyspark.ml import Pipeline
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml.evaluation import (BinaryClassificationEvaluator,
                                   MulticlassClassificationEvaluator)
from pyspark.ml.feature import (OneHotEncoder, StandardScaler, StringIndexer,
                                VectorAssembler)
from pyspark.sql import functions as F

import config
from live_features import CATEGORICAL, FEATURES, add_live_features
from spark_utils import banner, get_spark, save_metrics, timed

MODEL_DIR = config.ROOT / "models" / "live_bot_rf"


def main():
    spark = get_spark("pf_live_train")
    banner("TRAIN LIVE-SERVABLE BOT CLASSIFIER")

    # Map the historical dump onto the canonical live column names, so the very
    # same feature code runs at train time and at serve time.
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

    df = add_live_features(src).cache()
    n = df.count()
    print(f"  training rows available: {n:,}")

    # same actor-disjoint discipline as p05_classification
    bucket = F.abs(F.hash(F.concat(F.col("actor_key"),
                                   F.lit(str(config.SEED))))) % 100
    df = df.withColumn("_b", bucket)
    train = df.filter(F.col("_b") < 80).drop("_b")
    test = df.filter(F.col("_b") >= 80).drop("_b")
    n_tr, n_te = train.count(), test.count()
    shared = train.select("actor_key").intersect(test.select("actor_key")).count()
    print(f"  train {n_tr:,} / test {n_te:,} | shared actors: {shared}")

    idx = StringIndexer(inputCols=CATEGORICAL,
                        outputCols=[f"{c}_idx" for c in CATEGORICAL],
                        handleInvalid="keep")
    ohe = OneHotEncoder(inputCols=[f"{c}_idx" for c in CATEGORICAL],
                        outputCols=[f"{c}_ohe" for c in CATEGORICAL],
                        handleInvalid="keep")
    num = VectorAssembler(inputCols=FEATURES, outputCol="num_raw",
                          handleInvalid="keep")
    sca = StandardScaler(inputCol="num_raw", outputCol="num_scaled",
                         withMean=True, withStd=True)
    asm = VectorAssembler(
        inputCols=["num_scaled"] + [f"{c}_ohe" for c in CATEGORICAL],
        outputCol="features", handleInvalid="keep")
    rf = RandomForestClassifier(labelCol="label_bot", featuresCol="features",
                                numTrees=40, maxDepth=10, maxBins=64,
                                seed=config.SEED)

    with timed("fit"):
        model = Pipeline(stages=[idx, ohe, num, sca, asm, rf]).fit(train)

    pred = model.transform(test)
    out = {}
    out["roc_auc"] = float(BinaryClassificationEvaluator(
        labelCol="label_bot", metricName="areaUnderROC").evaluate(pred))
    out["pr_auc"] = float(BinaryClassificationEvaluator(
        labelCol="label_bot", metricName="areaUnderPR").evaluate(pred))
    for m in ["accuracy", "f1"]:
        out[m] = float(MulticlassClassificationEvaluator(
            labelCol="label_bot", predictionCol="prediction",
            metricName=m).evaluate(pred))
    cm = {(int(r["label_bot"]), int(r["prediction"])): r["count"]
          for r in pred.groupBy("label_bot", "prediction").count().collect()}
    tp, fp = cm.get((1, 1), 0), cm.get((0, 1), 0)
    fn = cm.get((1, 0), 0)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    out.update({"bot_precision": prec, "bot_recall": rec,
                "bot_f1": (2 * prec * rec / (prec + rec)) if prec + rec else 0.0,
                "n_train": n_tr, "n_test": n_te, "shared_actors": shared,
                "n_features": len(FEATURES),
                "note": "live-servable subset; batch model uses richer columns"})
    print(f"  ROC-AUC {out['roc_auc']:.4f} | PR-AUC {out['pr_auc']:.4f} "
          f"| acc {out['accuracy']:.4f} | bot-F1 {out['bot_f1']:.4f}")

    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    model.write().overwrite().save(str(MODEL_DIR))
    print(f"  saved model -> {MODEL_DIR}")
    out["model_path"] = str(MODEL_DIR)
    save_metrics("pf_live_train", out)
    spark.stop()


if __name__ == "__main__":
    main()
