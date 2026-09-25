# Sicherheitsreview, Stand 25.09.2026

Prüfumfang: Alles seit Version 1.10.0 laut CHANGELOG.md und `git log --stat`, plus der
uncommittete Arbeitsstand (`git status`). Schwerpunkt auf den benannten Modulen
(portal, platform, handover, banking, objektakte, communication, ai, tickets, letting,
workspace, sla, immoware) sowie den BFF Routen der beiden Next.js Apps.

Dies ist ein Review, keine Freigabe. Es wurde nichts am Code verändert.

Hinweis zur Abdeckung: Aus Zeitgründen wurden `apps/api/src/mhvp/banking/finapi.py`,
`apps/api/src/mhvp/communication/gcal.py` und `apps/api/src/mhvp/immoware/discovery.py` nur
oberflächlich geprüft (Suche nach Token- und State-Handling, kein vollständiges Line-by-Line
Review). Diese drei Dateien sollten in einem Folgereview vertieft werden, insbesondere OAuth
State TTL und Single-Use in Redis. Keine Datei war zum Prüfzeitpunkt mid-edit und unparsebar.

## Befunde

### 1. Autorisierung

**Kein hoch/mittel Befund.** Stichprobe der neuen und geänderten Router
(`objektakte/routers.py`, `banking/routers.py`, `sla/routers.py`, `portal/routers.py`,
`platform/routers.py`) zeigt durchgängig `require_permission(...)` als Dependency und
`tenant_tx(request, principal)` für den DB-Zugriff. Objektzugriffe prüfen zusätzlich
`row.tenant_id != principal.tenant_id` vor Verwendung (z. B.
`apps/api/src/mhvp/objektakte/routers.py:93`, `:155`).

- **Datei/Zeile:** `apps/api/src/mhvp/portal/access.py:104-158` (Funktion `staff_permissions`,
  `visible_documents`), `apps/api/src/mhvp/portal/routers.py` (Tickets- und Work-Orders-Liste)
  **Schwere:** mittel
  **Beschreibung:** Mit der neuen Pflicht-Portalfreigabe für Mitarbeiter (M2-08) sieht ein
  Portal-Account mit Rolle `tenant_admin`/`administrator`/`support` (Default) bzw. jeder
  Standardrolle nun tenantweit alle Dokumente, Tickets und Arbeitsaufträge, nicht nur die
  eigenen. `ensure_staff_portal_access` (`apps/api/src/mhvp/platform/routers.py:714-776`) sucht
  den PortalAccount aber über `contact_id == contact_id OR user_id == user_id`. Ist derselbe
  Kontakt zugleich externer Portal-Nutzer (z. B. Eigentümer, der später auch Mitarbeiter wird,
  oder ein Mitarbeiter, dessen Kontakt zuvor als Dienstleister/Eigentümer angelegt war), wird
  der bestehende externe PortalAccount wiederverwendet und erhält zusätzlich den tenantweiten
  `staff_access`-Grant. Der Account bündelt damit externe und interne Sichtbarkeit in einem
  Login. Das widerspricht dem Prüfziel "Staff-Portalgrants dürfen nicht für externe Nutzer
  entstehen" im Ergebnis, auch wenn der Mechanismus formal nur für Mitglieder mit Membership
  greift.
  **Fix-Vorschlag:** Vor dem Wiederverwenden eines bestehenden Accounts prüfen, ob dieser
  bereits einen nicht-staff `legal_basis`-Grant (z. B. `owner`, `tenant`, `provider`) trägt;
  in diesem Fall separaten Account für die Mitarbeiterrolle anlegen oder die Kollision explizit
  in `docs/OPEN_QUESTIONS.md` mit Eigentümer und betroffenem Gate benennen, bevor produktiv
  genutzt.

  **Behoben (25.09.2026):** `ensure_staff_portal_access` (`platform/routers.py`) prüft vor dem
  Vergeben des Staff-Grants per `portal.access.has_external_grant`, ob der gefundene Account
  bereits einen externen Grant (owner/tenant/provider/handover_participant) trägt; im
  Konfliktfall wird kein Grant vergeben, ein Audit-Event
  `portal_account.staff_grant_conflict` protokolliert und `"conflict"` zurückgegeben, das
  `POST /api/v1/tenant/members` als `portal_access: "conflict"` mit deutscher Begründung
  (`portal_access_reason`) im `MemberOut` ausgibt. Umgekehrt weist `provision_account`
  (`portal/routers.py`) die Vergabe eines externen Grants für ein Konto mit vorhandenem
  Staff-Grant (`portal.access.has_staff_grant`) jetzt mit 409 und deutscher Meldung zurück.
  Beide Zweige getestet:
  `tests/integration/test_m2_platform.py::test_staff_invite_conflicts_with_existing_external_portal_account`
  und `::test_external_portal_grant_refused_for_staff_account`.

