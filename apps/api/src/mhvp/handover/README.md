# handover

Übergabeprotokolle (M30) im Bereich Makler: digitale Wohnungsübergabe für Vermietung,
Verkauf und allgemeine Übergaben. Plan: `docs/plans/M30-uebergabeprotokoll.md`, Regel:
`docs/rules/M30-01.md`.

| Datei | Inhalt |
| --- | --- |
| `models.py` | `handover_protocol` mit Adress- und Einheitensnapshot, Kaution, interne Felder, Abschluss und PDF-Verweis; Teildatensätze `handover_participant` (optional Kontakt), `handover_meter` (optional Zähler der Stammdaten), `handover_room`, `handover_defect`, `handover_key`, `handover_item`, `handover_note`; `handover_signature` (PNG-Dokument, SHA-256, Zeitpunkt) |
| `services.py` | Nummernvergabe `UP-JJJJMMTT-NNN`, Vorbelegung aus Einheit und Objekt, Laden aller Teildaten samt Dokumenten, Hinweise vor dem Abschluss, neue Version mit Dateireferenzen statt Kopien, PDF-Ablage als Dokument |
| `pdf.py` | PDF mit reportlab auf dem Briefbogen des Mandanten (Firmendaten und Farbband aus `tenant_settings`), alle Abschnitte auch wenn leer, Fotos je Teildatensatz, Unterschriften mit Hash, Entwurfs- und Stornovermerk |
| `routers.py` | `/api/v1/handover/protocols`: Liste, Vorbelegung, Anlage, Feldänderung, Teildatensätze je Abschnitt (`/{section}`, `/{section}/{item_id}`, `/{section}/order`), Fotos und Anhänge (`/documents`), Unterschriften (`/signatures`), Hinweise, Abschluss, PDF, Versionen, Status, Zustellung, Portalzugang je Beteiligtem (`/participants/{id}/portal-access`) |
| `portal.py` | `/api/v1/portal/handover`: Sicht des Beteiligten mit Portalkonto und Recht `handover` (Stufe 3). Liste, Lesen ohne interne Felder, Felder ändern, Teildatensätze, Fotos, Unterschriften, Hinweise, Abschluss (danach Recht `read` für `READ_DAYS`), PDF; Schreiboperationen delegieren an `routers.py` |

Rechte: `contracts:read` lesen, `contracts:create` anlegen und neue Version,
`contracts:update` bearbeiten und abschließen, `contracts:delete` für die Stornierung
abgeschlossener Protokolle. Dateien liegen als Dokumente (M6) mit Verknüpfung
`handover_protocol` und je Teildatensatz `handover_meter`, `handover_room`,
`handover_defect`, `handover_item` (`documents.services.LINKABLE`).

Nicht enthalten (offen): Zustellung des Einladungscodes für den Portalzugang (M30-01 in
`docs/OPEN_QUESTIONS.md`), Datenübernahme aus U-Protokoll (M30-03), Entfernen von
Bildmetadaten (M30-04), zweiter Faktor für Gehilfen (M30-05).

## Weitere Dateien (Nachtrag 26.09.2026)

Im Abgleich mit dem Ordnerinhalt am 26.09.2026 fehlten oben:

* `images.py`: Bildbereinigung für Übergabefotos und Portal-Uploads (M30-04, A55, A58): EXIF, GPS, XMP, ICC entfernen, Ausrichtung übernehmen, skalieren; HEIC/HEIF vom iPhone über `pillow-heif` dekodieren und als JPEG speichern (A72, `output_mime_type` liefert den gespeicherten Typ)
* `imports.py`: Router `/api/v1/handover/imports/uprotokoll` für die Datenübernahme aus U-Protokoll (M30 Stufe 4)
* `uprotokoll_import.py`: Parser und Übernahmelogik für den U-Protokoll-Datenbankexport (M30 Stufe 4)

## Vertrag und Zählerstände (Package F, 28.09.2026)

Schließt die Lücken der Anleitung Mieterwechsel (`docs/handbuch/anleitung-mieterwechsel.md`):

