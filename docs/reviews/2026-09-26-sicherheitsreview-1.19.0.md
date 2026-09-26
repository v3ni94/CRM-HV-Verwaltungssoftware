# Sicherheits- und Korrektheitsreview 1.19.0, Stand 26.09.2026

Prüfumfang: die mit Version 1.19.0 hinzugekommenen Endpunkte und Module
(`git diff 52d6498..6071d61 --stat`, Branch `claude/funny-cerf-ppg9in`): Antwortvorlagen und
Ticketantwort (`tickets/reply_templates.py`, `tickets/routers.py`), Stammdatenvorschläge
(`tickets/proposals.py`), Mailanhänge (`communication/attachments.py`), Belegeingang
(`receipts/*`), Bankkontenauswahl (`banking/account_selection.py`, neue Endpunkte in
`banking/routers.py` und `properties/routers.py`), Mahnschreiben (`accounting/dunning_letters.py`,
Dunning-Endpunkte), OpenImmo-Export (`letting/openimmo.py`, `letting/routers.py`),
objektakte-Listen, KI-Aufrufprotokoll und Differenzimport (`objektakte/lists*.py`,
`objektakte/ai_call_routers.py`, `objektakte/tasks.py`, `objektakte/routers.py`), CLI-Importe
(`imports/objektdaten.py`, `imports/kontakte.py`) und die Fehlerdurchreichung der KI-Anbieter
(`ai/providers.py`, `ai/gateway.py`).

Prüfkriterien: Berechtigungen je Endpunkt, Mandantentrennung, IDOR, Geldregeln (keine Buchung,
keine Zahlung, keine automatische IBAN-Übernahme, Gates G1/G2), Datenschutz (IBAN, Schlüssel,
Klartext in Logs, Fehlermeldungen, an den KI-Anbieter), Pfad- und Dateiprüfungen, Injection,
Vier-Augen-Prinzip beim Versand, Rate- und Größenlimits.

Dies ist ein Review, keine Freigabe. Befunde mit Schweregrad hoch und mittel wurden direkt
minimal behoben und getestet, niedrige zunächst nur dokumentiert; die Befunde 3 bis 8 wurden
im Nachgang am 26.09.2026 ebenfalls behoben (siehe unten). Nichts wurde committet; VERSION,
CHANGELOG.md und changelog.ts sind unverändert (Festlegung des Auftrags, parallele Agenten im
selben Arbeitsbaum).

## Befunde

