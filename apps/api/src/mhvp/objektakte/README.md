# objektakte

M35 Stufe 1 (Datenmodell und Migrationsgerüst), Stufe 2 (Dokumentenmigration, Metadaten,
OCR-Text, Review-Startbestand) und Stufe 3 Teil 1+3 (Regelklassifikation, Review-Center) der
Übernahme der Anwendung objektakte (Django/MariaDB) in dieses CRM. Plan:
`docs/plans/M35-objektakte-uebernahme.md`, Regeln: `docs/rules/M35-01.md` (Stufe 1),
`docs/rules/M35-02.md` (Klassifikation Stufe 1 von drei). Die KI-Klassifikationsstufe
(Auftragsteil 2), die Vollständigkeitsprüfung (Teil 4) und die CRM-Oberfläche (Teil 5) sind
eigene, noch nicht begonnene Teilaufträge.

| Datei (Stufe 3) | Inhalt |
| --- | --- |
| `classification.py` | `classify_document(session, tenant_id, document)`: Regelstufe (Stufe 1 von drei) — wertet `objektakte_classification_rule` je Mandant aus, sammelt jeden Treffer als Kandidat mit Score; oberhalb der Mandantenschwelle nur ein Vorschlag in `document.source_meta["classification"]` (nie `document.category_id`, rule 0.1.6), sonst ein offener `DocumentReviewCase` |
| `review_routers.py` | `/api/v1/objektakte/review` (Liste mit Filtern, Abruf, `decide`, `bulk-decide`), Rechte `documents:read`/`documents:update` |
| `models.py` (Ergänzung) | `ObjektakteClassificationRule` (Muster, Ziel, Priorität, `confidence`), `ClassificationPatternType` |

| Datei | Inhalt |
| --- | --- |
| `models.py` | `objektakte_drive_node` (Google-Drive-Baum je Objekt, ab Stufe 2 durch den Importer gefüllt), `objektakte_document_review_case`/`_decision` (minimaler Mirror von `review_cases`/`review_decisions`, Startbestand für die spätere Review-Center-Oberfläche), `objektakte_party_assignment` (Staging-Tabelle für `parties.OwnerUnitAssignment`-Zeilen ohne passendes CRM-Zielmodell), `objektakte_document_class` (Stufe 2, neu: objektakte `documents_documentsubfolder`/`documents_documenttype`, da die flache CRM-Kategorie das nicht abbildet) |
| `objektakte_import.py` | Mapping der objektakte-Tabellen `objects_managedobject`, `objects_unit`, `parties_owner`, `parties_tenant`, `parties_ownerunitassignment` (Stufe 1) sowie `documents_documentcategory`, `documents_documentsubfolder`, `documents_documenttype`, `drive_drivenode`, `documents_document`, `review_reviewcase`, `review_reviewdecision` (Stufe 2) auf `Property`, `Unit`, `Contact`, `mhvp.documents.models.{Document,DocumentCategory}`, `objektakte_drive_node`, `objektakte_document_class`, `objektakte_document_review_case`/`_decision` bzw. die Staging-Tabelle; nutzt den geteilten Dump-Parser `mhvp.core.sqldump` (auch von `mhvp.handover.uprotokoll_import` verwendet) |
| `routers.py` | `/api/v1/objektakte/imports` (`mode=preview\|apply`, SQL-Dump-Upload), `/api/v1/objektakte/imports/{id}` und (Stufe 2) `/api/v1/objektakte/imports/{id}/ocr-cache` (ZIP-Upload des objektakte `/data/ocr-cache`-Verzeichnisses) |

Herkunftsspalten `source_system`/`source_id` (eindeutig je Mandant, wenn gesetzt) wurden
Stufe 1 auf `mhvp.documents.models.Document`, `mhvp.properties.models.Property`,
`mhvp.properties.models.Unit` und `mhvp.contacts.models.Contact` ergänzt (Migration 0058); sie
sind der Idempotenzschlüssel jedes objektakte-Imports. Migration 0060 (Stufe 2) ergänzt
`document.duplicate_of_id` (Selbstverweis, ein von objektakte selbst erkanntes Duplikat),
`document.source_meta` (JSONB: objektakte-Status, Subordner-/Typname, `ocr_cache_key`, die
Zeilenprüfsumme für den idempotenten Re-Import) sowie `document_category.source_system`/
`source_id` (gleiches Muster für den Kategorie-Katalog) und die neue Tabelle
`objektakte_document_class`.

## Dokumentenmigration (Stufe 2)

