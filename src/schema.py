"""
Schema for the Wikimedia `mediawiki_history` TSV dumps.

IMPORTANT: the public documentation at
  https://wikitech.wikimedia.org/wiki/Analytics/Data_Lake/Edits/Mediawiki_history_dumps
states 76 fields, but the 2026-10 snapshot actually ships 78 tab-separated
columns. The difference is the two `*_central_id` fields, which the doc has not
yet picked up. The order below was verified empirically against the real file by
profiling every column's fill-rate and value shape (see docs/schema_notes.md).

Column 2 (`event_log_id`) is undocumented: it is populated almost exclusively on
`event_entity == 'user'` rows. We filter to revision events, so it is unused.
"""
from pyspark.sql.types import StructType, StructField, StringType

FIELDS = [
    # --- event global ---
    "wiki_db",
    "event_log_id",                 # undocumented, user-entity rows only
    "event_entity",                 # page | revision | user
    "event_type",                   # create | move | delete | ...
    "event_timestamp",
    "event_comment",
    # --- event user (the actor performing the event) ---
    "event_user_id",
    "event_user_central_id",
    "event_user_text_historical",
    "event_user_text",
    "event_user_blocks_historical",
    "event_user_blocks",
    "event_user_groups_historical",
    "event_user_groups",
    "event_user_is_bot_by_historical",
    "event_user_is_bot_by",         # <-- PRIMARY CLASSIFICATION LABEL SOURCE
    "event_user_is_created_by_self",
    "event_user_is_created_by_system",
    "event_user_is_created_by_peer",
    "event_user_is_anonymous",
    "event_user_is_temporary",
    "event_user_is_permanent",
    "event_user_is_cross_wiki",
    "event_user_registration_timestamp",
    "event_user_creation_timestamp",
    "event_user_first_edit_timestamp",
    "event_user_revision_count",
    "event_user_seconds_since_previous_revision",
    # --- page ---
    "page_id",
    "page_title_historical",
    "page_title",
    "page_namespace_historical",
    "page_namespace_is_content_historical",
    "page_namespace",
    "page_namespace_is_content",
    "page_is_redirect",
    "page_is_deleted",
    "page_creation_timestamp",
    "page_first_edit_timestamp",
    "page_revision_count",
    "page_seconds_since_previous_revision",
    # --- user (the user the event is *about*; set on user events) ---
    "user_id",
    "user_central_id",
    "user_text_historical",
    "user_text",
    "user_blocks_historical",
    "user_blocks",
    "user_groups_historical",
    "user_groups",
    "user_is_bot_by_historical",
    "user_is_bot_by",
    "user_is_created_by_self",
    "user_is_created_by_system",
    "user_is_created_by_peer",
    "user_is_anonymous",
    "user_is_temporary",
    "user_is_permanent",
    "user_registration_timestamp",
    "user_creation_timestamp",
    "user_first_edit_timestamp",
    # --- revision ---
    "revision_id",
    "revision_parent_id",
    "revision_minor_edit",
    "revision_deleted_parts",
    "revision_deleted_parts_are_suppressed",
    "revision_text_bytes",
    "revision_text_bytes_diff",
    "revision_text_sha1",
    "revision_content_model",
    "revision_content_format",
    "revision_is_deleted_by_page_deletion",
    "revision_deleted_by_page_deletion_timestamp",
    "revision_is_identity_reverted",   # <-- SECONDARY CLASSIFICATION LABEL
    "revision_first_identity_reverting_revision_id",
    "revision_seconds_to_identity_revert",
    "revision_is_identity_revert",
    "revision_is_from_before_page_creation",
    "revision_tags",
]

assert len(FIELDS) == 78, f"expected 78 fields, got {len(FIELDS)}"

# Read everything as String and cast explicitly in Phase 3. The dump uses
# empty strings for nulls and non-ISO timestamps ("2001-05-18 21:57:10.0"),
# so letting Spark infer types silently drops rows.
RAW_SCHEMA = StructType([StructField(f, StringType(), True) for f in FIELDS])

# Columns actually needed downstream. Projecting early is the single biggest
# win when reading ~10 GB of TSV (Phase 7: predicate/projection pushdown).
REVISION_COLUMNS = [
    "wiki_db", "event_entity", "event_type", "event_timestamp", "event_comment",
    "event_user_id", "event_user_text", "event_user_is_bot_by",
    "event_user_groups", "event_user_is_anonymous", "event_user_revision_count",
    "event_user_seconds_since_previous_revision",
    "event_user_registration_timestamp",
    "page_id", "page_title", "page_namespace", "page_namespace_is_content",
    # _historical variants survive page deletion; the current-state columns go
    # NULL once a page is deleted. Needed to avoid dropping ~15% of revisions,
    # which would bias the revert label (deleted pages concentrate vandalism).
    "page_title_historical", "page_namespace_historical",
    "page_namespace_is_content_historical",
    "page_is_redirect", "page_revision_count",
    "revision_id", "revision_parent_id", "revision_minor_edit",
    "revision_text_bytes", "revision_text_bytes_diff",
    "revision_is_identity_reverted", "revision_is_identity_revert",
    "revision_seconds_to_identity_revert", "revision_tags",
]
