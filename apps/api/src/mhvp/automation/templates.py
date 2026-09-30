"""Example rule templates (S13-04, section 13.4 Flow). Examples only: nothing is created
until the operator copies one into a rule; templates have no webhook to Flow and are never
active. The operator supplies the real Flow procedures (docs/integrations/dossier-flow.md)."""

from typing import Any

RULE_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "key": "urgent-ticket-notify",
        "name": "Dringendes Ticket melden",
        "description": "Benachrichtigt die Objektbetreuung bei dringenden Tickets.",
        "trigger_kind": "event",
        "trigger_event_type": "ticket.created",
        "conditions": {"field": "entity.priority", "op": "eq", "value": "urgent"},
        "actions": [
            {
                "type": "notify",
                "role_codes": ["caretaker"],
                "title": "Dringendes Ticket {payload.number}",
                "body": "{entity.title}",
            }
        ],
    },
    {
        "key": "damage-escalate",
        "name": "Schadensmeldung hoch priorisieren",
        "description": "Setzt die Priorität von Tickets der Kategorie Wasserschaden auf hoch.",
        "trigger_kind": "event",
        "trigger_event_type": "ticket.created",
        "conditions": {"field": "entity.category", "op": "eq", "value": "Wasserschaden"},
        "actions": [{"type": "set_ticket_field", "field": "priority", "value": "high"}],
    },
    {
        "key": "weekly-open-tickets-task",
        "name": "Wöchentliche Prüfung offener Tickets",
        "description": "Legt montags eine Aufgabe zur Durchsicht offener Tickets an.",
        "trigger_kind": "schedule",
        "schedule": {"frequency": "weekly", "weekday": 0, "time": "08:00"},
        "conditions": {},
        "actions": [
            {"type": "create_task", "title": "Offene Tickets durchsehen", "priority": "normal"}
        ],
    },
)
