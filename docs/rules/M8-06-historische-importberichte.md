# M8-06 Weitere Importberichte der Migration (SEPA, Kontenplan, Bankhistorie, Dokumente, Tickets, offene Posten)

* ID: M8-02, M8-03, M8-04, M8-06, M8-07 (Paket Q08).
* Geltungsbereich: Mandant mit Immoware24-Übernahme, je Objekt und Buchungskreis.
* Quellenstatus: Fachliche Umsetzung aus MASTER-PROMPT 13.1 und 6.9.10, keine Rechtsgrundlage
  aus Anhang C. Die Spaltennamen der Immoware24-Exporte sind nicht spezifiziert (M8-01 offen):
  jede Datei wird je Berichtsart über eine gespeicherte Spaltenzuordnung (Vorlage, versioniert)
  den Plattformfeldern zugeordnet. Pflichtfelder sind benannt, die Prüfung nennt fehlende.
* Gemeinsame Regeln: Testlauf mit Prüfbericht im Savepoint (Rollback), Übernahme als
  `import_run`, idempotent über fachliche Schlüssel, vorhandene Datensätze werden nie
  überschrieben (gleich: unverändert, abweichend: Konflikt). Nichts bucht, zieht ein oder mahnt;
  G1 bis G5 bleiben geschlossen.
* SEPA-Übersicht (M8-02): legt den Zahlungsplan (Intervall, Fälligkeitstag, Regel) am Vertrag an;
  ein Mandat (`sepa_mandate`) nur mit Mandatsreferenz, Gläubiger-ID, Unterschriftsdatum, IBAN
  (beim Kontakt hinterlegt) und vorhandenem Nachweisdokument, sonst Hinweis im Bericht. Der Einzug
  bleibt bis G2 gesperrt. Fehlt die Sequenz, gilt `recurring` (Annahme A-Q08-01).
* Kontenplan (M8-03): Konten je Buchungskreis des Objekts (bei mehreren Buchungskreisen mit
  Rechtsträgerart), sechsstellige Nummer (kürzere werden links aufgefüllt, A-047), neue Konten
  mit Prüfstatus `entwurf`; steuerliche Einordnung bleibt bei einer Person.
* Bankhistorie (M8-04): `bank_transaction` mit Status `ignored` (Historie, kein Abgleich, keine
  Buchung), nur bis zum Migrationsstichtag des Buchungskreises; Zuordnung zum
  Migrationsjournal über die Buchungsnummer (`migrated_bank_link`), ein Wiederholungslauf
  vervollständigt offene Zuordnungen. Gleiche Umsätze ohne Bankreferenz bleiben zwei Umsätze.
* Dokumente (M8-06): verknüpft bereits übernommene DMS-Dokumente (Quell-ID oder Dateiname) mit
  Objekt, Einheit und Vertrag; kein Dokument wird angelegt, verschoben oder gelöscht.
* Tickets (M8-06): historische Tickets nur lesend (`migrated_ticket`), kein Live-Ticket, keine
  Fristen, keine Benachrichtigung.
* Offene Posten (M8-07): Einzelposten je Art (Forderung, Guthaben, Kaution, Rücklage, Darlehen,
  Sonderumlage) mit Ursprungsfälligkeit, Teilzahlung und Beschlussbezug in `migrated_open_item`.
  Regeln: Bezahlt höchstens Ursprungsbetrag, offen = Ursprungsbetrag minus bezahlt, genannter
  offener Betrag muss stimmen, Forderung und Sonderumlage brauchen die Ursprungsfälligkeit.
  Ein Abgleich mit den Saldensummen der Eröffnungsbilanz erfolgt über die Summen je Art.
* Abnahmefälle: `apps/api/tests/integration/test_q08_import_history.py` (Zahlen im Test
  kommentiert), D11 bleibt unberührt.
* Änderungsgrund: Lückenliste 30.09.2026 M8-02, M8-03, M8-04, M8-06, M8-07.

## Ergänzung Welle 4 (R04, 01.10.2026)

* Geltungsbereich: Prüfbericht Einzelposten gegen Eröffnungsbilanz (M8-07), Kandidatenliste Journalzuordnung (M8-04), Rücknahme der Berichtsarten.
* Quellenstatus Anhang C: Produktschutz, keine Rechtsnorm. Vorzeichenregel als Annahme A-Q08-01, offen in Q08-03.
* Regel: Der Prüfbericht vergleicht je Gruppe (Debitoren, Kreditoren, Rücklagen) Offene-Posten-Summe und Salden der Eröffnungsbilanz und korrigiert nie. Die Kandidatenliste nennt Journalbuchungen im Buchungskreis der Bankverbindung mit gleichem Betrag und Datum innerhalb der Toleranz (Standard 3 Tage) und ordnet nie automatisch zu. Die Rücknahme entfernt importierte Konten (nur Prüfstatus entwurf und unverwendet), historische Bankumsätze (nur Status ignoriert), Tickets und Einzelposten; andere bleiben mit Grund.
* Abnahmefall: tests/integration/test_q08_import_history.py (test_r04_balance_check_candidates_undo).
* Änderungsgrund: Lückenliste 30.09.2026, M8-04 und M8-07.
