# PROP-OWNER-PERIOD: Zeiträume und Anteile der Objekteigentümer (Mietverwaltung)

- ID: PROP-OWNER-PERIOD (Befund GAJ-603, Paket AM03, Welle 23)
- Geltungsbereich: `POST /properties/{id}/owners` und Import von Eigentumsverträgen für Mietobjekte (`imports/services.py`, Vertragsimport mit Art ownership).
- Regel: Dieselbe Partei darf für ein Objekt keine überlappenden Eigentumszeiträume haben. Die bekannten Anteile (`share_percent`) aller an einem Tag aktiven Eigentümer dürfen zusammen 100 Prozent nicht übersteigen. Eigentümer ohne Anteil zählen nicht (Miteigentum mit unbekanntem Anteil). Verstoß über die API: 422 mit Angabe des Tages und der Summe.
- Import: Offene Eigentümer anderer Parteien mit Beginn vor dem Stichtag werden zum Vortag beendet (Ereignis `property.owner_updated`, Vermerk im Importbericht). Ein Eigentümer mit späterem Beginn oder eine Anteilsverletzung ergibt eine Konfliktzeile im Importbericht, nichts wird geändert. Gleicher Beginn gilt als Miteigentum.
- Quellenstatus (Anhang C): Produktschutz (Datenqualität), keine Rechtsgrundlage behauptet.
- Abnahmefall: kein eigener Anhang-D-Fall; Test `tests/integration/test_am03_owner_periods.py`.
- Änderungsgrund: Stichtagsauswertungen der Eigentümer lieferten bei Überlappungen mehrdeutige Ergebnisse (GAJ-603). Kein Exclusion Constraint (keine Migration in dieser Welle).
