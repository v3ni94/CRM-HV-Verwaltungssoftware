"""Minutes draft of an owners' meeting (A62, M25-04): document template with placeholders,
rendered as PDF on the tenant letterhead (``mhvp.documents.letters``) and filed as a draft.

The draft carries agenda, attendance with voting rights, the resolution text per item, the
tally as recorded, the announcement (or its absence) and signature lines. AE31 (AD06): for a
hybrid or virtual meeting, or when portal data exist, it also carries the online part (portal
confirmations, proxies, requests to speak, online votes per item, open vote conflicts and the
checklist of recorded facts for the meeting form; no legal statement). It is a working
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
from mhvp.hoa import meeting_rules
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
{% if versammlung.fristvermerk %}{{ versammlung.fristvermerk }}
{% endif %}Versammlungsleitung: {{ leitung.name }}
Stimmprinzip: {{ versammlung.stimmprinzip }}

Tagesordnung

{% for top in tagesordnung %}TOP {{ top.nummer }}: {{ top.titel }}
{% endfor %}
Anwesenheit und Stimmrechte

[[table:anwesenheit]]

Anwesend oder vertreten: {{ anwesenheit.vertreten }} von {{ anwesenheit.gesamt }} Stimmen, \
{{ anwesenheit.einheiten_vertreten }} von {{ anwesenheit.einheiten_gesamt }} Einheiten.
Feststellung der Beschlussfähigkeit durch die Versammlungsleitung: ____________________

{% if online.abschnitt %}{{ online.abschnitt }}

{% endif %}{% for top in tagesordnung %}TOP {{ top.nummer }}: {{ top.titel }}

Beschlusstext: {{ top.beschlusstext }}

Abstimmungsergebnis nach {{ top.prinzip }}:
Ja {{ top.ja }}, Nein {{ top.nein }}, Enthaltung {{ top.enthaltung }}\
{% if top.ausgeschlossen %}, vom Stimmrecht ausgeschlossen: {{ top.ausgeschlossen }}{% endif %}
Mehrheitserfordernis: {{ top.mehrheit }}
{% if top.online %}{{ top.online }}
{% endif %}
Verkündung: {{ top.verkuendung }}
{% if top.ergebnis %}Ergebnis: {{ top.ergebnis }}
{% endif %}{% if top.protokolltext %}
{{ top.protokolltext }}
{% endif %}
{% endfor %}Unterschriften

Versammlungsleitung: ______________________________ ({{ leitung.name }})

Vorsitz des Verwaltungsbeirats: ______________________________

Weiteres Mitglied des Verwaltungsbeirats oder Protokollführung: ______________________________
"""

MEETING_KIND = {
    "ordinary": "ordentlichen",
    "extraordinary": "außerordentlichen",
    "repeat": "wiederholten",
    "continuation": "fortgesetzten",
    "partial": "auf eine Untergemeinschaft beschränkten",
    "circular_resolution": "im Umlaufverfahren geführten",
}
ITEM_RESULT = {
    "accepted": "angenommen",
    "rejected": "abgelehnt",
    "deferred": "vertagt",
    "no_vote": "ohne Abstimmung",
}
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
    "all_owners": "Zustimmung aller Eigentümer",
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


PROXY_STATE = {"active": "wirksam erfasst", "inactive": "außerhalb des Zeitraums"}
SPEAKER_STATE = {"open": "offen", "done": "erledigt", "withdrawn": "zurückgezogen"}


def _unit_label(labels: dict[uuid.UUID, tuple[str, str]], contract_id: uuid.UUID | None) -> str:
    if contract_id is None:
        return "Verwaltung"
    return f"Einheit {labels.get(contract_id, (PLACEHOLDER, PLACEHOLDER))[0]}"


