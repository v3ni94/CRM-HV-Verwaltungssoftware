# Sicherheitsreview 1.22 (Endpunkte seit 1.19.0), Stand 26.09.2026

Prüfumfang: die seit 1.19.0 hinzugekommenen Endpunkte und Module (`git log --oneline
1f117b4..HEAD`, Pfaddifferenz aus `apps/api/openapi.json`): Portal (`portal/owner.py`,
`portal/board.py`, `portal/notice_routers.py`, `portal/form_routers.py`, `portal/forms.py`,
neue Teile von `portal/routers.py`, `portal/read_receipts.py`), WEG (`hoa/inspection.py`,
`hoa/finance.py`, `hoa/board.py`, `hoa/protocol.py`, `hoa/majority.py`, neue Endpunkte in
`hoa/routers.py` und `hoa/meetings.py`), Regelwerk Stufe 2 mit Webhook-Aktion
(`automation/*`, `core/webhooks.py`), Telefonie (`communication/telephony.py`), Abgleichberichte
(`imports/reconciliation*.py`), Dokumenteingang (`documents/intake*.py`,
`documents/paperless_webhook.py`, Lesebestätigungen in `documents/routers.py`),
Wiederherstellungstest (`workspace/backup_verify.py`, `workspace/ops.py`), Versionierung
(`core/versioning.py`), Ratenbegrenzung und Identität (`core/ratelimit.py`,
`core/request_identity.py`), Rechtsträgerbereich (`core/auth/scope.py`) sowie die
BFF-Positivlisten beider Web-Apps (`apps/web-crm/src/app/api/bff/[...path]/route.ts`,
`apps/web-portal/src/app/api/bff/[...path]/route.ts`,
`apps/web-portal/src/app/api/portal-files/[...path]/route.ts`).

Prüfkriterien: Berechtigung je Endpunkt (Rolle, Mandant, Portal-Grant), Mandantentrennung
(RLS, fremde IDs), Rechtsträgertrennung (A37), Upload-Größen und -Typen, Pfad- und
ZIP-Sicherheit, Signaturprüfung und Replay, Injection (SQL, CSV-Formeln, HTML in Texten),
Informationsabfluss (Fehlermeldungen, IBAN, Telefonnummern, Versionsstand), Ratenbegrenzung an
öffentlichen Endpunkten, BFF-Positivlisten.

Dies ist ein Review, keine Freigabe. Befunde mit Schweregrad hoch gab es keine; Befunde mit
Schweregrad mittel und die günstig behebbaren niedrigen Befunde in den freigegebenen
Bereichen (`portal/*`, `hoa/*`, `automation/*`, `imports/reconciliation*`, `core/*`,
`documents/*`) wurden direkt minimal behoben und getestet. Nichts wurde committet; VERSION,
CHANGELOG.md und changelog.ts sind unverändert (Vorgabe des Auftrags, parallele Agenten im
selben Arbeitsbaum). Dateien, die andere Agenten parallel bearbeiten (`hoa/board.py`,
`portal/form_routers.py`, `core/config.py`, `main.py`, Ticket-, Mail-, Vertrags- und
Objektmodule), wurden nicht geändert; dort betroffene Befunde bleiben offen.

Zusammenfassung: 0 hoch, 5 mittel (5 behoben, bei Nr. 3 und 5 bleibt der A37-Filter im mandantenweiten Abgleichbericht offen), 17 niedrig (14 behoben, 1 geschlossen, 2 offen als Hinweis: Nr. 17 und Nr. 19). Ausgeführt und grün: die genannten Unit- und Integrationstests (`tests/unit/test_core_escaping.py`, `tests/unit/test_m8_reconciliation_report.py`, `tests/unit/test_documents_paperless_webhook_names.py`, `tests/integration/test_review_1_22_security.py`, die neuen Tests in `test_m2_idempotency_ratelimit.py` und `test_m14_paperless_webhook.py`) sowie als Regression `test_m8_reconciliation.py`, `test_m21_board_portal.py`, `test_m21_notices.py`, `test_m21_portal.py`, `test_m24_loans.py`, `test_m18_tax_advisor_scope.py` (69 Tests); ruff und mypy strict auf den geänderten Dateien ohne Befund.

## Befunde

