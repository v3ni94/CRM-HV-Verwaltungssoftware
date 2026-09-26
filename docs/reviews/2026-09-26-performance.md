# Performance-Prüfung Listen und Detailabfragen, Stand 26.09.2026

Prüfumfang: Listen- und Detailendpunkte in `mhvp/contacts`, `mhvp/properties`,
`mhvp/contracts`, `mhvp/accounting` (Listen), `mhvp/documents`, `mhvp/workspace`
(Startseite, Digest, Suche) sowie die CRM-Seite `buchhaltung/[id]` (Journal).
Nicht geprüft (parallel in Bearbeitung): Tickets, Kommunikation, Vermietung, Portal.

Prüfkriterien: N+1-Abfragen (Schleifen mit `session.get` oder Einzel-SELECT je Zeile),
fehlende Indizes für häufige Filter (Mandant kombiniert mit Status, Datum, Fremdschlüssel),
Listen ohne Paginierung, Abfragezahl je Seitenaufruf der Startseite.

Dies ist eine Messung mit Testdaten (12 Zeilen je Liste) in der Integrationsumgebung, keine
Lastmessung. Die Dauer ist die Antwortzeit des `TestClient` im selben Prozess und dient nur
der Orientierung; die Abfragezahl ist die belastbare Kennzahl.

## Messmethode

`tests/integration/test_perf_queries.py`: ein SQLAlchemy-Zähler (`before_cursor_execute` auf
der App-Engine) zählt jede Anweisung eines Aufrufs. Zielwert je Liste: unter 15 Anweisungen,
unabhängig von der Zeilenzahl. Der Zielwert wird als Test abgesichert; die Tabelle unten
entsteht mit `MHVP_PERF_REPORT=1 uv run pytest tests/integration/test_perf_queries.py -s`.

Zu beachten: jeder Aufruf enthält 8 Anweisungen der Anmeldung und des Mandantenkontexts
(Benutzer, Mitgliedschaft, Rollen, Rollenvererbung, Berechtigungen, Mandantendomäne, zwei
Mal `set_config`). Diese liegen außerhalb des Prüfbereichs (`core/auth`) und sind in den
Zahlen enthalten. Der Fachanteil einer Liste liegt nach der Änderung bei 2 bis 6 Anweisungen.

## Messung vorher und nachher (12 Zeilen je Liste)

| Endpunkt | Anweisungen vorher | Dauer vorher | Anweisungen nachher | Dauer nachher | Ursache vorher |
| --- | --- | --- | --- | --- | --- |
| GET /contracts | 57 | 79,7 ms | 13 | 21,8 ms | je Vertrag refresh, Debitorenkonto, Zahlungen, Fälligkeitsregeln |
| GET /contracts?page=2&page_size=5 | keine Paginierung | | 13 | 21,4 ms | |
| GET /contracts/{id}/versions | nicht gemessen (gleicher Pfad, 4 Abfragen je Version) | | 13 | 17,0 ms | |
| GET /properties/{id}/units | 45 | 68,1 ms | 11 | 16,1 ms | je Einheit refresh, Schlüsselwerte, USt-Option |
| GET /properties/{id}/units?as_of | nicht gemessen (wie ohne as_of) | | 11 | 16,8 ms | |
| GET /parties?contact_id | 21 | 31,9 ms | 10 | 15,3 ms | je Partei ein SELECT der Mitglieder |
| GET /accounting/ledgers/{id}/entries | 22 | 54,7 ms | 12 | 20,0 ms | je Buchungssatz ein SELECT der Zeilen |
| GET /accounting/ledgers/{id}/entries?page=2 | keine Paginierung (nur limit/offset) | | 12 | 15,5 ms | |
| GET /accounting/invoices | 33 | 51,6 ms | 12 | 20,5 ms | je Rechnung Zeilen und Prüfschritte |
| GET /sepa-mandates | 10 (1 Mandat) | 27,9 ms | 11 | 19,9 ms | `session.get` je Mandat (bei n Mandaten 9+n), jetzt konstant inkl. Zählung |
| GET /documents/intake-proposals | 10 (0 Vorschläge) | 35,2 ms | 11 | 23,6 ms | `session.get` je Vorschlag (bei n Vorschlägen 10+n), jetzt konstant |
| GET /workspace/dashboard | 19 | 91,2 ms | 11 | 25,3 ms | neun einzelne count-Abfragen, jetzt eine Anweisung |
| GET /workspace/digest | 14 (unverändert) | | 14 | 28,2 ms | konstant, keine Änderung nötig |
| GET /workspace/search?q= | 13 (unverändert) | | 13 | 26,6 ms | konstant, keine Änderung nötig |
| GET /documents | 10 (unverändert) | | 10 | 14,7 ms | bereits paginiert und gebündelt |
| GET /contacts | 15 | 52,2 ms | 11 | 25,3 ms | fünf Einzelabfragen der Zusammenfassung, jetzt ein UNION ALL |
| GET /properties | 10 (unverändert) | | 10 | 19,9 ms | bereits paginiert |

