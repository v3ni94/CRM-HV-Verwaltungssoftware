"""E-Mail-Signatur je angemeldetem Nutzer (operator 27.09.2026, migration 0215).

Die Signatur wird serverseitig aus drei Quellen gerendert: dem Nutzer (``app_user``, nur
der Anzeigename), der Mitgliedschaft im Mandanten (``membership.position``,
``membership.phone``) und den Mandanteneinstellungen (Firmendaten, Branding,
``signature_template``). Ohne Vorlage gilt der Standard aus den Firmendaten des Seeds:
Kapitalgesellschaft (HVM) mit Kennlinie, Registerzeile und Position; Einzelunternehmen
(Timo Müller) als Wortmarke mit kurzer Akzentlinie, ohne Funktionsbezeichnung und ohne
Registerangaben. Steuernummern und Bankverbindungen sind nie Teil der Signatur.

Never part of the signature (review 1.36.0): ``membership.mobile_phone`` (internal on-call
number for SMS escalations, M35) and the login address ``app_user.email`` (shared by all
tenants of the user). The e-mail line carries the address of the mailbox the reply is sent
from; without one it is omitted.

The stored body is the single source of truth (review 1.36.0): ``sign_body`` inserts the
signature into ``Message.body`` when a draft is created and, if missing, when it is
submitted, so the approver sees exactly the text that is sent. The send path sends
``Message.body`` verbatim and never appends anything. ``with_signature`` is idempotent on
the rendered signature text itself (whitespace normalised), not on the ``-- `` delimiter.
At submit (``respect_delimiter``) a ``-- `` delimiter line also counts as present, so an
edited signature block or a changed profile, template or mailbox never gets a second
signature. When it appends, the template closing lines ``[Name]`` and ``[Firma]`` are
removed, since the signature supplies name and company.

Outgoing mail is text/plain in 1.36.0. The HTML signature (``with_signature_html``, preview
endpoint) is preview only and not sent.

Endpunkte (``router``): ``GET /mail/signature/preview`` (eigene Signatur, mit ``members:read``
auch ``?membership_id=`` eines anderen Mitglieds), ``GET`` und ``PUT
/mail/signature/profile`` (eigene Position und Durchwahl; die Position ist Freitext, der
Katalog ``POSITION_CATALOGUE`` plus die Mandantenliste liefert Vorschläge).
"""

from __future__ import annotations

