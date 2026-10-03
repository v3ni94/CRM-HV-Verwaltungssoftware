# Datenschutz (`mhvp.privacy`)

Abschnitt 16 und 7.11 S06 des Master-Prompts. Regeln: `docs/rules/S16-P17-privacy.md`
(Löschprofile, Löschantrag, Register) und `docs/rules/S711-10.md` (Verzeichnis, Anbieter aus der
Konfiguration). Handbuch: `docs/handbuch/datenschutz.md`.

- `models.py`: `privacy_register_entry` (Auftragsverarbeiter, Unterauftragnehmer,
  Verarbeitungstätigkeiten, Verantwortlichkeiten), `privacy_deletion_profile`,
  `privacy_erasure_request`. Migration 0266, Pflegefelder Migration 0388.
- `erasure.py`: Sperrprüfung, Vier-Augen-Freigabe und Anonymisierung eines Kontakts.
- `config_sources.py` (AE32): erkennt aus den Plattformeinstellungen (`Settings`) und den
  Konnektortabellen des Mandanten (unter RLS) die tatsächlich genutzten externen Dienste: Gmail,
  Google Kalender, IMAP/SMTP-Hosts, Google Drive, Paperless-ngx, finAPI, GoCardless,
  KI-Anbieter, Postversand (LetterXpress), WhatsApp, SMS-Gateway, Telefonanlage, Lexware Office,
  Objektspeicher, objektakte, Tracing. Ausgegeben werden nur technische Angaben (Host, Modus,
  Anzahl, aktiv), nie Zugangsdaten oder Postfachadressen. `sync` legt fehlende Dienste als
  Unterauftragnehmer an (AVV `none`, Drittland `open`, Prüfung `open`, `source_key`) und
  aktualisiert bei bestehenden Einträgen nur `source_detail`. Weitere Konnektoren werden in
  `DETECTORS` ergänzt.
- `register_doc.py`: baut das Verzeichnis als Blockstruktur und druckt sie als Markdown
  (`render`) und PDF (`render_pdf`, reportlab). Rollen von GdWE, Verwalter und Betreiber je
  Tätigkeit, Rechtsgrundlage und Drittland erscheinen wie eingetragen, leer als "offen"; offene
  Punkte werden gesammelt. Der Prüfhinweis V13 ist fester Bestandteil.
- `routers.py`: `/api/v1/privacy/*` mit `privacy:read`, `privacy:manage`, `privacy:approve`.
  Neu (AE32): `GET /privacy/register/config-sources`, `POST
  /privacy/register/config-sources/sync`, `GET /privacy/processing-records/pdf`; Registereinträge
  mit `third_country_status`, `third_country_countries`, `legal_basis`, `responsibilities`,
  `responsibility_note`, `processor_ids`.

Keine Rechtsaussage im Code: die Plattform belegt weder Rollen noch Rechtsgrundlagen noch
Drittlandangaben vor. Die operative Rechtsgrundlage für Einwilligungsprüfungen liegt im Register
`/consent-legal-basis` (AE34); `legal_basis` im Verzeichnis ist eine Dokumentationsangabe.

## Erkannte Dienste, Stand 02.10.2026 (GAE-34, AF22)

Zusätzliche Detektoren in `config_sources.py`: Schadenstool, Makler-CRM (je Anbieter),
Webhook-Ziele (je Zielhost, ohne Secret), EBICS und FinTS Bankzugänge. Die Liste
`GET /privacy/register/config-sources` zeigt je Dienst lesend die Rechtsgrundlage der betroffenen
Einwilligungszwecke (`consent_purposes`, `consent_basis` aus `/consent-legal-basis`) und den Text
`legal_basis` des Registereintrags. Das ist eine Anzeige, keine Rechtsfeststellung; der Status als
Auftragsverarbeiter bleibt Pflegefeld.

## Löschvorschläge je Datenart (AJ12, GAI-501 bis GAI-504, GAI-522)

`mhvp.privacy.proposals` (Beat `privacy-deletion-proposals`, täglich 04:25) erzeugt nur Vorschläge: Kontakte mit abgelaufenem Löschdatum erhalten einen Antrag im Status `proposed`, wenn das Kontaktprofil freigegeben ist und `auto_propose` (Migration 0445, Standard aus) eingeschaltet ist. Übernahme per `POST /privacy/erasure-requests/{id}/accept` (erste Person), Freigabe wie bisher durch eine zweite Person. Andere Datenarten (Kommunikation, Tickets, Portalzugänge, `domain_event`) werden nur gezählt (`GET /privacy/deletion-proposals`); `platform_user` und `bank_raw` sind nur dokumentierbar. Sitzungsmetadaten bereinigt `mhvp.core.auth.session_purge`. Regel: docs/rules/AJ12-loeschvorschlaege.md.

## Oversight (AJ13, GAI-506 to GAI-510, GAI-414)

`routers_oversight.py`: `GET /privacy/consent-overview` (consent counts per purpose),
`GET|PUT /privacy/request-deadlines` (response periods in `tenant_settings.sources`
`privacy_request_deadlines`, no default value, AJ13-01), `GET /privacy/request-deadlines/monitor`
(open erasure requests with warn and due date; access requests need an intake table, AJ13-03),
`GET /privacy/register/readiness` (pre G1 list of services without settled entry; informative,
opens no gate, AJ13-02). `config_sources` additionally detects OIDC relying parties, ClamAV,
`BACKUP_REMOTE` and `ALERT_WEBHOOK_URL`. Rule: docs/rules/AJ13-datenschutzaufsicht.md.

## Access requests (AK06, GAI-506, GAI-507, migration 0448)

`access_requests.py`: `GET|POST /privacy/access-requests`, `GET /privacy/access-requests/{id}`,
`POST /privacy/access-requests/{id}/status` (intake record with receipt date, channel and status;
closed requests stay). Due date only from `privacy_request_deadlines.access_days` (no default,
AJ13-01); with a period the open request is mirrored into `compliance_deadline` (kind
`privacy_access_request`, source reader in `workspace.jobs.calendar_sources`) and shown in
`/privacy/request-deadlines/monitor`. The access export (`contacts.access_export`) adds portal
account with login events and sessions, payment data and contract data behind the tenant
switches `include_portal_account`, `include_payments`, `include_contracts` (default off, counts
only). Rule: docs/rules/AK06-auskunftsantraege.md.
