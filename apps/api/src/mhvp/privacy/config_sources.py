"""Service providers derived from the actual configuration (AE32, S711-10, docs/rules/S711-10.md).

``detect`` reads the platform settings and the connector tables of the current tenant (the
session runs under RLS, so only the tenant's own rows are visible) and lists every external
service the platform is configured to use: mail, calendar, document stores, bank data access,
AI providers, print and mail, messaging, accounting, object storage, tracing.

The result carries technical facts only (host, mode, count, active flag). It contains no
credentials, no mailbox addresses and no legal finding: whether a service is a processor or a
sub processor, whether data leave the EU and on which legal basis is a maintenance field of the
register entry that starts ``open`` (rule 0.1.3, V13). ``sync`` takes detected services over as
register entries with every legal field open and never overwrites what the operator entered.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.models import AiProviderConfig
from mhvp.banking.models import BankConnection, ConnectionStatus, Connector, FinApiTenantConfig
from mhvp.communication.models import Mailbox, PostalSettings
from mhvp.communication.telephony import TelephonySettings
from mhvp.core.config import Settings
from mhvp.core.webhooks import WebhookSubscription
from mhvp.documents.models import DmsConnection, StorageKind
from mhvp.integrations.models import LexofficeTenantConfig
from mhvp.integrations.schadenstool.models import SchadenstoolTenantConfig
from mhvp.letting.models import BrokerTenantConfig
from mhvp.privacy.models import PrivacyRegisterEntry
from mhvp.sla.models import SmsGateway, WhatsAppConfig

SOURCE_KIND = "sub_processor"
_AI_NAMES = {"anthropic": "Anthropic (KI-Anbieter)", "openai": "OpenAI (KI-Anbieter)"}


@dataclass(frozen=True)
class DetectedSource:
    key: str
    name: str
    service: str
    active: bool
    detail: str
    scope: str  # "tenant": connector of this tenant, "platform": operator wide setting

    @property
    def detail_text(self) -> str:
        state = "aktiv" if self.active else "konfiguriert, derzeit nicht aktiv"
        origin = "Plattformeinstellung" if self.scope == "platform" else "Mandantenkonfiguration"
        return f"Aus {origin} erkannt ({state}). {self.detail}".strip()


def _host(url: str | None) -> str:
    if not url:
        return ""
    try:
        return (urlsplit(url if "//" in url else f"//{url}").hostname or "").lower()
    except ValueError:
        return ""


def _key(prefix: str, value: str = "") -> str:
    return (f"{prefix}:{value}" if value else prefix)[:64]


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


async def _mail(session: AsyncSession, _: Settings, __: str) -> list[DetectedSource]:
    rows = list(await session.scalars(select(Mailbox)))
    out: list[DetectedSource] = []
    gmail = [m for m in rows if m.kind == "gmail"]
    if gmail:
        on = sum(1 for m in gmail if m.enabled)
        out.append(
            DetectedSource(
                "gmail",
                "Google Gmail",
                "Abruf, Ablage und Versand von E-Mails über die Gmail API",
                on > 0,
                f"{_count(len(gmail), 'Postfach', 'Postfächer')} verbunden, davon {on} aktiv.",
                "tenant",
            )
        )
        cal = [m for m in gmail if m.calendar_enabled]
        if cal:
            out.append(
                DetectedSource(
                    "google_calendar",
                    "Google Kalender",
                    "Abgleich von Terminen über die Google Calendar API",
                    any(m.enabled for m in cal),
                    f"Kalenderabgleich an {_count(len(cal), 'Postfach', 'Postfächern')}.",
                    "tenant",
                )
            )
    hosts: dict[str, list[Mailbox]] = {}
    for m in rows:
        if m.kind != "gmail":
            host = _host(m.imap_host) or _host(m.smtp_host)
            if host:
                hosts.setdefault(host, []).append(m)
    for host, boxes in sorted(hosts.items()):
        on = sum(1 for m in boxes if m.enabled)
        out.append(
            DetectedSource(
                _key("mail", host),
                f"E-Mail-Server {host}",
                "Abruf und Versand von E-Mails über IMAP und SMTP",
                on > 0,
                f"{_count(len(boxes), 'Postfach', 'Postfächer')} mit Host {host}, "
                f"davon {on} aktiv.",
                "tenant",
            )
        )
    return out


async def _dms(session: AsyncSession, _: Settings, __: str) -> list[DetectedSource]:
    out: list[DetectedSource] = []
    for row in await session.scalars(select(DmsConnection).order_by(DmsConnection.kind)):
        if row.kind == StorageKind.GOOGLE_DRIVE:
            out.append(
                DetectedSource(
                    "google_drive",
                    "Google Drive",
                    "Spiegelung und Ablage von Dokumenten in Google Drive",
                    row.enabled,
                    "Dokumentspiegel Google Drive eingerichtet.",
                    "tenant",
                )
            )
        elif row.kind == StorageKind.PAPERLESS:
            host = _host(row.base_url)
            out.append(
                DetectedSource(
                    "paperless",
                    f"Paperless-ngx ({host})" if host else "Paperless-ngx",
                    "Spiegelung, Verschlagwortung und Belegeingang von Dokumenten",
                    row.enabled,
                    f"Host {host or 'nicht hinterlegt'}. Ob der Dienst selbst oder durch Dritte "
                    "betrieben wird, ist im Eintrag zu erfassen.",
                    "tenant",
                )
            )
    return out


async def _banking(session: AsyncSession, _: Settings, __: str) -> list[DetectedSource]:
    out: list[DetectedSource] = []
    finapi = await session.scalar(select(FinApiTenantConfig).limit(1))
    if finapi is not None:
        mode = "Sandbox" if finapi.sandbox else "Live"
        out.append(
            DetectedSource(
                "finapi",
                "finAPI",
                "Abruf von Kontoumsätzen und Salden über finAPI Access (nur lesend)",
                True,
                f"Umgebung {mode}, Host {_host(finapi.base_url) or 'Standard'}.",
                "tenant",
            )
        )
    gocardless = int(
        await session.scalar(
            select(func.count())
            .select_from(BankConnection)
            .where(
                BankConnection.connector == Connector.AGGREGATOR_GOCARDLESS,
                BankConnection.status != ConnectionStatus.DISABLED,
            )
        )
        or 0
    )
    if gocardless:
        out.append(
            DetectedSource(
                "gocardless",
                "GoCardless Bank Account Data",
                "Abruf von Kontoumsätzen über GoCardless Bank Account Data (nur lesend)",
                True,
                f"{_count(gocardless, 'Bankverbindung', 'Bankverbindungen')} eingerichtet.",
                "tenant",
            )
        )
    return out


async def _ai(session: AsyncSession, _: Settings, __: str) -> list[DetectedSource]:
    out: list[DetectedSource] = []
    for row in await session.scalars(select(AiProviderConfig).order_by(AiProviderConfig.provider)):
        provider = str(row.provider)
        released = row.released_at is not None
        avv_doc = "hinterlegt" if row.dpa_document_id else "nicht hinterlegt"
        out.append(
            DetectedSource(
                _key("ai", provider),
                _AI_NAMES.get(provider, f"{provider} (KI-Anbieter)"),
                "Verarbeitung maskierter Inhalte für KI-Vorschläge",
                row.enabled and released,
                f"Endpunktregion laut Konfiguration: {row.endpoint_region or 'nicht angegeben'}; "
                f"Freigabe in der KI-Konfiguration: {'ja' if released else 'nein'}; "
                f"AVV-Dokument in der KI-Konfiguration: {avv_doc}. Diese Angaben ersetzen "
                "keine Prüfung des Vertrags.",
                "tenant",
            )
        )
    return out


async def _postal(session: AsyncSession, _: Settings, __: str) -> list[DetectedSource]:
    row = await session.scalar(select(PostalSettings).limit(1))
    if row is None or row.provider == "manual":
        return []
    name = "LetterXpress" if row.provider == "letterxpress" else row.provider
    return [
        DetectedSource(
            _key("postal", row.provider),
            name,
            "Druck, Kuvertierung und Versand von Briefen",
            row.enabled,
            f"Modus {row.mode}.",
            "tenant",
        )
    ]


async def _messaging(session: AsyncSession, settings: Settings, _: str) -> list[DetectedSource]:
    out: list[DetectedSource] = []
    wa = await session.scalar(select(WhatsAppConfig).limit(1))
    if wa is not None:
        out.append(
            DetectedSource(
                "whatsapp",
                "Meta WhatsApp Business Platform",
                "Versand von Benachrichtigungen über freigegebene WhatsApp-Vorlagen",
                wa.enabled,
                f"Host {_host(settings.whatsapp_api_base_url)}.",
                "tenant",
            )
        )
    sms = await session.scalar(select(SmsGateway).limit(1))
    if sms is not None and _host(sms.url):
        host = _host(sms.url)
        out.append(
            DetectedSource(
                _key("sms", host),
                f"SMS-Gateway ({host})",
                "Versand von SMS-Benachrichtigungen",
                sms.enabled,
                f"Host {host}.",
                "tenant",
            )
        )
    tel = await session.scalar(select(TelephonySettings).limit(1))
    if tel is not None and tel.enabled:
        label = tel.provider_label or "Anbieter nicht benannt"
        out.append(
            DetectedSource(
                "telephony",
                f"Telefonanlage ({label})",
                "Übermittlung von Anrufereignissen (Rufnummer, Zeitpunkt, Dauer)",
                True,
                f"Anbieterbezeichnung laut Einstellung: {label}.",
                "tenant",
            )
        )
    return out


async def _accounting(session: AsyncSession, _: Settings, __: str) -> list[DetectedSource]:
    rows = list(await session.scalars(select(LexofficeTenantConfig)))
    if not rows:
        return []
    on = sum(1 for r in rows if r.enabled)
    return [
        DetectedSource(
            "lexoffice",
            "Lexware Office (lexoffice)",
            "Abgleich von Kontakten und Rechnungen mit Lexware Office",
            on > 0,
            f"{_count(len(rows), 'Organisation', 'Organisationen')} eingerichtet, "
            f"davon {on} aktiv.",
            "tenant",
        )
    ]


async def _platform(_: AsyncSession, settings: Settings, slug: str) -> list[DetectedSource]:
    out: list[DetectedSource] = []
    if settings.s3_configured:
        host = _host(settings.s3_endpoint_url)
        out.append(
            DetectedSource(
                _key("s3", host),
                f"Objektspeicher S3-API ({host})",
                "Speicherung der Dokumentdateien und Exporte",
                True,
                f"Host {host}, Region {settings.s3_region}.",
                "platform",
            )
        )
    if settings.objektakte_api_configured and (settings.objektakte_tenant or "") == slug:
        host = _host(settings.objektakte_api_url)
        out.append(
            DetectedSource(
                "objektakte",
                f"objektakte ({host})",
                "Lesezugriff und Ablage von Dokumenten der Objektakte",
                True,
                f"Host {host}; Upload {'aktiv' if settings.objektakte_upload_active else 'aus'}.",
                "platform",
            )
        )
    if settings.otel_endpoint:
        host = _host(settings.otel_endpoint)
        out.append(
            DetectedSource(
                _key("otel", host),
                f"Tracing-Endpunkt OpenTelemetry ({host})",
                "Übermittlung technischer Ablaufdaten (Traces)",
                True,
                f"Host {host}, Dienstname {settings.otel_service_name}.",
                "platform",
            )
        )
    return out


async def _bank_channels(session: AsyncSession, _: Settings, __: str) -> list[DetectedSource]:
    """EBICS and FinTS connections (GAE-34): the bank is the counterparty, the channel is read
    only here (no payment, G2)."""
    out: list[DetectedSource] = []
    for connector, key, name, service in (
        (Connector.EBICS, "ebics", "EBICS Bankzugang", "Bankkommunikation über EBICS"),
        (Connector.FINTS, "fints", "FinTS Bankzugang", "Abruf von Kontoumsätzen über FinTS"),
    ):
        rows = list(
            await session.scalars(
                select(BankConnection).where(BankConnection.connector == connector)
            )
        )
        if rows:
            on = sum(1 for r in rows if r.status != ConnectionStatus.DISABLED)
            banks = ", ".join(sorted({r.bank_name for r in rows if r.bank_name})[:5])
            out.append(
                DetectedSource(
                    key,
                    name,
                    service,
                    on > 0,
                    f"{_count(len(rows), 'Bankverbindung', 'Bankverbindungen')}, davon {on} "
                    f"aktiv. Banken: {banks or 'nicht hinterlegt'}.",
                    "tenant",
                )
            )
    return out


async def _damage_tool(session: AsyncSession, _: Settings, __: str) -> list[DetectedSource]:
    row = await session.scalar(select(SchadenstoolTenantConfig).limit(1))
    if row is None:
        return []
    host = _host(row.base_url)
    return [
        DetectedSource(
            "schadenstool",
            f"Schadenstool ({host})" if host else "Schadenstool",
            "Übergabe von Schadenmeldungen und Tickets an das Schadenstool",
            row.enabled,
            f"Host {host or 'nicht hinterlegt'}. Auftragsverarbeitung laut Bestätigung im "
            "Konnektor, Register nicht ersetzt.",
            "tenant",
        )
    ]


async def _broker(session: AsyncSession, _: Settings, __: str) -> list[DetectedSource]:
    out: list[DetectedSource] = []
    for row in await session.scalars(
        select(BrokerTenantConfig).order_by(BrokerTenantConfig.provider)
    ):
        host = _host(row.base_url)
        out.append(
            DetectedSource(
                _key("broker", row.provider),
                f"Makler-CRM {row.provider}",
                "Übergabe von Objekt- und Interessentendaten an das Makler- oder Portal-CRM",
                row.enabled,
                f"Anbieter {row.provider}, Host {host or 'Standard'}.",
                "tenant",
            )
        )
    return out


async def _webhook_targets(session: AsyncSession, _: Settings, __: str) -> list[DetectedSource]:
    """Target hosts of webhook subscriptions: Dritte erhalten Ereignisdaten (GAE-34)."""
    hosts: dict[str, list[WebhookSubscription]] = {}
    for sub in await session.scalars(select(WebhookSubscription)):
        hosts.setdefault(_host(sub.url) or "unbekannt", []).append(sub)
    out: list[DetectedSource] = []
    for host, subs in sorted(hosts.items()):
        on = sum(1 for s in subs if s.active)
        out.append(
            DetectedSource(
                _key("webhook", host),
                f"Webhook-Ziel {host}",
                "Zustellung von Ereignissen an ein externes System per Webhook",
                on > 0,
                f"{_count(len(subs), 'Abonnement', 'Abonnements')}, davon {on} aktiv.",
                "tenant",
            )
        )
    return out


Detector = Callable[[AsyncSession, Settings, str], Awaitable[list[DetectedSource]]]
DETECTORS: tuple[Detector, ...] = (
    _mail,
    _dms,
    _banking,
    _ai,
    _postal,
    _messaging,
    _accounting,
    _bank_channels,
    _damage_tool,
    _broker,
    _webhook_targets,
    _platform,
)


async def detect(
    session: AsyncSession, settings: Settings, tenant_slug: str
) -> list[DetectedSource]:
    found: list[DetectedSource] = []
    for detector in DETECTORS:
        found.extend(await detector(session, settings, tenant_slug))
    return found


def consent_purposes(key: str) -> list[str]:
    """Consent purposes (contacts.consent_rules.PURPOSES) a detected service serves, derived
    from its key; a display aid only (GAE-34), never a legal finding."""
    if key in ("gmail",) or key.startswith("mail:"):
        return ["email_delivery"]
    if key == "schadenstool" or key.startswith(("broker:", "webhook:")):
        return ["data_sharing"]
    return []


@dataclass
class SyncResult:
    created: list[PrivacyRegisterEntry]
    updated: list[PrivacyRegisterEntry]
    skipped_inactive: int


async def sync(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    sources: list[DetectedSource],
    include_inactive: bool,
) -> SyncResult:
    """Create missing register entries for detected services; refresh only ``source_detail``.

    Serialised per tenant by a transaction scoped advisory lock so that two parallel calls do
    not both create the same entry (the partial unique index would reject the second one)."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"privacy_register_sync:{tenant_id}"},
    )
    existing = {
        e.source_key: e
        for e in await session.scalars(
            select(PrivacyRegisterEntry).where(PrivacyRegisterEntry.source_key.is_not(None))
        )
    }
    result = SyncResult(created=[], updated=[], skipped_inactive=0)
    for src in sources:
        row = existing.get(src.key)
        if row is not None:
            if row.source_detail != src.detail_text:
                row.source_detail = src.detail_text
                row.updated_by = user_id
                result.updated.append(row)
            continue
        if not src.active and not include_inactive:
            result.skipped_inactive += 1
            continue
        row = PrivacyRegisterEntry(
            tenant_id=tenant_id,
            created_by=user_id,
            kind=SOURCE_KIND,
            name=src.name[:200],
            purpose=src.service,
            avv_status="none",
            third_country=False,
            third_country_status="open",
            legal_review_status="open",
            source_key=src.key,
            source_detail=src.detail_text,
        )
        session.add(row)
        result.created.append(row)
    await session.flush()
    return result