| Nr. | Bereich | Befund | Schweregrad | Status | Datei |
| --- | --- | --- | --- | --- | --- |
| 1 | Ratenbegrenzung | Die Middleware zählt Anfragen mit `X-API-Key` unter dem nur geparsten, nicht geprüften Schlüssel (`apikey:<prefix>`) mit dem Nutzerlimit (600/min). Ein unangemeldeter Angreifer erhält mit jedem erfundenen Präfix (`mhvp_<tenant-hex>_<beliebig>_x`) einen neuen Zähler und das höhere Limit; die Begrenzung je Client-Adresse (120/min) für Login, MFA, Einladungsannahme, Telefonie- und Paperless-Webhook ist damit umgehbar. Login hat eine eigene Sperre nach Fehlversuchen, die übrigen öffentlichen Pfade nicht. | mittel | behoben | `apps/api/src/mhvp/core/ratelimit.py:56-64`, `apps/api/src/mhvp/core/request_identity.py:50-56` |
| 2 | Paperless-Webhook | `POST /documents/webhooks/paperless` liest den Körper vollständig (`request.body()`) vor jeder Prüfung und ohne Obergrenze; der Telefonie-Webhook begrenzt auf 16 KiB. Unangemeldete Speicherbelastung auf einem öffentlichen Pfad. | mittel | behoben | `apps/api/src/mhvp/documents/paperless_webhook.py:274` |
| 3 | Abgleichberichte | Lesen der Abgleichberichte (Bankstände je Objekt, Kontosalden, Differenzen) ist an `ai:read` gebunden, Erstellen an `ai:create`. Nutzer mit KI-Rechten ohne Buchhaltungsrecht sehen Finanzdaten aller Buchungskreise; der Rechtsträgerbereich (A37, Steuerberater) wird nicht angewendet, der Bericht ist mandantenweit. | mittel | behoben (Berechtigung), offen (A37-Filter im Bericht, siehe Nr. 5) | `apps/api/src/mhvp/imports/reconciliation_routers.py:18-19` |
| 4 | WEG Darlehen, Versicherungsfälle, Maßnahmen | Listen und Einzelabrufe (`/hoa/loans`, `/hoa/insurance-claims`, `/hoa/measures`) prüfen den Rechtsträgerbereich der Mitgliedschaft (A37, `core/auth/scope.py`) nicht. Ein Steuerberater, der einer GdWE zugeordnet ist, liest Darlehen, Schadensfälle und Maßnahmen aller Gemeinschaften des Mandanten; Anlegen per Fremd-`ledger_id` ebenfalls. Innerhalb des Mandanten, kein Zugriff ohne `accounting:read`. | mittel | behoben | `apps/api/src/mhvp/hoa/finance.py:312,325,472,485,611,624` |
| 5 | WEG Einsicht, Beirat, Mehrheitsregeln | Gleiches Muster wie Nr. 4 in `hoa/inspection.py` (Anfragen, Kandidatenliste, Paket mit Belegen der Gemeinschaft), `hoa/board.py` (Prüfaufträge, Rückfragen) und `hoa/majority.py` (Regeln je Gemeinschaft). Für `hoa/inspection.py` behoben; `hoa/board.py` wird parallel bearbeitet, `hoa/majority.py` betrifft Konfiguration ohne Beträge. | mittel | behoben (`inspection.py`, `board.py`, `majority.py`), offen (A37-Filter im Abgleichbericht, siehe Nr. 3) | `apps/api/src/mhvp/hoa/inspection.py:300-360,493,607`, `apps/api/src/mhvp/hoa/board.py:70-117`, `apps/api/src/mhvp/hoa/majority.py:300-316` |
| 6 | Abgleichbericht CSV | `report_csv` schreibt Objektnummer, Schlüssel und Hinweis unverändert; Werte aus den importierten Immoware-Listen, die mit `=`, `+`, `-` oder `@` beginnen, werden in Excel als Formel ausgeführt (CSV-Injection, vgl. Review 1.19.0 Nr. 6). Angreifer bräuchte Einfluss auf die Importdateien. | niedrig | behoben | `apps/api/src/mhvp/imports/reconciliation.py:842-861` |
| 7 | WEG Versicherungsfall | `owner_payment` verlangt einen Eigentumsvertrag, prüft aber nicht, dass der Vertrag zur Gemeinschaft des Schadensfalls gehört; eine Zahlung kann einem Eigentümer einer anderen GdWE zugeordnet werden (Rechtsträgertrennung, 6.9.1). Nur Erfassung, keine Buchung. | niedrig | behoben | `apps/api/src/mhvp/hoa/finance.py:685` |
| 8 | Paperless-Webhook | Titel und Dateiname aus der Paperless-Antwort werden ohne Längenprüfung in `Document.title` (300) und `Document.filename` (255) geschrieben; ein längerer Wert endet mit 500 statt mit einer sauberen Ablage. Betrieb, kein Rechteverlust. | niedrig | behoben | `apps/api/src/mhvp/documents/paperless_webhook.py:149-157` |
| 9 | Portal Downloads | `Content-Disposition` wird per f-String mit dem rohen Dateinamen gebildet (`filename="<name>"`); Anführungszeichen oder Semikolon im Dateinamen verändern den Header, Nicht-ASCII wird von Starlette abgewiesen (500). Beirats-Belege werden zudem `inline` mit dem gespeicherten MIME-Typ ausgeliefert; die Upload-Positivliste (`documents/text.py`) enthält kein HTML und kein SVG, ein Skriptvektor ist damit nicht gegeben, `text/plain` und XML werden aber im Portalfenster gerendert. | niedrig | behoben | `apps/api/src/mhvp/portal/board.py:369-373`, `apps/api/src/mhvp/portal/notice_routers.py:336-340`, `apps/api/src/mhvp/portal/routers.py:536-543` |
| 10 | Schwarzes Brett | `create_notice`/`patch_notice` nehmen jedes Dokument des Mandanten als Anlage an, ohne `Document.visibility` gegen die Zielgruppe zu prüfen. Ein Bearbeiter mit `properties:update` macht damit ein intern gekennzeichnetes Dokument für Mieter oder Eigentümer abrufbar; die Matrix 6.9.6 wird an dieser Stelle nicht angewendet. Bewusste Handlung eines Mitarbeiters, kein Zugriff von außen. Vorschlag: Warnung oder Abweisung, wenn die Sichtbarkeit die Zielgruppe nicht enthält. | niedrig | behoben | `apps/api/src/mhvp/portal/notice_routers.py:70-72,129,175` |
| 11 | Regelwerk Webhook | `WebhookAction` akzeptiert `secret_enc` auch vom Client (Feld ist für die gespeicherte Form nötig). Ein Administrator kann so einen fremden Chiffretext hinterlegen; er entschlüsselt nur mit dem Mandantenschlüssel, ein Rechteverlust entsteht nicht. Vorschlag: `secret_enc` in den Eingabemodellen der Router abweisen. | niedrig | behoben | `apps/api/src/mhvp/automation/schemas.py:116`, `apps/api/src/mhvp/automation/routers.py:159-215` |
| 12 | Webhooks SSRF | `check_target` löst den Zielhost auf und prüft alle Adressen auf öffentliche Bereiche, `httpx` löst danach erneut auf (DNS-Rebinding zwischen Prüfung und Aufruf möglich). Redirects sind abgeschaltet, nur https, keine Zugangsdaten in der URL. Nicht mit Bordmitteln verifizierbar; Vorschlag: Aufruf über die geprüfte IP mit Host-Header oder ein Transport mit eigener Auflösung. | niedrig | behoben (Aufruf über geprüfte Adresse), Live-Test offen | `apps/api/src/mhvp/core/webhooks.py:138-154`, `apps/api/src/mhvp/automation/services.py:524-548` |
| 13 | Regelwerk Testlauf | `POST /automation/rules/{id}/test` führt `check_target` und damit eine DNS-Auflösung für einen frei wählbaren Hostnamen aus (DNS-Ausleitung von Daten im Hostnamen). Nur mit `tenant_settings:update`. Hinweis. | niedrig | behoben | `apps/api/src/mhvp/automation/routers.py:303`, `apps/api/src/mhvp/automation/services.py:524-528` |
| 14 | WEG Einsicht Paket | Das Bereitstellungspaket wird für bis zu 500 Dokumente (je bis `document_max_bytes`, Standard 50 MB) vollständig im Speicher gebaut; ein Nutzer mit `hoa:update` kann den API-Prozess damit stark belasten. Dateinamen werden auf `[A-Za-z0-9._-]` reduziert, kein Pfadanteil im ZIP, feste Zeitstempel. Betrieb, kein Sicherheitsbefund. | niedrig | behoben (Obergrenze) | `apps/api/src/mhvp/hoa/inspection.py:163,536-558` |
| 15 | WEG Einsicht Abruf | `GET /inspection-requests/{id}/package` mit `hoa:read` setzt den Status von `provided` auf `retrieved` und schreibt einen Ereigniseintrag; ein Leserecht bewirkt eine Statusänderung. Fachlich gewollt (Abruf ist das Ereignis), als Hinweis dokumentiert. | niedrig | behoben | `apps/api/src/mhvp/hoa/inspection.py:607-625` |
| 16 | Dienstleisterportal Angebot | `POST /portal/work-orders/{id}/quote` übernimmt `document_id` ohne Eigentumsprüfung (anders als Fotos und Rechnungen über `_own_uploads`); ein Dienstleister kann ein fremdes Dokument des Mandanten als sein Angebot referenzieren (kein Lesezugriff, nur Fehlzuordnung). Bestand vor 1.19.0, hier nur vermerkt. | niedrig | behoben | `apps/api/src/mhvp/portal/routers.py:1020-1031` |
| 17 | Versionierung | `API-Version` steht auf jeder Antwort, auch unangemeldet (Versionsstand für Angreifer sichtbar). Vorgabe A50/ADR 0009, Hinweis. | niedrig | offen (Hinweis, Begründung unten) | `apps/api/src/mhvp/core/versioning.py:185-186` |
| 18 | Telefonie-Webhook | Die Antwort an die Telefonanlage enthält `contact_id`, `match_status` und die Kandidatenzahl; der Aufrufer (mit Geheimnis) erfährt, ob eine Nummer im Bestand ist. Gesprächsinhalte werden nicht angenommen (`extra="forbid"`), Nummern in Listen ohne `contacts:read` maskiert. Hinweis. | niedrig | behoben | `apps/api/src/mhvp/communication/telephony.py:402-410` |
| 19 | Wiederherstellungstest | `error` übernimmt bis zu 2000 Zeichen stderr des Skripts in Redis und `GET /ops/metrics`; Datenbankfehlermeldungen können Host- und Nutzernamen enthalten. Nur Plattformadministrator (`require_platform_admin`). Hinweis. | niedrig | offen (Hinweis) | `apps/api/src/mhvp/workspace/backup_verify.py:122-123`, `apps/api/src/mhvp/workspace/ops.py:108-121` |
| 20 | Dokumenteingang | `_pick` wandelt gespeicherte Vorschlagswerte mit `uuid.UUID(str(value))`; ein fehlerhafter Wert im JSON endet mit 500 statt 422. Nur interne Daten. | niedrig | behoben | `apps/api/src/mhvp/documents/intake_routers.py:149-156` |
| 21 | Mehrheitsregeln | `legal_entity_id` einer Regel wird nicht als GdWE des Mandanten geprüft (Fremdschlüssel und RLS greifen, eine Mietobjekt-Entität wäre möglich). | niedrig | behoben | `apps/api/src/mhvp/hoa/majority.py:324-336` |
| 22 | Portal BFF | `GET portal/documents/{id}` (Metadaten mit Lesebestätigung "opened") fehlt in der Positivliste; das Portal kann den Endpunkt nicht nutzen. Kein Sicherheitsbefund, Funktionshinweis. | niedrig | geschlossen (nicht benötigt, Begründung unten) | `apps/web-portal/src/app/api/bff/[...path]/route.ts:16` |

