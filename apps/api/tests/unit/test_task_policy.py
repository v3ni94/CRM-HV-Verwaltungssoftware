"""Celery task policy (GAI-316 to GAI-319): limits, visibility timeout, beat queues and
expiry, overlap lock and retry wrappers."""

from typing import Any

import pytest
from celery.exceptions import Retry

from mhvp.core import task_policy
from mhvp.core.config import Settings
from mhvp.core.task_policy import (
    FAST_BEAT_TASKS,
    IMPORT_TASKS,
    LONG_TASKS,
    NETWORK_RETRY_TASKS,
    NO_RETRY_REVIEWED,
    TaskPolicyAnnotation,
    limits_from_settings,
    task_class,
    visibility_timeout,
)
from mhvp.worker import QUEUES, create_celery


def test_limits_and_visibility_timeout(settings: Settings) -> None:
    limits = limits_from_settings(settings)
    for item in limits.values():
        assert item.soft < item.hard
    assert limits["short"].hard < limits["medium"].hard < limits["long"].hard
    assert limits["long"].hard < limits["import"].hard
    conf = create_celery(settings, set_as_current=False).conf
    vt = conf.broker_transport_options["visibility_timeout"]
    assert vt == visibility_timeout(limits)
    assert vt > max(item.hard for item in limits.values())
    assert conf.task_time_limit == limits["medium"].hard
    assert conf.task_soft_time_limit == limits["medium"].soft


def test_limits_are_overridable(settings: Settings) -> None:
    custom = settings.model_copy(
        update={"celery_limit_import_soft": 20_000, "celery_limit_import_hard": 21_000}
    )
    limits = limits_from_settings(custom)
    assert limits["import"].hard == 21_000
    assert visibility_timeout(limits) == 21_600
    bad = settings.model_copy(update={"celery_limit_short_soft": 300})
    with pytest.raises(ValueError, match="lower than the hard limit"):
        limits_from_settings(bad)


def test_every_task_gets_limits_and_classified_names_exist(settings: Settings) -> None:
    app = create_celery(settings, set_as_current=False)
    app.loader.import_default_modules()
    names = {name for name in app.tasks if name.startswith("mhvp.")}
    for group in (FAST_BEAT_TASKS, LONG_TASKS, IMPORT_TASKS, NETWORK_RETRY_TASKS):
        assert group <= names, group - names
    assert set(NO_RETRY_REVIEWED) <= names, set(NO_RETRY_REVIEWED) - names
    limits = limits_from_settings(settings)
    for name in names:
        task = app.tasks[name]
        expected = limits[task_class(name)]
        assert task.time_limit == expected.hard, name
        assert task.soft_time_limit == expected.soft, name
        wrapped = getattr(type(task).__call__, "__wrapped__", None) is not None
        assert wrapped == (
            name in FAST_BEAT_TASKS or name in NETWORK_RETRY_TASKS or name in NO_RETRY_REVIEWED
        ), name


def test_beat_entries_have_known_queue_and_registered_task(settings: Settings) -> None:
    app = create_celery(settings, set_as_current=False)
    app.loader.import_default_modules()
    names = set(app.tasks)
    for key, entry in app.conf.beat_schedule.items():
        assert entry["task"] in names, key
        assert entry["options"]["queue"] in QUEUES, key
        if entry["task"] in FAST_BEAT_TASKS and isinstance(entry["schedule"], int | float):
            assert entry["options"]["expires"] <= entry["schedule"], key
    fast_in_beat = {e["task"] for e in app.conf.beat_schedule.values()} & FAST_BEAT_TASKS
    assert fast_in_beat == FAST_BEAT_TASKS


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    def set(self, key: str, value: str, nx: bool, ex: int) -> bool:
        if nx and key in self.data:
            return False
        self.data[key] = value.encode()
        return True

    def get(self, key: str) -> bytes | None:
        return self.data.get(key)

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


class _Task:
    name = "mhvp.sla.check_clocks"

    class request:  # noqa: N801
        called_directly = False
        retries = 0

    def retry(self, exc: BaseException, countdown: int, max_retries: int) -> Retry:
        self.countdown = countdown
        return Retry(exc=exc, when=countdown)


