# M6-03 Löschung gespiegelter Dokumente: Drive löschen, Paperless mit "gelöscht" kennzeichnen

| Field | Content |
| --- | --- |
| ID | `M6-03` |
| Title | Nach einer rechtmäßigen Löschung in der Plattform wird die Kopie in Google Drive gelöscht (endgültig, ersatzweise Papierkorb, vermerkt), das Dokument in Paperless-ngx bleibt erhalten und erhält das Schlagwort "gelöscht"; beide Schritte werden protokolliert, die Löschung gilt bis zum Erfolg beider Schritte als "offen" |
| Scope | `mhvp.documents.mirror_deletion` (Schritte, Celery-Task `mhvp.documents.delete_mirror`, Wiederholungsleiter 1 min bis 24 h), `mhvp.documents.dms.GoogleDriveStore.delete`/`trash`, `PaperlessStore.add_tag`, Tabelle `document_mirror_deletion` (Migration 0143, RLS), `DELETE /documents/{id}`, `GET /documents/deletions`, `POST /documents/deletions/{document_id}/retry`, Wiederanwendung nach Restore (`deletion_journal`, A44); alle Mandanten |
| Source status | Fachliche Umsetzung (6.9.5: Löschung wird in Index, MinIO, Paperless und Drive gleich behandelt und protokolliert) mit Betreiberentscheidung 26.09.2026 zur Ausgestaltung (Drive löschen, Paperless behalten und kennzeichnen). Produktschutz: Löschung bleibt "offen" bis beide Schritte gelungen sind, kein stiller Abbruch. Keine Rechtsnorm wird zitiert; die Voraussetzungen der Löschung selbst (freigegebenes Profil, abgelaufene Frist, keine Sperre) bleiben unverändert und richten sich nach M6-04 und V17 |
| Acceptance case | D46 (Ablehnung und Teillöschung begründet und protokolliert), D47 (Restore berücksichtigt Löschentscheidungen): `tests/integration/test_m6_mirror_deletion.py` (Schrittzeilen und Ereignisse in der Löschtransaktion, Drive löschen, Drive-Ablehnung mit Papierkorb, bereits entfernt, Paperless-Schlagwort anlegen und einmalig zuweisen, Fehler mit Wiederholung, Zustand offen bis erledigt, erneutes Anstoßen, Mandantentrennung, Sperre ohne freigegebenes Profil unverändert), `tests/unit/test_documents_mirror_deletion_clients.py` (Clients ohne Netz) |
| Implementation | Ereignisse `document.mirror_delete_requested`, `document.mirror_deleted` (Drive, `result` `deleted`, `trashed`, `already_gone`, `note` bei Ersatz), `document.mirror_marked_deleted` (Paperless, `result` `tagged`, `already_gone`, `tag` `gelöscht`), `document.mirror_delete_failed` (Versuch, Fehler); Schrittstatus `open`/`done`, `attempts`, `last_error` |
| Change reason | Betreiberentscheidung 26.09.2026 zu M6-03 (zuvor: gespiegelte Dokumente gesperrt bis zur protokollierten Löschung in den Spiegeln, dann Löschung in beiden Spiegeln) |

## Regeln

- Kein Schritt hier hebt die Löschvoraussetzungen auf: `DELETE /documents/{id}` prüft weiterhin
  freigegebenes Aufbewahrungsprofil, abgelaufene Frist und fehlende Löschungssperre
  (`deletion_blocker`, MHVP-DOC-0001). Die frühere zusätzliche Sperre gespiegelter Dokumente
  entfällt; Spiegel allein sind kein Grund, ein Dokument zu behalten.
- Google Drive: `delete` (endgültig) zuerst. Lehnt Drive ab (HTTP-Fehler außer 404), folgt
  `trash` (Papierkorb); das Journal enthält `result` `trashed` und den Grund in `note`. 404
  ergibt `already_gone`.
- Paperless-ngx: Das Dokument wird nie gelöscht. Das Schlagwort "gelöscht" wird mit dem
  Mandanten-Token gesucht (`name__iexact`) und bei Bedarf angelegt; die Zuweisung ist
  idempotent (bereits gesetzt: kein zweiter PATCH). 404 ergibt `already_gone`.
- Fehler bleiben im Journal (`document.mirror_delete_failed`) und in der Schrittzeile; die
  Wiederholung folgt der Standardleiter des Celery-Tasks; nach dem letzten Versuch bleibt der
  Schritt `open` und über `POST /documents/deletions/{document_id}/retry` erneut anstoßbar.
- Restore-Wiederanwendung (A44): gespiegelte Dokumente werden wie alle anderen gelöscht, die
  Schritte nach dem Commit eingereiht (`replay: true`, `mirror_deletions` im Ereignis).