import html as html_lib
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Mailbox, MailboxUser
from mhvp.core.auth.principal import (
    Principal,
    TenantPrincipal,
    get_principal,
    tenant_tx,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, FieldError, ProblemError
from mhvp.platform.models import Membership, TenantSettings, User
from mhvp.platform.schemas import MemberPosition

log = logging.getLogger(__name__)

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

# RFC 3676 delimiter above the text signature, comment in the HTML. The rendered text is the
# primary idempotency key; at submit an existing delimiter line also counts as "signature
# present", so an edited signature block is not appended twice (review 1.36.0, see
# ``with_signature``).
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


# Placeholder ``{name}``; ``{{`` and ``}}`` are literal braces. No ``str.format``: attribute,
# index and width forms (``{company.name}``, ``{name[0]}``, ``{name:>999999999}``) must
# neither raise nor allocate (review 1.36.0).
_TOKEN = re.compile(r"\{\{|\}\}|\{([^{}\n]*)\}")


def unknown_placeholders(template: str | None) -> list[str]:
    """Placeholders of ``template`` that are not in ``PLACEHOLDERS`` (in text order, without
    duplicates); used to validate a template when it is saved."""
    names: list[str] = []
    for match in _TOKEN.finditer(template or ""):
        name = match.group(1)
        if name is not None and name not in PLACEHOLDERS and name not in names:
            names.append(name)
    return names


def assert_known_placeholders(template: dict[str, Any]) -> None:
    """422 with the unknown placeholder names when a template is saved (review 1.36.0)."""
    unknown: dict[str, list[str]] = {}
    for key in ("text", "html"):
        names = unknown_placeholders(str(template.get(key) or ""))
        if names:
            unknown[key] = names
    if not unknown:
        return
    listed = ", ".join(
        dict.fromkeys("{" + name + "}" for names in unknown.values() for name in names)
    )
    raise ProblemError(
        ErrorCodes.VALIDATION,
        detail=f"Unbekannte Platzhalter in der Signaturvorlage: {listed}. Zulässig sind "
        + ", ".join("{" + p + "}" for p in PLACEHOLDERS)
        + "; geschweifte Klammern im Text als {{ und }} schreiben.",
        errors=[
            FieldError(
                location=["body", "signature_template", key],
                field=key,
                code="unknown_placeholder",
                message="Unbekannte Platzhalter: " + ", ".join(names),
            )
            for key, names in unknown.items()
        ],
        extensions={"unknown_placeholders": sorted({n for v in unknown.values() for n in v})},
    )


def fill_template(template: str, values: dict[str, str], *, escape: bool = False) -> str:
    """Ersetzt Platzhalter; Zeilen, die nur aus leer aufgelösten Platzhaltern und Beiwerk
    bestehen, entfallen (so bleibt ``Telefon {phone}`` ohne Nummer nicht stehen).
    Unknown or malformed placeholders render empty and never raise. They are logged once per
    template with their names only, also when their line is dropped (no values, no personal
    data)."""
    safe = {k: (html_lib.escape(v) if escape else v) for k, v in values.items()}
    unknown = unknown_placeholders(template)
    if unknown:
        log.warning(
            "Signature template placeholders %s are unknown and rendered empty.",
            ", ".join(repr(name[:64]) for name in unknown),
        )

    def _replace(match: re.Match[str]) -> str:
        matched = match.group(0)
        if matched in ("{{", "}}"):
            return matched[0]
        name = match.group(1)
        return safe.get(name, "") if name in PLACEHOLDERS else ""

    out: list[str] = []
    for line in template.split("\n"):
        keys = [m.group(1) for m in _TOKEN.finditer(line) if m.group(1) is not None]
        if keys and all(not safe.get(k, "") for k in keys):
            continue
        out.append(_TOKEN.sub(_replace, line))
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


# Closing lines of the reply templates (mail.draft_reply, ticket proposals, call assistant) that
# ask for name and company by hand; with a signature they are redundant (review 1.36.0).
_CLOSING_PLACEHOLDERS = frozenset({"[Name]", "[Firma]"})


def _normalised(text: str) -> str:
    return " ".join(text.split())


def _signature_block(signature: Signature) -> str:
    """Rendered signature text without the ``-- `` delimiter line."""
    lines = signature.text.split("\n")
    if lines and lines[0] == TEXT_MARKER:
        lines = lines[1:]
    return "\n".join(lines)


def has_signature(body: str | None, signature: Signature) -> bool:
    """Whether the rendered signature text (whitespace normalised) is already in ``body``.
    The ``-- `` delimiter alone does not count: deleting it does not double the signature,
    and a delimiter in pasted text does not suppress it (review 1.36.0)."""
    block = _normalised(_signature_block(signature))
    return bool(block) and block in _normalised(body or "")


def has_delimiter(body: str | None) -> bool:
    """Whether ``body`` has a line that is exactly the standard signature delimiter ``-- ``
    (RFC 3676; CRLF line ends allowed, quoted ``> -- `` does not count)."""
    return any(line == TEXT_MARKER for line in (body or "").splitlines())


def with_signature(
    body: str | None, signature: Signature | None, *, respect_delimiter: bool = False
) -> str:
    """Plain text with the signature appended; unchanged when the signature text is already
    present. Appending removes the closing placeholder lines ``[Name]`` and ``[Firma]``.

    ``respect_delimiter`` (submit): a ``-- `` delimiter line also counts as present, so an
    edited signature block, or a profile, template or mailbox changed since the draft was
    signed, does not get a second signature appended (review 1.36.0)."""
    text = body or ""
    if signature is None or not _normalised(_signature_block(signature)):
        return text
    if has_signature(text, signature) or (respect_delimiter and has_delimiter(text)):
        return text
    kept = "\n".join(line for line in text.split("\n") if line.strip() not in _CLOSING_PLACEHOLDERS)
    return f"{kept.rstrip()}\n\n{signature.text}\n"


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
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    *,
    email: str | None = None,
) -> Signature | None:
    """Signatur des Nutzers im Mandanten (``None`` für API-Schlüssel oder ohne Mitgliedschaft).
    ``session`` ist eine Mandantensitzung; die Plattformtabellen sind darin lesbar.
    ``email`` is the address of the sending mailbox, never the login address; without it
    the e-mail line is omitted."""
    if user_id is None:
        return None
    # Hotfix 27.09.2026: only the display name of ``app_user``, never the whole entity. Loading
    # ``User`` decrypts ``totp_secret``, which is sealed in the platform scope; in this tenant
    # session the scope is the tenant, so every user with a second factor got a CryptoError
    # (500 "Interner Fehler") on Antworten, Vorschlag übernehmen, ticket reply and preview.
    row = (
        await session.execute(
            select(Membership, User.display_name)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
        )
    ).first()
    if row is None:
        return None
    membership, display_name = row
    settings = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    return render_signature(
        display_name=display_name or "",
        # Never ``user.email``: the login address is shared by all tenants of the user.
        email=email,
        position=membership.position,
        phone=membership.phone,
        # Never ``membership.mobile_phone``: internal on-call number for SMS escalations
        # (M35), not collected for publication.
        mobile=None,
        company=dict(settings.company or {}) if settings else {},
        branding=dict(settings.branding or {}) if settings else {},
        template=dict(settings.signature_template or {}) if settings else {},
    )


