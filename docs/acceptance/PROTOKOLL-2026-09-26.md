# Abnahmeprotokoll Anhang D.3, Stand 26.09.2026

Aufgabe A01 aus `docs/plans/LUECKENLISTE-2026-09-26.md`. Format nach `docs/MASTER-PROMPT.md` Anhang D.3 und der Vorlage in `docs/acceptance/D-cases.md`. Softwarestand: Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0. Datenbank PostgreSQL und Redis lokal; Tests mit `--no-cov`.

Geltung: Dieses Protokoll dokumentiert die technische Ausführung der vorhandenen Tests mit Fallkennung. Es ist keine fachliche Abnahme. Die Bestätigung der Sollwerte und Sonderfälle durch die fachkundige Person (V16, `docs/OPEN_QUESTIONS.md`) und die Freigabe der Rechtsstände (P01 bis P03, V23) sind für alle Fälle offen. Alle Freigabestufen G1 bis G5 bleiben geschlossen. Kein Sollwert wurde an das Ist-Ergebnis angepasst. Sämtliche Eingaben sind synthetische Modellwerte aus Anhang D, keine Echtdaten.

Regelversion: Nur H04 (CO2) trägt eine Versionskennung im Code. Für alle übrigen Regeln wird die Regeldatei in `docs/rules/` mit Status aus dem Register (`implemented, not accepted`) und der Stand der Datei (23.09.2026) angegeben; eine formale Versionsnummer je Regel fehlt und ist als Auffälligkeit unten vermerkt.

Gesamtergebnis: 15 Tests ausgeführt, 15 bestanden (`15 passed in 28.99s`). Fachliche Bewertung je Fall: 9 technisch bestanden (D01, D03, D04, D05, D07, D08, D10, D12, D16), 6 teilweise (D02, D06, D13, D14, D15, D56), 1 nicht ausgeführt (D17, kein Test vorhanden), 0 fehlgeschlagen.

Sammelbefehl:

```
cd apps/api && uv run pytest \
  tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03 \
  tests/integration/test_m10_ledger.py::test_ledger_per_legal_entity_open_items_and_reversal \
  tests/integration/test_m10_ledger.py::test_transfer_opening_balance_lock_and_gate \
  tests/integration/test_m11_banking.py::test_camt_import_identity_transfer_and_reconciliation \
  tests/integration/test_m11_finapi.py::test_connect_multiple_accounts_assign_and_partial_failure \
  tests/integration/test_m15_payments.py::test_payment_run \
  tests/integration/test_m17_operating_costs.py::test_d08_d10_units \
  tests/integration/test_m17_operating_costs.py::test_operating_cost_statement \
  tests/integration/test_m14_invoices.py::test_invoice_review_release_post_and_d12 \
  tests/unit/test_m5_rules.py::test_rental_statement_path \
  tests/unit/test_m5_rules.py::test_hoa_statement_needs_resolution_on_this_snapshot \
  tests/integration/test_m5_contracts.py::test_rental_tenancy_lifecycle \
  tests/integration/test_m5_contracts.py::test_ownership_transfer_and_sev \
  tests/integration/test_m5_contracts.py::test_mandates_direct_debit_and_deposits \
  tests/integration/test_m4_properties.py::test_bank_accounts_follow_legal_entities \
  -q --no-cov
```

Gliederung: Abschnitt 1 (bis einschließlich „Auffälligkeiten“) protokolliert den ersten Lauf zu D01 bis D17 und D56; Abschnitt 2 am Ende der Datei ergänzt die Fälle D17 bis D58 mit neuen Tests (Arbeitsstand 1.20.0 vor Commit).

## Übersicht

| Kennung | Test | Ergebnis Test | Status Fall |
| --- | --- | --- | --- |
| D01 | `tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03` | bestanden | technisch bestanden |
| D02 | `tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03` | bestanden | teilweise (Auszahlungsverbot nicht geprüft) |
| D03 | `tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03` | bestanden | technisch bestanden |
| D04 | `tests/integration/test_m10_ledger.py::test_transfer_opening_balance_lock_and_gate`, `tests/integration/test_m11_banking.py::test_camt_import_identity_transfer_and_reconciliation` | bestanden | technisch bestanden |
| D05 | `tests/integration/test_m11_banking.py::test_camt_import_identity_transfer_and_reconciliation`, `tests/integration/test_m11_finapi.py::test_connect_multiple_accounts_assign_and_partial_failure` | bestanden | technisch bestanden |
| D06 | `tests/integration/test_m15_payments.py::test_payment_run` | bestanden | teilweise (Skontovariante, Bankbestand bei Export nicht geprüft) |
| D07 | `tests/integration/test_m10_ledger.py::test_ledger_per_legal_entity_open_items_and_reversal` | bestanden | technisch bestanden |
| D08 | `tests/integration/test_m17_operating_costs.py::test_d08_d10_units` | bestanden | technisch bestanden |
| D10 | `tests/integration/test_m17_operating_costs.py::test_operating_cost_statement` | bestanden | technisch bestanden |
| D12 | `tests/integration/test_m14_invoices.py::test_invoice_review_release_post_and_d12` | bestanden | technisch bestanden |
| D13 | `tests/unit/test_m5_rules.py::test_hoa_statement_needs_resolution_on_this_snapshot`, `tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03` | bestanden | teilweise (nur Statusmodell) |
| D14 | `tests/unit/test_m5_rules.py::test_hoa_statement_needs_resolution_on_this_snapshot`, `tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03` | bestanden | teilweise (Differenzanzeige nicht geprüft) |
| D15 | `tests/integration/test_m5_contracts.py::test_rental_tenancy_lifecycle`, `tests/integration/test_m5_contracts.py::test_ownership_transfer_and_sev` | bestanden | teilweise (nur Schema, M24-Logik offen) |
| D16 | `tests/integration/test_m5_contracts.py::test_ownership_transfer_and_sev` | bestanden | technisch bestanden |
| D17 | kein Test | nicht ausgeführt | nicht ausgeführt |
| D56 | `tests/integration/test_m4_properties.py::test_bank_accounts_follow_legal_entities` | bestanden | teilweise (nur Schema, Buchungsseite offen) |

Alle Fälle: fachliche Bestätigung offen (V16).

## Einzelprotokolle

### D01

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D01 |
| Geprüfte Regelversion | W05 (`docs/rules/W05-hoa-result.md`, Status implemented, not accepted; Quellen R04, P01 offen), W06 (`docs/rules/W06-resolution.md`); keine Regelversionsnummer im Code, Stand der Regeldatei 23.09.2026 |
| Fachliche Annahmen | Wie Anhang D: kein Eigentümerwechsel, keine Rücklagen- oder Sonderumlagenkomponente, Beschlussgrundlage wird im Test nach der Berechnung erfasst (W06). Testvereinfachung laut Testkommentar: ein gebuchter Monat trägt den gesamten beschlossenen Vorschuss 2.800,00 EUR. `docs/ASSUMPTIONS.md` enthält keine eigene Annahme zu D01; P01 (Rechtsprechung Abrechnungsspitze) offen. |
| Anonymisierte Eingaben | WEG-Modellobjekt, Jahr 2025, MEA 3.000/2.500 von 5.500, Gesamtkosten 5.500,00 EUR; Einheit 01: Kostenanteil 3.000,00 EUR, beschlossene Soll-Vorschüsse 2.800,00 EUR, gezahlt 2.500,00 EUR. |
| Erwartetes Ergebnis | Abrechnungsspitze 200,00 EUR; Vorschussrückstand 300,00 EUR; Gesamtbelastung als Information 500,00 EUR; keine neue Forderung 500,00 EUR zusätzlich zum Rückstand. |
| Tatsächlich beobachtetes Ergebnis | Snapshot Einheit 01: cost_share 3.000,00, advances_resolved 2.800,00, advances_paid 2.500,00, result 200,00, arrears 300,00, information_total 500,00. Beschlussbindung: Übergang nach `resolved` nur mit Beschluss auf genau diesem Snapshot; Ausgabe hinter G4 (403). |
| Differenz | Keine. Nicht geprüft: Verbuchung der Spitze als Forderung (Buchung hinter G4, Test prüft 403). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03 -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

### D02

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D02 |
| Geprüfte Regelversion | W05 (`docs/rules/W05-hoa-result.md`, Status implemented, not accepted; Quellen R04, P01 offen), W06 (`docs/rules/W06-resolution.md`); keine Regelversionsnummer im Code, Stand der Regeldatei 23.09.2026 |
| Fachliche Annahmen | Wie D01. Der Test prüft die Rechenwerte und die getrennte Ausweisung; er enthält keine Zusicherung, dass keine automatische Auszahlung von 300,00 EUR ausgelöst wird, und keine Prüfung des Fortbestands der Altforderung als offener Posten. |
| Anonymisierte Eingaben | Einheit 02 desselben Modellobjekts: Kostenanteil 2.500,00 EUR, Soll-Vorschüsse 2.800,00 EUR, gezahlt 2.500,00 EUR. |
| Erwartetes Ergebnis | Abrechnungsanpassung -300,00 EUR; Vorschussrückstand 300,00 EUR getrennt; rechnerisch 0,00 EUR; keine automatische Auszahlung, keine Löschung der Altforderung. |
| Tatsächlich beobachtetes Ergebnis | Snapshot Einheit 02: cost_share 2.500,00, result -300,00, arrears 300,00, information_total 0,00. |
| Differenz | Lücke: Verbot der automatischen Auszahlung und Fortbestand der Altforderung als offener Posten sind nicht als eigene Zusicherung getestet. Rechtlich zulässige Verrechnung ist laut Anhang D eigenständig zu prüfen (P01). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03 -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | teilweise, fachliche Bestätigung offen (V16) |

### D03

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D03 |
| Geprüfte Regelversion | W08 (Registereintrag `docs/rules/README.md`: implemented (M24), D03 tested; keine eigene Regeldatei, keine Regelversionsnummer) |
| Fachliche Annahmen | Wie Anhang D. Rücklagenbewegungen werden als Eingabewerte des Abrechnungsentwurfs erfasst (reserve_opening, reserve_withdrawals, reserve_interest); Zahlungseingänge aus den gebuchten Beiträgen. |
| Anonymisierte Eingaben | Anfangsbestand 20.000,00 EUR; Soll-Zuführung 6.000,00 EUR; eingegangen 4.500,00 EUR; Entnahme 3.000,00 EUR; Nettozins 100,00 EUR. |
| Erwartetes Ergebnis | Tatsächlicher Bestand 21.600,00 EUR; offene Beiträge 1.500,00 EUR separat; nicht 23.100,00 EUR. |
| Tatsächlich beobachtetes Ergebnis | reserve.closing 21.600,00; contributions_open 1.500,00; contributions_resolved 6.000,00. |
| Differenz | Keine bei den Rechenwerten. Nicht Gegenstand des Tests: Abstimmung Bank- und Mittelzuordnung (W04 Überleitung, Aufgabe A60). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03 -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

