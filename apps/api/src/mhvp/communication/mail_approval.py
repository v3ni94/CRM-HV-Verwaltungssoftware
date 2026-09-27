"""M20-04 Vier-Augen-Prinzip beim Mailversand (docs/rules/M20-04.md).

Baut auf M20-03 (``mhvp.communication.routers._self_approval_allowed``) auf und ergänzt:

1. **Mandantenkonfiguration** (``TenantSettings.mail_approval_mode``): ``all`` (jede
   ausgehende Mail braucht eine zweite Person), ``external_only`` (nur Mails an Kontakte der
   Kategorie Behörde/Gericht/Investor, Standard) oder ``off`` (Verfasser darf selbst senden).
   Annahme (docs/ASSUMPTIONS.md M20-04): der Kompetenzkatalog kennt bisher nur den Kontakttyp
   ``authority`` (Behörde); Gericht und Investor werden über die Kontakt-Tags ``gericht`` und
   ``investor`` erkannt, bis ein eigener Kontakttyp entschieden ist (docs/OPEN_QUESTIONS.md).
2. **Re-Authentifizierung**: Freigabe nur mit einem höchstens 5 Minuten alten Nachweis
   (Passwort oder TOTP), unabhängig vom Konfigurationsmodus.
3. **Superadmin-Bypass** (ADR 0011): nur mit dem Plattform-Flag ``gate_superadmin_bypass`` und
   nur für den einzigen Superadmin; die Freigabe bleibt dann protokolliert mit
   ``four_eyes = false`` und ``superadmin_bypass = true``.
4. **Vertretung**: ein befristet eingetragener Stellvertreter (``MailApprovalDeputy``) darf für
   einen abwesenden Postfachnutzer freigeben; die Freigabe wird mit beiden Identitäten
   protokolliert.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import MailApprovalDeputy, MailApprovalReauth, Message
from mhvp.core.auth import passwords, totp
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantSettings, User

REAUTH_WINDOW = timedelta(minutes=5)

# Annahme M20-04 (docs/ASSUMPTIONS.md): Kontakt-Tags, die zusätzlich zum Kontakttyp ``authority``
# als "extern im Sinne des Vier-Augen-Prinzips" gelten, solange kein eigener Kontakttyp für
# Gericht/Investor entschieden ist.
EXTERNAL_CATEGORY_TAGS = {"gericht", "investor", "gerichte", "investoren"}


class MailApprovalMode(StrEnum):
    ALL = "all"
    EXTERNAL_ONLY = "external_only"
    OFF = "off"


def _mode(value: str | None) -> MailApprovalMode:
    try:
        return MailApprovalMode(value or MailApprovalMode.EXTERNAL_ONLY)
    except ValueError:
        return MailApprovalMode.EXTERNAL_ONLY


async def approval_mode(session: AsyncSession, tenant_id: uuid.UUID) -> MailApprovalMode:
    value = await session.scalar(
        select(TenantSettings.mail_approval_mode).where(TenantSettings.tenant_id == tenant_id)
    )
    return _mode(value)


async def _is_external_category_contact(session: AsyncSession, contact_id: uuid.UUID) -> bool:
    """Kontakt der Kategorie Behörde/Gericht/Investor (siehe Moduldocstring)."""
    from mhvp.contacts.models import ContactTag, ContactTagLink, ContactType, ContactTypeCode

    is_authority = await session.scalar(
        select(ContactType.id).where(
            ContactType.contact_id == contact_id,
            ContactType.type == ContactTypeCode.AUTHORITY,
        )
    )
    if is_authority is not None:
        return True
    rows = await session.execute(
        select(ContactTag.name)
        .join(ContactTagLink, ContactTagLink.tag_id == ContactTag.id)
        .where(ContactTagLink.contact_id == contact_id)
    )
    names = {n.lower() for (n,) in rows}
    return bool(names & EXTERNAL_CATEGORY_TAGS)


async def is_external_recipient_message(session: AsyncSession, row: Message) -> bool:
    """Fällt der Empfänger der Nachricht unter die Kategorie externer Empfänger (Behörde,
    Gericht, Investor)? Ohne verknüpften Kontakt gilt die Nachricht vorsorglich als extern
    (Standardregel des Mandanten "an für externe Empfänger" soll niemanden auslassen)."""
    if row.contact_id is None:
        return True
    return await _is_external_category_contact(session, row.contact_id)


async def four_eyes_required(session: AsyncSession, row: Message) -> bool:
    """Ob die Identitätsprüfung (Freigebender != Verfasser) für diese Nachricht überhaupt
    gilt; die Ausnahmen aus M20-03 (Ticketantwort, Kennzeichen, Notbremse) wirken zusätzlich
    innerhalb dieser Regel, siehe ``routers._self_approval_allowed``."""
    mode = await approval_mode(session, row.tenant_id)
    if mode is MailApprovalMode.OFF:
        return False
    if mode is MailApprovalMode.ALL:
        return True
    return await is_external_recipient_message(session, row)


# Re-Authentifizierung -----------------------------------------------------------------


@dataclass(frozen=True)
class ReauthResult:
    method: str
    verified_at: datetime


def verify_identity(user: User, *, password: str | None, totp_code: str | None) -> str:
    """Prüft Passwort oder TOTP frisch (nicht die bestehende Sitzung, sondern ein erneuter
    Nachweis wie beim Login) gegen das Konto in ``platform_session``; bei TOTP wird
    ``user.totp_last_step`` fortgeschrieben (Replay-Schutz wie beim Login). Genau eines von
    ``password``/``totp_code`` wird erwartet, gibt die genutzte Methode zurück."""
    if totp_code:
        if not user.totp_enabled or not user.totp_secret:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="TOTP ist für dieses Konto nicht eingerichtet."
            )
        step = totp.matching_step(user.totp_secret, totp_code, last_step=user.totp_last_step)
        if step is None:
            raise ProblemError(ErrorCodes.INVALID_CREDENTIALS, detail="Der Code ist ungültig.")
        user.totp_last_step = step
        return "totp"
    if password:
        if not passwords.verify_password(user.password_hash, password):
            raise ProblemError(ErrorCodes.INVALID_CREDENTIALS, detail="Das Passwort ist falsch.")
        return "password"
    raise ProblemError(ErrorCodes.VALIDATION, detail="Passwort oder TOTP-Code werden benötigt.")


async def record_reauth(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, method: str
) -> ReauthResult:
    """Speichert den Nachweis (Tabelle ``mail_approval_reauth``, Mandanten-Session) für das
    5-Minuten-Fenster vor einer Mailfreigabe."""
    now = datetime.now(UTC)
    stmt = pg_insert(MailApprovalReauth).values(
        tenant_id=tenant_id, user_id=user_id, method=method, verified_at=now
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_mail_approval_reauth_user",
        set_={"method": method, "verified_at": now, "updated_at": now},
    )
    await session.execute(stmt)
    return ReauthResult(method=method, verified_at=now)


async def has_recent_reauth(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, *, now: datetime | None = None
) -> bool:
    now = now or datetime.now(UTC)
    verified_at = await session.scalar(
        select(MailApprovalReauth.verified_at).where(
            MailApprovalReauth.tenant_id == tenant_id, MailApprovalReauth.user_id == user_id
        )
    )
    return verified_at is not None and now - verified_at <= REAUTH_WINDOW


def require_recent_reauth(has_reauth: bool) -> None:
    if not has_reauth:
        raise ProblemError(
            ErrorCodes.MAIL_APPROVAL_REAUTH_REQUIRED,
            detail=(
                "Bitte Passwort oder TOTP-Code erneut eingeben, bevor die Mail freigegeben "
                "wird (gültig für 5 Minuten)."
            ),
        )


# Vertretung ---------------------------------------------------------------------------


async def active_deputy_of(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    deputy_user_id: uuid.UUID,
    absent_user_id: uuid.UUID,
    now: datetime | None = None,
) -> MailApprovalDeputy | None:
    """Ist ``deputy_user_id`` gerade eine gültige Vertretung von ``absent_user_id``?"""
    if deputy_user_id == absent_user_id:
        return None
    now = now or datetime.now(UTC)
    row = await session.scalar(
        select(MailApprovalDeputy).where(
            MailApprovalDeputy.tenant_id == tenant_id,
            MailApprovalDeputy.absent_user_id == absent_user_id,
            MailApprovalDeputy.deputy_user_id == deputy_user_id,
            MailApprovalDeputy.revoked_at.is_(None),
            MailApprovalDeputy.starts_at <= now,
            MailApprovalDeputy.ends_at >= now,
        )
    )
    return row


async def deputises_for_any(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    deputy_user_id: uuid.UUID,
    absent_user_ids: set[uuid.UUID],
    now: datetime | None = None,
) -> uuid.UUID | None:
    """Erste Person aus ``absent_user_ids``, für die ``deputy_user_id`` gerade vertritt, sonst
    ``None``. Für Postfächer, die nur bestimmten Personen zugewiesen sind (M16): der
    Stellvertreter erhält so ohne eigene Zuweisung Zugriff für die Dauer der Vertretung."""
    absent_user_ids.discard(deputy_user_id)
    if not absent_user_ids:
        return None
    now = now or datetime.now(UTC)
    row = await session.scalar(
        select(MailApprovalDeputy.absent_user_id).where(
            MailApprovalDeputy.tenant_id == tenant_id,
            MailApprovalDeputy.deputy_user_id == deputy_user_id,
            MailApprovalDeputy.absent_user_id.in_(absent_user_ids),
            MailApprovalDeputy.revoked_at.is_(None),
            MailApprovalDeputy.starts_at <= now,
            MailApprovalDeputy.ends_at >= now,
        )
    )
    return row