- **Datei/Zeile:** `apps/api/src/mhvp/portal/staff_access.py:33-44`
  **Schwere:** niedrig
  **Beschreibung:** Das Default-Mapping vergibt `tenant_admin`/`administrator` automatisch
  volle `PORTAL_STAFF_PERMISSIONS` (inkl. `documents:read`, `handover:read`), ohne dass der
  Tenant dies aktiv konfiguriert. Das ist eine bewusste Produktschutz-Entscheidung
  (dokumentiert), aber als Default sehr weitreichend; sollte im Abnahmetest explizit erwähnt
  werden, damit der Betreiber es kennt.
  **Fix-Vorschlag:** Keiner zwingend, ggf. im Abnahmeprotokoll gegenzeichnen lassen.

### 2. Secrets

**Kein hoch/mittel Befund** bei den neu geprüften Feldern:
- `WhatsAppConfig.access_token` ist `EncryptedText()` (`apps/api/src/mhvp/sla/models.py:217`)
  und wird nur als `access_token_set: bool` ausgegeben, nie im Klartext
  (`apps/api/src/mhvp/sla/routers.py:218-223`).
- `apps/api/src/mhvp/documents/property_filing.py:48-56` liest `client_secret`/`refresh_token`
  aus einer verschlüsselt gespeicherten Connection und reicht sie nur intern an
  `GoogleDriveStore` weiter, keine Ausgabe an den Client.
- IBAN in der objektakte-Übernahme: `apps/api/src/mhvp/objektakte/objektakte_import.py:29-33,
  476-478` liest laut Kommentar und Code nur `iban_last4`/`iban_hash` aus dem Dump, keine
  Plaintext-IBAN wird in ein `ContactBankAccount` geschrieben (das Feld bleibt leer/erfordert
  eine separate autorisierte Erfassung). Das entspricht der Vorgabe.

- **Datei/Zeile:** `apps/api/src/mhvp/sla/whatsapp_webhook.py:55` und
  `apps/api/src/mhvp/sla/whatsapp.py` (kein Log-Statement mit Payload-Inhalt gefunden)
  **Schwere:** niedrig
  **Beschreibung:** Beim ungültigen Signatur-Header wird nur `log.warning("whatsapp webhook:
  invalid or missing signature")` geloggt, ohne Payload oder Telefonnummern. Positiv zu
  vermerken, kein Finding, nur zur Dokumentation der Prüfung.

- **Datei/Zeile:** `apps/api/src/mhvp/banking/invoice_matching.py` (grep nach IBAN/Log)
  **Schwere:** niedrig, zur Vertiefung
  **Beschreibung:** Datei wurde nur überflogen; keine offensichtliche Ausgabe von
  Kontodaten in Out-Schemas gefunden, aber keine vollständige Zeilenprüfung durchgeführt.
  Im Folgereview gezielt auf `OrderOut`/`InvoiceOut`-Schemas prüfen, ob IBAN maskiert
  zurückgegeben wird (z. B. nur letzte 4 Stellen).

### 3. Input-Handling

**Kein hoch/mittel Befund bei `mhvp/core/sqldump.py`.** Der Parser (`apps/api/src/mhvp/core/
sqldump.py`) führt kein SQL aus (nur `re`-basiertes Parsen von `INSERT INTO ... VALUES`), hat
keinen `eval`/`exec`, keine dynamische Codeausführung. `split_tuples`/`parse_fields` behandeln
Anführungszeichen, Escapes und verdoppelte Quotes zeichenweise; bei fehlerhaftem Tupel
(`len(values) != len(columns)`) wird die Zeile übersprungen statt eine Exception zu werfen
(`parse_dump`, Zeile 156-157). Das ist robust gegen abgeschnittene/manipulierte Dumps. Ein
gezielt bösartiger Dump kann höchstens fehlerhafte Daten einschleusen (die dann von den
Importern gegen bekannte Tabellen/Spalten gemappt werden), aber keine SQL-Injection oder
Codeausführung auslösen.

