# M30 Übergabeprotokoll: U-Protokoll in den Bereich Makler überführen

Stand 25.09.2026, Entscheidung des Betreibers: Die eigenständige Anwendung U-Protokoll
(PHP, MariaDB, produktiv unter uprotokoll.muellerhv.de, Repository v3ni94/UProtkoll) wird als
Unterpunkt "Übergabeprotokoll" des Bereichs Makler in das CRM überführt. Alle Daten liegen
zentral in der CRM-Datenbank (PostgreSQL, Mandantentrennung per RLS), Dateien im
Objektspeicher der Dokumentenverwaltung (M6), Versand über die Zustellung (M23) und den
Postausgang mit Vier-Augen-Freigabe (M20).

## Zielbild

- Reiter Makler, Unterpunkt Übergabeprotokoll (Recht `contracts:read`, Schreiben mit
  `contracts:create`/`contracts:update`, wie die Anzeigen aus M28).
- Ein Protokoll entsteht aus Objekt und Einheit (Adresse, Etage und Einheit werden
  vorbelegt und bleiben als Momentaufnahme editierbar) oder ohne Objektbezug
  (Allgemeines Übergabeprotokoll). Optional wird eine Anzeige (Makler) verknüpft.
- Beteiligte sind Kontakte des CRM (Mieter, Eigentümer, Verwaltung, Zeugen); ein
  Beteiligter ohne Kontakt kann als Name erfasst werden.
- Zähler kommen aus den Zählerstammdaten des Objekts (Zählernummer, Art), die
  Ablesung im Protokoll ist ein eigener Stand mit Foto; freie Zähler bleiben möglich.
- Fotos, Anhänge, Unterschriften (PNG mit SHA-256) und das abgeschlossene PDF sind
  Dokumente der Dokumentenverwaltung, verknüpft mit Protokoll, Objekt und Einheit.
- Abschluss sperrt das Protokoll, erzeugt das PDF auf dem Briefbogen des Mandanten und
  bereitet die Zustellung an die Beteiligten vor. Nachträgliche Änderungen nur als neue
  Version mit Änderungsgrund; das Original bleibt unverändert.
- Kein inhaltliches Pflichtfeld; der Abschluss zeigt Hinweise (fehlende Adresse, keine
  Zähler, keine Unterschrift) und verlangt eine ausdrückliche Bestätigung.

## Abweichungen gegenüber der Einzelanwendung

| Thema | U-Protokoll (PHP) | CRM |
| --- | --- | --- |
| Versand nach Abschluss | automatisch per SMTP an alle Beteiligten | Zustellung wird vorbereitet (Dispatch mit E-Mail-Entwurf je Beteiligtem); Versand nur über den Postausgang mit Vier-Augen-Freigabe (M20-01, Regel 0.1.7 sinngemäß: keine unbeaufsichtigte Außenkommunikation) |
| Gehilfenzugang (Mieter füllt selbst aus) | eigene Benutzerrolle mit Passwort per E-Mail | Portalzugang (M21) mit Zugriffsrecht `handover`/`edit` auf genau ein Protokoll, Einladungscode aus dem CRM, Anmeldung im Portal mit Passwort und zweitem Faktor (Plattformregel für alle Benutzer); nach dem Abschluss nur noch lesend für 14 Tage (Stufe 3) |
| Protokollnummer | UP-JJJJMMTT-NNN aus MAX+1 | UP-JJJJMMTT-NNN aus der Nummernfolge je Mandant und Tag (`number_sequence`, lückenlos innerhalb der Transaktion) |
| Dateiablage | lokal oder SFTP | Objektspeicher (S3, ADR 0005) über `documents.services.store_document` |
| Ortsermittlung per GPS | Browser-Geolocation mit Nominatim | nicht übernommen (externer Dienst, Datenschutz offen, M30-02) |
| Rollen | Admin, Mitarbeiter, Objektbetreuer, Nur Lesen, Gehilfe | Rechte-Matrix des CRM (Abschnitt 3.4) |