def test_overlap_lock_skips_second_run(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(task_policy, "_redis_client", lambda _url: fake)
    annotation = TaskPolicyAnnotation(settings)
    around = annotation.annotate(_Task())
    assert around is not None
    calls: list[str] = []

    def inner(_task: Any) -> str:
        calls.append("run")
        # A concurrent second instance while the first holds the lock is skipped.
        assert wrapped(_task) is None
        return "ok"

    wrapped = around["@__call__"](inner)
    assert wrapped(_Task()) == "ok"
    assert calls == ["run"]
    assert fake.data == {}  # released after the run
    assert wrapped(_Task()) == "ok"


def test_overlap_lock_fails_open_without_redis(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_url: str) -> Any:
        raise ConnectionError("down")

    monkeypatch.setattr(task_policy, "_redis_client", broken)
    around = TaskPolicyAnnotation(settings).annotate(_Task())
    assert around is not None
    assert around["@__call__"](lambda _t: "ran")(_Task()) == "ran"


def test_lock_can_be_disabled(settings: Settings) -> None:
    custom = settings.model_copy(update={"celery_overlap_lock_enabled": False})
    around = TaskPolicyAnnotation(custom).annotate(_Task())
    assert around is not None
    assert "@__call__" not in around


def test_retry_only_for_transient_errors(settings: Settings) -> None:
    class Net(_Task):
        name = "mhvp.communication.gmail_push_sync"

    around = TaskPolicyAnnotation(settings).annotate(Net())
    assert around is not None
    task = Net()

    def flaky(_t: Any) -> None:
        raise ConnectionError("reset")

    with pytest.raises(Retry):
        around["@__call__"](flaky)(task)
    assert 1 <= task.countdown <= task_policy.RETRY_BASE_SECONDS

    def wrong(_t: Any) -> None:
        raise ValueError("domain")

    with pytest.raises(ValueError, match="domain"):
        around["@__call__"](wrong)(task)

    class Exhausted(Net):
        class request:  # noqa: N801
            called_directly = False
            retries = task_policy.RETRY_MAX

    with pytest.raises(ConnectionError):
        around["@__call__"](flaky)(Exhausted())


def test_money_runs_are_not_retried_or_locked(settings: Settings) -> None:
    annotation = TaskPolicyAnnotation(settings)
    for name in ("mhvp.accounting.dunning_run", "mhvp.payments.payment_run"):
        task = type("T", (), {"name": name})()
        result = annotation.annotate(task)
        assert result is not None
        assert "@__call__" not in result
        assert task_class(name) == "long"


def test_backoff_is_capped() -> None:
    for retries in range(10):
        assert 1 <= task_policy.retry_countdown(retries) <= task_policy.RETRY_CAP_SECONDS


def test_reviewed_tasks_are_never_retried_and_failures_are_noted(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """AK05 (GAI-317): the eight reviewed event tasks get no generic retry; a failure is
    logged with the verdict and re-raised, an own ``self.retry`` passes unchanged."""
    assert not set(NO_RETRY_REVIEWED) & NETWORK_RETRY_TASKS
    assert NO_RETRY_REVIEWED["mhvp.banking.compute_proposals"] == "money"
    assert NO_RETRY_REVIEWED["mhvp.banking.fints_step"] == "bank_dialog"

    class Fints(_Task):
        name = "mhvp.banking.fints_step"

    around = TaskPolicyAnnotation(settings).annotate(Fints())
    assert around is not None

    def flaky(_t: Any) -> None:
        raise ConnectionError("reset")

    with caplog.at_level("ERROR", logger="mhvp.core.task_policy"), pytest.raises(ConnectionError):
        around["@__call__"](flaky)(Fints())
    notes = [r for r in caplog.records if r.getMessage() == "task.failed_no_retry"]
    assert len(notes) == 1
    assert notes[0].__dict__["verdict"] == "bank_dialog"

    class Archive(_Task):
        name = "mhvp.communication.archive_message"

    own = TaskPolicyAnnotation(settings).annotate(Archive())
    assert own is not None

    def own_retry(_t: Any) -> None:
        raise Retry(exc=ConnectionError("x"), when=60)

    caplog.clear()
    with pytest.raises(Retry):
        own["@__call__"](own_retry)(Archive())
    assert not [r for r in caplog.records if r.getMessage() == "task.failed_no_retry"]