| Nr. | Bereich | Befund | Schweregrad | Status | Datei |
| --- | --- | --- | --- | --- | --- |
| 1 | objektakte Differenzimport | `PUT /objektakte/sync` nahm jeden absoluten `.sql`-Pfad an; der Worker las die Datei mit `read_dump_file` und importierte sie in den Mandanten. Ein Mandantenadministrator konnte so den Export eines anderen Mandanten (oder jede andere `.sql`-Datei auf dem Worker, auch per Symlink) in den eigenen Mandanten übernehmen. Mandantentrennung über die Infrastruktur unterlaufen, kein Zugriff ohne `tenant_settings:update`. | mittel | behoben | `apps/api/src/mhvp/objektakte/tasks.py:39-64`, `apps/api/src/mhvp/objektakte/routers.py:226-233`, `apps/api/src/mhvp/core/config.py:64-67` |
| 2 | Belegeingang, Paperless | `POST /receipts/drafts/paperless` lud das Paperless-Dokument ohne Größenprüfung (`fetch_file` liest `response.content` vollständig) und legte es über `store_document` ab. Das Upload-Limit `document_max_bytes` (A-016) griff hier nicht; Speicher und Objektspeicher waren über ein großes DMS-Dokument belastbar. | mittel | behoben | `apps/api/src/mhvp/receipts/routers.py:178-184` |
| 3 | Ticketantwort | `TicketReplyIn.to_addresses` sind freie Zeichenketten ohne Adressprüfung; sie landen unverändert in `Message.to_addresses`. Kein Header-Injection möglich (`EmailMessage` weist Zeilenumbrüche in Headern mit `ValueError` ab, geprüft), aber eine ungültige Adresse führt bei der Freigabe durch die zweite Person zu einem unbehandelten 500 statt zu einer Validierungsmeldung. Gleiches Muster besteht bereits in `communication/routers.py` (`MessageIn.to_addresses`). | niedrig | behoben | `apps/api/src/mhvp/tickets/routers.py:561`, `apps/api/src/mhvp/communication/routers.py:71` |
| 4 | Ticketantwort, Postfach | Die Antwort wird über das Postfach der letzten Eingangsmail oder das Standardpostfach angelegt, ohne `MailboxUser`-Freigabe des Bearbeiters zu prüfen (`_accessible_mailboxes` gilt nur für die Mailliste). Der Versand bleibt an `communication:approve` einer anderen Person gebunden (Vier-Augen-Prinzip eingehalten). Hinweis, kein Rechteverlust nachweisbar. | niedrig | behoben | `apps/api/src/mhvp/tickets/routers.py:760-776` |
| 5 | Bankkontenauswahl | Suchparameter `q` wird ungeschützt in `ILIKE '%…%'` eingesetzt; `%` und `_` wirken als Wildcards. Keine SQL-Injection (gebundener Parameter), nur weitere Treffer innerhalb des eigenen Mandanten (RLS). | niedrig | behoben | `apps/api/src/mhvp/banking/account_selection.py:96` |
| 6 | objektakte Listen, CSV | Titel und Dateinamen aus Dokumenten werden unverändert in die CSV geschrieben; ein Wert, der mit `=`, `+`, `-` oder `@` beginnt, wird in Excel als Formel interpretiert (CSV-Injection). Angreifer bräuchte Schreibrecht auf Dokumente desselben Mandanten. | niedrig | behoben | `apps/api/src/mhvp/objektakte/lists.py:209` |
| 7 | objektakte Differenzimport | `POST /objektakte/sync/runs` ohne Datei stößt den Worker-Lauf mit `force=True` an und ignoriert damit den per `tenant_settings:update` gesetzten Schalter `enabled`; ausgelöst werden kann er mit `documents:create`. Dokumentiertes Verhalten, aber schwächer als die Einstellung selbst. | niedrig | behoben | `apps/api/src/mhvp/objektakte/routers.py:248`, `apps/api/src/mhvp/objektakte/tasks.py:142` |
| 8 | objektakte Differenzimport | `read_dump_file` lädt bis zu 2 GiB (`MAX_DUMP_BYTES`) vollständig in den Speicher des Workers, der Upload-Weg erlaubt 200 MB. Betriebsrisiko, kein Sicherheitsbefund. | niedrig | behoben | `apps/api/src/mhvp/objektakte/tasks.py:32` |
| 9 | KI-Anbieter, Fehlerdurchreichung | `status_detail` übernimmt bis zu 300 Zeichen der Anbieterantwort in `ProviderError` und damit in `AiTaskRun.error`, die Chatantwort und das strukturierte Log (`reason=str(exc)`). Schlüsselmuster (`sk-…`, `Bearer …`) werden entfernt; eine Rückgabe von Prompt-Inhalten durch den Anbieter in Fehlermeldungen ist nicht bekannt, aber nicht ausschließbar. Hinweis. | niedrig | offen | `apps/api/src/mhvp/ai/providers.py:27-56`, `apps/api/src/mhvp/ai/gateway.py:868` |
| 10 | Mahnschreiben | `POST /dunning-cases/{id}/letter-preview` erzeugt das PDF mit Schuldneranschrift und Beträgen bereits mit `accounting:read` (Ablage braucht `accounting:create`, Versand `accounting:approve` und bleibt hinter G1 gesperrt). Konsistent zur Leseberechtigung des Mahnfalls, kein Befund. | niedrig | offen | `apps/api/src/mhvp/accounting/routers.py:1727` |

## Behobene Befunde im Detail

**Nr. 1, Exportpfad außerhalb des Exportverzeichnisses (mittel).** Neue Einstellung
`Settings.objektakte_dump_dir` (`MHVP_OBJEKTAKTE_DUMP_DIR`, Standard
`/data/objektakte-export`). `PUT /objektakte/sync` weist mit 422 jeden Pfad ab, der nach
Normalisierung (`..` aufgelöst) nicht in diesem Verzeichnis liegt
(`mhvp.objektakte.tasks.path_within_dump_dir`). `read_dump_file(dump_path, base_dir)` prüft
im Worker zusätzlich den aufgelösten Pfad (Symlinks), sodass auch ein Link im
Exportverzeichnis auf eine fremde Datei mit `DumpUnreadableError` endet; der Fehler wird wie
bisher je Mandant im Sync-Status protokolliert. Tests:
`tests/unit/test_m35_objektakte_sync.py::test_read_dump_file_stays_inside_the_export_directory`
(direkt, `..`, Symlink, Präfixverwechslung) und
`tests/integration/test_m35_objektakte_sync.py::test_switch_is_off_by_default_and_needs_a_dump_path`
(422 für `/etc/objektakte.sql` und `/data/objektakte-export/../x/objektakte.sql`).
Betriebshinweis: bestehende Installationen, deren Export nicht unter
`/data/objektakte-export` liegt, müssen `MHVP_OBJEKTAKTE_DUMP_DIR` setzen; ein bereits
gespeicherter Pfad außerhalb schlägt beim nächsten Lauf fehl und wird im Status sichtbar.

