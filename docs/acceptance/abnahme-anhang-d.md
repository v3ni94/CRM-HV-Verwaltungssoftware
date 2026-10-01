# Abnahmeprotokoll Anhang D (fachliche Abnahme durch den Betreiber)

**Zweck:** Vorlage für die fachliche Abnahme der Fälle D01 bis D58 aus Anhang D des Master-Prompts durch die fachkundige Person (V16) und den Betreiber. Die technischen Tests (`docs/acceptance/D-cases.md`, `docs/acceptance/PROTOKOLL-2026-09-26.md`) belegen nur, dass die Software den vorgegebenen Sollwert liefert; die Abnahme nach Anhang D.3 bestätigt Sollwert, fachliche Annahmen und Sonderfälle. Ein Fall gilt erst nach Eintrag von Ergebnis, Datum, Name und Unterschrift als abgenommen. Das Ergebnis je Fall wird zusätzlich in der Software erfasst (Einstellungen, Buchhaltung, G1 Öffnung, `PUT /api/v1/accounting/g1-opening/items/{Kennung}`), damit der Stand der Öffnungsliste M12-09 aus dem System ableitbar ist.

**Geltung:** Für die Freigabestufe G1 (produktive Buchführung) sind die Fälle mit Freigabestufe G1 sowie die Querschnittsfälle D50, D51 und D57 abzunehmen (23 Fälle). Die übrigen Fälle gehören zu G2 bis G4 und sind hier vollständig aufgeführt, damit ein Protokoll für alle Stufen genügt. Sollwerte stammen wörtlich aus Anhang D; Rechenwege sind ergänzt. Ein Sollwert darf nicht nachträglich an das Ist-Ergebnis angepasst werden (D.3).

**Softwarestand für diese Vorlage:** Arbeitsstand 1.45.0, 29.09.2026. Bei der Abnahme sind Commit und Version einzutragen. Testbefehl je Fall: `cd apps/api && uv run pytest <Testpfad> -q --no-cov` mit gesetzter Testdatenbank (siehe `docs/acceptance/PROTOKOLL-2026-09-26.md`).

**Stand der Testabdeckung:** 57 von 58 Fällen sind durch Tests mit Sollwert abgedeckt; D26 (Ersatzprozess Verbrauchsinformation) ist nicht durch einen Test abgedeckt, weil der Ersatzprozess organisatorisch ist. D24 trägt einen als erwarteter Fehlschlag markierten Test, weil die Betreiberentscheidung M17-03 fehlt; der Sollwert wurde nicht abgeschwächt. D16 ist ohne Fallkennung im Testnamen geprüft.

## Übersicht

| Kennung | Bezeichnung | Modul | Freigabestufe | Testabdeckung | Ergebnis | Datum | Name |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D01 | WEG-Spitze und Rückstand | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D02 | WEG-Anpassung und Guthaben | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D03 | Tatsächliche Rücklage | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D04 | Interner Banktransfer | Buchhaltung und Bank | G1 | Test vorhanden | | | |
| D05 | Echte Gleichzahlungen | Buchhaltung und Bank | G1 | Test vorhanden | | | |
| D06 | Zahlung wird nicht bei Export ausgeglichen | Sollstellung, Mahnwesen und Zahlungen | G2 | Test vorhanden | | | |
| D07 | Teil- und Überzahlung | Buchhaltung und Bank | G1 | Test vorhanden | | | |
| D08 | Centverteilung | Buchhaltung und Bank | G1 | Test vorhanden | | | |
| D09 | Heizkostenüberleitung | Mietabrechnung und Heizkosten | G3/G4 | Test vorhanden | | | |
| D10 | CO₂-Stufengrenze | Mietabrechnung und Heizkosten | G3 | Test vorhanden | | | |
| D11 | Unterjährige Jahresvollständigkeit | Datenübernahme, Aufbewahrung und Sicherung | G1 | Test vorhanden | | | |
| D12 | Abschlag und Schlussrechnung | Belegeingang und Rechnungen | G1 | Test vorhanden | | | |
| D13 | WEG-Ergebnis intern bestätigt, kein wirksamer Beschluss | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D14 | Ergebnisversion nach Beschlussfassung geändert | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D15 | Eigentümerwechsel mit offenen Vorschüssen | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D16 | Nutzen- und Lastenwechsel weicht vom Eigentumswechsel ab | Rechtsträger, Eigentum und Kaution | G4 | Test vorhanden | | | |
| D17 | Eine Person mit zwei Einheiten, eine Einheit mit mehreren Personen | Rechtsträger, Eigentum und Kaution | G4 | Test vorhanden | | | |
| D18 | Untergemeinschaft ohne belegte Grundlage | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D19 | Rücklagenzuführung beschlossen, aber unbezahlt | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D20 | Sonderumlage in Raten mit teilweiser Erstattung | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D21 | Vermietetes Wohnungseigentum ohne Miet-Verteilungsschlüssel | Mietabrechnung und Heizkosten | G3 | Test vorhanden | | | |
| D22 | Mischrechnung Verwaltung, Instandsetzung, Betrieb | Mietabrechnung und Heizkosten | G3 | Test vorhanden | | | |
| D23 | Abrechnung kurz vor Fristende erzeugt, Zugang nicht rechtzeitig | Mietabrechnung und Heizkosten | G3 | Test vorhanden | | | |
| D24 | Mietvorauszahlungen offen, Abrechnung erteilt | Mietabrechnung und Heizkosten | G3 | Test mit xfail | | | |
| D25 | Nutzerwechsel im Winter mit Zwischenablesung | Mietabrechnung und Heizkosten | G3 | Test vorhanden | | | |
| D26 | Pflichtige Verbrauchsinformation, Portal noch nicht entwickelt | Mietabrechnung und Heizkosten | G3 | Test vorhanden (test_d26_consumption_info_substitute.py, 30.09.2026) | | | |
| D27 | Gemischte CO₂-Sachverhalte, Selbstversorgung, fehlende Lieferangaben | Mietabrechnung und Heizkosten | G3 | Test vorhanden | | | |
| D28 | Neue Rechtsregel gilt erst in späterem Zeitraum | Mietabrechnung und Heizkosten | G3 | Test vorhanden | | | |
| D29 | Eigentümer beantragt GdWE-Unterlagen außerhalb eigener Einzelabrechnung | Portal und Datenschutz | G3/G4 | Test vorhanden | | | |
| D30 | Fremde GdWE- oder private SEV-Akte ohne Rechtsgrund | Portal und Datenschutz | G3/G4 | Test vorhanden | | | |
| D31 | Mieter beantragt Abrechnungsbelege mit Angaben Dritter | Portal und Datenschutz | G3 | Test vorhanden | | | |
| D32 | Beirat prüft nur ausgewählte Belege | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D33 | Rechnung nach Beiratsprüfung geändert | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D34 | Lesebestätigung oder Ablauf einer Portal-Einladung | Portal und Datenschutz | G3/G4 | Test vorhanden | | | |
| D35 | Betrag oder Empfänger-IBAN nach Zahlungsfreigabe geändert | Sollstellung, Mahnwesen und Zahlungen | G2 | Test vorhanden | | | |
| D36 | Umgehung der Zahlungsfreigabe mit zweiter Identität | Sollstellung, Mahnwesen und Zahlungen | G2 | Test vorhanden | | | |
| D37 | Bank lehnt Auftrag ab oder führt nur Teile aus | Sollstellung, Mahnwesen und Zahlungen | G2 | Test vorhanden | | | |
| D38 | Bereits zugeordnete Zahlung wird zurückgegeben | Sollstellung, Mahnwesen und Zahlungen | G2 | Test vorhanden | | | |
| D39 | Tilgungsbestimmung gegen Kontenpriorität | Buchhaltung und Bank | G1 | Test vorhanden | | | |
| D40 | Mahnung ohne nachgewiesenen Verzug | Sollstellung, Mahnwesen und Zahlungen | G1 | Test vorhanden | | | |
| D41 | Formal valide E-Rechnung ohne erbrachte Leistung | Belegeingang und Rechnungen | G1 | Test vorhanden | | | |
| D42 | Hybridrechnung mit Widerspruch zwischen XML und PDF | Belegeingang und Rechnungen | G1 | Test vorhanden | | | |
| D43 | Original soll nach OCR gelöscht werden | Belegeingang und Rechnungen | G1 | Test vorhanden | | | |
| D44 | §-35a-Anteil fehlt oder ist KI-Schätzung | Belegeingang und Rechnungen | G3 | Test vorhanden | | | |
| D45 | Steuerliche Option ohne passenden Steuerstatus | Belegeingang und Rechnungen | G1/G3 | Test vorhanden | | | |
| D46 | Aufbewahrung gegen Löschwunsch oder Import-Rücknahme | Datenübernahme, Aufbewahrung und Sicherung | G1 | Test vorhanden | | | |
| D47 | Wiederherstellung eines Backups nach rechtmäßiger Löschung | Datenübernahme, Aufbewahrung und Sicherung | G1 | Test vorhanden | | | |
| D48 | Sollstellungslauf gleichzeitig, Retry und doppelter Aufruf | Buchhaltung und Bank | G1 | Test vorhanden | | | |
| D49 | Historischer OP-Stichtag | Buchhaltung und Bank | G1 | Test vorhanden | | | |
| D50 | Nur-Lese-Nutzer versucht Finanzänderung | Querschnitt: Berechtigung, Regelkonfiguration, KI | ohne eigene Stufe | Test vorhanden | | | |
| D51 | Unbekannte Regel als Konfiguration eingetragen | Querschnitt: Berechtigung, Regelkonfiguration, KI | ohne eigene Stufe | Test vorhanden | | | |
| D52 | Parallelbetrieb mit altem Schreibadapter | Buchhaltung und Bank | G1 | Test vorhanden | | | |
| D53 | Virtuelle Versammlung ohne Grundlage oder mit Störung | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D54 | Anfechtung gegen Beschluss erfasst | WEG-Abrechnung und Versammlung | G4 | Test vorhanden | | | |
| D55 | Steuerberater- und Prüfexport | Prüfexport | G1 | Test vorhanden | | | |
| D56 | Private Kaution neben GdWE- und Miet-Bankmitteln | Rechtsträger, Eigentum und Kaution | G1 | Test vorhanden | | | |
| D57 | KI-Ausgabe enthält Anweisung | Querschnitt: Berechtigung, Regelkonfiguration, KI | ohne eigene Stufe | Test vorhanden | | | |
| D58 | Gebührenrechnung der Verwaltung für SEV | Sollstellung, Mahnwesen und Zahlungen | G1 | Test vorhanden | | | |