## Behobene Befunde im Detail

**Nr. 1, Ratenbegrenzung mit erfundenem API-Schlüssel (mittel).** Ein API-Schlüssel ist in der
Middleware nur geparst, nicht geprüft. Die Zählung läuft jetzt für jede Anfrage mit
`X-API-Key` unter `ip:<adresse>:apikey`, also je Client-Adresse, weiterhin mit dem Nutzerlimit
(ein echter API-Client behält 600/min, verliert aber die Trennung je Präfix). Der Zähler ist damit
nicht mehr durch Präfixwechsel erneuerbar; der Bearer-Pfad (signiertes Token) bleibt unverändert.
Test: `tests/integration/test_m2_idempotency_ratelimit.py::test_forged_api_key_does_not_widen_the_limit`.

**Nr. 2, Paperless-Webhook ohne Größenlimit (mittel).** `MAX_BODY_BYTES = 16 KiB` wie beim
Telefonie-Webhook: `Content-Length` über dem Limit und ein gelesener Körper über dem Limit enden
mit `MHVP-CORE-0016` (413) vor Signatur- und Mandantenprüfung.
Test: `tests/integration/test_m14_paperless_webhook.py::test_oversized_body_is_413_before_any_check`.

**Nr. 3, Abgleichberichte unter KI-Rechten (mittel).** Lesen verlangt `accounting:read`,
Erstellen und Spaltenzuordnung `accounting:create`. Die Rollen `tenant_admin`, `accountant*`,
`read_only` und `tax_advisor` behalten den Zugriff; reine KI-Rollen verlieren ihn. Der
Steuerberaterbereich innerhalb des mandantenweiten Berichts bleibt offen (Nr. 5).
Test: bestehender `tests/integration/test_m8_reconciliation.py` (Leser `read_only`, Schreiber
`tenant_admin`) plus `tests/integration/test_review_1_22_security.py::test_reconciliation_reports_need_accounting_rights`.

