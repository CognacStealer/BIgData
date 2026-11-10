"""
Phase 5a: MLlib Classification  (+ Phase 6 metrics for classification)

Target: label_bot -- was this edit made by a flagged automated account?

Models compared: LogisticRegression, RandomForest, GBTClassifier.

Two feature sets are trained so the report can attribute performance:
  "structural" -> numeric + namespace one-hot only (no comment vocabulary)
  "full"       -> structural + 24-dim comment TF-IDF/SVD block

SPLIT DESIGN (important): we split by ACTOR, not by row. A random row split
would place the same bot account in both train and test; the model could then
memorise actor-specific cadence/edit-count fingerprints and report a wildly
optimistic score. Hashing actor_key into disjoint train/test groups makes the
test set contain only accounts never seen in training, which is the realistic
deployment condition.
"""
from pyspark.ml import Pipeline
from pyspark.ml.classification import (GBTClassifier, LogisticRegression,
                                       RandomForestClassifier)
from pyspark.ml.evaluation import (BinaryClassificationEvaluator,
                                   MulticlassClassificationEvaluator)
from pyspark.ml.feature import (OneHotEncoder, StandardScaler, StringIndexer,
                                VectorAssembler, VectorSizeHint)
from pyspark.ml.functions import vector_to_array
from pyspark.sql import functions as F

import config
from p04_features import CATEGORICAL_EDIT_FEATURES, NUMERIC_EDIT_FEATURES
from spark_utils import banner, get_spark, save_metrics, timed


def actor_split(df, train_fraction, seed):
    """Deterministic, actor-disjoint train/test split."""
    bucket = F.abs(F.hash(F.concat(F.col("actor_key"), F.lit(str(seed))))) % 100
    df = df.withColumn("_bucket", bucket)
    cut = int(train_fraction * 100)
    return (df.filter(F.col("_bucket") < cut).drop("_bucket"),
            df.filter(F.col("_bucket") >= cut).drop("_bucket"))


def build_pipeline(model, use_text):
    idx = StringIndexer(inputCols=CATEGORICAL_EDIT_FEATURES,
                        outputCols=[f"{c}_idx" for c in CATEGORICAL_EDIT_FEATURES],
                        handleInvalid="keep")
    ohe = OneHotEncoder(inputCols=[f"{c}_idx" for c in CATEGORICAL_EDIT_FEATURES],
                        outputCols=[f"{c}_ohe" for c in CATEGORICAL_EDIT_FEATURES],
                        handleInvalid="keep")
    num = VectorAssembler(inputCols=NUMERIC_EDIT_FEATURES,
                          outputCol="num_raw", handleInvalid="keep")
    # Scaling is fitted inside the Pipeline => fitted on TRAIN ONLY, never on
    # the full dataset. Fitting the scaler on everything is a classic leak.
    sca = StandardScaler(inputCol="num_raw", outputCol="num_scaled",
                         withMean=True, withStd=True)

    parts = ["num_scaled"] + [f"{c}_ohe" for c in CATEGORICAL_EDIT_FEATURES]
    stages = [idx, ohe, num, sca]
    if use_text:
        parts.append("cmt_svd")
        # cmt_svd comes out of a UDF, so it carries no size metadata and
        # VectorAssembler cannot infer its width under handleInvalid="keep"
        # ("Can not infer column lengths"). Declare it explicitly.
        stages.append(VectorSizeHint(inputCol="cmt_svd", size=config.SVD_K,
                                     handleInvalid="skip"))
    asm = VectorAssembler(inputCols=parts, outputCol="features",
                          handleInvalid="keep")
    return Pipeline(stages=stages + [asm, model])


def evaluate(pred, label_col="label_bot"):
    out = {}
    auc = BinaryClassificationEvaluator(labelCol=label_col,
                                        rawPredictionCol="rawPrediction",
                                        metricName="areaUnderROC")
    pr = BinaryClassificationEvaluator(labelCol=label_col,
                                       rawPredictionCol="rawPrediction",
                                       metricName="areaUnderPR")
    out["roc_auc"] = float(auc.evaluate(pred))
    out["pr_auc"] = float(pr.evaluate(pred))
    for m in ["accuracy", "weightedPrecision", "weightedRecall", "f1"]:
        ev = MulticlassClassificationEvaluator(labelCol=label_col,
                                               predictionCol="prediction",
                                               metricName=m)
        out[m] = float(ev.evaluate(pred))

    # Per-class (positive = bot) precision/recall/F1 from the confusion matrix
    cm = (pred.groupBy(label_col, "prediction").count().collect())
    c = {(int(r[label_col]), int(r["prediction"])): r["count"] for r in cm}
    tp, fp = c.get((1, 1), 0), c.get((0, 1), 0)
    fn, tn = c.get((1, 0), 0), c.get((0, 0), 0)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    out.update({
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "bot_precision": prec, "bot_recall": rec,
        "bot_f1": (2 * prec * rec / (prec + rec)) if prec + rec else 0.0,
    })
    return out


