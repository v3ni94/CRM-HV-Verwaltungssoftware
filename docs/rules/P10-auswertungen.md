# P10 Auswertungen mit Kopfangaben, Monatsmatrix, Soll/Ist, Bankkontoabrechnung, Excel, Verfahrensdokumentation, Prüfexport

| Field | Content |
| --- | --- |
| ID | `P10` (Teilregeln M18-REP-01 bis M18-REP-06) |
| Title | Einheitliche Kopfangaben je Auswertung, Monatsmatrix, Soll/Ist der Forderungen, Bankkontoabrechnung mit Abgleich, Excel-Ausgabe, Verfahrensdokumentation als Entwurf aus dem Betrieb, vollständige Vertragshistorie und Freigaben von Mahnung und Zahlung im Prüfexport |
| Scope | `mhvp.accounting.report_views`, `report_xlsx`, `procedure_doc`, `report_routers` (`/accounting/ledgers/{id}/reports/...`, `.../procedure-documentation`), `audit_export` (Tabellen `vertraege`, `freigaben`), CRM Buchhaltung, Auswertungen. Alle Mandanten, je Rechtsträger |
| Source status | Fachliche Umsetzung zu Abschnitt 7.7 (Auswertungen, Prüfexport, Verfahrensdokumentation). Keine Rechtsnorm wird ausgelegt. Das GoBD-Datenträgerformat und die Freigabe der Verfahrensdokumentation bleiben offen (P05, M18-01) |
| Acceptance case | keine in Anhang D; Tests `apps/api/tests/integration/test_p10_reports.py`, `apps/api/tests/unit/test_p10_reports.py`, Vitest `ReportsExplorer.test.tsx` |
| Implementation | siehe Regeln unten |
| Change reason | Lückenliste 30.09.2026, Befunde M18-01 bis M18-05, M18-07 bis M18-09 |

## Regeln

- M18-REP-01 Kopfangaben: Jede neue Auswertung liefert `header` mit Rechtsträger, Buchungskreis, Zeitraum, Stichtag, Datenstand (Erzeugungszeitpunkt UTC), angewandten Filtern und Status `draft` samt Hinweis. Die Auswertungen sind Entwürfe zur internen Verwendung, keine Bescheinigung.
- M18-REP-02 Monatsmatrix: Konten der Kategorien Ertrag und Aufwand (wählbar) je Monat aus gebuchten Sätzen. Ertragskonten Haben minus Soll, alle anderen Soll minus Haben. Höchstens 60 Monate.
- M18-REP-03 Soll/Ist: Soll sind offene Posten der Art Forderung mit Fälligkeit (ersatzweise Buchungstag) im Zeitraum, ohne abgeschriebene. Ist auf Soll sind die Ausgleiche dieser Posten bis Zeitraumende, Stornos saldieren. Zusätzlich Eingänge im Zeitraum. Keine Verrechnung über Debitoren (B01).
- M18-REP-04 Bankkontoabrechnung: Anfangsbestand, Bewegungen und Endbestand eines Bank- oder Kassenkontos des Buchungskreises. Abgleich mit dem Schlusssaldo des jüngsten importierten Kontoauszugs, dessen Schlussdatum im Zeitraum liegt. Eine Differenz wird angezeigt, nie gebucht (B09).
- M18-REP-05 Excel: Journal und Auswertungen als XLSX mit Kopfblock. Textzellen werden wie im CSV gegen Formelinjektion entschärft, Beträge sind Zahlen. Jeder Abruf wird als Exportlauf (`xlsx_<name>`) mit SHA-256 protokolliert.
- M18-REP-06 Prüfexport: Tabelle `vertraege` mit allen Verträgen und Versionen der Einheiten des Objekts, des Rechtsträgers und der gebuchten Verträge. Stammdatenhistorie wird für alle diese Verträge aus dem Änderungsprotokoll gelesen. Tabelle `freigaben` enthält zusätzlich Freigaben von Mahnläufen und Zahlungsaufträgen des Buchungskreises im Zeitraum.
- M18-07 Verfahrensdokumentation: Der Endpunkt erzeugt ein Markdown aus belegbaren Betriebsdaten, alles Übrige bleibt `[zu ergänzen]`. Der Text ist Entwurf und keine Aussage zur GoBD-Konformität.
