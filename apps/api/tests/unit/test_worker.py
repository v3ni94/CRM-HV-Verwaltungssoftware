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
    assert set(conf.beat_schedule) == {
        "webhooks-dispatch",
        "documents-mirror",
        "workspace-reminders",
        "banking-sync-all",
        "accounting-dunning-run",
        "letting-purge-prospects",
        "platform-usage-all",
        "communication-gmail-sync",
        "sla-check-clocks",
    }
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
