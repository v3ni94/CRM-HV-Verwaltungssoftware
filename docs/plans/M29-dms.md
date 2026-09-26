# M29 DMS: Objektübernahme (objektakte) an das CRM anbinden

Stand 25.09.2026. Quelle: Repository v3ni94/objekt-bernahme_automatisieren. (Kurzname objektakte),
läuft bereits auf dem Betreiberserver als Container-Stack objektakte-* (Django, HTMX, Celery,
MariaDB, Redis), Zieldomain uebernahme.muellerhv.de, Ablage in Google Drive (ablage@muellerhv.de).
Bestand laut Architektur: 67 Objekte, 869 Einheiten. Funktionen: Sechs-Ordner-Struktur je Objekt,
Upload, OCR, dreistufige Klassifikation (Regeln, lokales Modell, externe KI mit Maskierung),
Review Center, Eigentümer- und Mieterlisten, Vollständigkeitsprüfung, Nachforderungsschreiben.

## Entscheidung: vollständige Übernahme in dieses Repository (ersetzt frühere Entscheidung)

Betreiberentscheidung vom 25.09.2026: die frühere Entscheidung "nicht in dieses Repository
kopieren" ist aufgehoben. objektakte wird vollständig in dieses CRM überführt (Datenmodell,
Daten, Funktionen als Neubau, kein Code-Copy). Stufenplan, Datenmodellinventar,
Migrationsansatz, Risiken und Aufwandsschätzung stehen in
`docs/plans/M35-objektakte-uebernahme.md`. Die Stufen 1 bis 5 unten (Reiter DMS, SSO,
lesende Schnittstelle) sind damit hinfällig bzw. nur als Übergangslösung während des in
M35 beschriebenen Parallelbetriebs relevant.

## Stufen

1. **Reiter DMS im CRM** (ohne Änderung an objektakte): Absprung zu uebernahme.muellerhv.de je
   Objekt (Objektnummer NNN ist in beiden Systemen der Schlüssel), Erklärung der
   Ordnerstruktur, Link auf die Drive-Objektakte, sobald die Drive-Ordner-ID bekannt ist.
2. **Zentrale Anmeldung**: objektakte nutzt django-allauth; der Plattform-OIDC-Provider (ADR 0006
   Nr. 7) wird dort als Provider "openid_connect" konfiguriert. Konfiguration, kein Code.
   Benutzer werden weiterhin im CRM gepflegt.
3. **Lesende Schnittstelle in objektakte** (neuer Baustein im anderen Repository, Token mit
   Scopes): je Objekt Übernahmestatus, offene Review-Fälle, Vollständigkeitsprüfung,
   Dokumentliste (Titel, Klasse, Ordner, drive_file_id, sha256), Eigentümer- und Mieterliste.
   Ausgehender Webhook "Dokument abgelegt" und "Objekt übernommen" mit HMAC wie beim vorhandenen
   Paperless-Webhook. Keine direkte Datenbankkopplung (Datenschutz, IBAN-Schutz).
4. **CRM-Seite DMS mit Daten**: Kacheln je Objekt (Status, offene Fälle, fehlende Unterlagen),
   Dokumentliste mit Absprung in Drive, Verknüpfung der Dokumente als CRM-Dokumente (M6) über
   drive_file_id und sha256, Übernahme der Eigentümer- und Mieterlisten als Importvorschlag
   (M8-Muster, Testlauf, Abgleich, Freigabe).
5. **Später**: gemeinsame Objektnummernvergabe und Stammdatenführung nur im CRM; objektakte liest
   Objekte und Einheiten aus dem CRM.

## Voraussetzungen

- Entscheidung des Betreibers zu Stufe 3 (Auftrag für die Schnittstelle im objektakte-Repository;
  Schreibzugriff auf dieses Repository in einer eigenen Sitzung).
- Drive-Ordner-IDs je Objekt für den Absprung (liefert objektakte aus drive_nodes).
- Datenschutz: Zugriff des CRM nur auf maskierte Felder; keine IBAN im Klartext.

## Ergänzung 25.09.2026: Mail-Vorbereitung liest Paperless und Drive strikt je Objekt (M34, M20-05)

Für die Mail-Vorbereitung (Welle 3 Punkt 14, `docs/plans/M34-ki-wissensbasis.md`) muss die
Dokumentsuche eines eingehenden Vorgangs auf genau ein Objekt beschränkt bleiben, unabhängig von
den Stufen oben:

- **Paperless**: wiederverwendet die bestehende, bereits objektbeschränkte Suche aus M31
  (`mhvp.documents.paperless_search.PaperlessSearch.list_by_object_number`, Custom-Field
  `object_field_id`). Keine neue Schnittstelle.