### D04

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D04 |
| Geprüfte Regelversion | B09 (`docs/rules/B09.md`, Abnahmefall D04) und B01; Bankseite: Annahme Bankumsatz-Identität und interne Umbuchung in `docs/ASSUMPTIONS.md` (Zeile 264, M11); keine Regelversionsnummer |
| Fachliche Annahmen | Interne Umbuchung als Buchungsart `bank_transfer` zwischen zwei Bankkonten desselben Rechtsträgers; im Bankimport wird die Gegenbuchung anhand IBAN, Betrag und Zeitnähe gepaart (transfer_pair_id). |
| Anonymisierte Eingaben | Buchungskreis-Test: Anfangsbestände Bank A 10.000,00 EUR, Bank B 20.000,00 EUR, Umbuchung 1.000,00 EUR am 01.02.2026. Bankimport-Test: synthetische CAMT.053-Dateien für A (Abgang 1.000,00 EUR) und B (Zugang 1.000,00 EUR). |
| Erwartetes Ergebnis | A 9.000,00 EUR, B 21.000,00 EUR, Summe 30.000,00 EUR; keine Ausgabe oder Einnahme; keine zweite Wirkung; keine Rücklagenzuführung. |
| Tatsächlich beobachtetes Ergebnis | Saldenliste: 001200 = 9.000,00, 001202 = 21.000,00, Summe 30.000,00, keine Konten der Kategorien cost oder revenue mit Bewegung. Bankimport: Import B zählt transfers = 1, Zugang auf B trägt transfer_pair_id des Abgangs auf A; Wiederimport der Datei A ergibt new = 0. |
| Differenz | Keine. Hinweis: dass keine Rücklagenzuführung entsteht, ist nur mittelbar geprüft (keine Ertrags- oder Kostenbewegung); eine Zusicherung am Rücklagenkonto fehlt. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m10_ledger.py::test_transfer_opening_balance_lock_and_gate tests/integration/test_m11_banking.py::test_camt_import_identity_transfer_and_reconciliation -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

### D05

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D05 |
| Geprüfte Regelversion | M11-finapi-dedup (`docs/rules/M11-finapi-dedup.md`, D05) und Annahme Bankumsatz-Identität (`docs/ASSUMPTIONS.md` Zeile 264: Bankreferenz AcctSvcrRef, ersatzweise NtryRef oder TxId); keine Regelversionsnummer |
| Fachliche Annahmen | Beide Zahlungen tragen unterschiedliche Bankreferenzen (REF-1, REF-2) und sind damit im Bankdatensatz unterscheidbar; ohne Referenz landet ein inhaltsgleicher Umsatz in der Prüfung und wird nie verworfen (Zusatzprüfung im selben Test). |
| Anonymisierte Eingaben | CAMT.053 mit zwei Gutschriften je 400,00 EUR, gleicher Zahler, Tag 05.01.2026, Verwendungszweck Hausgeld Januar; anschließend derselbe Datei-Import erneut. finAPI-Variante: zwei Umsätze je 700,00 EUR mit Referenzen tx-1 und tx-2, zweiter Abruf. |
| Erwartetes Ergebnis | Zunächst 800,00 EUR aus zwei Zahlungen; nach Wiederimport weiterhin 800,00 EUR (weder 400,00 noch 1.600,00 EUR). |
| Tatsächlich beobachtetes Ergebnis | Erstimport new = 3 (inklusive Umbuchung), possible_duplicates = 1 (Prüfhinweis, keine Verwerfung); Wiederimport new = 0, duplicates = 3; Summe der Gutschriften auf Konto A 800,00 EUR; finAPI: zwei Umsätze bleiben nach erneutem Abruf zwei. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m11_banking.py::test_camt_import_identity_transfer_and_reconciliation tests/integration/test_m11_finapi.py::test_connect_multiple_accounts_assign_and_partial_failure -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

### D06

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D06 |
| Geprüfte Regelversion | M11-06 (`docs/rules/M11-06-payment-proposal-only-until-g2.md`), B08; Annahme Zahlungsauftrag und Skonto in `docs/ASSUMPTIONS.md` Zeile 308; keine Regelversionsnummer |
| Fachliche Annahmen | G2 ist geschlossen und wird im Test durch einen Test-Resolver geöffnet; nur das führende System darf zahlen (13.1). Abweichend vom Fall nutzt der Test eine Rechnung mit Skonto 2 %: Zahlbetrag 1.166,20 EUR, Skonto 23,80 EUR, Ausgleich insgesamt 1.190,00 EUR. |
| Anonymisierte Eingaben | Freigegebene Rechnung Z-1 über 1.190,00 EUR (Skonto 2 % bis Skontodatum), Zahlungsauftrag mit Vier-Augen-Freigabe, Sammler pain.001.001.09, Status submitted, dann executed mit Nachweis durch importierten Bankumsatz D-1 (1.166,20 EUR), Rückmeldung executed ein zweites Mal. |
| Erwartetes Ergebnis | Bei Export und Einreichung bleibt die Verbindlichkeit offen und der Bankbestand unverändert; Ausführung mit Nachweis gleicht einmalig 1.190,00 EUR aus; doppelte Rückmeldung erzeugt keinen zweiten Ausgleich. |
| Tatsächlich beobachtetes Ergebnis | Nach Export offener Posten 1.190,00 EUR; nach submitted weiterhin 1.190,00 EUR; executed ohne Nachweis abgelehnt (422); executed mit Bankumsatz: offener Posten leer, Saldo 027000 = -23,80 (Skonto), 001210 = -1.166,20; zweite Rückmeldung liefert dieselbe journal_entry_id. |
| Differenz | Teilweise: Eingabe weicht ab (Skontovariante statt glatter 1.190,00 EUR Zahlung); der unveränderte Bankbestand bei Export und Einreichung ist nicht als eigene Zusicherung geprüft (nur der offene Posten). Ergänzung im Rahmen B08 (G2) oder als Zusatztest empfohlen. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m15_payments.py::test_payment_run -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | teilweise, fachliche Bestätigung offen (V16) |

### D07

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D07 |
| Geprüfte Regelversion | B07 (`docs/rules/B07.md`, Abnahmefall D07), B08 (Ausgleich nie über Restbetrag); keine Regelversionsnummer |
| Fachliche Annahmen | Eindeutiger Schuldner und Tilgungszweck; Überzahlung wird nicht als Ausgleich über den Restbetrag zugelassen (422), sondern mit Ausgleich 400,00 EUR gebucht, der Überschuss 50,00 EUR bleibt als Guthaben auf dem Personenkonto. |
| Anonymisierte Eingaben | Forderung 1.000,00 EUR fällig 03.01.2026; Zahlung 600,00 EUR am 10.01.2026; Zahlung 450,00 EUR am 20.01.2026. |
| Erwartetes Ergebnis | Nach Zahlung 1 Rest-OP 400,00 EUR; danach Forderung ausgeglichen, 50,00 EUR gesondertes Guthaben, nicht als Ertrag. |
| Tatsächlich beobachtetes Ergebnis | Rest-OP am 10.01.2026 = 400,00 EUR; Versuch, 450,00 EUR auf 400,00 EUR Rest auszugleichen: 422; Buchung mit Ausgleich 400,00 EUR: offene Posten am 31.01.2026 leer, Stichtag 15.01.2026 weiterhin 400,00 EUR (B07); Saldenliste: Ertragskonto 060100 = -1.000,00 (kein Zusatzertrag), Personenkonto -50,00 (Guthaben), Bank 001200 = 1.050,00. |
| Differenz | Keine. Folgefälle Rückgabe und Erstattung sind laut Anhang D separat und nicht Gegenstand dieses Tests. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m10_ledger.py::test_ledger_per_legal_entity_open_items_and_reversal -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

### D08

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D08 |
| Geprüfte Regelversion | B06 Restcentverteilung (`docs/rules/D08-rest-cents.md`, Produktstandard 6.9.8: Abrunden auf Cent, größter Rest, Gleichstand nach stabilem Schlüssel Einheitsnummer und Nutzerschlüssel); Annahme `docs/ASSUMPTIONS.md` Zeile 498 (über D08 hinaus nur Produktstandard) |
| Fachliche Annahmen | Keine abweichende Vorschrift; Zuordnung des Restcents nach vorab bestimmtem stabilem Schlüssel, nicht nach Bildschirmreihenfolge. |
| Anonymisierte Eingaben | 100,00 EUR; drei Anteile mit identischem Gewicht 1; Eingabereihenfolge 02, 01, 03 und danach 03, 01, 02. |
| Erwartetes Ergebnis | Ein Anteil 33,34 EUR, zwei Anteile 33,33 EUR, Summe 100,00 EUR; Umordnen wechselt nicht den begünstigten Datensatz. |
| Tatsächlich beobachtetes Ergebnis | Einheit 01 = 33,34, Einheit 02 = 33,33, Einheit 03 = 33,33; Ergebnis bei umgekehrter Reihenfolge identisch. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m17_operating_costs.py::test_d08_d10_units -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

### D10

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D10 |
| Geprüfte Regelversion | H04 (`docs/rules/H04-co2.md`), Regelversion `CO2KostAufG-Anlage-residential-2026-09-23` (`mhvp.billing.calc.CO2_RULE_VERSION`); Quelle Anhang C R15, Prüfung gegen den amtlichen Text durch den Betreiber offen (M17-02), nicht freigegeben |
| Fachliche Annahmen | Wohngebäude-Regelfall ohne Ausnahmen; Eingangswert wird nicht vorzeitig gerundet (Vergleichswert 11,9 im Test, nicht 11,99). |
| Anonymisierte Eingaben | Endpunkt `/api/v1/statements/co2-split`: spezifischer Ausstoß 12,0 kg CO2/m²/a, Kosten 100,00 EUR; Vergleich 11,9 kg, 100,00 EUR. |
| Erwartetes Ergebnis | Stufe 12 bis unter 17: Mieter 90,00 EUR, Vermieter 10,00 EUR; unter 12: 100/0. |
| Tatsächlich beobachtetes Ergebnis | 12,0: tenant = 90,00; 11,9: landlord = 0,00. |
| Differenz | Keine bei den Stufenwerten. Gesetzliche Berechnung und Rundung des Eingangswerts sind laut Anhang D separat zu testen und hier nicht enthalten; Freigabe des Rechtsstands offen (M17-02, B12). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m17_operating_costs.py::test_operating_cost_statement -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

