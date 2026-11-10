# Label leakage control (methodological core of the project)

## Why this matters — and why we did not use GDELT

The rubric requires both classification and clustering, so the project needs a
genuine supervised label. The obvious alternative dataset, **GDELT 2.0**, offers
`QuadClass` and `GoldsteinScale` as targets. Both are **deterministic lookup
tables keyed on `EventCode`**:

* keep `EventCode` as a feature → the classifier scores near-perfectly by
  reproducing a lookup table, which demonstrates nothing;
* drop `EventCode` → the remaining signal is weak and the task becomes
  ill-posed.

Wikimedia's `event_user_is_bot_by` is different in kind. It derives from
MediaWiki **user-group membership and the bot-name registry** — administrative
facts about an account — not from any property of the individual edit. Predicting
it from edit behaviour is therefore a real learning problem.

## Columns excluded as leaky

| Column | Why it leaks |
|---|---|
| `event_user_text`, `event_user_text_historical` | usernames literally contain the string "Bot" (e.g. `SchlurcherBot`) |
| `event_user_groups`, `event_user_groups_historical` | contain the `bot` group that **defines** the label |
| `event_user_is_bot_by*`, `user_is_bot_by*` | the label itself |
| `user_groups*` | same as above for user-entity rows |
| revision tags containing `bot` | tag vocabulary names the automation |

These are listed in `config.LEAKY_COLUMNS` and are never assembled into a
feature vector. `event_user_text` *is* used — but only as a grouping key
(`actor_key`) for per-editor aggregation, which never reaches a model.

## A judgement call: `event_comment`

Comment text is **kept**, with reasoning stated explicitly rather than hidden:

* it is observable at edit time;
* it is not derived from user-group membership;
* bot comments genuinely look different ("automatically adding structured data
  based on file information"), and learning that is legitimate pattern
  recognition, not leakage.

To keep this honest and measurable, Phase 5 trains **every model twice** —
`structural` (no comment vocabulary) and `full` (structural + 24-dim comment
SVD). The gap between the two quantifies exactly how much performance comes from
text, so the report can state it instead of hoping nobody asks.

## Two further leaks we closed

**1. Actor-disjoint split.** A random row-level split would put the same bot
account in both train and test. The model could then memorise actor-specific
fingerprints (edit count, cadence) and report an inflated score. We hash
`actor_key` into disjoint buckets, so the test set contains **only accounts never
seen during training** — the realistic deployment condition. The script asserts
the intersection is empty.

**2. Scaler fitted on train only.** `StandardScaler` sits *inside* the Spark ML
`Pipeline`, so its mean and variance are estimated from the training fold alone.
Fitting it on the full dataset before splitting is a common and subtle leak.

## Clustering validation

`e_is_bot` is **not** a clustering input. It is used only afterwards, as
external validation.

**The obvious validation metric is a trap here.** Cluster *purity* against the
bot flag came out at 0.9963 — which looks excellent until you notice it is
*exactly* the majority-class baseline, because only 0.37% of accounts are bots
(they are few accounts making very many edits). Purity carries literally zero
information in this setting, and reporting it alone would be misleading.

The pipeline therefore reports purity **only next to its own baseline**, plus
per-cluster **enrichment** (cluster bot share / overall bot share), which is the
quantity that actually moves. The honest answer is that bots are 3.6x enriched
in the high-activity cluster: a real but modest effect, and not a recovery of
the automation boundary.