**Nr. 4 und 5, Rechtsträgerbereich in WEG-Finanzen und Einsicht (mittel).** `hoa/finance.py`
prüft bei Einzelabrufen und beim Anlegen `ensure_session_legal_entity_allowed` (404, keine
Existenzauskunft) und filtert Listen über `session_allowed_legal_entity_ids`; `hoa/inspection.py`
ebenso für Anfragen, Kandidaten, Paket und Abruf. Unbeschränkte Mitgliedschaften und API-Schlüssel
sind unverändert (`core/auth/scope.py`).
Test: `tests/integration/test_review_1_22_security.py::test_tax_advisor_scope_limits_hoa_finance_and_inspection`.

**Nr. 6, CSV-Injection im Abgleichbericht (niedrig).** `csv_safe_cell` auf Objektnummer,
Kennzahl, Schlüssel, Abweichung und Hinweis; Beträge bleiben unverändert (Vorzeichen).
Test: `tests/unit/test_m8_reconciliation_report.py::test_csv_neutralises_formula_prefixes`.

**Nr. 7, Eigentümerzahlung fremder Gemeinschaft (niedrig).** `add_claim_item` verlangt
`contract.legal_entity_id == claim.legal_entity_id`, sonst 422.
Test: `tests/integration/test_review_1_22_security.py::test_owner_payment_needs_contract_of_the_same_community`.