def main():
    spark = get_spark("p05_classification")
    banner("PHASE 5a + 6: Classification (label_bot)")

    df = spark.read.parquet(str(config.EDIT_FEATURES))
    train, test = actor_split(df, config.TRAIN_FRACTION, config.SEED)
    if config.TRAIN_SAMPLE < 1.0:
        train = train.sample(False, config.TRAIN_SAMPLE, seed=config.SEED)
        print(f"  (training on a {config.TRAIN_SAMPLE:.0%} sample of the train split;"
              f" test split is always evaluated in full)")
    train.cache(); test.cache()
    n_tr, n_te = train.count(), test.count()
    tr_pos = train.filter("label_bot = 1").count()
    te_pos = test.filter("label_bot = 1").count()
    print(f"  train {n_tr:,} rows ({100*tr_pos/n_tr:.2f}% bot)")
    print(f"  test  {n_te:,} rows ({100*te_pos/n_te:.2f}% bot)")
    print(f"  actor-disjoint split verified: "
          f"{train.select('actor_key').intersect(test.select('actor_key')).count()} shared actors")

    models = {
        "logistic_regression": LogisticRegression(
            labelCol="label_bot", featuresCol="features",
            maxIter=50, regParam=0.01, elasticNetParam=0.0),
        "random_forest": RandomForestClassifier(
            labelCol="label_bot", featuresCol="features",
            numTrees=40, maxDepth=10, maxBins=48, seed=config.SEED),
        "gbt": GBTClassifier(
            labelCol="label_bot", featuresCol="features",
            maxIter=30, maxDepth=5, maxBins=48, seed=config.SEED),
    }

    results = {}
    importances = {}
    for feat_set, use_text in [("structural", False), ("full", True)]:
        for name, mdl in models.items():
            key = f"{name}__{feat_set}"
            with timed(key):
                pipe = build_pipeline(mdl, use_text)
                fitted = pipe.fit(train)
                pred = fitted.transform(test)
                results[key] = evaluate(pred)
            r = results[key]
            print(f"    ROC-AUC {r['roc_auc']:.4f} | PR-AUC {r['pr_auc']:.4f} "
                  f"| acc {r['accuracy']:.4f} | bot-F1 {r['bot_f1']:.4f}")

            stage = fitted.stages[-1]
            if hasattr(stage, "featureImportances"):
                imp = stage.featureImportances.toArray()
                names = list(NUMERIC_EDIT_FEATURES)
                n_ohe = len(imp) - len(names) - (config.SVD_K if use_text else 0)
                names += [f"ns_ohe_{i}" for i in range(max(n_ohe, 0))]
                if use_text:
                    names += [f"cmt_svd_{i}" for i in range(config.SVD_K)]
                names = (names + [f"unk_{i}" for i in range(len(imp))])[:len(imp)]
                importances[key] = sorted(
                    zip(names, imp.tolist()), key=lambda kv: -kv[1])[:20]

            # Persist scored test rows so Phase 6 can draw the ROC/PR curves
            if key == "gbt__full":
                (pred.select(
                    "label_bot",
                    vector_to_array("probability")[1].alias("p_bot"))
                 .write.mode("overwrite")
                 .parquet(str(config.DATA_FEATURES / "roc_input")))

    best = max(results, key=lambda k: results[k]["roc_auc"])
    print(f"\n  BEST: {best}  ROC-AUC={results[best]['roc_auc']:.4f}")

    save_metrics("p05_classification", {
        "n_train": n_tr, "n_test": n_te,
        "train_bot_rate": tr_pos / n_tr, "test_bot_rate": te_pos / n_te,
        "split": "actor-disjoint hash split",
        "results": results, "best_model": best,
        "feature_importances": importances,
    })
    spark.stop()

if __name__ == "__main__":
    main()
