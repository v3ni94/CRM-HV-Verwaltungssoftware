# M26-VAC-01 Leerstandsmaßnahmen mit Sollmiete, entgangener Miete und Kosten

| Field | Content |
| --- | --- |
| ID | `M26-VAC-01` |
| Title | Leerstandsmaßnahmen mit Sollmiete, entgangener Miete und Kosten |
| Scope | Domäne `letting`, Tabelle `vacancy_case`, nur Verwaltungsart RENTAL, Rechte `contracts:read`, `contracts:update`, `contracts:create` |
| Source status | Fachliche Umsetzung, keine Rechtsgrundlage. Rechenwerte sind Orientierung, keine Forderung |
| Acceptance case | keine in Anhang D; Test `test_p20_letting_dispatch_w2.py::test_basis_checks_vacancy_prospects_expose` |
| Implementation | `mhvp.letting.routers` (`GET /letting/vacancies`, `PUT /letting/vacancies/{unit_id}`, `POST .../listing`), `VacancyTable`, `VacancyMeasure`, Migration 0269 |
| Change reason | Lückenliste 30.09.2026, Befund M26-04 |

## Regeln

- Der Leerstand bleibt aus den Mietverträgen abgeleitet. Die Maßnahme hält Status (offen, inseriert, Besichtigung, vermietet, Renovierung, gesperrt), verantwortliche Person, Wiedervorlage, Sollmiete, Kosten je Monat und Notiz.
- Entgangene Miete = Sollmiete je Monat x 12 / 365 x Leerstandstage. Leerstandskosten = Kosten je Monat x 12 / 365 x Leerstandstage. Beispiel 600,00 x 12 / 365 x 85 = 1.676,71 EUR. Ohne Sollmiete (Maßnahme oder Mietanzeige) bleibt der Wert leer.
- SEV-Einheiten in WEG und fiktive Einheiten erscheinen nicht und können keine Maßnahme erhalten.
- Direktaktion Anzeige anlegen erzeugt einen Entwurf der Mietanzeige; nur eine offene Maßnahme wechselt dabei auf inseriert. Veröffentlichen bleibt ein eigener Schritt.
