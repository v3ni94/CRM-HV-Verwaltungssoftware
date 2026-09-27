# Dossier: Objektakte (uebernahme.muellerhv.de)

Stand 27.09.2026. Erhebung nach Anhang B des Master-Prompts (Abschnitt 13.2). Der vollständige
Anhang-B-Erhebungslauf im Objektakte-Projekt selbst steht laut Abschnitt 13.2 noch aus; dieses
Dossier fasst zusammen, was aus `docs/MASTER-PROMPT.md` und dem bereits bestehenden
Schnittstellenvertrag `docs/integrations/objektakte.md` (Milestone M29, Stufe 3/4) belegbar
ist. Für die technischen Details der Endpunkte gilt `docs/integrations/objektakte.md` als
maßgebliche Quelle; dieses Dossier bündelt sie im Anhang-B-Format.

## 1. Zweck

Bestehende Anwendung der HVM für die Übernahme neuer Verwaltungsobjekte: Massen-OCR und
Klassifikation von Übernahmeakten, Ablage in Google Drive je Objekt nach der Sechs-Ordner-
Struktur, Review Center, Requirement Engine, automatisch erzeugte Eigentümer- und
Mieterlisten (Excel und PDF). Verarbeitet laut Abschnitt 13.2 ein bis vier Objekte je Tag mit
1.000 bis 10.000 Seiten. Nutzer: HVM-Mitarbeiter im Onboarding-Prozess neuer Objekte.

## 2. Technik

Python, Docker Compose, MariaDB, Redis, Celery-Worker (OCR, IO, NLP, Control, Beat),
Verarbeitungsjobs je Objekt (`discover`, `hash`, `ocr_chunk`, `merge_pages`,
`render_previews`, `classify`, `file_to_drive`), KI-Klassifikation aus lokalem Modell und
externer KI, Ablage in Google Drive (Abschnitt 13.2). Weitere Konfigurationsvariablen,
Hosting-Details und Abhängigkeiten außerhalb von Drive: [zu ergänzen durch Betreiber].

## 3. Datenbestand

Aus der bereits produktiven lesenden API (`docs/integrations/objektakte.md`, Abschnitt 1)
belegbare Entitäten und Schlüssel:

- Objekt (`number`, Objektnummer als gemeinsamer Schlüssel mit dem CRM, `name`, `archived`,
  `takeover_status`, `open_review_cases`, Vollständigkeitskennzahlen, Drive-Ordnerverweis,
  Adresse).
- Dokument (`id`, `title`, `doc_type`, `category`, `subfolder`, `status`, `drive_file_id`,
  `drive_url`, `sha256`, `filed_at`, `mime_type`, `size_bytes`, seit der Erweiterung vom
  26.09.2026 zusätzlich `crm_document_id`, `paperless_id`, `open_review_cases`, `deleted`,
  `duplicate_of`).
- Eigentümer (`id`, `display_name`, `unit_labels`, `share`, `email_masked`, `iban_masked`,
  IBAN nie im Klartext).
- Mieter (`id`, `display_name`, `unit_labels`, `lease_start`, `lease_end`, `email_masked`).

Internes Datenmodell (Tabellen, Feldnamen, Beziehungen jenseits dieser API-Sicht) liegt nicht
vor: [zu ergänzen durch Betreiber].

## 4. Schnittstellen

Vollständig dokumentiert in `docs/integrations/objektakte.md`:

- Lesende REST-Schnittstelle (`https://uebernahme.muellerhv.de/api/crm/v1/`, Bearer-Token mit
  Scopes `objects:read`, `documents:read`, `persons:read`, seit Ergänzung auch
  `documents:write`, `persons:write`): Objektliste und -detail, Dokumentliste, Eigentümer- und
  Mieterlisten, Dokument-Upload aus dem CRM, Einheiten-/Personenexport aus dem CRM.
- Webhooks von objektakte an das CRM (`document.filed`, `object.taken_over`) mit
  HMAC-SHA256-Signatur (`X-Objektakte-Signature`).
- Authentifizierung: Bearer-Token, in objektakte nur als SHA-256-Hash mit Scopes gespeichert.

## 5. Ablösestatus im CRM (was ist bereits umgesetzt)

Die Anbindung ist bereits produktiv umgesetzt, nicht nur geplant:

- Modul `apps/api/src/mhvp/objektakte` (Milestone M29, Plan `docs/plans/M29-dms.md`).
- Endpunkte `/api/v1/integrations/objektakte/*`: Status, Objektliste und -detail,
  Dokumentliste mit `crm_document_id`, Verknüpfung nachholen, Eigentümer-/Mieterlisten,
  Importvorschlag (Abruf, Testlauf, Freigabe, Verwerfen) für Eigentümer- und Mieterdaten,
  Einheiten-/Personenexport an objektakte, Webhook-Empfang.
