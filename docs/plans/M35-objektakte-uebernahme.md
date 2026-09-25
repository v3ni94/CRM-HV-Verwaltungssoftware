# M35 objektakte-Übernahme: vollständige Migration in das CRM

Stand 25.09.2026. Betreiberentscheidung vom 25.09.2026: objektakte (Repository-Klon
`/home/user/v3ni94/objektakte`, produktiv als Container-Stack `objektakte-*`, ca. 26.000
Dokumente mit Vorschaubildern, OCR und dreistufiger Klassifikation, Review Center,
Eigentümer- und Mieterlisten, Vollständigkeitsprüfung, Nachforderungsschreiben,
Google-Drive-Ablage mit Sechs-Ordner-Struktur je Objekt) wird vollständig in dieses
Repository (FastAPI, PostgreSQL mit RLS, Celery, Next.js) überführt. Diese Entscheidung
ersetzt die frühere Entscheidung in `docs/plans/M29-dms.md` ("nicht in dieses Repository
kopieren"). Paperless-ngx bleibt eigener Dienst über API, Kimai und n8n bleiben getrennt.

Kein Code-Copy: objektakte ist Django/MariaDB, das CRM ist FastAPI/PostgreSQL. Übernommen
werden Datenmodell, Daten und Funktionen als Neubau auf vorhandenen bzw. neuen CRM-Modulen,
nicht der Python-Code selbst (Ausnahme: Fachlogik wie Klassifikationsregeln, Vollständigkeits-
prüfungsregeln, Textbausteine der Nachforderungsschreiben werden als Spezifikation
übernommen und im CRM-Stil neu implementiert).

## 1. Inventar objektakte

### 1.1 Apps und Zweck
- `apps.objects`: `ManagedObject` (Schlüssel `object_number`, z. B. "623"; Drive-Wurzelordner
  `drive_root_folder_id`/`drive_root_folder_name`; Übernahmezeitraum `takeover_from/to`;
  Vorverwalterdaten), `Unit` (Einheiten je Objekt).
- `apps.parties`: `Owner`, vermutlich `Tenant` (gleiche Basis `PartyBase`), `OwnerUnitAssignment`
  (zeitlich gültige Eigentums-/Mietzuordnung, Ergänzung 5.6 Nr. 8/13/19). IBAN nur als
  `iban_last4` + `iban_hash` (HMAC); `iban_encrypted` bleibt leer, solange
  `security.store_full_iban` falsch ist (Beschluss B-18 in objektakte).
- `apps.documents`: `Document` (uuid, sha256, drive_md5, drive_file_id, `drive_node` FK,
  Status registered→hashed→ocr_done→classified→filed/review/duplicate/moved_out/error,
  `category`/`subfolder`/`document_type`, `duplicate_of`, `ocr_cache_key`), `DocumentCategory`,
  `DocumentSubfolder`, `DocumentType`, `RetentionPolicy` (mit Freigabe `is_approved`,
  `approved_by`).
- `apps.drive`: `DriveNode` (Baum der Sechs-Ordner-Struktur je Objekt: `drive_file_id` unique,
  `drive_parent_id`, `parent_node` FK, `node_kind`, `list_type`/`list_format`, `year` für
  Jahresordner unter Ordner 03), `DriveSyncRun` (Abgleichläufe, dry_run, Aktionen), `OAuthToken`
  (`access_token_encrypted`/`refresh_token_encrypted` über `FieldCipher(purpose="token")`,
  Redis-Lock `drive:token:refresh` beim Refresh).
- `apps.classification`: Regeln, lokales Modell und externe KI mit Maskierung (Modelldateien
  unter `DATA_DIR/models/<version>`); Modelldatei selbst enthält keine personenbezogenen Daten,
  Trainingsdaten schon.
- `apps.review`: `ReviewCase` (Stufe der Klassifikation, Kandidaten, `proposed_action`,
  Priorität, Snooze), `ReviewDecision` (before/after State, bulk-Entscheidungen).
- `apps.pipeline`: `ProcessingRun` (Lauf je Objekt: Dokumente/Seiten total/done/failed,
  KI-Kosten, Review-Fälle erzeugt), `ProcessingJob` (Celery-Queue, `idempotency_key` unique,
  Jobtypen OCR/NLP/IO, Sperre `locked_by`).
- `apps.ai`: `AiCall` (Zweck, Provider, Modell, maskierte Entitäten, Tokens, Kosten in EUR,
  Fallback-Kette).
- `apps.lists`: `ListGeneration` (Eigentümer-/Mieterlisten je Objekt, Trigger, Zeilen aktuell/
  Historie/offen, `content_hash`, abgelegt als `DriveNode`).
- `apps.audit`: `AuditEvent` (Vorher/Nachher-State, Akteur, IP), `IbanAccessLog` (jeder
  IBAN-Klartextzugriff protokolliert, Zweckbindung).
- `apps.config`: `AppSetting` (Schlüssel/Wert/Kategorie, `is_secret`), Verschlüsselungsschlüssel
  `FIELD_KEYS` je Zweck (`totp`, `token`, `iban`, `iban_hmac`) als Secrets, nicht in `app_settings`.
- `apps.accounts`: eigene `User`/`Role`-Tabelle (django-allauth vorgesehen laut M29-dms.md
  Stufe 2, OIDC-Provider "openid_connect"), unabhängig von der CRM-Benutzerverwaltung.
- `apps.requirements`, `apps.imports`, `apps.sync`, `apps.status`, `apps.ui`, `apps.reporting`:
  Vollständigkeitsprüfung, CSV/Batch-Importe (`DATA_DIR/imports/<batch_id>`), Statusseite/
  Health, HTMX-Oberfläche, Auswertungen. Vor der Detailplanung von Stufe 2 (Abschnitt 4) durch
  Lesen der jeweiligen `models.py` zu vervollständigen (in diesem Plan nicht im Detail
  aufgeführt, da ohne Modelldateien nicht sicher).

### 1.2 Speicherlayout (`DATA_DIR`, Default `/data`)
- `/data/work`: Arbeitsverzeichnis laufender Verarbeitungsschritte (OCR, Klassifikation je Job).
- `/data/transit/<object_id>/imports`: Zwischenablage von Importen je Objekt vor Übernahme
  in die Drive-Struktur.
- `/data/previews`: gerenderte Seiten-/Dokumentvorschauen (`render_previews`).
- `/data/ocr-cache` bzw. `/data/ocr_cache`: OCR-Textcache, referenziert über
  `Document.ocr_cache_key`.
- `/data/models/<version>`: lokales Klassifikationsmodell (Versionsordner).
- `/data/imports/<batch_id>`: hochgeladene Importdateien (Listen, Altbestand).
- `/data/exports/drive-sync`: Exportdateien der Drive-Abgleichläufe.
- `/data/backup`: Sicherungsstatus (`backup/status.json`).
- Die eigentlichen Dokumentoriginale liegen nicht lokal, sondern in Google Drive
  (`ablage@muellerhv.de`); `Document.drive_file_id` verweist darauf. `/data/*` ist Arbeits-
  und Cache-Fläche, keine Primärablage.

### 1.3 Verschlüsselung
- Je Zweck ein eigener Schlüssel (`FIELD_KEYS`), gelesen aus Docker Secret/Env, nie im
  Repository. `FieldCipher(purpose)` kapselt Verschlüsselung/Entschlüsselung.
- Drive-OAuth-Tokens: `access_token_encrypted`/`refresh_token_encrypted` (Schlüssel `token`).
- IBAN: HMAC-Hash (Schlüssel `iban_hmac`) plus verschlüsselter Klartext (Schlüssel `iban`),
  Klartext nur wenn `security.store_full_iban` aktiv; jeder Klartextzugriff wird in
  `IbanAccessLog` protokolliert.
- CRM hat mit `mhvp.core.crypto.EncryptedText` (siehe `apps/api/src/mhvp/contacts/models.py`)
  bereits ein äquivalentes Verschlüsselungskonzept; Schlüsselübergabe ist unter Risiken
  (Abschnitt 5) gesondert zu behandeln.

## 2. Funktionszuordnung zu CRM-Modulen

| objektakte-Funktion | Zielmodul im CRM | Status |
|---|---|---|
| Dokument, Kategorie/Subordner/Typ, Retention | `mhvp.documents` (M6: `Document`, `DocumentCategory`, `RetentionPolicy`) | vorhanden, Felder ergänzen (sha256/drive_md5 bereits ähnlich in M6 laut `document_mirror`; `duplicate_of`, `ocr_cache_key`, Statuswerte `hashed`/`classified`/`moved_out` neu prüfen) |
| Google-Drive-Sechs-Ordner-Struktur, `DriveNode`-Baum, OAuth-Token | `mhvp.documents.dms.GoogleDriveStore` (M6) | vorhanden als Mirror-Client; Baummodell `DriveNode` mit Positions- und Statuslogik (`position_key`, `NodeStatus`) fehlt und ist neu (`mhvp.documents` erweitern oder neues Untermodul `mhvp.documents.drive_tree`) |
| OCR, Vorschauen | `mhvp.documents` + Paperless-Mirror (M6: „scans/Bilder sind pending für OCR (Paperless)“) | teilweise vorhanden über Paperless; objektakte-eigene OCR-Pipeline (Worker-OCR, `/data/ocr-cache`) wird nicht übernommen, stattdessen bestehender Paperless-Weg genutzt; Altbestand mit vorhandenem OCR-Text wird als Text importiert (kein Neu-OCR nötig) |
| Dreistufige Klassifikation (Regeln, lokales Modell, externe KI mit Maskierung) | neu, `mhvp.ai` (M7) als viertes/erweitertes AI-Purpose `classify_document`, orchestriert aus `mhvp.documents` | neu; lokales Modell (`/data/models`) entweder als eigener Klassifikationsservice weiterbetrieben (Aufruf über `mhvp.ai.providers`) oder stufenweise durch KI-Gateway-Regeln ersetzt (Betreiberentscheidung, siehe Risiken) |
| Review Center (`ReviewCase`/`ReviewDecision`) | neu, `mhvp.documents.review` (Erweiterung M6) oder eigenes Untermodul `mhvp.review` | neu; kein Äquivalent im CRM vorhanden |
| Verarbeitungsläufe/Jobs (`ProcessingRun`/`ProcessingJob`) | `mhvp.worker`/Celery-Task-Infrastruktur des CRM (bereits vorhanden für M6-Mirror-Jobs) | Infrastruktur vorhanden, neue Jobtypen ergänzen |
| Eigentümer-/Mieterlisten (`ListGeneration`) | `mhvp.properties` (Eigentümerliste je `Property`/`Unit`) + `mhvp.documents` (Ablage der generierten Liste als Dokument) | teilweise vorhanden (Stammdaten in `properties.PropertyOwner`), Listengenerierung neu |
| Eigentümer/Mieter Stammdaten, Zuordnungen | `mhvp.contacts` (M3) + `mhvp.properties` (`PropertyOwner`, M4) | vorhanden, Zusammenführung nötig (Abschnitt 3) |
| Vollständigkeitsprüfung, Nachforderungsschreiben | `mhvp.documents` (Prüfregeln neu) + `mhvp.documents.letters` (Vorlage, M6 vorhanden) | Briefvorlage-Mechanik vorhanden, Prüfregeln neu |
| KI-Aufruf-Protokoll (`AiCall`) | `mhvp.ai` (M7, vorhandenes Kosten-/Tokenmodell) | vorhanden, Zweck ergänzen |
| Benutzer/Rollen | CRM-Benutzerverwaltung (bestehende OIDC/Rollenmatrix, `docs/plans/M2.md`) | vorhanden; eigene objektakte-`User`/`Role`-Tabelle entfällt, Benutzer wandern in CRM-Rollen (neue Berechtigungsschlüssel `documents:review`, `documents:classify` o. ä.) |
| Audit (`AuditEvent`, `IbanAccessLog`) | CRM-Audit-Infrastruktur (vorhanden, siehe MASTER-PROMPT 0.1.7/13) | vorhanden, Herkunft „objektakte“ als `source`-Kennzeichen übernehmen |
| Mail-Vorbereitung Objektbeschränkung (M34/M20-05) | `mhvp.communication` (M20) | bereits auf CRM-Dokumente umzustellen, sobald Dokumente im CRM liegen (Ablösung von `mhvp.documents.dms.GoogleDriveStore.search`-Workaround durch native Suche) |
| SSO (django-allauth, OIDC) | entfällt | mit Abschaltung von objektakte hinfällig |

## 3. Datenmigration

### 3.1 MariaDB → PostgreSQL
- Einmaliger `mysqldump`/`mydumper`-Export der objektakte-Datenbank, Ziel: Staging-Schema
  `objektakte_import` in der CRM-PostgreSQL-Instanz (nicht direkt in Produktivtabellen).
- Migrationsskript (Python, außerhalb dieses Repositories bis M35 zur Umsetzung freigegeben
  ist) liest je Zieltabelle aus dem Staging-Schema und schreibt idempotent in die
  CRM-Tabellen mit einer Herkunftsspalte `source_system='objektakte'` und
  `source_id=<objektakte PK>` (unique zusammen mit `tenant_id`), damit wiederholte Läufe
  (Testlauf, Korrekturlauf, Differenzimport bis zum Umschalttermin) keine Duplikate erzeugen
  (Muster wie bestehender M8-Import laut `docs/plans/M29-dms.md` Stufe 4).
- Reihenfolge wegen Fremdschlüsseln: `objects.ManagedObject`→`properties.Property`
  (Schlüssel `object_number`), `objects.Unit`→`properties.Unit`, `parties.Owner`/`Tenant`→
  `contacts` + `properties.PropertyOwner`, `documents.DocumentCategory/Type`→
  `mhvp.documents.DocumentCategory` (Abgleich mit bereits gepflegten CRM-Kategorien, keine
  Dubletten), `drive.DriveNode`→neues Baum-Modell, `documents.Document`→`mhvp.documents.Document`
  (mit `drive_file_id`, `sha256` als Abgleichschlüssel zu ggf. bereits über M6-Mirror
  vorhandenen Dokumenten), `review.ReviewCase/Decision`, `ai.AiCall`, `lists.ListGeneration`,
  `audit.AuditEvent/IbanAccessLog` (historisch, read-only Übernahme).
- IBAN-Übernahme: `iban_hash`/`iban_last4` unverändert kopieren; `iban_encrypted` nur
  entschlüsseln und mit dem CRM-eigenen Schlüssel neu verschlüsseln, wenn beide Schlüssel
  (objektakte `iban`, CRM `EncryptedText`-Schlüssel) im selben, durch die Geschäftsführung
  freigegebenen Migrationslauf verfügbar sind (Vier-Augen, kein Klartext in Logs oder
  Zwischendateien, siehe Risiken).

### 3.2 Dateien
- Dokumentoriginale: nicht aus `/data/*` kopieren, sondern `drive_file_id` unverändert in
  `mhvp.documents.Document.drive_file_id` übernehmen; das CRM greift wie objektakte per
  Drive-API auf dieselbe Ablage (`ablage@muellerhv.de`) zu. Kein doppeltes Vorhalten der
  Originale.
- Vorschaubilder (`/data/previews`): entweder mitkopieren in den CRM-Objektspeicher (S3,
  `tenants/<tenant>/documents/<id>/preview`) oder aus dem Dokument neu gerendert (abhängig von
  Volumen/Zeitbudget, Stufe 3 unten).
- OCR-Text (`/data/ocr-cache`): Text mitkopieren in `mhvp.documents` Volltextindex
  (`tsvector`), damit die Suche ohne Neu-OCR sofort funktioniert; kein Neu-OCR für die
  ca. 26.000 Bestandsdokumente nötig.
- Lokales Klassifikationsmodell (`/data/models`): Weiterverwendung nur, wenn ein Übernahmepfad
  in `mhvp.ai.providers` entsteht (siehe Abschnitt 2); sonst Neuklassifikation über
  KI-Gateway/Regeln bei erstmaligem Zugriff, historische Klassifikation bleibt als Feld
  erhalten.

## 4. Stufenplan (4 bis 6 Stufen)

**Stufe 1: Datenmodell und Migrationsgerüst**
- Neue Alembic-Migration: Herkunftsspalten (`source_system`, `source_id`) auf
  `mhvp.documents.Document`, `mhvp.properties.Property/Unit`, `mhvp.contacts` (wo fehlend);
  neues Baum-Modell für `DriveNode`-Äquivalent; neue Tabellen `document_review_case`,
  `document_review_decision`, `document_classification_run` (oder Erweiterung bestehender
  Job-Infrastruktur).
- Migrationsskript (Staging-Schema-Reader) für Stammdaten (Objekte, Einheiten, Eigentümer,
  Mieter, Zuordnungen) mit Testlauf gegen eine Kopie der objektakte-Datenbank.
- Akzeptanz: Testlauf importiert alle 67 Objekte/869 Einheiten fehlerfrei, wiederholter
  Lauf erzeugt keine Duplikate (idempotent geprüft), Abgleichsbericht (Zeilen je Tabelle,
  Abweichungen) liegt vor.

**Ergebnis Stufe 1 (25.09.2026)**

- Neues Modul `mhvp.objektakte` (`apps/api/src/mhvp/objektakte/{models,objektakte_import,
  routers}.py`, README dort): Baum-Modell `objektakte_drive_node` (Mirror von objektakte
  `drive_nodes`, `property_id` nullable), minimaler Mirror `objektakte_document_review_case`/
  `_decision` (Startbestand für die spätere Review-Center-Oberfläche, Stufe 3), Staging-Tabelle
  `objektakte_party_assignment` für `parties.OwnerUnitAssignment`-Zeilen ohne passendes
  CRM-Zielmodell auf Einheitenebene (Owner- wie Tenant-Zuordnung).
- Herkunftsspalten `source_system`/`source_id` (unique je Mandant, partieller Index) auf
  `mhvp.documents.models.Document`, `mhvp.properties.models.Property`,
  `mhvp.properties.models.Unit`, `mhvp.contacts.models.Contact`. Migration `0058_objektakte_
  takeover` (down_revision `0057`, einziger Head danach, geprüft mit `alembic heads`).
- Importer `mhvp.objektakte.objektakte_import` (Stammdaten: `objects_managedobject` →
  `Property`, `objects_unit` → `Unit`, `parties_owner`/`parties_tenant` → `Contact`,
  `parties_ownerunitassignment` → `objektakte_party_assignment`); nutzt den aus
  `mhvp.handover.uprotokoll_import` herausgezogenen, geteilten Dump-Parser
  `mhvp.core.sqldump` (U-Protokoll-Import läuft unverändert über denselben Parser, Tests
  weiterhin grün). Endpunkte `/api/v1/objektakte/imports` (`mode=preview|apply`) und
  `/api/v1/objektakte/imports/{id}`, Rechte `documents:read`/`documents:create`.
- Abweichungen von der obigen Skizze, mit Begründung: keine eigene Tabelle
  `document_classification_run` (Stufe 3 entscheidet über Form der Klassifikationsläufe,
  vermeidet Felder "auf Vorrat", rule 0.1.4.2); `Property.number` ist auf genau drei Ziffern
  beschränkt (6.9.1 `number_format`), ein objektakte `object_number` außerhalb 1..999 wird
  daher nicht automatisch zu einer `Property` und als `unmatched_properties` gemeldet statt
  abgeschnitten oder neu vergeben; `mhvp.properties.models.Unit.building_id` ist
  Pflichtfeld, objektakte kennt keine Gebäudeebene, deshalb legt der Importer je
  übernommenem Objekt ein Platzhaltergebäude an; IBAN wird in Stufe 1 gar nicht in eine
  `ContactBankAccount` übernommen (die verlangt eine vollständige, CRM-seitig
  verschlüsselte IBAN, die aus objektakte ohne separaten, freigegebenen
  Entschlüsselungsschritt nicht verfügbar ist) — siehe `docs/rules/M35-01.md`.
- Tests: `apps/api/tests/unit/test_m35_objektakte_import.py` (Parser-Mapping, Objektnummer-
  Normalisierung, Anzeigename), `apps/api/tests/integration/test_m35_objektakte_import.py`
  (Preview-Zählung, idempotente Übernahme, Rechteprüfung, Mandantentrennung über RLS),
  `apps/api/tests/integration/test_migrations.py` (kein Autogenerate-Drift durch diese
  Migration, Auf-/Abstieg), `apps/api/tests/unit/test_m30_uprotokoll_import.py` weiterhin
  grün nach dem Parser-Refactoring.
- Offene Punkte für Stufe 2/3: Dokumentenmigration selbst, Klassifikationsregeln,
  Review-Center-Oberfläche, Auflösung der Staging-Tabelle `objektakte_party_assignment` auf
  ein endgültiges Vertragsmodell, etwaige IBAN-Neuverschlüsselung (nur mit ausdrücklicher
  Freigabe der Geschäftsführung, Vier-Augen).

**Stufe 2: Dokumentenmigration (Metadaten, OCR-Text, Vorschauen)**
- Import aller ca. 26.000 `Document`-Zeilen inkl. `drive_file_id`, `sha256`, Kategorie/
  Subordner/Typ-Zuordnung, OCR-Text in den Volltextindex; Vorschaubilder kopieren oder Regel
  für Neu-Rendern festlegen.
- Dublettenabgleich gegen bereits über M6-Mirror vorhandene Paperless-/Drive-Dokumente
  (Schlüssel `sha256`/`drive_file_id`).
- Akzeptanz: Stichprobe von 50 Dokumenten je Kategorie im CRM auffindbar, Volltextsuche
  liefert dieselben Treffer wie objektakte, Vorschau öffnet, Drive-Link funktioniert.

**Ergebnis Stufe 2 (25.09.2026)**

- Importer erweitert (`mhvp.objektakte.objektakte_import`) um `documents_documentcategory` →
  `mhvp.documents.models.DocumentCategory` (Treffer über `source_id`, sonst Name, sonst neu),
  `documents_documentsubfolder`/`documents_documenttype` → neue Tabelle
  `objektakte_document_class` (die flache CRM-Kategorie kann die zweite Ebene nicht halten),
  `drive_drivenode` → Stufe-1-Baum `objektakte_drive_node` (jetzt gefüllt, Elternverknüpfung
  in einem zweiten Durchlauf, da ein Kind vor seinem Elternknoten im Dump stehen kann),
  `documents_document` → `mhvp.documents.models.Document` und `review_reviewcase`/
  `review_reviewdecision` → die Stufe-1-Tabellen `objektakte_document_review_case`/`_decision`.
- Kein Binärkopieren: `storage = google_drive`, `storage_ref` ist die objektakte
  Drive-Datei-ID unverändert, exakt die Konvention, die `mhvp.documents.dms.GoogleDriveStore.
  put`/`resolve` für ein gespiegeltes Dokument ohnehin schon verwenden. Der Downloadpfad
  (`GET /api/v1/documents/{id}/content`) wurde um genau diesen Fall erweitert
  (`mhvp.documents.services.download_from_drive`, neue `GoogleDriveStore.download`), sodass
  ein migriertes Dokument über die eingerichtete Drive-Anbindung abrufbar ist, ohne dass ein
  Original je lokal abgelegt wird.
- OCR-Text: neuer Endpunkt `POST /api/v1/objektakte/imports/{id}/ocr-cache` (ZIP-Upload des
  objektakte `/data/ocr-cache`-Verzeichnisses), Abgleich über `source_meta["ocr_cache_key"]`,
  setzt `ocr_text`/`text_status = extracted`. Bis zum Hochladen des Caches steht ein
  Dokument mit erkanntem Text in objektakte im CRM auf `text_status = pending`, nie
  vorzeitig auf `extracted`.
- Idempotenz über eine Zeilenprüfsumme (`source_meta["row_hash"]`, sha256 der sortierten
  JSON-Repräsentation der Dump-Zeile): ein zweiter Apply mit unverändertem Dump ändert nichts,
  eine geänderte Zeile wird aktualisiert (`updated`-Zähler im Ergebnis), nie stillschweigend
  übersprungen.
- Migration `0060_objektakte_documents` (down_revision `0058`... `0059`, einziger Head danach,
  mit `alembic heads` geprüft): `document.duplicate_of_id` (Selbstverweis, `SET NULL`),
  `document.source_meta` (JSONB), `document_category.source_system`/`source_id` (gleiches
  Muster wie Stufe 1) und die neue Tabelle `objektakte_document_class`.
- Abweichungen von der obigen Skizze, mit Begründung: kein Dublettenabgleich gegen bereits
  über M6-Mirror vorhandene Paperless-/Drive-Dokumente (die produktive M6-Dokumentbasis dieses
  Mandanten ist zum jetzigen Zeitpunkt praktisch leer; ein `sha256`/`drive_file_id`-Abgleich
  bleibt ein Stufe-5-Thema, sobald der Parallelbetrieb beide Bestände tatsächlich
  überschneidet); keine Vorschaubilder (das CRM rendert für keinen Dokumenttyp, auch nicht
  für hochgeladene Dokumente, überhaupt eine eigene Vorschau; ein Vorschau-Pfad ist unabhängig
  vom objektakte-Bestand offen, M35-02); `sha256` ist auf `Document` Pflicht, eine
  objektakte-Zeile ohne Hash (Status `registered`) bekommt einen deterministischen
  Platzhalter, markiert `source_meta["sha256_placeholder"] = true`, nie einen erfundenen
  Inhaltshash; `decided_by` auf der übernommenen `ReviewDecision` bleibt unbesetzt
  (objektakte-Benutzer-IDs werden erst in Stufe 4 auf CRM-Nutzer abgebildet).
- Tests: `apps/api/tests/unit/test_m35_objektakte_import.py` (Dump-Parsing der neuen Tabellen,
  Zeilenprüfsumme stabil/ändert sich, Textstatus-Zuordnung), `apps/api/tests/integration/
  test_m35_objektakte_import.py` (Vorschau-Zähler für Dokumente/Review-Fälle, idempotenter
  Apply mit anschließendem Update bei geänderter Zeile, OCR-Cache-ZIP mit Treffer- und
  Fehltrefferzählung, Download eines migrierten Dokuments über den bestehenden
  Downloadpfad mit einem simulierten Drive-Store), `apps/api/tests/integration/
  test_m6_documents.py` (M6 unverändert grün nach den Downloadpfad-/Modelländerungen),
  `apps/api/tests/integration/test_migrations.py` (kein durch diese Migration verursachter
  Autogenerate-Drift; ein bei diesem Lauf bereits vorhandener Drift aus anderen, parallel
  laufenden Arbeiten an Banking/SLA-Modulen betrifft keine dieser Tabellen/Spalten).
- Offene Punkte für Stufe 3/4/5: Klassifikationsregeln, Review-Center-Oberfläche, Auflösung
  der Staging-Tabelle `objektakte_party_assignment`, Vorschaubilder (M35-02), Dublettenabgleich
  gegen den M6-Bestand sobald beide Systeme parallel laufen, etwaige IBAN-Neuverschlüsselung.

**Stufe 3: Klassifikation, Review Center, Vollständigkeitsprüfung**
- Neubau Review-Center-Oberfläche und -API im CRM (`ReviewCase`/`ReviewDecision`-Äquivalent),
  Übernahme aller offenen Fälle aus objektakte als Startbestand.
- Klassifikationsregeln (Stufe 1 des dreistufigen Verfahrens) als Regelwerk im CRM neu
  hinterlegt (`docs/rules/M35-classification.md`); Stufe 2 (lokales Modell) und Stufe 3
  (externe KI mit Maskierung) über `mhvp.ai` angebunden oder vorerst nur Regeln plus manuelle
  Prüfung (Betreiberentscheidung, siehe offene Punkte).
- Vollständigkeitsprüfung und Nachforderungsschreiben als Regelwerk plus Brief-Vorlage (M6
  Letters) neu gebaut.
- Akzeptanz: alle offenen Review-Fälle aus objektakte im CRM sichtbar und bearbeitbar,
  ein Testlauf Vollständigkeitsprüfung für ein Testobjekt liefert dieselben fehlenden
  Unterlagen wie objektakte, ein Nachforderungsschreiben lässt sich aus dem CRM erzeugen.

**Stufe 4: Eigentümer-/Mieterlisten, KI-Protokoll, Benutzer/Rollen**
- Listengenerierung (`ListGeneration`-Äquivalent) im CRM, Ablage der erzeugten Liste als
  Dokument mit Verknüpfung zu `Property`.
- `AiCall`-Historie importiert (read-only, für Kostenauswertung), neue KI-Aufrufe laufen
  über `mhvp.ai`.
- Benutzer der objektakte-Anmeldung auf CRM-Rollen abgebildet (keine eigene Benutzertabelle
  mehr), neue Berechtigungsschlüssel für Review/Klassifikation angelegt.
- Akzeptanz: Eigentümerliste für ein Testobjekt aus dem CRM erzeugt und mit der letzten
  objektakte-Liste inhaltlich abgeglichen (gleiche Zeilenzahl); alle bisherigen
  objektakte-Benutzer können sich im CRM mit passenden Rechten anmelden.

**Stufe 5: Paralleler Betrieb und Produktivabgleich**
- Beide Systeme laufen parallel (objektakte read-only oder nur für laufende
  Übernahme-Altfälle beschreibbar, CRM führend für Neuzugänge), Zeitfenster mindestens
  zwei bis vier Wochen für den laufenden Geschäftsbetrieb (Postfachverarbeitung M20,
  Vollständigkeitsprüfung, Reviews).
- Täglicher Differenzimport (nur neue/geänderte Zeilen seit letztem Lauf, über
  `updated_at`/Herkunfts-ID) hält das CRM aktuell, bis Umschalttermin feststeht.
- Akzeptanz: an mindestens fünf aufeinanderfolgenden Werktagen keine ungeklärte Differenz
  zwischen objektakte- und CRM-Dokumentenzahl je Objekt; alle während des Fensters neu
  angelegten Dokumente sind im CRM vorhanden.

**Stufe 6: Umschaltung und Abschaltung objektakte**
- Letzter Differenzimport, Sperrung von objektakte (read-only), finale Prüfsumme
  (Dokumentanzahl, Summe `size_bytes`, Anzahl offener Review-Fälle) zwischen beiden Systemen.
- DNS/Link-Umstellung: DMS-Reiter im CRM zeigt nur noch auf CRM-Dokumente, kein Absprung
  mehr nach `uebernahme.muellerhv.de`.
- objektakte-Container-Stack stoppen, Datenbank und `/data`-Volumes als Archiv sichern
  (Aufbewahrungspflicht der Dokumente, Regel 0.1.7), danach Abschaltung.
- Akzeptanz: CRM ist alleinige Quelle für Dokumente, Reviews, Listen; objektakte-Stack
  gestoppt; Archivsicherung geprüft (Rücksicherbarkeit stichprobenartig getestet).

**Ergebnis Stufe 3, Teil 1 und 3 (25.09.2026)**

- Regelstufe (Stufe 1 von drei) neu: `mhvp.objektakte.models.ObjektakteClassificationRule`
  (Muster `filename_regex`/`text_keyword`/`sender_domain`/`drive_folder`, Zielkategorie,
  `target_document_type`, Priorität, `active`, `confidence`), Service
  `mhvp.objektakte.classification.classify_document` (alle aktiven Regeln je Mandant nach
  Priorität, beste Kandidatin gegen `TenantSettings.objektakte_classification
  .auto_apply_threshold`, Standard `0.85`); oberhalb der Schwelle nur ein Vorschlag in
  `document.source_meta["classification"]` (nie `document.category_id`, rule 0.1.6),
  unterhalb ein offener `DocumentReviewCase` (`stage="rules"`). Regelsemantik und die zwei
  seedbaren Referenzregeln in `docs/rules/M35-02.md` (von 202 Referenzregeln in
  `/home/user/v3ni94/objektakte/src/apps/classification/rules.py` bzw.
  `db/seeds/rules/regeln.json` erfüllen nur zwei ausschließlich die vier hier
  unterstützten, einfachen Bedingungsarten; die übrigen mit Entitäten-, Ordner- oder
  Konfliktbedingungen sind nicht Teil dieser Stufe, siehe die Datei für die Begründung).
  Migration `0064_objektakte_classification_rules` (down_revision `0063`).
- Review-Center (Teil 3) neu: `/api/v1/objektakte/review` (`mhvp.objektakte.review_routers`)
  mit Liste (Filter Status, Objekt über `DocumentLink`, Mindestpriorität, Stufe), Einzelabruf
  mit Kandidaten und Dokument-Vorschaulink (`/api/v1/documents/{id}/content`), Entscheidung
  (`accept_candidate`, `set_manually`, `reject`, `snooze`) und Sammelentscheidung
  (`bulk-decide`, eine Zielklasse für mehrere Fälle). Jede Entscheidung schreibt eine
  `objektakte_document_review_decision`-Zeile mit Vorher-/Nachher-Zustand und `decided_by`
  (bestehende Stufe-1-Tabelle, jetzt erstmals beschrieben statt nur importiert). Rechte:
  `documents:read` (Liste/Abruf), `documents:update` (Entscheiden), wie in
  `mhvp.documents.routers`.
- Stufe 2 (lokales Modell) bleibt außerhalb des Umfangs (M35-01 offen, siehe dort). Die
  KI-Stufe (Auftragsteil 2), die Vollständigkeitsprüfung (Teil 4) und die CRM-Oberfläche
  (Teil 5) sind eigene, noch nicht begonnene Teilaufträge.
- Tests: `apps/api/tests/unit/test_m35_classification_rules.py` (Musterabgleich, kein
  DB-Zugriff), `apps/api/tests/integration/test_m35_classification_rules.py` (Schwelle vs.
  Review-Fall, Mandantentrennung), `apps/api/tests/integration/test_m35_review_center.py`
  (Filter, Abruf, Entscheiden inkl. Autorisierung `documents:read` vs. `documents:update`,
  Sammelentscheidung, Audit-Zeile, Mandantentrennung).
- Offene Punkte: ob die restlichen 200 Referenzregeln in einem erweiterten Regelschema
  übernommen werden, ist eine Betreiberentscheidung (`docs/OPEN_QUESTIONS.md`); kein Feld
  dieser Stufe füllt derzeit `sender_domain`/`drive_folder` automatisch (kein Mail- oder
  Drive-Sync-Modul schreibt diese `source_meta`-Schlüssel), sie sind erst nutzbar, sobald ein
  solches Modul sie befüllt.

**Ergebnis Stufe 3, Teil 2, 4 und 5 (25.09.2026)**

- KI-Stufe (Teil 2, Stufe 3 von drei): neuer AI-Task `classify_document`
  (`mhvp.ai.models.AiTask.CLASSIFY_DOCUMENT`, Migration `0070_objektakte_ai_classification`,
  `ALTER TYPE ai_task ADD VALUE`), Prompt `mhvp.ai.prompts.classify_document.v1`, Schema
  `ClassifyDocumentResult` (`document_class`, `category`, `confidence`, `reasons`) in
  `mhvp.ai.tasks`. Maskierung vor jedem Versand: `mhvp.objektakte.masking.mask_text` (kein
  vorhandener Masker gefunden) ersetzt IBAN, E-Mail, deutsche Telefonnummern und
  wahrscheinliche Personennamen durch feste Platzhalter; der `AiTaskRun` trägt den bereits
  maskierten Text als `input_ref["instruction"]` und `document_ids=[]`, sodass der generische
  Gateway-Pfad nie erneut den unmaskierten Dokumenttext liest. Endpunkt
  `POST /api/v1/objektakte/review/{case_id}/ask-ai` (`documents:update`): Ergebnis immer ein
  Vorschlag (`document.source_meta["classification"]["stage"]="ai"`,
  `case.candidates["ai"]`), nie automatisch angewandt (rule 0.1.6). Details und die
  Maskierungsregeln in `docs/rules/M35-02.md` (Ergänzung).
- Vollständigkeitsprüfung (Teil 4): neue Tabelle `objektakte_required_document` (Mandant,
  `management_type` — bewusst das bestehende `mhvp.properties.models.ManagementType`
  wiederverwendet, keine eigene "weg"/"rental"-Vokabular, siehe Modell-Docstring —,
  Dokumentkategorie, `mandatory`), Migration `0073_objektakte_required_document`. Endpunkte
  `/api/v1/objektakte/required-documents` (Einstellungen, Liste/Anlegen/Löschen),
  `GET /api/v1/objektakte/properties/{id}/completeness` (fehlende/erfüllte Kategorien, prüft
  nur Vorhandensein eines verknüpften Dokuments der Kategorie, keine Aktualität oder Inhalt)
  und `POST .../completeness/nachforderungsschreiben` (deutscher Textentwurf, klar als
  "ENTWURF" markiert, nie automatisch versendet, Auftragsteil erlaubt diesen einfacheren
  Textweg ausdrücklich als Alternative zur Briefvorlagen-Mechanik).
- Regel-CRUD (Grundlage für Teil 5): `/api/v1/objektakte/classification-rules` (Liste,
  Anlegen, Ändern/Aktivieren, Löschen), da Teil 1 nur den Lesepfad (`classify_document`)
  gebaut hatte, aber keine Verwaltungsoberfläche brauchte.
- CRM-Oberfläche (Teil 5, `apps/web-crm`): Menüpunkt "Objektakte" (`app/(app)/layout.tsx`,
  additiv, Berechtigung `documents:read`), Review-Center-Seite
  (`app/(app)/objektakte/page.tsx` + `components/objektakte/ReviewCenter.tsx`: Filter,
  Kandidaten, "KI fragen", Dokumentlink, Sammelentscheidung), Regeln-Einstellungsseite
  (`app/(app)/einstellungen/objektakte/page.tsx` + `components/objektakte/RulesSettings.tsx`:
  Liste, Anlegen, Bearbeiten, Aktivieren/Deaktivieren) und eine additive
  Vollständigkeits-Karte auf der Objektseite (`components/objektakte/CompletenessPanel.tsx`,
  eingefügt nach dem bestehenden DMS-Panel). BFF-Allowlist ergänzt
  (`app/api/bff/[...path]/route.ts`), deutsche Texte in `messages/de.json`/`en.json` unter dem
  neuen Namensraum `Objektakte` sowie `Shell.objektakte`/`Settings.objektakte`.
- Tests: `apps/api/tests/unit/test_m35_masking.py`,
  `apps/api/tests/integration/test_m35_ai_classification.py` (Fake-Provider, prüft
  ausdrücklich, dass keine IBAN, E-Mail oder Name den simulierten Aufruf erreicht),
  `apps/api/tests/integration/test_m35_completeness.py`,
  `apps/api/tests/integration/test_m35_rules_crud.py`; im Frontend
  `components/objektakte/ReviewCenter.test.tsx` (Kandidat übernehmen, Sammelentscheidung) und
  `components/objektakte/RulesSettings.test.tsx` (Regel anlegen, deaktivieren). Alle
  bestehenden Vitest-Suiten (304 Tests) und `tsc`/`eslint` weiterhin grün.
- Offene Punkte: die Namensheuristik der Maskierung ist kein NER-Modell (Übermaskierung
  bewusst in Kauf genommen, siehe `docs/rules/M35-02.md`); die Vollständigkeitsprüfung prüft
  nur Vorhandensein, keine Aktualität; kein Seeding der zwei referenzierten Klassifikations-
  regeln in eine Mandanten-Instanz (nur als Spezifikation dokumentiert).

## 5. Risiken

- **OCR-Last auf dem CRM-Worker**: objektakte hat dedizierte OCR-Worker (`worker-ocr`).
  Migration übernimmt vorhandenen OCR-Text (kein Neu-OCR nötig für Altbestand), aber
  laufende Neuzugänge müssen entweder über Paperless (bereits vorhanden, M6) oder einen
  neuen OCR-Pfad im CRM-Worker laufen; Kapazitätsprüfung vor Stufe 3 nötig.
- **Schlüsselübergabe Verschlüsselung**: objektakte-Schlüssel (`iban`, `iban_hmac`, `token`)
  müssen für die Umschlüsselung kurzzeitig neben den CRM-Schlüsseln vorliegen; strikt nur im
  Migrationslauf, nicht dauerhaft, mit Vier-Augen-Prinzip und Löschung danach.
- **Laufende Übernahmefälle während der Migration**: Objekte mit offenem
  `takeover_from/to`-Zeitraum und offenen Review-Fällen dürfen nicht zwischen den Systemen
  „verloren" gehen; Differenzimport (Stufe 5) muss diese Fälle als beschreibbar in
  objektakte belassen, bis das CRM den Fall vollständig übernommen hat.
- **Drive-Kontingent**: Beide Systeme greifen während des Parallelbetriebs auf dieselbe
  Drive-API (`ablage@muellerhv.de`) zu; Kontingentverbrauch verdoppelt sich zeitweise
  (Sync-Läufe beider Systeme), Google-API-Quota vorab prüfen.
- **Klassifikationsqualität**: das lokale Modell (`/data/models`) enthält gelernte
  Trainingsdaten, deren Übernahme in das CRM (Format, Bibliotheksversion) nicht geprüft ist;
  im Zweifel Neustart mit Regeln plus manueller Prüfung, bis ein neues Modell im CRM
  trainiert ist.
- **Vorschaubilder-Volumen**: ca. 26.000 Dokumente mit Vorschauen können mehrere zehn GB
  Kopiervolumen bedeuten; Entscheidung Kopieren vs. Neu-Rendern beeinflusst Stufe 2 Dauer
  erheblich.

## 6. Aufwandsschätzung (Agentenarbeitssitzungen)

| Stufe | Sitzungen (grobe Schätzung) |
|---|---|
| 1 Datenmodell und Migrationsgerüst | 4 bis 6 |
| 2 Dokumentenmigration | 5 bis 8 |
| 3 Klassifikation, Review, Vollständigkeitsprüfung | 8 bis 12 |
| 4 Listen, KI-Protokoll, Benutzer/Rollen | 4 bis 6 |
| 5 Paralleler Betrieb und Abgleich | 3 bis 5 (davon viel Wartezeit/Beobachtung, wenig Agentenzeit) |
| 6 Umschaltung und Abschaltung | 2 bis 3 |
| **Summe** | **26 bis 40 Sitzungen**, ohne die in Abschnitt 7 genannten Betreiberentscheidungen, die vorab zu klären sind |

Schätzung ohne Gewähr; abhängig von noch ungelesenen Detailmodellen
(`apps.requirements`, `apps.imports`, `apps.sync`, `apps.status`, `apps.ui`, `apps.reporting`),
die vor Stufe 1 vollständig zu inventarisieren sind.

## 7. Offene Entscheidungen für den Betreiber

Siehe `docs/OPEN_QUESTIONS.md`, Punkte M35-01 bis M35-07.
