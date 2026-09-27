# Paperless-ngx (Spiegel-DMS)

Stand 26.09.2026. Technische Anbindung: `apps/api/src/mhvp/documents/dms.py`
(`PaperlessStore`), Spiegeljob `tasks.py`, Suche `paperless_search.py`, Webhook
`paperless_webhook.py`. Offene Betreiberpunkte in `docs/OPEN_QUESTIONS.md` M6-01.

## Zugang

- Instanz je Mandant über `PUT /dms-connections/paperless` (`base_url`, API-Token als
  `secret`, feldverschlüsselt). Der Token verlässt die Plattform nicht; Dateien werden über
  den Proxy `GET /dms-documents/{id}/file` ausgeliefert.
- Schlagwörter: `mhvp:tenant:<slug>`, `objekt:<Objektnummer>`, Kategorie-Schlagwörter;
  Korrespondent und Dokumenttyp aus den Dokumentmetadaten. Fehlende Schlagwörter,
  Korrespondenten und Dokumenttypen werden mit dem Mandanten-Token angelegt.

## Spiegelung

`POST /api/documents/post_document/`, asynchrone Verarbeitung; die Dokument-ID wird über
`/api/tasks/` aufgelöst (`external_ref` erst `task:<id>`, dann die Paperless-ID).

## Löschung im CRM (Betreiberentscheidung 26.09.2026, M6-03)

Das Paperless-Dokument wird bei einer Löschung im CRM nicht gelöscht. Es erhält das
Schlagwort `gelöscht` (`PaperlessStore.add_tag`: `GET /api/documents/{id}/`, Schlagwort über
`/api/tags/?name__iexact=gelöscht` suchen oder anlegen, `PATCH /api/documents/{id}/` mit der
erweiterten Schlagwortliste, idempotent). Antwortet Paperless mit 404, gilt die Kopie als
bereits entfernt. Jeder Schritt wird als Ereignis `document.mirror_marked_deleted` oder
`document.mirror_delete_failed` protokolliert; die Löschung im CRM bleibt "offen", bis der
Schritt gelungen ist (`GET /documents/deletions`). Regel `docs/rules/M6-03-loeschung-spiegel.md`.

Hinweis für die Sachbearbeitung: Dokumente mit dem Schlagwort `gelöscht` sind im CRM nicht
mehr vorhanden; eine Bereinigung in Paperless selbst ist Sache des Betreibers nach dem
Löschkonzept (V17) und wird nicht von der Plattform ausgelöst.
