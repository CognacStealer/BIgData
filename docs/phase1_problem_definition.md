# Phase 1: Problem Definition and Dataset Understanding

## 1. The problem

Wikimedia projects accept edits from anyone, with no pre-publication review. The
English and sister projects together absorb **30–50 edits per second**, which is
far beyond what volunteer reviewers can inspect. A large and growing share of
that traffic is automated: approved bots performing maintenance, semi-automated
human tooling, and unapproved scripts.

Platform-integrity teams therefore need to answer two questions continuously:

1. **Is this edit automated?** Automation is not inherently bad — approved bots
   do essential maintenance — but reviewer attention is a scarce resource and
   should not be spent on predictable machine edits. Conversely, *unflagged*
   automation is a policy violation and a vandalism vector.
2. **What kinds of editors exist on this platform?** Reviewer tooling, rate
   limits and onboarding should be designed around actual behavioural
   populations, not assumed ones.

The first question is a **supervised classification** problem. The second is an
**unsupervised clustering** problem. The project addresses both, as the rubric
requires, on the same underlying corpus.

**Domain:** Social Media / Platform Trust & Safety.

## 2. Dataset

| Property | Value |
|---|---|
| Source | Wikimedia `mediawiki_history` dumps, snapshot `2026-10` |
| URL | `https://dumps.wikimedia.org/other/mediawiki_history/2026-10/simplewiki/` |
| Wiki used | `simplewiki` (Simple English Wikipedia), complete all-time history |
| Compressed size | 951 MB (bz2 TSV) |
| Raw rows | 15,201,370 |
| Revision (edit) rows | 11,023,987 |
| Columns | 78 (documentation claims 76 — see `schema_notes.md`) |
| Licence | CC0 / public domain dedication for the dump data |
| Live companion feed | `https://stream.wikimedia.org/v2/stream/recentchange` (SSE) |

Each revision row carries the acting user, the page and namespace, byte sizes
before and after, the edit comment, cadence since that user's previous edit, and
revert relationships.

## 3. Why this dataset was selected

**It has honest ground truth.** `event_user_is_bot_by` is populated from
MediaWiki **user-group membership and the bot-name registry** — administrative
facts about an *account*, not properties of the individual edit. A model
predicting it from edit behaviour is therefore solving a real inference problem.

We explicitly evaluated and rejected the alternative, **GDELT 2.0**. Its natural
labels (`QuadClass`, `GoldsteinScale`) are deterministic lookup tables keyed on
`EventCode`: keeping that column makes the task a trivially leaky lookup, and
dropping it leaves the task ill-posed. Full argument in `leakage.md`.

**It is genuinely massive and genuinely distributed work.** 11 million edits in
one of ~900 wikis. The per-editor aggregation is a wide shuffle whose cost scales
with distinct actors, and the same code scales to `enwiki` unchanged.

**It supports both required task families from one corpus**, with a second
supervised label (`revision_is_identity_reverted`) available as an extension.

**It is reproducible and free.** No credentials, no rate limits, no licensing
restrictions, and a live stream for demonstration.

## 4. Expected outcomes

| Outcome | Form |
|---|---|
| A bot-detection classifier evaluated under an actor-disjoint split | ROC-AUC, PR-AUC, precision/recall/F1 for three algorithms |
| A measurement of how much predictive power comes from comment text | paired `structural` vs `full` feature-set results |
| A set of named editor archetypes | cluster profile table + silhouette-justified `k` |
| Evidence that unsupervised behaviour clusters align with automation | bot-share per cluster, as external validation |
| A scalability analysis grounded in observed stage behaviour | Phase 7 discussion |

### Hypotheses we set out to test

1. **Cadence regularity, not volume, is the strongest automation signal.** Bots
   run on schedules, so the coefficient of variation of inter-edit gaps should
   dominate raw edit counts.
2. **Structural features alone get most of the way.** Comment vocabulary should
   add a measurable but not dominant increment.
3. **Behavioural clustering will partially — not cleanly — recover the bot
   boundary**, because semi-automated human tooling occupies the middle ground.

Stating these in advance matters: it means the results section reports whether
predictions held, rather than narrating whatever the numbers happened to show.

### Outcome of those hypotheses

| # | Hypothesis | Outcome |
|---|---|---|
| 1 | Cadence regularity, not volume, is the strongest automation signal | **Partly supported.** Cadence features are in the top block, but tree ensembles spread importance across cadence, namespace and edit-size features rather than relying on one. |
| 2 | Structural features alone get most of the way | **Supported, more strongly than expected.** GBT reaches ROC-AUC 0.9756 with no comment vocabulary; adding text slightly lowers it. |
| 3 | Behavioural clustering will partially recover the bot boundary | **Not supported.** The clusters separate activity level, not automation; bots are only 3.6x enriched in the busiest cluster and purity equals its own baseline exactly. See the Results section of the README. |

Hypothesis 3 failing is the more interesting result, and it is kept in the
report rather than quietly dropped.
