# M-lexoffice: Lexware Office Erweiterung

Betreiberauftrag 28.09.2026 (Spezifikation im Arbeitsbereich, Betreiberentscheidungen 1 bis 4
vom 28.09.2026). Regel INT-LEXO-01, ADR 0015, Betreiberdoku docs/integrations/lexoffice.md.

## Umfang

| Stufe | Inhalt | Dateien | Stand |
| --- | --- | --- | --- |
| A | Migration 0233 (Konfiguration je Gesellschaft, AVV, Profil, Rechnungsartzuordnung, Verknüpfungen, Warteschlange, Entwürfe, Rechnungskopien, Dauerrechnungen), asynchroner Client, Anfragelimit, Verbindungstest mit Organisationsbindung, Warteschlange und Worker, Einstellungsseite | `apps/api/alembic/versions/0233_lexoffice_extension.py`, `mhvp/integrations/models.py`, `lexoffice_async.py`, `lexoffice_ext/{services,ratelimit,tasks,routers,schemas}.py`, `apps/web-crm/.../lexware-office`, `LexofficeSettings.tsx`, `LexofficeOutbox.tsx` | umgesetzt 29.09.2026 |
| B | Kontaktverknüpfungen, Abgleichslauf, Prüfliste, Hook nach angewandter Änderung, Konflikte | `lexoffice_ext/{payloads,sync,matching}.py`, `contacts/routers.py`, `tickets/proposals.py`, `LexofficeContactLinks.tsx` | umgesetzt 29.09.2026 |
| C | Erkennung der Rechnungskopie im Postfach, Anfrage am Ticket, Suche, Prüfung des Empfängers, Abruf, Antwortentwurf mit gesperrtem Empfänger | `communication/mail.py`, `lexoffice_ext/invoice_copy.py`, `communication/routers.py` (Sperre) | Backend umgesetzt 29.09.2026; Ticketkarte im CRM offen |
| D | Rechnungsentwürfe je Rechnungsart, Dauerrechnungen vorbereiten | `lexoffice_ext/invoice_drafts.py`, `accounting/routers.py` (Hook), `LexofficeRecurringPreps.tsx` | Backend und Reiter umgesetzt; Formular für Entwürfe im CRM offen |

## Tests

`apps/api/tests/unit/test_lexoffice_async_client.py`, `test_lexoffice_payloads.py`,
`test_lexoffice_matching.py`, `test_lexoffice_ratelimit.py`, `test_mail_invoice_copy.py`,
`apps/api/tests/integration/test_lexoffice_ext.py` (Fake Server `tests/lexoffice_fake.py`),
`apps/web-crm/src/components/settings/Lexoffice*.test.tsx`, BFF Abdeckung in `route.test.ts`.
Nicht ausgeführt: Aufrufe gegen die echte API (docs/acceptance/lexoffice.md, LEXO-13),
Playwright für die neue Seite.

## Offene Punkte

docs/OPEN_QUESTIONS.md LEXO-04 bis LEXO-16; Ticketkarte für Rechnungskopien und das Formular
für Rechnungsentwürfe im CRM (API vorhanden); Erweiterung des KI Prompts `classify_email`
um `intent` und `invoice_number` (deterministische Erkennung ist umgesetzt).