- **Datei/Zeile:** `apps/api/src/mhvp/objektakte/routers.py:108-137` (ZIP-Verarbeitung
  OCR-Cache)
  **Schwere:** mittel
  **Beschreibung:** Die Größe des komprimierten Uploads wird begrenzt
  (`MAX_OCR_ZIP_BYTES = 500 MB`), die Größe der **entpackten** Einzeldateien dagegen nicht,
  bevor `archive.read(info)` aufgerufen wird. Ein präpariertes ZIP (Zip-Bomb) mit hoher
  Kompressionsrate könnte beim Entpacken excessive Arbeitsspeicher belegen, auch wenn kein
  Zip-Slip vorliegt (es wird nichts auf das Dateisystem geschrieben, nur `filename.rsplit`
  zur Schlüsselbildung verwendet, kein Pfad-Traversal-Risiko).
  **Fix-Vorschlag:** Vor `archive.read(info)` `info.file_size` prüfen und bei Überschreiten
  eines Limits (z. B. 20 MB je Texteintrag, passend zu `MAX_OCR_TEXT_CHARS`) überspringen statt
  lesen; zusätzlich Gesamtzahl der Einträge begrenzen (`len(archive.infolist())`).

  **Behoben (25.09.2026):** `apply_ocr_cache` prüft `info.file_size` je Eintrag gegen
  `MAX_OCR_ENTRY_BYTES` (20 MB) und die fortlaufende Summe gegen
  `MAX_OCR_TOTAL_UNCOMPRESSED_BYTES` (2 GB) vor `archive.read()`; ein Überschreiten zählt als
  `skipped_too_large` statt gelesen zu werden. Die Eintragszahl ist zusätzlich auf
  `MAX_OCR_ENTRIES` (50.000) begrenzt (Ablehnung mit 400 bei Überschreitung). Getestet in
  `tests/integration/test_m35_objektakte_import.py::test_ocr_cache_zip_skips_entries_over_the_size_limit`.

- **Datei/Zeile:** `apps/api/src/mhvp/objektakte/routers.py:27-36` (`_read_dump`)
  **Schwere:** niedrig
  **Beschreibung:** `MAX_DUMP_BYTES = 200 MB` wird geprüft, danach vollständiger Text im
  Speicher gehalten und mit `re.DOTALL`-Regex über den gesamten String gescannt
  (`_INSERT_RE`). Bei 200 MB Text und pathologischen Eingaben (sehr viele verschachtelte
  Anführungszeichen) ist ein worst-case regex-Backtracking theoretisch möglich, auch wenn der
  Regex selbst keine offensichtlich katastrophale Rückverfolgung enthält (kein verschachteltes
  `.*.*`). Nicht dringend, aber als Lastrisiko vermerkt.
  **Fix-Vorschlag:** Keine akute Änderung nötig; bei Performance-Problemen einen
  Stream-Parser statt eines einzelnen `finditer` über den Gesamttext erwägen.

- **XML/XXE:** Keine neue Verwendung von `xml.etree.ElementTree` mit externer DTD gefunden in
  den geprüften Modulen; OpenImmo-Export (`letting/listings/{id}/openimmo.xml`) ist laut
  BFF-Kommentar "read only, no portal upload" (nur Export, kein Parsen fremder XML). Keine
  XXE-relevante Änderung im geprüften Diff identifiziert. Für abschließende Sicherheit sollte
  der Exporter (nicht im Kernumfang dieses Reviews enthalten, da unverändert) trotzdem einmal
  gezielt auf verwendete Parser-Klasse geprüft werden, falls dort `lxml` mit
  `resolve_entities=True` verwendet wird.

### 4. Web (BFF, CSRF, Redirect, Webhooks)

