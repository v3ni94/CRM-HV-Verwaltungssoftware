# Package F: Übergabeprotokoll mit Vertrag, Zählerstände übernehmen, Objektordner 04 und 05, Upload mit Verknüpfungen

Stand 28.09.2026. Schließt die Lücken der Anleitungen Mieterwechsel (Zeilen 1 und 2) und
Objektordner (Zeilen 1 bis 3) aus `docs/handbuch/README.md`, Abschnitt Lücken in der Software.
Gates G1 bis G5 bleiben geschlossen; kein Geldfluss, keine Abrechnung, keine Rechtsregel.

## Befund vor der Umsetzung

- `handover_protocol.contract_id` und die Annahme in `POST`/`PATCH /handover/protocols`
  bestanden bereits; es fehlten die Prüfung beim `PATCH`, die Anzeige und die Auswahl im CRM.
- Zählerstände des Protokolls (`handover_meter`) hatten keinen Bezug zu `meter_reading`;
  die Übernahme musste doppelt von Hand erfolgen (Vertrag beenden, Zählerstände zur
  Beendigung).
- Standardkategorien (`documents/defaults.py`) kannten keine Ziele `04_Mieterakte` und
  `05_Eigentümerakte`; die Ordnerstruktur war nur im Handbuch beschrieben.
- `POST /documents` konnte Kategorie und Verknüpfungen `contract`/`contact` bereits; nur der
  Upload in der Dokumentsuche bot sie nicht an.

## Umsetzung

| Bereich | Dateien |
| --- | --- |
| API Übergabe | `mhvp/handover/models.py` (`meter_reading_id`), `services.py` (`transfer_meter_readings`), `routers.py` (`_contract_summary`, `_require_contract`, `POST /protocols/{id}/meters/transfer`), Migration `0231_handover_meter_reading_link.py`, Fehlercodes `MHVP-HDOV-0001`/`0002` |
| API Dokumente | `mhvp/documents/defaults.py` (`tenant_file`, `owner_file`), `folders.py`, `routers.py` (`GET /document-folders`, `POST /document-categories/ensure-defaults`) |
| CRM Übergabe | `HandoverCreate.tsx` (Vertragsauswahl), `HandoverContractLink.tsx`, `HandoverMeterTransfer.tsx`, `HandoverEditor.tsx` (zwei Blöcke eingehängt), `types.ts` |
| CRM DMS | `DmsUpload.tsx` (Kategorie, Vertrag, Kontakt), `DmsFolderStructure.tsx`, `app/(app)/dms/suche/page.tsx` |
| BFF | `GET contracts`, `POST handover/protocols/{id}/meters/transfer`, `GET document-folders`, `POST document-categories/ensure-defaults` |
| Texte | `messages/de.json`, `messages/en.json` (nur ergänzt) |
| Tests | `tests/integration/test_package_f_handover_folders.py`; `HandoverCreate.test.tsx`, `HandoverContractLink.test.tsx`, `HandoverMeterTransfer.test.tsx`, `DmsUpload.test.tsx`, `DmsFolderStructure.test.tsx` |
| Doku | Handbuch `anleitung-mieterwechsel.md`, `anleitung-objektordner.md`; READMEs `handover`, `documents`; Regel `docs/rules/M30-07.md`; offener Punkt F-01 |

## Entscheidungen

- Ablesungen aus dem Protokoll erhalten die Quelle `manual` mit der Protokollnummer in der
  Notiz und dem Verweis `handover_meter.meter_reading_id`; ein neuer Enum-Wert in
  `reading_source` hätte eine Typänderung in `properties` verlangt und keinen Mehrwert.
- Die Übernahme braucht `properties:update` zusätzlich zu `contracts:update`, weil sie
  Stammdaten erzeugt.
- Migration 0231 setzt auf 0223 auf (tatsächlicher Kopf im Arbeitsstand); der Integrator
  kettet neu.
- Die elf Unterordner werden nicht erfunden: das CRM zeigt sie aus der objektakte-Übernahme
  oder "zu verifizieren" (F-01).

## Nicht enthalten

- Auswahl eines Zählers der Einheit direkt im Zählereintrag des Protokolls (Editor wird
  von einem anderen Team umgebaut); bis dahin Zuordnung über die Zählernummer.
- Anlage der Unterordner je Person in Drive durch das CRM.
