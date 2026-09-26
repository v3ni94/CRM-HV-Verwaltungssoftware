# Berechtigungsreview D50 (Aufgabe A04), Stand 26.09.2026

Prüfgegenstand: Anhang D Fall D50 des Master-Prompts. Ein Benutzer mit reinem Leserecht versucht
Finanzänderungen über Massen- und Nebenwege: alle schreibenden Massenendpunkte, Celery-Jobs und
API-Schlüssel mit eingeschränkten Scopes. Erwartung nach Regel 0.1.4 (API first, Sperren gelten
auch für Jobs, Importe, Massenaktionen und Integrationen): serverseitige Ablehnung mit 403, nie
2xx und nie 500. Das Verstecken in der Oberfläche allein genügt nicht.

Dies ist ein Review, keine Freigabe. Nichts wurde committet; VERSION, CHANGELOG.md und
changelog.ts sind unverändert (Festlegung des Auftrags, parallele Agenten im selben Arbeitsbaum).

## Vorgehen

1. Endpunktliste aus `apps/api/openapi.json` abgeleitet: alle Pfade, deren Name `bulk`, `apply`,
   `approve`, `run`, `release`, `post` oder `confirm` enthält, ohne die Lesemethoden GET, HEAD
   und OPTIONS. Ergebnis: 38 Endpunkte (Stand der exportierten Spezifikation).
2. Jeder Endpunkt wurde dreimal aufgerufen: mit der Systemrolle `read_only` (Bearer Token), mit
   einem API-Schlüssel, der ausschließlich `*:read`-Scopes trägt, und ohne Anmeldung.
   Pfadparameter erhalten syntaktisch gültige Werte (zufällige UUIDs, `provider=openai`), damit
   allein der Berechtigungsschutz entscheidet. Der Rumpf ist leer, außer bei `/workspace/bulk`,
   dessen Prüfung je Aktion im Handler liegt und deshalb einen gültigen Rumpf braucht.
3. Positivkontrolle: dieselben Aufrufe passieren mit `tenant_admin` den Berechtigungsschutz und
   scheitern erst an der Eingabeprüfung (422). Damit ist belegt, dass die 403 der fehlenden
   Berechtigung zuzurechnen ist und nicht dem synthetischen Rumpf.
4. Stichprobe Gate-Sperren: `POST /banking/payment-batches` (G2) und
   `POST /hoa/statements/{id}/post` (G4) werden auch für `tenant_admin` mit `MHVP-GATE-0001`
   abgewiesen; der persistente Resolver meldet alle Gates G1 bis G5 für den Testmandanten
   geschlossen; der Job-Guard `release_gated` wirft ohne Freigabe und ohne Mandantenkontext.
5. Celery-Jobs: Signaturen aller registrierten `mhvp.*`-Tasks geprüft; kein Task nimmt einen
   Principal, Berechtigungen oder Rollen entgegen.

Testdatei: `apps/api/tests/integration/test_d50_authorization.py` (124 Tests, alle bestanden,
ausgeführt mit `uv run pytest tests/integration/test_d50_authorization.py --no-cov`).

## Ergebnisliste Massenendpunkte

Spalten: Aufruf mit Rolle `read_only`, Aufruf mit API-Schlüssel (nur `*:read`), Aufruf ohne
Anmeldung. Guard ist die serverseitig hinterlegte Abhängigkeit des Endpunkts.

