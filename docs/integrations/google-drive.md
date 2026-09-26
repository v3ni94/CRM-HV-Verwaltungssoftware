# Google Drive (Spiegelablage)

Stand 26.09.2026. Technische Anbindung: `apps/api/src/mhvp/documents/dms.py`
(`GoogleDriveStore`, Drive v3 REST API, OAuth-Refresh-Token des technischen Kontos),
Spiegeljob `tasks.py`, Objektakte `property_filing.py`. Offene Betreiberpunkte
(OAuth-Client, Wurzelordner, Auftragsverarbeitung) in `docs/OPEN_QUESTIONS.md` M6-02.

## Zugang und Ablage

- Je Mandant über `PUT /dms-connections/google_drive` (`options.root_folder_id`,
  `options.client_id`, `secret` als JSON mit `client_secret` und `refresh_token`,
  feldverschlüsselt).
- Ordnerstruktur je Objekt: `01_Legitimationsunterlagen`, `02_Stammakte`, `03_Buchhaltung`,
  `04_Mieterakte`, `05_Eigentümerakte`, `06_Sonstiges` (Standard). `external_ref` ist die
  Drive-Datei-ID.

## Löschung im CRM (Betreiberentscheidung 26.09.2026, M6-03)

Bei einer rechtmäßigen Löschung im CRM wird die Drive-Kopie entfernt:

1. `DELETE /drive/v3/files/{id}?supportsAllDrives=true` (endgültig, bevorzugt).
2. Lehnt Drive das ab (HTTP-Fehler außer 404, zum Beispiel fehlendes Löschrecht auf einer
   geteilten Ablage), folgt `PATCH /drive/v3/files/{id}` mit `{"trashed": true}`
   (Papierkorb). Das Journal enthält dann `result` `trashed` und in `note` den Grund.
3. 404 bedeutet: bereits entfernt (`already_gone`).

Protokoll: Ereignisse `document.mirror_deleted` beziehungsweise `document.mirror_delete_failed`
je Versuch; die Löschung im CRM bleibt "offen", bis der Schritt gelungen ist. Wiederholung
mit der Standardleiter des Tasks (1, 5, 30 Minuten, 2, 6, 24 Stunden), danach über
`POST /documents/deletions/{document_id}/retry`. Der Papierkorb von Drive leert sich nach
den Regeln von Google, nicht durch die Plattform. Regel `docs/rules/M6-03-loeschung-spiegel.md`.
