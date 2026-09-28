# C2-01 Wartungszyklus: Erledigung rückt die Fälligkeit um das eingetragene Intervall vor

| Field | Content |
| --- | --- |
| ID | `C2-01` |
| Title | Erledigung einer Wartung oder Prüfpflicht mit Intervall setzt die nächste Fälligkeit auf Erledigungsdatum plus Intervall in Monaten (Tag auf das Monatsende begrenzt); ohne Intervall wird der Eintrag geschlossen |
| Scope | `mhvp.properties` (`POST /maintenance/{id}/done`, `PATCH /maintenance/{id}`, `services.add_months`, `services.done_at_for`), Objektseite Abschnitt Wartungen und Prüfpflichten; alle Mandanten, kein Geldbezug |
| Source status | Fachliche Umsetzung (Masterprompt 6.2 `maintenance_item`, Handbuch Stammdaten). Kein Rechtsbezug: welche Prüfpflichten mit welchem Zyklus bestehen (zum Beispiel Aufzug, Trinkwasser, Blitzschutz, Rauchwarnmelder), ist nicht hinterlegt; das Intervall ist eine Betreibereingabe ohne Vorgabe, gekennzeichnet als zu verifizieren (Offene Entscheidung STAMM-01) |
| Acceptance case | `tests/integration/test_property_masterdata_c2.py::test_maintenance_patch_and_done_cycle` (31.01.2026 plus 12 Monate = 31.01.2027, 31.01.2026 plus 1 Monat = 28.02.2026, ohne Intervall Status erledigt und 409 bei zweiter Erledigung), `::test_add_months_clamps_to_month_end` |
| Implementation | `done_at` wird aus dem Erledigungsdatum als 12:00 Uhr Europe/Berlin in UTC gespeichert, `last_done_on` gibt den Berliner Kalendertag zurück. Mit Intervall bleibt der Status `open`, `due_date` = Erledigungsdatum plus Intervall; ohne Intervall Status `done`, erneute Erledigung 409 `MHVP-PROP-0005`. Ereignis `maintenance.done` mit vorheriger und nächster Fälligkeit. Die Sammelaktion Erledigt der Arbeitsfläche (`workspace.bulk`) bleibt unverändert und schließt Einträge ohne Vorrücken |
| Change reason | Lückenliste Handbuch 28.09.2026, zweite Stammdatenzeile: Wartungen nur über Import oder Schnittstelle pflegbar |

## Produktschutz

Die Fälligkeit ist eine Wiedervorlage, keine Frist mit Rechtsfolge. Fristen aus Gesetz,
Vertrag oder Bescheid werden nicht abgeleitet; die Fristenliste zeigt die Fälligkeit als
Orientierung. Ein Intervall ersetzt keine Prüfung, ob und in welchem Zyklus eine Pflicht
besteht (Verantwortung Betreiber, gegebenenfalls mit Fachfirma oder Rechtsberatung).
