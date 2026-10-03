"""Celery application (section 3.2: queues default, io, ocr, ai, bank, mail, beat).

``celery -A mhvp.worker worker`` resolves ``app`` lazily. Reliability defaults for later
money flows: late acknowledgement, requeue on worker loss, prefetch 1. Tasks with economic
effect must additionally be idempotent (B08); the queue settings alone do not guarantee it.
"""

from functools import lru_cache
from typing import Any

from celery import Celery, signals
from celery.schedules import crontab
from kombu import Queue

from mhvp.core.config import Settings, get_settings
from mhvp.core.logging import configure_logging
from mhvp.core.task_policy import apply_beat_policy, celery_policy_conf
from mhvp.core.telemetry import instrument_celery

QUEUES: tuple[str, ...] = ("default", "io", "ocr", "ai", "bank", "mail", "beat")


def create_celery(settings: Settings | None = None, *, set_as_current: bool = False) -> Celery:
    """Build the Celery app. The process-wide instance is installed by `get_celery` as the
    default app; ``set_as_current`` additionally binds the *thread-local* current app and is
    off by default so that inspecting the configuration (tests, tooling) never rebinds the
    ``shared_task`` proxies of the calling thread to a throwaway instance."""
    settings = settings or get_settings()
    backend = settings.celery_result_backend
    reconciliation_hour, reconciliation_minute = (
        int(part) for part in settings.import_reconciliation_time.split(":")
    )
    app = Celery(
        "mhvp",
        set_as_current=set_as_current,
        broker=settings.celery_broker_url.get_secret_value(),
        backend=backend.get_secret_value() if backend else None,
        include=[
            "mhvp.core.tasks",
            "mhvp.core.webhook_tasks",
            "mhvp.portal.tasks",
            "mhvp.portal.assistant_job",
            "mhvp.documents.tasks",
            "mhvp.documents.paperless_webhook",
            "mhvp.documents.intake",
            "mhvp.documents.mirror_deletion",
            "mhvp.documents.retention",
            "mhvp.documents.deletion_checklist",
            "mhvp.documents.trash",
            "mhvp.ai.jobs",
            "mhvp.workspace.tasks",
            "mhvp.workspace.backup_verify",
            "mhvp.workspace.scale",
            "mhvp.communication.tasks",
            "mhvp.communication.postal_tasks",
            "mhvp.banking.tasks",
            "mhvp.banking.payment_run_tasks",
            "mhvp.accounting.tasks",
            "mhvp.letting.tasks",
            "mhvp.contracts.tasks",
            "mhvp.platform.licensing",
            "mhvp.platform.export_job",
            "mhvp.platform.availability_probe",
            "mhvp.sla.tasks",
            "mhvp.immoware.tasks",
            "mhvp.objektakte.tasks",
            "mhvp.automation.tasks",
            "mhvp.integrations.schadenstool.tasks",
            "mhvp.integrations.lexoffice_ext.tasks",
            "mhvp.imports.tasks",
            "mhvp.metering.tasks",
            "mhvp.billing.consumption_info_tasks",
            "mhvp.billing.deadline_tasks",
            "mhvp.hoa.inspection_transfer",
            "mhvp.core.auth.session_purge",
            "mhvp.privacy.proposals",
        ],
    )
    app.conf.update(
        task_queues=[Queue(name) for name in QUEUES],
        task_default_queue="default",
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        enable_utc=True,
        timezone="Europe/Berlin",
        broker_connection_retry_on_startup=True,
        result_expires=86_400,
        worker_hijack_root_logger=False,
        # Jobs of section 15.1 are added with their milestones and remain subject to the
        # release gates and domain checks (Freigabevorbehalt aller Zeitpläne).
        beat_schedule={
            # Webhook delivery is not a money flow; its retries follow section 12.
            "webhooks-dispatch": {
                "task": "mhvp.core.webhooks.dispatch",
                "schedule": 60.0,
                "options": {"queue": "io"},
            },
            # Claims adjuster link (INT-SDT-01): outbound queue and webhook events every minute,
            # reconciliation pull every 15 minutes; only tenants with the link enabled.
            "schadenstool-process": {
                "task": "mhvp.integrations.schadenstool.process",
                "schedule": 60.0,
                "options": {"queue": "io"},
            },
            "schadenstool-pull": {
                "task": "mhvp.integrations.schadenstool.pull",
                "schedule": 900.0,
                "options": {"queue": "io"},
            },
            # Lexware Office extension (INT-LEXO-01): outbound queue every minute for enabled
            # configs, retention purge of queue rows daily.
            "lexoffice-process": {
                "task": "mhvp.integrations.lexoffice.process",
                "schedule": 60.0,
                "options": {"queue": "io"},
            },
            "lexoffice-purge": {
                "task": "mhvp.integrations.lexoffice.purge",
                "schedule": crontab(hour=3, minute=20),
                "options": {"queue": "io"},
            },
            # Mirror copies to Paperless/Drive; only tenants with an enabled connection (11.1).
            "documents-mirror": {
                "task": "mhvp.documents.mirror",
                "schedule": 60.0,
                "options": {"queue": "io"},
            },
            # Upload of CRM documents to objektakte (filing in Drive and Paperless there); no-op
            # unless OBJEKTAKTE_UPLOAD_ENABLED and the read API are configured.
            "objektakte-upload": {
                "task": "mhvp.objektakte.upload",
                "schedule": 60.0,
                "options": {"queue": "io"},
            },
            # Document inbox (A42, 11.4, 15.1): daily 06:30, proposals only (rule 0.1.6);
            # Paperless, Drive inbox folder and mailbox attachments since the tenant watermark.
            "documents-process-inbox": {
                "task": "mhvp.documents.process_inbox",
                "schedule": crontab(hour=6, minute=30),
                "options": {"queue": "io"},
            },
            # Drive Changes API (M6-05): hourly, cursor per tenant; marks mirror files removed
            # in Drive, never deletes an index entry.
            "documents-drive-changes": {
                "task": "mhvp.documents.drive_changes",
                "schedule": crontab(minute=40),
                "options": {"queue": "io"},
            },
            # Temporary objects (M6-08): lifecycle rule for tmp/ and sweep of staged uploads.
            "documents-cleanup-tmp": {
                "task": "mhvp.documents.cleanup_tmp",
                "schedule": crontab(hour=4, minute=10),
                "options": {"queue": "io"},
            },
            # Restore test of the newest backup (A67, M9, 15.1 ops.backup_verify): daily
            # 02:00; result (status, duration, checked file, error) in /platform/ops/metrics.
            # Not configured tenants/hosts record "not_configured" instead of failing.
            "ops-backup-verify": {
                "task": "mhvp.ops.backup_verify",
                "schedule": crontab(hour=2, minute=0),
                "options": {"queue": "io"},
            },
            # Weekly measurement of the partitioning triggers of ADR 0021 (AE36, AC09-01): Monday
            # 03:10; stores one snapshot per ISO week, alarms platform administrators for a new
            # trigger. Measures and reports only; nothing is rebuilt.
            "ops-scale-snapshot": {
                "task": "mhvp.ops.scale_snapshot",
                "schedule": crontab(day_of_week=1, hour=3, minute=10),
                "options": {"queue": "io"},
            },
            # Maintenance reminders as in-app notifications (M9); idempotent per unread item.
            # Bank retrieval 06:00 (8.2); connectors without contract report "not configured".
            # Prospect records are deleted after their deletion date (M26).
            # Usage counters per tenant on the 1st (M27, operating metrics only).
            "platform-usage-all": {
                "task": "mhvp.platform.usage_all",
                "schedule": crontab(day_of_month=1, hour=2, minute=0),
            },
            # Daily snapshot of the usage counters for the history (M27-05).
            "platform-usage-daily": {
                "task": "mhvp.platform.usage_all",
                "schedule": crontab(hour=2, minute=10),
            },
            # Learning examples older than the tenant's retention months are deleted daily
            # (ADR 0010 addendum 27.09.2026, M7-04); one journal event per tenant.
            "ai-examples-retention": {
                "task": "mhvp.ai.examples_retention",
                "schedule": crontab(hour=3, minute=45),
            },
            # Nightly collective run of deferred AI runs (9.3 batch processing, M7-07).
            "ai-batch-nightly": {
                "task": "mhvp.ai.batch_nightly",
                "schedule": crontab(hour=1, minute=30),
                "options": {"queue": "io"},
            },
            # Hourly polling of submitted provider batches (9.3, GAB-09); no-op without any.
            "ai-batch-poll": {
                "task": "mhvp.ai.batch_poll",
                "schedule": crontab(minute=40),
                "options": {"queue": "io"},
            },
            # Monthly deletion proposal (M6-04, V17): lists documents whose released retention
            # period ended; deletes nothing, approval and execution are two persons.
            "documents-deletion-proposals": {
                "task": "mhvp.documents.deletion_proposals",
                "schedule": crontab(day_of_month=2, hour=4, minute=20),
            },
            # AC07 (GA08-08): daily follow up of recent deletions; repeats open targets
            # (original, derivatives, mirror steps), never deletes a restored document.
            "documents-deletion-follow-up": {
                "task": "mhvp.documents.deletion_follow_up",
                "schedule": crontab(hour=4, minute=50),
            },
            # AE33 (AC07-03): final deletion of trashed documents whose period ended; every
            # retention check runs again, a hold keeps the document in the trash.
            "documents-trash-purge": {
                "task": "mhvp.documents.trash_purge",
                "schedule": crontab(hour=5, minute=10),
            },
            # T01-01: delete expired tenant export archives (retention per tenant, default off).
            "platform-purge-expired-exports": {
                "task": "mhvp.platform.purge_expired_exports",
                "schedule": crontab(hour=3, minute=50),
                "options": {"queue": "io"},
            },
            "letting-purge-prospects": {
                "task": "mhvp.letting.purge_prospects",
                "schedule": crontab(hour=3, minute=30),
            },
            # AO03 (GAK-203): draft rent increase proposals, only with the tenant switch on.
            "letting-propose-rent-increases": {
                "task": "mhvp.letting.propose_rent_increases",
                "schedule": crontab(hour=4, minute=40),
            },
            # Payment run preview (S15-02, 15.1 payments.payment_run): Monday 08:00, only for
            # tenants that switched it on; lists only, no order, file or posting (G2).
            "payments-payment-run-preview": {
                "task": "mhvp.payments.payment_run",
                "schedule": crontab(day_of_week=1, hour=8, minute=0),
            },
            "banking-sync-all": {
                "task": "mhvp.banking.sync_all",
                "schedule": crontab(hour=6, minute=0),
                "options": {"queue": "io"},
            },
            # finAPI Stage 2: opt-in per tenant only (`FinApiTenantConfig.auto_fetch_enabled`,
            # default off); the task itself queues nothing for a tenant that has not opted in.
            "banking-finapi-scheduled-fetch": {
                "task": "mhvp.banking.finapi_scheduled_fetch",
                "schedule": crontab(hour=6, minute=30),
                "options": {"queue": "io"},
            },
            # GAB-02: daily EBICS C53 fetch, only tenants with the EBICS switch on (default
            # off) and subscribers in state ready; without transport the run logs BANK-0050.
            "banking-ebics-scheduled-fetch": {
                "task": "mhvp.banking.ebics_scheduled_fetch",
                "schedule": crontab(hour=6, minute=40),
                "options": {"queue": "io"},
            },
            # Consent reminder 10 days before an aggregator consent expires (A29, 8.2): daily,
            # per tenant, one notification per connection and expiry date.
            # M11-05: tenants with a configured sync hour other than 06:00 (bank_sync_setting).
            "banking-sync-due": {
                "task": "mhvp.banking.sync_due",
                "schedule": crontab(minute=2),
                "options": {"queue": "io"},
            },
            # Plan M12 S10: weekly L3 digest of the previous week, Monday morning.
            "banking-weekly-digest": {
                "task": "mhvp.banking.weekly_digest",
                "schedule": crontab(day_of_week=1, hour=5, minute=50),
                "options": {"queue": "io"},
            },
            # T03-02: provider comparison of the consent expiry before the reminders; tenants
            # opt in (tenant_settings.sources["bank_consent_sync"], default off).
            "banking-consent-provider-sync": {
                "task": "mhvp.banking.consent_provider_sync",
                "schedule": crontab(hour=7, minute=0),
                "options": {"queue": "io"},
            },
            "banking-consent-reminders": {
                "task": "mhvp.banking.consent_reminders",
                "schedule": crontab(hour=7, minute=5),
                "options": {"queue": "io"},
            },
            # Verbrauchsinformation (rule H03, 15.1 heating.consumption_info): monthly on the
            # 3rd at 05:40 as specified (S15-05), per tenant with the switch on (default off),
            # idempotent per unit and month.
            "billing-deadline-watch": {
                "task": "mhvp.billing.deadline_watch",
                "schedule": crontab(hour=5, minute=25),
            },
            # AF08 / GAA-02: ownership transfers -> owner check note on open inspection
            # requests (hint only, never closes a request).
            "hoa-inspection-ownership-scan": {
                "task": "mhvp.hoa.inspection_ownership_scan",
                "schedule": crontab(minute=23),
            },
            "billing-consumption-info": {
                "task": "mhvp.billing.consumption_info",
                "schedule": crontab(day_of_month=3, hour=5, minute=40),
            },
            # Receivable run (15.1 accounting.receivable_run, S15-01): on the 1st at 05:00 a
            # preview per tenant that switched it on; posting stays manual (G1).
            "accounting-receivable-run": {
                "task": "mhvp.accounting.receivable_run",
                "schedule": crontab(day_of_month=1, hour=5, minute=0),
            },
            # S69-04: nightly read copy of open item remainders (no posting).
            "accounting-open-item-balance": {
                "task": "mhvp.accounting.open_item_balance_refresh",
                "schedule": crontab(hour=2, minute=35),
            },
            # Dunning previews on the 5th (15.1); approval and sending stay manual.
            "accounting-dunning-run": {
                "task": "mhvp.accounting.dunning_run",
                "schedule": crontab(day_of_month=5, hour=6, minute=0),
            },
            # Gmail inbox sync for enabled mailboxes (M20-01); read only, Message-ID dedup.
            # Safety net next to the Pub/Sub push, every 60 s; runs do not overlap (Redis lock).
            "communication-gmail-sync": {
                "task": "mhvp.communication.gmail_sync_all",
                "schedule": 60.0,
                "options": {"queue": "mail"},
            },
            # IMAP fetch for mailboxes of kind imap (M20-01, decision 5 a); BODY.PEEK only,
            # same ingest pipeline as Gmail, runs do not overlap (Redis lock).
            "communication-imap-sync": {
                "task": "mhvp.communication.imap_sync_all",
                "schedule": 120.0,
                "options": {"queue": "mail"},
            },
            # Renewal of the Gmail push watches (Google ends them after seven days): daily
            # 04:10, renews every watch that expires within a day; no-op without a topic.
            "communication-gmail-watch-renew": {
                "task": "mhvp.communication.gmail_watch_renew_all",
                "schedule": crontab(hour=4, minute=10),
                "options": {"queue": "mail"},
            },
            # Gmail back channel (rule M20-08): hourly reconcile of the stored copy states
            # with the inbox listing of every enabled Gmail mailbox (minute 17, queue mail).
            "communication-gmail-state-reconcile": {
                "task": "mhvp.communication.gmail_state_reconcile_all",
                "schedule": crontab(minute=17),
                "options": {"queue": "mail"},
            },
            # Gmail back channel (rule M20-08): settle periods of pending group decisions.
            "communication-gmail-settle": {
                "task": "mhvp.communication.gmail_settle_all",
                "schedule": 60.0,
                "options": {"queue": "mail"},
            },
            # Catch up of Gmail archiving (operator 27.09.2026): every 15 minutes, all inbound
            # mails of the last 30 days that are done or requested but not archived; mailboxes
            # without gmail.modify wait until they are reconnected.
            "communication-archive-retry": {
                "task": "mhvp.communication.archive_retry_all",
                "schedule": 900.0,
                "options": {"queue": "mail"},
            },
            # Statusabruf beim Postdienst (M23-01): alle 30 Minuten, nur Mandanten mit
            # freigegebenem externem Anbieter; manuelle Aufträge werden nie abgefragt.
            "communication-postal-status-poll": {
                "task": "mhvp.communication.postal_status_poll_all",
                "schedule": 1800.0,
                "options": {"queue": "io"},
            },
            "workspace-reminders": {
                "task": "mhvp.workspace.reminders",
                "schedule": 3600.0,
            },
            # Mails zu Benachrichtigungen nach Benutzereinstellung (M23-04), alle 5 Minuten.
            "workspace-notification-mails": {
                "task": "mhvp.workspace.notification_mails",
                "schedule": 300.0,
            },
            # Tagessammelmail zu Benachrichtigungen mit Einstellung "täglich" (M23-04), 07:30.
            "workspace-notification-mails-daily": {
                "task": "mhvp.workspace.notification_mails_daily",
                "schedule": crontab(hour=7, minute=30),
            },
            # Daily digest per user 07:00 (A40, 15.1 tasks.digest): in-app notification, mail
            # only with the tenant switch (default off); idempotent per user and day.
            "workspace-digest": {
                "task": "mhvp.workspace.digest",
                "schedule": crontab(hour=7, minute=0),
            },
            # Deadline list 20:00 (A41, 15.1 compliance.deadlines): orientation only, lead time
            # from the tenant settings; no legal deadline calculation (M1-09).
            "workspace-compliance-deadlines": {
                "task": "mhvp.workspace.compliance_deadlines",
                "schedule": crontab(hour=20, minute=0),
            },
            # SLA-Ampel und Eskalation (M21 Übernahme aus dem Immoware Hub), alle 5 Minuten.
            # Regel-Engine (A38, A39, 15.2): neue Ereignisse je Mandant seit Wasserstand und
            # faellige Zeitplanregeln (einmal je Termin); Aktionen ohne Geldwirkung (Ticket,
            # Benachrichtigung, Ticketfeld, Webhook, Entwuerfe, KI-Vorschlag).
            "automation-process-events": {
                "task": "mhvp.automation.process_events",
                "schedule": 60.0,
            },
            # Lernender Buchhalter (ADR 0014, plan M12 S0): Ereignisverbrauch je Mandant seit
            # Wasserstand (Storno im Buchungskreis, Doppelumsatz geklaert, Kontaktloeschung);
            # bucht nichts, oeffnet kein Gate.
            "banking-process-events": {
                "task": "mhvp.banking.process_events",
                "schedule": 60.0,
            },
            # Automatikstufen (ADR 0014 Nachtrag S6, Regel M12-05): Nachtjob nur mit
            # Herabstufung aus den Kennzahlen der letzten 30 Tage; nie eine Anhebung.
            "banking-levels-refresh": {
                "task": "mhvp.banking.levels_refresh",
                "schedule": crontab(hour=4, minute=10),
            },
            # Lernspeicher (Betreiberentscheidung M12-06, 24 Monate): nächtliche
            # Anonymisierung statt Löschung (Guard-Trigger, B03), OPEN_QUESTIONS M12-09.
            "banking-learning-retention": {
                "task": "mhvp.banking.learning_retention",
                "schedule": crontab(hour=3, minute=50),
            },
            # SEPA mandates past ``valid_until`` become expired (M5-03), daily 03:40; no money
            # flow, direct debit of the affected contracts stops like on revocation.
            "contracts-expire-mandates": {
                "task": "mhvp.contracts.expire_mandates",
                "schedule": crontab(hour=3, minute=40),
            },
            "sla-check-clocks": {
                "task": "mhvp.sla.check_clocks",
                "schedule": 300.0,
            },
            # Portal account status model (6.2, AB08): expired and locked are persisted.
            "portal-account-status": {
                "task": "mhvp.portal.sync_account_status",
                "schedule": 900.0,
                "options": {"queue": "io"},
            },
            # Immoware24-DAV-Abholung (M32): Beat fest alle 15 Minuten, Task prueft selbst
            # anhand von ``poll_minutes``, ob ein Lauf faellig ist (read only, kein Schreibpfad).
            "immoware-sync-webdav": {
                "task": "mhvp.immoware.sync_webdav",
                "schedule": 900.0,
            },
            "immoware-sync-carddav": {
                "task": "mhvp.immoware.sync_carddav",
                "schedule": 900.0,
            },
            "immoware-sync-caldav": {
                "task": "mhvp.immoware.sync_caldav",
                "schedule": 900.0,
            },
            # objektakte differential import (M35 Stufe 5): daily 05:15, opt-in per tenant only
            # (`ObjektakteSyncState.enabled`, default off); the task skips every other tenant.
            "objektakte-sync-all": {
                "task": "mhvp.objektakte.sync_all",
                "schedule": crontab(hour=5, minute=15),
                "options": {"queue": "io"},
            },
            # Daily reconciliation report of the parallel operation (13.1, A68): staged
            # Immoware24 rows against platform figures, read and compare only; time of day from
            # ``Settings.import_reconciliation_time`` (default 05:30).
            "imports-reconciliation-report": {
                "task": "mhvp.imports.reconciliation_all",
                "schedule": crontab(hour=reconciliation_hour, minute=reconciliation_minute),
                "options": {"queue": "io"},
            },
        },
    )
    # AE35 (GB16-02): own availability measurement. The minute check exists only while at least
    # one health URL is configured; evaluation of the months and the retention purge of the
    # minute points run daily either way (no network, so old points are still handled after the
    # URLs were removed). Evaluation after 00:25 UTC, so the ended month is complete.
    if settings.availability_probe_urls:
        app.conf.beat_schedule["platform-availability-probe"] = {
            "task": "mhvp.platform.availability_probe",
            "schedule": 60.0,
            "options": {"queue": "io", "expires": 55},
        }
    app.conf.beat_schedule["platform-availability-evaluate"] = {
        "task": "mhvp.platform.availability_evaluate",
        "schedule": crontab(hour=3, minute=25),
        "options": {"queue": "io"},
    }
    app.conf.beat_schedule["platform-availability-purge"] = {
        "task": "mhvp.platform.availability_purge",
        "schedule": crontab(hour=3, minute=55),
        "options": {"queue": "io"},
    }
    # AJ12 (GAI-502): device descriptions of ended sessions are blanked, rows stay.
    app.conf.beat_schedule["auth-session-metadata-purge"] = {
        "task": "mhvp.core.auth.session_metadata_purge",
        "schedule": crontab(hour=4, minute=10),
        "options": {"queue": "io"},
    }
    # AJ12 (GAI-501): deletion proposals per released profile with auto_propose; only
    # proposals with four eyes release, nothing is deleted (V17 open).
    app.conf.beat_schedule["privacy-deletion-proposals"] = {
        "task": "mhvp.privacy.deletion_proposals",
        "schedule": crontab(hour=4, minute=25),
        "options": {"queue": "io"},
    }
    # Time limits, visibility timeout, retries and overlap locks (GAI-316 to GAI-319).
    app.conf.update(celery_policy_conf(settings))
    apply_beat_policy(app.conf.beat_schedule)
    return app


