"""Portal assistant: questions about the documents a person may read (AE28, M7-06, SA-04).

Next to the ticket chat (``mhvp.portal.chat``, a message channel with the management) the
assistant answers questions of a tenant or owner from the documents released for that person.
It is a feature of the tenant, off until ``PortalFeatureSetting.chat_bot_enabled`` is on:

* **Permission filter** (security critical): the readable documents come from the access matrix
  of the account only (``mhvp.portal.assistant_scope``). A unit or document outside the grants
  answers 404, an account without grants has an empty scope and the assistant calls no provider.
* **Search without AI** is always possible when the switch is on: the full text search runs over
  the released documents and lists hits as links to the portal document list.
* **AI answer** needs the privacy feature (``privacy_feature_enabled``) with a released privacy
  notice (text block ``portal_chat_privacy_notice``, four eyes) that the person has acknowledged
  for the current version, and the open gateway gate (released provider with data processing
  agreement and training opt out, masking, budget; ``mhvp.ai.portal_answer``). Otherwise the
  answer falls back to the search hits and says why.
* **Log**: every question is stored masked with mode, status and checked sources
  (``PortalChatLog``); the management reads it with ``tenant_settings:update``.

Nothing here decides, books or promises anything: the answer is information (rule 0.1.6). The
text of the privacy notice is maintained and released by the operator; the software ships none."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import session_allowed_property_ids
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal import assistant_scope, features
from mhvp.portal.models import (
    PortalAccount,
    PortalChatLog,
    PortalChatPrivacyAck,
    PortalFeatureSetting,
)
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal/assistant", tags=["Portal"])
admin = APIRouter(prefix="/portal-admin/assistant", tags=["Portal Verwaltung"])
MANAGE = require_permission("tenant_settings:update")

PRIVACY_NOTICE_CODE = "portal_chat_privacy_notice"
HOURLY_LIMIT = 20  # questions per account and hour (cost protection, Produktschutz)
MAX_HITS = 5
MAX_SCOPE_DOCUMENTS = 200
NOTICE = (
    "Automatisch erstellte Hinweise auf Grundlage Ihrer freigegebenen Unterlagen. Sie sind eine "
    "Orientierung und keine Auskunft, Entscheidung oder Zusage der Verwaltung. Bei Fragen zu "
    "Ansprüchen, Fristen oder Beträgen wenden Sie sich bitte mit einer Meldung an die Verwaltung."
)
EMERGENCY_NOTE = "Bei Gefahr für Leib und Leben rufen Sie bitte sofort den Notruf 112 an."
MESSAGES = {
    "privacy_feature_off": (
        "Die KI-Antwort ist nicht eingeschaltet. Sie sehen Treffer aus Ihren Unterlagen."
    ),
    "privacy_notice_not_released": (
        "Der Datenschutzhinweis zur KI-Antwort ist noch nicht freigegeben. "
        "Sie sehen Treffer aus Ihren Unterlagen."
    ),
    "privacy_ack_missing": (
        "Bitte nehmen Sie zuerst den Datenschutzhinweis zur Kenntnis. "
        "Bis dahin sehen Sie Treffer aus Ihren Unterlagen."
    ),
    "provider_not_released": (
        "Die KI-Antwort ist derzeit nicht verfügbar. Sie sehen Treffer aus Ihren Unterlagen."
    ),
    "ai_run_failed": (
        "Die KI-Antwort ist derzeit nicht verfügbar. Sie sehen Treffer aus Ihren Unterlagen."
    ),
    "no_grant": "Für Ihren Zugang sind keine Unterlagen freigegeben, die der Assistent lesen darf.",
    "no_documents": (
        "In dieser Auswahl liegen keine Unterlagen, die der Assistent für Sie lesen darf."
    ),
}


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PortalAssistantQuestionIn(_In):
    question: str = Field(min_length=3, max_length=2000)
    unit_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None


class PortalAssistantAckIn(_In):
    text_version: int = Field(ge=1)


class PortalAssistantSourceOut(BaseModel):
    document_id: uuid.UUID
    title: str
    excerpt: str | None = None


class PortalAssistantHitOut(BaseModel):
    document_id: uuid.UUID
    title: str


class PortalAssistantAnswerOut(BaseModel):
    id: uuid.UUID
    mode: Literal["ai", "search"]
    status: Literal["answered", "not_answerable", "failed", "search_hits", "no_sources"]
    answer: str | None
    sources: list[PortalAssistantSourceOut]
    hits: list[PortalAssistantHitOut]
    ai_available: bool
    ai_blocked_code: str | None
    ai_blocked_reason: str | None
    notice: str
    emergency_note: str
    created_at: datetime


@dataclass(frozen=True)
class AiState:
    available: bool
    code: str | None = None
    message: str | None = None
    technical: str | None = None


async def _enabled(session: Any) -> PortalFeatureSetting:
    row: PortalFeatureSetting = await features.get_or_default(session)
    if not row.chat_bot_enabled:
        raise ProblemError(ErrorCodes.PORTAL_ASSISTANT_LOCKED)
    return row


async def privacy_notice(session: Any) -> Any:
    """The approved privacy notice text block (four eyes release), or ``None``."""
    from mhvp.documents.models import LegalTextBlock

    return await session.scalar(
        select(LegalTextBlock).where(
            LegalTextBlock.code == PRIVACY_NOTICE_CODE, LegalTextBlock.status == "approved"
        )
    )


async def ai_state(session: Any, row: PortalFeatureSetting, account: PortalAccount) -> AiState:
    """Whether the AI answer may run for this account right now, with a coded reason. The
    privacy feature, the released notice and the acknowledgement come first, the gateway gate
    (released provider, data processing agreement, budget) last."""
    from mhvp.ai import gateway
    from mhvp.ai.models import AiTask

    if not row.privacy_feature_enabled:
        return AiState(False, "privacy_feature_off", MESSAGES["privacy_feature_off"])
    notice = await privacy_notice(session)
    if notice is None:
        return AiState(
            False, "privacy_notice_not_released", MESSAGES["privacy_notice_not_released"]
        )
    acknowledged = await session.scalar(
        select(PortalChatPrivacyAck.id).where(
            PortalChatPrivacyAck.account_id == account.id,
            PortalChatPrivacyAck.text_block_id == notice.id,
        )
    )
    if acknowledged is None:
        return AiState(False, "privacy_ack_missing", MESSAGES["privacy_ack_missing"])
    try:
        await gateway.route(session, AiTask.ANSWER_QUESTION)
    except gateway.GatewayBlockedError as exc:
        return AiState(
            False, "provider_not_released", MESSAGES["provider_not_released"], str(exc)[:500]
        )
    return AiState(True)


def _hit_out(document: Any) -> dict[str, Any]:
    return {"document_id": document.id, "title": document.title or document.filename}


async def _hits(session: Any, scope: assistant_scope.AssistantScope, text: str) -> list[Any]:
    """Full text hits inside the scope (the scope filters before the limit)."""
    from mhvp.ai import gateway

    if scope.empty:
        return []
    return await gateway.retrieve_keyword(
        session, text, MAX_HITS, only_ids=sorted(scope.document_ids)
    )


async def _check_rate(session: Any, account: PortalAccount) -> None:
    from datetime import UTC

    since = datetime.now(UTC) - timedelta(hours=1)
    used = await session.scalar(
        select(func.count())
        .select_from(PortalChatLog)
        .where(PortalChatLog.account_id == account.id, PortalChatLog.created_at >= since)
    )
    if int(used or 0) >= HOURLY_LIMIT:
        raise ProblemError(
            ErrorCodes.RATE_LIMITED,
            detail=f"Es sind höchstens {HOURLY_LIMIT} Fragen pro Stunde möglich.",
        )


def _no_scope_code(scope: assistant_scope.AssistantScope) -> str:
    return "no_grant" if not scope.unit_ids and scope.readable_documents == 0 else "no_documents"


@router.get(
    "/status",
    summary="Status des Portal-Assistenten",
    dependencies=[Depends(strict_query)],
)
async def assistant_status(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    """Switch, privacy notice (text and version only when released), acknowledgement, whether the
    AI answer is available (coded reason) and the size of the readable scope."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        row = await _enabled(session)
        scope = await assistant_scope.build_scope(session, account, local_today())
        state = await ai_state(session, row, account)
        notice = await privacy_notice(session) if row.privacy_feature_enabled else None
        acknowledged = False
        if notice is not None:
            acknowledged = (
                await session.scalar(
                    select(PortalChatPrivacyAck.id).where(
                        PortalChatPrivacyAck.account_id == account.id,
                        PortalChatPrivacyAck.text_block_id == notice.id,
                    )
                )
            ) is not None
        return {
            "enabled": True,
            "privacy": {
                "feature_enabled": bool(row.privacy_feature_enabled),
                "notice_status": (
                    "not_required"
                    if not row.privacy_feature_enabled
                    else ("released" if notice is not None else "not_released")
                ),
                "title": notice.title if notice is not None else None,
                "body": notice.body if notice is not None else None,
                "version": notice.version if notice is not None else None,
                "acknowledged": acknowledged,
            },
            "ai": {
                "available": state.available,
                "blocked_code": state.code,
                "blocked_message": state.message,
            },
            "scope": {
                "units": len(scope.unit_ids),
                "documents": scope.readable_documents,
            },
            "hourly_limit": HOURLY_LIMIT,
            "notice": NOTICE,
            "emergency_note": EMERGENCY_NOTE,
        }


