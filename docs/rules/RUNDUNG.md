# Rundungsregister (6.9.8, B06)

| Feld | Inhalt |
| --- | --- |
| ID | RUNDUNG (Querschnitt zu B06) |
| Geltungsbereich | alle Rechenwerte mit Geldbezug und Verhältniswerte im Paket `mhvp` |
| Quellenstatus | Produktstandard (6.9.8); keine Rechtsregel behauptet. Rundungsvorgaben aus Gesetz oder Vereinbarung sind je Rechenwert nicht bestätigt |
| Abnahmefall | D08 (Restcent), D10 (CO2); übrige ohne eigenen Abnahmefall |
| Änderungsgrund | GAH-115, Welle 20 (AI17), 02.10.2026: zentrale Übersicht der im Code verwendeten Rundungsverfahren |

Stand: aus dem Code abgelesen (Datei:Zeile unter `apps/api/src/mhvp`), Arbeitsstand 1.64.0. Keine Codeänderung. Die Eignung jedes Verfahrens ist fachlich nicht freigegeben.

## Verfahren je Rechenwert

| Rechenwert | Verfahren | Ort | Testbezug |
| --- | --- | --- | --- |
| Kostenverteilung Betriebskosten (Restcent) | ROUND_DOWN auf Cent, Restcent nach größtem Rest, Gleichstand nach stabilem Schlüssel | billing/calc.py:33 (`distribute`, 26 bis 39) | D08, `integration/test_m17_operating_costs.py::test_d08_d10_units` |
| CO2-Anteil Mieter | ROUND_HALF_UP auf Cent | billing/calc.py:92 (`co2_split`) | D10, ebenda |
| Heizkosten Zwischenwerte | ROUND_HALF_UP auf Cent | billing/heating_calc.py:84 | `unit/test_m17_heating_calc.py` (ohne Rundungszusicherung geprüft) |
| Heizkostenvergleich | ROUND_HALF_UP auf Cent | billing/heating_compare.py:33 | nicht ermittelt |
| Vorauszahlungsvorschlag | ROUND_HALF_UP auf Cent | billing/advance_rule.py:142 | nicht ermittelt |
| Monatsbetrag im Anschreiben | ROUND_HALF_UP auf Cent | billing/letters.py:65 | nicht ermittelt |
| KI-Plausibilität (Anzeige) | ROUND_HALF_UP auf Cent und auf 0,1 | billing/ai_check.py:66, 78 | nicht ermittelt |
| WEG Monatsrate Hausgeld | ROUND_HALF_UP auf Cent (Jahresbetrag durch 12) | hoa/calc.py:89 | nicht ermittelt |
| WEG Darlehen Tilgungsanteil und Zins | ROUND_HALF_UP auf Cent | hoa/calc.py:441, 447 | nicht ermittelt |
| Rücklagenaufteilung nach Planverhältnis | ROUND_HALF_EVEN auf Cent | hoa/reserve_split.py:60 | nicht ermittelt |
| Verzugszinsen Mahnung | ROUND_HALF_UP auf Cent (Tage durch 365) | accounting/dunning.py:255, 301 | nicht ermittelt |
| Steuerausweise (Modul tax) | ROUND_HALF_UP auf Cent | accounting/tax.py:40 | nicht ermittelt |
| Zeitanteile (Proration) | ROUND_HALF_UP auf Cent und auf 8 Stellen (`NUMERIC(20,8)`) | accounting/proration.py:41, 45 | nicht ermittelt |
| Rechnung USt-Prüfung, Kostenanteile, Skonto | ROUND_HALF_UP auf Cent | accounting/invoices.py:77, 332, 387; invoice_checks.py:82 | nicht ermittelt |
| Sachliche Rechnungsprüfung | ROUND_HALF_UP auf Cent | accounting/invoice_factual.py:63, 72, 88, 225, 309 | nicht ermittelt |
| Netto aus Brutto Kreditor | ROUND_HALF_UP auf Cent | accounting/creditor_routers.py:68 | nicht ermittelt |
| Sollstellungslauf | ROUND_HALF_UP auf Cent | accounting/receivables.py:680, 687, 689 | nicht ermittelt |
| XRechnung und ZUGFeRD | ROUND_HALF_UP auf Cent | accounting/xrechnung.py:144, 417, 687, 726; zugferd.py:112, 381 | nicht ermittelt |
| Mieterhöhung und Kappung (Vermietung) | ROUND_HALF_UP auf Cent | letting/routers.py:222, 233, 245, 838, 891; letting/basis_checks.py:98, 110 | nicht ermittelt |
| Lexoffice Übergabe | ROUND_HALF_UP auf Cent | integrations/lexoffice_ext/payloads.py:320 | nicht ermittelt |
| Kennzahlen (Quoten, Verfügbarkeit) | ROUND_HALF_UP auf 0,0001 beziehungsweise ROUND_FLOOR | banking/matching_metrics.py:79; banking/levels.py:234; platform/availability_probe.py:81, 89; platform/maintenance.py:446; portal/provider_info.py:80 | ohne Geldbezug |

## Befund: Rundung ohne ausdrückliches Verfahren

Rund 100 Aufrufe von `quantize` geben kein Verfahren an und runden damit nach dem Python Standardkontext (ROUND_HALF_EVEN). Mit Geldbezug unter anderem: hoa/plan_change.py:113, 115; hoa/calc.py:437, 855; ai/imports.py:946 (Netto aus Brutto, nur Vorschlag); platform/licensing.py:696; billing/owner_statement.py:130. Ob dort HALF_UP gewollt ist, ist offen (AI17-13 in docs/OPEN_QUESTIONS.md). Keine Änderung ohne Entscheidung und Test mit unabhängigem Sollwert.