async def online_context(
    session: AsyncSession,
    meeting: Meeting,
    items: list[AgendaItem],
    labels: dict[uuid.UUID, tuple[str, str]],
) -> dict[str, Any]:
    """Online part of the draft (AE31, AD06): section text, one text block per agenda item and
    the review notes for the notice. Everything comes from recorded data; empty strings when a
    presence meeting has no portal data, so the draft stays unchanged then."""
    from sqlalchemy import or_

    from mhvp.hoa import online_meeting, online_rules
    from mhvp.hoa.models import MeetingProxy, MeetingSpeakerRequest, MeetingVoteConflict, Vote

    day = meeting.scheduled_at.date()
    item_ids = [i.id for i in items]
    position = {i.id: i.position for i in items}
    confirmed = (
        await session.scalars(
            select(Attendance)
            .where(Attendance.meeting_id == meeting.id, Attendance.portal_confirmed_at.is_not(None))
            .order_by(Attendance.portal_confirmed_at, Attendance.id)
        )
    ).all()
    speakers = (
        await session.scalars(
            select(MeetingSpeakerRequest)
            .where(MeetingSpeakerRequest.meeting_id == meeting.id)
            .order_by(MeetingSpeakerRequest.requested_at, MeetingSpeakerRequest.id)
        )
    ).all()
    online_votes = (
        (
            await session.scalars(
                select(Vote).where(Vote.agenda_item_id.in_(item_ids), Vote.channel == "online")
            )
        ).all()
        if item_ids
        else []
    )
    conflicts = (
        await session.scalars(
            select(MeetingVoteConflict)
            .where(MeetingVoteConflict.meeting_id == meeting.id)
            .order_by(MeetingVoteConflict.attempted_at, MeetingVoteConflict.id)
        )
    ).all()
    shown = meeting.mode != "presence" or bool(confirmed or speakers or online_votes or conflicts)
    if not shown:
        return {"abschnitt": "", "per_item": {}, "notices": []}

    per_item: dict[uuid.UUID, str] = {}
    for item in items:
        votes = [v for v in online_votes if v.agenda_item_id == item.id]
        lines: list[str] = []
        if votes or meeting.mode != "presence":
            by_proxy = sum(1 for v in votes if v.proxy_id is not None or v.cast_source == "proxy")
            line = f"Online abgegebene Stimmen: {len(votes)}"
            lines.append(line + (f", davon mit Vollmacht: {by_proxy}." if by_proxy else "."))
        lines += [
            "Prüfhinweis Stimmkonflikt. "
            + online_rules.conflict_sentence(
                unit=labels.get(c.contract_id, (PLACEHOLDER, PLACEHOLDER))[0],
                first_source=c.first_source,
                first_choice=c.first_choice,
                second_source=c.second_source,
                second_choice=c.second_choice,
                status=c.status,
                resolution=c.resolution,
            )
            for c in conflicts
            if c.agenda_item_id == item.id
        ]
        per_item[item.id] = "\n".join(lines)

    proxies = (
        await session.scalars(
            select(MeetingProxy)
            .where(
                MeetingProxy.legal_entity_id == meeting.legal_entity_id,
                or_(MeetingProxy.meeting_id.is_(None), MeetingProxy.meeting_id == meeting.id),
            )
            .order_by(MeetingProxy.created_at, MeetingProxy.id)
        )
    ).all()
    lines = ["Online-Teilnahme", ""]
    lines.append(
        f"Zusagen zur Online-Teilnahme im Eigentümerportal: {len(confirmed)}"
        + (
            " (" + ", ".join(_unit_label(labels, a.contract_id) for a in confirmed) + ")."
            if confirmed
            else "."
        )
    )
    if proxies:
        lines.append("Vollmachten über das Eigentümerportal, Stand am Versammlungstag:")
        for p in proxies:
            active = online_meeting.proxy_active(p, day, meeting.scheduled_at)
            until = f" bis {_fmt_date(p.valid_to)}" if p.valid_to else ""
            state = PROXY_STATE["active" if active else "inactive"]
            if p.revoked_at is not None:
                state = f"widerrufen am {_fmt_date(p.revoked_at.astimezone(_LOCAL))}"
            target = _unit_label(labels, p.proxy_contract_id if p.proxy_kind == "owner" else None)
            lines.append(
                f"{_unit_label(labels, p.grantor_contract_id)} an {target}, "
                f"gültig ab {_fmt_date(p.valid_from)}{until}, {state}."
            )
    else:
        lines.append("Vollmachten über das Eigentümerportal: keine erfasst.")
    if speakers:
        lines.append("Wortmeldungen über das Eigentümerportal:")
        for r in speakers:
            when = r.requested_at.astimezone(_LOCAL)
            top = f", TOP {position[r.agenda_item_id]}" if r.agenda_item_id in position else ""
            owner = labels.get(r.contract_id, (PLACEHOLDER, PLACEHOLDER))
            note = f": {r.note}" if r.note else ""
            lines.append(
                f"{when:%H:%M} Uhr, Einheit {owner[0]} ({owner[1]}){top}{note}, "
                f"{SPEAKER_STATE.get(r.status, r.status)}."
            )
    else:
        lines.append("Wortmeldungen über das Eigentümerportal: keine erfasst.")
    check = await online_meeting.admissibility(session, meeting)
    notices: list[str] = []
    if check["applicable"]:
        lines.append("")
        lines.append(
            "Prüfpunkte zur Versammlungsform (Übersicht der erfassten Angaben, keine "
            "Rechtsauskunft; die Zulässigkeit ist rechtlich zu klären):"
        )
        lines += [f"{c['label']}: {c['detail']} ({c['state_label']})" for c in check["checks"]]
        if not check["complete"]:
            notices.append("Prüfpunkte zur Versammlungsform offen.")
    open_conflicts = sum(1 for c in conflicts if c.status == "open")
    if open_conflicts:
        notices.append(f"Offene Stimmkonflikte (Vollmacht gegen eigene Stimme): {open_conflicts}.")
    return {"abschnitt": "\n".join(lines), "per_item": per_item, "notices": notices}


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
    labels: dict[uuid.UUID, tuple[str, str]] = {}
    total = Decimal(0)
    represented = Decimal(0)
    units_represented = 0
    seen_heads: set[uuid.UUID] = set()
    for contract in members:
        unit = await session.get(Unit, contract.unit_id)
        party = await session.get(Party, contract.party_id)
        att = attendance.get(contract.id)
        labels[contract.id] = (
            unit.number if unit else PLACEHOLDER,
            party.name if party else PLACEHOLDER,
        )
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
                status = "anwesend (online)" if att.online else "anwesend (Präsenz)"
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
    online = await online_context(session, meeting, list(items), labels)
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
                # GA03-02
                "ergebnis": ITEM_RESULT.get(item.result or ""),
                "protokolltext": item.minutes_text,
                # AE31: online votes of the item and review notes on vote conflicts
                "online": online["per_item"].get(item.id, ""),
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
            # M25-03: note when the invitation was recorded after the latest dispatch date
            "fristvermerk": meeting_rules.short_notice_note(
                meeting, await meeting_rules.invitation_weeks(session, meeting.tenant_id)
            )
            or "",
            "stimmprinzip": PRINCIPLE.get(meeting.voting_principle, meeting.voting_principle),
        },
        "leitung": {"name": chair.display_name if chair else PLACEHOLDER},
        "tagesordnung": tops,
        "online": {"abschnitt": online["abschnitt"], "notices": online["notices"]},
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
    for hint in context.get("online", {}).get("notices", []):
        notice += " " + hint
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