## Stufen

1. **Datenmodell und API** (umgesetzt 25.09.2026): Domäne `handover`, Tabellen
   `handover_protocol`, `handover_participant`, `handover_meter`, `handover_room`,
   `handover_defect`, `handover_key`, `handover_item`, `handover_note`,
   `handover_signature` (Migration 0043 mit RLS). Endpunkte unter `/api/v1/handover`:
   Liste, Anlage mit Vorbelegung, Feldänderung, Teildatensätze je Abschnitt, Fotos,
   Unterschriften, Hinweise, Abschluss mit PDF, neue Version, Stornierung, Archivierung,
   Zustellung vorbereiten.
2. **Oberfläche im CRM** (umgesetzt 25.09.2026): `/makler/uebergabe` (Liste mit Suche,
   Status, Archiv), `/makler/uebergabe/neu`, `/makler/uebergabe/[id]` (Abschnitte als
   Reiter, Speichern je Abschnitt, Fotos, Unterschriften per Canvas, Abschluss mit
   Hinweisen und Rückfrage, PDF, Versionen, Zustellung).
3. **Gehilfenzugang über das Portal** (umgesetzt 25.09.2026): Im CRM richtet die Verwaltung
   je Beteiligtem mit CRM-Kontakt den Portalzugang ein (`POST
   /handover/protocols/{id}/participants/{pid}/portal-access`): fehlt ein Portalkonto, wird es
   angelegt (Rolle `portal_user`, Einladungscode einmalig angezeigt), das Zugriffsrecht
   `access_grant` mit `scope_type=handover`, `right=edit`, `legal_basis=handover_participant`
   verweist auf genau dieses Protokoll und überlebt die Neuableitung der Vertragsrechte.
   Portal-API `/api/v1/portal/handover`: Liste, Lesen ohne interne Felder, Felder ändern
   (keine internen Felder, keine CRM-Verweise), Teildatensätze, Fotos, Unterschriften,
   Hinweise, Abschluss, PDF; jede Schreiboperation wird an die CRM-Handler delegiert. Nach dem
   Abschluss wird das Recht `read` mit Ablauf nach 14 Tagen (`READ_DAYS`). Portal-Oberfläche
   in `apps/web-portal`: Anmeldung mit Passwort und zweitem Faktor (wie CRM, gleiche
   Cookie-Sitzung), `/uebergabe` (Liste), `/uebergabe/[id]` (Abschnitte, Fotos, Unterschrift,
   Abschluss). Offen: Zustellung des Einladungscodes per Schreiben oder E-Mail (M23) und die
   Frage, ob die Pflicht zum zweiten Faktor für Gehilfen tragbar ist (M30-05).
