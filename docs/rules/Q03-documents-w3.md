# Q03 Dokumente Welle 3: direkter Transfer, Massenupload, geschwärzte Kopien, Sperren, Eingangsadresse, Drive-Änderungen

| Field | Content |
| --- | --- |
| ID | `Q03` (S12-06, M6-08, M6-03, M25-01, S711-06, M6-04, M6-05; CRM M6-01, M6-02, M6-09) |
| Title | Signierte Upload- und Download-URLs, Lebenszyklus temporärer Objekte, ZIP-Massenupload als `import_run`, geschwärzte Belegkopie mit Protokoll und Vier-Augen-Freigabe, Sperrart und WEG-Dauerunterlage, Aufbewahrungsprofil je Rechtsträgerart, Mandanten-Eingangsadresse mit Plus-Adressierung, Drive Changes API mit Cursor |
| Scope | `mhvp.documents.transfer_routers` (`/documents/uploads`, `/documents/uploads/{id}/complete`, `/documents/{id}/download-url`, `/documents/zip-import`, `/documents/{id}/redactions[/{rid}/release]`, `/document-intake-address`, `/dms-changes/google-drive/sync`), `blobs.py` (`tmp/`), `tasks.py` (`mhvp.documents.cleanup_tmp`, `mhvp.documents.drive_changes`), `drive_changes.py`, `intake_address.py`, `intake.process_mailbox`, `retention.profile_for_document`, `services.deletion_blocker`; Migration 0272; alle Mandanten |
| Source status | Fachliche Umsetzung nach 11.2, 11.4, 12 (Dateien), 7.9.2 PÜ11 und 7.11 S04/S05. Keine Rechtsnorm zitiert. Die Behandlung von Teilungserklärung und Protokollen einer GdWE als Dauerunterlage ist Produktschutz (0.2), keine behauptete Rechtspflicht; die Fristen selbst bleiben Entwürfe (V17, M6-04) |
| Acceptance case | `tests/integration/test_q03_documents_w3.py` (vorgerechnet: ZIP mit fünf Einträgen ergibt zwei Dokumente, zwei abgewiesene Dateien, ein ignorierter Systemeintrag; Profil der Klasse mit Art `hoa` für ein WEG-Objekt, Basisprofil für ein Mietobjekt; Drive-Cursor 10 auf 11, zwei Änderungen, eine zugeordnet, eine entfernt; Rechte 403, anderer Mandant 404, Validierung 422, Vier Augen 403) |
| Change reason | Lückenliste 30.09.2026, Welle 3, Paket Q03 |

## Regeln

- Direkter Upload: Die API prüft Typ und angekündigte Größe und gibt eine signierte PUT-URL in den
  Bereich `tmp/<Mandant>/uploads/<id>` aus (300 Sekunden). Erst `complete` legt das Dokument an und
  führt dieselben Prüfungen wie der Upload über die API aus (Inhalt, Größe, Schadsoftware, Bilder
  ohne Metadaten). Der Schlüssel enthält die Mandanten-ID; ein fremder Mandant findet nichts (404).
- Download-URL: nur für Originale im Objektspeicher, nach Rechte-, Mandanten- und Scopeprüfung,
  300 Sekunden gültig, protokolliert als `document.downloaded` mit `signed`.
- Temporäre Objekte: Lebenszyklusregel auf `tmp/` (ein Tag, auch abgebrochene Multipart-Uploads)
  und täglicher Bereinigungsjob, der Objekte älter als ein Tag entfernt. Originale unter
  `tenants/` sind nie betroffen.
- ZIP-Massenupload: jede Datei läuft einzeln durch die normale Ablage; abgewiesene Dateien stehen
  mit Grund im Ergebnis und halten die übrigen nicht auf. Fällt Speicher oder Prüfdienst aus,
  bricht der ganze Lauf ohne Teilergebnis ab. Höchstens 200 Dateien, Archiv höchstens das
  Vierfache der Dokumentgrenze, jede Datei höchstens die Dokumentgrenze (ohne Vertrauen auf die
  angegebene Größe). Der Lauf ist ein `import_run` (Quelle `document_zip`) mit einer Position je
  Dokument; ein Rückgängig löscht keine Dokumente (0.1.7).
- Geschwärzte Kopie: neue Datei als eigenes Dokument, verknüpft mit dem Original (Rolle
  `generated`) und mit dessen Bezügen; Grund, Umfang und Bearbeitungsschritte als Protokoll. Das
  Original bleibt unverändert; eine inhaltsgleiche Datei wird abgewiesen. Die Kopie ist intern,
  bis eine zweite Person sie für Portalrollen freigibt. Solange Kopien bestehen, ist das Original
  nicht löschbar.
- Sperren: Sperrart `litigation`, `tax_procedure`, `evidence`, `legal_matter` oder `other` am
  Dokument. Eine Sperre am Original hält die abgeleiteten Dokumente und umgekehrt.
- WEG-Dauerunterlage: Teilungserklärung und Protokolle eines Dokuments, das zu einer GdWE gehört
  (Rechtsträgerbezug oder WEG-Objekt), werden als Dauerunterlage gekennzeichnet und nie über ein
  Standardprofil gelöscht. Das Kennzeichen setzt jeder mit Änderungsrecht; aufheben nur mit
  `documents:approve`.
- Profil je Rechtsträger: gibt es zur Unterlagenklasse des Kategorieprofils ein Profil genau für
  die Rechtsträgerart des Dokuments, gilt dieses (Annahme A-Q03-01 zur Ableitung der Art).
- Eingangsadresse: `<postfach>+<token>@<domain>` je Mandant, Konfiguration in
  `TenantSettings.sources`. Nachrichten an die eigene Adresse laufen als Quelle `forward` durch den
  Dokumenteneingang (nur Vorschläge), mit optionaler Absenderliste; Plus-Adressen mit fremdem
  Token werden übersprungen.
- Drive-Änderungen: erster Lauf speichert nur den Startcursor. Danach werden Änderungen an
  gespiegelten oder in Drive gespeicherten Dokumenten gezählt; entfernte oder gelöschte Dateien
  werden am Spiegel vermerkt und als `document.drive_removed` protokolliert. Kein Indexeintrag und
  kein Original wird geändert oder gelöscht.