Ergebnis: bestanden, nicht bestanden, nicht ausgeführt.

## Buchhaltung und Bank (M10, M11, M12)

### D04 Interner Banktransfer

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Gemeinschaft mit Bank A 10.000,00 EUR und Bank B 20.000,00 EUR. Transfer 1.000,00 EUR von A nach B ohne Gebühr. Beide Kontoauszüge werden importiert. |
| Erwartetes Ergebnis und Rechenweg | Bank A: 10.000,00 EUR minus 1.000,00 EUR = 9.000,00 EUR. Bank B: 20.000,00 EUR plus 1.000,00 EUR = 21.000,00 EUR. Summe: 9.000,00 EUR plus 21.000,00 EUR = 30.000,00 EUR, unverändert. Der Transfer erzeugt keine Einnahme, keine Ausgabe, keine Rücklagenzuführung und wirkt genau einmal: die zweite Hälfte des erkannten Transferpaars gilt als erledigt (Regel B08, Ablehnung mit `MHVP-BANK-0019` beziehungsweise `MHVP-BANK-0020` gegen das Partnerbankkonto). Wird die erste Hälfte vor dem zweiten Import gegen Geldtransit (009999) gebucht, wird die zweite Hälfte gegen Geldtransit gebucht; Geldtransit danach 0,00 EUR. |
| Prüfort im CRM | Bank (`/bank`): beide Umsätze mit Vorschlag Umbuchung; Buchhaltung, Buchungskreis (`/buchhaltung/{id}`), Saldenliste: 001200 und Partnerkonto, Konto 009999 Durchlaufposten; Bank, Abstimmung (`/bank/abstimmung`): Abstimmungsdifferenz 0,00 EUR. |
| Automatisierter Test | `integration/test_annex_d_gaps.py::test_d04_transfer_between_own_accounts_is_booked_once_and_is_no_income`<br>`integration/test_annex_d_gaps.py::test_d04_second_half_of_the_transfer_pair_has_no_second_effect`<br>`integration/test_annex_d_gaps.py::test_d04_pair_guard_error_code_retry_and_tenant_separation`<br>`integration/test_annex_d_gaps.py::test_d04_reversal_reopens_the_pair_once_from_either_half`<br>`integration/test_annex_d_gaps.py::test_d04_parallel_bookings_of_both_halves_post_once`<br>`integration/test_annex_d_gaps.py::test_d04_half_booked_against_transit_before_pairing_is_cleared_via_transit`<br>`integration/test_m10_ledger.py::test_transfer_opening_balance_lock_and_gate`<br>`integration/test_m11_banking.py::test_camt_import_identity_transfer_and_reconciliation` |
| Hinweis | Konfliktbezug E07. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D05 Echte Gleichzahlungen

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Zwei tatsächliche Zahlungen von je 400,00 EUR, gleicher Zahler, gleicher Tag, gleicher Verwendungszweck, aber unterscheidbare Bankdatensätze. Danach werden beide Originaldatensätze erneut importiert. |
| Erwartetes Ergebnis und Rechenweg | Nach dem ersten Import: 400,00 EUR plus 400,00 EUR = 800,00 EUR, zwei Umsätze. Nach dem Wiederimport: weiterhin 800,00 EUR und zwei Umsätze (Identität aus den Bankdatensätzen, nicht aus Betrag, Tag und Zweck). Verboten: 400,00 EUR (Zusammenlegung) oder 1.600,00 EUR (Doppelung). |
| Prüfort im CRM | Bank (`/bank`): Umsatzliste nach dem zweiten Import mit zwei Zeilen zu 400,00 EUR; Importe (`/importe`): Lauf mit Zähler übersprungener Duplikate; Buchhaltung, Kontenblatt Bank: 800,00 EUR. |
| Automatisierter Test | `integration/test_annex_d_gaps.py::test_d05_two_equal_real_payments_stay_two_after_reimport_and_booking`<br>`integration/test_m11_banking.py::test_camt_import_identity_transfer_and_reconciliation`<br>`integration/test_m11_banking.py::test_mt940_import_reimport_and_tenant_separation` |
| Hinweis | Konfliktbezug E07. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D07 Teil- und Überzahlung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Fällige Forderung 1.000,00 EUR. Erste zugeordnete Zahlung 600,00 EUR, zweite tatsächliche Zahlung 450,00 EUR. Schuldner und Tilgungszweck eindeutig. |
| Erwartetes Ergebnis und Rechenweg | Nach Zahlung 1: 1.000,00 EUR minus 600,00 EUR = 400,00 EUR Rest offen. Nach Zahlung 2: 400,00 EUR minus 450,00 EUR = minus 50,00 EUR, also Forderung ausgeglichen und 50,00 EUR gesondertes Guthaben (Konto 001400 Überzahlungen, kein Ertrag). Erstattung oder Verrechnung des Guthabens ist ein eigener Vorgang (M10-03). |
| Prüfort im CRM | Bank (`/bank`): Zuordnung beider Zahlungen; Buchhaltung, Buchungskreis, Offene Posten: Forderung 0,00 EUR offen; Kontenblatt 001400: 50,00 EUR; Debitorenkonto des Zahlers mit Guthaben. |
| Automatisierter Test | `integration/test_annex_d_gaps.py::test_d07_partial_then_overpayment_via_bank_import_leaves_separate_credit`<br>`integration/test_m10_ledger.py::test_ledger_per_legal_entity_open_items_and_reversal` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D08 Centverteilung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | 100,00 EUR auf drei identische Verteilungsgewichte, keine abweichende Vorschrift. Der Rest wird nach stabiler, vorab bestimmter Zuordnung ausgeglichen. |
| Erwartetes Ergebnis und Rechenweg | 100,00 EUR geteilt durch 3 = 33,333... EUR; gerundet 33,33 EUR je Anteil = 99,99 EUR; Rest 0,01 EUR geht an den vorab bestimmten Datensatz. Ergebnis: 33,34 EUR, 33,33 EUR, 33,33 EUR, Summe 100,00 EUR. Eine andere Sortierung der Bildschirmzeilen ändert nicht, welcher Datensatz den Cent erhält. |
| Prüfort im CRM | Abrechnung (`/abrechnung/{id}`): Verteilung mit drei gleichen Anteilen, Summenkontrolle; Buchhaltung, Buchungssatz mit drei Zeilen. |
| Automatisierter Test | `integration/test_m17_operating_costs.py::test_d08_d10_units` |
| Hinweis | Konfliktbezug E08 (Regel B06). |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D39 Tilgungsbestimmung gegen Kontenpriorität

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Zahlung mit eindeutiger Tilgungsbestimmung des Zahlers (Verwendungszweck nennt einen bestimmten offenen Posten), die einer internen Kontenpriorität oder der Vorschlagsreihenfolge widerspricht. |
| Erwartetes Ergebnis und Rechenweg | Die Tilgungsbestimmung des Zahlers geht vor (M10-03, §§ 366, 367 BGB als Regelstand, Rechtsprüfung vor G1 offen). Die Plattform ordnet den benannten Posten zu oder zeigt den Widerspruch zur Prüfung; sie wendet nie stillschweigend die interne Reihenfolge an. Der Vorschlag bleibt Vorschlag, eine Person bestätigt. |
| Prüfort im CRM | Bank (`/bank`): Buchungsvorschlag mit Hinweis Tilgungsbestimmung; Buchhaltung, Offene Posten nach der Buchung: der benannte Posten ist ausgeglichen, die übrigen unverändert. |
| Automatisierter Test | `integration/test_m12_matching.py::test_d39_payment_determination_is_not_overridden_by_account_priority` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D48 Sollstellungslauf gleichzeitig, Retry und doppelter Aufruf

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Ein Sollstellungslauf wird zweimal gleichzeitig gestartet, nach Abbruch wiederholt und mit demselben Idempotenzschlüssel doppelt aufgerufen. |
| Erwartetes Ergebnis und Rechenweg | Genau eine vollständige wirtschaftliche Wirkung: Anzahl der Sollstellungsposten und Summe entsprechen einem Lauf. Keine halben Buchungen (Transaktion), keine doppelten offenen Posten; der Wiederholungsaufruf liefert dasselbe Ergebnis. |
| Prüfort im CRM | Buchhaltung, Sollstellungen (`/buchhaltung/sollstellungen`): ein Lauf mit Positionen; Buchhaltung, Offene Posten: je Vertrag genau ein Posten der Periode. |
| Automatisierter Test | `integration/test_m13_receivables.py::test_d48_receivable_run_concurrency_retry_and_idempotency` |
| Hinweis | Konfliktbezug E15. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D49 Historischer OP-Stichtag

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Offene Posten zu einem Stichtag abfragen, danach Zahlung und Storno nach dem Stichtag buchen, Abfrage zum selben Stichtag wiederholen. |
| Erwartetes Ergebnis und Rechenweg | Beide Abfragen liefern denselben Bestand (Summe und Posten) zum Stichtag. Spätere Zahlungen und Stornos werden nicht rückwirkend eingerechnet; Buchungen nach dem Stichtag erscheinen nur in einer Abfrage mit späterem Stichtag. |
| Prüfort im CRM | Buchhaltung, Buchungskreis, Offene Posten mit Stichtagsauswahl (`GET /accounting/ledgers/{id}/open-items?as_of=`); Saldenliste zum Stichtag. |
| Automatisierter Test | `integration/test_m10_ledger.py::test_d49_historical_open_items_after_later_payment_and_reversal` |
| Hinweis | Konfliktbezug E15. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D52 Parallelbetrieb mit altem Schreibadapter

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Buchungskreis mit führendem System Immoware24 (nicht führende Plattform). Sollstellungslauf, Mahnlauf und Zahlungslauf werden in der Plattform gestartet. |
| Erwartetes Ergebnis und Rechenweg | Genau ein führender Geldprozess je Scope: im nicht führenden Buchungskreis entstehen nur interne Vergleichsbuchungen ohne Außenwirkung; keine Mahnung, keine Lastschrift und kein Zahlungsauftrag aus beiden Systemen (Zahlungsläufe nur aus dem führenden System). Umstellung nur über Buchhaltung, Buchungskreis, Führendes System (erfordert G1). |
| Prüfort im CRM | Buchhaltung, Buchungskreis (`/buchhaltung/{id}`): Anzeige führendes System; Mahnwesen (`/buchhaltung/mahnwesen`) und Bank, Zahlungen (`/bank/zahlungen`): keine externen Läufe für den nicht führenden Kreis. |
| Automatisierter Test | `integration/test_m15_payments.py::test_d52_payment_batch_only_from_leading_system`<br>`integration/test_m16_dunning.py::test_d52_comparison_ledger_receivable_run_and_dunning_stay_internal` |
| Hinweis | Konfliktbezug E10; Betreiberentscheidung M10-05 zur Vergleichsbuchung offen. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

