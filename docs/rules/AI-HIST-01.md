# AI-HIST-01 Migrationsjournal als Trainingsbasis für Buchungsvorschläge

* ID: AI-HIST-01
* Geltungsbereich: Aufgabe `propose_posting` (hinter Mandantenschalter `ai_posting_enabled`, Gate G1 unberührt).
* Regel: Vergleichbare Buchungen aus `migrated_journal_entry` und `migrated_journal_line` (Schlagwortabgleich auf dem Buchungstext, abgestimmte Buchungen zuerst, neueste zuerst, höchstens drei) werden als nur lesende Beispiele mit Kontonummern, Soll und Haben in den Prompt aufgenommen. Texte werden maskiert. Es wird nichts gebucht oder verändert, der Vorschlag bleibt freigabepflichtig.
* Quellenstatus Anhang C: Fachliche Umsetzung (Masterprompt M8 Zeile 18, 13.1).
* Abnahmefall: `tests/unit/test_ai_journal_history.py` (Schlagwortauswahl).
* Änderungsgrund: Befund M8-05 (Lückenliste 30.09.2026). Bankzuordnungen der Historie sind noch nicht angebunden.