**Nr. 2, Paperless-Dokument ohne Größenlimit (mittel).** `create_draft_from_paperless` weist
Inhalte über `settings.document_max_bytes` mit `MHVP-DOC-0003` (422) ab, bevor etwas
gespeichert oder eine Extraktion gestartet wird. Test:
`tests/integration/test_m14_receipt_drafts.py::test_paperless_document_over_size_limit_is_rejected`.

**Nr. 3, Adressprüfung (niedrig).** `TicketReplyIn.to_addresses` und
`MailDraftPatchIn.to_addresses` sind jetzt `list[EmailStr]` (höchstens 20); eine ungültige
Adresse endet mit 422 beim Anlegen statt mit 500 bei der Freigabe. Test:
`tests/integration/test_m19_ticket_reply_templates.py::test_reply_rejects_invalid_addresses_and_foreign_mailbox`.

**Nr. 4, Postfachberechtigung der Ticketantwort (niedrig).** Neue Hilfsfunktion
`mhvp.communication.routers.mailbox_accessible` (Administrator mit `tenant_settings:update`,
Standardpostfach oder `MailboxUser`-Freigabe, dieselbe Regel wie `_accessible_mailboxes` der
Mailliste). `POST /tickets/{id}/reply` antwortet mit 403 und klarer Meldung, wenn der
Bearbeiter das Postfach des Tickets nicht nutzen darf. Test: siehe Nr. 3.

