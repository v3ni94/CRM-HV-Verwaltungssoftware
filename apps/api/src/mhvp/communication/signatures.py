"""E-Mail-Signatur je angemeldetem Nutzer (operator 27.09.2026, migration 0215).

Die Signatur wird serverseitig aus drei Quellen gerendert: dem Nutzer (``app_user``), der
Mitgliedschaft im Mandanten (``membership.position``, ``membership.phone``,
``membership.mobile_phone``) und den Mandanteneinstellungen (Firmendaten, Branding,
``signature_template``). Ohne Vorlage gilt der Standard aus den Firmendaten des Seeds:
Kapitalgesellschaft (HVM) mit Kennlinie, Registerzeile und Position; Einzelunternehmen
(Timo Müller) als Wortmarke mit kurzer Akzentlinie, ohne Funktionsbezeichnung und ohne
Registerangaben. Steuernummern und Bankverbindungen sind nie Teil der Signatur.

Einbindung in den Versandpfad (additiv, ein Aufruf): ``with_signature(body, signature)``
für den Klartext und ``with_signature_html(html, signature)`` für HTML. Beide sind
idempotent über eine Signaturmarke (``TEXT_MARKER`` als eigene Zeile, ``HTML_MARKER`` als
Kommentar): enthält der Entwurf die Marke bereits, wird nichts angehängt.

Endpunkte (``router``): ``GET /mail/signature/preview`` (eigene Signatur, mit ``members:read``
auch ``?membership_id=`` eines anderen Mitglieds), ``GET`` und ``PUT
/mail/signature/profile`` (eigene Position und Durchwahl; die Position ist Freitext, der
Katalog ``POSITION_CATALOGUE`` plus die Mandantenliste liefert Vorschläge).
"""

from __future__ import annotations

import html as html_lib
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import (
    Principal,
    TenantPrincipal,
    get_principal,
    tenant_tx,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import Membership, TenantSettings, User
from mhvp.platform.schemas import MemberPosition

# Standardpositionen (Betreiberwunsch 27.09.2026); freie Eingabe bleibt erlaubt.
POSITION_CATALOGUE: tuple[str, ...] = (
    "Geschäftsführer",
    "Prokurist",
    "Assistenz",
    "Objektbetreuung",
    "Immobilienkaufmann",
    "Buchhaltung",
    "Leitung Buchhaltung",
    "Asset Management",
)

# Signaturmarke: RFC 3676 Trennzeile im Klartext, Kommentar im HTML.
TEXT_MARKER = "-- "
HTML_MARKER = "<!-- mhvp-signature -->"
LOGO_MAX_WIDTH = 180

_DEFAULT_FONT = "system-ui, 'Helvetica Neue', Arial, sans-serif"
_DEFAULT_TEXT = "#1A1A1A"
_DEFAULT_MUTED = "#87888A"
_DEFAULT_ACCENT = "#E6A83C"

# Standardvorlage Klartext: Zeilen, deren Platzhalter alle leer bleiben, entfallen.
DEFAULT_TEXT_TEMPLATE = (
    "{name}\n{position}\n{company}\n{street}\n{postal_code} {city}\n"
    "Telefon {phone}\nMobil {mobile}\nE-Mail {email}\n{register}\n{website}"
)
PLACEHOLDERS: tuple[str, ...] = (
    "name",
    "position",
    "phone",
    "mobile",
    "email",
    "company",
    "street",
    "postal_code",
    "city",
    "register",
    "website",
)


@dataclass(frozen=True)
class Signature:
    text: str
    html: str


def position_catalogue(tenant_extra: list[str] | None = None) -> list[str]:
    """Katalog plus manuell angelegte Positionen des Mandanten, ohne Doppelungen."""
    seen: dict[str, None] = dict.fromkeys(POSITION_CATALOGUE)
    for raw in tenant_extra or []:
        value = " ".join(str(raw).split())
        if value and value not in seen:
            seen[value] = None
    return list(seen)


async def remember_position(
    session: AsyncSession, tenant_id: uuid.UUID, position: str | None
) -> None:
    """Merkt eine manuell eingegebene Position in ``tenant_settings.position_catalogue_extra``,
    damit sie im Dropdown wiederkehrt (Betreiberwunsch 27.09.2026)."""
    if not position or position in POSITION_CATALOGUE:
        return
    row = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id).with_for_update()
    )
    if row is None:
        return
    current = [str(p) for p in (row.position_catalogue_extra or [])]
    if position not in current:
        row.position_catalogue_extra = [*current, position]


# --- rendering -----------------------------------------------------------------------------


