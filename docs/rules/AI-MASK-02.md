# AI-MASK-02 Adressmaskierung und Namensregel bei KI-Aufrufen

* ID: AI-MASK-02
* Geltungsbereich: Eingaben an externe KI-Anbieter für die Aufgaben in `gateway.MASKED_TASKS` (Fragen, Zusammenfassung, Abrechnungsprüfung, Klassifikation, Antwortentwurf, Gesprächsnotiz).
* Regel: Vor dem Anbieteraufruf werden IBAN, E-Mail, Telefon (wie bisher) und zusätzlich Straße mit Hausnummer sowie Postleitzahl mit Ort durch Platzhalter ersetzt (`mhvp.ai.masking`). Namen bleiben erhalten, weil Textentwürfe die Anrede brauchen und Extraktionsaufgaben den Namen selbst suchen. Die Maskierung ist musterbasiert und kein Anonymitätsnachweis; sie ersetzt weder AVV noch Anbieterfreigabe.
* Quellenstatus Anhang C: Produktschutz (strengerer interner Standard, keine gesetzliche Pflicht).
* Abnahmefall: `tests/unit/test_ai_address_masking.py`.
* Änderungsgrund: Befund M7-10 (Lückenliste 30.09.2026). Die Pseudonymisierung von Namen ist Teil der offenen Entscheidung M34-05 und nicht umgesetzt.