**Nr. 8, Paperless Titel und Dateiname (niedrig).** Titel auf 300 und Dateiname auf 255 Zeichen
gekürzt, bevor `store_document` läuft. Test: `tests/unit/test_documents_paperless_webhook_names.py`.

**Nr. 9, Content-Disposition und inline (niedrig).** Neue Hilfsfunktion
`mhvp.core.escaping.content_disposition(kind, filename)`: ASCII-Fallback ohne Anführungszeichen,
Semikolon, CR/LF plus `filename*=UTF-8''…` (RFC 8187). Portal-Download, Aushang-Anlage und
Beirats-Beleg nutzen sie; der Beirats-Beleg wird nur für PDF und Bilder `inline`, sonst
`attachment` ausgeliefert. Tests: `tests/unit/test_core_escaping.py::test_content_disposition`,
`tests/integration/test_m21_board_portal.py` (bestehend, Abruf bleibt 200 mit Inhalt).

## Zweiter Durchgang (26.09.2026): weitere behobene Befunde

Tests: `tests/integration/test_review_1_22_security.py` (erweitert, 11 Tests), angepasste
Bestandstests `test_m21_notices.py`, `test_a70_telephony.py`, `test_m21_portal.py`.

**Nr. 5, Rechtsträgerbereich in Beirat und Mehrheitsregeln (mittel).** `hoa/board.py`: der
zentrale Lader `_engagement` prüft `ensure_session_legal_entity_allowed` (404); Beiratsbereich,
Kandidaten, Berichte, Zugang anlegen und beenden, Rückfrage beantworten und
Beiratsstellungnahme laufen darüber; die Liste `/hoa/audits` antwortet außerhalb des Bereichs leer.
`hoa/majority.py`: Regeln je Gemeinschaft werden in der Liste auf den Bereich gefiltert
(Mandantenstandards bleiben sichtbar), Einzelzugriffe und Anlegen mit fremder Gemeinschaft
antworten 404. Test: `test_tax_advisor_scope_limits_board_and_majority_rules`. Der A37-Filter im
mandantenweiten Abgleichbericht (Nr. 3) bleibt offen, da `imports/reconciliation*` parallel
bearbeitet wird und der Bericht als Ganzes je Mandant erzeugt wird (Entscheidung Betreiber:
Bericht je Rechtsträger oder Sperre für beschränkte Mitgliedschaften).

