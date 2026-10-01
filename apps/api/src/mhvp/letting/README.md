# mhvp.letting

Rent increases, vacancies, exposés, prospects, listings and the OpenImmo export (M26, M28).
Plans: `docs/plans/M26.md`, `docs/plans/M28-makler.md`. Rules: `docs/rules/M26-rent-law.md`,
`docs/rules/M26-02.md`, `docs/rules/M28-01.md`.

## Files

* `models.py`: rent increase cases, prospects, listings (migration 0023 and later, RLS).
* `routers.py`: `/api/v1/letting` (rent increase process, vacancies, exposé draft, prospects,
  listings); registered in `main.py`.
* `rentlaw.py`: rent law rule set for rent increases (M26-01); `platform_router` and
  `tenant_router` registered in `main.py`.
* `openimmo.py`: OpenImmo 1.2.7 XML export for listings (M26-02), read only, no portal upload.
* `openimmo_schema.py`: structural check of the OpenImmo export (no official XSD bundled).
* `flow_import.py`: FLOW import from a MySQL/MariaDB dump (M28 stage 4), idempotent per
  `external_uuid`.
* `tasks.py`: Celery job deleting prospect records after their deletion date (data minimisation).

Gates: no money flows; sending to portals or FLOWFACT is not implemented (M28 stage 3 open).

## Addendum 29.09.2026 (rent increase letter on the letterhead, M12 gaps)

* `routers.py`: `POST /letting/rent-increases/{id}/letter/pdf` (`contracts:approve`) files the
  letter of `rentlaw.letter_body` on the tenant letterhead as a document of the case, contract,
  unit, property and tenant, optional ticket link and dispatch record
  (`mhvp.documents.letter_records`). The process step `send` stays behind G3, the portal
  channel is refused while G3 is closed, e-mail only as a draft for the mail approval; the PDF
  carries the draft marking until the legal review is documented.


## Welle 2 (P20, 30.09.2026)

* `basis_checks.py`: Rechenprüfung für die Basen `index`, `modernization`, `graduated` aus `basis_data` (Regel `docs/rules/M26-BASIS-01-mieterhoehung-basen.md`); keine hinterlegten Gesetzeswerte, Quelldokument Pflicht.
* `rentindex.py`: Mietspiegelwerte je Gemeinde (`/letting/rent-index`, CSV-Import mit Vorschau, Abfrage `/lookup`), Regel `M26-INDEX-01`.
* `routers.py`: Leerstandsmaßnahmen (`vacancy_case`, `PUT /letting/vacancies/{unit_id}`, Anzeige aus Leerstand), Exposé als PDF im DMS (`POST /letting/units/{unit_id}/expose/pdf`), Suchprofil der Interessenten und Abgleich (`GET /letting/listings/{id}/prospect-matches`). Regeln `M26-VAC-01`, `M26-PROS-01`.
* Migration `0269_letting_w2`. Offen: KI-Plausibilitätsprüfung (`docs/OPEN_QUESTIONS.md` P20-01), Bilder im Exposé-PDF.

## Paket Q14 (30.09.2026, Welle 3)

* M26-05: `POST /letting/units/{unit_id}/expose/pdf` bettet die Bilder der Anzeige ein (PNG, JPEG, höchstens 8,
  `Letter.images` in `mhvp.documents.letters`); Antwort mit `images_embedded`.
* M26-03: `POST /letting/rent-increases/{id}/adopt-rent-index` übernimmt Untergrenze, Mittelwert oder Obergrenze
  eines Mietspiegelwertes in einen Entwurfsfall und prüft neu.
* M5-08: `rent_increase_case.ai_check_id` (Migration 0281, Verweis auf `ai_proposal`), `PUT /letting/rent-increases/{id}/ai-check`.
* M26-06: CRM Interessentenabgleich an der Einheit; CRM Seite `/vermietung/mietspiegel`.
* R09 (Q14-02): `create_rent_increase` and `adopt-rent-index` call `rent_increase_check.auto_queue` after the transaction (switch `ai_automation.rent_increase_check`, released provider, unchanged input queues nothing); the case itself never changes, errors of the AI never block it.
