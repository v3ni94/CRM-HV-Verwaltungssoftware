# M17-10 Ergebnis je Vertrag, Zugang, Differenzbericht, Belegeinsicht und Ergebnisbuchung

| Feld | Inhalt |
| --- | --- |
| ID | `M17-10-ergebnis-zugang-einsicht` |
| Geltungsbereich | `mhvp.billing.results`, `mhvp.billing.result_routers`, `mhvp.billing.consumption_info_routers`; Betriebskostenabrechnungen Miete und SEV (`statement`); alle Mandanten; Ergebnisbuchung und Ausgabe hinter G3 |
| Quellenstatus | Fachliche Umsetzung (6.5 `operating_cost_statement`, `statement_line`, `statement_result`; 6.9.3; 7.6 A01, A04, A05, A07; 7.9 PÜ11; Phasengrenze 10). Rechtsgrundlage R06 (§ 556 BGB) nur für die angezeigte Orientierung der Einwendungsfrist, keine automatische Rechtsfolge |
| Abnahmefall | D23 (Zugang statt Erstellung), D26 (Ersatzprozess Verbrauchsinformation); Tests `tests/integration/test_m17_results.py`, `tests/integration/test_d26_consumption_info_substitute.py` |
| Änderungsgrund | Lückenliste 30.09.2026, Befunde M17-01 bis M17-08, SD-01 |

## Regeln

- Entwurf: Kopfdaten und Kostenpositionen sind nur im Status `draft` änderbar oder löschbar;
  danach nur über eine neue Version mit Bezug (6.9.3).
- Sonderzeitraum (A05): ein Zeitraum, der keine zwölf Monate umfasst, muss als unterjährig
  gekennzeichnet sein und einen Zweck tragen; ohne Zweck wird nicht angelegt (Datenbankprüfung
  `ck_statement_interim_purpose`).
- Kostenaufstellung je Vertrag (M17-02): nur aus dem Snapshot (Bezeichnung, Gesamtbetrag,
  Schlüssel, Grundlage, Anteil); das Anschreiben enthält die Aufstellung.
- Zugang je Mieter (M17-03): Versandart, Zugangsdatum und Nachweis sind Pflicht; der Zugang
  liegt nie vor der Berechnung. Erfassung ab interner Freigabe bis Status fällig. Die
  Einwendungsfrist wird als Orientierung angezeigt (zwölf Monate nach Zugang), sie ist je Fall
  zu prüfen.
- Differenzbericht (M17-05): Kosten, gezahlte Vorauszahlungen und Saldo je Vertrag sowie
  Positionssummen alt und neu mit Differenz.
- Belegeinsicht (M17-06): Anfrage mit Eingang und Weg, Bereitstellung (elektronisch, Kopien,
  Termin) mit Datum, Schwärzungsvermerk, Einwendung mit Eingang und Inhalt, Abschluss erst
  nach Bereitstellung. Die Freigabe einzelner Belege an das Mieterportal ist nicht umgesetzt.
- Ergebnisbuchung (M17-01): nur mit G3 und im Status `due`; je Vertrag mit Saldo ungleich
  null ein Buchungsentwurf (Nachzahlung: Debitor Soll, Ergebniskonto Haben; Guthaben
  umgekehrt), Gegenkonto aus der Zahlungsart `statement_result`. Nachforderungen mit
  Fristsperre ohne Ausnahme werden nicht erzeugt. `posted` erst, wenn alle Entwürfe über die
  Buchhaltung gebucht sind; `locked` setzt den Sperrzeitpunkt der Abrechnung.
- Verbrauchsinformation ohne Portal (D26): druckbare Fassung, Liste der noch nicht
  zugestellten Einheiten, Zustellung mit Weg (Post, E-Mail, Übergabe), Datum und Nachweis.
