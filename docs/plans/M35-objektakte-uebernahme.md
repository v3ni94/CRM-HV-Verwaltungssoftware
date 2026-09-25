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

**Stufe 2: Dokumentenmigration (Metadaten, OCR-Text, Vorschauen)**
- Import aller ca. 26.000 `Document`-Zeilen inkl. `drive_file_id`, `sha256`, Kategorie/
  Subordner/Typ-Zuordnung, OCR-Text in den Volltextindex; Vorschaubilder kopieren oder Regel
  für Neu-Rendern festlegen.
- Dublettenabgleich gegen bereits über M6-Mirror vorhandene Paperless-/Drive-Dokumente
  (Schlüssel `sha256`/`drive_file_id`).
- Akzeptanz: Stichprobe von 50 Dokumenten je Kategorie im CRM auffindbar, Volltextsuche
  liefert dieselben Treffer wie objektakte, Vorschau öffnet, Drive-Link funktioniert.

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
