"""Legal texts of the portal per tenant (AE29, M21-04, OPEN_QUESTIONS R10-03/R10-04).

Imprint, privacy notice and terms of use are kept in ``legal_text_block`` (release workflow with a
second person, mhvp.documents.text_blocks). The software ships no legal text: without an approved
version the portal shows the marker "Text nicht freigegeben" (or the external https link of the
branding, if the tenant maintains one there).

Link to the portal terms version of the consent policy (AC06, ``portal_terms_version``):

* ``manual`` (default): the label of the policy is maintained by hand, nothing changes when a
  terms text is approved. The status shows whether the label matches the approved text version.
* ``follow_text``: approving a new terms text sets the label to ``NB-<text version>``. Because
  portal accounts must then accept the new version, this is a tenant decision (switch, off by
  default, change needs ``contacts:approve``).

Independent of the mode, an authorised person can apply the label of the approved text explicitly
(``POST /tenant/legal-texts-config/apply-terms-version``). Public reads return only approved
text and only for the tenant of the portal host.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, NamedTuple

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, sessions, tenant_tx
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import TEXT_BLOCK_CODES, LegalTextBlock
from mhvp.platform.models import TenantSettings

PORTAL_LEGAL_CODES: tuple[str, ...] = ("impressum", "datenschutz", "nutzungsbedingungen")
TERMS_CODE = "nutzungsbedingungen"
SETTINGS_KEY = "legal_texts"
PLACEHOLDER = "Text nicht freigegeben"
TermsMode = Literal["manual", "follow_text"]
LegalCode = Literal["impressum", "datenschutz", "nutzungsbedingungen"]
# Branding link that stands in for a text while none is approved (https only, see Branding).
EXTERNAL_URL_FIELD = {"impressum": "imprint_url", "datenschutz": "privacy_url"}

router = APIRouter(prefix="/tenant", tags=["Mandant"])
CONFIG_READ = require_permission("tenant_settings:read")
POLICY_WRITE = require_permission("contacts:approve")


class ApprovedText(NamedTuple):
    """Values of an approved text block (no ORM instance, usable after the transaction)."""

    code: str
    version: int
    title: str
    body: str
    approved_at: datetime | None


def terms_label(version: int) -> str:
    """Label of the consent policy for a terms text version (``NB-3``)."""
    return f"NB-{version}"


def mode_from(sources: dict[str, Any] | None) -> TermsMode:
    raw = (sources or {}).get(SETTINGS_KEY)
    if isinstance(raw, dict) and raw.get("terms_version_mode") == "follow_text":
        return "follow_text"
    return "manual"


async def approved_blocks(session: AsyncSession) -> dict[str, ApprovedText]:
    """Approved version per portal legal code (RLS limits to the tenant of the session)."""
    rows = await session.scalars(
        select(LegalTextBlock).where(
            LegalTextBlock.status == "approved", LegalTextBlock.code.in_(PORTAL_LEGAL_CODES)
        )
    )
    return {
        r.code: ApprovedText(r.code, r.version, r.title, r.body, r.approved_at) for r in rows.all()
    }


async def released_codes(session: AsyncSession) -> list[str]:
    """Codes with an approved version, in the fixed order of ``PORTAL_LEGAL_CODES``."""
    approved = await approved_blocks(session)
    return [code for code in PORTAL_LEGAL_CODES if code in approved]


def _item(code: str, block: ApprovedText | None, branding: dict[str, Any]) -> dict[str, Any]:
    field = EXTERNAL_URL_FIELD.get(code)
    external = branding.get(field) if field else None
    return {
        "code": code,
        "label": TEXT_BLOCK_CODES[code],
        "released": block is not None,
        "version": block.version if block else None,
        "approved_at": block.approved_at if block else None,
        "display": None if block else PLACEHOLDER,
        "external_url": external if isinstance(external, str) and external else None,
    }


def _terms_info(blocks: dict[str, ApprovedText], policy: dict[str, Any]) -> dict[str, Any]:
    text = blocks.get(TERMS_CODE)
    label = policy.get("portal_terms_version")
    return {
        "terms_version": label,
        "terms_text_version": text.version if text else None,
        "terms_in_sync": bool(text and label == terms_label(text.version)),
    }


async def _settings_row(session: AsyncSession) -> TenantSettings:
    row: TenantSettings | None = await session.scalar(select(TenantSettings).with_for_update())
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _set_policy_label(
    session: AsyncSession, principal: TenantPrincipal, label: str, origin: str
) -> None:
    """Sets ``consent_policy.portal_terms_version``; the other switches stay as they are."""
    from mhvp.contacts import consent_rules

    row = await _settings_row(session)
    sources = row.sources or {}
    before = sources.get(consent_rules.POLICY_KEY)
    value = {**consent_rules.policy_from(sources).as_dict(), "portal_terms_version": label}
    row.sources = {**sources, consent_rules.POLICY_KEY: value}
    row.version += 1
    row.updated_by = principal.user_id
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="consent_policy.updated",
        entity_type="tenant_settings",
        entity_id=row.id,
        actor_user_id=principal.user_id,
        payload={"before": before, "after": value, "origin": origin},
    )


async def follow_terms_version(
    session: AsyncSession, block: LegalTextBlock, principal: TenantPrincipal
) -> None:
    """Hook of the release of a text block: in mode ``follow_text`` an approved terms text
    sets the consent policy label. In mode ``manual`` (default) nothing happens."""
    if block.code != TERMS_CODE:
        return
    row = await session.scalar(select(TenantSettings))
    if row is None or mode_from(row.sources) != "follow_text":
        return
    await _set_policy_label(session, principal, terms_label(block.version), "legal_texts.follow")


async def _public_state(
    request: Request,
) -> tuple[dict[str, ApprovedText], dict[str, Any], dict[str, Any]]:
    """Approved texts, branding and consent policy of the tenant of the portal host (3.3)."""
    from mhvp.contacts import consent_rules
    from mhvp.platform.routers import _public_branding_tenant

    tenant_id: uuid.UUID | None = await _public_branding_tenant(request)
    if tenant_id is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    async with tenant_transaction(sessions(request), tenant_id) as session:
        row = await session.scalar(select(TenantSettings))
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        blocks = await approved_blocks(session)
        branding = dict(row.branding or {})
        policy = consent_rules.policy_from(row.sources).as_dict()
    return blocks, branding, policy


@router.get(
    "/legal-texts",
    summary="Rechtstexte des Portals (öffentlich, nur freigegebene Fassungen)",
    dependencies=[Depends(strict_query)],
)
async def public_legal_texts(request: Request) -> dict[str, Any]:
    """Which portal legal texts are released for the tenant of the portal host. The body is not
    part of the list; ``display`` carries the marker while a text is not approved."""
    blocks, branding, policy = await _public_state(request)
    return {
        "items": [_item(code, blocks.get(code), branding) for code in PORTAL_LEGAL_CODES],
        **_terms_info(blocks, policy),
    }


@router.get(
    "/legal-texts/{code}",
    summary="Rechtstext des Portals (öffentlich, nur die freigegebene Fassung)",
    dependencies=[Depends(strict_query)],
)
async def public_legal_text(code: LegalCode, request: Request) -> dict[str, Any]:
    blocks, branding, policy = await _public_state(request)
    block = blocks.get(code)
    out = _item(code, block, branding)
    out["title"] = block.title if block else None
    out["body"] = block.body.strip() if block else None
    if code == TERMS_CODE:
        out.update(_terms_info(blocks, policy))
    return out


class LegalTextsConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terms_version_mode: TermsMode


class LegalTextsApplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Applying the label obliges portal accounts to accept the new version: explicit consent.
    confirm: Literal[True]


async def _config_out(session: AsyncSession) -> dict[str, Any]:
    from mhvp.contacts import consent_rules

    row = await session.scalar(select(TenantSettings))
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    blocks = await approved_blocks(session)
    branding = dict(row.branding or {})
    policy = consent_rules.policy_from(row.sources).as_dict()
    text = blocks.get(TERMS_CODE)
    return {
        "terms_version_mode": mode_from(row.sources),
        "policy_terms_version": policy.get("portal_terms_version"),
        "approved_text_version": text.version if text else None,
        "suggested_label": terms_label(text.version) if text else None,
        "in_sync": _terms_info(blocks, policy)["terms_in_sync"],
        "items": [_item(code, blocks.get(code), branding) for code in PORTAL_LEGAL_CODES],
    }


@router.get(
    "/legal-texts-config",
    summary="Rechtstexte des Portals: Freigabestand und Abgleich mit der Terms-Fassung",
    dependencies=[Depends(strict_query)],
)
async def legal_texts_config(
    request: Request, principal: TenantPrincipal = Depends(CONFIG_READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return await _config_out(session)


@router.put(
    "/legal-texts-config",
    summary="Schalter: Fassung der Nutzungsbedingungen folgt dem freigegebenen Text",
)
async def put_legal_texts_config(
    body: LegalTextsConfigIn,
    request: Request,
    principal: TenantPrincipal = Depends(POLICY_WRITE),
) -> dict[str, Any]:
    """``follow_text`` lets the release of a terms text set the consent policy label, which
    obliges portal accounts to accept the new version: therefore ``contacts:approve``."""
    async with tenant_tx(request, principal) as session:
        row = await _settings_row(session)
        before = mode_from(row.sources)
        row.sources = {
            **(row.sources or {}),
            SETTINGS_KEY: {"terms_version_mode": body.terms_version_mode},
        }
        row.version += 1
        row.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="legal_texts.config_updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"before": before, "after": body.terms_version_mode},
        )
        await session.flush()
        return await _config_out(session)


@router.post(
    "/legal-texts-config/apply-terms-version",
    summary="Terms-Fassung der Einwilligungsrichtlinie auf den freigegebenen Text setzen",
)
async def apply_terms_version(
    body: LegalTextsApplyIn,
    request: Request,
    principal: TenantPrincipal = Depends(POLICY_WRITE),
) -> dict[str, Any]:
    """Explicit action: sets ``consent_policy.portal_terms_version`` to ``NB-<version>`` of the
    approved terms text. Without an approved text nothing is set (409)."""
    async with tenant_tx(request, principal) as session:
        text = (await approved_blocks(session)).get(TERMS_CODE)
        if text is None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Es gibt keinen freigegebenen Text der Nutzungsbedingungen.",
            )
        await _set_policy_label(session, principal, terms_label(text.version), "legal_texts.apply")
        await session.flush()
        return await _config_out(session)