- **Google Drive**: neu, `mhvp.documents.dms.GoogleDriveStore.search`. Sucht zuerst den
  Objektordner (`property_folder_name`, dieselbe Benennung wie beim Mirror-Job) unterhalb des
  konfigurierten Wurzelordners, fragt danach nur Dateien innerhalb dieses einen Ordners ab. Kein
  Zugriff auf den gesamten Drive-Bestand des Mandanten, siehe Regel `docs/rules/M20-05.md`.
- Ohne verbundenes DMS oder ohne auflösbares Objekt bleibt die Dokumentliste leer; ein DMS-Fehler
  unterbricht die Vorbereitung nicht.

## Ergebnis Stufe 4 (26.09.2026)

Grundlage ist der Schnittstellenvertrag in `docs/integrations/objektakte.md` (Stufe 3 wird im
objektakte-Repository umgesetzt). Stufe 4 im CRM:

- Client `mhvp.objektakte.remote` (httpx, Zeitlimit, Paginierung, Fehler als 502 an das
  Frontend), Einstellungen `OBJEKTAKTE_API_URL`, `OBJEKTAKTE_API_TOKEN`,
  `OBJEKTAKTE_WEBHOOK_SECRET`, `OBJEKTAKTE_TENANT` (leer bedeutet aus, `infra/compose.yaml`,
  `infra/env.prod.example`).
- Endpunkte `/api/v1/integrations/objektakte/...` (`mhvp.objektakte.dms_routers`) mit den
  vorhandenen Rechten `objektakte:*`, `documents:create`, `contacts:read`; keine neue Rolle.
- Webhook `POST /api/v1/integrations/objektakte/webhook` (`mhvp.objektakte.webhook`) mit
  HMAC-Prüfung und Idempotenz; `document.filed` wird als M6-Dokument mit Objektverknüpfung
  abgelegt (Abgleich über objektakte-ID, `drive_file_id`, `sha256`; M6 trägt das ohne neue
  Dokumenttabelle).
- Eigentümer- und Mieterlisten als Importvorschlag mit Testlauf, Abgleich und Freigabe
  (`objektakte_person_proposal`), ohne Schreiben in Stammdaten.
- Migration `0133_objektakte_dms` (Tabellen `objektakte_webhook_receipt`,
  `objektakte_person_proposal`, beide mit RLS).
- CRM-Seite `/dms` mit Kacheln je Objekt (Status, offene Fälle, Vollständigkeit, fehlende
  Unterlagen) und `/dms/{nummer}` mit fehlenden Unterlagen, Dokumentliste mit Absprung in Drive,
  Nachholen der Verknüpfung und Importvorschlag; ohne Anbindung Hinweis und Rückfall auf Stufe 1.
- Tests: `apps/api/tests/unit/test_m29_objektakte_remote.py`,
  `apps/api/tests/integration/test_m29_dms_objektakte.py` (Fake-Antworten über
  `httpx.MockTransport`, keine echten Aufrufe), `apps/web-crm/src/components/dms/*.test.tsx`.

Offen:

- Stufe 3 in objektakte (Endpunkte, Token-Kommando, Webhook-Versand) liegt noch nicht vor; die
  Anbindung ist bis dahin aus. Ein Abnahmetest gegen die echte Schnittstelle steht aus.
- Übernahme freigegebener Importvorschläge in die Stammdaten: bewusst nicht umgesetzt, weil die
  Listen keine Vertragsdaten (Eigentumsübergang, Vertragsbeginn der Eigentümer) und nur
  maskierte Kontaktdaten liefern. Entscheidung des Betreibers, ob ein Übernahmeschritt folgen
  soll (Betreiber, kein Gate betroffen).
- `takeover_status` wird so angezeigt, wie objektakte ihn liefert; eine deutsche Bezeichnung je
  Wert folgt, sobald die Werteliste im Vertrag festgelegt ist.
- `object.taken_over` wird nur protokolliert; eine Folgeaktion (zum Beispiel Objektstatus im
  CRM) ist nicht festgelegt.
## Stand 26.09.2026

Zusammenfassung aus den Nachträgen dieses Plans, dem `CHANGELOG.md` (1.19.0 bis 1.22.1) und der Lückenliste `docs/plans/LUECKENLISTE-2026-09-26.md`; keine neuen Sachverhalte.

* Im Code: Paperless-Anzeige in Ticket und Objekt (M31), Drive-Objektordnersuche für die Mail-Vorbereitung (Regel M20-05), vollständige Übernahme von objektakte nach `docs/plans/M35-objektakte-uebernahme.md` (Stufen 1 bis 5 mit Differenzimport und Synchronisationsstand), OIDC-Browserbrücke für externe Dienste (`docs/plans/M30-sso.md`).
* Die Stufen 1 bis 5 dieses Plans (Reiter DMS, SSO für objektakte, lesende Schnittstelle) sind durch die Entscheidung vom 25.09.2026 hinfällig; der Reiter `/dms` im CRM bleibt als Übergangslösung.
* Offen: M34-02 (Drive-Suche gegen echten Account), Entscheidungen in Abschnitt 7 von M35.