3a. **Gehilfenzugänge und manuelles Objekt** (umgesetzt 25.09.2026, Entscheidung des
   Integrators: bestehenden Portalzugang erweitern statt eines zweiten Auth-Systems):
   - Freitext-Objekt (Teil A des Betreiberauftrags): neue Felder `external_object_number` und
     `owner_name` am Protokoll (Migration 0053), zusätzlich zu den bereits vorhandenen
     Freitext-Feldern für Adresse, Etage und Einheit. Anlageformular (`HandoverCreate.tsx`)
     zeigt einen Schalter „Objekt aus dem Bestand“ / „Objekt manuell erfassen“; im manuellen
     Fall werden Adresse, Etage, Einheit, externe Objektnummer und Eigentümer/Vermieter frei
     eingegeben und direkt nach der Anlage gespeichert. Beide Felder erscheinen im PDF und im
     Formular (`HandoverEditor.tsx`).
   - Gehilfenzugänge (Teil B, aus U-Protokoll übernommen, docs/rules/M30-06.md): eigene
     Endpunkte `/handover/protocols/{id}/helper-access` (Liste, Anlage mit Art
     helper/tenant/owner, optionaler Anmeldung als Beteiligter mit Einzug/Auszug, Wiederversand,
     Beenden). Es entsteht kein zweites Zugangssystem: die Anlage sucht oder legt einen
     minimalen CRM-Kontakt an und richtet darauf denselben Portalzugang (M21) wie bei einem
     Beteiligten ein, mit `role` = Art des Gehilfen und `valid_to` = 30 Tage ab Anlage (wie
     U-Protokoll Migration 006, Einstellung `helper.access_days`). Die Einladung geht, wenn ein
     Postfach eingerichtet ist, als Entwurf in den Postausgang (Vier-Augen-Freigabe, M20-01);
     sonst wird der Code der Verwaltung einmalig angezeigt. Staff-Oberfläche: Abschnitt
     „Gehilfenzugänge“ im Reiter Prüfung/Abschluss (`HelperAccessSection.tsx`).
   - Abschluss durch einen Gehilfen (`POST /portal/handover/{id}/complete`) sperrt das
     Protokoll wie bisher, bereitet danach automatisch je einen Zustellungsentwurf (M23) für
     jeden Beteiligten mit CRM-Kontakt sowie für den Gehilfen vor (Status wechselt dadurch auf
     „Zustellung vorbereitet“, nicht mehr nur „abgeschlossen“) und erzeugt ein internes
     Ereignis für den anlegenden Sachbearbeiter (kein eigener Push-/Mail-Kanal vorhanden). Die
     Bestätigungsseite im Portal fragt „Ist die Übergabe vollständig abgeschlossen?“ (Ja/Nein);
     danach zeigt die Zusammenfassung den PDF-Link.
4. **Datenübernahme** aus U-Protokoll (umgesetzt 25.09.2026, Testdaten): Endpunkt `POST
   /api/v1/handover/imports/uprotokoll` (Query `mode=preview|apply`) parst einen
   `mysqldump`-Export (utf8mb4, Schema `database/migrations/001_create_schema.sql` von
   v3ni94/UProtkoll) ohne SQL auszuführen (`mhvp.handover.uprotokoll_import.parse_dump`,
   eigener Parser für `INSERT ... VALUES`-Tupel mit Anführungszeichen, Escaping und `NULL`).
   Vorschau meldet Anzahl je Tabelle, nicht zugeordnete Objekte (Adressabgleich gegen
   `property`, sonst Freitext-Objekt nach Stufe 1/Teil A) und Duplikate über bereits
   vorhandene `import_source`. Übernahme legt Protokolle, Beteiligte, Zähler, Räume, Mängel,
   Schlüssel, Gegenstände und Hinweise an, jede Zeile mit `import_source =
   "uprotokoll:<Quell-ID>"` (Migration 0054), wodurch ein erneuter Lauf desselben Exports
   nichts verändert (idempotent). Protokollversionen und E-Mail-Historie aus U-Protokoll
   werden gezählt, aber nicht als eigene Datensätze angelegt (offener Punkt, siehe unten).
   Fotos, Unterschriften und das frühere PDF liegen nicht im SQL-Dump: `POST
   /api/v1/handover/imports/uprotokoll/files?import_run_id=...` nimmt ein ZIP des
   U-Protokoll-Speicherordners entgegen, gleicht jede Datei über SHA-256 (bevorzugt) oder den
   gespeicherten Pfad mit den bei der Übernahme hinterlegten `protocol_files`-Metadaten ab und
   legt sie als Dokument der Dokumentenverwaltung an, verknüpft mit Protokoll, Zähler, Raum,
   Mangel oder Gegenstand; eine Datei der Art `signature` erzeugt zusätzlich den
   `handover_signature`-Datensatz. Der Importlauf ist ein `mhvp.ai.models.ImportRun` mit
   `source="uprotokoll"`, wie jeder andere bestätigte Import der Plattform.
   Getestet mit einem synthetischen Dump (`tests/unit/test_m30_uprotokoll_import.py`,
   `tests/integration/test_m30_handover.py::test_uprotokoll_import_preview_apply_and_files`),
   nicht mit echten Daten (Regel 0.1.9). Offen (M30-03): echter Exportbefehl und Speicherort
   der Dateien beim Betreiber, Ablösung von uprotokoll.muellerhv.de.