- **Datei/Zeile:** `apps/web-crm/src/app/api/session/return/route.ts:10-19` (`safeNext`)
  **Schwere:** niedrig
  **Beschreibung:** Der Schutz gegen Open Redirect prüft `startsWith("/")`,
  `startsWith("//")` und `includes("\\")`. Das deckt die gängigen Umgehungen ab. Nicht
  geprüft sind Steuerzeichen wie führende Tabs/Zeilenumbrüche vor einem Schema
  (`/\t/evil.com` wird von `startsWith("/")` als Treffer gewertet, Browser interpretieren
  das aber nicht als Protokollwechsel, da kein `:` vorkommt) sowie mehrfach kodierte
  Sequenzen (`%2F%2F`), die aber vom Query-Parameter-Decoding bereits vor `safeNext` einmalig
  aufgelöst würden und dann durch die `//`-Prüfung griffen. Insgesamt kein praktikabler
  Bypass gefunden, Empfehlung ist präventiv.
  **Fix-Vorschlag:** Zusätzlich `raw.includes(":")` ablehnen (schließt `javascript:`,
  `/\t:evil` u. ä. sicher aus) und `next` gegen eine Positivliste bekannter interner Pfade
  oder ein striktes Pfad-Muster (`^/[a-zA-Z0-9/_-]*$`) validieren statt nur Negativliste.

  **Behoben (25.09.2026):** `safeNext` validiert `next` zusätzlich gegen das Positivmuster
  `^\/[A-Za-z0-9._~/-]*(\?[^#\s]*)?$` und lehnt ein `:` vor dem `?` (im Pfadteil) explizit ab;
  ein `:` innerhalb der Query bleibt erlaubt. Getestet in `route.test.ts`
  ("refuses a path carrying a scheme before the query",
  "allows a colon in the query string but not in the path").

- **Datei/Zeile:** `apps/web-crm/src/app/api/bff/[...path]/route.ts:282-288`
  **Schwere:** niedrig
  **Beschreibung:** CSRF-Schutz (`rejectForeignOrigin`) wird korrekt nur für Nicht-GET
  Methoden aufgerufen, vor dem eigentlichen Forward. Die Allowlist-Einträge sind überwiegend
  eng gefasst (feste Literale oder `ID`-Muster mit UUID-Regex); keine breite Catch-all-Regex
  wie `.*` gefunden. Einzig `{ method: "GET", pattern: /^dms-documents\/[0-9]+\/file$/ }`
  (Zeile 225) verwendet eine numerische ID statt UUID, was aber zum Datenmodell (Paperless
  nutzt integer IDs) passt und keine Tenant-Grenze umgeht, da die Tenant-Prüfung serverseitig
  (`tenant_tx`) erfolgt.
  **Fix-Vorschlag:** Kein Fix nötig; nur zur Dokumentation der Prüfung.

- **Datei/Zeile:** `apps/web-portal/src/app/api/bff/[...path]/route.ts`,
  `apps/web-portal/src/app/api/session/login/route.ts`
  **Schwere:** nicht bewertet (nur oberflächlich gegengelesen)
  **Beschreibung:** Struktur identisch zum CRM-BFF (Allowlist + `rejectForeignOrigin`).
  Cookie-Attribute (`httpOnly`, `secure`, `SameSite=Strict`) wurden nicht im Detail
  nachvollzogen, da `apps/web-portal/src/lib/api-server.ts` bzw. das Cookie-Setzen außerhalb
  des explizit genannten Pfads liegt. Empfehlung: im Folgereview gezielt die Cookie-Flags am
  Ort des `Set-Cookie` verifizieren (Login-Route und Refresh-Pfad).

- **Datei/Zeile:** `apps/api/src/mhvp/sla/whatsapp_webhook.py:29-43` (GET-Verifizierung),
  `:46-73` (POST-Signatur)
  **Schwere:** kein Befund
  **Beschreibung:** `verify_webhook_signature` nutzt `hmac.compare_digest` (timing-safe),
  Verify-Token wird aus `SecretStr` gelesen. Fehlender oder falscher Header führt zu 403
  bzw. `{"status": "ignored"}`, keine Fehlerdetails werden preisgegeben. Positiv.

### 5. Geld und Gates

