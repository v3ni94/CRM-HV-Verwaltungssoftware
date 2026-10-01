# UI-R15 Oberflächenkonsistenz

- ID: UI-R15
- Geltungsbereich: CRM und Portal, alle Seiten der Wellen 2 und 3 (Produktschutz, keine Fachregel).
- Quellenstatus Anhang C: keine Rechtsgrundlage, interner Standard.
- Inhalt: Neue Seiten sind über Menü, Einstellungsübersicht oder Elternseite erreichbar und im Hilfeindex geführt. Ladefehler sind sichtbar. Formulare haben ein aria-label. Texte stehen in de und en. Tabellen haben einen Scroll-Wrapper.
- Abnahmefall: Vitest `surface-consistency.test.ts`, `chat-suggestions.test.ts`, `table-wrapper.test.ts`; `scripts/check_i18n.py`.
- Änderungsgrund: Konsistenzprüfung 01.10.2026, Befunde: Aufträge ohne Menüeintrag, Benachrichtigungen ohne Kachel, drei Seiten ohne Fehlerzustand, ein hart codierter Spaltenkopf, Formulare ohne aria-label.
