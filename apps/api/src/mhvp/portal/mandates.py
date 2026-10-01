"""Digital SEPA direct debit mandate from the portal (M3-02 portal stage, section 14).

A portal user reads the mandate text (creditor identifier of the legal entity, mandate
reference, recurring collection), enters an IBAN, confirms as account holder; the platform
records time stamp, IP address and the confirmed text as a PDF (Textform evidence) and files a
*proposal*. The proposal never becomes an active mandate by itself: a staff member decides in
the CRM, and acceptance only creates a contact bank account with mandate evidence that still
needs the four eyes release of the IBAN (M5-01). ``mhvp.contracts.models.SepaMandate`` (the
mandate used for collection) is not created here at all; collection stays locked until release
gate G2. The AI never decides here (rule 0.1.6).
"""

import io
import secrets
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contracts.models import Contract
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import session_allowed_property_ids
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal import access
from mhvp.portal.models import PortalAccount, SepaMandateProposal
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal", tags=["Portal"])
admin = APIRouter(prefix="/portal-admin", tags=["Portal Verwaltung"])
MANAGE = require_permission("contacts:update")

SCHEME = "core"
SEQUENCE = "recurrent"
STATUS_PROPOSED = "proposed"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"


# Text -----------------------------------------------------------------------------------

# Draft wording of the SEPA core mandate (recurring). The exact wording is to be confirmed by
# the operator with the collecting bank (docs/OPEN_QUESTIONS.md M3-03); until then the text is
# labelled as a draft in the rule register, not as a legal rule.
MANDATE_TEXT = (
    "SEPA-Lastschriftmandat (SEPA-Basislastschrift, wiederkehrende Zahlung)\n"
    "Zahlungsempfänger: {creditor_name}\n"
    "Gläubiger-Identifikationsnummer: {creditor_id}\n"
    "Mandatsreferenz: {reference}\n"
    "Vertrag: {contract_number}\n\n"
    "Ich ermächtige {creditor_name}, Zahlungen von meinem Konto mittels Lastschrift "
    "einzuziehen. Zugleich weise ich mein Kreditinstitut an, die von {creditor_name} auf mein "
    "Konto gezogenen Lastschriften einzulösen.\n\n"
    "Hinweis: Ich kann innerhalb von acht Wochen, beginnend mit dem Belastungsdatum, die "
    "Erstattung des belasteten Betrages verlangen. Es gelten dabei die mit meinem "
    "Kreditinstitut vereinbarten Bedingungen.\n\n"
    "Zahlungsart: wiederkehrende Zahlung\n"
    "Kontoinhaber: {holder}\n"
    "IBAN: {iban_masked}\n"
)


def mandate_text(
    *,
    creditor_name: str,
    creditor_id: str,
    reference: str,
    contract_number: str,
    holder: str,
    iban_masked: str,
) -> str:
    return MANDATE_TEXT.format(
        creditor_name=creditor_name,
        creditor_id=creditor_id,
        reference=reference,
        contract_number=contract_number,
        holder=holder,
        iban_masked=iban_masked,
    )


def new_reference(contract_number: str, today: date) -> str:
    """Mandate reference (max 35 characters, SEPA character set): contract number, date and a
    random suffix so that a renewed mandate of the same contract gets a new reference."""
    stem = "".join(ch for ch in contract_number.upper() if ch.isalnum() or ch == "-")[:20]
    return f"{stem}-{today:%Y%m%d}-{secrets.token_hex(2).upper()}"


