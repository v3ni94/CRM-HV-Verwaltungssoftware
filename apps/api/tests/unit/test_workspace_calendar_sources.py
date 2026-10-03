"""GAH-312: the deadline source registry is fixed and complete (section 15.1)."""

from __future__ import annotations

import inspect

from mhvp.contacts.models import ContactNote
from mhvp.tickets.models import Ticket
from mhvp.workspace import jobs


def test_calendar_sources_complete() -> None:
    names = [reader.__name__ for reader in jobs.calendar_sources()]
    assert names == [
        "_read_contracts",
        "_read_meters",
        "_read_bank_consents",
        "_read_documents",
        "_read_service_contracts",
        "_read_meetings",
        "_read_maintenance",
        "_read_energy_certificates",
        "_read_note_follow_ups",
        "_read_ticket_due",
        "_read_work_order_appointments",
        "_read_deadline_entries",
        "_read_privacy_access_requests",
    ]


def test_every_reader_function_is_registered() -> None:
    declared = {
        name
        for name, obj in inspect.getmembers(jobs, inspect.iscoroutinefunction)
        if name.startswith("_read_")
    }
    assert declared == {reader.__name__ for reader in jobs.calendar_sources()}


def test_source_fields_exist() -> None:
    assert hasattr(ContactNote, "follow_up_on")
    assert hasattr(Ticket, "due_on")
    assert not hasattr(jobs, "_has_attr")