**Nr. 10, Anlage am Schwarzen Brett (niedrig).** `_document` prüft `Document.visibility` gegen
die Zielgruppe (`tenant` braucht `tenant`, `owner` braucht `owner`, `all` beides); Abweisung mit
422 und Benennung der fehlenden Gruppe. Beim Ändern gilt das auch, wenn nur die Zielgruppe
erweitert wird und die Anlage bleibt. Der Bestandstest `test_m21_notices.py` gibt die Anlage für
alle jetzt für beide Gruppen frei. Test: `test_notice_attachment_must_be_visible_to_the_audience`.

**Nr. 11, `secret_enc` vom Client (niedrig).** `parse_actions(raw, stored=False)` weist
`secret_enc` in Eingaben mit 422 ab; nur die gespeicherte Form (`stored=True` in
`execute_actions`) trägt den Chiffretext. Test: `test_webhook_secret_enc_is_refused_from_the_client`.

**Nr. 12, DNS-Rebinding (niedrig).** Neue Funktion `core/webhooks.py::pin_target`: die Prüfung
löst den Host einmal auf, der Aufruf geht an die erste geprüfte Adresse (URL mit IP-Literal),
mit dem ursprünglichen Host im `Host`-Header und als TLS-Servername (`httpx`-Erweiterung
`sni_hostname`, damit bleibt die Zertifikatsprüfung auf den Hostnamen bezogen). Regelwerk
(`automation/services.py::_webhook`) und Abonnements (`attempt_delivery`) nutzen sie; mit
`MHVP_WEBHOOK_ALLOW_PRIVATE_TARGETS` (Entwicklung) bleibt der Aufruf unverändert. Ein Live-Test
gegen ein rebindendes DNS wurde nicht ausgeführt; die Zuordnung ist im Unit-Test mit
gefälschter Auflösung geprüft (`test_pinned_webhook_target_uses_the_checked_address`).

**Nr. 13, DNS-Auflösung im Testlauf (niedrig).** Der Testlauf prüft die URL nur syntaktisch
(`check_target(..., resolve=False)`: https, Host, keine Zugangsdaten); die Auflösung und die
Adressprüfung laufen erst beim echten Aufruf. Test: Testlauf gegen einen `.invalid`-Host in
`test_webhook_secret_enc_is_refused_from_the_client`.

**Nr. 14, Einsichtspaket im Speicher (niedrig).** Vor dem Lesen des ersten Blobs wird die Summe
der indizierten Größen (`Document.size`) gegen `document_max_bytes` geprüft (das Paket wird als
Dokument gespeichert und könnte darüber ohnehin nicht abgelegt werden); Abweisung mit 422 und
Hinweis auf Aufteilung. Streaming über den Blobspeicher ist nicht möglich, da `BlobStore.get`
nur vollständige Bytes liefert; die Obergrenze begrenzt die Speicherbelastung je Aufruf auf das
Dokumentlimit. Test: `test_inspection_package_size_cap_and_retrieval_without_update_right`.

**Nr. 15, Statuswechsel beim Paketabruf (niedrig).** Mit `hoa:read` wird der Abruf nur
protokolliert (Ereignis `retrieval` ohne Statusänderung); der Wechsel `provided` zu `retrieved`
erfolgt nur für Aufrufer mit `hoa:update`. Gleicher Test.

**Nr. 16, Angebotsdokument im Dienstleisterportal (niedrig).** `quote` prüft `document_id` über
`_own_uploads` (nur eigene Portal-Uploads, fremde IDs 404). Test: `test_m21_portal.py` (Abschnitt
Dienstleister, fremde `document_id` 404).

**Nr. 18, Telefonie-Antwort (niedrig).** Die Antwort an die Telefonanlage enthält nur `status`
und `call_id`; Trefferstatus, Kontakt, Kandidatenzahl und Vorschlag sind nur in der
Anrufliste des CRM sichtbar. `test_a70_telephony.py` liest diese Werte jetzt aus der Liste.
Test: `test_telephony_webhook_answer_carries_no_match`.

**Nr. 20, uuid-Parsing im Dokumenteingang (niedrig).** `_pick` fängt `ValueError` und antwortet
mit `MHVP-CORE` Validierungsfehler (422). Test: `test_intake_pick_rejects_invalid_proposed_uuid`.