### D12

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D12 |
| Geprüfte Regelversion | Annahme Abschlag und Schlussrechnung in `docs/ASSUMPTIONS.md` Zeile 297 (Bruttobuchung ohne Umsatzsteueroption; Schlussrechnung bucht nur die verbleibende Wirkung nach Abzug gebuchter Abschläge desselben Ausstellers); keine eigene Regeldatei, keine Regelversionsnummer |
| Fachliche Annahmen | Buchungskreis ohne Umsatzsteueroption; Abschlag AB-1 ist geprüft, freigegeben und gebucht; Schlussrechnung SR-1 weist den Abschlag als Abzug aus (deductions). |
| Anonymisierte Eingaben | Abschlag AB-1: netto 2.000,00, USt 380,00, brutto 2.380,00 EUR; Schlussrechnung SR-1: netto 5.000,00, USt 950,00, brutto 5.950,00 EUR, Abzug 2.380,00 EUR; Sachkonto 041400. |
| Erwartetes Ergebnis | Verbleibende Zahlungsverpflichtung 3.570,00 EUR; Leistungssumme 5.950,00 EUR, nicht 8.330,00 EUR. |
| Tatsächlich beobachtetes Ergebnis | Saldo 041400 = 5.950,00; offene Kreditorenposten 2.380,00 (Abschlag, im Test nicht bezahlt) und 3.570,00 (Schlussrechnung) neben 1.190,00 aus einem anderen Teil des Tests; Konsistenzprüfung ok. |
| Differenz | Abweichung zur Eingabe: der Abschlag ist gebucht, aber im Test nicht bezahlt (Fall setzt bezahlt voraus); der Ausgleich der offenen Posten wird nicht geprüft. Buchung, Steuer und Zahlung sind laut Anhang D je Rechenwerk separat zu testen; Steuerbehandlung mit Option bleibt offen (B06). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m14_invoices.py::test_invoice_review_release_post_and_d12 -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

### D13

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D13 |
| Geprüfte Regelversion | W06 (`docs/rules/W06-resolution.md`) und Statusmodell 6.9.3 in `mhvp.billing.status`; keine Regelversionsnummer |
| Fachliche Annahmen | Statusmodell: Übergang DUE nach POSTED für WEG-Abrechnungen nur mit Beschlussstatus final; angefochtener Beschluss (contested) blockiert. Der Unit-Test prüft nur den Statusübergang, nicht die Sollstellung oder Lastschrift. |
| Anonymisierte Eingaben | Reiner Regeltest: check_transition(DUE, POSTED, is_hoa=True, resolution_status=contested) und mit final; Integrationstest: Ausgabe der Abrechnung ohne G4 abgelehnt (403). |
| Erwartetes Ergebnis | Keine neue beschlussabhängige Forderung und keine Lastschrift ohne wirksamen Beschluss. |
| Tatsächlich beobachtetes Ergebnis | Übergang mit contested löst TransitionError mit Kennung D13 aus; mit final ist er erlaubt. Ausgabe ohne G4: 403. |
| Differenz | Lücke: Es wird nicht geprüft, dass ohne wirksamen Beschluss keine Sollstellung (M13) und keine Lastschrift (M15) aus der Abrechnung entsteht; Abdeckung nur auf Ebene des Statusmodells. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/unit/test_m5_rules.py::test_hoa_statement_needs_resolution_on_this_snapshot tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03 -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | teilweise, fachliche Bestätigung offen (V16) |

### D14

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D14 |
| Geprüfte Regelversion | W06 (`docs/rules/W06-resolution.md`: Beschluss nur mit Snapshot-Hash der berechneten Version, neue Version trägt den Beschluss nie); keine Regelversionsnummer |
| Fachliche Annahmen | Ergebnisversion ist über den Snapshot-Hash identifiziert; ein Beschluss auf einem anderen Hash wird beim Übergang nach resolved abgelehnt. |
| Anonymisierte Eingaben | Unit-Test: check_transition(BOARD_REVIEWED, RESOLVED, is_hoa=True) ohne und mit resolution_snapshot_matches; Integrationstest: Beschluss mit Hash 0...0 auf der Abrechnung, Übergang nach resolved mit diesem Beschluss. |
| Erwartetes Ergebnis | Beschluss wird nicht automatisch auf andere Zahlen umgehängt; Differenz und erneuter Entscheidungsschritt sichtbar. |
| Tatsächlich beobachtetes Ergebnis | Ohne passenden Snapshot: TransitionError mit Kennung D14; mit Übereinstimmung erlaubt. Integrationstest: Beschluss mit falschem Hash wird beim Übergang abgelehnt, zweiter Beschluss mit richtigem Hash (Nummer 2) erlaubt den Übergang. |
| Differenz | Lücke: Der Fall einer nach Beschluss geänderten Ergebnisversion (neue Berechnung nach resolved) mit sichtbarer Differenz ist nicht getestet; geprüft ist nur die Ablehnung eines nicht passenden Beschlusses. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/unit/test_m5_rules.py::test_hoa_statement_needs_resolution_on_this_snapshot tests/integration/test_m24_hoa.py::test_hoa_statement_d01_d03 -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | teilweise, fachliche Bestätigung offen (V16) |

### D15

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D15 |
| Geprüfte Regelversion | B01 (`docs/rules/B01.md`) und Schema 6.9 (Personenkonto je Vertrag); W07 Eigentümerwechsel in `docs/rules/README.md` offen (M24-01); Quelle P01 offen |
| Fachliche Annahmen | Nur Schema-Teil (M5): jeder Vertrag erhält ein eigenes Personenkonto; beim Eigentümerwechsel entsteht ein neuer Vertrag mit neuem Personenkonto, der alte Vertrag endet am Vortag der Eigentumsumschreibung. Die M24-Logik (Spitze beim maßgeblichen Eigentümer, alter Rückstand beim alten Schuldner in der Abrechnung) ist nicht getestet. |
| Anonymisierte Eingaben | Mietvertrag mit Personenkonto 090000; Eigentumsvertrag Verkäufer ab 01.01.2020, Eigentümerwechsel an Käufer mit Eigentumsumschreibung 01.04.2026. |
| Erwartetes Ergebnis | Alter Vorschussrückstand beim bisherigen Schuldner; Abrechnungsspitze beim rechtlich maßgeblichen Eigentümer; Kaufvertragsausgleich getrennt. |
| Tatsächlich beobachtetes Ergebnis | Neuer Vertrag mit party_id Käufer, start_date 01.04.2026, eigenes Personenkonto 090001 (ungleich dem des Verkäufers); alter Vertrag end_date 31.03.2026, Zahlung valid_to 31.03.2026. |
| Differenz | Lücke: Zuordnung der Abrechnungsspitze und des Rückstands in der WEG-Abrechnung nach Eigentümerwechsel ist nicht getestet (W07 offen, M24-01, P01). Getrennte Personenkonten sind die technische Voraussetzung. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m5_contracts.py::test_rental_tenancy_lifecycle tests/integration/test_m5_contracts.py::test_ownership_transfer_and_sev -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | teilweise, fachliche Bestätigung offen (V16) |

### D16

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D16 |
| Geprüfte Regelversion | Schema 6.9 Eigentumsvertrag (title_transfer_date, benefit_burden_date getrennt); Konflikt E02; keine Regeldatei, keine Regelversionsnummer |
| Fachliche Annahmen | Beide Zeitpunkte werden getrennt erfasst; der Vertragsbeginn folgt der Eigentumsumschreibung (Außenverhältnis), der Nutzen- und Lastenwechsel wird gesondert gespeichert (Innenverhältnis). Eine Auswertung beider Zeitpunkte in der Abrechnung ist nicht Gegenstand (siehe D15). |
| Anonymisierte Eingaben | Eigentümerwechsel mit title_transfer_date 01.04.2026 und benefit_burden_date 01.03.2026; Versuch ohne benefit_burden_date. |
| Erwartetes Ergebnis | Kein stilles Gleichsetzen der Daten; beide Zeitpunkte ausgewiesen. |
| Tatsächlich beobachtetes Ergebnis | Neuer Vertrag: start_date 01.04.2026, benefit_burden_date 01.03.2026 (unverändert gespeichert); Wechsel ohne benefit_burden_date wird abgelehnt (422). |
| Differenz | Keine auf Schemaebene. Verwendung in Abrechnung und Kaufvertragsausgleich nicht geprüft (W07, M24-01). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m5_contracts.py::test_ownership_transfer_and_sev -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

### D17

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D17 |
| Geprüfte Regelversion | keine (Partei- und Stimmrechtsmodell 6.9, Anhang E02; Mehrheitsregeln M25-01 offen) |
| Fachliche Annahmen | Keine Prüfung möglich: die Kennung D17 steht nur im Docstring von `tests/integration/test_m5_contracts.py`; kein Test legt eine Person mit zwei Einheiten oder eine Einheit mit mehreren Personen an und prüft Kopfstimme oder Forderung. |
| Anonymisierte Eingaben | Keine. |
| Erwartetes Ergebnis | Zulässige Partei- und Stimmrechtszuordnung ohne doppelte Kopfstimme oder doppelte Forderung. |
| Tatsächlich beobachtetes Ergebnis | Nicht beobachtet, kein Test vorhanden. |
| Differenz | Vollständige Lücke. Empfehlung: Test in M5 (Partei mit mehreren Mitgliedern, Partei mit zwei Eigentumsverträgen, je eine Sollstellung je Vertrag) und M25 (Kopfstimme je Partei) als neue Aufgabe der Lückenliste aufnehmen. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest (kein Test vorhanden) -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | nicht ausgeführt, fachliche Bestätigung offen (V16) |