Nicht in der Tabelle, aber gleich behandelt: `GET /contracts/{id}/deposits` (Bewegungen
aller Kautionen in einer Abfrage) und `GET /accounting/direct-debits` (Lastschriften und
gültige Freigaben aller Läufe in zwei Abfragen statt zwei je Lauf).

## Änderungen

### N+1 entfernt

- `contracts/routers.py`: `_outs`, `_mandates_out`, `_deposits_out` bündeln Debitorenkonten,
  Zahlungen, Fälligkeitsregeln, Bankkonten und Kautionsbewegungen über IN-Listen. Die
  Einzelhelfer `_out`, `_mandate_out`, `_deposit_out` bleiben und delegieren.
- `properties/routers.py`: `_units_out` lädt Schlüsselwerte und USt-Optionen aller Einheiten
  in zwei Abfragen; `session.refresh` je Einheit entfällt in der Liste.
- `contacts/routers.py`: `_parties_out` lädt Mitglieder und Anzeigenamen aller Parteien in einer
  Abfrage. `contacts/services.summaries`: E-Mail, Telefon, Ort, Tags und Typen in einer
  UNION-ALL-Anweisung statt fünf.
- `accounting/routers.py`: `_outs` (Journalzeilen aller Buchungssätze, neue Hilfsfunktion
  `services.entry_lines_of`), `_invoices_full` (Zeilen und Prüfschritte aller Rechnungen).
- `accounting/direct_debit_routers.py`: `_runs_out` mit `direct_debit.orders_of_runs` und
  `direct_debit.valid_approvals_of_runs`.
- `documents/intake_routers.py`: Dokumente aller Vorschläge in einer IN-Abfrage.
- `workspace/routers.py`: Kacheln der Startseite als eine Anweisung mit Skalar-Unterabfragen.

### Paginierung (Muster `GET /tickets`, Antwortform bleibt Liste)

Neue Parameter `page`, `page_size` (zusätzlich zu `limit`; beim Journal bleibt `offset`
erhalten) und Kopfzeilen `X-Total-Count`, `X-Page`, `X-Page-Size` an `GET /contracts`,
`GET /sepa-mandates`, `GET /accounting/ledgers/{id}/entries`, `GET /accounting/invoices`.
Gemeinsame Hilfe `core/pagination.py` (`paginate`, `PAGE_HEADERS`). Standardwerte:
Verträge und Mandate `limit=200` (bisher unbegrenzt), Journal 100, Rechnungen 500 (wie
bisher). Die CRM-Seite `buchhaltung/[id]` blättert das Journal über `?page=`.

### Indizes (Migration 0127, Modelle mit identischen `Index`-Deklarationen, `alembic check` ohne Abweichung)