@router.get(
    "/scope",
    summary="Einheiten und Unterlagen, die der Assistent lesen darf",
    dependencies=[Depends(strict_query)],
)
async def assistant_scope_view(
    request: Request,
    unit_id: uuid.UUID | None = Query(default=None),
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    """The permission filter made visible: the units with a grant and the documents the
    assistant may read (all, or narrowed to one unit). A unit without grant answers 404; an
    account without grants gets empty lists."""
    from mhvp.documents.models import Document
    from mhvp.properties.models import Unit

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _enabled(session)
        scope = await assistant_scope.build_scope(session, account, local_today(), unit_id=unit_id)
        units = (
            (await session.scalars(select(Unit).where(Unit.id.in_(scope.unit_ids)))).all()
            if scope.unit_ids
            else []
        )
        documents = (
            (
                await session.scalars(
                    select(Document)
                    .where(Document.id.in_(scope.document_ids))
                    .order_by(func.lower(Document.title), Document.id)
                    .limit(MAX_SCOPE_DOCUMENTS)
                )
            ).all()
            if scope.document_ids
            else []
        )
        return {
            "focus_unit_id": scope.focus_unit_id,
            "units": [
                {"id": u.id, "number": u.number, "label": u.label}
                for u in sorted(units, key=lambda x: (x.number, str(x.id)))
            ],
            "documents": [_hit_out(d) for d in documents],
            "total_documents": len(scope.document_ids),
        }


@router.post("/privacy-ack", summary="Datenschutzhinweis zur KI-Antwort zur Kenntnis nehmen")
async def acknowledge_privacy(
    body: PortalAssistantAckIn, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """Records that the person took note of the approved notice in exactly the named version.
    No acknowledgement without the privacy feature, a released text and the current version;
    repeating it changes nothing. It is no consent decision and opens no gate."""
    from datetime import UTC

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        row = await _enabled(session)
        notice = await privacy_notice(session) if row.privacy_feature_enabled else None
        if notice is None or notice.version != body.text_version:
            raise ProblemError(ErrorCodes.PORTAL_ASSISTANT_PRIVACY_STATE)
        existing = await session.scalar(
            select(PortalChatPrivacyAck).where(
                PortalChatPrivacyAck.account_id == account.id,
                PortalChatPrivacyAck.text_block_id == notice.id,
            )
        )
        if existing is None:
            existing = PortalChatPrivacyAck(
                tenant_id=principal.tenant_id,
                account_id=account.id,
                text_block_id=notice.id,
                text_code=notice.code,
                text_version=notice.version,
                acknowledged_at=datetime.now(UTC),
                created_by=principal.user_id,
            )
            session.add(existing)
            await session.flush()
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="portal_assistant.privacy_acknowledged",
                entity_type="portal_account",
                entity_id=account.id,
                actor_user_id=principal.user_id,
                payload={"text_version": notice.version},
            )
        return {
            "acknowledged": True,
            "text_version": existing.text_version,
            "acknowledged_at": existing.acknowledged_at,
        }


def _answer_out(log: PortalChatLog, hits: list[dict[str, Any]], state: AiState) -> dict[str, Any]:
    return {
        "id": log.id,
        "mode": log.mode,
        "status": log.status,
        "answer": log.answer,
        "sources": list(log.sources or []),
        "hits": hits,
        "ai_available": state.available,
        "ai_blocked_code": state.code,
        "ai_blocked_reason": state.message,
        "notice": NOTICE,
        "emergency_note": EMERGENCY_NOTE,
        "created_at": log.created_at,
    }


@router.post(
    "/questions",
    status_code=201,
    summary="Frage an den Assistenten (nur Unterlagen des eigenen Zugangs)",
    response_model=PortalAssistantAnswerOut,
)
async def ask(
    body: PortalAssistantQuestionIn, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """Answers from the released documents of the account. The scope check comes first (foreign
    unit or document: 404, no grant: nothing is read and no provider is called); the AI stage
    runs only when the privacy feature, the acknowledgement and the gateway gate allow it, else
    the full text hits inside the scope are returned with the reason. Every question is logged."""
    from mhvp.ai import portal_answer
    from mhvp.ai.masking import mask_personal_data
    from mhvp.core.auth.principal import sessions
    from mhvp.documents.blobs import BlobStore

    principal, account = ctx
    if principal.user_id is None:  # pragma: no cover - portal_user guarantees a user
        raise ProblemError(ErrorCodes.FORBIDDEN)
    masked_question = mask_personal_data(body.question).strip()
    async with tenant_tx(request, principal) as session:
        row = await _enabled(session)
        await _check_rate(session, account)
        scope = await assistant_scope.build_scope(
            session,
            account,
            local_today(),
            unit_id=body.unit_id,
            document_id=body.document_id,
        )
        state = await ai_state(session, row, account)
        hits = [_hit_out(d) for d in await _hits(session, scope, masked_question)]
        if scope.empty:
            code = _no_scope_code(scope)
            log = await _write_log(
                session,
                principal,
                account,
                body,
                masked_question,
                scope,
                mode="search",
                status="no_sources",
                answer=MESSAGES[code],
                reason_code=code,
            )
            return _answer_out(log, [], state)
        if not state.available:
            log = await _write_log(
                session,
                principal,
                account,
                body,
                masked_question,
                scope,
                mode="search",
                status="search_hits" if hits else "no_sources",
                answer=state.message,
                reason_code=state.code,
                technical_reason=state.technical,
            )
            return _answer_out(log, hits, state)
    # AI stage outside the transaction (provider call), then the log in a new one.
    result = await portal_answer.answer(
        sessions(request),
        principal.tenant_id,
        account_id=account.id,
        user_id=principal.user_id,
        question=body.question,
        scope_ids=set(scope.document_ids),
        focus_ids=(
            sorted(scope.document_ids)
            if scope.focus_unit_id is not None or scope.focus_document_id is not None
            else None
        ),
        attach_document_id=scope.focus_document_id,
        blobs=BlobStore(request.app.state.settings),
    )
    async with tenant_tx(request, principal) as session:
        failed = result.status == "failed"
        log = await _write_log(
            session,
            principal,
            account,
            body,
            masked_question,
            scope,
            mode="ai",
            status=result.status,
            answer=MESSAGES["ai_run_failed"] if failed else result.answer,
            reason_code=result.reason_code,
            technical_reason=result.technical_reason,
            sources=[
                {"document_id": str(s["document_id"]), "title": s["title"]} for s in result.sources
            ],
            run_id=result.run_id,
        )
        out = _answer_out(log, hits, AiState(True) if not failed else _failed_state(result))
        out["sources"] = [] if failed else result.sources
        return out


def _failed_state(result: Any) -> AiState:
    return AiState(False, result.reason_code, MESSAGES["ai_run_failed"], result.technical_reason)


async def _write_log(
    session: Any,
    principal: TenantPrincipal,
    account: PortalAccount,
    body: PortalAssistantQuestionIn,
    masked_question: str,
    scope: assistant_scope.AssistantScope,
    *,
    mode: str,
    status: str,
    answer: str | None,
    reason_code: str | None = None,
    technical_reason: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    run_id: uuid.UUID | None = None,
) -> PortalChatLog:
    log = PortalChatLog(
        tenant_id=principal.tenant_id,
        account_id=account.id,
        unit_id=body.unit_id,
        document_id=body.document_id,
        question=masked_question,
        answer=answer,
        mode=mode,
        status=status,
        reason_code=reason_code,
        technical_reason=technical_reason,
        sources=sources or [],
        scope_documents=len(scope.document_ids),
        run_id=run_id,
        created_by=principal.user_id,
    )
    session.add(log)
    await session.flush()
    await session.refresh(log)
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="portal_assistant.question",
        entity_type="portal_chat_log",
        entity_id=log.id,
        actor_user_id=principal.user_id,
        payload={"mode": mode, "status": status, "reason_code": reason_code},
    )
    return log


@router.get(
    "/questions",
    summary="Eigener Verlauf der Fragen an den Assistenten",
    dependencies=[Depends(strict_query)],
)
async def my_questions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    ctx: Portal = Depends(portal_user),
) -> list[dict[str, Any]]:
    """Own questions, newest first. Sources are shown only while the document is still readable
    for the account."""
    from mhvp.portal import access

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _enabled(session)
        rows = (
            await session.scalars(
                select(PortalChatLog)
                .where(PortalChatLog.account_id == account.id)
                .order_by(PortalChatLog.created_at.desc(), PortalChatLog.id.desc())
                .limit(limit)
            )
        ).all()
        readable = {
            str(i) for i in await access.visible_document_ids(session, account, local_today())
        }
        return [
            {
                "id": r.id,
                "question": r.question,
                "answer": r.answer,
                "mode": r.mode,
                "status": r.status,
                "sources": [s for s in (r.sources or []) if s.get("document_id") in readable],
                "created_at": r.created_at,
            }
            for r in rows
        ]


