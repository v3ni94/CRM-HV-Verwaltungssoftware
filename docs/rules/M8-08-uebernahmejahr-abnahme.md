# M8-08 Übernahmejahr und Abnahmeprotokoll der Migration

* ID: M8-08 (Jahresansicht, D11) und M8-09 (Abnahmeprotokoll).
* Geltungsbereich: Buchungskreis mit Migrationsstichtag (Jahresansicht) und Objekt (Abnahme).
* Quellenstatus: Fachliche Umsetzung aus MASTER-PROMPT 6.9.10 und 13.1, keine Rechtsgrundlage
  aus Anhang C. Die Jahresansicht ist eine Auswertung, keine Abrechnung und löst keine Buchung
  aus; G1 bis G5 bleiben unberührt.
* Regel Jahresansicht: Ausgaben eines Kalenderjahres = Aufwandskonten im Migrationsjournal
  vor dem Stichtag plus Aufwandskonten im aktiven Journal ab dem Stichtag. Die Eröffnungsbuchung
  (Quelle migration) ist Bestandsbewegung und keine Ausgabe. Migrationsbuchungen ab dem
  Stichtag zählen nicht, damit nichts doppelt gezählt wird. Nur gebuchte Belege zählen.
* Regel Abnahme: Das Protokoll enthält Prüfumfang, verantwortliche Personen, nicht migrierbare
  Daten, Rückfallplan, Archiv- und Auskunftskonzept und optional den Abgleichbericht. Die
  Unterzeichnung erfolgt durch eine andere Person als die Bearbeitung (Vier-Augen) und nur bei
  ausgefülltem Prüfumfang, Personen, Rückfallplan und Archivkonzept. Ein unterzeichnetes
  Protokoll wird nicht geändert, eine Korrektur ist ein neues Protokoll.
* Abnahmefall: D11 (400,00 EUR vor, 600,00 EUR nach dem Stichtag 01.07.2026 ergeben
  1.000,00 EUR), Test `test_d11_year_expenses_prior_and_later_period`; Abnahmeprotokoll
  `test_acceptance_record_lifecycle`.
* Änderungsgrund: Lückenliste 30.09.2026 (M8-08, M8-09, M10-07). Die Einbindung der
  Jahresansicht in die Abrechnungen (M14) ist noch offen.
