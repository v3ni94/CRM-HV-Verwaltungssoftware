# AN15 Rücklastschrift mit Nachweis, Forderungsausbuchung als Vorgang

| Feld | Inhalt |
| --- | --- |
| ID | AN15-01 (GAK-101), AN15-02 (GAK-104) |
| Geltungsbereich | `accounting/direct_debit_feedback.py`, `banking/bank_status.py` (camt.054), `accounting/write_offs.py`, `accounting/services.subledger_reconciliation`, `accounting/report_views.py`, Migration 0454 |
| Quellenstatus (Anhang C) | Fachliche Umsetzung und Produktschutz aus 7.1 B03, B07, B08 und 7.3 (Rücklastschrift, Ausbuchung); keine Rechtsregel. Weiterbelastung von Gebühren und Rechtsgrund der Ausbuchung sind offene Entscheidungen (AN15-01, AN15-02) |
| Abnahmefall (Anhang D) | kein eigener Fall; Integrationstest `tests/integration/test_an15_return_writeoff.py` |
| Änderungsgrund | GAK-101: der Einzugsverweis wurde bei der Rückgabe überschrieben, Rückgabedatum und Gebühr fehlten. GAK-104: `written_off` war ein Kennzeichen ohne Datum, Grund und Urheber, rückwirkend für alle Stichtage |

## Regel

1. Eine Rücklastschrift lässt `bank_transaction_id` (Einzug) unverändert; der Rückbelastungsumsatz steht in `return_transaction_id`, das Rückgabedatum der Bank in `returned_on` (Eingabe oder Buchungstag des Umsatzes beziehungsweise `BookgDt` aus camt.054), die tatsächliche Gebühr in `return_fee_amount` (NUMERIC(14,2), nicht negativ) mit Beleg `return_fee_document_id`.
2. Erfasste Angaben werden nur ergänzt, nie ersetzt (abweichender Wert 409); Wiederholung mit gleichen Werten ohne Wirkung (B08). Rückgabedatum nie in der Zukunft.
3. Die Gebühr wird nie automatisch weiterbelastet oder gebucht. Mit Schalter `return_fee_pass_on_enabled` zeigt die Abstimmung `return_fee_pass_on = proposal`, sonst `locked`.
4. Eine Ausbuchung entsteht nur als Vorschlag (`open_item_write_off`) mit Grund (mindestens 10 Zeichen), Stichtag (nicht in der Zukunft, nicht vor Entstehung), Restbetrag zum Stichtag, Beleg und Urheber; ein aktiver Vorschlag je Posten; nur Forderungen.
5. Freigabe nur mit Schalter `write_off_approval_enabled`, offenem G1, durch eine andere Person als die vorschlagende, mit offener Periode. Sie setzt `written_off`, `written_off_on`, `written_off_at`, `written_off_reason`, `written_off_by`; der Datenbankwächter macht diese Felder danach unveränderlich. Es wird nichts gebucht.
6. Auswertungen (Nebenbuchprüfung, Soll-Ist je Zeitraum) behandeln einen Posten erst ab `written_off_on` als ausgebucht (B07).

## Ergänzung AO01 (Welle 25)

7. Auswahlen von Lastschrift, Guthabenauszahlung (Verrechnung mit Forderungen) und KI-Nachschlagewerkzeug lesen das Kennzeichen stichtagsbezogen (`not_written_off_as_of`): ausgebucht erst ab `written_off_on`; ein altes Kennzeichen ohne Datum gilt für jeden Stichtag.
8. Der Prüfexport (Formatversion 2) enthält in `offene_posten` die Spalte "Ausgebucht am"; `meta.format_version` ist 2.
9. `GET /accounting/open-item-write-offs/{id}/posting-preview` zeigt nur an: Haben Forderungskonto in Höhe des Vorschlagsbetrags, Soll offen (AN15-02). `posting_allowed` ist immer falsch, auch bei offenem G1; eine spätere Buchung würde nie überschreiben, Korrektur nur per Storno.
10. Rücknahme einer Freigabe ist nur vorbereitet: Schalter `accounting.write_off_revocation` in `tenant_settings.sources` (Standard aus); Status `revocation_status` `locked` oder `awaiting_decision`; keine Route, AN15-02 bleibt offen.
11. AO12-04: vor der Freigabe wird der Restbetrag zum Stichtag erneut berechnet; weicht er vom Vorschlag ab, 409 `MHVP-ACC-0042`. AO12-05: Vorschlag und Freigabe nur durch eine Person (`MHVP-ACC-0043`, 403); ein alter Vorschlag ohne Person kann nicht freigegeben werden.
12. CRM: Ausbuchungsvorschläge im Buchungskreis unter den offenen Posten (anlegen, Freigabe per GatedAction G1, ablehnen, Buchungsvorschau); Rücklastschrift-Nachweis und Weiterbelastungsstatus in der Lastschriftabstimmung.
