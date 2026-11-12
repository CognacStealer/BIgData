"""
DataFrame analytics and Spark SQL over the prepared revision table.

Registers the cleaned DataFrame as a temporary view and answers the
assignment's analytical questions declaratively, so the DataFrame API and
Spark SQL can be compared on identical data against the RDD results in
reports/metrics/pb_rdd.json.

  source env.sh && python src/pc_sql.py
"""
import time

from pyspark.sql import functions as F

import config
from spark_utils import banner, get_spark, save_metrics, timed

NS_NAMES = {0: "Article", 1: "Talk", 2: "User", 3: "User talk", 4: "Project",
            6: "File", 10: "Template", 14: "Category", 12: "Help"}


def main():
    spark = get_spark("pc_sql")
    banner("DATAFRAME ANALYTICS AND SPARK SQL")
    out = {}

    df = spark.read.parquet(str(config.DATA_PARQUET / "prepared")).cache()
    out["rows"] = df.count()
    out["columns"] = len(df.columns)
    print(f"  rows: {out['rows']:,}  columns: {out['columns']}")

    df.createOrReplaceTempView("wikimedia_edits")

    # ---- DataFrame API: edits per namespace ------------------------------
    with timed("DataFrame groupBy namespace"):
        t0 = time.time()
        ns = (df.groupBy("page_namespace")
                .agg(F.count("*").alias("edits"),
                     F.round(F.avg("label_bot"), 4).alias("bot_share"),
                     F.round(F.avg("label_reverted"), 4).alias("revert_rate"))
                .orderBy(F.desc("edits")).limit(10).collect())
        out["df_api_seconds"] = time.time() - t0
    out["namespaces"] = [{"namespace": int(r["page_namespace"]),
                          "name": NS_NAMES.get(int(r["page_namespace"]), "other"),
                          "edits": r["edits"], "bot_share": float(r["bot_share"]),
                          "revert_rate": float(r["revert_rate"])} for r in ns]
    for r in out["namespaces"][:5]:
        print(f"    ns {r['namespace']:>3} {r['name']:<10} {r['edits']:>10,} "
              f"bot {100*r['bot_share']:5.1f}%  revert {100*r['revert_rate']:5.1f}%")

    # ---- Spark SQL: the same question, declaratively ---------------------
    with timed("Spark SQL groupBy namespace (same query)"):
        t0 = time.time()
        spark.sql("""
            SELECT page_namespace, COUNT(*) AS edits
            FROM wikimedia_edits GROUP BY page_namespace
            ORDER BY edits DESC LIMIT 10""").collect()
        out["sql_seconds"] = time.time() - t0
    print(f"  DataFrame API {out['df_api_seconds']:.2f}s vs Spark SQL "
          f"{out['sql_seconds']:.2f}s (same Catalyst plan)")

    # ---- Spark SQL: label summary ----------------------------------------
    rows = spark.sql("""
        SELECT label_bot, COUNT(*) AS edits,
               ROUND(AVG(label_reverted), 4) AS revert_rate,
               ROUND(AVG(revision_text_bytes_diff), 1) AS avg_bytes_diff
        FROM wikimedia_edits GROUP BY label_bot ORDER BY label_bot""").collect()
    out["by_label_bot"] = [{"label_bot": int(r["label_bot"]), "edits": r["edits"],
                            "revert_rate": float(r["revert_rate"]),
                            "avg_bytes_diff": float(r["avg_bytes_diff"])}
                           for r in rows]
    total = sum(r["edits"] for r in out["by_label_bot"])
    for r in out["by_label_bot"]:
        print(f"    label_bot={r['label_bot']}: {r['edits']:,} "
              f"({100*r['edits']/total:.1f}%) revert {100*r['revert_rate']:.2f}%")

    # ---- Spark SQL: activity by year (trend) -----------------------------
    yr = spark.sql("""
        SELECT YEAR(event_timestamp) AS yr, COUNT(*) AS edits,
               ROUND(AVG(label_bot), 4) AS bot_share
        FROM wikimedia_edits GROUP BY YEAR(event_timestamp) ORDER BY yr""").collect()
    out["by_year"] = [{"year": int(r["yr"]), "edits": r["edits"],
                       "bot_share": float(r["bot_share"])} for r in yr if r["yr"]]
    peak = max(out["by_year"], key=lambda r: r["edits"])
    out["peak_year"] = peak
    print(f"  busiest year: {peak['year']} with {peak['edits']:,} edits "
          f"({100*peak['bot_share']:.1f}% bot)")

    # ---- Spark SQL: monthly trend (Part C example query) -----------------
    mon = spark.sql("""
        SELECT date_format(event_timestamp, 'yyyy-MM') AS ym,
               COUNT(*) AS edits,
               ROUND(AVG(label_bot), 4) AS bot_share
        FROM wikimedia_edits
        WHERE event_timestamp >= '2024-01-01'
        GROUP BY 1 ORDER BY 1""").collect()
    out["by_month"] = [{"month": r["ym"], "edits": r["edits"],
                        "bot_share": float(r["bot_share"])} for r in mon]
    if out["by_month"]:
        pk = max(out["by_month"], key=lambda r: r["edits"])
        out["peak_month"] = pk
        print(f"  busiest month since 2024: {pk['month']} "
              f"({pk['edits']:,} edits, {100*pk['bot_share']:.1f}% bot)")

    # ---- Spark SQL: most edited pages ------------------------------------
    pages = spark.sql("""
        SELECT page_title, COUNT(*) AS edits
        FROM wikimedia_edits WHERE page_namespace = 0
        GROUP BY page_title ORDER BY edits DESC LIMIT 10""").collect()
    out["top_pages"] = [{"title": r["page_title"], "edits": r["edits"]} for r in pages]
    print("  top article:", out["top_pages"][0])

    # ---- Spark SQL: most frequent comment terms (Part C example query) ---
    # The RDD phase answers this with flatMap/reduceByKey; doing it again in
    # SQL lets the two APIs be compared on an identical question.
    terms = spark.sql("""
        SELECT word, COUNT(*) AS n
        FROM (SELECT explode(split(lower(event_comment), '[^a-z0-9]+')) AS word
              FROM wikimedia_edits)
        WHERE length(word) > 2
        GROUP BY word ORDER BY n DESC LIMIT 15""").collect()
    out["top_terms_sql"] = [{"word": r["word"], "n": r["n"]} for r in terms]
    print("  top comment terms (SQL):",
          ", ".join(f"{r['word']}={r['n']:,}" for r in terms[:5]))

    # ---- Spark SQL: anonymous vs registered vs bot -----------------------
    seg = spark.sql("""
        SELECT CASE WHEN label_bot = 1 THEN 'bot'
                    WHEN event_user_is_anonymous THEN 'anonymous'
                    ELSE 'registered human' END AS segment,
               COUNT(*) AS edits,
               ROUND(AVG(label_reverted), 4) AS revert_rate
        FROM wikimedia_edits GROUP BY 1 ORDER BY edits DESC""").collect()
    out["segments"] = [{"segment": r["segment"], "edits": r["edits"],
                        "revert_rate": float(r["revert_rate"])} for r in seg]
    for r in out["segments"]:
        print(f"    {r['segment']:<18} {r['edits']:>10,}  revert "
              f"{100*r['revert_rate']:5.2f}%")

    save_metrics("pc_sql", out)
    spark.stop()


if __name__ == "__main__":
    main()