@admin.get(
    "/log",
    summary="Protokoll des Portal-Assistenten",
    dependencies=[Depends(strict_query)],
)
async def assistant_log(
    request: Request,
    account_id: uuid.UUID | None = Query(default=None),
    status: Literal["answered", "not_answerable", "failed", "search_hits", "no_sources"]
    | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(MANAGE),
) -> list[dict[str, Any]]:
    """Management view of the question log (masked questions, answers shown, checked sources,
    reason codes and technical reasons). With a property assignment only accounts whose contact
    has a contract inside the assignment are listed."""
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract

    async with tenant_tx(request, principal) as session:
        query = select(PortalChatLog, PortalAccount.contact_id).join(
            PortalAccount, PortalAccount.id == PortalChatLog.account_id
        )
        if account_id is not None:
            query = query.where(PortalChatLog.account_id == account_id)
        if status is not None:
            query = query.where(PortalChatLog.status == status)
        allowed = session_allowed_property_ids(session)
        if allowed is not None:
            visible = (
                select(PartyMember.contact_id)
                .join(Contract, Contract.party_id == PartyMember.party_id)
                .where(Contract.property_id.in_(allowed))
            )
            query = query.where(PortalAccount.contact_id.in_(visible))
        rows = (
            await session.execute(
                query.order_by(PortalChatLog.created_at.desc(), PortalChatLog.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [
            {
                "id": log.id,
                "account_id": log.account_id,
                "contact_id": contact_id,
                "unit_id": log.unit_id,
                "document_id": log.document_id,
                "question": log.question,
                "answer": log.answer,
                "mode": log.mode,
                "status": log.status,
                "reason_code": log.reason_code,
                "technical_reason": log.technical_reason,
                "sources": list(log.sources or []),
                "scope_documents": log.scope_documents,
                "run_id": log.run_id,
                "created_at": log.created_at,
            }
            for log, contact_id in rows
        ]
