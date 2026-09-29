"""Regel M19-11 Prozessflows: Katalog, deterministische Vorgangsart je Beispielmail (zwölf
Mails, eine je Vorgangsart, feste Erwartung), Zusammenführung mit der KI-Antwort und die
einmalige Checklisteninstanz."""

import re
from typing import Any

import pytest

from mhvp.communication import mail
from mhvp.communication.suggest import fallback_suggestion, merge_suggestion
from mhvp.core.auth.permissions import SYSTEM_ROLES
from mhvp.tickets import flows
from mhvp.workspace.jobs import DEADLINE_KINDS

EXAMPLES: dict[str, tuple[str, str]] = {
    "kuendigung": (
        "Kündigung meiner Wohnung",
        "Hiermit kündige ich das Mietverhältnis für die Wohnung im 2. OG zum 31.12.2026.",
    ),
    "vermietung": (
        "Bewerbung um die Wohnung",
        "Ich bin Mietinteressent und bitte um einen Besichtigungstermin. Selbstauskunft anbei.",
    ),
    "versicherungsschaden": (
        "Schadensmeldung Leitungswasser",
        "Im Keller ist ein Leitungswasserschaden entstanden, bitte an die Versicherung melden.",
    ),
    "reparaturanfrage": (
        "Heizung defekt",
        "Die Heizung im Wohnzimmer funktioniert nicht, bitte einen Handwerker schicken.",
    ),
    "beschwerde": (
        "Beschwerde über Ruhestörung",
        "Der Nachbar im 3. OG verstößt nachts regelmäßig gegen die Hausordnung.",
    ),
    "buchhaltung": (
        "Frage zur Nebenkostenabrechnung",
        "In der Abrechnung fehlt meine Zahlung vom März, bitte Kontoauszug prüfen.",
    ),
    "uebergabe": (
        "Wohnungsübergabe am 15.10.",
        "Können wir die Übergabe der Wohnung mit Zählerständen auf 10 Uhr legen?",
    ),
    "mieterhoehung": (
        "Mieterhöhung nach Mietspiegel",
        "Bitte den Fall zur Mietanpassung anlegen, Vergleichsmiete laut Mietspiegel 2026.",
    ),
    "gericht": (
        "Amtsgericht Köln, Az.: 123 C 45/26",
        "Anbei die Klage nebst Aufforderung zur Stellungnahme, Aktenzeichen siehe Betreff.",
    ),
    "objektuebernahme": (
        "Verwalterwechsel Objekt 210",
        "Wir übernehmen die Verwaltung ab 01.01.2027, Unterlagen der Vorverwaltung folgen.",
    ),
    "objektabgabe": (
        "Kündigung der Verwaltung Objekt 118",
        "Die Eigentümer haben den Verwaltervertrag gekündigt, Nachfolgeverwaltung bestellt.",
    ),
    "kaution": (
        "Kautionsrückzahlung",
        "Wann erhalte ich meine Kaution zurück? Die Kautionsabrechnung liegt mir nicht vor.",
    ),
}


def test_catalogue_has_twelve_consistent_entries() -> None:
    assert tuple(p["code"] for p in flows.PROCESS_CATALOGUE) == flows.PROCESS_CODES
    assert len(flows.PROCESS_CODES) == 12
    roles = {r.code for r in SYSTEM_ROLES}
    for process in flows.PROCESS_CATALOGUE:
        assert process["checklist"], process["code"]
        assert process["responsible_role"] in roles
        assert set(process["required_links"]) <= set(flows.LINK_KINDS)
        assert set(process["deadline_type_codes"]) <= set(DEADLINE_KINDS)
        assert process["document_kinds"]
        keys = [c["key"] for c in flows.catalogue_checklist(process)]
        assert len(keys) == len(set(keys))
        for label in process["checklist"]:
            assert not re.search("[\u2013\u2014]", label), label


@pytest.mark.parametrize(("code", "example"), sorted(EXAMPLES.items()))
def test_process_category_of_example_mails(code: str, example: tuple[str, str]) -> None:
    subject, body = example
    result = mail.process_category(subject, body)
    assert result["process_code"] == code, result
    assert 0.5 <= result["confidence"] <= 0.9
    assert result["reason"].startswith("Schlüsselwörter: ")


def test_process_category_without_keywords() -> None:
    result = mail.process_category("Hallo", "Vielen Dank für das Gespräch gestern.")
    assert result == {
        "process_code": None,
        "confidence": 0.0,
        "reason": "kein Schlüsselwort erkannt",
    }


def test_merge_suggestion_keeps_model_code_and_falls_back_on_unknown() -> None:
    subject, body = EXAMPLES["kaution"]
    fallback = fallback_suggestion(subject, body, [])
    assert fallback["process_code"] == "kaution"
    merged = merge_suggestion(
        {"process_code": "gericht", "process_confidence": 0.8, "process_reason": "Klage"},
        fallback,
    )
    assert merged["process_code"] == "gericht"
    assert merged["process_confidence"] == 0.8
    assert merged["process_reason"] == "Klage"
    merged = merge_suggestion({"process_code": "unbekannt"}, fallback)
    assert merged["process_code"] == "kaution"
    assert merged["process_reason"] == fallback["process_reason"]
    merged = merge_suggestion({}, fallback)
    assert merged["process_code"] == "kaution"


def test_instantiate_checklist_is_idempotent_and_keeps_marks() -> None:
    template = flows.catalogue_checklist(flows.PROCESS_BY_CODE["kuendigung"])
    first = flows.instantiate_checklist([], template)
    assert len(first) == len(template)
    assert all(item["done"] is False for item in first)
    first[0]["done"] = True
    again = flows.instantiate_checklist(first, template)
    assert len(again) == len(template)
    assert again[0]["done"] is True
    extra: list[dict[str, Any]] = [{"key": "eigen", "label": "Eigener Punkt", "required": True}]
    merged = flows.instantiate_checklist(extra, template)
    assert merged[0]["key"] == "eigen"
    assert len(merged) == len(template) + 1