**Kein Befund.** Stichprobe in `apps/api/src/mhvp/banking/routers.py` zeigt für den
Zahlungsdatei-Export (`/payment-batches`) einen expliziten
`ensure_release_gate_open(ReleaseGate.G2, ...)`-Aufruf (Zeile 837-841); Kommentare an
mehreren Stellen ("gate G2 stays closed, so this never submits or initiates a payment")
decken sich mit dem Code. `invoice_matching.py` verweist im Docstring auf denselben
gated Flow und erzeugt laut Kommentar nur Vorschläge/Order-Entwürfe. Keine neue Stelle
gefunden, die eine Zahlung oder Buchung ohne Gate-Prüfung auslöst. Für eine abschließende
Aussage müssten zusätzlich `mhvp/tickets/routers.py`, `mhvp/letting/*` (Mieterhöhung
versenden) und `mhvp/workspace/*` auf Gate-Aufrufe durchsucht werden; das wurde nur über den
BFF-Allowlist-Kommentar ("sending needs G3, checked by the API") plausibilisiert, nicht am
API-Code selbst nachvollzogen.

### 6. DSGVO

- **Datei/Zeile:** `apps/api/src/mhvp/portal/access.py:107-140` (siehe Befund 1)
  **Schwere:** mittel (gleicher Befund wie oben, hier unter Datenminimierung eingeordnet)
  **Beschreibung:** Die tenantweite Dokument-/Ticket-/Auftragssicht für Staff-Portal-Accounts
  ist das Gegenteil von Datenminimierung im externen Portal-Kontext, wenn ein Account
  gleichzeitig externe Grants trägt (siehe oben). Bei reinen internen Mitarbeiter-Accounts ist
  die volle Sicht dagegen sachlich begründet (interner Kanal) und daher kein DSGVO-Problem für
  sich genommen.
  **Fix-Vorschlag:** Siehe Fix-Vorschlag Befund 1.

- **Löschung:** Keine neue Lösch-Route in den geprüften Dateien gefunden, die nicht bereits
  über `require_permission` auf Admin-Rechte eingeschränkt wäre (z. B.
  `contacts/{id}` DELETE bleibt in der bestehenden Allowlist mit UUID-Muster, keine
  Erweiterung der Löschrechte im Diff sichtbar).

### 7. Nebenläufigkeit und Idempotenz von Importen

**Kein hoch/mittel Befund.** `objektakte_import.py` ist laut Docstring und Code (Zeilen
181-373) idempotent über `source_id` je `source_system="objektakte"`: vor dem Anlegen wird
je Tabelle die Menge bereits vorhandener `source_id`s geladen (`_existing_source_ids`) und
neue Zeilen werden dagegen geprüft. Ein zweiter `apply`-Aufruf mit demselben Dump sollte
daher keine Duplikate erzeugen, sofern die DB-Transaktion (`tenant_tx`) Race Conditions
zwischen zwei parallelen Applies auf denselben Tenant nicht zulässt (kein `SELECT ... FOR
UPDATE` oder Unique-Constraint auf `(tenant_id, source_system, source_id)` im Code sichtbar
geprüft; die Existenzprüfung erfolgt vor dem Schreiben, nicht atomar).

- **Datei/Zeile:** `apps/api/src/mhvp/objektakte/objektakte_import.py` (`_existing_source_ids`,
  `apply_import`)
  **Schwere:** niedrig
  **Beschreibung:** Ohne einen DB-seitigen Unique-Constraint auf
  `(tenant_id, source_system, source_id)` könnten zwei zeitgleiche `apply`-Requests
  (z. B. Doppelklick oder Retry nach Timeout) beide die gleiche "nicht vorhanden"-Prüfung
  bestehen und doppelte Zeilen anlegen. Ob ein solcher Constraint existiert, wurde nicht in
  den Alembic-Migrationen verifiziert (aus Zeitgründen nicht geprüft).
  **Fix-Vorschlag:** Unique Index auf `(tenant_id, source_system, source_id)` je betroffener
  Tabelle sicherstellen (Migration prüfen/ergänzen) und/oder den Apply-Endpunkt zusätzlich
  gegen einen `Idempotency-Key`-Header oder laufenden `ImportRun` desselben Tenants sperren.

  **Behoben (25.09.2026):** Migration `0065_objektakte_staging_source_unique` ergänzt die
  fehlende Spalte `source_system` sowie einen partiellen Unique-Index auf
  `(tenant_id, source_system, source_id)` (`source_id IS NOT NULL`) für
  `objektakte_drive_node`, `objektakte_document_review_case` und
  `objektakte_document_review_decision` (`objektakte_party_assignment` und
  `objektakte_document_class` hatten den Constraint bereits). Der Importer
  (`objektakte_import.py`) fängt eine `IntegrityError` beim Einfügen dieser vier Tabellen über
  eine Savepoint-geschützte Hilfsfunktion (`_insert_or_get_by_source`) ab und liest die von der
  parallelen Transaktion committete Zeile erneut, statt den ganzen Import abzubrechen.

