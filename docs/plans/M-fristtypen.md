# Package E: Fristtypen, eigene Fristen, Kündigungsfrist, Checkliste Verwalterwechsel, Zugangsdatum

Stand 28.09.2026. Schließt die Handbuchlücken Verwalterwechsel Zeile 1, Mieterwechsel Zeile 3 und
Mieterhöhung Zeilen 2 und 3 (nur der Fristtypteil; Briefbogen-PDF bleibt offen). Regel
`docs/rules/WS-01-fristtypen.md`. Freigabestufen G1 bis G5 bleiben geschlossen; kein Geldbezug.

## Umfang

1. Fristtypkatalog je Mandant (`deadline_type`): Bezeichnung, Code, Auslöser, Dauer in Monaten
   und Tagen (Betreibereingabe, kein Vorgabewert, "zu verifizieren"), verantwortliche Rolle,
   Quelle der Dauer, aktiv. Systemtypen Verwalterwechsel, Kautionsabrechnung, Mieterhöhung ohne
   Dauer je Mandant gesät.
2. Eigene Fristen (`deadline_entry`) aus Ticket, Vertrag, Einheit, Objekt oder Mieterhöhungsfall
   mit verantwortlicher Person (ES-10), Fälligkeit berechnet oder eingetragen; Spiegel in der
   Fristenliste (`compliance_deadline`, Typ `custom_deadline`) und im Kalender, Vorfrist an die
   verantwortliche Person.
3. Kündigungsfrist als Orientierung (`GET /workspace/notice-period`) im Formular Vertrag beenden.
4. Checkliste Verwalterwechsel je Objekt (`property_checklist`, Vorlage aus der
   Handlungsanweisung), Abhaken mit Datum und Benutzer.
5. Zugangsdatum der Mieterhöhung im CRM über die Aktion `receipt` der bestehenden Aktions-API.

## Dateien

- API: `mhvp/workspace/models.py` (drei Modelle), `mhvp/workspace/deadlines.py`,
  `mhvp/workspace/deadline_routers.py`, `mhvp/workspace/jobs.py` (Typ, Leser, Benachrichtigung),
  `mhvp/workspace/links.py`, `mhvp/letting/routers.py` (Aktion `receipt`),
  `mhvp/core/problems.py` (`MHVP-WS-0001` bis `0003`), `mhvp/main.py`, Migration
  `0230_deadline_types.py` (down_revision 0223, Integrator kettet um).
- CRM: `components/workspace/DeadlineCreatePanel.tsx`, `DeadlineEntriesPanel.tsx`,
  `components/settings/DeadlineTypesAdmin.tsx`, `components/properties/ManagerChangeChecklist.tsx`,
  `components/contracts/NoticePeriodHint.tsx`, `components/letting/RentIncreaseReceipt.tsx`,
  Seite `einstellungen/fristtypen`, Hooks auf Fristen, Ticket, Vertrag, Einheit, Objekt,
  Mieterhöhungsfall, Vertragsformular; BFF-Allowlist, `settings-index.ts`, `messages/de.json`,
  `messages/en.json` (additiv).
- Doku: Regel WS-01, Modul-README, Handbuchseiten Verwalterwechsel, Mieterwechsel, Mieterhöhung,
  Einstellungen, README Abschnitt Fristen, offene Punkte WS-01-Q1 und WS-01-Q2, Annahme A-074.

## Tests

- `tests/unit/test_deadline_math.py`: feste Erwartungswerte der Datumsarithmetik.
- `tests/integration/test_deadline_types.py`: Happy Path, 403, Mandantentrennung, Validierung,
  Tagesjob, Aktion `receipt`.
- Vitest je neuer Komponente; BFF-Allowlist-Abdeckung; Settings-Index.

## Offen

- Dauer der drei Systemtypen (WS-01-Q1), Vertragsfeld Kündigungsfrist (WS-01-Q2).
- Briefbogen-PDF des Mieterhöhungsschreibens (Handbuch Mieterhöhung Zeile 3, zweiter Teil).
