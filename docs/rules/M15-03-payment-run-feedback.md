# M15-03 Zahllauf-Vorschau, Sammelaufträge, Auszahlungen ohne Rechnung, Banklimits, Bankrückmeldungen und Fristen je Verfahren

| Field | Content |
| --- | --- |
| ID | `M15-03` |
| Title | Zahllauf-Vorschau je Rechtsträger, Sammelanlage von Auftragsentwürfen, Auszahlung ohne Rechnung, Einzel- und Tageslimit je Auftraggeberkonto, Hinweis Empfängerüberprüfung, Rückmeldung und Abstimmung je Lastschrift, Import pain.002 und camt.054, Einreichungs- und Vorabinformationsfristen als konfigurierbare Prüfung, wöchentliche Vorschau |
| Scope | `mhvp.banking.payment_run`, `mhvp.banking.payment_run_routers` (`/api/v1/accounting/payment-runs`), `mhvp.banking.bank_status`, `mhvp.banking.payment_run_tasks` (Job `mhvp.payments.payment_run`), `mhvp.accounting.direct_debit_feedback`, `mhvp.accounting.direct_debit` (`sequence_lead_block`, `pre_notification_check`), `mhvp.accounting.direct_debit_routers` (`/{run_id}/bank-status`, `/{run_id}/reconciliation`), Sperre in `POST /api/v1/banking/payment-batches`; alle Mandanten; Datei weiter nur hinter G2 |
| Source status | Nachrichtenstruktur pain.002 (`CstmrPmtStsRpt`) und camt.054 (`BkToCstmrDbtCdtNtfctn`) nach den öffentlichen ISO-20022-Schemata (Betreiberentscheidung 2 a vom 30.09.2026); Statuscodes und Rückgabegründe werden wie gemeldet gespeichert, nicht rechtlich gedeutet. Limits, Einreichungsfristen je Verfahren (FRST, RCUR) und Frist der Vorabinformation sind Betreibereingaben aus Bankvereinbarung und Mandat, Quellenstatus zu verifizieren; die Plattform leitet keinen Vorgabewert ab. Empfängerüberprüfung (Verification of Payee) nur als Hinweis, Verfahren der Bank zu verifizieren. Produktschutz: keine Buchung aus Rückmeldungen, Vier-Augen je Auftrag, G2 |
| Acceptance case | D06, D35 bis D38 (bestehend); Tests `apps/api/tests/unit/test_m15_payment_run.py` und `apps/api/tests/integration/test_m15_payment_run.py` |
| Implementation | Migration `0253_payment_run_bank_status` |
| Change reason | Lückenliste 30.09.2026: M15-01, M15-02 (Entscheidung 2 a), M15-03, M15-04, M15-06, M15-07, S15-02 |

## Regeln

- Vorschau (`GET /preview`): gebuchte Rechnungen mit offenem Verbindlichkeitsposten ohne
  aktiven Zahlungsauftrag, fällig bis Stichtag plus Horizont (Vorgabe 7 Tage), gruppiert
  nach Rechtsträger mit dessen nicht getrennten, gültigen Konten und deren Limits.
  Gesperrt angezeigt: fehlende IBAN, unbestätigte abweichende IBAN (PÜ04), Buchungskreis
  nicht führend. Dazu fällige Lastschriftläufe und fehlende Vorabinformationen. Die
  Vorschau legt nichts an.
- Sammelanlage (`POST /orders`): je Rechnung `payments.order_from_invoice` in einem
  Savepoint; Fehler werden je Rechnung gemeldet. Limits erscheinen als Warnung.
- Banklimits (`PUT /bank-limits/{konto}`, Recht `accounting:approve`): Einzelauftragslimit
  und Tageslimit je Auftraggeberkonto. Bei der Zahlungsdatei wird jeder Auftrag über dem
  Einzellimit und jede Summe je Ausführungstag (inklusive bereits ausgegebener Aufträge)
  über dem Tageslimit mit 409 abgelehnt.
- Auszahlung ohne Rechnung (`POST /payout-orders`): nur auf offene Verbindlichkeitsposten
  ohne Rechnung; Empfängerkonto freigegeben (M5-01), gültig und, wenn der Posten einen
  Vertrag hat, Konto eines Mitglieds der Vertragspartei. Kautionsrückzahlung nur vom
  getrennten Kautionskonto, alle anderen Auszahlungen nie davon. Der Freigabe-Snapshot
  enthält zusätzlich das Empfängerkonto.
- Lastschrift-Rückmeldung (`POST /direct-debits/{lauf}/bank-status`): nur für ausgegebene
  Dateien (Status `exported`); Übergänge offen zu angenommen, abgelehnt, eingezogen,
  zurückgegeben; Wiederholung ohne Wirkung. Keine Buchung. Die Abstimmung zeigt je
  Lastschrift den Restbetrag des Postens und einen Befund (Einzug ohne Ausgleich,
  Teileinzug, Rücklastschrift nach Ausgleich mit Hinweis auf Storno).
- Import (`POST /bank-status-reports`): Zuordnung über die Ende-zu-Ende-Referenz zu
  Überweisung oder Lastschrift; pain.002 RJCT setzt nicht ausgeführte Überweisungen auf
  abgelehnt, ACCP/ACSP/ACTC/ACWC/ACSC auf angenommen; camt.054 meldet Einzug, Belastung
  oder Rückgabe. Ausführung einer Überweisung wird nie aus der Meldung abgeleitet (D06),
  Rückgaben werden nicht automatisch storniert. Gleiche Datei (Prüfsumme) ohne Wirkung.
- Fristen je Verfahren: `dd_lead_days_frst` und `dd_lead_days_rcur` sperren beim Anlegen
  eines Laufs jede Lastschrift, deren Einzugsdatum die Frist ab heute unterschreitet;
  `pre_notification_days` sperrt die Vorabinformation, wenn bis zum Einzug weniger Tage
  bleiben. Ohne Eingabe gilt nur die beim Lauf angegebene Vorlauffrist, die
  Vorabinformation meldet dann nur eine Warnung.
- Wöchentliche Vorschau: Job `mhvp.payments.payment_run` montags 08:00, nur für Mandanten
  mit `payment_run_setting.weekly_preview_enabled` (Vorgabe aus); speichert die Vorschau,
  erzeugt keinen Auftrag, keine Datei, keine Buchung.
- B2B-Lastschriften bleiben gesperrt (M15-05, Entscheidung offen): nur CORE-Mandate.
