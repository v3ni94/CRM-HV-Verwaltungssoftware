# M8-01 Weitere Importberichte der Migration (Kaution, Umlageschlüssel, Zähler, Energieausweis, Dienstleister, Portalstatus)

* ID: M8-01 (Paket T10, Welle 5).
* Geltungsbereich: Mandant mit Immoware24-Übernahme, je Objekt.
* Quellenstatus: Fachliche Umsetzung aus MASTER-PROMPT 13.1, keine Rechtsgrundlage aus Anhang C.
  Die Spaltennamen der Immoware24-Exporte sind nicht belegt (docs/integrations enthält keine
  Beispielspalten, M8-01 bleibt für echte Exporte offen): jede Datei wird je Berichtsart über eine
  gespeicherte Spaltenzuordnung den Plattformfeldern zugeordnet.
* Gemeinsame Regeln: wie M8-06 (Testlauf mit Rollback, Übernahme als `import_run`, idempotent über
  fachliche Schlüssel, nichts wird überschrieben: gleich ist unverändert, abweichend ist Konflikt,
  Rücknahme über die Protokollierung des Laufs, bearbeitete Daten bleiben stehen).
* Kaution (`deposit`): Pflicht Objektnummer, Einheitennummer, Kontakt-ID Mieter, Art, Betrag
  (soll), Gültig ab. Schlüssel: Mietverhältnis (Mieter, Einheit, Beginn bis Gültig ab) und
  Gültig ab. Legt die Vereinbarung mit Status `open` an, keine Bewegung, keine Buchung, kein
  Kautionskonto (Zuordnung folgt manuell, Hinweis im Bericht). Rücknahme nur ohne Bewegungen,
  Dokumente, Kontozuordnung und Statuswechsel. Betragssumme im Bericht.
* Umlageschlüssel (`allocation_key`): Pflicht Objektnummer und Kürzel. Neuer Schlüssel braucht
  Bezeichnung, Maßeinheit und Art. Mit Einheit, Wert und Gültig ab entsteht der zeitlich gültige
  Einheitenwert (ein früher offener Wert wird am Vortag geschlossen). Abweichender Wert im selben
  Zeitraum ist Konflikt. Rücknahme entfernt zuerst den Wert (öffnet den früheren wieder), danach
  den Schlüssel, sofern keine Werte mehr hängen.
* Zähler (`meter`): Katalogcode der Zählerart wird geprüft, Schlüssel Objekt, Art und Nummer,
  optional ein Anfangsstand. Rücknahme nur ohne weitere Zählerstände und Zählerwechsel.
* Energieausweis (`energy_certificate`): Werte laut Ausweis am Gebäude (A63), nichts abgeleitet.
  Ein leerer Ausweis wird gefüllt, abweichende Angaben sind Konflikt. Bei mehreren Gebäuden ist
  die Gebäudebezeichnung nötig. Rücknahme leert den Ausweis nur, wenn er seit dem Import
  unverändert ist.
* Dienstleister (`service_provider`): Katalogcode der Vertragsart wird geprüft, Schlüssel Objekt,
  Kontakt, Art und Gültig ab. Das Kreditorenkonto wird nicht angelegt (Kontenstamm bleibt beim
  Buchungskreis des Objekts), die Freistellungsbescheinigung wird nicht übernommen.
* Portalnutzer (`portal_user`): nur Statusabgleich mit dem Portalkonto des Kontakts. Es entsteht
  kein Konto, es geht keine Einladung hinaus, nichts wird überschrieben. Ohne Konto: `staged_only`
  mit Hinweis auf die Portalverwaltung.
* Abnahmefall: `tests/integration/test_w5_t10_import_reports.py` (fachliche Soll-Werte im Test).
* Änderungsgrund: Lückenliste M8-01 (Berichtsarten fehlten); `ReportType` ist ein Datenbank-Enum,
  Migration 0297 ergänzt die Werte.