4a. **Versionen und E-Mail-Historie beim Import** (umgesetzt 26.09.2026): Die Übernahme läuft in
   zwei Durchläufen. Erst werden alle Protokolle angelegt, dann wird `protocols.parent_protocol_id`
   auf `handover_protocol.parent_id` abgebildet (`change_reason` wird mit übernommen); ein
   bereits gesetzter Verweis bleibt unverändert, ein Vorgänger, der weder im Dump noch im CRM
   vorhanden ist, wird als `versions_unresolved` gezählt. Die Tabelle `protocol_emails` wird
   vollständig gezählt (`emails_total` in Vorschau und Bericht) und je Protokoll als interner
   Hinweis (`handover_note`, Kategorie `other`, `is_internal`, `import_source =
   "uprotokoll:email:<id>"`) mit Zeitpunkt, Empfänger, Betreff und Sendestatus übernommen; der
   Mailtext wird nie übernommen. Beide Schritte sind idempotent und wirken auch auf Protokolle,
   die ein früherer Lauf ohne diese Schritte angelegt hat.
4b. **Portal für Mitarbeiter** (umgesetzt 26.09.2026, M2-08 Rest): `GET
   /api/v1/portal/handover-protocols` (Liste mit Objekt, Einheit, Datum, Status, PDF-Link),
   `/{id}` (ohne interne Felder) und `/{id}/pdf` für Mitgliedschaften mit dem Portalrecht
   `handover:read` (`mhvp.handover.portal_staff`); Portalseite `/uebergabeprotokolle` mit
   Navigationslink und Startkachel nur bei vorhandenem Recht. Beim Rollenwechsel in eine
   ausgenommene Rolle wird der mandantenweite Zugriffsgrant deaktiviert, beim Rückwechsel
   wieder aktiviert (`mhvp.platform.staff_portal_sync`).

## Dateien (Stufe 3)

- `apps/api/src/mhvp/handover/portal.py` (Portal-Router, delegiert an `routers.py`)
- `apps/api/src/mhvp/handover/routers.py` (Portalzugang einrichten und beenden, `portal_access`
  je Beteiligtem), `apps/api/src/mhvp/portal/access.py` (manuelle Rechte bleiben bei Resync),
  `apps/api/src/mhvp/portal/routers.py` (`provision_account`)
- `apps/api/tests/integration/test_m30_handover.py::test_handover_portal_flow`
- `apps/web-portal/src/**` (Sitzung, Anmeldung, BFF, Dateiproxy, Liste, Erfassungsseite),
  `apps/web-crm/src/components/handover/PortalAccessBox.tsx`

## Dateien (Stufe 3a: Gehilfenzugänge, manuelles Objekt, 25.09.2026)

- `apps/api/src/mhvp/handover/models.py` (Felder `external_object_number`, `owner_name`,
  `import_source` je Tabelle), `apps/api/alembic/versions/0053_handover_manual_object.py`,
  `apps/api/alembic/versions/0054_handover_import_source.py`
- `apps/api/src/mhvp/handover/routers.py` (`HelperAccessIn`, `create_helper_access`,
  `list_helper_access`, `revoke_helper_access`, `resend_helper_access`,
  `prepare_helper_completion_dispatch`, `notify_creator_of_completion`)
- `apps/api/src/mhvp/handover/portal.py` (`complete` ruft die automatische Zustellung und die
  interne Benachrichtigung auf)