| Nr. | Endpunkt | Guard | `read_only` | API-Key nur lesen | anonym |
| --- | --- | --- | --- | --- | --- |
| 1 | POST `/accounting/dunning-runs/{run_id}/approve` | `accounting:approve` | 403 | 403 | 401 |
| 2 | POST `/accounting/dunning-runs` | `accounting:create` | 403 | 403 | 401 |
| 3 | POST `/accounting/invoices/{invoice_id}/confirm-iban` | `accounting:approve` | 403 | 403 | 401 |
| 4 | POST `/accounting/invoices/{invoice_id}/post` | `accounting:create` | 403 | 403 | 401 |
| 5 | POST `/accounting/invoices/{invoice_id}/release` | `accounting:approve` | 403 | 403 | 401 |
| 6 | POST `/accounting/ledgers/{ledger_id}/entries/{entry_id}/approve` | `accounting:approve` | 403 | 403 | 401 |
| 7 | POST `/accounting/ledgers/{ledger_id}/entries/{entry_id}/post` | `accounting:create` | 403 | 403 | 401 |
| 8 | POST `/accounting/receivable-runs/{run_id}/post` | `accounting:create` | 403 | 403 | 401 |
| 9 | POST `/accounting/receivable-runs/{run_id}/reverse` | `accounting:approve` | 403 | 403 | 401 |
| 10 | POST `/accounting/receivable-runs` | `accounting:create` | 403 | 403 | 401 |
| 11 | POST `/accounting/templates/{template_id}/release` | `accounting:approve` | 403 | 403 | 401 |
| 12 | POST `/ai/proposals/{proposal_id}/apply` | `ai:create` | 403 | 403 | 401 |
| 13 | POST `/ai/providers/{provider}/release` | `ai:approve` | 403 | 403 | 401 |
| 14 | POST `/banking/auto-post` | `accounting:create` | 403 | 403 | 401 |
| 15 | POST `/banking/bulk-confirm` | `accounting:create` | 403 | 403 | 401 |
| 16 | POST `/banking/payment-orders/{order_id}/approve` | `accounting:approve` | 403 | 403 | 401 |
| 17 | POST `/banking/rules/{rule_id}/approve` | `accounting:approve` | 403 | 403 | 401 |
| 18 | POST `/hoa/plans/{plan_id}/apply` | `accounting:approve` | 403 | 403 | 401 |
| 19 | POST `/hoa/special-levies/{levy_id}/apply` | `accounting:approve` | 403 | 403 | 401 |
| 20 | POST `/hoa/statements/{statement_id}/post` | `accounting:approve` | 403 | 403 | 401 |
| 21 | POST `/immoware/learning/runs` | `immoware:update` | 403 | 403 | 401 |
| 22 | POST `/imports/immoware24/files/{source_id}/apply` | `ai:create` | 403 | 403 | 401 |
| 23 | POST `/imports/immoware24/files/{source_id}/test-run` | `ai:create` | 403 | 403 | 401 |
| 24 | POST `/letting/flow-import/{run_id}/apply` | `contracts:create` | 403 | 403 | 401 |
| 25 | POST `/mail/messages/{message_id}/apply-playbook` | `communication:update` | 403 | 403 | 401 |
| 26 | POST `/mail/messages/{message_id}/approve` | `communication:approve` | 403 | 403 | 401 |
| 27 | POST `/objektakte/imports/{import_run_id}/ocr-cache` | `documents:create` | 403 | 403 | 401 |
| 28 | POST `/objektakte/properties/{property_id}/completeness/nachforderungsschreiben` | `objektakte:read` (nur Entwurfstext, keine Schreibwirkung) | 404 (siehe Hinweis 1) | 404 (siehe Hinweis 1) | 401 |
| 29 | POST `/objektakte/review/bulk-decide` | `objektakte:update` | 403 | 403 | 401 |
| 30 | POST `/objektakte/sync/runs` | `documents:create` | 403 | 403 | 401 |
| 31 | POST `/platform/tenants/{tenant_id}/release-gates/requests/{request_id}/approve` | `require_platform_admin` | 403 | 403 | 401 |
| 32 | POST `/platform/tenants/{tenant_id}/release-gates/requests/{request_id}/reject` | `require_platform_admin` | 403 | 403 | 401 |
| 33 | POST `/receipts/drafts/{draft_id}/confirm` | `accounting:create` | 403 | 403 | 401 |
| 34 | POST `/retention-profiles/{profile_id}/release` | `documents:approve` | 403 | 403 | 401 |
| 35 | POST `/tenant/release-gates/requests/{request_id}/revoke` | `release_gates:update` | 403 | 403 | 401 |
| 36 | POST `/tenant/release-gates/requests` | `release_gates:create` | 403 | 403 | 401 |
| 37 | POST `/tickets/bulk-status` | `tickets:update` | 403 | 403 | 401 |
| 38 | POST `/workspace/bulk` | `member` und je Aktion `contacts:update` bzw. `properties:update` | 403 | 403 | 401 |

