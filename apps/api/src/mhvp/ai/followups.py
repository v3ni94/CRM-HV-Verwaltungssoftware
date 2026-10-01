"""Follow up steps offered after a confirmed chat creation (10.1 step 6, M7-04).

After the confirmation of a contact import, a property import or a chat action the platform
(not the model) derives which next steps make sense and offers them in the chat and in the
import summary: prepare portal invitations, create contracts, request missing data by form,
create units, file documents. Every step is only an offer: nothing is sent, invited or created
here; each step is a separate action that the user starts and confirms (rule 0.1.6, 10.3).
The derivation is deterministic and counts only records of this import run.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.models import AiMessage, ImportRun, ImportRunItem

CONTRACT_ROLES = {"owner", "tenant"}


def _step(code: str, label: str, href: str | None, count: int | None = None) -> dict[str, Any]:
    return {"code": code, "label": label, "href": href, "count": count}


async def _run_contact_ids(session: AsyncSession, import_run_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (
            await session.scalars(
                select(ImportRunItem.entity_id)
                .where(
                    ImportRunItem.import_run_id == import_run_id,
                    ImportRunItem.entity_type == "contact",
                )
                .order_by(ImportRunItem.sequence)
            )
        ).all()
    )


async def after_contacts(
    session: AsyncSession, import_run: ImportRun, role: str | None
) -> list[dict[str, Any]]:
    """Steps after a contact import: portal invitations (created contacts with an e-mail
    address and without a portal account), contracts (owners or tenants), missing data by form
    (contacts marked incomplete)."""
    from mhvp.contacts.models import Completeness, Contact, ContactEmail
    from mhvp.portal.models import PortalAccount

    ids = await _run_contact_ids(session, import_run.id)
    if not ids:
        return []
    with_mail = int(
        await session.scalar(
            select(func.count(func.distinct(ContactEmail.contact_id))).where(
                ContactEmail.contact_id.in_(ids),
                ~ContactEmail.contact_id.in_(select(PortalAccount.contact_id)),
            )
        )
        or 0
    )
    incomplete = int(
        await session.scalar(
            select(func.count(Contact.id)).where(
                Contact.id.in_(ids), Contact.completeness != Completeness.COMPLETE
            )
        )
        or 0
    )
    steps: list[dict[str, Any]] = []
    if with_mail:
        steps.append(
            _step(
                "portal_invites",
                f"Portaleinladungen vorbereiten ({with_mail} Kontakte mit E-Mail-Adresse)",
                "/kontakte",
                with_mail,
            )
        )
    if role in CONTRACT_ROLES:
        steps.append(_step("contracts", "Verträge anlegen", "/vertraege", len(ids)))
    if incomplete:
        steps.append(
            _step(
                "request_data",
                f"Fehlende Daten per Formular anfordern ({incomplete} unvollständige Kontakte)",
                "/portal/formulare",
                incomplete,
            )
        )
    return steps


def after_property(property_id: str | None) -> list[dict[str, Any]]:
    """Steps after a property was created (import or chat action)."""
    href = f"/objekte/{property_id}" if property_id else "/objekte"
    return [
        _step("units", "Einheiten und Gebäude prüfen oder anlegen", href),
        _step("documents", "Unterlagen der Vorverwaltung ablegen", href),
        _step("contracts", "Verträge anlegen", "/vertraege"),
    ]


def after_chat_action(kind: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    if kind == "property_create":
        return after_property(summary.get("property_id"))
    if kind == "portal_invite_prepare":
        return [
            _step(
                "invitation_letter",
                "Einladungsschreiben erzeugen oder Einladung per E-Mail versenden",
                f"/kontakte/{summary.get('contact_id')}" if summary.get("contact_id") else None,
            )
        ]
    if kind == "letter_create":
        return [
            _step(
                "letter_review",
                "Briefentwurf prüfen und versenden",
                f"/dokumente/{summary.get('document_id')}" if summary.get("document_id") else None,
            )
        ]
    return []


def text_of(steps: list[dict[str, Any]]) -> str:
    lines = [f"- {s['label']}" for s in steps]
    return "Mögliche nächste Schritte (jeweils eigene Bestätigung):\n" + "\n".join(lines)


def post_message(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    task_run_id: uuid.UUID | None,
    steps: list[dict[str, Any]],
) -> None:
    """Offers the steps as an assistant message of the chat the proposal came from."""
    if conversation_id is None or not steps:
        return
    session.add(
        AiMessage(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role="assistant",
            content=text_of(steps),
            document_ids=[],
            task_run_id=task_run_id,
            proposal_id=None,
            links=[],
        )
    )