def is_sole_proprietorship(company: dict[str, Any]) -> bool:
    return "einzelunternehm" in str(company.get("legal_form") or "").lower()


def _register_line(company: dict[str, Any]) -> str:
    court, number = company.get("register_court"), company.get("register_number")
    if not court or not number:
        return ""
    line = f"{court} {number}"
    management = [str(m) for m in company.get("management") or [] if m]
    if management:
        title = str(company.get("management_title") or "").strip()
        line += f", {title + ' ' if title else ''}{', '.join(management)}"
    return line


def signature_values(
    *,
    display_name: str,
    email: str | None,
    position: str | None,
    phone: str | None,
    mobile: str | None,
    company: dict[str, Any],
) -> dict[str, str]:
    """Platzhalterwerte; beim Einzelunternehmen entfallen Funktionsbezeichnung und Register."""
    sole = is_sole_proprietorship(company)
    values = {
        "name": display_name.strip(),
        "position": "" if sole else (position or "").strip(),
        "phone": (phone or "").strip(),
        "mobile": (mobile or "").strip(),
        "email": (email or "").strip(),
        "company": "" if sole else str(company.get("name") or "").strip(),
        "street": str(company.get("street") or "").strip(),
        "postal_code": str(company.get("postal_code") or "").strip(),
        "city": str(company.get("city") or "").strip(),
        "register": "" if sole else _register_line(company),
        "website": str(company.get("website") or "").strip(),
    }
    if sole and values["name"] and values["name"] != str(company.get("name") or "").strip():
        # Wortmarke ist der Unternehmensname; eine abweichende Person steht darunter.
        values["company"] = str(company.get("name") or "").strip()
    return values