- Dokumentenverknüpfung (M6): abgelegte Dokumente werden CRM-Dokumente mit Verknüpfung zum
  Objekt gleicher Nummer, Abgleich über objektakte-ID, Drive-Datei-ID, Prüfsumme; kein
  Duplikat, Original bleibt in Drive.
- Upload aus dem CRM nach objektakte (Ergänzung 26.09.2026): Job
  `mhvp.objektakte.upload`, Tabelle `objektakte_upload` (Migration 0155), mit Fehler- und
  Wiederholungslogik, Rückmeldung über den Verarbeitungsstand.
- Eigentümer- und Mieterlisten als Importvorschlag (M8-Muster): Abgleich mit laufenden
  Verträgen, Freigabe ändert keine Stammdaten (`writes_master_data: false`).
- Einheiten- und Personenexport an objektakte (Ergänzung 27.09.2026): Übergabe einer
  Einheitenliste mit Namen laufender Eigentums- und Mietverträge, ohne Anschrift, E-Mail,
  Telefon oder Bankdaten.
- Fehlercodes `MHVP-OAK-0001` bis `MHVP-OAK-0003` für nicht eingerichtete Anbindung,
  Verbindungsfehler und unbekannte Objektnummer.
- Onboarding-Chat (Abschnitt 10.2 des Master-Prompts) soll die Klassifikationsergebnisse und
  generierten Listen als Eingabe für `extract_property` nutzen; ob dieser Chat-Baustein bereits
  produktiv ist: [zu ergänzen durch Betreiber, Verweis auf zuständiges Modul fehlt hier].

Empfehlung nach Abschnitt 13.2: anbinden als eigenständiger Dienst über REST und Webhooks,
keine Übernahme der OCR-/Klassifikationsfunktion in die Plattform. Diese Empfehlung ist bereits
umgesetzt; objektakte bleibt eigenständiger Fachdienst für Massen-OCR und Übernahmeakten.

## 6. Fachlogik, die erhalten bleiben soll

KI-Klassifikation von Dokumentkategorien und die Sechs-Ordner-Drive-Struktur bleiben in
objektakte; die Plattform übernimmt nur die klassifizierten Ergebnisse und Metadaten, ohne die
Klassifikationslogik nachzubauen (Abschnitt 13.2).

## 7. Bekannte Probleme und offene Punkte

- Der in Anhang B verlangte vollständige Erhebungslauf (README, Konfiguration, internes
  Datenmodell, Einstiegspunkte des objektakte-Quelltexts) wurde nicht durchgeführt; die
  bisherige Dokumentation beschreibt den Schnittstellenvertrag aus Sicht des CRM, nicht den
  internen Aufbau von objektakte.
- Kontakt-IDs werden beim Personenexport zwar gespeichert, wirken laut
  `docs/integrations/objektakte.md` aber noch nicht, weil objektakte Personen nicht mit der
  CRM-Kennung führt; Eigentümer und Mieter kommen dort weiterhin über den
  Immoware24-Listenimport herein.
- Löschung eines über objektakte abgelegten Dokuments im CRM löscht die Ablage in objektakte,
  Drive und Paperless nicht mit; die Löschung dort folgt eigenen Aufbewahrungsregeln.
- Technische Schulden, Hosting-Details und interne Fehleranfälligkeit von objektakte selbst
  sind mangels Repo-Zugriff nicht bekannt: [zu ergänzen durch Betreiber].
- Punkt V1 in `docs/OPEN_QUESTIONS.md` vermerkt für Objektakte weiterhin, dass der vollständige
  Anhang-B-Dossierlauf im Objektakte-Projekt aussteht.

## Zusammenfassung in zehn Zeilen

1. Objektakte ist die bestehende HVM-Anwendung für Massen-OCR und Klassifikation bei
   Objektübernahmen.
2. Sie bleibt eigenständiger Dienst; die Plattform bindet sie über REST und Webhooks an.
3. Die lesende Schnittstelle liefert Objekte, Dokumente, Eigentümer und Mieter, jeweils mit
   Objektnummer als gemeinsamem Schlüssel.
4. Webhooks von objektakte melden abgelegte Dokumente und abgeschlossene Übernahmen.
5. Die Anbindung im CRM ist bereits produktiv (Modul `mhvp.objektakte`, Milestone M29).
6. Dokumente werden automatisch mit CRM-Dokumenten verknüpft, ohne Duplikate.
7. Ein Upload-Pfad vom CRM nach objektakte inklusive Statusverfolgung existiert bereits.
8. Eigentümer- und Mieterlisten laufen als geprüfter Importvorschlag, ohne automatische
   Stammdatenänderung.
9. Interner Aufbau, Konfiguration und technische Schulden von objektakte selbst sind mangels
   Quelltextzugriff nicht bekannt.
10. Nächster Schritt: Betreiber führt den vollständigen Anhang-B-Erhebungslauf im
    Objektakte-Projekt aus und ergänzt die markierten Lücken.
