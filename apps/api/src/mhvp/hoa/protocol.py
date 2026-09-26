"""Minutes draft of an owners' meeting (A62, M25-04): document template with placeholders,
rendered as PDF on the tenant letterhead (``mhvp.documents.letters``) and filed as a draft.

The draft carries agenda, attendance with voting rights, the resolution text per item, the
tally as recorded, the announcement (or its absence) and signature lines. It is a working
draft only: no legal effect, no replacement of the signed minutes linked in
``Meeting.minutes_document_id``. Values come from the recorded meeting data; nothing is
estimated or completed by the system (rule 0.1.3)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents import letters
from mhvp.hoa.models import AgendaItem, Attendance, Meeting, Resolution

_LOCAL = ZoneInfo("Europe/Berlin")  # meeting time as invited, same choice as the letter date

DRAFT_NOTICE = (
    "Entwurf des Protokolls. Keine Rechtsfolge. Das unterschriebene Protokoll der "
    "Versammlungsleitung ersetzt diesen Entwurf."
)

# Document template (Jinja2 placeholders, rendered through letters.render_text with
# autoescape and StrictUndefined). Paragraphs are separated by blank lines; the attendance
# table is inserted through the [[table:anwesenheit]] marker of the letter renderer.
TEMPLATE = """Protokoll der {{ versammlung.art }} Eigentümerversammlung der {{ gemeinschaft.name }}

Objekt: {{ objekt.bezeichnung }}
Datum und Uhrzeit: {{ versammlung.datum }}, {{ versammlung.uhrzeit }} Uhr
Ort: {{ versammlung.ort }}
Form: {{ versammlung.form }}
Einladung vom: {{ versammlung.einladung }}
Versammlungsleitung: {{ leitung.name }}
Stimmprinzip: {{ versammlung.stimmprinzip }}

Tagesordnung

{% for top in tagesordnung %}TOP {{ top.nummer }}: {{ top.titel }}
{% endfor %}
Anwesenheit und Stimmrechte

[[table:anwesenheit]]

Anwesend oder vertreten: {{ anwesenheit.vertreten }} von {{ anwesenheit.gesamt }} Stimmen, \
{{ anwesenheit.einheiten_vertreten }} von {{ anwesenheit.einheiten_gesamt }} Einheiten.
Feststellung der Beschlussfähigkeit durch die Versammlungsleitung: ____________________

{% for top in tagesordnung %}TOP {{ top.nummer }}: {{ top.titel }}

Beschlusstext: {{ top.beschlusstext }}

Abstimmungsergebnis nach {{ top.prinzip }}:
Ja {{ top.ja }}, Nein {{ top.nein }}, Enthaltung {{ top.enthaltung }}\
{% if top.ausgeschlossen %}, vom Stimmrecht ausgeschlossen: {{ top.ausgeschlossen }}{% endif %}
Mehrheitserfordernis: {{ top.mehrheit }}

Verkündung: {{ top.verkuendung }}

{% endfor %}Unterschriften

Versammlungsleitung: ______________________________ ({{ leitung.name }})

Vorsitz des Verwaltungsbeirats: ______________________________