**Nr. 5, ILIKE-Wildcards (niedrig).** `mhvp.core.escaping.escape_like` maskiert `%`, `_` und
`\`; `banking/account_selection.py` sucht damit wörtlich (`ilike(..., escape="\")`). Tests:
`tests/unit/test_core_escaping.py`,
`tests/integration/test_bank_account_selection.py::test_search_term_matches_literally`.

**Nr. 6, CSV-Injection (niedrig).** `mhvp.core.escaping.csv_safe_cell` stellt Zellen, die mit
`=`, `+`, `-`, `@`, Tabulator oder CR beginnen, ein Hochkomma voran (nur Zeichenketten, Zahlen
bleiben unverändert). Angewendet in `objektakte/lists.py::to_csv` und auf die Textfelder
(Belegnummer, Text, Kontobezeichnung) des Journalexports in `accounting/reports.py`. Der
DATEV-Buchungsstapel bleibt unverändert, da das Format vom DATEV-Import gelesen wird und ein
vorangestelltes Hochkomma den Buchungstext verfälschen würde; die Datei ist nicht für Excel
bestimmt. Tests: `tests/unit/test_core_escaping.py`,
`tests/unit/test_objektakte_lists_csv.py::test_csv_neutralises_formula_prefixes`.

**Nr. 7, manueller Lauf gegen den Schalter (niedrig).** `POST /objektakte/sync/runs` ohne
Datei antwortet mit 409, solange `enabled` aus ist; der Worker-Task
`mhvp.objektakte.sync_tenant` läuft nicht mehr mit `force=True` und prüft den Schalter erneut.
Ein Upload bei ausgeschaltetem Import bleibt Administratoren (`tenant_settings:update`)
vorbehalten, andere Nutzer mit `documents:create` erhalten 403. Test:
`tests/integration/test_m35_objektakte_sync.py::test_manual_run_respects_the_switch`.

**Nr. 8, Exportgröße im Worker (niedrig).** Neue Einstellung
`Settings.objektakte_dump_max_bytes` (`MHVP_OBJEKTAKTE_DUMP_MAX_BYTES`, Standard 512 MiB,
höchstens 4 GiB); `read_dump_file(dump_path, base_dir, max_bytes)` prüft die Größe per `stat`
vor dem Lesen und nennt Größe und Obergrenze im Fehler. `MHVP_OBJEKTAKTE_DUMP_DIR` und die
Obergrenze sind in `infra/env.prod.example` und `docs/runbooks/server-setup.md` dokumentiert.
Test: `tests/unit/test_m35_objektakte_sync.py::test_read_dump_file_checks_size_before_reading`.

## Geprüft ohne Befund

- Berechtigungen: alle neuen Endpunkte tragen `require_permission` passend zum Modul
  (`tickets:read/update` plus `communication:update` für den Antwortweg, `contacts:update` für
  die Übernahme von Stammdatenvorschlägen, `accounting:read/create/approve` beim Belegeingang
  und Mahnwesen, `banking:read/update`, `contracts:read` beim OpenImmo-Export,
  `objektakte:read` für Listen und KI-Protokoll, `tenant_settings:update` für den Sync-Schalter).
  Die neue Ressource `objektakte` in `core/auth/permissions.py` erweitert Standardrollen nur um
  Lese- und Prüfrechte; Löschen bleibt beim Mandantenadministrator (M2-07).
- Mandantentrennung und IDOR: jede Abfrage läuft in `tenant_tx` (RLS). IDs aus Body oder Query
  (`template_id`, `attachment_document_ids`, `document_id`, `message_id`, `contact_id`,
  `property_id`, `bank_account_id`) werden per `session.get` unter RLS geladen; fremde IDs
  enden als 404 oder 422, nie als Zugriff. `_pending` bindet Vorschläge an das Ticket der URL,
  `_start` prüft, dass der Anhang zur Nachricht gehört, `_check_property_scope` die
  Rechtsträgertrennung der Kontenzuordnung.
- Geldregeln: keine Buchung, keine Zahlung. Belegeingang erzeugt nur einen offenen, ungebuchten
  Rechnungsentwurf; eine IBAN wird ausschließlich mit `iban_confirmed=true` vom Prüfer
  übernommen, dem Modell wird sie nie gezeigt (deterministische Kandidaten, verschlüsselt
  gespeichert, maskiert ausgegeben). Stammdatenvorschläge weisen Bankfelder in
  `_validate_changes` und `_to_contact_in` ab. Mahnschreiben bleiben Entwurf, `letter/send`
  prüft G1 und lehnt danach immer ab. Bankkontenauswahl ist reine Organisation.
- Datenschutz gegenüber dem KI-Anbieter: Belegtext über `receipts.masking.mask_text`,
  Ticketmails über `mask_identifiers` (IBAN, E-Mail, Telefon), Klassifikation über
  `mask_ibans`; maskierter Auszug wird am Entwurf gespeichert. Logs enthalten IDs, Status und
  Fehlergrund, keine IBAN und keine Schlüssel.
- Vier-Augen-Prinzip: Ticketantworten entstehen als `pending` mit `submitted_by`; der Versand
  läuft ausschließlich über `POST /mail/messages/{id}/approve`, das eigene Entwürfe ablehnt.
  Anhänge werden erst beim Versand unter RLS geladen; ein fehlendes Dokument bricht ab.
- Pfad- und Dateiprüfungen: OpenImmo-Bilddateinamen werden von `/` und `\` bereinigt,
  CSV-Dateinamen auf `[A-Za-z0-9._-]` reduziert, PDF-Dateinamen per `quote()` gesetzt;
  `store_document` verwendet einen eigenen Speicherschlüssel, nie den Dateinamen. Upload des
  Differenzimports auf 200 MB begrenzt, Belegdrafts auf PDF, PNG, JPEG, Text.
- Injection: keine `text()`-Abfragen in den geprüften Modulen; die neuen Alembic-Migrationen
  0076 bis 0083 verwenden nur konstante Tabellennamen in f-Strings. Briefinhalte werden mit
  `html.escape` in die Vorlage übernommen.
- CLI-Importe (`imports/objektdaten.py`, `imports/kontakte.py`): nur Kommandozeile, kein
  Endpunkt; Testlauf als Standard, Schreiben nur mit `--apply`; keine Beträge, Verträge oder
  Bankverbindungen werden angelegt.

## Hinweis zur Abdeckung

`objektakte/objektakte_import.py` (Stufe 5, 760 geänderte Zeilen) wurde nur auf rohes SQL,
Löschungen und Fehlerdurchreichung geprüft, nicht Zeile für Zeile. Der Frontend-Anteil
(BFF-Route, neue Komponenten) war nicht Gegenstand dieses Reviews.

## Testlauf

- `ruff check`, `ruff format` und `mypy` auf den geänderten Dateien: ohne Befund.
- `pytest --no-cov`: `tests/unit/test_m35_objektakte_sync.py`,
  `tests/unit/test_m14_receipt_drafts.py`, `tests/integration/test_m35_objektakte_sync.py`,
  `tests/integration/test_m14_receipt_drafts.py`: 19 bestanden (PostgreSQL und Redis lokal).
- Nicht ausgeführt: die übrige Testsuite, Frontend- und Playwright-Tests.
