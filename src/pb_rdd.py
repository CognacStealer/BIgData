"""
RDD-based processing over the raw dump (low-level Spark API).

This phase deliberately uses the RDD API rather than DataFrames: textFile,
filter, map, flatMap, reduceByKey, takeOrdered, persist. It answers the same
kind of questions the DataFrame phases answer, so the two APIs can be compared
on identical data in the Results section.

The parsed RDD is projected down to a compact tuple before persisting. Keeping
full 78-field lists for 11 M rows as Python objects would not fit; the
projection is a few small fields and spills to disk cheaply.

  source env.sh && python src/pb_rdd.py
"""
import re
import time

from pyspark import StorageLevel

import config
import schema
from spark_utils import banner, get_spark, save_metrics, timed

# field indices into the raw TSV (0-based), from src/schema.py
I = {name: i for i, name in enumerate(schema.FIELDS)}

TOKEN = re.compile(r"[^\w]+", re.UNICODE)
STOP = {
    "the", "and", "for", "with", "that", "this", "from", "was", "are",
    "page", "link", "links", "via", "using", "add", "added", "new",
}


def parse(line):
    """Split one TSV line into the handful of fields we need.

    split("\\t") is safe here: tabs are the delimiter and never appear inside a
    field. (Quotes DO appear inside event_comment, which is why the DataFrame
    reader must disable quote handling -- but a raw split is unaffected.)
    """
    f = line.split("\t")
    if len(f) != 78:
        return None
    try:
        diff = int(f[I["revision_text_bytes_diff"]] or 0)
    except ValueError:
        diff = 0
    return (
        f[I["event_entity"]],
        f[I["page_namespace"]] or f[I["page_namespace_historical"]] or "?",
        f[I["event_user_text"]] or "?",
        1 if f[I["event_user_is_bot_by"]].strip() else 0,
        1 if f[I["revision_is_identity_reverted"]] == "true" else 0,
        1 if f[I["event_user_is_anonymous"]] == "true" else 0,
        diff,
        f[I["event_comment"]],
    )


def main():
    spark = get_spark("pb_rdd")
    sc = spark.sparkContext
    banner("RDD-BASED PROCESSING")
    out = {}

    # ---- creation ---------------------------------------------------------
    lines = sc.textFile(str(config.RAW_TSV), minPartitions=24)
    out["num_partitions"] = lines.getNumPartitions()
    print(f"  partitions: {out['num_partitions']}")

    # ---- map + filter -----------------------------------------------------
    parsed = lines.map(parse).filter(lambda r: r is not None)
    revs = (parsed.filter(lambda r: r[0] == "revision")
                  .map(lambda r: r[1:])          # drop entity, keep the rest
                  .persist(StorageLevel.MEMORY_AND_DISK))

    with timed("count revisions (forces the parse)"):
        out["num_revisions"] = revs.count()
    print(f"  revisions: {out['num_revisions']:,}")

    # ---- reduceByKey: edits per namespace ---------------------------------
    with timed("edits per namespace"):
        ns = (revs.map(lambda r: (r[0], 1))
                  .reduceByKey(lambda a, b: a + b)
                  .takeOrdered(10, key=lambda kv: -kv[1]))
    out["top_namespaces"] = ns
    print("  top namespaces:", ns[:5])

    # ---- reduceByKey: most active editors ---------------------------------
    with timed("most active editors"):
        top_users = (revs.map(lambda r: (r[1], 1))
                         .reduceByKey(lambda a, b: a + b)
                         .takeOrdered(15, key=lambda kv: -kv[1]))
    out["top_editors"] = top_users
    print("  top editors:", top_users[:5])

    # ---- flatMap: word count over edit comments ---------------------------
    with timed("comment word count (flatMap)"):
        words = (revs.flatMap(lambda r: TOKEN.split(r[6].lower()))
                     .filter(lambda w: len(w) > 2 and w not in STOP)
                     .map(lambda w: (w, 1))
                     .reduceByKey(lambda a, b: a + b)
                     .persist(StorageLevel.MEMORY_AND_DISK))
        out["total_comment_tokens"] = words.map(lambda kv: kv[1]).sum()
        out["top_comment_words"] = words.takeOrdered(20, key=lambda kv: -kv[1])
        words.unpersist()
    print(f"  comment tokens: {out['total_comment_tokens']:,}")
    print("  top words:", out["top_comment_words"][:6])

    # ---- aggregate: bot vs human, anonymous, revert rates -----------------
    with timed("bot / anon / revert aggregates"):
        # (edits, reverted, bytes_added) keyed by bot flag
        by_bot = (revs.map(lambda r: (r[2], (1, r[3], max(r[5], 0))))
                      .reduceByKey(lambda a, b: (a[0] + b[0], a[1] + b[1],
                                                 a[2] + b[2]))
                      .collectAsMap())
        anon_edits = revs.filter(lambda r: r[4] == 1).count()
        anon_reverted = revs.filter(lambda r: r[4] == 1 and r[3] == 1).count()

    out["by_bot"] = {("bot" if k else "human"): {
        "edits": v[0], "reverted": v[1], "bytes_added": v[2],
        "revert_rate": v[1] / v[0] if v[0] else 0.0,
    } for k, v in by_bot.items()}
    out["anonymous_edits"] = anon_edits
    out["anonymous_reverted"] = anon_reverted
    out["anonymous_revert_rate"] = anon_reverted / anon_edits if anon_edits else 0.0

    for k, v in out["by_bot"].items():
        print(f"  {k:>6}: {v['edits']:,} edits, revert rate {100*v['revert_rate']:.2f}%")
    print(f"  anonymous: {anon_edits:,} edits, revert rate "
          f"{100*out['anonymous_revert_rate']:.2f}%")

    out["num_jobs_note"] = "one Spark job per action; the parse is shared via persist()"
    save_metrics("pb_rdd", out)
    revs.unpersist()
    spark.stop()


if __name__ == "__main__":
    main()