- Kein Binärkopieren: `Document.storage = google_drive`, `storage_ref` ist die objektakte
  Drive-Datei-ID unverändert, exakt die gleiche Konvention wie bei einem gespiegelten
  Drive-Dokument (`mhvp.documents.dms.GoogleDriveStore.put`/`resolve` behandeln die Datei-ID
  selbst schon als Referenz). Der Download-Endpunkt
  (`GET /api/v1/documents/{id}/content`) und `mhvp.documents.services.download_from_drive`
  holen das Original über die eingerichtete Google-Drive-Anbindung, ohne dass ein Original
  jemals lokal abgelegt wird.
- `sha256` ist auf `Document` Pflicht; eine objektakte-Zeile ohne Hash (Status noch
  `registered`) bekommt einen deterministischen Platzhalter (`sha256(f"objektakte-pending:
  {source_id}")`), markiert in `source_meta["sha256_placeholder"] = true`, niemals einen
  erfundenen Inhaltshash.
- Status: objektakte-Status (`registered` … `error`) bleibt wörtlich in
  `source_meta["objektakte_status"]`; `text_status` wird `pending` (nicht `extracted`), solange
  kein OCR-Text tatsächlich vorliegt (siehe unten), `duplicate_of_id` wird gesetzt, wenn die
  objektakte-Zeile selbst schon `duplicate_of_document_id` trug.
- Kategorie/Subordner/Typ: `documents_documentcategory` wird auf `DocumentCategory` gemappt
  (Treffer über `source_id`, sonst über den Namen, sonst neu angelegt mit Code `oa-<code>`);
  `documents_documenttype` (mit seinem `documents_documentsubfolder`) landet in
  `objektakte_document_class`, da die CRM-Kategorie flach ist und die zweite Ebene nicht halten
  kann; der Dokumentimport löst `category_id` zuerst über den `document_type_id`, sonst über
  `category_code` auf.
- Objektbezug: über `documents_document.object_id` und die in Stufe 1 aufgebaute
  Property-Zuordnung; ein Dokument ohne auflösbares Objekt bekommt keinen `DocumentLink` und
  wird im Vorschaubericht als `documents_without_property` gezählt.
- Idempotenz: jede Zeile trägt eine Prüfsumme (`source_meta["row_hash"]`, sha256 über die
  sortierte JSON-Repräsentation der Dump-Zeile). Ein zweiter Apply mit unverändertem Dump
  ändert nichts (`skipped_duplicates`); eine geänderte Zeile (z. B. vor der Umschaltung noch
  einmal umklassifiziert) wird aktualisiert und im Ergebnis unter `updated` gezählt, nie
  stillschweigend übersprungen.
- OCR-Text: `POST /api/v1/objektakte/imports/{id}/ocr-cache` nimmt ein ZIP des objektakte
  `/data/ocr-cache`-Verzeichnisses entgegen (eine Textdatei je Cache-Eintrag, Dateiname ohne
  Endung = `ocr_cache_key`), gleicht gegen `source_meta["ocr_cache_key"]` ab und setzt
  `ocr_text`/`text_status = extracted`, sodass die Volltextsuche ohne Neu-OCR der ca. 26.000
  Bestandsdokumente funktioniert (Plan Abschnitt 5, Risiko OCR-Last). Ein nicht zuordenbarer
  Schlüssel wird als `unmatched_keys` gemeldet, nie verworfen.
- Vorschaubilder: **nicht** Teil dieser Stufe. Das CRM rendert derzeit für keinen
  Dokumenttyp eine eigene Vorschau (weder für hochgeladene noch für migrierte Dokumente); ein
  Vorschau-Pfad ist offen (`docs/OPEN_QUESTIONS.md`), unabhängig vom objektakte-Bestand. (Die
  Rule-ID `M35-02` bezeichnet seit Stufe 3 die Klassifikationsregeln, nicht diesen Punkt.)
- Review-Startbestand: `review_reviewcase`/`review_reviewdecision` füllen die Stufe-1-Tabellen
  `objektakte_document_review_case`/`_decision`, verknüpft über die migrierte `document_id`;
  `decided_by` bleibt unbesetzt (objektakte-Benutzer-IDs werden erst in Stufe 4 auf CRM-Nutzer
  abgebildet).

Rechte: `documents:read` lesen, `documents:create` Vorschau, Übernahme und OCR-Cache-Upload
(wie andere Importe, `mhvp.imports.routers`). Kein Feld ist zwingend aus objektakte lesbar:
fehlt eine Adresse oder ein Objekttyp, wird nichts geraten, sondern das Feld bleibt leer.

Nicht enthalten (Stufe 3 bis 6, siehe Plan): Klassifikation und die eigentliche
Review-Center-Oberfläche, Vollständigkeitsprüfung und Nachforderungsschreiben, Vorschaubilder,
Eigentümer-/Mieterlisten, Übernahme von `AiCall`-Historie und Benutzern, Parallelbetrieb.