## Belegeingang und Rechnungen (M13, M14)

### D12 Abschlag und Schlussrechnung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Gesamte vereinbarte Leistung 5.950,00 EUR brutto. Abschlag 2.380,00 EUR bereits abgerechnet und bezahlt. Die Schlussrechnung weist beides korrekt aus. |
| Erwartetes Ergebnis und Rechenweg | Verbleibende Zahlungsverpflichtung: 5.950,00 EUR minus 2.380,00 EUR = 3.570,00 EUR. Leistungssumme insgesamt 5.950,00 EUR, nicht 8.330,00 EUR (5.950,00 EUR plus 2.380,00 EUR). Buchung, Steuer und Zahlung sind je Rechenwerk gesondert zu prüfen. |
| Prüfort im CRM | Rechnungen (`/rechnungen/{invoiceId}`): Schlussrechnung mit Abschlagsbezug, offener Betrag 3.570,00 EUR; Buchhaltung, Offene Posten Kreditor: 3.570,00 EUR. |
| Automatisierter Test | `integration/test_m14_invoices.py::test_invoice_review_release_post_and_d12` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D41 Formal valide E-Rechnung ohne erbrachte Leistung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | XRechnung, die alle Strukturprüfungen besteht, deren Leistung aber sachlich beanstandet wird. |
| Erwartetes Ergebnis und Rechenweg | Technisch valide (Strukturprüfung grün), sachlich beanstandet (Einwand mit Grund); keine automatische Zahlungsfreigabe. Ausgangsseitig: Erzeugung ohne Leitweg-ID, IBAN oder Steuerdaten gesperrt; Kleinunternehmer und abweichende Steuer werden gesperrt. |
| Prüfort im CRM | Rechnungen, Belegeingang (`/rechnungen/belegeingang`): Entwurf mit Prüfergebnis und Einwand; Freigabe zur Zahlung nicht möglich, solange der Einwand besteht. |
| Automatisierter Test | `integration/test_m13_xrechnung.py::test_d41_xrechnung_issue_generate_check_and_store`<br>`integration/test_m13_xrechnung.py::test_d41_kleinunternehmer_and_vat_mismatch_are_locked`<br>`integration/test_m14_receipt_drafts.py::test_d41_xrechnung_xml_is_read_without_provider_call_and_objection_blocks_release`<br>`unit/test_m13_xrechnung.py::test_d41_fee_lines_carry_minimum_and_maximum_as_explicit_adjustment`<br>`unit/test_m13_xrechnung.py::test_d41_xml_structure_mandatory_fields_and_sums`<br>`unit/test_m13_xrechnung.py::test_d41_kleinunternehmer_uses_exemption_category_with_reason`<br>`unit/test_m13_xrechnung.py::test_d41_structure_check_reports_sum_and_field_findings`<br>`unit/test_m13_xrechnung.py::test_d41_generation_locked_without_leitweg_id_iban_or_tax_data` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D42 Hybridrechnung mit Widerspruch zwischen XML und PDF

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | ZUGFeRD-Rechnung, deren XML-Teil und PDF-Text sich in Betrag oder Empfänger widersprechen. |
| Erwartetes Ergebnis und Rechenweg | Der Widerspruch wird sichtbar ausgewiesen; die strukturierten Daten bleiben maßgeblich erhalten, der PDF-Text als Zusatzinformation. Keine stille Auswahl einer Seite; Zahlungsprüfung durch eine Person. |
| Prüfort im CRM | Rechnungen, Belegeingang: Entwurf mit Konfliktanzeige XML gegen PDF gegen KI-Lesung; Freigabe erst nach Entscheidung der Person. |
| Automatisierter Test | `integration/test_m14_receipt_drafts.py::test_d42_hybrid_zugferd_conflict_is_visible_and_never_chosen_silently`<br>`unit/test_m14_einvoice.py::test_d42_hybrid_conflicts_xml_against_pdf_text_and_against_ai_reading` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D43 Original soll nach OCR gelöscht werden

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Rechnung liegt als Original und als OCR-Text beziehungsweise JSON-Extraktion vor; Löschung des Originals wird angefordert. |
| Erwartetes Ergebnis und Rechenweg | Die Löschung wird abgelehnt und protokolliert; OCR und JSON ersetzen das Original nicht (Aufbewahrung, Beweissicherung). Das Original bleibt verknüpft. |
| Prüfort im CRM | Dokumente (`/dokumente/{documentId}`): Löschversuch mit Ablehnung und Sperrgrund; Rechnung mit verknüpftem Original. |
| Automatisierter Test | `integration/test_m14_ai_extract_invoice.py::test_d43_d46_original_locked_after_json_extraction_and_import_undo`<br>`integration/test_m6_documents.py::test_d43_original_locked_while_only_ocr_text_exists` |
| Hinweis | Konfliktbezug E05. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D44 §-35a-Anteil fehlt oder ist KI-Schätzung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | Rechnung mit haushaltsnahen Dienstleistungen ohne ausgewiesenen Lohnanteil; die KI schätzt einen Anteil. |
| Erwartetes Ergebnis und Rechenweg | Die Schätzung wird nie als belegter Betrag gezeigt; der Anteil bleibt offen mit Nachforderung beim Aussteller oder Prüfung durch eine Person. Kein Fantasiebetrag in Abrechnung oder Bescheinigung. |
| Prüfort im CRM | Rechnungen, Belegeingang: Feld § 35a mit Kennzeichen Schätzung, nicht übernommen; Abrechnung: kein § 35a-Ausweis ohne Nachweis. |
| Automatisierter Test | `integration/test_m14_receipt_drafts.py::test_d44_ai_estimated_section_35a_share_is_never_shown_as_evidence`<br>`unit/test_m14_einvoice.py::test_d44_section_35a_estimate_is_never_evidence` |
| Hinweis | Freigabestufe G3, hier wegen des Kontenkennzeichens § 35a mitgeführt. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D45 Steuerliche Option ohne passenden Steuerstatus

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1/G3 |
| Eingaben und fachliche Annahmen | Buchungskreis mit Umsatzsteueroption; Rechnung mit Steuer und Sollstellung mit Option, aber ohne freigegebenen Steuerstatus. |
| Erwartetes Ergebnis und Rechenweg | Keine automatische Vorsteuer- oder Umsatzsteuerbuchung aus der bloßen Flächenbelegung: die Rechnung wird nicht gebucht, die Sollstellungsposition bleibt manuell. Freigabe des Steuerstatus durch die Steuerberatung (V21) ist Voraussetzung. |
| Prüfort im CRM | Rechnungen: Buchung mit Sperrhinweis; Buchhaltung, Sollstellungen: Position mit Status manuell; Einstellungen, Buchhaltung, Steuern (`/einstellungen/buchhaltung/steuern`). |
| Automatisierter Test | `integration/test_m13_receivables.py::test_d45_receivable_run_vat_option_without_tax_status_stays_manual`<br>`integration/test_m14_invoices.py::test_d45_invoice_with_vat_on_option_ledger_is_not_posted` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