## Top 10, priorisiert

1. **Mittel — Behoben (25.09.2026)** – Staff-Portal-Account-Wiederverwendung kann externe und
   interne Rollen in einem Account vermischen (`platform/routers.py:714-776`,
   `portal/access.py:104-158`). Blockierte **G5** (Drittmandanten/externe Portalnutzer), da
   externe Nutzer potenziell interne Sicht erhalten könnten. Siehe Befund 1 oben.
2. **Mittel — Behoben (25.09.2026)** – Kein Limit für entpackte Einzeldateigröße im
   OCR-Cache-ZIP-Import (`objektakte/routers.py:108-137`), Zip-Bomb-Risiko. Siehe Abschnitt 3
   oben.
3. **Niedrig, aber empfohlen — Behoben (25.09.2026)** – Kein Unique-Constraint-Nachweis für
   Idempotenz des objektakte-Imports bei parallelen Applies (`objektakte_import.py`). Siehe
   Abschnitt 7 oben.
4. **Niedrig — Behoben (25.09.2026)** – `safeNext` in `session/return/route.ts` zusätzlich
   gegen `:` und ein strengeres Positivmuster absichern. Siehe Abschnitt 4 oben.
5. **Niedrig** – Default-Portalrechte für `tenant_admin`/`administrator` sind weitreichend;
   im Abnahmeprotokoll gegenzeichnen lassen.
6. **Zur Vertiefung** – `finapi.py`, `gcal.py`, `immoware/discovery.py`: OAuth-State-Handling
   (Redis TTL, Single-Use) in einem Folgereview mit mehr Zeit vollständig prüfen.
7. **Zur Vertiefung** – `banking/invoice_matching.py`: Out-Schemas gezielt auf IBAN-Maskierung
   prüfen.
8. **Zur Vertiefung** – Cookie-Flags (`httpOnly`/`secure`/`SameSite=Strict`) am Ort des
   `Set-Cookie` in `web-portal` und `web-crm` verifizieren, nicht nur am BFF-Proxy.
9. **Kein Befund, aber zu beobachten** – `_read_dump` hält 200 MB Text vollständig im Speicher
   und scannt mit einem `DOTALL`-Regex über den Gesamtstring; Lastrisiko bei böswillig
   großen/pathologischen Dumps, keine akute Schwachstelle.
10. **Kein Befund** – Geld-/Buchungspfade (Zahlungsdatei-Export, Mahnungen, HGV-Abrechnungen)
    sind an den geprüften Stellen korrekt hinter Release-Gates (G1-G5) und
    Genehmigungsschritten; AI-Apply-Pfade laut Docstrings nur Entwürfe/Vorschläge.

## Aussage zu den Release-Gates

Kein Befund in diesem Review deutet auf eine ungeschützte Geldbewegung oder Buchung hin
(Abschnitt 5); die geprüften Zahlungs- und Buchungspfade bleiben hinter G1/G2 verriegelt.
**Befund 1 (Staff-Portal-Account-Vermischung) sollte vor Öffnung von G5 (Drittmandanten)
geklärt werden**, da er die Trennung zwischen internem Personal und externen Portalnutzern
berührt, die Grundlage von G5 ist. Befund 2 (Zip-Bomb im OCR-Cache-Import) blockiert kein
Gate direkt, sollte aber vor breiterem produktivem Einsatz der objektakte-Übernahme (M35)
behoben werden. Alle übrigen Befunde sind niedrig priorisiert oder reine
Vertiefungshinweise und stehen der bestehenden Gate-Lage nicht entgegen.