| Tabelle | Index | Spalten | Verwendung |
| --- | --- | --- | --- |
| contract | ix_contract_tenant_end_date | tenant_id, end_date | Startseite (aktive, endende Verträge), Fristen |
| contract | ix_contract_tenant_termination_date | tenant_id, termination_date | abgeleitete Termine |
| contract | ix_contract_tenant_kind | tenant_id, kind | Vertragsliste nach Art |
| sepa_mandate | ix_sepa_mandate_tenant_status | tenant_id, status | Mandatsliste |
| journal_entry | ix_journal_entry_ledger_status | tenant_id, ledger_id, status | Journalfilter |
| journal_entry | ix_journal_entry_ledger_booking_date | tenant_id, ledger_id, booking_date | Journalzeitraum |
| journal_line | ix_journal_line_journal_entry_id | journal_entry_id | Zeilen je Buchungssatz (bisher ohne Index) |
| journal_line | ix_journal_line_account_id | account_id | Kontenblatt |
| invoice | ix_invoice_tenant_ledger_id | tenant_id, ledger_id | Rechnungseingang je Buchungskreis |
| invoice | ix_invoice_tenant_review_status_date | tenant_id, review_status, invoice_date | Rechnungseingang, Digest |
| invoice_line | ix_invoice_line_invoice_id | invoice_id | Zeilen je Rechnung (bisher ohne Index) |
| invoice_review | ix_invoice_review_invoice_id | invoice_id | Prüfschritte je Rechnung (bisher ohne Index) |
| direct_debit_run | ix_direct_debit_run_tenant_status_date | tenant_id, status, collection_date | Lastschriftläufe |
| document | ix_document_tenant_created_at | tenant_id, created_at | Dokumentliste, neueste zuerst |
| ai_proposal | ix_ai_proposal_tenant_entity_decision | tenant_id, entity_type, decision, created_at | Dokumenteingang, Startseite |
| maintenance_item | ix_maintenance_item_tenant_status_due | tenant_id, status, due_date | Startseite, Erinnerungen |
| property | ix_property_tenant_status | tenant_id, status, management_type | Objektliste |
| contact | ix_contact_tenant_display_name | tenant_id, display_name | Kontaktliste (Sortierung) |

## Offene Punkte

1. Revisionskollision: ein anderer Agent hat `0126_mail_review_fixes.py` (down_revision 0125)
   angelegt. Die Indexmigration ist deshalb `0127_performance_indexes.py` mit down_revision
   0126, nicht 0126 wie beauftragt. Ein Kopf, `alembic upgrade head` und `alembic check`
   laufen sauber. Vor dem Merge prüfen, ob beide Migrationen zusammen ausgeliefert werden.
2. Anmeldung und Mandantenkontext kosten 8 Anweisungen je Aufruf (`core/auth`, außerhalb des
   Prüfbereichs). Ein Cache der Rollen und Berechtigungen je Mitgliedschaft (mit
   Invalidierung bei Rollenänderung) würde jede Liste um 4 bis 5 Anweisungen entlasten.
   Eigentümer: Betreiber, kein Gate betroffen.
   Nachtrag 26.09.2026: umgesetzt in `core/auth/permission_cache.py` (TTL höchstens 30 s,
   Invalidierung bei Rollen- und Rechteänderung, Sperren und Portal-Grants nie gecacht, ADR
   0002 Nachtrag). Kontext bis zur Mandantendomäne: 7 Anweisungen kalt, 3 warm; die Listen der Tabelle oben
   liegen mit warmem Cache 4 Anweisungen niedriger (`GET /contracts` 9 statt 13, `GET
   /properties` 6 statt 10).
3. `GET /contracts` liefert ohne Parameter jetzt höchstens 200 Verträge (bisher alle).
   Aufrufer, die vollständige Listen erwarten, müssen `page`/`page_size` oder `limit` setzen.
   Bekannter Aufrufer: die Seite `vermietung` (Bereich Vermietung, parallel in Bearbeitung,
   nicht geändert); bei mehr als 200 aktiven Mietverträgen wird dort blättern nötig.
   Nachtrag 26.09.2026: die Seite `vermietung` lädt über
   `components/letting/contractOptions.ts` alle Seiten (`page`/`page_size=200`, Ende nach
   `X-Total-Count`), Komponententest `contractOptions.test.ts`.
4. `apps/api/openapi.json` und `packages/api-client/src/schema.d.ts` wurden neu erzeugt und
   enthalten auch die parallel entstandenen Endpunkte anderer Agenten (gemeinsamer
   Arbeitsbaum). `openapi-check` (ADR 0009) meldet keine entfernten Pfade oder Felder.
5. Die Dauerwerte sind Einzelmessungen ohne Aufwärmen und schwanken um 20 bis 40 Prozent
   zwischen Läufen. Eine Lastmessung mit produktionsnahen Datenmengen (869 Einheiten,
   4.600 Kontakte) steht aus.
