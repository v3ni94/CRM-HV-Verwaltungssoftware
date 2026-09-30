"""Generated draft of the Verarbeitungsverzeichnis and the processor register (S16-04, S711-10).

The text is assembled only from the register entries the operator maintains. It contains no
legal finding of its own; the notice that a lawyer has to review it (V13) is part of the
document and cannot be switched off.
"""

from __future__ import annotations

from datetime import date

from mhvp.privacy.models import PrivacyRegisterEntry

REVIEW_NOTICE = (
    "ENTWURF. Der Inhalt ist vor Verwendung durch einen Rechtsanwalt zu prüfen "
    "(offener Punkt V13). "
    "Er ersetzt keine rechtliche Bewertung."
)
_AVV = {
    "none": "kein Nachweis",
    "requested": "angefordert",
    "confirmed": "bestätigt",
    "not_required": "nicht erforderlich",
}


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "nicht erfasst"


def _fmt(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "offen"


def _third(e: PrivacyRegisterEntry) -> str:
    if not e.third_country:
        return "nein"
    return "ja, " + (e.third_country_note or "Garantien nicht erfasst")


def _review(e: PrivacyRegisterEntry) -> str:
    if e.legal_review_status == "reviewed":
        return "geprüft am " + _fmt(e.legal_reviewed_on)
    return "offen"


def render(tenant_name: str, entries: list[PrivacyRegisterEntry], today: date) -> str:
    active = [e for e in entries if e.active]
    lines = [
        "# Verzeichnis von Verarbeitungstätigkeiten (Entwurf)",
        "",
        f"Verantwortlicher: {tenant_name}",
        f"Stand: {_fmt(today)}",
        "",
        f"**{REVIEW_NOTICE}**",
        "",
        "## 1. Verarbeitungstätigkeiten",
        "",
    ]
    acts = [e for e in active if e.kind == "processing_activity"]
    for e in acts:
        lines += [
            f"### {e.name}",
            f"- Zweck: {e.purpose or 'nicht erfasst'}",
            f"- Kategorien personenbezogener Daten: {_join(list(e.data_categories))}",
            f"- Kategorien betroffener Personen: {_join(list(e.data_subjects))}",
            f"- Empfänger: {e.recipients or 'nicht erfasst'}",
            f"- Drittlandübermittlung: {_third(e)}",
            f"- Löschfristen: {e.retention_note or 'nicht erfasst'}",
            f"- Prüfstatus Rechtsanwalt: {_review(e)}",
            "",
        ]
    if not acts:
        lines += ["Keine Verarbeitungstätigkeit erfasst.", ""]
    lines += ["## 2. Verantwortlichkeiten", ""]
    resp = [e for e in active if e.kind == "responsibility"]
    lines += [
        f"- {e.name} ({e.role or 'Rolle offen'}): {e.purpose or 'nicht erfasst'}" for e in resp
    ] or ["Keine Verantwortlichkeit erfasst."]
    lines += ["", "## 3. Auftragsverarbeiter und Unterauftragnehmer", ""]
    procs = [e for e in active if e.kind in ("processor", "sub_processor")]
    for e in procs:
        kind = "Unterauftragnehmer" if e.kind == "sub_processor" else "Auftragsverarbeiter"
        third = "Drittland: ja" if e.third_country else "Drittland: nein"
        avv = _AVV[e.avv_status] + (f" am {_fmt(e.avv_confirmed_on)}" if e.avv_confirmed_on else "")
        lines.append(
            f"- {e.name} ({kind}), Zweck: {e.purpose or 'nicht erfasst'}, AVV: {avv}, {third}"
        )
    if not procs:
        lines.append("Kein Auftragsverarbeiter erfasst.")
    lines += ["", "## 4. Offene Punkte", ""]
    gaps = [
        f"- {e.name}: AVV-Nachweis fehlt" for e in procs if e.avv_status in ("none", "requested")
    ]
    gaps += [
        f"- {e.name}: Drittlandübermittlung ohne dokumentierte Garantie"
        for e in active
        if e.third_country and not e.third_country_note
    ]
    lines += gaps or ["Keine offenen Punkte aus dem Register erkennbar."]
    return "\n".join(lines) + "\n"
