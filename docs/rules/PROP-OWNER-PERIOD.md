# PROP-OWNER-PERIOD: Zeiträume und Anteile der Objekteigentümer (Mietverwaltung)

- ID: PROP-OWNER-PERIOD (Befund GAJ-603, Paket AM03, Welle 23)
- Geltungsbereich: `POST /properties/{id}/owners` und Import von Eigentumsverträgen für Mietobjekte (`imports/services.py`, Vertragsimport mit Art ownership).
- Regel: Dieselbe Partei darf für ein Objekt keine überlappenden Eigentumszeiträume haben. Die bekannten Anteile (`share_percent`) aller an einem Tag aktiven Eigentümer dürfen zusammen 100 Prozent nicht übersteigen. Eigentümer ohne Anteil zählen nicht (Miteigentum mit unbekanntem Anteil). Verstoß über die API: 422 mit Angabe des Tages und der Summe.
- Import: Offene Eigentümer anderer Parteien mit Beginn vor dem Stichtag werden zum Vortag beendet (Ereignis `property.owner_updated`, Vermerk im Importbericht). Ein Eigentümer mit späterem Beginn oder eine Anteilsverletzung ergibt eine Konfliktzeile im Importbericht, nichts wird geändert. Gleicher Beginn gilt als Miteigentum.
- Quellenstatus (Anhang C): Produktschutz (Datenqualität), keine Rechtsgrundlage behauptet.
- Abnahmefall: kein eigener Anhang-D-Fall; Test `tests/integration/test_am03_owner_periods.py`.
- Änderungsgrund: Stichtagsauswertungen der Eigentümer lieferten bei Überlappungen mehrdeutige Ergebnisse (GAJ-603). Kein Exclusion Constraint (keine Migration in dieser Welle).

## Ergänzung Welle 24 (Paket AN09, Rest AM03)

- Geltungsbereich erweitert: Die Periodenprüfung (`owner_period_problems`) gilt in allen Anlagepfaden eines Objekteigentümers. Zuordnung mit Vermieter (`imports/zuordnung.py`, `_landlord`): Verstoß ergibt 422, nichts wird angelegt. Vollimport Verträge (`imports/vollimport_vertraege.py`, Eigentum in Mietverwaltung): Verstoß ergibt eine Konfliktzeile im Bericht. KI-Objektimport (`ai/imports.py`, `apply_property`): der Eigentümer wird nicht angelegt, der Grund steht in den Hinweisen.
- Importrückgängig: Beendet der Vertragsimport einen bisherigen Eigentümer, merkt sich der Importlauf den alten und den neuen Wert von `valid_to` (Eintrag `property_owner_end:<alt>:<neu>`). Die Rücknahme entfernt zuerst den neuen Eigentümer und stellt dann das alte Ende wieder her. Wurde das Ende nach dem Import geändert oder ergäbe die Wiederherstellung eine Überschneidung derselben Partei, bleibt der Zeitraum unverändert und der Grund steht beim Eintrag.
- Weiterhin kein Exclusion Constraint in der Datenbank (nur Code, keine Migration).
- Tests: `tests/unit/test_an09_owner_period_paths.py`, `tests/integration/test_an09_owner_period_import_undo.py`.
