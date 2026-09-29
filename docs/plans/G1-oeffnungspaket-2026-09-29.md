# G1 Öffnungspaket (Betreiberauftrag 29.09.2026, M12-09)

Ziel: Betreiberunterlagen und ein Systemstand, mit denen der Betreiber die Öffnungsliste
M12-09 abarbeiten und den Antrag auf die Freigabestufe G1 stellen kann. Nichts im Paket
öffnet die Stufe; die Entscheidung bleibt bei einer zweiten Person auf der Plattformseite
(ADR 0003).

## Umfang

| Nr. | Teil | Dateien |
| --- | --- | --- |
| 1 | Kontenrahmen-Prüfung nach Anhang A.1 (aus `defaults.py`), offene Fragen, Freigabe in der Software | `docs/acceptance/kontenrahmen-pruefung.md` |
| 2 | Abnahmeprotokoll Anhang D, ein Abschnitt je Fall mit Rechenweg, Prüfort im CRM und Ergebnisfeldern; Fälle ohne Test gekennzeichnet | `docs/acceptance/abnahme-anhang-d.md` |
| 3 | Verfahrensdokumentation, Kapitel 7 Automatik der Buchhaltung (M12-04 bis M12-06) | `docs/handbuch/verfahrensdokumentation.md` |
| 4 | Tabelle `g1_acceptance` (Migration 0242, RLS), Endpunkte `GET /accounting/g1-opening`, `PUT .../items/{key}`, `POST .../request`; CRM-Seite Einstellungen, Buchhaltung, G1 Öffnung | `apps/api/src/mhvp/accounting/g1_opening.py`, `g1_opening_routers.py`, `apps/web-crm/src/components/settings/G1OpeningChecklist.tsx`, `apps/web-crm/src/app/(app)/einstellungen/buchhaltung/g1-oeffnung/page.tsx` |

## Tests

* `apps/api/tests/integration/test_g1_opening.py`: feste Werte (23 Fälle, 5 manuelle Punkte),
  403 ohne Recht, 422 bei fehlendem Namen und unbekanntem Schlüssel, Kontenrahmenstand nach
  Freigabe, Antrag als regulärer Freigabeantrag mit Nachweiszeile, Stufe bleibt geschlossen,
  zweiter Antrag 409, Mandantentrennung.
* `apps/web-crm/src/components/settings/G1OpeningChecklist.test.tsx`: Stand, Ergebnis eintragen,
  Antrag stellen, Rechte.

## Offene Punkte

Siehe `docs/OPEN_QUESTIONS.md` M12-09; das Paket ändert keine Entscheidung.