## Sollstellung, Mahnwesen und Zahlungen (M13, M15, M16)

### D06 Zahlung wird nicht bei Export ausgeglichen

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G2 |
| Eingaben und fachliche Annahmen | Freigegebene Rechnung 1.190,00 EUR. Zahlungsdatei exportiert, dann eingereicht, später ausgeführt. Doppelte Rückmeldung der Bank. |
| Erwartetes Ergebnis und Rechenweg | Nach Export und Einreichung: Verbindlichkeit 1.190,00 EUR offen, Bankbestand unverändert. Nach Ausführung oder Nachweis: einmaliger Ausgleich 1.190,00 EUR (offen 0,00 EUR). Eine zweite Rückmeldung erzeugt keinen zweiten Ausgleich. |
| Prüfort im CRM | Bank, Zahlungen (`/bank/zahlungen`): Lauf mit Status exportiert, eingereicht, ausgeführt; Buchhaltung, Offene Posten Kreditor je Status. |
| Automatisierter Test | `integration/test_annex_d_money.py::test_d06_export_and_submission_leave_bank_and_payable_untouched` |
| Hinweis | Freigabestufe G2 (Zahlungsveranlassung); Konfliktbezug E09. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D35 Betrag oder Empfänger-IBAN nach Zahlungsfreigabe geändert

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G2 |
| Eingaben und fachliche Annahmen | Zahlung freigegeben; danach werden Betrag oder Empfänger-IBAN geändert. |
| Erwartetes Ergebnis und Rechenweg | Die alte Freigabe ist für den neuen Zahlungsstand unwirksam; erneute Prüfung und Freigabe erforderlich, bevor exportiert wird. |
| Prüfort im CRM | Bank, Zahlungen: Zahlung fällt nach der Änderung auf Status zu prüfen zurück; Ereignisprotokoll. |
| Automatisierter Test | `integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback` |
| Hinweis | Konfliktbezug E09. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D36 Umgehung der Zahlungsfreigabe mit zweiter Identität

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G2 |
| Eingaben und fachliche Annahmen | Ein Nutzer erstellt eine Zahlung und versucht sie mit einem zweiten Konto oder API-Schlüssel selbst freizugeben. |
| Erwartetes Ergebnis und Rechenweg | Die Freigabe verlangt eine andere Person (serverseitig geprüft, `MHVP-GATE-0002` beziehungsweise Fachfehler der Zahlung); kein scheinbares Vier-Augen-Prinzip über Identitäten derselben Person oder Schlüssel. |
| Prüfort im CRM | Bank, Zahlungen: Freigabe durch den Ersteller abgelehnt; Einstellungen, Benutzer. |
| Automatisierter Test | `integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback` |
| Hinweis | Konfliktbezug E09. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D37 Bank lehnt Auftrag ab oder führt nur Teile aus

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G2 |
| Eingaben und fachliche Annahmen | Zahlungslauf mit mehreren Aufträgen; die Bank meldet Ablehnung eines Auftrags und Teilausführung. |
| Erwartetes Ergebnis und Rechenweg | Nur tatsächlich bestätigte Teilbeträge werden ausgeglichen; abgelehnte Aufträge bleiben offen mit Fehlergrund; Restposten sind nachvollziehbar. |
| Prüfort im CRM | Bank, Zahlungen: Rückmeldung je Auftrag; Buchhaltung, Offene Posten: nur bestätigte Beträge ausgeglichen. |
| Automatisierter Test | `integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback` |
| Hinweis | Konfliktbezug E09. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D38 Bereits zugeordnete Zahlung wird zurückgegeben

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G2 |
| Eingaben und fachliche Annahmen | Eine zugeordnete Zahlung wird als Rückläufer zurückgegeben, mit Gebühr. |
| Erwartetes Ergebnis und Rechenweg | Die ursprüngliche Zuordnung wird nachvollziehbar korrigiert (Storno mit Grundcode `bank_return`), der offene Posten ist wieder richtig offen; Gebühren werden nur belegt und geprüft gebucht, nie automatisch dem Schuldner belastet. |
| Prüfort im CRM | Bank (`/bank`): Rückläufer mit Bezug zur Ursprungsbuchung; Buchhaltung, Journal: Stornosatz; Offene Posten wieder offen. |
| Automatisierter Test | `integration/test_m15_payments.py::test_d35_to_d38_payment_release_and_bank_feedback` |
| Hinweis | Konfliktbezug E09. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D40 Mahnung ohne nachgewiesenen Verzug

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Mahnlauf ohne Gebührenbetrag und ohne Basiszinssatz; Verzug nicht nachgewiesen. |
| Erwartetes Ergebnis und Rechenweg | Keine automatische Nebenforderung (keine Mahngebühr, keine Zinsen, keine 40,00 EUR Pauschale); Anspruchsart und Beteiligte werden geprüft, der Mahnlauf erzeugt nur den Mahnvorgang ohne Zusatzforderung. |
| Prüfort im CRM | Buchhaltung, Mahnwesen (`/buchhaltung/mahnwesen`): Lauf ohne Nebenforderungen; Mahnwesen, Einstellungen (`/buchhaltung/mahnwesen/einstellungen`). |
| Automatisierter Test | `integration/test_m16_dunning.py::test_d40_dunning_without_fee_amount_and_base_rate_creates_no_side_claim` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D58 Gebührenrechnung der Verwaltung für SEV

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Verwaltergebühr für eine Sondereigentumsverwaltung: Zahler, Rechnungsempfänger und Zahlungsempfänger. |
| Erwartetes Ergebnis und Rechenweg | Schuldner ist der SEV-Eigentümer, Zahlungsempfänger die Verwaltung; das Feld `recipient` löst keinen Honorarfluss an den Eigentümer aus. Debitor und Zahlungsempfänger sind getrennt ausgewiesen. |
| Prüfort im CRM | Buchhaltung, Sollstellungen: Position Verwaltergebühr mit Schuldner und Empfänger; Buchhaltung, Buchungskreis des Verwalters (Mandant): Forderung. |
| Automatisierter Test | `integration/test_m13_receivables.py::test_d58_sev_admin_fee_debtor_and_payee` |
| Hinweis | Konfliktbezug E13. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

## Datenübernahme, Aufbewahrung und Sicherung (M6, M7, M8, M9)