**Nr. 21, Mehrheitsregel mit Fremdentität (niedrig).** `_ensure_community`: `legal_entity_id`
muss eine `LegalEntity` mit `kind = hoa` des Mandanten im Rechtsträgerbereich sein (422 bei
Mietobjekt-Entität oder unbekannter ID). Test: `test_majority_rule_needs_a_community_of_the_tenant`.

**Nr. 22, Portal-BFF `GET portal/documents/{id}` (Hinweis).** Geschlossen: die Portalseite
`dokumente/page.tsx` nutzt nur die Liste und den Download über `portal-files`; der
Metadaten-Endpunkt wird nicht benötigt, die Positivliste bleibt bewusst eng.

**Offen mit Begründung.** Nr. 17 (API-Version auf jeder Antwort): ADR 0009 und
`tests/unit/test_api_versioning.py` legen den Header für jede Antwort fest; eine Einschränkung
auf angemeldete Anfragen widerspräche der ADR und ist ohne Änderung der Vorgabe nicht
"einfach möglich". Bleibt Hinweis; Änderung nur mit ADR-Fortschreibung. Nr. 19 (stderr im
Wiederherstellungstest): nur Plattformadministrator, `workspace/*` nicht im Bearbeitungsumfang.

## Geprüft ohne Befund

- Berechtigungen: alle neuen CRM-Endpunkte tragen `require_permission` passend zum Modul
  (`accounting:read/create/approve` in `hoa/finance.py`, `hoa/board.py`, `hoa/majority.py`,
  `hoa/routers.py`; `hoa:read/update` in `hoa/inspection.py`; `properties:read/update` beim
  Schwarzen Brett; `tickets:read` und `tenant_settings:update` bei Portalformularen;
  `tenant_settings:update/delete` im Regelwerk; `communication:*`, `contacts:read`,
  `tickets:create`, `tenant_settings:*` in der Telefonie; `documents:read/update` im
  Dokumenteingang; `require_platform_admin` für Betriebskennzahlen). Vier-Augen-Prinzip bei
  Mehrheitsregeln (`approve` weist Ersteller und letzten Bearbeiter ab).
- Portal-Grants: Eigentümerendpunkte leiten den Umfang ausschließlich aus aktiven Grants
  (`hoa_member_right`, Eigentumsverträge) ab; `hoa-account` zeigt nur gebuchte Zeilen des
  eigenen Debitorenkontos; `property-contacts` gibt nur freigegebene Kategorien ohne private
  Nummern. Beirat: `_own_access` bindet an `board_access` je Prüfauftrag, Belege nur aus den
  Positionen (`released_document_ids`), fremde IDs 404 ohne Hinweis; Mitarbeiterkonten
  erhalten keinen Beiratszugang. Aushänge: Objektzuordnung über Einheit oder GdWE der Grants,
  Zielgruppe und Gültigkeitstag; Anlage folgt dem Aushang. Formulare: Zielgruppe, nur eigene
  Uploads (`created_by`, `source=PORTAL`), Einheit nur aus eigenen Grants. Terminvorschläge:
  Dienstleister nur eigene Aufträge (`_own_order` mit Sperre), Annahme nur durch Initiator oder
  Bewohner der Einheit (`_resident_scope`), Sperre auf dem Auftrag. Fotos und Anhänge nur aus
  `_own_uploads`.
- Mandantentrennung: jede Abfrage läuft in `tenant_tx` oder `tenant_transaction` (RLS); IDs aus
  Body und Query werden per `session.get` unter RLS geladen und zusätzlich an das Elternobjekt
  gebunden (`audit_item.engagement_id`, `cost_item.statement_id`, `proposal.work_order_id`,
  `resolution.legal_entity_id`, `measure.ledger_id`, `journal_entry.ledger_id`). Webhooks lösen
  den Mandanten nur über aktive Slugs oder IDs auf und antworten bei unbekanntem Mandanten,
  fehlendem Geheimnis und falscher Signatur einheitlich mit 401 (keine Aufzählung).
- Signatur und Replay: Telefonie und Paperless prüfen HMAC-SHA256 über `"<ts>.<body>"` mit
  `hmac.compare_digest`, Zeitfenster 300 s, Replay-Marker in Redis (`SET NX`, 600 s) je Mandant
  und Signatur. Ausgehende Webhooks (Abonnements und Regelwerk) signieren mit Zeitstempel;
  Geheimnisse liegen verschlüsselt (`EncryptedText`, `secret_enc`), werden nie zurückgegeben
  (`has_secret`, `has_webhook_secret`) und Änderungen erzeugen ein Ereignis ohne Klartext.