### D56

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D56 |
| Geprüfte Regelversion | B01 (`docs/rules/B01.md`, Abnahmefall D56 Teil): Bankkonto nur vom gleichen Rechtsträger; Kautionskonto als segregiertes Konto des Vermieters; Annahme `docs/ASSUMPTIONS.md` Zeile 308 (Zahlungsauftrag nie vom Kautionskonto) |
| Fachliche Annahmen | Nur Schema-Teil (M4): Kautionskonto (kind deposit) ist beim Rechtsträger GdWE unzulässig und beim Eigentümer als segregiert gekennzeichnet. Nicht getestet: Buchungsseite (M10), dass Kautionsmittel und Zinsen nicht als frei verfügbares Objektgeld in Saldenliste oder Zahlungsläufen erscheinen. |
| Anonymisierte Eingaben | WEG-Objekt 344 mit GdWE: Bankkonto kind hoa (201), Bankkonto kind deposit auf GdWE (422). Mietobjekt 345 mit Eigentümer als Rechtsträger: Kautionskonto kind deposit (201, segregated = true); Konto kind reserve auf Mietobjekt (422). |
| Erwartetes Ergebnis | Kaution bleibt ihrer Vermögenssphäre und Zinszuordnung zugeordnet; kein Zugriff als frei verfügbares Objektgeld. |
| Tatsächlich beobachtetes Ergebnis | Zuordnungsregeln wie beschrieben; Kautionskonto segregiert. |
| Differenz | Lücke: Buchungs- und Zahlungsseite (kein Zahlungsauftrag vom Kautionskonto, Zinszuordnung, Ausschluss aus freier Liquidität) ist nicht durch einen Test mit Kennung D56 belegt; Kautionsverzinsung und Abrechnung sind Betreiberentscheidung (B15). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m4_properties.py::test_bank_accounts_follow_legal_entities -q --no-cov` |
| Softwarestand (Commit, Version) | Commit 6071d61 (Branch claude/funny-cerf-ppg9in), Arbeitsstand 1.19.0 |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | teilweise, fachliche Bestätigung offen (V16) |

## Auffälligkeiten

1. Keine Regelversionsnummern: Außer H04 (`CO2_RULE_VERSION`) und der Betriebskostenabrechnung (`operating-costs-v1`) tragen die Regeln keine Versionskennung; Anhang D.3 verlangt die geprüfte Regelversion. Empfehlung: Feld `Rule version` in jeder Regeldatei unter `docs/rules/` einführen und im Snapshot der WEG-Abrechnung mitführen (A24 behandelt dies für die Mietabrechnung).
2. D17 trägt die Kennung nur im Docstring von `test_m5_contracts.py`; es gibt keinen Test. Die Lückenliste enthält dafür keine Aufgabe, ebenso nicht für D51. Beide sind als neue Aufgaben aufzunehmen.
3. D13, D14, D15 und D56 sind nur auf Schema- oder Statusebene abgedeckt. Die eigentlichen Geldwirkungen (Sollstellung, Lastschrift, Abrechnungszuordnung nach Eigentümerwechsel, Kautionsmittel in Zahlungsläufen) sind ungetestet; die betroffenen Gates G1 und G4 bleiben geschlossen.
4. D06 und D12 weichen in der Eingabe vom Anhang D ab (Skonto; Abschlag gebucht, aber nicht bezahlt). Die Sollwerte bleiben unverändert; die Abweichung ist im jeweiligen Protokoll ausgewiesen und ist bei der fachlichen Abnahme zu bewerten.
5. Die Tests laufen in Testdateien, die parallel von anderen Agenten geändert werden (`test_m10_ledger.py`, `test_m15_payments.py`, `test_m24_hoa.py`, `test_m17_operating_costs.py`). Das Protokoll gilt für den genannten Commit; nach Abschluss der parallelen Änderungen ist der Sammelbefehl erneut auszuführen.
6. `docs/rules/README.md` führt B06, W05, W06 und W08 als implementiert; der Registerstatus `accepted` darf erst nach fachlicher Bestätigung (V16) gesetzt werden und wurde nicht geändert.

## Abschnitt 2: Fälle D17 bis D58 mit neuen Tests, Stand 26.09.2026

Aufgaben A02 bis A26 aus `docs/plans/LUECKENLISTE-2026-09-26.md` sowie D17 und D51 ohne eigene Aufgabe. Softwarestand: Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen). Datenbank PostgreSQL und Redis lokal, Migrationskette zum Zeitpunkt des Laufs linear bis 0099; Tests mit `--no-cov`. Geltung, Regelversion, Freigabestufen und Prüfer wie in Abschnitt 1: technische Ausführung, keine fachliche Abnahme, alle Gates geschlossen, kein Sollwert an das Ist-Ergebnis angepasst, nur synthetische Modellwerte.

Gesamtergebnis: Sammellauf über alle Testfunktionen mit Fallkennung `test_dNN_*` (D17 bis D58) und die Datei `test_d50_authorization.py`, Ergebnis `1 failed, 220 passed, 777 deselected in 83.01s` (der Filter `-k` erfasst zusätzlich Tests ohne Fallkennung, alle bestanden). Fachliche Bewertung je Fall: 34 technisch bestanden, 1 teilweise (D55, Worker-Pfad Lauf zu wiederholen), 0 nicht bestanden. Nicht enthalten, weil ohne Test mit Fallkennung: D09, D11, D24 bis D27, D34, D47.

Sammelbefehl:

```
cd apps/api && uv run pytest tests -k "test_d17_ or test_d18_ or test_d19_ or test_d20_ or test_d21_ or test_d22_ or test_d23_ or test_d28_ or test_d29_ or test_d30_ or test_d31_ or test_d32_ or test_d35_ or test_d39_ or test_d40_ or test_d41_ or test_d42_ or test_d43_ or test_d44_ or test_d45_ or test_d46_ or test_d48_ or test_d49_ or test_d51_ or test_d52_ or test_d53_ or test_d54_ or test_d55_ or test_d57_ or test_d58_ or test_d50" -q --no-cov
```

Hinweis zur Wiederholbarkeit: Nach dem Lauf wurde der Arbeitsbereich durch parallele Agentensitzungen verändert (zwei Migrationen mit Nummer 0100, geänderte Signatur `require_permission()`); ein zweiter Lauf zur Bestätigung schlug bereits in der Testsammlung fehl. Der Sammelbefehl ist nach Abschluss dieser Arbeiten erneut auszuführen.

### Übersicht Abschnitt 2

| Kennung | Test | Ergebnis Test | Status Fall |
| --- | --- | --- | --- |
| D17 | `tests/integration/test_m5_contracts.py::test_d17_one_owner_two_units_and_one_unit_two_owners` | bestanden | technisch bestanden |
| D18 | `tests/integration/test_m24_hoa.py::test_d18_sub_community_without_basis_blocks_release` | bestanden | technisch bestanden |
| D19 | `tests/integration/test_m24_hoa.py::test_d19_reserve_contribution_unpaid_no_settlement_entry` | bestanden | technisch bestanden |
| D20 | `tests/integration/test_w09_special_levy.py::test_d20_levy_instalments_with_partial_refund` | bestanden | technisch bestanden |
| D21 | `tests/integration/test_m17_operating_costs.py::test_d21_let_condominium_needs_recorded_key` | bestanden | technisch bestanden |
| D22 | `tests/integration/test_m17_operating_costs.py::test_d22_mixed_invoice_split_must_be_posted` | bestanden | technisch bestanden |
| D23 | `tests/integration/test_m17_operating_costs.py::test_d23_creation_is_not_access` | bestanden | technisch bestanden |
| D28 | `tests/integration/test_m17_operating_costs.py::test_d28_rule_version_pinned_in_snapshot` | bestanden | technisch bestanden |
| D29 | `tests/integration/test_m21_portal.py::test_d29_owner_sees_gdwe_documents_outside_own_statement` | bestanden | technisch bestanden |
| D30 | `tests/integration/test_m21_portal.py::test_d30_foreign_gdwe_and_sev_files_denied_on_every_path`, `tests/integration/test_m7_ai.py::test_d30_ai_context_excludes_foreign_documents` | bestanden | technisch bestanden |
| D31 | `tests/integration/test_m21_portal.py::test_d31_tenant_never_reaches_the_unredacted_receipt`, `tests/integration/test_m21_portal.py::test_d31_tenant_gets_released_version_with_redaction_note` | bestanden | technisch bestanden |
| D32 | `tests/integration/test_m25_meeting.py::test_d32_d33_audit_sample_report_and_invoice_change_after_check` | bestanden | technisch bestanden |
| D33 | `tests/integration/test_m25_meeting.py::test_d32_d33_audit_sample_report_and_invoice_change_after_check` | bestanden | technisch bestanden |
| D35 | `tests/integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback` | bestanden | technisch bestanden |
| D36 | `tests/integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback` | bestanden | technisch bestanden |
| D37 | `tests/integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback` | bestanden | technisch bestanden |
| D38 | `tests/integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback` | bestanden | technisch bestanden |
| D39 | `tests/integration/test_m12_matching.py::test_d39_payment_determination_is_not_overridden_by_account_priority` | bestanden | technisch bestanden |
| D40 | `tests/integration/test_m16_dunning.py::test_d40_dunning_without_fee_amount_and_base_rate_creates_no_side_claim` | bestanden | technisch bestanden |
| D41 | `tests/integration/test_m13_xrechnung.py::test_d41_xrechnung_issue_generate_check_and_store`, `tests/integration/test_m13_xrechnung.py::test_d41_kleinunternehmer_and_vat_mismatch_are_locked`, `tests/integration/test_m14_receipt_drafts.py::test_d41_xrechnung_xml_is_read_without_provider_call_and_objection_blocks_release`, `tests/unit/test_m13_xrechnung.py` | bestanden | technisch bestanden |
| D42 | `tests/integration/test_m14_receipt_drafts.py::test_d42_hybrid_zugferd_conflict_is_visible_and_never_chosen_silently`, `tests/unit/test_m14_einvoice.py::test_d42_hybrid_conflicts_xml_against_pdf_text_and_against_ai_reading` | bestanden | technisch bestanden |
| D43 | `tests/integration/test_m6_documents.py::test_d43_original_locked_while_only_ocr_text_exists`, `tests/integration/test_m14_ai_extract_invoice.py::test_d43_d46_original_locked_after_json_extraction_and_import_undo` | bestanden | technisch bestanden |
| D44 | `tests/integration/test_m14_receipt_drafts.py::test_d44_ai_estimated_section_35a_share_is_never_shown_as_evidence`, `tests/unit/test_m14_einvoice.py::test_d44_section_35a_estimate_is_never_evidence` | bestanden | technisch bestanden |
| D45 | `tests/integration/test_m14_invoices.py::test_d45_invoice_with_vat_on_option_ledger_is_not_posted`, `tests/integration/test_m13_receivables.py::test_d45_receivable_run_vat_option_without_tax_status_stays_manual` | bestanden | technisch bestanden |
| D46 | `tests/integration/test_m7_ai.py::test_d46_import_undo_never_removes_a_recorded_original`, `tests/integration/test_m14_ai_extract_invoice.py::test_d43_d46_original_locked_after_json_extraction_and_import_undo` | bestanden | technisch bestanden |
| D48 | `tests/integration/test_m13_receivables.py::test_d48_receivable_run_concurrency_retry_and_idempotency` | bestanden | technisch bestanden |
| D49 | `tests/integration/test_m10_ledger.py::test_d49_historical_open_items_after_later_payment_and_reversal` | bestanden | technisch bestanden |
| D50 | `tests/integration/test_d50_authorization.py` | bestanden | technisch bestanden |
| D51 | `tests/integration/test_d51_rule_configuration.py::test_d51_configured_rule_is_never_productive_without_decision_and_tests` | bestanden | technisch bestanden |
| D52 | `tests/integration/test_m16_dunning.py::test_d52_comparison_ledger_receivable_run_and_dunning_stay_internal`, `tests/integration/test_m15_payments.py::test_d52_payment_batch_only_from_leading_system` | bestanden | technisch bestanden |
| D53 | `tests/integration/test_m25_meeting.py::test_d53_virtual_meeting_needs_basis_and_documents_disruption` | bestanden | technisch bestanden |
| D54 | `tests/integration/test_m24_hoa.py::test_d54_contested_resolution_blocks_posting_and_reverses_nothing` | bestanden | technisch bestanden |
| D55 | `tests/integration/test_m18_audit_export.py::test_d55_audit_export_zip_contents_hashes_and_reversal`, `tests/integration/test_m18_audit_export.py::test_d55_audit_export_on_worker` | 1 bestanden, 1 fehlgeschlagen | teilweise: ZIP-Inhalt, Hashes und Storno technisch bestanden; Worker-Pfad Test vorhanden, Lauf zu wiederholen |
| D57 | `tests/integration/test_m7_ai.py::test_d57_instruction_in_contacts_and_property_output_has_no_effect`, `tests/integration/test_m14_ai_extract_invoice.py::test_d57_instruction_in_model_output_is_not_executed`, `tests/integration/test_m19_ticket_proposals.py::test_d57_instruction_mail_yields_no_change_and_no_bank_update` | bestanden | technisch bestanden |
| D58 | `tests/integration/test_m13_receivables.py::test_d58_sev_admin_fee_debtor_and_payee` | bestanden | technisch bestanden |

Alle Fälle: fachliche Bestätigung offen (V16).

### Einzelprotokolle Abschnitt 2

#### D17

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D17 |
| Geprüfte Regelversion | 6.9.2 Debitor je Partei und Einheit, § 25 Abs. 2 WEG Kopfprinzip wie in M25 umgesetzt (W06 `docs/rules/W06-resolution.md`); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Partei A besitzt Einheiten 01 und 02, Partei B (zwei Personen, je 50 Prozent) besitzt Einheit 03; kein Eigentümerwechsel im Zeitraum; Kopfprinzip als Standard, abweichende Vereinbarungen nicht geprüft. |
| Anonymisierte Eingaben | Drei Eigentumsverträge, Hausgeld 300,00 EUR je Vertrag und Monat. |
| Erwartetes Ergebnis | Debitorenkonto je Partei und Einheit (nicht je Person, nicht ein Konto für beide Einheiten); eine Forderung je Vertrag und Monat (3 x 300,00 = 900,00 EUR, keine je Miteigentümer); eine Kopfstimme je Partei: A ja mit beiden Einheiten, B nein ergibt 1:1; abweichende Stimmabgabe eines Eigentümers über zwei Einheiten wird abgelehnt. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet: drei Verträge, Debitoren je Partei und Einheit, Forderungen 3 x 300,00 EUR, Abstimmung 1:1, abweichende Stimme abgelehnt. |
| Differenz | Keine. Nicht geprüft: Wertprinzip oder Objektprinzip nach Gemeinschaftsordnung (fachliche Entscheidung, V16). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m5_contracts.py::test_d17_one_owner_two_units_and_one_unit_two_owners -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D18

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D18 |
| Geprüfte Regelversion | W03 (`docs/rules/W03-cost-allocation.md`, implemented, not accepted); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Eine Kostenposition erreicht über den Verteilungsschlüssel nur die Einheiten 01 und 02 von drei Einheiten und gilt damit als Untergemeinschaft; Grundlage muss Beschluss oder Teilungserklärung mit Quelle sein. |
| Anonymisierte Eingaben | WEG-Modellobjekt mit drei Einheiten; eine Position mit freiem Filter als Grundlage, dieselbe Position mit benanntem Beschluss als Quelle. |
| Erwartetes Ergebnis | Ohne belegte Grundlage: Prüfhinweis im Abrechnungspaket, interne Freigabe abgelehnt. Mit Beschluss als Quelle: dieselbe Verteilung freigabefähig. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet: Finding im Paket und Ablehnung der internen Freigabe ohne Grundlage; mit Beschlussquelle freigabefähig. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m24_hoa.py::test_d18_sub_community_without_basis_blocks_release -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D19

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D19 |
| Geprüfte Regelversion | W08 (Register `docs/rules/README.md`, implemented, D19 getestet); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Beschlossene Rücklagenzuführung 6.000,00 EUR, gezahlt 4.500,00 EUR auf das Rücklagenkonto, Anfangsbestand 10.000,00 EUR; keine Entnahmen im Zeitraum. |
| Anonymisierte Eingaben | Soll 6.000,00 EUR, Ist 4.500,00 EUR, Anfangsbestand 10.000,00 EUR (Bankanlage nur Ist). |
| Erwartetes Ergebnis | Getrennter Ausweis: Soll 6.000,00, Ist 4.500,00, Rückstand 1.500,00, buchhalterischer Endbestand 14.500,00, Bankbestand 4.500,00, Differenz zur Bank 10.000,00 erläutert; die Berechnung schreibt keine Buchung. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet, alle Werte identisch; kein Journaleintrag durch die Berechnung. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m24_hoa.py::test_d19_reserve_contribution_unpaid_no_settlement_entry -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D20

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D20 |
| Geprüfte Regelversion | W09 (Register `docs/rules/README.md`, implemented, not accepted); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Sonderumlage Fassade 6.000,00 EUR in drei Raten ab März 2026, MEA 600 zu 400; Änderungsbeschluss auf 4.500,00 EUR mit Erstattungsgrund; Erstattungen nur als Entwurfsgutschriften. |
| Anonymisierte Eingaben | Einheit 01: 3 x 1.200,00 EUR, Einheit 02: 3 x 800,00 EUR; März für Einheit 01 sollgestellt und bezahlt (1.200,00 EUR); Mittelverwendung 500,00 EUR; Änderung auf 4.500,00 EUR. |
| Erwartetes Ergebnis | Zweck, Soll und Ist, Verwendung, Fälligkeitsmonate und Erstattungsgrund bleiben erhalten; Differenzen 900,00 EUR und 600,00 EUR nur als Entwurfsgutschriften; Verwendung wird nicht doppelt gezählt. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_w09_special_levy.py::test_d20_levy_instalments_with_partial_refund -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D21

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D21 |
| Geprüfte Regelversion | A03 Schlüssel (Register `docs/rules/README.md`, implemented, not accepted), M17-01; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Vermietetes Wohnungseigentum (SEV) ohne abweichende Vereinbarung; Eigentümer A hält Einheiten 01 und 03 (MEA 250 und 500 laut Teilungserklärung), Eigentümer B Einheit 02; die Überleitung aus der WEG-Abrechnung selbst ist A06 und nicht Gegenstand. |
| Anonymisierte Eingaben | Kostenanteil Eigentümer A 750,00 EUR; Wohnflächenschlüssel aus der Mietvorlage; erfasster Schlüssel mit Quelle am Objekt. |
| Erwartetes Ergebnis | Vorlagenschlüssel (automatische m²-Regel) wird abgelehnt; erfasster Schlüssel mit Quelle verteilt 250,00 EUR und 500,00 EUR; Einheit von Eigentümer B erscheint nie in der Abrechnung von A. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. Umlagefähigkeit je Position bleibt M17-01. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m17_operating_costs.py::test_d21_let_condominium_needs_recorded_key -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D22

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D22 |
| Geprüfte Regelversion | A02 Betriebskosten Miete (Register, implemented, not accepted); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Mischrechnung 1.000,00 EUR, davon 700,00 EUR Hauswart (umlagefähig) und 300,00 EUR Reparatur (nicht umlagefähig), gesplittet auf zwei Konten gebucht. |
| Anonymisierte Eingaben | Rechnung 1.000,00 EUR, Buchung 700,00 EUR Hauswartkonto, 300,00 EUR Reparaturkonto. |
| Erwartetes Ergebnis | Volle 1.000,00 EUR auf dem Hauswartkonto abgelehnt (übersteigt gebuchte 700,00 EUR); Reparaturkonto und unklassifiziertes Konto abgelehnt; 700,00 EUR erreichen den Mieter. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m17_operating_costs.py::test_d22_mixed_invoice_split_must_be_posted -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D23

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D23 |
| Geprüfte Regelversion | M17-04 Zugang (Register), Fristorientierung 31.12.2026 ist Modellannahme; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Abrechnung 2025 wird am 28.12.2026 berechnet; Nachzahlung 120,00 EUR; die Ausgabe verlangt ein erfasstes Zugangsdatum; Fristfolgen sind fachlich nicht bewertet. |
| Anonymisierte Eingaben | Berechnung 28.12.2026, Zugangsdatum vor der Berechnung, Zugang 05.01.2027, Zugang vor Fristende. |
| Erwartetes Ergebnis | Zugang vor der Berechnung abgelehnt (Erzeugung ist kein Zugang); Zugang 05.01.2027 ohne erfasste Ausnahme abgelehnt; Zugang vor Fristende gibt aus. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. Rechtsfolge der Fristversäumung ist keine Aussage der Software (V16). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m17_operating_costs.py::test_d23_creation_is_not_access -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D28

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D28 |
| Geprüfte Regelversion | A01 Ergebnisstand, `statement_snapshot.rule_version` (Register, implemented, not accepted) |
| Fachliche Annahmen | Spätere Regelversion gültig ab 01.01.2027; Abrechnung 2025 bereits ausgegeben. |
| Anonymisierte Eingaben | Ausgegebener Snapshot 2025 mit Version und Hash; neue Version der Abrechnung 2025; Abrechnung für Zeitraum 2027. |
| Erwartetes Ergebnis | Snapshot behält Version und Hash; Neuberechnung 2025 nutzt die alte Regel; nur 2027 nimmt die neue Regel. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m17_operating_costs.py::test_d28_rule_version_pinned_in_snapshot -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D29

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D29 |
| Geprüfte Regelversion | Portalzugriff `mhvp.portal.access` (`hoa_member_right`, § 18 Abs. 4 WEG als Umsetzung, Rechtsgrund fachlich zu bestätigen); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Unterlagen sind nur mit der GdWE verknüpft, nicht mit Einheit oder Vertrag des Eigentümers; Mitgliedsrecht öffnet Liste und Download. |
| Anonymisierte Eingaben | Eigentümer der GdWE, Dokumente an der GdWE ohne Einheitsbezug. |
| Erwartetes Ergebnis | Liste und Download über das Mitgliedsrecht möglich. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m21_portal.py::test_d29_owner_sees_gdwe_documents_outside_own_statement -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D30

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D30 |
| Geprüfte Regelversion | Portalzugriff `mhvp.portal.access`, KI-Kontext M20-05 (`docs/rules/M20-05.md`); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Derselbe Eigentümer fordert fremde GdWE, private SEV-Akte eines anderen Eigentümers der eigenen GdWE und fremde Vertragsakte; Portalnutzer hat kein `ai:create`. |
| Anonymisierte Eingaben | Zwei GdWE, zwei Eigentümer, SEV-Akte und Vertragsdokument des anderen Eigentümers; KI-Lauf im Namen des Portalnutzers mit fremdem Dokument. |
| Erwartetes Ergebnis | Ablehnung über jeden Pfad (Liste, Download, Suche); Portalnutzer kann keinen Chat öffnen; Retrieval verwirft fremdes Dokument, angehängtes fremdes Dokument blockiert den Lauf. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m21_portal.py::test_d30_foreign_gdwe_and_sev_files_denied_on_every_path tests/integration/test_m7_ai.py::test_d30_ai_context_excludes_foreign_documents -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D31

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D31 |
| Geprüfte Regelversion | E06 (Anhang E, Schwärzung statt Vollfreigabe oder Vollverweigerung), Freigabesteuerung 14; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Beleg mit Angaben Dritter wird nicht als Ganzes freigegeben; freigegebene Version mit Schwärzungsvermerk; Nachbar sieht nichts. |
| Anonymisierte Eingaben | Abrechnungsbeleg mit Drittangaben, Mieter der Abrechnung, Nachbarmieter. |
| Erwartetes Ergebnis | Keine Vollfreigabe des Originals; freigegebene Version in Liste und Download mit Vermerk sichtbar; Nachbar ohne Zugriff. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m21_portal.py::test_d31_tenant_never_reaches_the_unredacted_receipt tests/integration/test_m21_portal.py::test_d31_tenant_gets_released_version_with_redaction_note -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D32

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D32 |
| Geprüfte Regelversion | PÜ09 (Register, implemented, not accepted); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Beirat prüft nur ausgewählte Belege; Bericht darf keine Vollprüfung behaupten. |
| Anonymisierte Eingaben | Positionen 120,00 EUR (geprüft) und 80,00 EUR (offen). |
| Erwartetes Ergebnis | Geprüft 1 Position mit 120,00 EUR, ungeprüft 1 Position mit 80,00 EUR, ausgewählt 2; keine Vollständigkeitsaussage. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m25_meeting.py::test_d32_d33_audit_sample_report_and_invoice_change_after_check -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D33

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D33 |
| Geprüfte Regelversion | PÜ09 (Register); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Rechnung wird nach der Beiratsprüfung des zugehörigen Belegs geändert. |
| Anonymisierte Eingaben | Wie D32, anschließend Änderung der geprüften Rechnung. |
| Erwartetes Ergebnis | Betroffene Position als veraltet markiert; Bericht und Prüfdetail zeigen keinen unveränderten grünen Gesamtstatus mehr. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m25_meeting.py::test_d32_d33_audit_sample_report_and_invoice_change_after_check -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D35

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D35 |
| Geprüfte Regelversion | 6.9.9 Vier-Augen-Freigabe, 7.5 Zahlungsverkehr, `docs/rules/M11-06-payment-proposal-only-until-g2.md`; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Synthetische Bankrückmeldungen; G2 bleibt geschlossen, Dateiexport nicht Gegenstand; Prüfung auf gleiche Person nach Kontakt und E-Mail-Domäne soweit technisch möglich (M15-02). |
| Anonymisierte Eingaben | Zahlungsauftrag mit Freigabe durch zwei Konten; Änderung von Betrag und IBAN; Ablehnung und Teilausführung; Rückgabe einer zugeordneten Zahlung. |
| Erwartetes Ergebnis | Änderung von Betrag oder Empfänger-IBAN nach Freigabe entwertet die Freigabe (Release-Hash); erneute Freigabe nötig. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet (Sammeltest für D35 bis D38). |
| Differenz | Keine. Bank-Testsystem bleibt M15-03. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D36

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D36 |
| Geprüfte Regelversion | 6.9.9 Vier-Augen-Freigabe, 7.5 Zahlungsverkehr, `docs/rules/M11-06-payment-proposal-only-until-g2.md`; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Synthetische Bankrückmeldungen; G2 bleibt geschlossen, Dateiexport nicht Gegenstand; Prüfung auf gleiche Person nach Kontakt und E-Mail-Domäne soweit technisch möglich (M15-02). |
| Anonymisierte Eingaben | Zahlungsauftrag mit Freigabe durch zwei Konten; Änderung von Betrag und IBAN; Ablehnung und Teilausführung; Rückgabe einer zugeordneten Zahlung. |
| Erwartetes Ergebnis | Zweites Konto derselben Person gilt nicht als zweiter Freigeber. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet (Sammeltest für D35 bis D38). |
| Differenz | Keine. Bank-Testsystem bleibt M15-03. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D37

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D37 |
| Geprüfte Regelversion | 6.9.9 Vier-Augen-Freigabe, 7.5 Zahlungsverkehr, `docs/rules/M11-06-payment-proposal-only-until-g2.md`; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Synthetische Bankrückmeldungen; G2 bleibt geschlossen, Dateiexport nicht Gegenstand; Prüfung auf gleiche Person nach Kontakt und E-Mail-Domäne soweit technisch möglich (M15-02). |
| Anonymisierte Eingaben | Zahlungsauftrag mit Freigabe durch zwei Konten; Änderung von Betrag und IBAN; Ablehnung und Teilausführung; Rückgabe einer zugeordneten Zahlung. |
| Erwartetes Ergebnis | Bei Ablehnung oder Teilausführung durch die Bank wird nur der bestätigte Teil ausgeglichen. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet (Sammeltest für D35 bis D38). |
| Differenz | Keine. Bank-Testsystem bleibt M15-03. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D38

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D38 |
| Geprüfte Regelversion | 6.9.9 Vier-Augen-Freigabe, 7.5 Zahlungsverkehr, `docs/rules/M11-06-payment-proposal-only-until-g2.md`; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Synthetische Bankrückmeldungen; G2 bleibt geschlossen, Dateiexport nicht Gegenstand; Prüfung auf gleiche Person nach Kontakt und E-Mail-Domäne soweit technisch möglich (M15-02). |
| Anonymisierte Eingaben | Zahlungsauftrag mit Freigabe durch zwei Konten; Änderung von Betrag und IBAN; Ablehnung und Teilausführung; Rückgabe einer zugeordneten Zahlung. |
| Erwartetes Ergebnis | Rückgabe einer bereits zugeordneten Zahlung storniert die Zuordnung und öffnet die Verbindlichkeit wieder; Korrektur nachvollziehbar, keine Löschung. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet (Sammeltest für D35 bis D38). |
| Differenz | Keine. Bank-Testsystem bleibt M15-03. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D39

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D39 |
| Geprüfte Regelversion | 7.4 Nr. 5 Tilgungsbestimmung, M10-03 offen (`docs/OPEN_QUESTIONS.md`); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Verwendungszweck benennt das Hausgeld Februar; keine interne Kontenpriorität darf dies überschreiben; Fall ohne Bestimmung geht in die Prüfung. |
| Anonymisierte Eingaben | Offen Januar 250,00 EUR und Februar 250,00 EUR; Zahlung 250,00 EUR „Hausgeld Februar 2026 <Vertrag>“; zweite Zahlung nur „<Vertrag>“. |
| Erwartetes Ergebnis | Zwei Kandidaten mit gleicher Evidenz, kein eindeutiger Treffer, aktive Regel bucht nichts, Massenvorschau als Ausnahme; ausdrücklicher Ausgleich Februar lässt Januar mit 250,00 EUR offen; Zahlung ohne Bestimmung geht in die Prüfung statt älteste zuerst. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Hinweis: Der Test deckt nur gleiche Restbeträge ab; bei ungleichen Restbeträgen könnte ein Betragstreffer allein als eindeutig gelten (neuer Punkt M12-03 in `docs/OPEN_QUESTIONS.md`). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m12_matching.py::test_d39_payment_determination_is_not_overridden_by_account_priority -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D40

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D40 |
| Geprüfte Regelversion | M16-01 (`docs/rules/M16-01.md`), V7 Betreibervorgabe vom 25.09.2026 (Stufe 1 kostenlos); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | V7-Vorgaben ohne Beträge; Gebühren ab `fee_from_level` 2; Verzugszins nur mit gepflegtem Basiszinssatz. |
| Anonymisierte Eingaben | Hauptforderung 350,00 EUR; Gebührenbetrag für Stufe 1 eingetragen; Zins aktiviert ohne `interest_base_rate`. |
| Erwartetes Ergebnis | Zahlungserinnerung 0,00 EUR trotz eingetragenem Betrag; Zins ohne Basiszinssatz mit MHVP-CORE-0004 abgelehnt; Vorschlag zeigt Gebühr 0,00 und Zins 0,00; Freigabe erzeugt weder Gebühreneintrag noch HVM-Rechnungsentwurf; OP bleibt 350,00 EUR. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Hinweis: „Stufe 1 immer 0,00“ hängt allein an `fee_from_level`; `PUT /dunning-settings` erlaubt `fee_from_level = 1` (neuer Punkt M16-14 in `docs/OPEN_QUESTIONS.md`). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m16_dunning.py::test_d40_dunning_without_fee_amount_and_base_rate_creates_no_side_claim -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D41

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D41 |
| Geprüfte Regelversion | 13.5 E-Rechnung, M13-04 (`docs/rules/M13-04.md`), Problem-Codes MHVP-BILL-0003, MHVP-BILL-0005 bis 0007; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Formal valide XRechnung wird ohne Anbieteraufruf gelesen; sachliche Beanstandung sperrt Freigabe und Buchung; Ausstellung: Leitweg-ID, IBAN und Steuerdaten aus `TenantBillingSettings`; Kleinunternehmer ohne USt. |
| Anonymisierte Eingaben | Eingang: XRechnung-XML über Belegeingang, Einwand „Leistung nicht erbracht“. Ausgang: Verwalterhonorar mit und ohne 19 Prozent, Mandant mit und ohne Leitweg-ID, IBAN, Steuerdaten. |
| Erwartetes Ergebnis | Eingang: Entwurf mit Quelle `xml`, kein KI-Aufruf; Rechnung durchläuft Prüfung; Einwand blockiert Freigabe und Buchung. Ausgang: XML mit Pflichtfeldern und Summen, Strukturprüfung meldet Summen- und Feldbefunde; ohne Leitweg-ID, IBAN oder Steuerdaten gesperrt; Kleinunternehmer mit 19 Prozent mit MHVP-BILL-0003 gesperrt statt stillem Kategoriewechsel. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet in allen acht Tests. |
| Differenz | Keine. KoSIT-Validator im CI nicht Teil dieses Laufs (A12 Validator-Lauf gesondert zu belegen). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m13_xrechnung.py::test_d41_xrechnung_issue_generate_check_and_store tests/integration/test_m13_xrechnung.py::test_d41_kleinunternehmer_and_vat_mismatch_are_locked tests/integration/test_m14_receipt_drafts.py::test_d41_xrechnung_xml_is_read_without_provider_call_and_objection_blocks_release tests/unit/test_m13_xrechnung.py -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D42

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D42 |
| Geprüfte Regelversion | 13.5, PÜ01, M14 Belegeingang (`mhvp.receipts.einvoice`); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | ZUGFeRD-PDF, dessen Textschicht dem eingebetteten XML widerspricht; XML bleibt Vorschlag mit Quelle; Bestätigung braucht ausdrückliche Kenntnisnahme. |
| Anonymisierte Eingaben | Hybridrechnung mit abweichendem Betrag in PDF-Text gegenüber XML; KI-Lesung als dritte Quelle. |
| Erwartetes Ergebnis | Alle Widersprüche gelistet; keine stille Auswahl; Bestätigung nur mit Kenntnisnahme; Konflikte begleiten die Rechnung als Prüfhinweise. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m14_receipt_drafts.py::test_d42_hybrid_zugferd_conflict_is_visible_and_never_chosen_silently tests/unit/test_m14_einvoice.py::test_d42_hybrid_conflicts_xml_against_pdf_text_and_against_ai_reading -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D43

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D43 |
| Geprüfte Regelversion | 6.9.5 Aufbewahrung, 11.3; Aufbewahrungsprofile bleiben V17; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Rechnung liegt als Original vor, daneben nur OCR-Text oder JSON-Extraktion; Sperre gilt ohne Profil als Standard. |
| Anonymisierte Eingaben | Dokument mit Textindex; Dokument nach KI-Extraktion (JSON); Löschversuch. |
| Erwartetes Ergebnis | Original kann nicht gelöscht werden; Text oder JSON ersetzt nichts; Ablehnung wird protokolliert. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m6_documents.py::test_d43_original_locked_while_only_ocr_text_exists tests/integration/test_m14_ai_extract_invoice.py::test_d43_d46_original_locked_after_json_extraction_and_import_undo -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D44

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D44 |
| Geprüfte Regelversion | M14-04, PÜ03 (§ 35a EStG Anteil nur mit Beleg); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Ein vom Modell nur geschätzter § 35a Anteil ist Kennzeichen `ai_estimate` mit Konfidenz 0; ein auf der Rechnung ausgewiesener Anteil bleibt gewöhnlicher Vorschlag. |
| Anonymisierte Eingaben | Rechnung ohne ausgewiesenen Anteil mit Modellschätzung; Rechnung mit ausgewiesenem Anteil. |
| Erwartetes Ergebnis | Schätzung wird nicht in die Rechnung geschrieben, erzeugt Befund und Nachforderung einer belegten Aufteilung; ausgewiesener Anteil als Vorschlag zur Prüfung am Original. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m14_receipt_drafts.py::test_d44_ai_estimated_section_35a_share_is_never_shown_as_evidence tests/unit/test_m14_einvoice.py::test_d44_section_35a_estimate_is_never_evidence -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D45

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D45 |
| Geprüfte Regelversion | M13-03, M14-02, Problem-Code MHVP-ACC-0005 (Steuerbehandlung nicht freigegeben); Steuerstatus bleibt V21; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Buchungskreis mit Umsatzsteueroption ohne gepflegte oder freigegebene Steuerbehandlung; keine automatische Vorsteuer oder Umsatzsteuer. |
| Anonymisierte Eingaben | Eingang: Rechnung 1.000,00 EUR netto plus 190,00 EUR USt; Rechnung 500,00 EUR ohne USt. Ausgang: Komponente 100,00 EUR netto (119,00 EUR brutto) und Komponente 50,00 EUR ohne USt. |
| Erwartetes Ergebnis | Eingang: Prüfung und Freigabe möglich, Buchung mit MHVP-ACC-0005 abgelehnt, Status, Journal und OP unverändert; Rechnung ohne USt wird gebucht. Ausgang: Komponente mit USt bleibt `manual` mit Grund, Komponente ohne USt gebucht; OP genau 50,00 EUR, kein Steuerkonto berührt. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m14_invoices.py::test_d45_invoice_with_vat_on_option_ledger_is_not_posted tests/integration/test_m13_receivables.py::test_d45_receivable_run_vat_option_without_tax_status_stays_manual -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D46

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D46 |
| Geprüfte Regelversion | 6.9.5, 11.3, Regel 0.1.7 (Undo umgeht keine Aufbewahrungssperre); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Importlauf hat ein Original als eigenes Element erfasst; Rückgängig des Laufs darf es nicht entfernen. |
| Anonymisierte Eingaben | Importlauf mit Dokument und Rechnungsentwurf; Undo des Laufs. |
| Erwartetes Ergebnis | Rechnungsentwurf entfällt, Original bleibt mit Aufbewahrungsgrund; Ablehnung als `document.deletion_refused` protokolliert; Lauf endet teilweise rückgängig mit Gründen. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m7_ai.py::test_d46_import_undo_never_removes_a_recorded_original tests/integration/test_m14_ai_extract_invoice.py::test_d43_d46_original_locked_after_json_extraction_and_import_undo -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D48

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D48 |
| Geprüfte Regelversion | B08 (`docs/rules/B08.md`), 18 M10 Abnahme (Konkurrenz, Abbruch, Wiederholung), Idempotency-Key; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Zwei Verträge mit je 300,00 EUR Hausgeld und 50,00 EUR Rücklage; gleichzeitiger Lauf, Wiederholung nach Abbruch, doppelter API-Aufruf mit gleichem Schlüssel. |
| Anonymisierte Eingaben | 2 x (300,00 + 50,00) = 700,00 EUR je Monat; Läufe März und April; Entwurf 12,34 EUR mit Schlüssel `d48-key`. |
| Erwartetes Ergebnis | Genau eine wirtschaftliche Wirkung je Szenario: OP 700,00 EUR März, 700,00 EUR April, ein Entwurf 12,34 EUR. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m13_receivables.py::test_d48_receivable_run_concurrency_retry_and_idempotency -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D49

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D49 |
| Geprüfte Regelversion | B07 (`docs/rules/B07.md`), Regel 0.1.7; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Historischer OP-Stichtag bleibt nach späterer Zahlung und Storno unverändert; Storno vor Stichtag wirkt nur als Gegenbuchung. |
| Anonymisierte Eingaben | Forderung 1.000,00 EUR am 01.03.; Zahlung 600,00 EUR am 10.04., Storno am 15.04.; Storno der Forderung am 20.03. |
| Erwartetes Ergebnis | Stand 31.03. = 1.000,00 vor und nach Zahlung und Storno; Stand 30.04. = 400,00 nach Zahlung, 1.000,00 nach Storno; Storno der Forderung am 20.03. ergibt 0,00 zum 31.03. und weiterhin 1.000,00 zum 19.03. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m10_ledger.py::test_d49_historical_open_items_after_later_payment_and_reversal -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D50

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D50 |
| Geprüfte Regelversion | Regel 0.1.4 (Gates auch für Jobs, Massenaktionen, Integrationen), ADR 0003; Ergebnistabelle `docs/reviews/2026-09-26-d50-berechtigungen.md`; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Benutzer mit Leserechten und API-Schlüssel mit Lesescopes; Endpunktliste aus OpenAPI abgeleitet; Jobs laufen systemseitig ohne Principal. |
| Anonymisierte Eingaben | Alle Massen- und Laufendpunkte aus OpenAPI; Leserolle, Leseschlüssel, ohne Anmeldung, Mandantenadministrator als Positivkontrolle. |
| Erwartetes Ergebnis | Serverseitige Ablehnung für Leser und Leseschlüssel vor Gate-Prüfung; Gates schließen Massenendpunkte auch für Administratoren; Job-Guard schließt standardmäßig; kein Job nimmt Rollen an; Positivkontrolle zeigt, dass nur das Recht die Ablehnung verursacht. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet in allen 11 Tests der Datei. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_d50_authorization.py -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D51

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D51 |
| Geprüfte Regelversion | Regel 0.1.3 (Konfiguration ersetzt keine gültige Regel), Anhang E; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Unbekannte Regel wird als Konfiguration eingetragen; ohne dokumentierte Entscheidung und Tests darf sie nicht produktiv wirken. |
| Anonymisierte Eingaben | Konfigurierte Regel ohne Entscheidung und ohne Testnachweis. |
| Erwartetes Ergebnis | Regel bleibt gesperrt beziehungsweise nicht produktiv; Sperre sichtbar. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_d51_rule_configuration.py::test_d51_configured_rule_is_never_productive_without_decision_and_tests -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D52

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D52 |
| Geprüfte Regelversion | 6.9.10, 13.1 Parallelbetrieb (genau ein führendes System je Rechtsträger, Datum und Vorgangstyp); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Vergleichs-Buchungskreis mit Immoware24 führend; Sollstellung nur als interne Vergleichsbuchung; keine Mahnung, kein Zahlungsauftrag aus dem nicht führenden System; Lastschrift folgt A11. |
| Anonymisierte Eingaben | 2 Verträge mit 300,00 EUR Hausgeld und 50,00 EUR Rücklage, Lauf 20.03.2026; Zahlungsauftrag voll freigegeben im Vergleichs-Buchungskreis, G2 im Test geöffnet. |
| Erwartetes Ergebnis | 2 Fälle zu 350,00 EUR; keine Mahnung (Ausschluss mit Grund); Vorschlag aus Plattform-führender Zeit nicht mehr freigebbar, sobald Immoware24 wieder führt; keine pain.001 im Vergleichs-Buchungskreis, Datei nur bei Plattform führend, zweite Datei nach Rückwechsel abgelehnt. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Hinweis: Lückenliste A17 verlangt „keine Sollstellung“, Code und 13.1 sehen eine Vergleichsbuchung ohne externe Wirkung vor (neuer Punkt M10-05 in `docs/OPEN_QUESTIONS.md`). |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m16_dunning.py::test_d52_comparison_ledger_receivable_run_and_dunning_stay_internal tests/integration/test_m15_payments.py::test_d52_payment_batch_only_from_leading_system -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D53

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D53 |
| Geprüfte Regelversion | M25 Versammlung, W06 (`docs/rules/W06-resolution.md`); Mehrheitsregeln fachlich zu bestätigen; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Virtuelle Versammlung braucht positiven Grundlagenbeschluss (negativer Umlaufbeschluss ist keine Grundlage); Störung wird als Ereignis dokumentiert. |
| Anonymisierte Eingaben | Versammlung ohne Grundlage; Ergebnis gegen die Auszählung; technische Störung mit dokumentierter Wiederaufnahme. |
| Erwartetes Ergebnis | Ablehnung ohne Grundlage; Verkündung gegen Auszählung abgelehnt; Störung blockiert Abstimmungen und Verkündungen bis zur Wiederaufnahme und bleibt sichtbar. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m25_meeting.py::test_d53_virtual_meeting_needs_basis_and_documents_disruption -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D54

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D54 |
| Geprüfte Regelversion | W06 (`docs/rules/W06-resolution.md`), Status `contested` in `mhvp.hoa.models`; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Erfasste Anfechtung sperrt die Ergebnisbuchung bis zur Bestandskraft; Wirksamkeit und Folgeschritte getrennt; nachträgliche Anfechtung ändert Gebuchtes nicht. |
| Anonymisierte Eingaben | Beschluss mit Anfechtung vor Buchung; Anfechtung nach Buchung. |
| Erwartetes Ergebnis | Buchung gesperrt bis bestandskräftig; nach Buchung erfasste Anfechtung lässt Buchungen und Abrechnung unberührt; kein automatisches Storno. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m24_hoa.py::test_d54_contested_resolution_blocks_posting_and_reverses_nothing -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D55

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D55 |
| Geprüfte Regelversion | 7.7 Prüfexport, M18-02 (`docs/rules/M18-02-pruefexport.md`); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | ZIP mit CSV je Tabelle, Inhaltsverzeichnis, verknüpften Originalen und SHA-256 je `ExportRun`; Storno-Beziehungen im Export; Hintergrundlauf über Worker. |
| Anonymisierte Eingaben | Buchungskreis 783 mit gebuchten und stornierten Einträgen und einem Dokument; Export synchron und mit `run_in_background`. |
| Erwartetes Ergebnis | Synchron: ZIP-Inhalt, Hashes und Stornobeziehung wie erwartet. Worker: Lauf `queued`, Ausführung durch den Worker-Stub, danach Ergebnis mit Hash. |
| Tatsächlich beobachtetes Ergebnis | Synchroner Test bestanden. Worker-Test fehlgeschlagen: `POST /audit-exports` mit `run_in_background` endet mit 500 (`OperationalError` aus kombu, „No hostname was supplied“), der Aufruf erreicht den echten Celery-Broker statt des Test-Stubs. |
| Differenz | Worker-Pfad nicht belegt. Ursache liegt im nicht committeten Arbeitsstand (`mhvp.accounting.audit_export_routers`, `test_m18_audit_export.py`) einer anderen Agentensitzung; Wiederholung derzeit nicht möglich, weil die Migrationskette zwei Köpfe hat (`0100_automation_rules`, `0100_workspace_jobs`) und `require_permission()` in der Sammlung fehlschlägt. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m18_audit_export.py::test_d55_audit_export_zip_contents_hashes_and_reversal tests/integration/test_m18_audit_export.py::test_d55_audit_export_on_worker -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | teilweise: ZIP-Inhalt, Hashes und Storno technisch bestanden; Worker-Pfad Test vorhanden, Lauf zu wiederholen; fachliche Bestätigung offen (V16) |

#### D57

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D57 |
| Geprüfte Regelversion | 9.4 Prompt-Injection, Regel 0.1.6 (KI nur Vorschlag); keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | Dokumenttext, Modellantwort oder Mail enthält Anweisung (neue IBAN, Selbstfreigabe, Datenexport, Zahlung); aufgezeichnete Modellantworten, kein Anbieteraufruf. |
| Anonymisierte Eingaben | Kontakt- und Objektextraktion mit Anweisung; Rechnungsextraktion mit Anweisung in der Modellantwort; Ticket-Mail mit Anweisung und aufgezeichneter Antwort. |
| Erwartetes Ergebnis | Keine Ausführung: bestehender Kontakt und Bankdaten unverändert, Anweisung landet in keinem Feld; striktes Apply-Schema weist eingeschmuggelte Felder ab, bestätigte IBAN des Prüfers wird genutzt, Rechnung bleibt ungebuchter Entwurf; Vorschlag mit leerer Änderungsliste, Annahme abgelehnt; Ereignisprotokoll ohne Freigabe, Zahlung oder Kontaktänderung. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet in allen drei Tests. |
| Differenz | Keine. Evaluationsdatensätze für `classify_email`, `draft_reply`, `map_columns`, `propose_posting` bleiben A46. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m7_ai.py::test_d57_instruction_in_contacts_and_property_output_has_no_effect tests/integration/test_m14_ai_extract_invoice.py::test_d57_instruction_in_model_output_is_not_executed tests/integration/test_m19_ticket_proposals.py::test_d57_instruction_mail_yields_no_change_and_no_bank_update -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

#### D58

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | D58 |
| Geprüfte Regelversion | E13 (Anhang E), 6.9.11 Zahler, Rechnungsempfänger, Zahlungsempfänger getrennt; keine Regelversionsnummer im Code, Stand des Registers `docs/rules/README.md` 26.09.2026 |
| Fachliche Annahmen | SEV-Eigentümer als Gebührenschuldner (`sev_fee_debtor_party_id`), GdWE als Gläubiger des Hausgelds; Mietvertrag im Rechtsträger des SEV-Eigentümers; Verwaltung als Zahlungsempfänger, nie eine Partei. |
| Anonymisierte Eingaben | Zwei Wohnungen, Verwaltergebühr 25,00 EUR je Einheit; Eigentümer mit SEV, Eigentümer ohne SEV, unbekannte Partei. |
| Erwartetes Ergebnis | WEG-Gebührenentwurf ohne Schuldnerpartei: 2 x 25,00 = 50,00 EUR als Kosten der Gemeinschaft; SEV-Gebührenentwurf mit Eigentümer als Schuldner: 25,00 EUR im Rechtsträger des SEV-Eigentümers, Zahlungsempfänger ist der Verwaltungsmandant; Eigentümer ohne SEV 0,00 EUR; unbekannte Partei abgelehnt. |
| Tatsächlich beobachtetes Ergebnis | Wie erwartet. |
| Differenz | Keine. |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | `cd apps/api && uv run pytest tests/integration/test_m13_receivables.py::test_d58_sev_admin_fee_debtor_and_payee -q --no-cov` |
| Softwarestand (Commit, Version) | Arbeitsstand 1.20.0 vor Commit (Basis Commit 6071d61, Branch claude/funny-cerf-ppg9in, mit nicht committeten Arbeitsständen anderer Agentensitzungen) |
| Prüfer | Coding-Agent (technische Ausführung); fachliche Bestätigung offen (V16) |
| Datum (TT.MM.JJJJ) | 26.09.2026 |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | technisch bestanden, fachliche Bestätigung offen (V16) |

### Auffälligkeiten Abschnitt 2

1. D55 Worker-Pfad: `test_d55_audit_export_on_worker` endet mit 500, weil der Aufruf `audit_export_run.delay` den echten Celery-Broker erreicht (kombu `OperationalError`) statt des Test-Stubs; Prüfexport-Dateien sind nicht committeter Arbeitsstand einer anderen Sitzung. Lauf nach Abschluss wiederholen.
2. Die Migrationskette hat nach dem Lauf zwei Köpfe (`0100_automation_rules.py`, `0100_workspace_jobs.py`); vor dem nächsten Testlauf ist die Kette zu linearisieren.
3. D39 deckt nur gleiche Restbeträge ab; D40 sichert die kostenlose Zahlungserinnerung nur über `fee_from_level`; D52 weicht in der Formulierung von Lückenliste A17 ab. Alle drei Punkte sind in `docs/OPEN_QUESTIONS.md` (M12-03, M16-14, M10-05) zur Entscheidung vorgelegt.
4. D41: der Lauf gegen den KoSIT-Validator im CI ist nicht Teil dieses Protokolls; A12 verlangt ihn zusätzlich.
5. Weiterhin ohne Test mit Fallkennung: D09, D11, D24 bis D27 (Heizkosten, Verbrauchsinformation, CO2-Sonderfälle, B10 und B11), D34 (A53), D47 (A44).
6. Die Regelversionsangabe bleibt wie in Abschnitt 1 eine Registerangabe ohne formale Versionsnummer je Regel (Auffälligkeit 1 in Abschnitt 1 gilt fort).