### D11 Unterjährige Jahresvollständigkeit

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Übernahme im laufenden Jahr: 400,00 EUR belegte Ausgaben vor Übernahme, 600,00 EUR danach; Anfangsbestand wird zusätzlich importiert. |
| Erwartetes Ergebnis und Rechenweg | Jahresausgaben: 400,00 EUR plus 600,00 EUR = 1.000,00 EUR. Der Anfangsbestand (Konto 009000) ist keine zusätzliche Ausgabe. Für alle 1.000,00 EUR ist die Belegkette verfügbar; Daten vor der Übernahme fehlen nicht. |
| Prüfort im CRM | Importe (`/importe`): Übernahmelauf mit Anfangsbestand; Buchhaltung, Kontenblatt Kostenkonto: 1.000,00 EUR mit Belegverknüpfung; Abrechnung: Jahressumme 1.000,00 EUR. |
| Automatisierter Test | `integration/test_annex_d_money.py::test_d11_mid_year_takeover_year_costs_complete_with_documents` |
| Hinweis | Konfliktbezug E10. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D46 Aufbewahrung gegen Löschwunsch oder Import-Rücknahme

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Löschwunsch und Rücknahme eines Imports treffen auf Unterlagen mit laufender Aufbewahrung oder Sperre. |
| Erwartetes Ergebnis und Rechenweg | Rechtmäßig gesperrte Unterlagen bleiben erhalten; Ablehnung oder Teillöschung wird begründet und protokolliert; die Import-Rücknahme entfernt kein erfasstes Original. |
| Prüfort im CRM | Dokumente, Löschvorschläge (`/dokumente/loeschvorschlaege`) und Einstellungen, Aufbewahrung (`/einstellungen/aufbewahrung`): Ablehnung mit Grund; Importe: Rücknahme ohne Löschung. |
| Automatisierter Test | `integration/test_m14_ai_extract_invoice.py::test_d43_d46_original_locked_after_json_extraction_and_import_undo`<br>`integration/test_m6_documents.py::test_d43_original_locked_while_only_ocr_text_exists`<br>`integration/test_m7_ai.py::test_d46_import_undo_never_removes_a_recorded_original` |
| Hinweis | Konfliktbezug E05. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D47 Wiederherstellung eines Backups nach rechtmäßiger Löschung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Backup wird nach einer bereits protokollierten rechtmäßigen Löschung wiederhergestellt. |
| Erwartetes Ergebnis und Rechenweg | Das Löschjournal wird nach der Wiederherstellung erneut angewendet (Replay): rechtmäßig gelöschte Dokumente sind wieder gelöscht, Dokumente mit anderem Inhalt unter derselben Kennung werden nie gelöscht (Beweisdaten bleiben). |
| Prüfort im CRM | Kein CRM-Bild; Runbook Wiederherstellung (`docs/runbooks/`), Ereignisprotokoll des Replays. |
| Automatisierter Test | `integration/test_m9_restore_replay.py::test_d47_replay_deletion_journal_after_restore`<br>`integration/test_m9_restore_replay.py::test_d47_replay_never_deletes_a_document_with_another_content` |
| Hinweis | Konfliktbezug E05; Restore einer echten Sicherung bleibt Runbook-Schritt. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

## Prüfexport (M18)

### D55 Steuerberater- und Prüfexport

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Prüfexport eines Buchungskreises mit Buchungen, Storno, Freigaben und Originalbelegen. |
| Erwartetes Ergebnis und Rechenweg | Das ZIP enthält Buchungen, Schlüssel, Historie, Freigaben und Belege mit Hashes nachvollziehbar verbunden (Tabellen einschließlich Entscheidungen, Nachkontrolle, Automatikstufen, Regelvorschläge, Bankregeln); der Storno ist als Stornosatz enthalten. Keine nur optische PDF-Sammlung. Der Export läuft auch über den Worker. |
| Prüfort im CRM | Buchhaltung, Buchungskreis, Auswertungen (`/buchhaltung/{id}/auswertungen`): Prüfexport starten und herunterladen; Einstellungen, Buchhaltung, DATEV (`/einstellungen/buchhaltung/datev`). |
| Automatisierter Test | `integration/test_m18_audit_export.py::test_d55_audit_export_zip_contents_hashes_and_reversal`<br>`integration/test_m18_audit_export.py::test_d55_audit_export_on_worker` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

## Rechtsträger, Eigentum und Kaution (M4, M5)

### D16 Nutzen- und Lastenwechsel weicht vom Eigentumswechsel ab

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Eigentümerwechsel mit Datum der Grundbucheintragung und abweichendem Datum des Nutzen- und Lastenwechsels. |
| Erwartetes Ergebnis und Rechenweg | Beide Zeitpunkte werden getrennt gespeichert und ausgewiesen (Außenverhältnis zur Gemeinschaft, Innenverhältnis zwischen Verkäufer und Käufer); kein stilles Gleichsetzen. |
| Prüfort im CRM | Objekte, WEG, Einheit, Eigentümerwechsel (`/objekte`, Anleitung Eigentümerwechsel); Verträge (`/vertraege`). |
| Automatisierter Test | `integration/test_m5_contracts.py::test_ownership_transfer_and_sev` |
| Hinweis | Konfliktbezug E02; Test ohne Fallkennung im Namen. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D17 Eine Person mit zwei Einheiten, eine Einheit mit mehreren Personen

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Eigentümer A besitzt zwei Einheiten; Einheit B gehört zwei Personen gemeinsam. |
| Erwartetes Ergebnis und Rechenweg | Partei- und Stimmrechtszuordnung nach Gemeinschaftsregel: A hat eine Kopfstimme, die Bruchteilsgemeinschaft eine Partei; keine doppelte Kopfstimme, keine doppelte Forderung je Einheit. |
| Prüfort im CRM | Objekte, WEG (`/weg/{propertyId}`): Eigentümerliste und Stimmrechte; Versammlung: Stimmenzählung. |
| Automatisierter Test | `integration/test_m5_contracts.py::test_d17_one_owner_two_units_and_one_unit_two_owners` |
| Hinweis | Konfliktbezug E02. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D56 Private Kaution neben GdWE- und Miet-Bankmitteln

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G1 |
| Eingaben und fachliche Annahmen | Kautionskonto einer Mietpartei und Bankkonten der Gemeinschaft und der Mietverwaltung nebeneinander. |
| Erwartetes Ergebnis und Rechenweg | Die Kaution bleibt ihrer Vermögenssphäre zugeordnet: sie zählt nicht zur freien Liquidität, ist keine Quelle für Zahlungsaufträge und wird nicht per Lastschrift eingezogen; Zinsen folgen der Zuordnung (Verzinsung B15 offen). |
| Prüfort im CRM | Bank (`/bank`): Kautionskonto mit Kennzeichen; Start, Liquidität; Bank, Zahlungen: Kautionskonto nicht wählbar; Bank, Lastschriften (`/bank/lastschriften`). |
| Automatisierter Test | `integration/test_annex_d_money.py::test_d56_deposit_funds_are_neither_free_liquidity_nor_a_payment_source` |
| Hinweis | Konfliktbezug E01; Verzinsung (B15) offen. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

## WEG-Abrechnung und Versammlung (M24, M25)