class _Safe(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def fill_template(template: str, values: dict[str, str], *, escape: bool = False) -> str:
    """Ersetzt Platzhalter; Zeilen, die nur aus leer aufgelösten Platzhaltern und Beiwerk
    bestehen, entfallen (so bleibt ``Telefon {phone}`` ohne Nummer nicht stehen)."""
    safe = _Safe({k: (html_lib.escape(v) if escape else v) for k, v in values.items()})
    out: list[str] = []
    for line in template.split("\n"):
        keys = [k for k in PLACEHOLDERS if "{" + k + "}" in line]
        if keys and all(not safe[k] for k in keys):
            continue
        try:
            out.append(line.format_map(safe))
        except (ValueError, IndexError, KeyError):
            out.append(line)
    return "\n".join(out).strip()


def _band_css(branding: dict[str, Any]) -> str:
    segments = branding.get("letter_band") or []
    stops: list[str] = []
    for seg in segments:
        try:
            color = str(seg["color"])
            start, end = float(seg["from"]) * 100, float(seg["to"]) * 100
        except (KeyError, TypeError, ValueError):
            continue
        stops.append(f"{color} {start:g}% {end:g}%")
    if not stops:
        return f"background-color:{branding.get('accent_color') or _DEFAULT_ACCENT};"
    first = str(segments[0].get("color") or _DEFAULT_MUTED)
    return f"background-color:{first};background:linear-gradient(90deg,{','.join(stops)});"


def default_html(
    values: dict[str, str], company: dict[str, Any], branding: dict[str, Any], logo_url: str | None
) -> str:
    """Tabellenlayout nach dem CI des Mandanten (HVM-Kennlinie 3 px; Einzelunternehmen als
    Wortmarke mit kurzer Akzentlinie)."""
    e = {k: html_lib.escape(v) for k, v in values.items()}
    font = str(branding.get("font_family") or _DEFAULT_FONT)
    text = str(branding.get("text_color") or _DEFAULT_TEXT)
    muted = str(branding.get("primary_color") or _DEFAULT_MUTED)
    accent = str(branding.get("accent_color") or _DEFAULT_ACCENT)
    base = f"font-family:{font};font-size:13px;line-height:1.45;color:{text};"
    small = f"font-family:{font};font-size:12px;line-height:1.45;color:{muted};"
    sole = is_sole_proprietorship(company)
    rows: list[str] = []
    if logo_url:
        rows.append(
            f'<tr><td style="padding:0 0 8px 0;"><img src="{html_lib.escape(logo_url)}" '
            f'alt="{e["company"] or e["name"]}" width="{LOGO_MAX_WIDTH}" '
            f'style="display:block;max-width:{LOGO_MAX_WIDTH}px;height:auto;border:0;"></td></tr>'
        )
    if sole:
        rows.append(
            f'<tr><td style="{base}font-size:15px;font-weight:600;letter-spacing:0.02em;">'
            f"{e['company'] or e['name']}</td></tr>"
        )
        rows.append(
            f'<tr><td style="padding:4px 0 8px 0;"><div style="width:40px;height:2px;'
            f'background-color:{accent};font-size:0;line-height:0;">&nbsp;</div></td></tr>'
        )
        if e["company"] and e["name"] != e["company"]:
            rows.append(f'<tr><td style="{base}">{e["name"]}</td></tr>')
    else:
        rows.append(
            f'<tr><td style="padding:0 0 8px 0;"><div style="height:3px;font-size:0;'
            f'line-height:0;{_band_css(branding)}">&nbsp;</div></td></tr>'
        )
        rows.append(f'<tr><td style="{base}font-weight:600;">{e["name"]}</td></tr>')
        if e["position"]:
            rows.append(f'<tr><td style="{small}">{e["position"]}</td></tr>')
        if e["company"]:
            rows.append(
                f'<tr><td style="{base}padding-top:6px;font-weight:600;">{e["company"]}</td></tr>'
            )
    address = ", ".join(p for p in (e["street"], f"{e['postal_code']} {e['city']}".strip()) if p)
    if address:
        rows.append(f'<tr><td style="{base}">{address}</td></tr>')
    contact_bits: list[str] = []
    if e["phone"]:
        contact_bits.append(f"Telefon {e['phone']}")
    if e["mobile"]:
        contact_bits.append(f"Mobil {e['mobile']}")
    if e["email"]:
        contact_bits.append(
            f'E-Mail <a href="mailto:{e["email"]}" style="color:{text};">{e["email"]}</a>'
        )
    if contact_bits:
        rows.append(f'<tr><td style="{base}">{" &middot; ".join(contact_bits)}</td></tr>')
    if e["register"]:
        rows.append(f'<tr><td style="{small}padding-top:6px;">{e["register"]}</td></tr>')
    if e["website"]:
        href = (
            values["website"]
            if values["website"].startswith("http")
            else f"https://{values['website']}"
        )
        rows.append(
            f'<tr><td style="{small}"><a href="{html_lib.escape(href)}" style="color:{accent};">'
            f"{e['website']}</a></td></tr>"
        )
    return (
        f'{HTML_MARKER}<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;max-width:480px;">{"".join(rows)}</table>'
    )


def render_signature(
    *,
    display_name: str,
    email: str | None,
    position: str | None,
    phone: str | None,
    mobile: str | None,
    company: dict[str, Any],
    branding: dict[str, Any],
    template: dict[str, Any] | None = None,
) -> Signature:
    """Text und HTML der Signatur; ``template`` (``TenantSettings.signature_template``) mit
    ``text``/``html`` überschreibt den Standard, ``logo_url`` bindet ein Logo ein."""
    template = template or {}
    values = signature_values(
        display_name=display_name,
        email=email,
        position=position,
        phone=phone,
        mobile=mobile,
        company=company,
    )
    text_template = str(template.get("text") or "") or DEFAULT_TEXT_TEMPLATE
    text = fill_template(text_template, values)
    logo_url = str(template.get("logo_url") or "") or None
    if template.get("html"):
        body = fill_template(str(template["html"]), values, escape=True)
        html = body if HTML_MARKER in body else HTML_MARKER + body
    else:
        html = default_html(values, company, branding, logo_url)
    return Signature(text=f"{TEXT_MARKER}\n{text}", html=html)


# --- application to outgoing mail ---------------------------------------------------------


def has_signature(body: str | None) -> bool:
    return any(line.rstrip("\r") == TEXT_MARKER for line in (body or "").split("\n"))


def with_signature(body: str | None, signature: Signature | None) -> str:
    """Klartext mit angehängter Signatur; unverändert, wenn die Marke schon enthalten ist."""
    text = body or ""
    if signature is None or has_signature(text):
        return text
    return f"{text.rstrip()}\n\n{signature.text}\n"


def with_signature_html(body_html: str | None, signature: Signature | None) -> str | None:
    """HTML mit angehängter Signatur; ``None`` bleibt ``None`` (kein HTML-Teil erzwungen)."""
    if body_html is None or signature is None or HTML_MARKER in body_html:
        return body_html
    block = f'<div style="margin-top:16px;">{signature.html}</div>'
    if "</body>" in body_html:
        return body_html.replace("</body>", block + "</body>", 1)
    return body_html + block


# --- data access -----------------------------------------------------------------------------


async def signature_for_user(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None
) -> Signature | None:
    """Signatur des Nutzers im Mandanten (``None`` für API-Schlüssel oder ohne Mitgliedschaft).
    ``session`` ist eine Mandantensitzung; die Plattformtabellen sind darin lesbar."""
    if user_id is None:
        return None
    row = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
        )
    ).first()
    if row is None:
        return None
    membership, user = row
    settings = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    return render_signature(
        display_name=user.display_name,
        email=user.email,
        position=membership.position,
        phone=membership.phone,
        mobile=membership.mobile_phone,
        company=dict(settings.company or {}) if settings else {},
        branding=dict(settings.branding or {}) if settings else {},
        template=dict(settings.signature_template or {}) if settings else {},
    )


