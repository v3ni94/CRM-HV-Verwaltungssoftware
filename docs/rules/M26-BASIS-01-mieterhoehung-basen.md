# M26-BASIS-01 Rechenprüfung der Mieterhöhungsbasen Index, Modernisierung und Staffel

| Field | Content |
| --- | --- |
| ID | `M26-BASIS-01` |
| Title | Rechenprüfung der Mieterhöhungsbasen Index, Modernisierung und Staffel |
| Scope | Domäne `letting`, Tabelle `rent_increase_case` (Spalte `basis_data`), Mandanten mit Recht `contracts:create` |
| Source status | Fachliche Umsetzung. Das Quellenregister (Anhang C) enthält keine Mietrechtsnormen; die Plattform enthält keine gesetzlichen Prozentsätze oder Grenzen für diese Basen. Geprüft wird nur, ob die erfasste Zielmiete rechnerisch zu den erfassten Werten passt. Keine Aussage zur Zulässigkeit |
| Acceptance case | keine in Anhang D; Test `apps/api/tests/integration/test_p20_letting_dispatch_w2.py::test_basis_checks_vacancy_prospects_expose` |
| Implementation | `mhvp.letting.basis_checks` (`validate`, `check`), `mhvp.letting.routers._check`, Migration 0269 |
| Change reason | Lückenliste 30.09.2026, Befund M26-02 |

## Regeln

- Index: Höchstmiete = aktuelle Miete x aktueller Index / Ausgangsindex (Rundung auf Cent). Beispiel 600,00 x 105 / 100 = 630,00 EUR.
- Modernisierung: Monatsbetrag = (Kosten minus Abzug Instandhaltung) x erfasster Umlagesatz in Prozent / 100 / 12; Höchstmiete = aktuelle Miete plus Monatsbetrag. Beispiel (12.000,00 x 8 / 100) / 12 = 80,00 EUR, Höchstmiete 680,00 EUR. Der Umlagesatz ist eine Eingabe mit Quelle, kein hinterlegter Gesetzeswert.
- Staffel: Es muss eine erfasste Staffel zum Wirksamkeitsdatum existieren und die Zielmiete muss ihrem Betrag entsprechen.
- Alle drei Basen verlangen ein Quelldokument (Vereinbarung, Kostennachweis) als `source_document_id`. Fehlt es, bleibt ein Hinweis offen und die Freigabe ist gesperrt.
- Hinweise sperren die Freigabe wie bei der Vergleichsmiete. Versand bleibt hinter G3 und der dokumentierten Rechtsprüfung.