def evidence_pdf(text: str, *, confirmed_at: datetime, ip: str | None, agent: str | None) -> bytes:
    """Textform evidence: the confirmed text, the time stamp, the IP address and the client."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="SEPA-Lastschriftmandat (Textform-Nachweis)",
    )
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, leading=14)
    head = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=13, leading=17)
    small = ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, leading=11)
    flow: list[Any] = [
        Paragraph("SEPA-Lastschriftmandat, Nachweis in Textform", head),
        Spacer(1, 6),
    ]
    for line in text.split("\n"):
        flow.append(Paragraph(_escape(line) or "&nbsp;", body))
    flow.append(Spacer(1, 10))
    stamp = confirmed_at.astimezone(UTC).strftime("%d.%m.%Y %H:%M:%S UTC")
    flow.append(Paragraph(f"Bestätigt durch den Kontoinhaber im Portal am {stamp}.", body))
    flow.append(Paragraph(f"IP-Adresse: {_escape(ip or 'unbekannt')}", small))
    flow.append(Paragraph(f"Client: {_escape(agent or 'unbekannt')}", small))
    flow.append(
        Paragraph(
            "Dieses Mandat wird erst nach Prüfung und Freigabe durch die Verwaltung verwendet; "
            "die Freigabe wird gesondert mitgeteilt.",
            small,
        )
    )
    doc.build(flow)
    return buffer.getvalue()


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Portal ---------------------------------------------------------------------------------


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PortalMandateIn(_In):
    contract_id: uuid.UUID
    iban: str = Field(min_length=15, max_length=40)
    holder: str = Field(min_length=2, max_length=200)
    bic: str | None = Field(default=None, min_length=8, max_length=11)
    # The account holder confirms the mandate text shown; without it nothing is recorded.
    confirmed: bool


async def _own_contract(
    session: AsyncSession, account: PortalAccount, contract_id: uuid.UUID
) -> Any:
    from mhvp.contracts.models import Contract

    active = await access.grants(session, account, local_today())
    if contract_id not in {g.scope_id for g in active if g.scope_type == "contract"}:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    contract = await session.get(Contract, contract_id)
    if contract is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return contract


async def _creditor(session: AsyncSession, legal_entity_id: uuid.UUID) -> tuple[str, str]:
    from mhvp.accounting.direct_debit import creditor_identifier
    from mhvp.properties.models import LegalEntity

    entity = await session.get(LegalEntity, legal_entity_id)
    creditor_id = await creditor_identifier(session, legal_entity_id)
    if entity is None or not creditor_id:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Für diesen Rechtsträger ist keine Gläubiger-Identifikationsnummer "
            "hinterlegt. Ein Mandat kann erst erteilt werden, wenn die Verwaltung sie "
            "eingetragen hat.",
        )
    return entity.name, creditor_id


def _out(row: SepaMandateProposal) -> dict[str, Any]:
    from mhvp.contacts.validation import mask_iban

    return {
        "id": row.id,
        "contract_id": row.contract_id,
        "legal_entity_id": row.legal_entity_id,
        "contact_id": row.contact_id,
        "creditor_id": row.creditor_id,
        "reference": row.reference,
        "scheme": row.scheme,
        "sequence": row.sequence,
        "holder": row.holder,
        "iban_masked": mask_iban(row.iban),
        "confirmed_at": row.confirmed_at,
        "status": row.status,
        "evidence_document_id": row.evidence_document_id,
        "decided_at": row.decided_at,
        "decision_note": row.decision_note,
        "contact_bank_account_id": row.contact_bank_account_id,
    }


@router.get("/sepa-mandates/preview", summary="Mandatstext für einen eigenen Vertrag")
async def preview(
    contract_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        contract = await _own_contract(session, account, contract_id)
        name, creditor_id = await _creditor(session, contract.legal_entity_id)
        reference = new_reference(contract.number, local_today())
        return {
            "contract_id": contract.id,
            "contract_number": contract.number,
            "creditor_name": name,
            "creditor_id": creditor_id,
            "reference": reference,
            "scheme": SCHEME,
            "sequence": SEQUENCE,
            "text": mandate_text(
                creditor_name=name,
                creditor_id=creditor_id,
                reference=reference,
                contract_number=contract.number,
                holder="(Kontoinhaber)",
                iban_masked="(IBAN)",
            ),
        }


@router.get(
    "/sepa-mandates", summary="Eigene Mandatsvorschläge", dependencies=[Depends(strict_query)]
)
async def mine(request: Request, ctx: Portal = Depends(portal_user)) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(SepaMandateProposal)
            .where(SepaMandateProposal.account_id == account.id)
            .order_by(SepaMandateProposal.created_at.desc())
        )
        return [_out(r) for r in rows.all()]


@router.post(
    "/sepa-mandates",
    status_code=201,
    summary="SEPA-Lastschriftmandat erteilen (Vorschlag, Freigabe durch die Verwaltung)",
)
async def create(
    body: PortalMandateIn, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.contacts.validation import InvalidValueError, mask_iban, normalise_iban
    from mhvp.contracts.models import ContractKind
    from mhvp.core import crypto
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import DocumentSource, LinkRole
    from mhvp.documents.services import store_document

    principal, account = ctx
    if not body.confirmed:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Das Mandat muss vom Kontoinhaber bestätigt werden."
        )
    try:
        iban = normalise_iban(body.iban)
    except InvalidValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from exc
    bic = body.bic.replace(" ", "").upper() if body.bic else None
    async with tenant_tx(request, principal) as session:
        contract = await _own_contract(session, account, body.contract_id)
        name, creditor_id = await _creditor(session, contract.legal_entity_id)
        today = local_today()
        reference = new_reference(contract.number, today)
        text = mandate_text(
            creditor_name=name,
            creditor_id=creditor_id,
            reference=reference,
            contract_number=contract.number,
            holder=body.holder.strip(),
            iban_masked=mask_iban(iban),
        )
        confirmed_at = datetime.now(UTC)
        ip = request.client.host if request.client else None
        agent = (request.headers.get("user-agent") or "")[:300] or None
        role = "owner" if contract.kind is ContractKind.OWNERSHIP else "tenant"
        doc = await store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=evidence_pdf(text, confirmed_at=confirmed_at, ip=ip, agent=agent),
            title=f"SEPA-Lastschriftmandat {reference}",
            filename=f"sepa-mandat-{reference}.pdf",
            mime_type="application/pdf",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=[
                ("contact", account.contact_id, LinkRole.ORIGINAL),
                ("contract", contract.id, LinkRole.ORIGINAL),
            ],
            created_by=principal.user_id,
            visibility=[role],
            scan_for_malware=False,
        )
        row = SepaMandateProposal(
            tenant_id=principal.tenant_id,
            account_id=account.id,
            contact_id=account.contact_id,
            contract_id=contract.id,
            legal_entity_id=contract.legal_entity_id,
            creditor_id=creditor_id,
            reference=reference,
            iban=iban,
            iban_suffix=iban[-4:],
            iban_fingerprint=crypto.fingerprint(iban),
            bic=bic,
            holder=body.holder.strip(),
            mandate_text=text,
            confirmed_at=confirmed_at,
            confirmed_ip=ip,
            user_agent=agent,
            evidence_document_id=doc.id,
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal.sepa_mandate.proposed",
            entity_type="portal_sepa_mandate_proposal",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"reference": reference, "contract_id": str(contract.id)},
        )
        return _out(row)


# CRM ------------------------------------------------------------------------------------


class DecideIn(_In):
    accept: bool
    note: str | None = Field(default=None, max_length=2000)


@admin.get(
    "/sepa-mandate-proposals",
    summary="Mandatsvorschläge aus dem Portal",
    dependencies=[Depends(strict_query)],
)
async def proposals(
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
    contact_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(SepaMandateProposal).order_by(SepaMandateProposal.created_at.desc())
        if contact_id is not None:
            query = query.where(SepaMandateProposal.contact_id == contact_id)
        if status is not None:
            query = query.where(SepaMandateProposal.status == status)
        allowed = session_allowed_property_ids(session)
        if allowed is not None:
            # Y01 (M2-02): with a property assignment only proposals whose contract lies in it.
            query = query.where(
                SepaMandateProposal.contract_id.in_(
                    select(Contract.id).where(Contract.property_id.in_(allowed))
                )
            )
        return [_out(r) for r in (await session.scalars(query.limit(500))).all()]


@admin.post(
    "/sepa-mandate-proposals/{proposal_id}/decide",
    summary="Mandatsvorschlag übernehmen oder ablehnen (kein aktives Mandat, G2)",
)
async def decide(
    proposal_id: uuid.UUID,
    body: DecideIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    from mhvp.contacts.models import (
        ContactBankAccount,
        MandateGrantedVia,
        MandateScheme,
    )

    async with tenant_tx(request, principal) as session:
        row = await session.get(SepaMandateProposal, proposal_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        allowed = session_allowed_property_ids(session)
        if allowed is not None:  # Y01 (M2-02): contract outside the assignment answers 404
            contract_property = await session.scalar(
                select(Contract.property_id).where(Contract.id == row.contract_id)
            )
            if contract_property not in allowed:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status != STATUS_PROPOSED:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits entschieden.")
        if body.accept:
            # Acceptance records the mandate evidence on a new contact bank account. The IBAN
            # stays "pending" until a second person releases it (M5-01); the collecting
            # mandate (sepa_mandate) is created only through the released CRM path (G2).
            bank = ContactBankAccount(
                tenant_id=row.tenant_id,
                contact_id=row.contact_id,
                iban=row.iban,
                iban_suffix=row.iban_suffix,
                iban_fingerprint=row.iban_fingerprint,
                bic=row.bic,
                holder=row.holder,
                valid_from=local_today(),
                sepa_enabled=True,
                mandate_reference=row.reference,
                mandate_signed_on=row.confirmed_at.date(),
                mandate_granted_via=MandateGrantedVia.PORTAL,
                mandate_document_id=row.evidence_document_id,
                mandate_scheme=MandateScheme.CORE,
                requested_by=principal.user_id,
            )
            session.add(bank)
            await session.flush()
            row.contact_bank_account_id = bank.id
        row.status = STATUS_ACCEPTED if body.accept else STATUS_REJECTED
        row.decided_by = principal.user_id
        row.decided_at = datetime.now(UTC)
        row.decision_note = body.note
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=f"portal.sepa_mandate.{row.status}",
            entity_type="portal_sepa_mandate_proposal",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "reference": row.reference,
                "contact_bank_account_id": str(row.contact_bank_account_id)
                if row.contact_bank_account_id
                else None,
            },
        )
        return _out(row)