Hinweis 1: `POST /objektakte/properties/{property_id}/completeness/nachforderungsschreiben`
erzeugt nur den Entwurfstext eines Nachforderungsschreibens aus der Vollständigkeitsprüfung und
schreibt nichts (kein Dokument, keine Buchung, kein Versand). Der Guard `objektakte:read` ist
deshalb fachlich richtig; ein Leser passiert ihn und erhält für ein unbekanntes Objekt 404. Der
Fall ist im Test als dokumentierte Ausnahme mit zulässigen Antworten 403 oder 404 geführt, damit
eine spätere Schreibwirkung auffällt. Kein Befund.

Hinweis 2: `POST /workspace/bulk` prüft die Berechtigung im Handler je Aktion
(`contacts.add_tag`, `contacts.remove_tag` mit `contacts:update`; `maintenance.done` mit
`properties:update`). Alle drei Aktionen werden für `read_only` und für den Lese-API-Schlüssel
mit 403 abgewiesen. Der API-Schlüssel scheitert zusätzlich an `member`, weil ein Schlüssel keinen
Benutzer trägt. Ein leerer Rumpf liefert 422 vor der Berechtigungsprüfung; das ist keine
Schreibwirkung, aber die Reihenfolge weicht von den übrigen Endpunkten ab (siehe offene Punkte).

Hinweis 3: Die Gate-Endpunkte der Plattform (`/platform/.../approve`, `/reject`) verlangen
`require_platform_admin`; API-Schlüssel werden dort grundsätzlich abgewiesen
(`principal.api_key_id is not None` führt zu 403).

## Gate-Sperren bei Massenendpunkten und Jobs (Stichprobe)

| Prüfung | Ergebnis |
| --- | --- |
| `POST /banking/payment-batches` als `tenant_admin`, G2 geschlossen | 403 `MHVP-GATE-0001`, `gate=G2`, Prüfung vor jedem Datenzugriff |
| `POST /hoa/statements/{id}/post` als `tenant_admin`, G4 geschlossen | 403 `MHVP-GATE-0001`, `gate=G4`, Prüfung vor dem Laden der Abrechnung |
| `POST /banking/payment-batches` als `read_only` | 403 `MHVP-AUTH-0003`, Berechtigung greift vor dem Gate |
| `DbReleaseGateResolver.is_open` für G1 bis G5, Testmandant | überall `False` (geschlossen, kein globaler Schalter, ADR 0003) |
| Job-Guard `release_gated(G1)` mit Standardresolver | `ReleaseGateClosedError` bei UUID, bei String-UUID und ohne Mandant; Jobrumpf wird nie erreicht |

## Celery-Jobs

Alle registrierten Jobs (`mhvp.core.ping`, `mhvp.core.webhooks.dispatch`, `mhvp.documents.mirror`,
`mhvp.ai.run`, `mhvp.workspace.reminders`, `mhvp.communication.*`, `mhvp.tickets.propose_contact_change`,
`mhvp.banking.sync_all`, `mhvp.banking.finapi_fetch`, `mhvp.banking.finapi_scheduled_fetch`,
`mhvp.accounting.dunning_run`, `mhvp.letting.purge_prospects`, `mhvp.platform.usage_all`,
`mhvp.sla.check_clocks`, `mhvp.immoware.*`, `mhvp.objektakte.sync_all`, `mhvp.objektakte.sync_tenant`)
laufen systemseitig ohne Principal. Die Berechtigungsprüfung liegt damit vollständig am
auslösenden Endpunkt:

