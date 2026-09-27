"""Absage-Textbausteine (rejection text blocks) for the Interessentenverwaltung. Fixed,
non-legal wording (Produktschutz, not a legal opinion); an operator picks and, if needed,
edits the text before sending, it is never sent automatically (rule 0.1.6)."""

from __future__ import annotations

from typing import Any

REJECTION_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "id": "andere_wahl",
        "label": "Andere Bewerbung ausgewählt",
        "text": (
            "vielen Dank für Ihr Interesse an der Wohnung und für die eingereichten "
            "Unterlagen. Wir haben uns nach sorgfältiger Prüfung aller Bewerbungen für eine "
            "andere Interessentin oder einen anderen Interessenten entschieden. Wir bedauern, "
            "Ihnen keine positive Nachricht geben zu können, und wünschen Ihnen bei der "
            "weiteren Wohnungssuche viel Erfolg."
        ),
    },
    {
        "id": "unvollstaendige_unterlagen",
        "label": "Unterlagen unvollständig oder Selbstauskunft nicht eingegangen",
        "text": (
            "vielen Dank für Ihre Anfrage. Da uns die für eine Entscheidung erforderlichen "
            "Unterlagen beziehungsweise die Selbstauskunft nicht innerhalb der genannten Frist "
            "vorlagen, können wir Ihre Bewerbung leider nicht weiter berücksichtigen. Bei "
            "Interesse an einer künftigen Wohnung können Sie sich gerne erneut bei uns melden."
        ),
    },
    {
        "id": "objekt_nicht_mehr_verfuegbar",
        "label": "Objekt anderweitig vergeben oder zurückgezogen",
        "text": (
            "vielen Dank für Ihre Anfrage zu der genannten Wohnung. Diese ist inzwischen "
            "anderweitig vergeben beziehungsweise nicht mehr verfügbar. Wir bedauern, Ihnen "
            "keine positive Nachricht geben zu können, und wünschen Ihnen bei der weiteren "
            "Wohnungssuche viel Erfolg."
        ),
    },
    {
        "id": "kein_kontakt",
        "label": "Kein Rückmeldekontakt zustande gekommen",
        "text": (
            "wir haben in den letzten Wochen mehrfach versucht, mit Ihnen zu der genannten "
            "Wohnung Kontakt aufzunehmen, leider ohne Rückmeldung. Wir gehen daher davon aus, "
            "dass kein Interesse mehr besteht, und schließen Ihre Bewerbung. Bei weiterhin "
            "bestehendem Interesse melden Sie sich gerne erneut."
        ),
    },
)


def list_templates() -> list[dict[str, str]]:
    return [dict(t) for t in REJECTION_TEMPLATES]


def template_by_id(template_id: str) -> dict[str, Any] | None:
    for t in REJECTION_TEMPLATES:
        if t["id"] == template_id:
            return dict(t)
    return None
