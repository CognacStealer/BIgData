# Dataset schema notes (Phase 1 evidence)

Source: `https://dumps.wikimedia.org/other/mediawiki_history/2026-10/simplewiki/2026-10.simplewiki.all-time.tsv.bz2`

## Discrepancy with the official documentation

The Wikitech page *Analytics/Data Lake/Edits/Mediawiki history dumps* states the
dataset has **76 fields**. The 2026-10 snapshot actually ships **78**
tab-separated columns. The two extra fields are `event_user_central_id` and
`user_central_id`, which the documentation has not yet picked up.

Column order was therefore **verified empirically**, not taken from the doc: we
profiled every column index over a sample of real rows, recording fill-rate and
value shape (boolean / integer / timestamp / free text / base-36 hash), then
matched those signatures against the documented field groups. Anchors used:

| Anchor | Column | Evidence |
|---|---|---|
| `wiki_db` | 1 | constant `simplewiki` |
| `event_entity` | 3 | only `page`, `revision`, `user` |
| `event_type` | 4 | `create`, `move`, ... |
| `page_id` | 29 | integer, 92% fill |
| `revision_text_sha1` | 68 | base-36 40-char hashes |
| `revision_tags` | 78 | last column |

Counting between anchors confirmed the `event_user_*` block occupies exactly
columns 7–28 (22 fields), which matches the documented field list for that group
once the two `central_id` additions are included.

## Undocumented column 2

Column 2 holds a large integer and is populated almost exclusively on rows where
`event_entity == 'user'` (146 of 147 non-empty cases in the sample). It does not
correspond to `user_id` or `user_central_id`, both of which appear separately
later in the same rows. We name it `event_log_id` in `src/schema.py` and flag it
as undocumented. **It is unused by the pipeline**, because every phase filters to
`event_entity == 'revision'`, where this column is always empty.

## Parsing hazards

1. **Quotes.** `event_comment` contains raw double quotes, e.g. `"Bad words"`.
   Spark's CSV reader treats `"` as a quote character by default and will absorb
   tab delimiters inside an apparently-quoted region, shifting every subsequent
   column. We set `.option("quote", "")` to disable quote processing entirely.
2. **No header row.** The first line is data.
3. **Nulls** are empty strings, not `\N`.
4. **Timestamps** use the form `2001-05-18 21:57:10.0` — pattern
   `yyyy-MM-dd HH:mm:ss.S`, not ISO-8601.
5. **bz2 is splittable** in Hadoop, so Spark parallelises the read. A gzip dump
   would have been limited to a single task.

## Labels available

| Label | Source column | Meaning |
|---|---|---|
| `label_bot` | `event_user_is_bot_by` non-empty | actor is a flagged automated account (by group membership and/or bot-name registry) |
| `label_reverted` | `revision_is_identity_reverted` | this edit was subsequently reverted |

Neither label is a deterministic function of any feature we engineer — see
`docs/leakage.md`.
