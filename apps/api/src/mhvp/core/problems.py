"""RFC 9457 problem details with registered error codes (ADR 0004).

Every error response uses ``application/problem+json``. ``title`` and ``detail`` are German
user texts, ``developer_message`` is English. Codes follow ``MHVP-<DOMAIN>-<NNNN>`` and are
registered once in :data:`REGISTRY`.
"""

import re
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from mhvp.core.context import get_correlation_id

PROBLEM_CONTENT_TYPE = "application/problem+json"
CODE_PATTERN = re.compile(r"^MHVP-[A-Z]+-\d{4}$")


@dataclass(frozen=True, slots=True)
class ErrorCode:
    code: str
    status: int
    title: str
    developer_message: str

    @property
    def type_uri(self) -> str:
        return f"urn:mhvp:problem:{self.code}"


class ErrorCodes:
    INTERNAL = ErrorCode("MHVP-CORE-0001", 500, "Interner Fehler", "Unexpected server error.")
    NOT_FOUND = ErrorCode(
        "MHVP-CORE-0002", 404, "Ressource nicht gefunden", "No route or resource matches."
    )
    METHOD_NOT_ALLOWED = ErrorCode(
        "MHVP-CORE-0003", 405, "Methode nicht erlaubt", "HTTP method not allowed here."
    )
    VALIDATION = ErrorCode("MHVP-CORE-0004", 422, "Eingaben ungültig", "Request validation failed.")
    HTTP_ERROR = ErrorCode(
        "MHVP-CORE-0005", 400, "Anfrage nicht verarbeitbar", "Generic HTTP error."
    )
    RATE_LIMITED = ErrorCode(
        "MHVP-CORE-0006",
        429,
        "Zu viele Anfragen",
        "Rate limit per token, API key or client address exceeded (A49); see Retry-After.",
    )
    IDEMPOTENCY_KEY_MISMATCH = ErrorCode(
        "MHVP-CORE-0007",
        422,
        "Idempotency-Key bereits anders verwendet",
        "Same Idempotency-Key reused with a different method, path or body (A48).",
    )
    IDEMPOTENCY_IN_PROGRESS = ErrorCode(
        "MHVP-CORE-0008",
        409,
        "Aufruf mit diesem Idempotency-Key läuft noch",
        "First request with this Idempotency-Key has not completed yet (A48).",
    )
    IDEMPOTENCY_KEY_INVALID = ErrorCode(
        "MHVP-CORE-0009",
        422,
        "Idempotency-Key ungültig",
        "Idempotency-Key header must be 1 to 255 characters (A48).",
    )
    NOT_AUTHENTICATED = ErrorCode(
        "MHVP-AUTH-0001", 401, "Anmeldung erforderlich", "Missing or invalid credentials."
    )
    INVALID_CREDENTIALS = ErrorCode(
        "MHVP-AUTH-0002", 401, "Anmeldung fehlgeschlagen", "E-mail, password or code invalid."
    )
    FORBIDDEN = ErrorCode(
        "MHVP-AUTH-0003", 403, "Keine Berechtigung", "Permission missing for this action."
    )
    ACCOUNT_LOCKED = ErrorCode(
        "MHVP-AUTH-0004", 423, "Konto vorübergehend gesperrt", "Too many failed logins."
    )
    TENANT_MISMATCH = ErrorCode(
        "MHVP-AUTH-0005", 403, "Mandant passt nicht zur Adresse", "Host and token tenant differ."
    )
    PASSWORD_POLICY = ErrorCode(
        "MHVP-AUTH-0006", 422, "Passwort erfüllt die Vorgaben nicht", "Password policy violated."
    )
    REFRESH_INVALID = ErrorCode(
        "MHVP-AUTH-0007", 401, "Sitzung abgelaufen", "Refresh token invalid, expired or reused."
    )
    AUTH_NOT_CONFIGURED = ErrorCode(
        "MHVP-AUTH-0008", 503, "Anmeldung nicht verfügbar", "Signing or encryption key missing."
    )
    TENANT_SELECTION = ErrorCode(
        "MHVP-AUTH-0009", 409, "Mandant auswählen", "Several memberships, tenant_id required."
    )
    OIDC_INVALID = ErrorCode(
        "MHVP-AUTH-0010", 400, "Anmeldeanfrage ungültig", "OIDC request invalid (RFC 6749)."
    )
    MAGIC_LINK_INVALID = ErrorCode(
        "MHVP-AUTH-0011",
        401,
        "Anmeldelink ungültig oder abgelaufen",
        "Magic link token unknown, expired or already used (M21-01).",
    )
    RESOURCE_NOT_FOUND = ErrorCode(
        "MHVP-PLAT-0001", 404, "Datensatz nicht gefunden", "Entity not found in this tenant."
    )
    CONFLICT = ErrorCode(
        "MHVP-PLAT-0002", 409, "Datensatz existiert bereits", "Unique constraint violated."
    )
    VERSION_CONFLICT = ErrorCode(
        "MHVP-PLAT-0003", 412, "Datensatz wurde zwischenzeitlich geändert", "If-Match mismatch."
    )
    WEBHOOK_TARGET = ErrorCode(
        "MHVP-HOOK-0001", 422, "Webhook-Ziel nicht zulässig", "Unsafe or invalid webhook URL."
    )
    WEBHOOK_SIGNATURE = ErrorCode(
        "MHVP-HOOK-0002",
        401,
        "Webhook-Signatur ungültig",
        "Missing, stale or invalid HMAC signature on an inbound webhook (A30).",
    )
    WEBHOOK_REPLAY = ErrorCode(
        "MHVP-HOOK-0003",
        409,
        "Webhook bereits verarbeitet",
        "Same signature delivered again within the replay window (A30).",
    )
    WEBHOOK_TOO_LARGE = ErrorCode(
        "MHVP-HOOK-0004",
        413,
        "Webhook-Inhalt zu groß",
        "Inbound webhook body exceeds the size limit (A70).",
    )
    GATE_FOUR_EYES = ErrorCode(
        "MHVP-GATE-0002",
        403,
        "Freigabe durch eine zweite Person erforderlich",
        "Requester and approver must be different persons.",
    )
    GATE_STATE = ErrorCode(
        "MHVP-GATE-0003", 409, "Freigabeantrag nicht im passenden Zustand", "Invalid state."
    )
    GATE_CHART_NOT_RELEASED = ErrorCode(
        "MHVP-GATE-0004",
        409,
        "Kontenrahmen nicht freigegeben",
        "G1 needs a chart of accounts template in status released for the tenant (V8, "
        "M10-01/M10-02); the request stays open until a version is released.",
    )
    GATE_G5_EVIDENCE_MISSING = ErrorCode(
        "MHVP-GATE-0005",
        409,
        "G5-Nachweise unvollständig oder Freigabe nicht durch den Superadmin",
        "G5 needs every evidence item done with a linked document and the superadmin as "
        "approver (M27-02); the request stays open until then.",
    )
    RETENTION_LOCKED = ErrorCode(
        "MHVP-DOC-0001",
        409,
        "Dokument ist aufbewahrungspflichtig oder gesperrt",
        "Deletion needs a released retention profile, an expired period and no hold (6.9.5).",
    )
    PLACEHOLDER = ErrorCode(
        "MHVP-DOC-0002", 422, "Platzhalter nicht auflösbar", "Template placeholder error."
    )
    UPLOAD_REJECTED = ErrorCode(
        "MHVP-DOC-0003", 422, "Datei nicht zulässig", "File type, content or size not accepted."
    )
    LETTERHEAD_INCOMPLETE = ErrorCode(
        "MHVP-DOC-0004",
        422,
        "Briefbogen unvollständig",
        "Mandatory company data of the tenant is missing (tenant settings).",
    )
    DMS_NOT_CONFIGURED = ErrorCode(
        "MHVP-DOC-0005",
        502,
        "Paperless ist nicht eingerichtet",
        "No enabled Paperless DmsConnection with base_url and token for this tenant.",
    )
    DMS_UNAVAILABLE = ErrorCode(
        "MHVP-DOC-0006",
        503,
        "Paperless nicht erreichbar",
        "Paperless request failed or timed out.",
    )
    OBJEKTAKTE_NOT_CONFIGURED = ErrorCode(
        "MHVP-OAK-0001",
        502,
        "objektakte ist nicht angebunden",
        (
            "OBJEKTAKTE_API_URL, OBJEKTAKTE_API_TOKEN or OBJEKTAKTE_TENANT is empty, or the "
            "signed in tenant is not the configured objektakte tenant (M29 Stufe 4)."
        ),
    )
    OBJEKTAKTE_UNAVAILABLE = ErrorCode(
        "MHVP-OAK-0002",
        502,
        "objektakte nicht erreichbar",
        "Request to the objektakte read API failed, timed out, was refused or was malformed.",
    )
    OBJEKTAKTE_OBJECT_NOT_FOUND = ErrorCode(
        "MHVP-OAK-0003",
        404,
        "Objekt in objektakte nicht gefunden",
        "objektakte answered 404 for this object number.",
    )
    OBJEKTAKTE_PROPOSAL_STATE = ErrorCode(
        "MHVP-OAK-0004",
        409,
        "Importvorschlag bereits entschieden",
        "The person list proposal is approved or rejected; start a new proposal instead.",
    )
    STORAGE_UNAVAILABLE = ErrorCode(
        "MHVP-DOC-0007",
        503,
        "Dokumentenspeicher nicht verfügbar",
        "Object storage (S3 API) is not configured or the request failed; nothing was stored.",
    )
    MALWARE_FOUND = ErrorCode(
        "MHVP-DOC-0008",
        422,
        "Datei wegen Schadsoftwarefund abgewiesen",
        "The malware scan (ClamAV) reported a finding; the file was not stored (27.09.2026).",
    )
    SCAN_UNAVAILABLE = ErrorCode(
        "MHVP-DOC-0009",
        503,
        "Schadsoftwareprüfung nicht möglich",
        "MHVP_CLAMAV_MODE=enforce and clamd did not answer; nothing was stored.",
    )
    ACC_UNBALANCED = ErrorCode(
        "MHVP-ACC-0001",
        422,
        "Buchungssatz nicht ausgeglichen",
        "A journal entry needs at least two lines and equal debit and credit sums (B02).",
    )
    ACC_PERIOD_LOCKED = ErrorCode(
        "MHVP-ACC-0002",
        409,
        "Zeitraum festgeschrieben",
        "The booking date lies in a locked period of the ledger (B03).",
    )
    ACC_POSTED_IMMUTABLE = ErrorCode(
        "MHVP-ACC-0003",
        409,
        "Gebuchter Satz unveränderlich",
        "Posted entries are corrected by reversal only (B03).",
    )
    ACC_WRONG_ENTITY = ErrorCode(
        "MHVP-ACC-0004",
        422,
        "Falscher Rechtsträger",
        "Accounts, open items or bank accounts belong to another ledger (B01).",
    )
    ACC_VAT_NOT_RELEASED = ErrorCode(
        "MHVP-ACC-0005",
        409,
        "Steuerbehandlung nicht freigegeben",
        (
            "The ledger has a VAT option but no released tax treatment: invoices with VAT and "
            "receivables with VAT are not posted automatically (M14-02, M13-03, D45)."
        ),
    )
    ACC_APPROVAL_LIMIT = ErrorCode(
        "MHVP-ACC-0006",
        409,
        "Zweite Freigabe erforderlich",
        (
            "The invoice exceeds the approval limit of the releasing person's roles; a second "
            "approval by a third person is required before posting (M14-03)."
        ),
    )
    AI_POSTING_NOT_RELEASED = ErrorCode(
        "MHVP-AI-0001",
        403,
        "KI-Kontierung ist nicht freigegeben",
        (
            "propose_posting needs tenant_settings.ai_posting_enabled and a released AI "
            "provider with DPA evidence (M7-09, M12-01)."
        ),
    )
    RELEASE_GATE_CLOSED = ErrorCode(
        "MHVP-GATE-0001",
        403,
        "Funktion nicht freigegeben",
        "Release gate is closed for this tenant (ADR 0003).",
    )
    IMW_NOT_CONFIGURED = ErrorCode(
        "MHVP-IMW-0001",
        502,
        "Immoware24 ist nicht eingerichtet",
        "No enabled ImmowareConnection with base_url and credentials for this tenant.",
    )
    IMW_UNAVAILABLE = ErrorCode(
        "MHVP-IMW-0002",
        503,
        "Immoware24 nicht erreichbar",
        "DAV request to Immoware24 failed or timed out.",
    )
    IMW_LEARNING_RUN_NOT_FOUND = ErrorCode(
        "MHVP-IMW-0004",
        404,
        "Lernlauf nicht gefunden",
        "No ImmowareLearningRun with this id for the tenant (M33).",
    )
    IMW_WRITE_BLOCKED = ErrorCode(
        "MHVP-IMW-0003",
        500,
        "Schreibversuch blockiert",
        "Write path to Immoware24 is hard-blocked; only PROPFIND/REPORT/GET are allowed.",
    )
    IMW_SYNC_RUNNING = ErrorCode(
        "MHVP-IMW-0005",
        409,
        "Abholung läuft bereits",
        "A sync run of this kind is still running for the tenant; a second start is refused.",
    )
    FINAPI_NOT_CONFIGURED = ErrorCode(
        "MHVP-BANK-0001",
        502,
        "finAPI ist für diesen Mandanten nicht eingerichtet",
        "No FinApiTenantConfig with client credentials for this tenant.",
    )
    FINAPI_UNAVAILABLE = ErrorCode(
        "MHVP-BANK-0002",
        503,
        "finAPI nicht erreichbar",
        "Request to the finAPI Access API failed or was rejected.",
    )
    FINAPI_NOT_VERIFIED = ErrorCode(
        "MHVP-BANK-0003",
        501,
        "finAPI-Funktion noch nicht freigegeben",
        (
            "Endpoint or field is marked 'zu prüfen' in docs/integrations/finapi.md and is not "
            "called until confirmed against the official documentation."
        ),
    )
    FINAPI_STATE = ErrorCode(
        "MHVP-BANK-0004",
        409,
        "Bankverbindung ist im falschen Zustand",
        "The requested action does not match the connection's current finAPI state.",
    )
    FINAPI_AUTH = ErrorCode(
        "MHVP-BANK-0005",
        502,
        "finAPI-Zugangsdaten abgelehnt",
        (
            "finAPI answered 401/403: client id/secret or the finAPI user token of this "
            "connection were rejected. Check the credentials in the bank settings."
        ),
    )
    FINAPI_RATE_LIMITED = ErrorCode(
        "MHVP-BANK-0006",
        503,
        "finAPI-Anfragelimit erreicht",
        (
            "finAPI answered 429 (rate limit). The request was not retried automatically; the "
            "next scheduled or manual fetch picks up where the cursor stopped."
        ),
    )
    # FinTS/HBCI (M11-01 addendum 27.09.2026, docs/integrations/fints.md section 5).
    FINTS_NOT_CONFIGURED = ErrorCode(
        "MHVP-BANK-0007",
        501,
        "FinTS ist nicht eingerichtet (Produktregistrierung fehlt)",
        (
            "MHVP_FINTS_PRODUCT_ID is empty. Register the product with the Deutsche "
            "Kreditwirtschaft and set the registration number (docs/integrations/fints.md)."
        ),
    )
    FINTS_INSTITUTE_NOT_CONNECTABLE = ErrorCode(
        "MHVP-BANK-0008",
        422,
        "Institut bietet keinen FinTS-Zugang",
        "The institute list has no FinTS URL for this BLZ; direct access is not possible.",
    )
    FINTS_PIN_REJECTED = ErrorCode(
        "MHVP-BANK-0009",
        502,
        "Bank hat Anmeldename oder PIN abgelehnt",
        (
            "The bank rejected the login (return codes 9340, 9910, 9930, 9931, 9942 or an "
            "error during dialog initialisation). No automatic retry: three failures lock the "
            "access at the bank."
        ),
    )
    FINTS_ACCOUNT_LOCKED = ErrorCode(
        "MHVP-BANK-0010",
        502,
        "Bankzugang gesperrt",
        "The bank reports a locked access (3938/9931); unlock it with the bank first.",
    )
    FINTS_TAN_REJECTED = ErrorCode(
        "MHVP-BANK-0011",
        502,
        "Bank hat die TAN abgelehnt",
        "The bank rejected the TAN (9941 ff). Start the step again with a new TAN.",
    )
    FINTS_SCA_REQUIRED = ErrorCode(
        "MHVP-BANK-0012",
        409,
        "Erneute Freigabe (TAN) nötig",
        (
            "The bank requires strong customer authentication (9075), typically every 90 days "
            "(PSD2). Start a new TAN session for this connection."
        ),
    )
    FINTS_UNAVAILABLE = ErrorCode(
        "MHVP-BANK-0013",
        503,
        "Bank nicht erreichbar",
        "The FinTS server did not answer or the connection failed.",
    )
    FINTS_BANK_REJECTED = ErrorCode(
        "MHVP-BANK-0014",
        502,
        "Bank hat die Anfrage abgelehnt",
        "The bank answered with an error return code (9xxx) not mapped more specifically.",
    )
    FINTS_STATE = ErrorCode(
        "MHVP-BANK-0015",
        409,
        "FinTS-Sitzung ist im falschen Zustand",
        "The requested action does not match the session or connection state.",
    )
    FINTS_PIN_BLOCKED = ErrorCode(
        "MHVP-BANK-0016",
        409,
        "PIN nach Fehlversuch gesperrt, neue Eingabe nötig",
        (
            "After a rejected login the stored PIN is not reused automatically (the bank locks "
            "the access after three failures). Enter the PIN again to continue."
        ),
    )
    PAYMENT_CHANNEL_UNAVAILABLE = ErrorCode(
        "MHVP-BANK-0017",
        409,
        "Einreichungsweg nicht verfügbar",
        (
            "The submission channel (FinTS or EBICS) is prepared but not activated: contract, "
            "initialisation or feature flag missing (M15-01, V2). Use the file channel."
        ),
    )
    PAYMENT_FILE_STATE = ErrorCode(
        "MHVP-BANK-0018",
        409,
        "Zahlungsdatei im falschen Zustand",
        "The batch has no stored file, was already submitted or its checksum does not match.",
    )
    BANK_TRANSFER_PAIR_SETTLED = ErrorCode(
        "MHVP-BANK-0019",
        409,
        "Umbuchung bereits über die Partnerseite gebucht",
        (
            "The other half of this recognised transfer pair (transfer_pair_id) is already "
            "posted; one posting moves both bank accounts, the second half has no second "
            "effect (D04, B08). Reverse that posting first to book the pair again."
        ),
    )
    BANK_TRANSFER_PARTNER_BOOKED_ELSEWHERE = ErrorCode(
        "MHVP-BANK-0020",
        409,
        "Gegenseite der Umbuchung anders gebucht",
        (
            "The other half of this recognised transfer pair is posted against another "
            "account (e.g. Geldtransit), not as a transfer between both bank accounts. Booking "
            "this half against the partner bank account would move that account a second "
            "time; book it against the account named in the detail, or reverse the partner "
            "posting first to post a direct transfer (D04, B08)."
        ),
    )
    BANK_DECISION_STALE = ErrorCode(
        "MHVP-BANK-0021",
        409,
        "Vorschlag veraltet",
        (
            "The proposal_id of the booking, rejection or ignore does not name the pending "
            "decision round of this transaction (posting_decision): the snapshot was refreshed "
            "or already closed. Reload the proposals and decide again (ADR 0014, M12-04)."
        ),
    )
    BANK_LEVEL_NOT_ELIGIBLE = ErrorCode(
        "MHVP-BANK-0022",
        409,
        "Automatikstufe nicht erreichbar",
        (
            "The case class does not meet the eligibility figures for the requested level "
            "(decisions in the window, precision of shown proposals, days at the previous "
            "level, automatic error rate) or is capped below it (plan M12 3.4, rule M12-05)."
        ),
    )
    BANK_LEVEL_TOO_LOW = ErrorCode(
        "MHVP-BANK-0023",
        409,
        "Automatikstufe zu niedrig",
        (
            "The one click acceptance needs level L1 for the case class of the transaction "
            "and a deterministically verified proposal; the automatic runner needs L2 or L3. "
            "Book through the full dialog instead (rule M12-05)."
        ),
    )
    BANK_RULE_PROPOSAL_WIDENED = ErrorCode(
        "MHVP-BANK-0024",
        422,
        "Regelvorschlag darf nur verengt werden",
        (
            "Accepting a learned rule proposal may narrow the amount band and add purpose "
            "tokens, never widen the band, drop the counterparty key or change the account "
            "(plan M12 3.3, rule M12-06)."
        ),
    )
    BANK_AUTO_POST_REFUSED = ErrorCode(
        "MHVP-BANK-0025",
        409,
        "Automatikbuchung abgelehnt",
        (
            "The deterministic verifier of the case class refused the posting at posting "
            "time (fingerprint mismatch, chronology, account lock criteria, period lock, "
            "limits, overdue review or missing evidence chain). The transaction stays open."
        ),
    )
    BILLING_PREFIX_MISSING = ErrorCode(
        "MHVP-BILL-0001",
        409,
        "Rechnungskürzel fehlt",
        "TenantBillingSettings.invoice_prefix is not configured (M13-04).",
    )
    BILLING_VAT_STATUS_MISSING = ErrorCode(
        "MHVP-BILL-0002",
        409,
        "Umsatzsteuerstatus fehlt",
        "TenantBillingSettings.vat_status is unset; XRechnung is blocked (M13-04).",
    )
    BILLING_TAX_DATA_MISSING = ErrorCode(
        "MHVP-BILL-0003",
        409,
        "Steuerdaten unvollständig",
        "Required tax data for the tenant's vat_status is missing (M13-04).",
    )
    DATEV_NOT_CONFIGURED = ErrorCode(
        "MHVP-BILL-0004",
        409,
        "DATEV-Parameter fehlen",
        "consultant_number, client_number or chart_of_accounts not set (M18-01).",
    )
    DATEV_MAPPING_MISSING = ErrorCode(
        "MHVP-BILL-0008",
        409,
        "DATEV-Kontenzuordnung unvollständig",
        "Posted lines use CRM accounts without a DatevAccountMapping for the ledger and "
        "booking date; the batch is not written with raw account numbers (A36, M18-04).",
    )
    DATEV_EXPORT_CONTENT_MISSING = ErrorCode(
        "MHVP-BILL-0009",
        409,
        "Exportdatei nicht gespeichert",
        "The export run has no stored content (written before migration 0190); the formal "
        "check needs the exact file. Create the export again (M18-01).",
    )
    CHART_TEMPLATE_NOT_DRAFT = ErrorCode(
        "MHVP-BILL-0010",
        409,
        "Kontenrahmen ist nicht im Entwurf",
        "Accounts of a template in review or released cannot be changed; create a new "
        "version instead (M10-01, V8).",
    )
    BILLING_LEITWEG_ID_MISSING = ErrorCode(
        "MHVP-BILL-0005",
        409,
        "Leitweg-ID fehlt",
        "TenantBillingSettings.leitweg_id is empty; XRechnung needs BT-10 BuyerReference (A12).",
    )
    BILLING_PAYEE_IBAN_MISSING = ErrorCode(
        "MHVP-BILL-0007",
        409,
        "Zahlungskonto fehlt",
        "TenantBillingSettings.payee_iban is empty; XRechnung needs BT-84 for a credit transfer.",
    )
    XRECHNUNG_NOT_ISSUED = ErrorCode(
        "MHVP-BILL-0006",
        409,
        "XRechnung nur für ausgestellte Rechnungen",
        "XRechnung XML is generated only for issued or released outgoing invoices (A12).",
    )
    RENT_INVOICE_NOT_ALLOWED = ErrorCode(
        "MHVP-BILL-0011",
        409,
        "Mietrechnung nicht möglich",
        "Contract without VAT option or receivable items without a released VAT split "
        "(rule M13-04, Mietrechnung).",
    )
    RENT_INVOICE_TAX_ID_MISSING = ErrorCode(
        "MHVP-BILL-0012",
        409,
        "Steuernummer oder USt-IdNr. des Rechtsträgers fehlt",
        "The legal entity has neither a tax number nor a VAT id in the master data; the "
        "rent invoice is not issued (rule M13-04, Mietrechnung).",
    )
    RENT_INVOICE_NO_ITEMS = ErrorCode(
        "MHVP-BILL-0013",
        409,
        "Keine Sollstellungsposten im Zeitraum",
        "No posted or ready receivable items of the contract in the period.",
    )
    RENT_INVOICE_CANCELLED = ErrorCode(
        "MHVP-BILL-0014",
        409,
        "Rechnung bereits storniert",
        "The rent invoice is already cancelled by a credit note, or is a credit note itself.",
    )
    # Messdienstleister module (stage 1).
    METERING_MODULE_DISABLED = ErrorCode(
        "MHVP-METR-0001",
        403,
        "Messdienstleister-Modul nicht freigeschaltet",
        "tenant_settings.metering_module_enabled is false; write endpoints are locked.",
    )
    METERING_ASSIGNMENT_CONFLICT = ErrorCode(
        "MHVP-METR-0002",
        409,
        "Widersprüchliche Zuordnung",
        "Another assignment covers the same units, service scope and period.",
    )
    METERING_VERSION_CONFLICT = ErrorCode(
        "MHVP-METR-0003",
        409,
        "Datensatz wurde zwischenzeitlich geändert",
        "Optimistic lock: the given version is not the current version.",
    )
    METERING_CAPABILITY_MISSING = ErrorCode(
        "MHVP-METR-0004",
        409,
        "Funktion beim Anbieter nicht freigegeben oder nicht implementiert",
        "documented_support, adapter_implemented and account_release must all be true.",
    )
    METERING_CREDENTIALS_MISSING = ErrorCode(
        "MHVP-METR-0005",
        422,
        "Zugangsdaten fehlen",
        "The adapter requires secrets that are not set on the connection.",
    )
    METERING_CONFLICT_BLOCKS_WRITE = ErrorCode(
        "MHVP-METR-0006",
        409,
        "Zuordnung im Konflikt, schreibender Vorgang gesperrt",
        "Assignments in status conflict block sync and submission until resolved.",
    )
    METERING_IMPORT_INVALID = ErrorCode(
        "MHVP-METR-0007",
        422,
        "Import enthält Fehler",
        "CSV import preview reported row errors; apply is refused.",
    )
    METERING_SYNC_ALREADY_RUNNING = ErrorCode(
        "MHVP-METR-0008",
        409,
        "Abruf läuft bereits",
        "A queued or running sync job with the same connection, data kind and scope exists.",
    )
    METERING_PROVIDER_UNKNOWN = ErrorCode(
        "MHVP-METR-0009",
        422,
        "Unbekannter Anbieter",
        "provider_code is not in the provider catalogue.",
    )
    METERING_CONNECTION_PAUSED = ErrorCode(
        "MHVP-METR-0010",
        409,
        "Verbindung pausiert",
        "The connection is paused; no test and no sync until it is active again.",
    )
    # Controlled write workflows (section 12).
    METERING_TRANSMISSION_STATE = ErrorCode(
        "MHVP-METR-0011",
        409,
        "Übermittlung in diesem Status nicht möglich",
        "The transmission is not in the status required for this step (check, release, order).",
    )
    METERING_RELEASE_INVALIDATED = ErrorCode(
        "MHVP-METR-0012",
        409,
        "Freigabe entwertet, Daten erneut prüfen",
        "The checked payload or a relevant assignment changed; the fingerprint no longer matches.",
    )
    METERING_WARNINGS_UNACKNOWLEDGED = ErrorCode(
        "MHVP-METR-0013",
        422,
        "Warnungen wurden nicht bestätigt",
        "Provider or local warnings must be acknowledged explicitly before the release.",
    )
    # Objekte: Beendigung des Verwaltungsverhältnisses (operator 27.09.2026).
    PROPERTY_NOT_TERMINABLE = ErrorCode(
        "MHVP-PROP-0001",
        409,
        "Objekt ist bereits deaktiviert",
        "Only properties in status onboarding or active can be terminated.",
    )
    PROPERTY_NOT_TERMINATED = ErrorCode(
        "MHVP-PROP-0002",
        409,
        "Objekt ist nicht deaktiviert",
        "Reactivation requires a property in status terminated with an open termination.",
    )
    PROPERTY_REACTIVATE_SUPERADMIN_ONLY = ErrorCode(
        "MHVP-PROP-0003",
        403,
        "Wieder aktivieren nur durch den Superadmin",
        "Reactivating a terminated property is reserved to the superadmin (ADR 0011).",
    )
    PROPERTY_TERMINATION_DATES = ErrorCode(
        "MHVP-PROP-0004",
        422,
        "Verwaltungsende liegt vor dem Kündigungsdatum",
        "effective_date must not be before notice_date.",
    )
    # Verträge: Eigentümerwechsel in der Oberfläche (operator 28.09.2026, D16, D17).
    CONTRACT_OWNERSHIP_TRANSFER_INVALID = ErrorCode(
        "MHVP-CONTR-0001",
        422,
        "Eigentümerwechsel nicht möglich",
        "Only an open ownership can be transferred, and not to its current owner.",
    )
    # Stammdaten in der Oberfläche (C2, 28.09.2026): maintenance completion.
    PROPERTY_MAINTENANCE_ALREADY_DONE = ErrorCode(
        "MHVP-PROP-0005",
        409,
        "Wartung ist bereits erledigt",
        "A maintenance item without interval that is already done cannot be completed again.",
    )
    # lexoffice (M13-lexoffice, docs/integrations/lexoffice.md).
    LEXOFFICE_NOT_CONFIGURED = ErrorCode(
        "MHVP-LEXO-0001",
        502,
        "lexoffice ist für diesen Mandanten nicht eingerichtet",
        "No LexofficeTenantConfig with an API key for this tenant, or the feature flag is off.",
    )
    LEXOFFICE_UNAVAILABLE = ErrorCode(
        "MHVP-LEXO-0002",
        503,
        "lexoffice nicht erreichbar",
        "Request to the lexoffice public REST API failed or was rejected.",
    )
    LEXOFFICE_AUTH = ErrorCode(
        "MHVP-LEXO-0003",
        502,
        "lexoffice-Zugangsdaten abgelehnt",
        "lexoffice answered 401/403: the stored API key was rejected.",
    )
    LEXOFFICE_RATE_LIMITED = ErrorCode(
        "MHVP-LEXO-0004",
        503,
        "lexoffice-Anfragelimit erreicht",
        "lexoffice answered 429 (rate limit, 2 req/s documented). Not retried automatically.",
    )
    LEXOFFICE_GATE_CLOSED = ErrorCode(
        "MHVP-LEXO-0005",
        403,
        "lexoffice-Export ist für diesen Mandanten gesperrt",
        (
            "Export to lexoffice needs release gate G1 (productive bookkeeping) open and the "
            "lexoffice feature flag enabled for the tenant; both default closed/off."
        ),
    )
    # Lexware Office extension (rule INT-LEXO-01, docs/integrations/lexoffice.md).
    LEXOFFICE_AVV_MISSING = ErrorCode(
        "MHVP-LEXO-0006",
        422,
        "Auftragsverarbeitungsvertrag nicht bestätigt",
        "A Lexware Office config can only be enabled after the AVV date and member are recorded.",
    )
    LEXOFFICE_FORBIDDEN_FIELD = ErrorCode(
        "MHVP-LEXO-0007",
        422,
        "Feld darf nicht übertragen werden",
        "A payload would change a bank, mandate or tax field; those never leave the platform.",
    )
    LEXOFFICE_CONTACT_NOT_LINKED = ErrorCode(
        "MHVP-LEXO-0008",
        409,
        "Kontakt ist nicht mit Lexware Office verknüpft",
        "The action needs a contact link in a synced state for this config.",
    )
    LEXOFFICE_RECIPIENT_UNVERIFIED = ErrorCode(
        "MHVP-LEXO-0009",
        422,
        "Rechnungsempfänger nicht bestätigt",
        "The requester is not the invoice recipient or the recipient could not be resolved.",
    )
    LEXOFFICE_REMOTE_CONFLICT = ErrorCode(
        "MHVP-LEXO-0010",
        409,
        "Datensatz in Lexware Office zwischenzeitlich geändert",
        "The remote contact changed since the baseline; resolve keep_crm or keep_lexoffice.",
    )
    LEXOFFICE_MANUAL_REQUIRED = ErrorCode(
        "MHVP-LEXO-0011",
        409,
        "Manuelle Pflege in Lexware Office erforderlich",
        "Multi entry lists, kind change or archived contact: the platform never writes here.",
    )
    LEXOFFICE_INVOICE_NOT_FOUND = ErrorCode(
        "MHVP-LEXO-0012",
        404,
        "Rechnung in Lexware Office nicht gefunden",
        "No finalized invoice with this voucher number in the configured organisation.",
    )
    LEXOFFICE_ORGANIZATION_MISMATCH = ErrorCode(
        "MHVP-LEXO-0013",
        409,
        "API Schlüssel gehört zu einer anderen Lexware Organisation",
        "The organisation id returned by Lexware differs from the one stored on the config.",
    )
    LEXOFFICE_CONNECTION_TEST_REQUIRED = ErrorCode(
        "MHVP-LEXO-0014",
        422,
        "Verbindungstest vor Aktivierung erforderlich",
        "Enable needs a successful connection test with the current API key.",
    )
    LEXOFFICE_DRAFT_RECIPIENT_LOCKED = ErrorCode(
        "MHVP-LEXO-0015",
        422,
        "Empfänger eines Entwurfs mit Rechnungskopie kann nicht geändert werden",
        "Recipients of a draft carrying a Lexware invoice file are locked to the contact.",
    )
    LEXOFFICE_FEATURE_DISABLED = ErrorCode(
        "MHVP-LEXO-0016",
        403,
        "Funktion für diese Lexware Organisation nicht aktiviert",
        "The feature switch (sync_contacts, invoice_copies, invoice_drafts) is off.",
    )
    LEXOFFICE_KIND_UNMAPPED = ErrorCode(
        "MHVP-LEXO-0017",
        422,
        "Rechnungsart ist keiner Gesellschaft zugeordnet",
        (
            "The invoice kind (broker, consulting, management) has no legal entity mapping, or "
            "the mapped legal entity has no Lexware Office config (settings UI)."
        ),
    )
    # Claims adjuster (Schadenstool, rule INT-SDT-01, docs/integrations/schadenstool.md).
    SCHADENSTOOL_NOT_ENABLED = ErrorCode(
        "MHVP-SDT-0001",
        409,
        "Anbindung an den Schadenbearbeiter ist nicht aktiv",
        "No SchadenstoolTenantConfig with base URL and token, or the feature flag is off.",
    )
    SCHADENSTOOL_UNAVAILABLE = ErrorCode(
        "MHVP-SDT-0002",
        503,
        "Schadenbearbeiter nicht erreichbar",
        "Request to the claims adjuster API timed out, failed or answered 5xx.",
    )
    SCHADENSTOOL_AUTH = ErrorCode(
        "MHVP-SDT-0003",
        502,
        "Token ungültig",
        "The claims adjuster answered 401/403: the stored integration token was rejected.",
    )
    SCHADENSTOOL_RATE_LIMITED = ErrorCode(
        "MHVP-SDT-0004",
        503,
        "Anfragelimit des Schadenbearbeiters erreicht",
        "The claims adjuster answered 429; Retry-After is honoured by the outbound queue.",
    )
    SCHADENSTOOL_AVV_MISSING = ErrorCode(
        "MHVP-SDT-0005",
        422,
        "Auftragsverarbeitungsvertrag nicht bestätigt",
        (
            "Enabling the claims adjuster link requires the AVV confirmation (date and "
            "confirming member) to be recorded first (rule 0.1.13, INT-SDT-01)."
        ),
    )
    SCHADENSTOOL_REJECTED = ErrorCode(
        "MHVP-SDT-0006",
        502,
        "Schadenbearbeiter hat die Anfrage abgelehnt",
        "The claims adjuster answered with a 4xx other than 401/403/429.",
    )
    # BrokerProvider (M28-01 stage 3, mhvp.letting.broker_provider).
    BROKER_NOT_CONFIGURED = ErrorCode(
        "MHVP-BRKR-0001",
        502,
        "Makler-Anbindung ist für diesen Mandanten nicht eingerichtet",
        "No enabled BrokerTenantConfig with credentials for this tenant/provider.",
    )
    BROKER_DOCUMENTATION_REQUIRED = ErrorCode(
        "MHVP-BRKR-0002",
        501,
        "Für diese Operation liegt keine belegte Schnittstellendokumentation vor",
        (
            "BrokerProvider raised DocumentationRequiredError: no verified public endpoint "
            "contract for this operation/provider (rule 0.1.3)."
        ),
    )
    # Deadline types and entries (rule WS-01, mhvp.workspace.deadlines).
    DEADLINE_DURATION_MISSING = ErrorCode(
        "MHVP-WS-0001",
        422,
        "Fristtyp ohne Dauer, Fälligkeit bitte eintragen",
        (
            "The deadline type carries no duration (operator has not entered one, no default "
            "exists); the due date must be entered explicitly."
        ),
    )
    DEADLINE_TYPE_INACTIVE = ErrorCode(
        "MHVP-WS-0002",
        422,
        "Fristtyp ist deaktiviert",
        "The deadline type is inactive; activate it in the catalogue first.",
    )
    CHECKLIST_ALREADY_OPEN = ErrorCode(
        "MHVP-WS-0003",
        409,
        "Für dieses Objekt ist bereits eine Checkliste dieser Art offen",
        "An open property checklist of this kind exists; finish it before starting another.",
    )
    # Übergabeprotokoll (M30, Package F): Zählerstände in die Stammdaten übernehmen.
    HANDOVER_TRANSFER_NOT_CONFIRMED = ErrorCode(
        "MHVP-HDOV-0001",
        422,
        "Übernahme der Zählerstände nicht bestätigt",
        "POST .../meters/transfer needs confirm=true; the takeover creates meter readings.",
    )
    HANDOVER_TRANSFER_NOTHING = ErrorCode(
        "MHVP-HDOV-0002",
        409,
        "Keine Zählerstände übernehmbar",
        (
            "No protocol meter could be matched to a meter of the unit or property, or every "
            "matched row was already taken over; nothing was created."
        ),
    )
    # M20-04 Vier-Augen-Prinzip beim Mailversand (mhvp.communication.mail_approval).
    MAIL_APPROVAL_FOUR_EYES = ErrorCode(
        "MHVP-COMM-0001",
        409,
        "Freigabe durch eine zweite Person erforderlich",
        (
            "Mail approval needs a second, different user identity than the draft's author; "
            "a superadmin bypass exists only behind the gate_superadmin_bypass platform flag "
            "(ADR 0011)."
        ),
    )
    MAIL_APPROVAL_REAUTH_REQUIRED = ErrorCode(
        "MHVP-COMM-0002",
        401,
        "Re-Authentifizierung erforderlich",
        (
            "Mail approval needs a fresh password or TOTP confirmation, valid for 5 minutes "
            "(mhvp.communication.mail_approval.REAUTH_WINDOW)."
        ),
    )
    # Zuordnungsprüfung mit Rückfrage (review 1.36.0, mhvp.communication.assignment_review).
    ASSIGNMENT_CHANGED = ErrorCode(
        "MHVP-COMM-0003",
        409,
        "Zuordnung inzwischen geändert",
        (
            "The assignment decision refers to an outdated view: the field no longer holds "
            "seen_value or the value the row was computed against, the row is already accepted, "
            "or candidate_id is not among the current candidates. Nothing was written; reload "
            "the review and decide again."
        ),
    )
    # Google Kalender (M23-02, hotfix 28.09.2026, mhvp.communication.gcal error kinds).
    GOOGLE_CALENDAR_RECONNECT = ErrorCode(
        "MHVP-COMM-0004",
        409,
        "Google-Kalender neu verbinden",
        (
            "The Google grant of the mailbox no longer works: the token endpoint refused the "
            "refresh token (expired or revoked), the Calendar API answered 401 after the retry "
            "or 403 without a rate limit reason (missing calendar scope), the configured "
            "calendar is not visible to the account, or no refresh token is stored. Reconnect "
            "the mailbox under Einstellungen, Postfächer. Never 401: that is the session's code."
        ),
    )
    GOOGLE_CALENDAR_UNAVAILABLE = ErrorCode(
        "MHVP-COMM-0005",
        502,
        "Kalender nicht erreichbar",
        (
            "Google Calendar answered with a rate limit (429, 403 rateLimitExceeded, "
            "userRateLimitExceeded, quotaExceeded) or a server error, or could not be reached "
            "at all. Transient: retry later, the stored grant is not affected."
        ),
    )
    # Rückkanal Gmail zu Plattform (rule M20-08, mhvp.communication.gmail_state).
    GMAIL_RESTORE_DISABLED = ErrorCode(
        "MHVP-COMM-0006",
        422,
        "Zurücklegen in den Gmail Posteingang ist aus",
        (
            "tenant_settings.gmail_restore_inbox_on_reopen is false: the platform never adds "
            "the INBOX label back. Switch it on under Mandant, Erledigt aus Gmail first."
        ),
    )
    GMAIL_SPIKE_NOT_CONFIRMED = ErrorCode(
        "MHVP-COMM-0007",
        422,
        "Modus Übernehmen braucht den bestätigten Spike",
        (
            "gmail_done_sync_mode may be set to done only after POST /tenant/settings/"
            "gmail-spike-confirm recorded the protocol of the Gmail behaviour test "
            "(docs/integrations/gmail.md, section Spike)."
        ),
    )
    RECONCILE_RUNNING = ErrorCode(
        "MHVP-COMM-0008",
        409,
        "Abgleich läuft bereits",
        "A reconcile of this mailbox is queued or running; wait for its result.",
    )
    GMAIL_REVERT_NOT_APPLICABLE = ErrorCode(
        "MHVP-COMM-0009",
        422,
        "Keine automatische Entscheidung vorhanden",
        (
            "The mail was not completed by the Gmail back channel (done_source is not gmail) "
            "and its ticket was not closed by it; there is nothing to revert."
        ),
    )
    # Lern-Workflow, rule proposals (rule M9-11, mhvp.automation.learning).
    RULE_PROPOSAL_NOT_OPEN = ErrorCode(
        "MHVP-AUTO-0001",
        409,
        "Regelvorschlag bereits entschieden",
        (
            "The rule proposal is no longer in status proposed (accepted, rejected or withdrawn "
            "meanwhile). Nothing was written; reload the proposals."
        ),
    )
    RULE_PROPOSAL_STALE = ErrorCode(
        "MHVP-AUTO-0002",
        409,
        "Regelvorschlag nicht mehr belegt",
        (
            "Recomputing the evidence from the decision log no longer confirms the proposal "
            "(contradicting decision, threshold not reached, or the target record is gone). "
            "No rule was created."
        ),
    )
    # WEG circular resolution with a lowered majority (M25-02).
    HOA_CIRCULAR_LOWER_MAJORITY_DISABLED = ErrorCode(
        "MHVP-HOA-0001",
        403,
        "Umlaufbeschluss mit einfacher Mehrheit ist für diesen Mandanten nicht freigeschaltet",
        "tenant_settings.hoa_circular_lower_majority_enabled is false (default off).",
    )
    HOA_CIRCULAR_ENABLING_RESOLUTION = ErrorCode(
        "MHVP-HOA-0002",
        422,
        "Umlaufbeschluss mit einfacher Mehrheit braucht einen zulassenden Beschluss",
        (
            "A positive prior resolution of the same community that admits the lower majority "
            "for this subject is required (M25-02)."
        ),
    )
    # WEG virtual meeting (M25-03, V13).
    HOA_VIRTUAL_MEETINGS_DISABLED = ErrorCode(
        "MHVP-HOA-0003",
        403,
        "Virtuelle Versammlungen sind für diesen Mandanten nicht freigeschaltet",
        "tenant_settings.hoa_virtual_meetings_enabled is false (default off, V13).",
    )
    HOA_VIRTUAL_BASIS_RESOLUTION = ErrorCode(
        "MHVP-HOA-0004",
        422,
        "Virtuelle Versammlung braucht einen zulassenden Beschluss mit Gültigkeitsende",
        (
            "A positive, final or legally binding resolution of the same community that admits "
            "virtual meetings, with a validity end on or after the meeting day (M25-03)."
        ),
    )
    # Bankverbindungen am Kontakt (CRM screen, M5-01 addendum 28.09.2026).
    CONTACT_BANK_ACCOUNT_ENDED = ErrorCode(
        "MHVP-CONT-0001",
        409,
        "Bankverbindung ist bereits beendet",
        "The bank account already has a valid_to in the past or is rejected; it cannot be "
        "changed or ended again.",
    )
    CONTACT_BANK_CHANGE_PENDING = ErrorCode(
        "MHVP-CONT-0002",
        409,
        "Für diese Bankverbindung wartet bereits eine Änderung auf Freigabe",
        "A replacement or an end request of this bank account is still pending; decide it first.",
    )
    CONTACT_BANK_ACCOUNT_DUPLICATE = ErrorCode(
        "MHVP-CONT-0003",
        409,
        "Diese IBAN ist beim Kontakt bereits hinterlegt",
        "An account with the same IBAN fingerprint already exists on this contact.",
    )


