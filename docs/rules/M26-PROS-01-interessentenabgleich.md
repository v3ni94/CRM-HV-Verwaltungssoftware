# M26-PROS-01 Abgleich von Interessenten mit Anzeigen über ein Suchprofil

| Field | Content |
| --- | --- |
| ID | `M26-PROS-01` |
| Title | Abgleich von Interessenten mit Anzeigen über ein Suchprofil |
| Scope | Domäne `letting`, Tabelle `prospect` (Spalten `listing_id`, `search_profile`), Rechte `contracts:read`, `contracts:update` |
| Source status | Fachliche Umsetzung. Personenbezogene Daten nur mit Zweck und Löschdatum wie bisher; das Suchprofil enthält nur Wunschkriterien |
| Acceptance case | keine in Anhang D; Test `test_p20_letting_dispatch_w2.py::test_basis_checks_vacancy_prospects_expose` |
| Implementation | `mhvp.letting.routers` (`GET /letting/listings/{id}/prospect-matches`, `ProspectProfileIn`), Migration 0269 |
| Change reason | Lückenliste 30.09.2026, Befund M26-06 |

## Regeln

- Kriterien: höchste Kaltmiete, höchste Warmmiete, Mindestzimmer, Mindestfläche, Bezug bis, Art der Anzeige, geforderte Ausstattungsmerkmale.
- Je Kriterium wird erfüllt, nicht erfüllt oder nicht prüfbar (Wert fehlt an der Anzeige) ausgewiesen. Die Reihung folgt der Zahl erfüllter Kriterien, dann der geringsten Zahl nicht erfüllter, dann dem frühesten Eingang.
- Kandidaten sind Interessenten der Einheit, mit der Anzeige verknüpfte Interessenten und Interessenten anderer Einheiten mit Suchprofil. Mehrere Einheiten je Person entstehen über mehrere Interessentenzeilen.
- Der Abgleich ist ein Vorschlag an die Sachbearbeitung, keine Zusage und keine Absage.