async def mailbox_address(session: AsyncSession, mailbox_id: uuid.UUID | None) -> str | None:
    """Address of the sending mailbox; a removed mailbox has none."""
    if mailbox_id is None:
        return None
    box = await session.get(Mailbox, mailbox_id)
    if box is None or box.deleted_at is not None:
        return None
    return box.address


async def personal_mailbox_address(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None
) -> str | None:
    """Address of the single personal mailbox granted to the user in this tenant (preview
    without a sending mailbox); ``None`` when there is none or more than one."""
    if user_id is None:
        return None
    rows = (
        await session.scalars(
            select(Mailbox.address)
            .join(MailboxUser, MailboxUser.mailbox_id == Mailbox.id)
            .where(
                Mailbox.tenant_id == tenant_id,
                MailboxUser.user_id == user_id,
                Mailbox.is_collective.is_(False),
                Mailbox.deleted_at.is_(None),
            )
            .limit(2)
        )
    ).all()
    return rows[0] if len(rows) == 1 else None


async def sign_body(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    body: str | None,
    *,
    mailbox_id: uuid.UUID | None,
    respect_delimiter: bool = False,
) -> str:
    """Draft body with the signature of ``user_id`` and the sending mailbox address;
    unchanged when the signature is already present or there is none (API key). At submit
    ``respect_delimiter=True``: a ``-- `` delimiter line also counts as present."""
    signature = await signature_for_user(
        session, tenant_id, user_id, email=await mailbox_address(session, mailbox_id)
    )
    return with_signature(body, signature, respect_delimiter=respect_delimiter)


# --- API -----------------------------------------------------------------------------------

router = APIRouter(prefix="/mail/signature", tags=["Postfach"])


class SignaturePreviewOut(BaseModel):
    """Outgoing mail is text/plain in 1.36.0: ``text`` is what is inserted and sent, ``html``
    is a preview of the HTML signature only and is not sent."""

    membership_id: uuid.UUID
    text: str = Field(
        description="Klartextsignatur, so wie sie in ausgehende Mails eingefügt wird."
    )
    html: str = Field(
        description="Nur Vorschau: die HTML-Signatur wird derzeit nicht versendet "
        "(ausgehende Mails sind Klartext)."
    )


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


@router.get(
    "/preview",
    summary="Vorschau der E-Mail-Signatur (Klartext wird versendet, HTML nur Vorschau)",
)
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
        signature = await signature_for_user(
            session,
            principal.tenant_id,
            membership.user_id,
            email=await personal_mailbox_address(session, principal.tenant_id, membership.user_id),
        )
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
        # The event only records whether an extension is set (no number in the log); the
        # write compares the real values, otherwise a changed extension would be dropped.
        before = {"position": membership.position, "phone_set": membership.phone is not None}
        after = {"position": body.position, "phone_set": body.phone is not None}
        if membership.position != body.position or membership.phone != body.phone:
            membership.position = body.position
            membership.phone = body.phone
            membership.updated_by = principal.user_id
            await session.flush()
        if before != after:
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