def _build_registry() -> dict[str, ErrorCode]:
    registry: dict[str, ErrorCode] = {}
    for value in vars(ErrorCodes).values():
        if isinstance(value, ErrorCode):
            if not CODE_PATTERN.fullmatch(value.code):
                raise ValueError(f"invalid error code format: {value.code}")
            if value.code in registry:
                raise ValueError(f"duplicate error code: {value.code}")
            registry[value.code] = value
    return registry


REGISTRY: dict[str, ErrorCode] = _build_registry()


class FieldError(BaseModel):
    location: list[str | int]
    field: str
    code: str
    message: str


class Problem(BaseModel):
    """Response schema of every error (documented in OpenAPI)."""

    type: str = Field(examples=["urn:mhvp:problem:MHVP-CORE-0002"])
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str
    developer_message: str
    correlation_id: str | None = None
    errors: list[FieldError] | None = None


class ProblemError(Exception):
    """Raise to answer with a registered problem."""

    def __init__(
        self,
        error: ErrorCode,
        *,
        detail: str | None = None,
        developer_message: str | None = None,
        errors: list[FieldError] | None = None,
        extensions: dict[str, Any] | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(developer_message or error.developer_message)
        self.error = error
        self.detail = detail
        self.developer_message = developer_message or error.developer_message
        self.errors = errors
        self.extensions = extensions or {}
        self.status = status or error.status


def problem_response(
    error: ErrorCode,
    *,
    instance: str | None,
    status: int | None = None,
    detail: str | None = None,
    developer_message: str | None = None,
    errors: list[FieldError] | None = None,
    extensions: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    problem = Problem(
        type=error.type_uri,
        title=error.title,
        status=status or error.status,
        detail=detail,
        instance=instance,
        code=error.code,
        developer_message=developer_message or error.developer_message,
        correlation_id=get_correlation_id(),
        errors=errors,
    )
    body = problem.model_dump(mode="json", exclude_none=True)
    for key, value in (extensions or {}).items():
        body.setdefault(key, value)
    return JSONResponse(
        body, status_code=problem.status, media_type=PROBLEM_CONTENT_TYPE, headers=headers
    )


_VALIDATION_MESSAGES = {
    "missing": "Pflichtangabe fehlt.",
    "extra_forbidden": "Angabe ist nicht zulässig.",
}


def _field_errors(exc: RequestValidationError) -> list[FieldError]:
    errors: list[FieldError] = []
    for item in exc.errors():
        location = [part if isinstance(part, int) else str(part) for part in item.get("loc", ())]
        error_type = str(item.get("type", "value_error"))
        # The submitted value ("input") is deliberately not echoed: it may contain personal data.
        errors.append(
            FieldError(
                location=location,
                field=str(location[-1]) if location else "",
                code=error_type,
                message=_VALIDATION_MESSAGES.get(error_type, "Wert ist ungültig."),
            )
        )
    return errors


async def _handle_problem(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ProblemError):  # pragma: no cover - registered per type
        raise exc
    return problem_response(
        exc.error,
        instance=request.url.path,
        status=exc.status,
        detail=exc.detail,
        developer_message=exc.developer_message,
        errors=exc.errors,
        extensions=exc.extensions,
    )


async def _handle_validation(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - registered per type
        raise exc
    return problem_response(
        ErrorCodes.VALIDATION,
        instance=request.url.path,
        detail="Bitte die markierten Angaben prüfen.",
        errors=_field_errors(exc),
    )


async def _handle_http(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover - registered per type
        raise exc
    headers = dict(exc.headers) if exc.headers else None
    if exc.status_code == 404:
        return problem_response(ErrorCodes.NOT_FOUND, instance=request.url.path, headers=headers)
    if exc.status_code == 405:
        return problem_response(
            ErrorCodes.METHOD_NOT_ALLOWED, instance=request.url.path, headers=headers
        )
    return problem_response(
        ErrorCodes.HTTP_ERROR,
        instance=request.url.path,
        status=exc.status_code,
        headers=headers,
    )


def install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProblemError, _handle_problem)
    app.add_exception_handler(RequestValidationError, _handle_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http)


def body_validation_error(exc: PydanticValidationError) -> RequestValidationError:
    """Turns a pydantic error raised inside a handler (e.g. validating a merged partial update
    against the full schema) into the same 422 problem a request body error produces."""
    return RequestValidationError(
        [{**item, "loc": ("body", *item.get("loc", ()))} for item in exc.errors()]
    )