* Vertragsverknüpfung: `contract_id` war im Modell und in `POST`/`PATCH /protocols` bereits
  vorhanden; neu sind die Prüfung des Vertrags beim `PATCH` (404 statt Fremdschlüsselfehler),
  die Zusammenfassung `contract` (Nummer, Art, Vertragspartei, Laufzeit) in
  `GET /protocols/{id}` sowie im CRM die Vertragsauswahl beim Anlegen (Verträge der
  gewählten Einheit) und der Block "Verknüpfter Vertrag" im Abschnitt Objekt des Editors
  (`HandoverContractLink.tsx`, bewusst als eigener kleiner Block, der Editor wird später
  umgebaut).
* Zählerstände übernehmen: `POST /protocols/{id}/meters/transfer` mit `{"confirm": true}`
  (Rechte `contracts:update` und `properties:update`, da Zählerstände Stammdaten sind).
  `services.transfer_meter_readings` legt je Protokollzähler mit Wert einen `meter_reading`
  (Quelle `manual`, Notiz `Übergabeprotokoll UP-…`) am Zähler der Einheit an; Zuordnung über
  `meter_id`, sonst über die Zählernummer (Leerzeichen, Bindestriche, Punkte, Schrägstriche
  ignoriert, Groß- und Kleinschreibung egal) unter den Zählern der Einheit und den
  Gemeinschaftszählern des Objekts. Ablesedatum: `read_on` der Zeile, sonst das
  Übergabedatum. Die neue Spalte `handover_meter.meter_reading_id` (Migration 0231) macht die
  Übernahme idempotent: eine Zeile mit Zählerstand wird nie ein zweites Mal übernommen; der
  Aufruf meldet `created`, `skipped` (mit Grund `no_value`, `no_date`, `no_meter`,
  `ambiguous_number`, `meter_not_in_unit`) und `already_transferred`. Ohne `confirm`
  422 `MHVP-HDOV-0001`; ohne übernehmbare oder bereits übernommene Zeile 409
  `MHVP-HDOV-0002`; stornierte Protokolle werden nicht übernommen. Abgeschlossene Protokolle
  dürfen übernommen werden (Regelfall nach der Unterschrift). Ereignis
  `handover.meters.transferred`. CRM: Block "Zählerstände übernehmen" im Abschnitt Zähler
  (`HandoverMeterTransfer.tsx`, Rückfrage vor der Übernahme). Regel `docs/rules/M30-07.md`.
* Tests: `tests/integration/test_package_f_handover_folders.py`.

## Tablet und Handy, Inhaltssperre nach Unterschrift (M31 WP2, 29.09.2026)

- `STEPS` enthält `defects` (Client Schritt Mängel); `current_step` akzeptiert alle 13 Schritte.
- Vollausgabe (`GET /protocols/{id}`, Portal ebenso) trägt additiv `hint_codes` (Codes
  parallel zu `hints`: `no_address`, `no_participants`, `no_meters`, `no_rooms`, `no_keys`,
  `no_signature`, `signatures_invalidated`, `no_date`, `iban_invalid`), `content_locked`
  und `changes`; jedes Dokument trägt `thumbnail_url` (null für Unterschriften, PDF und
  Nichtbilder).
- `GET /protocols/{id}/documents/{doc}/thumbnail` (Regel M30-08): abgeleitetes JPEG, längste
  Kante 320 px, `Cache-Control: private, no-store`, nichts wird gespeichert; Portal Pendant
  `GET /portal/handover/{id}/documents/{doc}/thumbnail` mit Grant.
- `GET /protocols` filtert mit `handover_date` (ein Tag) oder `handover_from` und
  `handover_to` (Bereich).
- Regel M30-09: nach der ersten gültigen Unterschrift antworten die Inhaltsabschnitte
  (Zähler, Räume, Mängel, Schlüssel, Gegenstände, Bemerkungen), Fotos und Anhänge sowie
  Protokollfelder außer `current_step` und den internen Feldern mit 409. `POST
  /protocols/{id}/changes` (`reason` Pflicht) schreibt `handover_change` (Grund, Zeitpunkt,
  Bearbeiter), kennzeichnet alle gültigen Unterschriften (`invalidated_at`,
  `invalidated_change_id`) und gibt den Inhalt frei; das PDF druckt den Verlauf. Migration
  0239.
- `image/heif` ist wie `image/heic` zulässig und wird als JPEG abgelegt.