## Uneinheitlichkeit

Die Rücklagenaufteilung rundet HALF_EVEN ohne Restcentausgleich, die Kostenverteilung ROUND_DOWN mit Restcentausgleich. Ob die Summe der Rücklagenanteile stets dem Ausgangsbetrag entspricht, ist mit einem Test zu prüfen (nicht Teil dieses Pakets).

## Zentrale Funktionen (Welle 21, AJ02)

`mhvp.core.money` bündelt die Rundung: `round_cents` (ROUND_HALF_UP auf Cent), `round_to` (ROUND_HALF_UP auf beliebige Stelle), `distribute_cents` (Verteilung nach Gewichten, Summe exakt, Restcent nach größtem Rest, negative Beträge spiegelbildlich), `parse_decimal_strict` (deutsche und einfache Zahlen, mehrdeutige Werte wie `12.500` werden abgelehnt, Excel Gleitkommawerte auf acht Nachkommastellen ROUND_HALF_UP) und `json_number` (Decimal als JSON Zahl nur verlustfrei, sonst Fehler).

| Rechenstelle | Rundung | Fundstelle | Test |
| --- | --- | --- | --- |
| Kappungsgrenze Mieterhöhung (beide Wege) | ROUND_HALF_UP auf Cent | letting/routers.py `_check`, letting/rentlaw.py | `unit/test_aj02_money.py` (11,50 EUR plus 15 Prozent gleich 13,23 EUR) |
| Brutto gegen Netto und Steuersatz (`check_amounts`) | ROUND_HALF_UP auf Cent, Toleranz 1 Cent (`CHECK_AMOUNTS_TOLERANCE`, Frage AJ02-01) | contracts/services.py | `unit/test_aj02_money.py` |
| Import Zahlenwerte | mehrdeutig abgelehnt, Excel float auf 8 Stellen | imports/fields.py `parse_decimal` | `unit/test_aj02_money.py`, `unit/test_m8_fields.py` |
| Abgleichbericht Beträge | ROUND_HALF_UP auf Cent | imports/reconciliation.py | `unit/test_m8_reconciliation_report.py` |
| lexoffice Menge | ROUND_HALF_UP auf 4 Stellen | integrations/lexoffice_ext/payloads.py `quantity` | `unit/test_aj02_money.py` |
| lexoffice und Makler JSON | Decimal verlustfrei als Zahl (`json_number`) | payloads.py `json_ready`, letting/broker_provider.py | `unit/test_aj02_money.py`, `unit/test_broker_provider.py` |

Quellenstatus: Produktschutz (kaufmännische Rundung, Anhang C enthält keine Rundungsnorm). Änderungsgrund: GAI-203 bis GAI-208, GAI-215.

## Änderung Welle 21 (AJ01, 02.10.2026)

Änderungsgrund: GAI-101, GAI-201, GAI-202, GAI-213, GAI-214, GAI-613, GAI-614. Quellenstatus unverändert Produktstandard (6.9.8), keine Rechtsregel behauptet. G3 und G4 bleiben geschlossen; Wirkung auf produktive Abrechnungen erst nach Freigabe der Geschäftsführung.

| Rechenwert | neues Verfahren | Ort | Test |
| --- | --- | --- | --- |
| Kostenverteilung bei negativer Summe | vorzeichensymmetrisch: Verteilung auf den Betrag, dann negiert; Restcent nach größtem Rest, Gleichstand nach stabilem Schlüssel; Summe exakt (bisher -100,00 / 3 ergab -99,97, jetzt -33,34 / -33,33 / -33,33) | billing/calc.py `distribute` | unit/test_aj01_rounding.py (Tabellenfälle, 2.000 Zufallsfälle Summentreue) |
| Negative Heizkostenanteile | Mandantenwert `negative_costs_mode` in `HeatingSettings`: `legacy_warn` (Standard, bisheriges Ergebnis mit Nullanteilen plus Warnhinweis in `notes`), `distribute` (vorzeichensymmetrische Verteilung) | billing/heating_calc.py `_component` | ebenda |
| WEG Monatsrate Hausgeld, Restcent | Regel `remainder_mode`: `report_only` (Standard, bisher, nur `rounding_difference`), `first_month`, `last_month` (Differenz auf diesen Monat, zwölf Raten ergeben den Jahresbetrag) | hoa/calc.py `monthly_rates`, `plan_results` | ebenda |
| Rücklagenaufteilung nach Planverhältnis | ROUND_HALF_UP statt HALF_EVEN, Restausgleich wie bisher | hoa/reserve_split.py | ebenda (Summentreue 2.000 Zufallsfälle) |
| Eigentümerabrechnung SEV Einzelwerte | ROUND_HALF_UP statt Standardkontext | billing/owner_statement.py `_d`, owner_statement_pdf.py | ebenda |
| übrige `quantize` in billing und hoa | ausdrücklich ROUND_HALF_UP (plan_change, calc Darlehen und Abweichung, assets, meetings, advance_rule, advance_routers, consumption_info, heating_import, letters) | | bestehende Tests |

Unverändert: Ratenaufteilung Sonderumlage (hoa/levies.py) rundet ROUND_DOWN je Rate, Rest auf die letzte Rate, Summe exakt. Die beiden Mandantenwerte sind bisher nur Parameter der Rechenfunktionen; eine dauerhafte Speicherung je Mandant braucht eine Schemaänderung (AJ01-01, AJ01-02).
