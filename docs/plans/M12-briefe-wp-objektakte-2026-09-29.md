# M12 Lücken: Briefe mit Versandnachweis, Wirtschaftsplan in die Zahlungspläne, Objektakte-Export (29.09.2026)

Drei Lücken aus `docs/plans/M12-lernender-buchhalter-und-luecken-2026-09-28.md` und
`docs/handbuch/README.md` (Abschnitt Lücken in der Software). Freigabestufen G1 bis G5 bleiben
geschlossen; nichts in diesem Paket versendet, bucht oder zahlt.

## 1. Schreiben auf Briefbogen mit Versandnachweis

* `mhvp/documents/letter_records.py`: Ablage eines gerenderten Briefs (`mhvp.documents.letters`,
  Briefbogen nur aus den Mandanteneinstellungen) als Dokument, Ticketverknüpfung mit internem
  Kommentar, Versandnachweis als `dispatch` (Kanal, Datum, Benutzer, Referenz) plus Ereignis.
* `POST /objektakte/properties/{id}/completeness/nachforderungsschreiben/pdf` (`documents:create`
  und `objektakte:read`), `POST /letting/rent-increases/{id}/letter/pdf` (`contracts:approve`).
* Was gesperrt bleibt: Post wird außerhalb versendet und nur erfasst; E-Mail entsteht als
  Entwurf für die Mailfreigabe (M20-04); Portalweg für die Mieterhöhung erst mit G3; der
  Prozessschritt Versand erfassen der Mieterhöhung bleibt hinter G3 (Status unverändert).
* UI: `LetterRecordForm` (Objektseite im Abschnitt Vollständigkeit, Link aus der Checkliste
  Verwalterwechsel; Fallseite Mieterhöhung).

## 2. Wirtschaftsplan in die Zahlungspläne (W02)

* `GET /hoa/plans/{id}/apply/preview`, `POST /hoa/plans/{id}/apply` mit `confirm` und
  `snapshot_hash`; zweite Person, idempotent, bereits gebuchte Monate nur als Hinweis.
* Gates: Zeilen sind Vertragsstammdaten (keine Stufe), Sollstellung daraus hinter G1
  (`docs/rules/W02-wirtschaftsplan.md`).
* UI: `PlanApplyPreview` in `HoaForms.tsx`.

## 3. Objektakte-Export bei Abgabe

* Migration `0246_objektakte_export.py` (Tabelle `objektakte_export`, RLS).
* `mhvp/objektakte/export.py`, `export_routers.py`, Celery `mhvp.objektakte.export_property`.
* Rechte `properties:update` und `documents:read`; Bestätigung und Datenschutzhinweis; nur nach
  erfasster Beendigung; Download mit Ereignis `objektakte_export.downloaded`.
* UI: `ObjektakteExportPanel` auf der Objektseite nach der Beendigung.

## Tests

* `tests/integration/test_m12_letters_plan_export.py` (feste Werte, 403, Mandantentrennung).
* Vitest: `LetterRecordForm.test.tsx`, `ObjektakteExportPanel.test.tsx`, `HoaForms.test.tsx`
  (PlanApplyPreview), `ManagerChangeChecklist.test.tsx`.

## Offene Punkte

`docs/OPEN_QUESTIONS.md` M12-L1 bis M12-L3.
