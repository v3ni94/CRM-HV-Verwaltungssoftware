# Runbook Zahllauf-Test mit dem Bank-Testsystem (M15-03, V2)

Ziel: einen synthetischen Zahllauf (Überweisungen pain.001 und Basislastschriften
pain.008) durch alle Stufen bis zur Datei führen und die Datei gegen das Testsystem der Bank
prüfen. Der Test bewegt kein Geld. G2 bleibt geschlossen; für den Test wird ein eigener
Testmandant mit geöffnetem G2 verwendet, nie ein produktiver Mandant.

## Voraussetzungen

- Bank-Testsystem oder Testzugang der Bank (V2, Betreiber beschafft). Ohne Testsystem endet
  der Test bei Schritt 6 (Dateiprüfung gegen das XSD).
- Mit der Bank abgestimmte Formatversion je Konto: pain.001.001.03 oder pain.001.001.09,
  pain.008.001.02 (pain.008.001.08 ist konfigurierbar, wird aber noch nicht erzeugt).
- Testmandant auf Staging, Bankkonto mit IBAN und BIC des Testsystems, Buchungskreis mit
  `leading_system = mhvp`, Gläubiger-Identifikationsnummer des Testsystems.
- Zwei Personen mit Freigaberecht (`accounting:approve`), keine Plattformadministratoren.

## Automatisierter Vorlauf

Der Ablauf ist als Test hinterlegt und läuft in der CI:
`apps/api/tests/integration/test_m15_payment_submission.py` (10 Überweisungen, 10
Lastschriften mit Mandaten, Vier-Augen, Datei, XSD-Prüfung, Download-Protokoll, manuelle
Einreichung). Lokal:

```
cd apps/api && uv run pytest tests/integration/test_m15_payment_submission.py tests/unit/test_pain001_versions.py --no-cov -p no:cacheprovider
```

## Ablauf mit dem Bank-Testsystem

1. Format je Konto setzen: `PUT /api/v1/banking/payment-bank-config/{account_id}` mit
   `pain001_version`, `pain008_version`, `submission_channel = file`,
   `confirmed_with_bank_on` und einer Notiz, wer die Version bei der Bank bestätigt hat.
2. Überweisungen: zehn Testrechnungen freigeben und buchen, je Rechnung
   `POST /api/v1/banking/payment-orders`, Freigabe durch zwei Personen
   (`.../approve`). Empfängerkonten nur Testkonten des Bank-Testsystems.
3. Sammler: `POST /api/v1/banking/payment-batches` mit allen Auftrags-IDs. Antwort
   prüfen: `transaction_count = 10`, `control_sum` gleich Summe der Aufträge,
   `file_sha256`, `status = file_generated`. Die Datei ist als Dokument abgelegt.
4. Download: `GET /api/v1/banking/payment-batches/{id}/file`. Header `X-Content-SHA256`
   mit `file_sha256` vergleichen. Jeder Download steht im Protokoll
   (`GET /api/v1/banking/payment-batches/{id}`, Feld `downloads`).
5. Lastschriften: Vorschau `POST /api/v1/accounting/direct-debits/preview`, Lauf anlegen,
   zwei Freigaben, `POST .../{run_id}/file`, Download `GET .../{run_id}/file`.
6. Dateiprüfung: beide Dateien gegen die XSDs in `apps/api/tests/data/iso20022/` prüfen
   (Testlauf oben) und zusätzlich mit dem Prüfwerkzeug der Bank (Format-Checker im
   Testsystem oder Onlinebanking-Upload im Testmodus).
7. Einreichung im Testsystem: Datei manuell hochladen, Protokollnummer notieren.
8. Einreichung bestätigen: `POST /api/v1/banking/payment-batches/{id}/submit` mit
   `{"reference": "<Protokollnummer>"}`. Status wird `submitted`, Aufträge `submitted`.
   Ohne vorherigen Download wird die Bestätigung abgelehnt (`MHVP-BANK-0018`).
9. Rückmeldung: Ablehnungen des Testsystems über
   `POST /api/v1/banking/payment-batches/{id}/bank-status` erfassen. Ausführung nur über
   den importierten Testkontoauszug (CAMT) nachweisen (D06); offene Posten bleiben bis dahin
   offen.
10. Ergebnis dokumentieren: Datum, Bank, Formatversion, Protokollnummern, Abweichungen.
    Abweichungen des Bank-Testsystems vom XSD (bankspezifische Einschränkungen, Zeichensatz)
    als Punkt zu M15-01 in `docs/OPEN_QUESTIONS.md` eintragen.

## Abbruchkriterien

- Prüfsumme der abgelegten Datei weicht ab (`MHVP-BANK-0018`): Datei nicht verwenden,
  Vorgang an die Geschäftsführung.
- Testsystem lehnt das Format ab: Version in der Kontokonfiguration prüfen, Ablehnungstext
  sichern, Betreiber entscheidet mit der Bank (M15-01).
- Freigabe durch nur eine Person oder Plattformadministrator: Sammler wird nicht erzeugt
  (`MHVP-GATE-0002`), so gewollt.

## Nach dem Test

- Testmandant: G2 wieder schließen, Testkonten und Zugänge dokumentiert löschen.
- Ergebnis an den Betreiber für die Abnahme M15 (`docs/OPEN_QUESTIONS.md`, M15-03).
