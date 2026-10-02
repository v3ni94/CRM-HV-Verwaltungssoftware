from mhvp import worker
from mhvp.core.config import Settings
from mhvp.worker import QUEUES, create_celery


def test_queues_and_reliability_settings(settings: Settings) -> None:
    app = create_celery(settings)
    conf = app.conf
    assert [queue.name for queue in conf.task_queues] == list(QUEUES)
    assert QUEUES == ("default", "io", "ocr", "ai", "bank", "mail", "beat")
    assert conf.task_default_queue == "default"
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.enable_utc is True
    assert conf.accept_content == ["json"]
    # Subset check: other tasks (A29, A38) add their own beat entries in parallel.
    assert set(conf.beat_schedule) >= {
        "webhooks-dispatch",
        "documents-mirror",
        "documents-process-inbox",
        "workspace-reminders",
        "banking-sync-all",
        "banking-finapi-scheduled-fetch",
        "accounting-dunning-run",
        "letting-purge-prospects",
        "platform-usage-all",
        "communication-gmail-sync",
        "sla-check-clocks",
        "immoware-sync-webdav",
        "immoware-sync-carddav",
        "immoware-sync-caldav",
        "objektakte-sync-all",
        "workspace-digest",
        "workspace-compliance-deadlines",
    }
    assert conf.beat_schedule["communication-gmail-sync"]["schedule"] == 60.0
    assert conf.beat_schedule["workspace-digest"]["task"] == "mhvp.workspace.digest"
    assert (
        conf.beat_schedule["workspace-compliance-deadlines"]["task"]
        == "mhvp.workspace.compliance_deadlines"
    )
    assert conf.beat_schedule["webhooks-dispatch"]["task"] == "mhvp.core.webhooks.dispatch"


def test_ping_task(settings: Settings) -> None:
    app = create_celery(settings)
    app.loader.import_default_modules()
    result = app.tasks["mhvp.core.ping"].apply()
    assert result.get() == "pong"


def test_lazy_module_attribute(monkeypatch: object) -> None:
    import pytest

    with pytest.raises(AttributeError):
        _ = worker.does_not_exist


def test_document_jobs_registered(settings: Settings) -> None:
    """A42 inbox job on the beat plan and A43 mirror deletion task with retry ladder."""
    from mhvp.documents import mirror_deletion

    app = create_celery(settings)
    app.loader.import_default_modules()
    assert "mhvp.documents.process_inbox" in app.tasks
    inbox = app.conf.beat_schedule["documents-process-inbox"]
    assert inbox["task"] == "mhvp.documents.process_inbox"
    assert inbox["options"] == {"queue": "io"}
    assert str(inbox["schedule"]) == "<crontab: 30 6 * * * (m/h/dM/MY/d)>"
    task = app.tasks[mirror_deletion.TASK_NAME]
    assert task.max_retries == len(mirror_deletion.BACKOFF_SECONDS)


def test_gmail_sync_lock_prevents_overlap() -> None:
    from mhvp.communication import tasks

    class FakeRedis:
        def __init__(self) -> None:
            self.keys: set[str] = set()

        def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
            if nx and key in self.keys:
                return False
            self.keys.add(key)
            return True

        def delete(self, key: str) -> None:
            self.keys.discard(key)

    fake = FakeRedis()
    assert tasks._try_sync_lock(fake) is True
    assert tasks._try_sync_lock(fake) is False
    tasks._release_sync_lock(fake)
    assert tasks._try_sync_lock(fake) is True
    assert tasks._try_sync_lock(None) is True


def test_gmail_settle_default_is_180() -> None:
    from mhvp.platform.models import TenantSettings
    from mhvp.platform.schemas import TenantSettingsOut, TenantSettingsPatch

    assert TenantSettingsOut.model_fields["gmail_settle_seconds"].default == 180
    assert TenantSettings.__table__.c.gmail_settle_seconds.default.arg == 180
    field = TenantSettingsPatch.model_fields["gmail_settle_seconds"]
    assert {type(m).__name__: m for m in field.metadata}["Ge"].ge == 0


def test_shared_tasks_publish_to_the_configured_broker(settings: Settings) -> None:
    """`shared_task(...).delay()` resolves `current_app`; the API binds it at startup via
    `get_celery()`. Without the binding the task would target Celery's default app
    (amqp://localhost) and every enqueue fails (prod incident MHVP-BANK-0057)."""
    import threading

    from celery import _state

    from mhvp.banking.tasks import fints_step

    app = create_celery(settings, set_as_current=False)
    previous = _state.default_app
    app.set_default()
    try:
        seen: list[object] = []
        # A thread that never set a current app (API request threads) must resolve the task
        # of the configured app, not Celery's built-in default.
        worker = threading.Thread(target=lambda: seen.append(fints_step.app))
        worker.start()
        worker.join()
        assert seen == [app]
        assert app.conf.broker_url == settings.celery_broker_url.get_secret_value()
    finally:
        _state.set_default_app(previous)