### D01 WEG-Spitze und Rückstand

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Kostenanteil 3.000,00 EUR; beschlossene kostenbezogene Soll-Vorschüsse 2.800,00 EUR; darauf gezahlt 2.500,00 EUR. Kein Eigentümerwechsel, keine Rücklage, keine Sonderumlage. |
| Erwartetes Ergebnis und Rechenweg | Abrechnungsspitze: 3.000,00 EUR minus 2.800,00 EUR = 200,00 EUR. Vorschussrückstand: 2.800,00 EUR minus 2.500,00 EUR = 300,00 EUR. Gesamtbelastung nach Beschlusswirkung: 200,00 EUR plus 300,00 EUR = 500,00 EUR. Verboten: neue Forderung 500,00 EUR plus nochmals 300,00 EUR (800,00 EUR). |
| Prüfort im CRM | WEG (`/weg/{propertyId}`), Jahresabrechnung, Einzelabrechnung: Spitze 200,00 EUR, Rückstand 300,00 EUR getrennt; Buchhaltung, Offene Posten Eigentümer. |
| Automatisierter Test | `integration/test_m24_hoa.py::test_hoa_statement_d01_d03` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D02 WEG-Anpassung und Guthaben

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Kostenanteil 2.500,00 EUR; Soll-Vorschüsse 2.800,00 EUR; gezahlt 2.500,00 EUR; im Übrigen wie D01. |
| Erwartetes Ergebnis und Rechenweg | Abrechnungsanpassung: 2.500,00 EUR minus 2.800,00 EUR = minus 300,00 EUR (Guthaben). Vorschussrückstand: 2.800,00 EUR minus 2.500,00 EUR = 300,00 EUR, getrennt ausgewiesen. Gesamtübersicht rechnerisch 0,00 EUR, aber keine automatische Auszahlung von 300,00 EUR und keine Löschung der Altforderung; Verrechnung nur nach eigenständiger rechtlicher Prüfung. |
| Prüfort im CRM | WEG, Jahresabrechnung, Einzelabrechnung: Guthaben und Rückstand getrennt; Bank, Zahlungen: kein automatischer Auszahlungsauftrag. |
| Automatisierter Test | `integration/test_annex_d_hoa.py::test_d02_credit_result_is_neither_paid_out_nor_offset_against_arrears` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D03 Tatsächliche Rücklage

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Anfangsbestand 20.000,00 EUR; Soll-Zuführung 6.000,00 EUR, tatsächlich eingegangen 4.500,00 EUR; aus der Rücklage finanziert 3.000,00 EUR; Nettozins 100,00 EUR. |
| Erwartetes Ergebnis und Rechenweg | Tatsächlicher Bestand: 20.000,00 EUR plus 4.500,00 EUR minus 3.000,00 EUR plus 100,00 EUR = 21.600,00 EUR. Offene Beiträge: 6.000,00 EUR minus 4.500,00 EUR = 1.500,00 EUR, separat und nicht verfügbar. Verboten: 23.100,00 EUR (Soll-Zuführung statt Ist). Bank- und Mittelzuordnung (001201) zusätzlich abstimmen. |
| Prüfort im CRM | WEG, Jahresabrechnung, Vermögensbericht: Rücklage Ist 21.600,00 EUR, offene Beiträge 1.500,00 EUR; Buchhaltung, Kontenblatt 008000 und 001201. |
| Automatisierter Test | `integration/test_m24_hoa.py::test_hoa_statement_d01_d03` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D13 WEG-Ergebnis intern bestätigt, kein wirksamer Beschluss

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Jahresabrechnung intern bestätigt; kein Beschluss nach § 28 Abs. 2 WEG erfasst. |
| Erwartetes Ergebnis und Rechenweg | Keine neue beschlussabhängige Forderung (Abrechnungsspitze) und keine darauf gestützte Lastschrift; Statusübergang mit Regelkennung als Hinweis. |
| Prüfort im CRM | WEG, Jahresabrechnung: Status ohne Beschluss, Sollstellung der Spitze gesperrt; Bank, Lastschriften: kein Einzug. |
| Automatisierter Test | `integration/test_annex_d_hoa.py::test_d13_no_resolution_means_no_result_claim_and_no_direct_debit`<br>`integration/test_m24_hoa.py::test_check_transition_messages_carry_the_rule_id` |
| Hinweis | Konfliktbezug E03. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D14 Ergebnisversion nach Beschlussfassung geändert

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Beschluss zu Abrechnungsversion 1 erfasst; danach Version 2 mit anderen Zahlen erzeugt. |
| Erwartetes Ergebnis und Rechenweg | Der Beschluss bleibt an Version 1; er wird nicht auf Version 2 umgehängt. Die Differenz beider Versionen und der erneut nötige Beschlussschritt sind sichtbar. |
| Prüfort im CRM | WEG, Jahresabrechnung: Versionsvergleich mit Differenz; Beschlussbezug auf Version 1. |
| Automatisierter Test | `integration/test_annex_d_hoa.py::test_d14_new_result_version_after_resolution_keeps_the_resolution_on_the_old_one`<br>`integration/test_m24_hoa.py::test_d14_statement_version_diff` |
| Hinweis | Konfliktbezug E03. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D15 Eigentümerwechsel mit offenen Vorschüssen

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Alter Eigentümer mit Vorschussrückstand; neuer Eigentümer; Abrechnung wird später beschlossen. |
| Erwartetes Ergebnis und Rechenweg | Gewöhnlicher Erwerbsfall ohne Sonderhaftung: der Vorschussrückstand bleibt beim bisherigen Schuldner, die Abrechnungsspitze trifft den Eigentümer zum Beschlusszeitpunkt (Regel owner-at-resolution-v1). Kaufvertragsausgleich getrennt; Regelstand P01 und Sonderfälle vom Betreiber ausdrücklich freizugeben. |
| Prüfort im CRM | WEG, Jahresabrechnung: Zuordnung Spitze und Rückstand je Eigentümer; Buchhaltung, Debitorenkonten alt und neu. |
| Automatisierter Test | `integration/test_annex_d_hoa.py::test_d15_owner_change_arrears_stay_with_seller_result_goes_to_owner_at_resolution` |
| Hinweis | Konfliktbezug E02; Produktivfreigabe hängt an P01. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D18 Untergemeinschaft ohne belegte Grundlage

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Kostenverteilung auf eine angelegte Untergemeinschaft ohne erfasste Grundlage (Teilungserklärung, Beschluss). |
| Erwartetes Ergebnis und Rechenweg | Keine endgültige Abrechnung nur wegen eines Filters; Prüfhinweis und Freigabestopp für den betroffenen Teil. |
| Prüfort im CRM | WEG, Jahresabrechnung: Prüfhinweis Untergemeinschaft, Freigabe gesperrt. |
| Automatisierter Test | `integration/test_m24_hoa.py::test_d18_sub_community_without_basis_blocks_release` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D19 Rücklagenzuführung beschlossen, aber unbezahlt

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Beschlossene Zuführung, teilweise nicht gezahlt; Rücklagenkonto der Bank weist einen anderen Stand aus. |
| Erwartetes Ergebnis und Rechenweg | Soll, Ist, Bankanlage und Rückstand werden getrennt ausgewiesen; die Differenz wird erklärt, keine automatische Ausgleichsbuchung. |
| Prüfort im CRM | WEG, Vermögensbericht: vier Werte getrennt; Buchhaltung, Kontenblätter 008000, 001201, 060200. |
| Automatisierter Test | `integration/test_m24_hoa.py::test_d19_reserve_contribution_unpaid_no_settlement_entry` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D20 Sonderumlage in Raten mit teilweiser Erstattung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Sonderumlage in mehreren Raten eingezogen, später teilweise erstattet. |
| Erwartetes Ergebnis und Rechenweg | Zweck, Soll und Ist, Verwendung, Fälligkeiten und Erstattungsgrund bleiben erhalten; keine doppelte Kostenerfassung; Erstattung als eigener Vorgang mit Bezug. |
| Prüfort im CRM | WEG, Sonderumlage: Raten, Zahlungen, Erstattung; Buchhaltung, Offene Posten je Rate. |
| Automatisierter Test | `integration/test_w09_special_levy.py::test_d20_levy_instalments_with_partial_refund` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D32 Beirat prüft nur ausgewählte Belege

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Verwaltungsbeirat prüft eine Stichprobe der Belege im Beiratsportal. |
| Erwartetes Ergebnis und Rechenweg | Der Bericht zeigt Stichprobe, Anzahl und Wert geprüfter Positionen sowie offene und ungeprüfte Positionen; keine Behauptung einer Vollprüfung. Der Beirat bucht nichts und sieht nur freigegebene Belege. |
| Prüfort im CRM | WEG, Belegprüfung Beirat; Beiratsportal (Portal-App). |
| Automatisierter Test | `integration/test_m21_board_portal.py::test_board_reads_positions_and_released_receipts_only_and_never_posts`<br>`integration/test_m25_meeting.py::test_d32_d33_audit_sample_report_and_invoice_change_after_check` |
| Hinweis | Konfliktbezug E14. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D33 Rechnung nach Beiratsprüfung geändert

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Eine vom Beirat geprüfte Rechnung wird danach geändert. |
| Erwartetes Ergebnis und Rechenweg | Die betroffene Prüfung wird als veraltet oder eingeschränkt markiert; der Gesamtstatus bleibt nicht unverändert grün. |
| Prüfort im CRM | WEG, Belegprüfung: Position mit Kennzeichen veraltet; Beiratsportal. |
| Automatisierter Test | `integration/test_m21_board_portal.py::test_board_question_answered_by_management_and_position_outdated_after_change`<br>`integration/test_m25_meeting.py::test_d32_d33_audit_sample_report_and_invoice_change_after_check` |
| Hinweis | Konfliktbezug E14. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D53 Virtuelle Versammlung ohne Grundlage oder mit Störung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Virtuelle Versammlung ohne gültige Beschlussgrundlage, mit falscher Mehrheit oder technischer Störung. |
| Erwartetes Ergebnis und Rechenweg | Regel- und Rechteprüfung vor der Einberufung; Störungen werden dokumentiert; kein erfolgreiches Videotreffen wird unterstellt. |
| Prüfort im CRM | WEG, Versammlung: Grundlage der virtuellen Form, Störungsprotokoll. |
| Automatisierter Test | `integration/test_m25_meeting.py::test_d53_virtual_meeting_needs_basis_and_documents_disruption` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D54 Anfechtung gegen Beschluss erfasst

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G4 |
| Eingaben und fachliche Annahmen | Zu einem gefassten Beschluss wird ein Anfechtungsverfahren erfasst. |
| Erwartetes Ergebnis und Rechenweg | Kein pauschales Löschen oder Ausbuchen; der Wirksamkeitsstatus wird unterschieden, Buchungen aus dem Beschluss sind gesperrt, nichts wird automatisch storniert. |
| Prüfort im CRM | WEG, Beschlüsse: Status angefochten; Buchhaltung: Buchung aus dem Beschluss gesperrt. |
| Automatisierter Test | `integration/test_m24_hoa.py::test_d54_contested_resolution_blocks_posting_and_reverses_nothing` |
| Hinweis | Konfliktbezug E03. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