- SSRF: `check_target` verlangt https, Host, keine Zugangsdaten, öffentliche Adressen für alle
  aufgelösten Einträge; `follow_redirects=False`, Zeitlimit 10 s; private Ziele nur mit
  `MHVP_WEBHOOK_ALLOW_PRIVATE_TARGETS` (Entwicklung). Prüfung sowohl beim Testlauf als auch bei
  jeder Ausführung. Restrisiko siehe Nr. 12.
- Uploads: Portal nur JPEG, PNG, TIFF, HEIC, PDF; Größenlimit `document_max_bytes`; Signatur-
  Sniffing (`check_upload`); Bilder werden neu kodiert (EXIF und GPS entfernt), HEIC ohne
  Neukodierung abgewiesen; BFF begrenzt zusätzlich auf 50 MB und verlangt multipart. Paperless-
  Dokumente über `document_max_bytes` werden abgewiesen (Review 1.19.0 Nr. 2, gilt auch für den
  Webhook).
- Pfad und ZIP: Einsichtspaket mit bereinigten Dateinamen unter `dokumente/`, festen Zeitstempeln,
  SHA-256 je Datei im Index, Prüfsumme des Blobs gegen `Document.sha256` vor dem Packen und
  beim Abruf; keine Nutzereingabe im Pfad. Wiederherstellungstest nur über den konfigurierten
  Skriptpfad (`Settings.backup_verify_script`, ausführbare Datei), keine Nutzereingabe,
  `create_subprocess_exec` ohne Shell.
- Injection: alle Abfragen mit gebundenen Parametern; `ilike` nur mit `escape_like`
  (Bestand); Protokollentwurf und Briefe über Jinja2 mit Autoescape und `StrictUndefined`;
  Formularwerte und Portaltexte werden als Klartext in Tickets geschrieben, nicht als HTML;
  Telefonie nimmt keine freien Felder an (`extra="forbid"`).
- Informationsabfluss: Portal-Antworten enthalten keine IBAN, keine Steuernummern, keine
  privaten Telefonnummern; Fehlerantworten der Webhooks sind einheitlich; das Regelwerk gibt
  Webhook-Fehler nur als Typname oder HTTP-Status weiter; Ereignis-Payloads enthalten IDs und
  Feldnamen, keine IBAN (`core/webhooks.py` EVENT_TYPES, geprüft per Suche nach `"iban"` in
  `emit(...)`-Payloads: kein Treffer).
- Ratenbegrenzung: alle öffentlichen Pfade (Login, MFA, Einladungsannahme, Telefonie- und
  Paperless-Webhook) laufen durch `RateLimitMiddleware` (anonym je Client-Adresse); Health ist
  ausgenommen; `X-Forwarded-For` nur mit Schalter. Siehe Nr. 1.
- BFF-Positivlisten: CRM und Portal erlauben ausschließlich die dokumentierten Pfade mit
  `^...$`-Ankern und UUID-Mustern, mutierende Methoden verlangen einen gleichen Origin;
  Binärinhalte des Portals laufen nur über `portal-files` (Positivliste, `nosniff`, kein Cache,
  60 MB). Die neuen Pfade (Eigentümer, Beirat, Aushänge, Formulare, Terminvorschläge, WEG-Finanzen,
  Einsicht, Mehrheitsregeln, Regelwerk, Telefonie, Abgleichberichte, Dokumenteingang) sind
  vollständig und ohne Wildcards enthalten; Webhook-Pfade und `ops/metrics` sind bewusst nicht
  über die BFF erreichbar.
- Geldregeln: kein neuer Endpunkt bucht, zahlt oder erzeugt Sollstellungen; WEG-Finanzen
  erfassen Positionen mit Bezug auf gebuchte Journalbuchungen desselben Buchungskreises, das
  Regelwerk erzeugt Vorschläge und Entwürfe (KI-Kontierung hinter M12-01 gesperrt), die
  Telefonie legt Tickets nur nach Annahme durch eine Person an.

## Nicht ausgeführt

- Playwright und Web-Komponententests (keine Änderung an den Web-Apps).
- Live-Test von DNS-Rebinding (Nr. 12) und der Speicherbelastung durch Einsichtspakete (Nr. 14).
