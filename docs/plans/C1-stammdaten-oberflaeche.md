# C1 Stammdaten in der Oberfläche: Gebäude, Einheiten und Umlageschlüsselwerte

Bezug: `docs/handbuch/README.md` Abschnitt Lücken in der Software (erste Zeile Stammdaten),
`docs/handbuch/anleitung-stammdaten.md`, MASTER-PROMPT Abschnitt 6.2 (Objekte, Gebäude,
Einheiten, Umlageschlüssel), `docs/OPEN_QUESTIONS.md` C1-01. Gates G1 bis G5 bleiben geschlossen.

## Ziel

Gebäude, Einheiten und Schlüsselwerte auf der Objektseite anlegen, statt nur über Import oder
Schnittstelle. Einheitennummern je Objekt eindeutig, Schlüsselwerte mit Gültigkeitszeitraum,
Summenprüfung je Schlüssel gegen eine vom Betreiber eingetragene Sollsumme als Warnung, nie als
Sperre.

## Umsetzung

- API (`mhvp.properties`): bestehende Endpunkte `POST /properties/{id}/buildings`,
  `POST /properties/{id}/units`, `POST /properties/{id}/allocation-keys`,
  `POST /units/{id}/allocation-values` unverändert genutzt. Neu: `AllocationKey.expected_total`
  (Migration `0227_allocation_key_expected_total.py`, down_revision 0222),
  `PATCH /properties/{id}/allocation-keys/{kid}`, `GET /properties/{id}/allocation-summary?as_of=`.
  Keine neuen Fehlercodes (Validierung, Konflikt und Nicht gefunden aus `mhvp.core.problems`).
- CRM (`apps/web-crm/src/components/properties`): `BuildingsCreate.tsx`, `UnitsCreate.tsx`,
  `AllocationKeysPanel.tsx`; Einbindung in `objekte/[propertyId]/page.tsx` und
  `objekte/[propertyId]/gebaeude/[buildingId]/page.tsx`. Erfassungsstandards: ES-03 am Gebäude
  (`checkBuilding` in `lib/entry-standards.ts`), Dublettenprüfung der Einheitennummer vor dem
  Speichern. BFF-Allowlist und Nachrichten (`de.json`, `en.json`) additiv.
- Dokumentation: `apps/api/src/mhvp/properties/README.md`, `docs/handbuch/anleitung-stammdaten.md`,
  `docs/handbuch/objekte-einheiten.md`, `docs/OPEN_QUESTIONS.md` C1-01.

## Tests

- `apps/api/tests/integration/test_c1_allocation_summary.py`: feste Erwartungswerte (400, 350,
  250 gegen Sollsumme 1000: Summe 750 und Abweichung -250 vor dem dritten Wert, danach 1000 und
  0), PATCH mit unveränderlichem Kürzel und negativer Sollsumme (422), Schlüssel eines anderen
  Objekts (404), Dublette der Einheitennummer (409), Zeitraum in falscher Reihenfolge (422),
  Hausmeisterrolle (403), zweiter Mandant (404), ohne Anmeldung (401).
- `BuildingsCreate.test.tsx`, `UnitsCreate.test.tsx`, `AllocationKeysPanel.test.tsx` (Vitest).

## Offen

- C1-01: Sollsummen je Objekt eintragen und verifizieren; Sperrwirkung vor G4 entscheiden.
- Kürzel, Bezeichnung, Maßeinheit und Art bestehender Schlüssel nur über die Schnittstelle änderbar.
