"""AP13: erasure audit redaction, new deletion data types, consent kinds sms and ai_processing.

* GAM-401: ``audit_log`` stays append only, but one update is allowed: reducing ``changes`` of
  a contact row to its field names (function ``audit_redact_changes``, row trigger
  ``audit_log_redact_only``). Deletes and truncates stay forbidden (statement trigger).
* GAM-404: ``privacy_deletion_profile.data_type`` also accepts ``ai_run``, ``call_log``,
  ``webhook_delivery``, ``postal_job`` (no profile is created, no period is set).
* GAM-406: ``consent_kind`` gains ``sms`` and ``ai_processing``.

Revision ID: 0465
Revises: 0464
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0465"
down_revision: str | None = "0464"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES_OLD = (
    "('contact', 'portal_account', 'communication', 'ticket', 'other', "
    "'domain_event', 'platform_user', 'bank_raw')"
)
_TYPES_NEW = (
    "('contact', 'portal_account', 'communication', 'ticket', 'other', "
    "'domain_event', 'platform_user', 'bank_raw', 'ai_run', 'call_log', "
    "'webhook_delivery', 'postal_job')"
)


def upgrade() -> None:
    op.execute("ALTER TYPE consent_kind ADD VALUE IF NOT EXISTS 'sms'")
    op.execute("ALTER TYPE consent_kind ADD VALUE IF NOT EXISTS 'ai_processing'")
    op.drop_constraint(
        "ck_privacy_deletion_profile_type", "privacy_deletion_profile", type_="check"
    )
    op.create_check_constraint(
        "ck_privacy_deletion_profile_type",
        "privacy_deletion_profile",
        f"data_type IN {_TYPES_NEW}",
    )
    op.execute(
        """
        CREATE FUNCTION audit_redact_changes(c jsonb) RETURNS jsonb
        LANGUAGE sql IMMUTABLE AS $$
          SELECT CASE WHEN jsonb_typeof(c) = 'object' THEN
            COALESCE(
              (SELECT jsonb_object_agg(key, '{"redacted": true}'::jsonb) FROM jsonb_each(c)),
              '{}'::jsonb)
          ELSE c END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION audit_log_redact_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.entity_type = 'contact'
             AND (to_jsonb(NEW) - 'changes') = (to_jsonb(OLD) - 'changes')
             AND NEW.changes = audit_redact_changes(OLD.changes) THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION '% is append-only', TG_TABLE_NAME
            USING ERRCODE = 'insufficient_privilege';
        END
        $$
        """
    )
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute(
        "CREATE TRIGGER audit_log_append_only BEFORE DELETE OR TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_redact_only BEFORE UPDATE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_redact_only()"
    )


def downgrade() -> None:
    # Redacted rows stay redacted (values are gone); enum values cannot be dropped and stay.
    op.execute("DROP TRIGGER IF EXISTS audit_log_redact_only ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute(
        "CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()"
    )
    op.execute("DROP FUNCTION IF EXISTS audit_log_redact_only()")
    op.execute("DROP FUNCTION IF EXISTS audit_redact_changes(jsonb)")
    op.drop_constraint(
        "ck_privacy_deletion_profile_type", "privacy_deletion_profile", type_="check"
    )
    # Profiles of the new data types are configuration only (no financial or evidential
    # content); they cannot exist under the old constraint.
    op.execute("ALTER TABLE privacy_deletion_profile NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "DELETE FROM privacy_deletion_profile WHERE data_type IN "
        "('ai_run', 'call_log', 'webhook_delivery', 'postal_job')"
    )
    op.execute("ALTER TABLE privacy_deletion_profile FORCE ROW LEVEL SECURITY")
    op.create_check_constraint(
        "ck_privacy_deletion_profile_type",
        "privacy_deletion_profile",
        f"data_type IN {_TYPES_OLD}",
    )