| Job | Auslöser | Guard des Auslösers | Geldwirkung im Job |
| --- | --- | --- | --- |
| `mhvp.ai.run` | `POST /ai/conversations/{id}/messages` sowie Intake-Aktionen über `start_extraction_run` mit dem Principal des Aufrufers | `ai:create` | keine, erzeugt nur Vorschläge; Übernahme über `POST /ai/proposals/{id}/apply` (`ai:create`) |
| `mhvp.immoware.learning_run` | `POST /immoware/learning/runs` | `immoware:update` | keine |
| `mhvp.objektakte.sync_tenant` | `POST /objektakte/sync/runs` | `documents:create` | keine |
| `mhvp.banking.finapi_fetch` | finAPI-Endpunkte (Verbindung anlegen, Umsätze abrufen) | `banking:approve` bzw. `accounting:update` | Umsatzimport, keine Buchung |
| `mhvp.accounting.dunning_run` | Zeitplan (5. des Monats) | keiner (Beat) | nur Mahnvorschau, `user_id=None`, kein Versand, keine Buchung |
| `mhvp.banking.sync_all`, `finapi_scheduled_fetch` | Zeitplan | keiner (Beat), je Mandant Opt-in | Umsatzimport, keine Buchung |

Die automatische Buchung (`banking.matching.auto_post`) ist nur über
`POST /banking/auto-post` (`accounting:create`) erreichbar und setzt zusätzlich die
Mandanteneinstellung `auto_posting_enabled` und eine freigegebene Regel (Vier-Augen,
`banking:rules/{id}/approve` mit `accounting:approve`) voraus. Kein Beat-Job ruft sie auf.

## Befunde im Produktcode

Keine. Alle 38 schreibenden Massenendpunkte sind mit einer passenden `require_permission`-
Abhängigkeit oder einer gleichwertigen Handlerprüfung geschützt; kein Endpunkt schreibt mit reinem
Leserecht, kein Aufruf endet mit 2xx oder 500. Es war keine Änderung am Produktcode nötig.

## Offene Punkte

1. Reihenfolge bei `POST /workspace/bulk`: Eingabeprüfung (422) läuft vor der Berechtigungsprüfung,
   weil das Recht je Aktion im Handler entschieden wird. Keine Schreibwirkung, aber ein Leser kann
   an der Antwort erkennen, welche Felder der Endpunkt erwartet. Empfehlung: zusätzlich eine
   Mindestberechtigung (`contacts:read` oder `properties:read`) als Abhängigkeit setzen. Niedrig,
   nicht geändert (kein Finanzpfad, Entscheidung des Betreibers).
2. `release_gated` wird von keinem registrierten Job verwendet. Das ist derzeit unkritisch, weil
   kein Beat-Job bucht oder zahlt; sobald ein Job Buchungen oder Zahlungen auslöst (M15 ff.), ist
   der Guard mit `tenant_id` als Schlüsselargument verpflichtend (Regel 0.1.4). Als Prüfpunkt in
   die Definition of Done der betroffenen Meilensteine aufnehmen.
3. Die Endpunktliste hängt von `apps/api/openapi.json` ab. Wird der Export nicht mit `make openapi`
   aktualisiert, prüft der Test einen veralteten Stand. Empfehlung: CI-Schritt, der den Export
   gegen die laufende App vergleicht (OpenAPI-Diff aus Abschnitt 17), damit neue Massenendpunkte
   automatisch in den D50-Test fallen.
4. Der Test deckt die Rolle `read_only` und einen API-Schlüssel mit Lese-Scopes ab. Weitere
   Rollen mit Teilrechten (zum Beispiel `clerk_no_accounting` gegen Buchungsendpunkte) wären eine
   sinnvolle Erweiterung, waren aber nicht Teil von A04.