@lru_cache(maxsize=1)
def get_celery() -> Celery:
    """The process-wide Celery app, built once from the environment settings and installed as
    Celery's *default* app. `shared_task(...).delay()` resolves ``current_app``, which falls
    back to the default app when the calling thread never set one; the thread-local
    ``set_current()`` alone would not reach the request threads of an API process. Without
    this binding a fresh API process publishes to Celery's built-in default app
    (amqp://localhost) and every `.delay()` fails (prod incident MHVP-BANK-0057)."""
    app = create_celery()
    app.set_default()
    return app


@signals.setup_logging.connect
def _configure_worker_logging(**_: Any) -> None:
    configure_logging(get_settings())


@signals.worker_init.connect
@signals.worker_process_init.connect
def _install_job_gate_resolver(**_: Any) -> None:
    """Jobs resolve release gates from the database per tenant (GA14-01, rule 0.1.4)."""
    from mhvp.core.release_gates import JobDbReleaseGateResolver, install_job_release_gate_resolver

    install_job_release_gate_resolver(
        JobDbReleaseGateResolver(get_settings().database_url.get_secret_value())
    )


@signals.worker_process_init.connect
def _configure_worker_tracing(**_: Any) -> None:
    # After the fork, so the batch exporter thread lives in the child process; no-op unless
    # MHVP_OTEL_ENDPOINT is set (M9-02).
    instrument_celery(get_settings())


def __getattr__(name: str) -> Celery:
    if name in ("app", "celery"):
        return get_celery()
    raise AttributeError(name)