## Mietabrechnung und Heizkosten (M17)

### D09 Heizkostenüberleitung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3/G4 |
| Eingaben und fachliche Annahmen | Freigegebenes Brennstoffbestandsverfahren (Modell): Zahlung für Brennstoff 10.000,00 EUR; verbrauchter zurechenbarer Brennstoff 8.000,00 EUR; sonst keine Heizkosten. |
| Erwartetes Ergebnis und Rechenweg | Geldfluss: 10.000,00 EUR. Verbrauchsverteilung: 8.000,00 EUR. Unterschied: 10.000,00 EUR minus 8.000,00 EUR = 2.000,00 EUR, in der Überleitung erklärt (Bestandsveränderung), nicht weggerechnet. Freigabe P02 erforderlich; keine universelle Formel. |
| Prüfort im CRM | Abrechnung, Heizkosten: Überleitung W04 mit Differenz 2.000,00 EUR; WEG, Jahresabrechnung: Geldfluss 10.000,00 EUR. |
| Automatisierter Test | `integration/test_annex_d_hoa.py::test_d09_fuel_payment_and_consumption_differ_and_the_bridge_explains_it` |
| Hinweis | Produktivfreigabe hängt an P02. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D10 CO₂-Stufengrenze

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | Wohngebäude, Regelfall: spezifischer Ausstoß 12,0 kg CO₂ je m² und Jahr, CO₂-Kosten 100,00 EUR. Vergleichsfall mit Wert unter 12. |
| Erwartetes Ergebnis und Rechenweg | Stufe 12 bis unter 17: Mieteranteil 90 Prozent von 100,00 EUR = 90,00 EUR, Vermieteranteil 10,00 EUR. Vergleichsfall unter 12: 100,00 EUR Mieter, 0,00 EUR Vermieter. Kein vorzeitiges Abrunden des Eingangswerts in eine günstigere Stufe. |
| Prüfort im CRM | Abrechnung (`/abrechnung/{id}`), Heizkosten: CO₂-Aufteilung je Einheit mit Stufe und Anteilen. |
| Automatisierter Test | `integration/test_m17_operating_costs.py::test_d08_d10_units` |
| Hinweis | Rechtsstand H04 zu bestätigen (M17-02). |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D21 Vermietetes Wohnungseigentum ohne Miet-Verteilungsschlüssel

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | Vermietete Eigentumswohnung; im Mietvertrag ist kein abweichender Verteilungsschlüssel erfasst. |
| Erwartetes Ergebnis und Rechenweg | Die Abrechnung verlangt den erfassten Schlüssel (§ 556a Abs. 3 BGB und Billigkeit im Regelwerk); die allgemeine Quadratmeterregel wird nicht automatisch angewendet. |
| Prüfort im CRM | Abrechnung: Sperrhinweis fehlender Schlüssel; Verträge: Feld Verteilungsschlüssel. |
| Automatisierter Test | `integration/test_m17_operating_costs.py::test_d21_let_condominium_needs_recorded_key` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D22 Mischrechnung Verwaltung, Instandsetzung, Betrieb

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | Rechnung mit Anteilen für Verwaltung, Instandsetzung und laufenden Betrieb. |
| Erwartetes Ergebnis und Rechenweg | Nicht umlagefähige Anteile bleiben aus der Betriebskostenbelastung; die Aufteilung muss gebucht und belegt sein, sonst ist die Abrechnung gesperrt. |
| Prüfort im CRM | Rechnungen: Positionen mit Kontierung je Anteil; Abrechnung: nur umlagefähige Anteile. |
| Automatisierter Test | `integration/test_m17_operating_costs.py::test_d22_mixed_invoice_split_must_be_posted` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D23 Abrechnung kurz vor Fristende erzeugt, Zugang nicht rechtzeitig

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | Mietabrechnung wird kurz vor Ablauf der Abrechnungsfrist erzeugt, erreicht den Empfänger aber nicht rechtzeitig. |
| Erwartetes Ergebnis und Rechenweg | Die Erzeugung gilt nicht als Zugang; Nachforderung wird geprüft, Ausnahme und Alternativprozess sind dokumentiert. |
| Prüfort im CRM | Abrechnung: Zustellstatus getrennt vom Erstellungsdatum; Fristen (`/fristen`). |
| Automatisierter Test | `integration/test_m17_operating_costs.py::test_d23_creation_is_not_access` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D24 Mietvorauszahlungen offen, Abrechnung erteilt

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | Offene Vorauszahlungsposten bei Erteilung der Abrechnung (Modellfall: Abrechnungssaldo gegen gezahlte Vorauszahlungen, ein Vorauszahlungsposten offen). |
| Erwartetes Ergebnis und Rechenweg | Kein doppelter wirtschaftlicher Anspruch: der offene Betrag darf nur einmal beansprucht werden (Modellfall 20,00 EUR statt 120,00 EUR). Behandlung nach fachlich bestätigter Vorschussregel (M17-03); bis dahin sind Struktur und Sperre umgesetzt, die Erteilung ist gesperrt. |
| Prüfort im CRM | Abrechnung: offene Vorauszahlungen getrennt ausgewiesen, Erteilung gesperrt; Buchhaltung, Offene Posten. |
| Automatisierter Test | `integration/test_annex_d_gaps.py::test_d24_open_advances_shown_apart_calculation_creates_no_claim_and_issue_is_locked`<br>`integration/test_annex_d_gaps.py::test_d24_statement_balance_and_open_advance_items_claim_the_open_amount_once (xfail, strikt)` |
| Hinweis | Offen: Betreiberentscheidung M17-03; ein Test als erwarteter Fehlschlag markiert, Sollwert nicht abgeschwächt. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D25 Nutzerwechsel im Winter mit Zwischenablesung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | Nutzerwechsel in der Heizperiode; Zwischenablesung vorhanden, im Vergleichsfall nicht. |
| Erwartetes Ergebnis und Rechenweg | Verbrauchs- und Grundanteile nach den passenden HeizkostenV-Regeln (Zeitanteil beziehungsweise Gradtagszahlen); keine pauschale Ganzjahres-Tagesverteilung; ohne Zwischenablesung wird die Aufteilung gekennzeichnet. |
| Prüfort im CRM | Abrechnung, Heizkosten: Nutzerwechsel mit Anteilen und Kennzeichen. |
| Automatisierter Test | `unit/test_m17_heating_calc.py::test_d25_user_change_time_share_and_notice`<br>`unit/test_m17_heating_calc.py::test_d25_user_change_degree_days`<br>`unit/test_m17_heating_calc.py::test_d25_unit_total_without_intermediate_reading_is_split_and_flagged`<br>`integration/test_m17_heating.py::test_heating_draft_d25_d27` |
| Hinweis | Regelwerte M17-02 offen (Betreiber mit Messdienst und Rechtsberatung). |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D26 Pflichtige Verbrauchsinformation, Portal noch nicht entwickelt

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | Verbrauchsinformation ist zu erteilen; das Portal ist dafür nicht freigegeben. |
| Erwartetes Ergebnis und Rechenweg | Nachgewiesener funktionierender Ersatzprozess; ein Verweis auf eine spätere Phase ist keine Erfüllung. |
| Prüfort im CRM | Einstellungen, Schalter Verbrauchsinformation (H03); Abrechnung, Verbrauchsinformation. |
| Automatisierter Test | **Nicht durch einen Test abgedeckt.** Vorhanden nur: `integration/test_m17_heating.py::test_heating_draft_d25_d27 (nur Datensatz)` |
| Hinweis | Kein Test für den Ersatzprozess; Betreiberentscheidung H03 offen. Der Ersatzprozess ist nicht automatisiert prüfbar. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D27 Gemischte CO₂-Sachverhalte, Selbstversorgung, fehlende Lieferangaben

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | CO₂-Sachverhalte außerhalb des Wohngebäude-Regelfalls; Lieferangaben fehlen. |
| Erwartetes Ergebnis und Rechenweg | Richtige Regelgruppe oder ausdrücklicher Prüfstatus; keine erfundenen Emissionswerte und keine Nullkosten. |
| Prüfort im CRM | Abrechnung, Heizkosten: CO₂-Position mit Status zu prüfen. |
| Automatisierter Test | `unit/test_m17_heating_calc.py::test_d27_unresolved_co2_stays_review_without_zero`<br>`integration/test_m17_heating.py::test_heating_draft_d25_d27` |
| Hinweis | Regelgruppen M17-02 offen. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D28 Neue Rechtsregel gilt erst in späterem Zeitraum

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | Eine veröffentlichte Regeländerung gilt erst ab einem späteren Zeitraum; Abrechnungen für 2026 und Altjahre bestehen. |
| Erwartetes Ergebnis und Rechenweg | Kein Eingriff in bestehende Abrechnungen; die Regelversion ist im Abrechnungs-Snapshot festgeschrieben; Stichtagsauswahl getestet. |
| Prüfort im CRM | Abrechnung: Anzeige der Regelversion je Abrechnung; Plattform, Mietrecht (`/plattform/mietrecht`). |
| Automatisierter Test | `integration/test_m17_operating_costs.py::test_d28_rule_version_pinned_in_snapshot` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