# --- API -----------------------------------------------------------------------------------

router = APIRouter(prefix="/mail/signature", tags=["Postfach"])


class SignaturePreviewOut(BaseModel):
    membership_id: uuid.UUID
    text: str
    html: str


class SignatureProfileOut(BaseModel):
    """Eigene Signaturdaten und der Positionskatalog für das Dropdown mit Freitext."""

    membership_id: uuid.UUID
    position: str | None
    phone: str | None
    mobile_phone: str | None
    catalogue: list[str] = Field(default_factory=list)


async def _tenant_user(request: Request) -> TenantPrincipal:
    """Jedes angemeldete Mitglied (kein API-Schlüssel) darf die eigene Signatur sehen und
    die eigene Position pflegen."""
    principal: Principal = await get_principal(request)
    if principal.tenant_id is None or principal.user_id is None or principal.api_key_id:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Tenant user required.")
    return TenantPrincipal(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        permissions=principal.permissions,
        roles=principal.roles,
        is_platform_admin=principal.is_platform_admin,
        platform_access_reason=principal.platform_access_reason,
        is_superadmin=principal.is_superadmin,
        legal_entity_ids=principal.legal_entity_ids,
    )


async def _own_membership(session: AsyncSession, principal: TenantPrincipal) -> Membership:
    membership = await session.scalar(
        select(Membership).where(
            Membership.tenant_id == principal.tenant_id, Membership.user_id == principal.user_id
        )
    )
    if membership is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return membership


async def _profile_out(session: AsyncSession, membership: Membership) -> SignatureProfileOut:
    extra = await session.scalar(
        select(TenantSettings.position_catalogue_extra).where(
            TenantSettings.tenant_id == membership.tenant_id
        )
    )
    return SignatureProfileOut(
        membership_id=membership.id,
        position=membership.position,
        phone=membership.phone,
        mobile_phone=membership.mobile_phone,
        catalogue=position_catalogue([str(p) for p in (extra or [])]),
    )


@router.get("/preview", summary="Vorschau der E-Mail-Signatur (Text und HTML)")
async def preview_signature(
    request: Request,
    membership_id: uuid.UUID | None = Query(default=None),
    principal: TenantPrincipal = Depends(_tenant_user),
) -> SignaturePreviewOut:
    async with tenant_tx(request, principal) as session:
        if membership_id is None:
            membership = await _own_membership(session, principal)
        else:
            if not principal.has("members:read"):
                raise ProblemError(
                    ErrorCodes.FORBIDDEN, developer_message="Missing permission members:read."
                )
            membership = await session.get(Membership, membership_id)  # type: ignore[assignment]
            if membership is None or membership.tenant_id != principal.tenant_id:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        signature = await signature_for_user(session, principal.tenant_id, membership.user_id)
    if signature is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return SignaturePreviewOut(
        membership_id=membership.id, text=signature.text, html=signature.html
    )


@router.get("/profile", summary="Eigene Position und Durchwahl für die Signatur")
async def get_signature_profile(
    request: Request, principal: TenantPrincipal = Depends(_tenant_user)
) -> SignatureProfileOut:
    async with tenant_tx(request, principal) as session:
        membership = await _own_membership(session, principal)
        return await _profile_out(session, membership)


@router.put("/profile", summary="Eigene Position und Durchwahl setzen")
async def put_signature_profile(
    body: MemberPosition, request: Request, principal: TenantPrincipal = Depends(_tenant_user)
) -> SignatureProfileOut:
    async with tenant_tx(request, principal) as session:
        membership = await _own_membership(session, principal)
        before = {"position": membership.position, "phone_set": membership.phone is not None}
        after = {"position": body.position, "phone_set": body.phone is not None}
        if before != after:
            membership.position = body.position
            membership.phone = body.phone
            membership.updated_by = principal.user_id
            await remember_position(session, principal.tenant_id, body.position)
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="membership.position_changed",
                entity_type="membership",
                entity_id=membership.id,
                actor_user_id=principal.user_id,
                changes={
                    k: {"old": before[k], "new": after[k]} for k in before if before[k] != after[k]
                },
            )
            await session.flush()
        return await _profile_out(session, membership)
