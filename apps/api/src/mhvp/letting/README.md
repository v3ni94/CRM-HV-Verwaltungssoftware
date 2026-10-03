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

### Datenmigration Selbstauskunft-Token (S16-03-01)

`tasks.hash_self_disclosure_tokens_once` stellt Altzeilen mit Klartext-Token auf `sha256:<hex>` um (idempotent, ohne Schemaänderung, alle Mandanten). Auslösung manuell: Celery-Task `mhvp.letting.hash_self_disclosure_tokens` oder `POST /api/v1/platform/maintenance/self-disclosure-token-hash` (Plattform-Administrator). Kein Beat-Eintrag.

### Begrenzung der Selbstauskunft (GAI-309, Welle 21, AJ07)

`POST /letting/self-disclosure/{token}` begrenzt `payload` (Produktschutz): höchstens 64 KiB als JSON, 200 Felder und Listeneinträge, Tiefe 3, Feldnamen bis 100 Zeichen, Texte bis 5.000 Zeichen; sonst 422. Die Abgabe erzeugt das Ereignis `self_disclosure.submitted` nur mit der Interessenten-Id, ohne Inhalt. Eigenes Limit je Token ist nicht umgesetzt (offener Punkt); Speicherdauer nach DSGVO ist mit dem Datenschutz abzustimmen.

### Verkaufsinserate hinter Schalter (GAK-208, Welle 24, AN19)

Schalter `letting.sale_marketing` in `tenant_settings.sources` (Standard aus, `GET/PUT /letting/settings/sale-marketing`). Aus: Verkaufsinserate nur als Entwurf; Aktivierung und Übergabe an Makleranbieter antworten 409. Abgrenzung Abschnitt 1, Frage AN19-02.

## Mieterhöhungssperre, Vorschläge, Interessentenlöschung (Welle 24, AN18)

- `increase_settings.py`: Schalter in `tenant_settings.sources` (`rent_increase_block_months.<basis>`, `rent_increase_proposals`), API `GET/PUT /letting/rent-increase-settings`.
- Aktion `apply` setzt den Zahlungsgrund aus der Begründung und legt `check.block_proposal` ab; Aktion `set_block` schreibt `contract.rent_increase_block_until` nach Bestätigung.
- `increase_proposals.py`: Rechenkern für fällige Staffelstufen und Indexanpassungen (nur Vorschlag, ohne Job, bis die Vertragsfelder existieren).
- `prospect_erasure.py`: Löschvorschlag (privacy_erasure_request proposed) für den Kontakt eines gelöschten Interessenten.

## Indexklausel, Staffel, Verbraucherpreisindex (Welle 25, AO03, GAK-203)

- `letting/index_rent.py`: `GET/PUT /letting/contracts/{id}/index-terms` (Indexklausel als `contract.index_agreement`,
  Staffelstufen in `contract_graduated_step`, Migration 0456), `GET /letting/rent-increase-proposals` (Entwürfe des
  Jobs), `POST /letting/rent-increase-proposals/run` (nur mit Schalter draft, sonst 409),
  `GET /letting/consumer-price-index?series=`; Plattform: `POST /platform/consumer-price-index/import` (CSV, Quelle,
  Datenstand, nicht freigegeben) und `/release` (nur Plattform-Admin).
- `increase_proposals.propose_for_tenant` und Celery `mhvp.letting.propose_rent_increases` (täglich 04:40): legen nur
  `rent_increase_case` draft an, nie Mietzeilen. Regel `docs/rules/AO03-indexklausel-staffel-vpi-vorschlaege.md`.