## Portal und Datenschutz (M21)

### D29 Eigentümer beantragt GdWE-Unterlagen außerhalb eigener Einzelabrechnung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3/G4 |
| Eingaben und fachliche Annahmen | Eigentümer fordert im Portal Gemeinschaftsunterlagen an, die nicht seine Einzelabrechnung sind. |
| Erwartetes Ergebnis und Rechenweg | Gesetzlich gedeckter Zugriff wird nicht pauschal durch den eigenen Vertragsfilter blockiert; freigegebene Gemeinschaftsdokumente sind sichtbar. |
| Prüfort im CRM | Eigentümerportal (Portal-App); Dokumente: Freigabe für Gemeinschaft. |
| Automatisierter Test | `integration/test_m21_portal.py::test_d29_owner_sees_gdwe_documents_outside_own_statement` |
| Hinweis | Konfliktbezug E06. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D30 Fremde GdWE- oder private SEV-Akte ohne Rechtsgrund

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3/G4 |
| Eingaben und fachliche Annahmen | Derselbe Nutzer fordert Unterlagen einer fremden Gemeinschaft oder einer privaten SEV-Akte an. |
| Erwartetes Ergebnis und Rechenweg | Zugriff verweigert über API, Download, Suche, KI-Kontext und Sammelexport. |
| Prüfort im CRM | Portal; Assistent (`/assistent`): kein fremdes Dokument im Kontext. |
| Automatisierter Test | `integration/test_m21_portal.py::test_d30_foreign_gdwe_and_sev_files_denied_on_every_path`<br>`integration/test_m7_ai.py::test_d30_ai_context_excludes_foreign_documents` |
| Hinweis | Konfliktbezug E06. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D31 Mieter beantragt Abrechnungsbelege mit Angaben Dritter

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3 |
| Eingaben und fachliche Annahmen | Mieter fordert Belegeinsicht zu einer Abrechnung; Belege enthalten Daten Dritter. |
| Erwartetes Ergebnis und Rechenweg | Zweckbezogene Einsicht mit erforderlicher Schwärzung: der Mieter erreicht nie den ungeschwärzten Beleg und erhält die freigegebene Version mit Schwärzungsvermerk; keine Vollverweigerung, keine Vollfreigabe. |
| Prüfort im CRM | Mieterportal; Dokumente: freigegebene Version mit Vermerk. |
| Automatisierter Test | `integration/test_m21_portal.py::test_d31_tenant_never_reaches_the_unredacted_receipt`<br>`integration/test_m21_portal.py::test_d31_tenant_gets_released_version_with_redaction_note` |
| Hinweis | Konfliktbezug E06. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D34 Lesebestätigung oder Ablauf einer Portal-Einladung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | G3/G4 |
| Eingaben und fachliche Annahmen | Lesebestätigung im Portal; Einladung läuft ab. |
| Erwartetes Ergebnis und Rechenweg | Keine automatische Anerkennung, kein Verzicht, keine ohne Grundlage ausgelöste Rechtsfrist; die Lesebestätigung ist ein Indiz neben der Zustellung. |
| Prüfort im CRM | Kommunikation, Zustellstatus; Portal, Einladungen. |
| Automatisierter Test | `integration/test_m21_read_receipts.py::test_d34_read_receipt_is_an_indication_apart_from_delivery`<br>`integration/test_m21_read_receipts.py::test_d34_expired_invitation_triggers_no_legal_consequence` |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

## Querschnitt: Berechtigung, Regelkonfiguration, KI (D50, D51, D57)

### D50 Nur-Lese-Nutzer versucht Finanzänderung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | ohne eigene Stufe |
| Eingaben und fachliche Annahmen | Nutzer mit Leserecht versucht Finanzänderungen über Massenendpunkt, Job und API-Schlüssel. |
| Erwartetes Ergebnis und Rechenweg | Berechtigung und Freigabe wirken serverseitig (403); das Verstecken in der Oberfläche allein genügt nicht. |
| Prüfort im CRM | Einstellungen, Rollen (`/einstellungen/rollen`); jede Finanzfunktion. |
| Automatisierter Test | `integration/test_d50_authorization.py (11 Tests)` |
| Hinweis | Konfliktbezug E12. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D51 Unbekannte Regel als Konfiguration eingetragen

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | ohne eigene Stufe |
| Eingaben und fachliche Annahmen | Eine Rechts- oder Verteilungsregel wird als Konfiguration ohne Quelle und Entscheidung eingetragen. |
| Erwartetes Ergebnis und Rechenweg | Keine automatische Produktivfreigabe; Quelle, Geltung, Entscheidung und Tests sind erforderlich (auch für Bankregeln: Aktivierung nur mit `max_amount` und Testnachweis, M12-06). |
| Prüfort im CRM | Einstellungen, Regelvorschläge (`/einstellungen/regelvorschlaege`); Bank, Regeln (`/bank/regeln`). |
| Automatisierter Test | `integration/test_d51_rule_configuration.py::test_d51_configured_rule_is_never_productive_without_decision_and_tests` |
| Hinweis | Konfliktbezug E04. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

### D57 KI-Ausgabe enthält Anweisung

| Feld | Inhalt |
| --- | --- |
| Freigabestufe | ohne eigene Stufe |
| Eingaben und fachliche Annahmen | Modellantwort oder Dokumenttext enthält eine Anweisung zu neuer IBAN, eigener Freigabe oder Datenexport. |
| Erwartetes Ergebnis und Rechenweg | Keine Ausführung aus Dokumenttext oder Modellantwort; nur der geprüfte Fachworkflow ändert Bankverbindungen, gibt frei oder exportiert. |
| Prüfort im CRM | Kontakte, Bankverbindungen (Freigabe); Tickets; Rechnungen, Belegeingang. |
| Automatisierter Test | `integration/test_m14_ai_extract_invoice.py::test_d57_instruction_in_model_output_is_not_executed`<br>`integration/test_m19_ticket_proposals.py::test_d57_instruction_mail_yields_no_change_and_no_bank_update`<br>`integration/test_m7_ai.py::test_d57_instruction_in_contacts_and_property_output_has_no_effect` |
| Hinweis | Konfliktbezug E04. |
| Geprüfte Regelversion | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl oder manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Ergebnis | [ ] bestanden [ ] nicht bestanden [ ] nicht ausgeführt |
| Datum (TT.MM.JJJJ) | |
| Name | |

Unterschrift Betreiber: ____________________________

## Gesamtbestätigung

| Feld | Eintrag |
| --- | --- |
| Fachkundige Person (V16) | |
| Abgenommene Fälle G1 (Anzahl von 23) | |
| Fälle mit Vorbehalt (Kennungen, Grund) | |
| Softwarestand (Commit, Version) | |
| Datum (TT.MM.JJJJ) | |
| Unterschrift Betreiber | |

**Nachtrag 01.10.2026 (AE01):** Sollwerte, Freigabe durch die fachkundige Person und Ergebnisse je Fall können im Abnahmeregister (Plattform, Abnahmeregister Anhang D) erfasst werden; `GET /api/v1/accounting/acceptance/export.md` erzeugt dieses Protokoll aus dem System.