Weiteres Mitglied des Verwaltungsbeirats oder Protokollführung: ______________________________
"""

MEETING_KIND = {"ordinary": "ordentlichen", "extraordinary": "außerordentlichen"}
MEETING_MODE = {"presence": "Präsenz", "hybrid": "Hybrid", "virtual": "Virtuell"}
PRINCIPLE = {
    "head": "Kopfprinzip (eine Stimme je Eigentümer)",
    "mea": "Wertprinzip (Miteigentumsanteile)",
    "unit": "Objektprinzip (eine Stimme je Einheit)",
}
PRINCIPLE_SHORT = {"head": "Kopfprinzip", "mea": "Wertprinzip", "unit": "Objektprinzip"}
MAJORITY = {
    "simple": "einfache Mehrheit",
    "qualified": "qualifizierte Mehrheit",
    "unanimous": "Einstimmigkeit",
}
STATUS = {"positive": "angenommen", "negative": "abgelehnt"}
PLACEHOLDER = "nicht erfasst"


@dataclass
class ProtocolDraft:
    title: str
    filename: str
    context: dict[str, Any]
    letter: letters.Letter
    missing: list[str] = field(default_factory=list)


def _fmt_date(value: date | datetime | None) -> str:
    return value.strftime("%d.%m.%Y") if value else PLACEHOLDER


def _fmt_number(value: Any) -> str:
    text = f"{Decimal(str(value)).normalize():f}" if value not in (None, "") else "0"
    return text.replace(".", ",")


async def build_context(
    session: AsyncSession, meeting: Meeting
) -> tuple[dict[str, Any], list[str]]:
    """Template context from the recorded meeting data plus the list of values that are not
    recorded (shown as placeholders in the draft, never invented)."""
    from mhvp.contacts.models import Contact, Party
    from mhvp.hoa.meetings import _hoa_property, _members, _tally, _weight
    from mhvp.platform.models import User
    from mhvp.properties.models import LegalEntity, Property, Unit

    missing: list[str] = []
    entity = await session.get(LegalEntity, meeting.legal_entity_id)
    property_id = await _hoa_property(session, meeting.legal_entity_id)
    prop = await session.get(Property, property_id)
    day = meeting.scheduled_at.date()
    address = " ".join(p for p in (prop.street, prop.house_number) if p) if prop else ""
    place = " ".join(p for p in (prop.postal_code, prop.city) if p) if prop else ""
    objekt = ", ".join(
        p for p in (f"{prop.number} {prop.name}" if prop else "", address, place) if p
    )

    chair = await session.get(User, meeting.chair_user_id) if meeting.chair_user_id else None
    if chair is None:
        missing.append("Versammlungsleitung")
    if not meeting.location:
        missing.append("Ort")
    if meeting.invited_at is None:
        missing.append("Einladungsdatum")

    members = await _members(session, property_id, day)
    attendance = {
        a.contract_id: a
        for a in (
            await session.scalars(select(Attendance).where(Attendance.meeting_id == meeting.id))
        ).all()
    }
    rows: list[list[str]] = []
    total = Decimal(0)
    represented = Decimal(0)
    units_represented = 0
    seen_heads: set[uuid.UUID] = set()
    for contract in members:
        unit = await session.get(Unit, contract.unit_id)
        party = await session.get(Party, contract.party_id)
        att = attendance.get(contract.id)
        weight = await _weight(session, meeting.voting_principle, contract, property_id, day)
        if meeting.voting_principle == "head":
            # one vote per owner regardless of the number of units (§ 25 Abs. 2 WEG)
            if contract.party_id in seen_heads:
                weight = Decimal(0)
            seen_heads.add(contract.party_id)
        total += weight
        if att is not None and (att.present or att.proxy_contact_id):
            represented += weight
            units_represented += 1
            if att.proxy_contact_id:
                proxy = await session.get(Contact, att.proxy_contact_id)
                status = f"vertreten durch {proxy.display_name if proxy else PLACEHOLDER}"
            else:
                status = "anwesend (online)" if att.online else "anwesend"
        else:
            status = "nicht anwesend"
        rows.append(
            [
                unit.number if unit else PLACEHOLDER,
                party.name if party else PLACEHOLDER,
                status,
                _fmt_number(weight),
            ]
        )

    items = (
        await session.scalars(
            select(AgendaItem)
            .where(AgendaItem.meeting_id == meeting.id)
            .order_by(AgendaItem.position)
        )
    ).all()
    if not items:
        missing.append("Tagesordnung")
    tops: list[dict[str, Any]] = []
    for item in items:
        tally = await _tally(session, item, meeting)
        resolution = await session.scalar(
            select(Resolution).where(
                Resolution.subject_type == "agenda_item", Resolution.subject_id == item.id
            )
        )
        if resolution is None:
            announcement = "Ergebnis noch nicht verkündet."
        else:
            outcome = STATUS.get(resolution.status, resolution.status)
            announcement = (
                f"Beschluss Nr. {resolution.number}: {outcome}"
                f" ({resolution.majority_basis or PLACEHOLDER})."
            )
        rule = tally.get("rule")
        tops.append(
            {
                "nummer": item.position,
                "titel": item.title,
                "beschlusstext": item.proposal or PLACEHOLDER,
                "prinzip": PRINCIPLE_SHORT.get(str(tally["principle"]), str(tally["principle"])),
                "ja": _fmt_number(tally["yes"]),
                "nein": _fmt_number(tally["no"]),
                "enthaltung": _fmt_number(tally["abstain"]),
                "ausgeschlossen": int(tally["excluded"]),
                "mehrheit": rule["label"] if rule else MAJORITY.get(item.majority, item.majority),
                "verkuendung": announcement,
            }
        )
        if not item.proposal:
            missing.append(f"Beschlusstext TOP {item.position}")

    context = {
        "gemeinschaft": {"name": entity.name if entity else PLACEHOLDER},
        "objekt": {"bezeichnung": objekt or PLACEHOLDER},
        "versammlung": {
            "art": MEETING_KIND.get(meeting.kind, meeting.kind),
            "datum": _fmt_date(meeting.scheduled_at.astimezone(_LOCAL)),
            "uhrzeit": meeting.scheduled_at.astimezone(_LOCAL).strftime("%H:%M"),
            "ort": meeting.location or PLACEHOLDER,
            "form": MEETING_MODE.get(meeting.mode, meeting.mode),
            "einladung": _fmt_date(meeting.invited_at),
            "stimmprinzip": PRINCIPLE.get(meeting.voting_principle, meeting.voting_principle),
        },
        "leitung": {"name": chair.display_name if chair else PLACEHOLDER},
        "tagesordnung": tops,
        "anwesenheit": {
            "vertreten": _fmt_number(represented),
            "gesamt": _fmt_number(total),
            "einheiten_vertreten": units_represented,
            "einheiten_gesamt": len(members),
            "rows": rows,
        },
    }
    return context, missing


def compose(context: dict[str, Any], missing: list[str], today: date) -> ProtocolDraft:
    """Render the template into a letter; the table and the draft notice are attached."""
    body = letters.render_text(TEMPLATE, context)
    table = letters.LetterTable(
        header=["Einheit", "Eigentümer", "Anwesenheit", "Stimmrecht"],
        rows=list(context["anwesenheit"]["rows"]),
        right_aligned=(3,),
        widths=(0.12, 0.38, 0.35, 0.15),
    )
    name = str(context["gemeinschaft"]["name"])
    datum = str(context["versammlung"]["datum"])
    subject = letters.render_text(
        "Protokollentwurf Eigentümerversammlung {{ name }} vom {{ datum }}",
        {"name": name, "datum": datum},
    )
    notice = DRAFT_NOTICE
    if missing:
        notice += " Nicht erfasst: " + ", ".join(missing) + "."
    letter = letters.Letter(
        recipient_lines=[name, str(context["objekt"]["bezeichnung"])],
        subject=subject,
        body=body,
        letter_date=today,
        info=[("Versammlung", datum), ("Status", "Entwurf")],
        closing="",
        signatory=[],
        tables={"anwesenheit": table},
        notice=notice,
    )
    stamp = datum.replace(".", "-")
    return ProtocolDraft(
        title=f"Protokollentwurf Eigentümerversammlung {datum} (Entwurf)",
        filename=f"protokollentwurf-{stamp}.pdf",
        context=context,
        letter=letter,
        missing=missing,
    )


def render(head: letters.Letterhead, draft: ProtocolDraft) -> bytes:
    return letters.render_pdf(head, draft.letter)