- `apps/api/src/mhvp/handover/pdf.py` (externe Objektnummer, Eigentümer/Vermieter)
- `apps/web-crm/src/components/handover/HandoverCreate.tsx` (Schalter Bestand/manuell),
  `HandoverEditor.tsx` (neue Felder, `HelperAccessSection`),
  `HelperAccessSection.tsx` (neu)
- `apps/web-crm/src/app/api/bff/[...path]/route.ts` (Positivliste `helper-access`)
- `apps/web-crm/messages/de.json`, `apps/web-portal/messages/de.json`
- `docs/rules/M30-06.md`, `docs/rules/README.md`
- `apps/api/tests/integration/test_m30_handover.py::test_helper_access_flow`

## Dateien (Stufe 4: Datenübernahme U-Protokoll, 25.09.2026)

- `apps/api/src/mhvp/handover/uprotokoll_import.py` (Parser, Vorschau, Übernahme)
- `apps/api/src/mhvp/handover/imports.py` (`/handover/imports/uprotokoll`,
  `/handover/imports/uprotokoll/files`), Einbindung in `apps/api/src/mhvp/main.py`
- `apps/api/tests/unit/test_m30_uprotokoll_import.py` (Parser, ohne Datenbank),
  `apps/api/tests/integration/test_m30_handover.py::test_uprotokoll_import_preview_apply_and_files`
- `docs/OPEN_QUESTIONS.md` (M30-03, aktualisiert)

## Dateien (Stufe 1 und 2)

- `apps/api/src/mhvp/handover/{models,routers,services,pdf,README}.py|md`
- `apps/api/alembic/versions/0043_handover.py`
- `apps/api/src/mhvp/documents/services.py` (verknüpfbare Entitäten `handover_*`)
- `apps/api/src/mhvp/models.py`, `apps/api/src/mhvp/main.py`
- `apps/api/tests/integration/test_m30_handover.py`
- `apps/web-crm/src/app/(app)/makler/uebergabe/**`, `apps/web-crm/src/components/handover/**`,
  BFF-Positivliste, `messages/de.json`, `messages/en.json`
- `docs/rules/M30-01.md`, `docs/OPEN_QUESTIONS.md`

## Gates

Keine Geldflüsse. Die Kautionsangaben (Betrag, IBAN) werden nur erfasst und im PDF
ausgegeben; sie erzeugen keine Forderung und keine Zahlung (G1, G2 unberührt). Die IBAN
wird formal geprüft (Mod 97), ein Prüfkennzeichen "IBAN geprüft" setzt nur die Verwaltung.

## Dateien (Stufe 4a und 4b: Versionen, E-Mail-Historie, Mitarbeiterportal, 26.09.2026)

- `apps/api/src/mhvp/handover/uprotokoll_import.py` (`_link_predecessors`,
  `_import_email_history`, `email_note_text`, Zähler in `ImportPlan` und `ImportResult`)
- `apps/api/src/mhvp/handover/portal_staff.py` (neu), `apps/api/src/mhvp/main.py` (Registrierung)
- `apps/api/src/mhvp/platform/staff_portal_sync.py` (neu), `apps/api/src/mhvp/platform/routers.py`
  (`put_member_roles`), `apps/api/src/mhvp/portal/access.py` (`staff_permissions` nur gültige Grants)
- `apps/web-portal/src/app/(portal)/uebergabeprotokolle/page.tsx`,
  `apps/web-portal/src/components/handover/StaffProtocolList.tsx`, `StartTiles.tsx`, `layout.tsx`,
  BFF und Dateiproxy (Positivlisten), `messages/de.json`, `messages/en.json`
- Tests: `tests/unit/test_m30_uprotokoll_import.py`,
  `tests/integration/test_m30_handover.py` (`test_uprotokoll_import_preview_apply_and_files`,
  `test_portal_handover_protocols_for_staff`, `test_staff_portal_grant_follows_role_change`),
  `apps/web-portal/src/components/handover/StaffProtocolList.test.tsx`, `StartTiles.test.tsx`
