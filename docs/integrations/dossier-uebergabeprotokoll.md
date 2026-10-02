# Dossier: Übergabeprotokoll (U-Protokoll)

Stand 27.09.2026. Erhebung nach Anhang B des Master-Prompts (Abschnitt 13.4). Der Quelltext
des Bestandsprojekts „Übergabeprotokoll“ liegt dem Plattform-Repo nicht vor. Dieses Dossier
fasst zusammen, was aus `docs/MASTER-PROMPT.md`, `docs/OPEN_QUESTIONS.md` (Punkt V1) und dem
bereits vorhandenen Plattformmodul `handover` (das die Datenübernahme aus „U-Protokoll“
referenziert) belegbar ist.

## 1. Zweck

Digitale Wohnungsübergabe (Einzug, Auszug) mit Zählerständen, Schlüsseln, Mängeln, Fotos und
Unterschriften (Abschnitt 13.4). [Betreiber-Erhebung offen, V1: zu ergänzen durch Betreiber: genaue Nutzergruppe,
Ablauf im Bestandsprogramm, Anzahl Protokolle pro Jahr, mobile Erfassung ja/nein].

## 2. Datenbestand

Kein Zugriff auf das Datenmodell des Bestandsprojekts. Im Plattformmodul `handover` existiert
bereits ein Parser für einen „U-Protokoll-Datenbankexport“
(`apps/api/src/mhvp/handover/uprotokoll_import.py`, Router
`apps/api/src/mhvp/handover/imports.py`, Endpunkt `/api/v1/handover/imports/uprotokoll`),
was auf ein exportierbares Datenbankschema des Bestandsprojekts hindeutet. Die konkrete
Feld- und Tabellenstruktur des Exports selbst ist [Betreiber-Erhebung offen, V1: zu ergänzen durch Betreiber].

## 3. Schnittstellen

Keine API des Bestandsprojekts bekannt; die Datenübernahme läuft über einen Datenbankexport,
nicht über eine Live-Schnittstelle. [Betreiber-Erhebung offen, V1: zu ergänzen durch Betreiber: Exportformat, Häufigkeit,
ob eine REST-Schnittstelle oder nur ein Exportjob existiert].

## 4. Ablösestatus im CRM

Die Plattform hat das Zielbild aus Abschnitt 13.4 bereits als eigenes Modul umgesetzt:

- Modul `apps/api/src/mhvp/handover` (Milestone M30, Plan
  `docs/plans/M30-uebergabeprotokoll.md`, Regel `docs/rules/M30-01.md`).
- Datenmodell: `handover_protocol` (Adress- und Einheitensnapshot, Kaution, interne Felder,
  Abschluss, PDF-Verweis) mit Teildatensätzen `handover_participant`, `handover_meter`,
  `handover_room`, `handover_defect`, `handover_key`, `handover_item`, `handover_note`,
  `handover_signature`.
- Erzeugt bereits die in Abschnitt 13.4 geforderten Folgeobjekte: Zählerstände über den
  optionalen Bezug `handover_meter` zu den Stammdaten-Zählern
  (`apps/api/src/mhvp/metering`), Mängel als Grundlage für Tickets (Teildatensatz
  `handover_defect`; Verknüpfung zur Ticketanlage laut Modul-README vorgesehen), Dokumente
  über die allgemeine Dokumentenverknüpfung (`documents.services.LINKABLE`), PDF auf dem
  Briefbogen des Mandanten (`handover/pdf.py`).
- Portalzugang je Beteiligtem (`handover/portal.py`, `/api/v1/portal/handover`), Bildbereinigung
  für Fotos inklusive HEIC/HEIF (`handover/images.py`, Aufgaben M30-04, A55, A58, A72).
- Datenübernahme aus U-Protokoll ist als eigene Stufe bereits angelegt (`imports.py`,
  `uprotokoll_import.py`, Milestone M30 Stufe 4), das heißt die Migration bestehender
  U-Protokoll-Daten in die Plattform ist technisch vorbereitet.

Noch nicht umgesetzt beziehungsweise offen laut Modul-README (`handover/README.md`):
Zustellung des Einladungscodes für den Portalzugang (M30-01), Entfernen von Bildmetadaten war
zum README-Stand noch offen und ist laut Nachtrag inzwischen in `images.py` umgesetzt, zweiter
Faktor für Gehilfen (M30-05).

## 5. Offene Punkte

- Kein Erhebungslauf nach Anhang B im Bestandsprojekt „Übergabeprotokoll“ durchgeführt;
  Zweck, Technik, Datenmodell, Schnittstellen und bekannte technische Schulden des
  Bestandsprojekts selbst sind unbekannt, abgesehen vom indirekt belegten
  Datenbankexportformat.
- Ob das Bestandsprojekt und der bereits vorhandene `uprotokoll_import`-Parser zueinander
  kompatibel sind (Feldnamen, Version des Exportformats), ist ohne Sichtung des
  Bestandsprojekts nicht zu bestätigen.
- Empfehlung aus Abschnitt 13.4 lautet „Übernahme als Modul der Plattform oder Anbindung per
  API“; die Plattform hat die Übernahme als Modul bereits vollzogen. Eine endgültige
  Stilllegung des Bestandsprojekts setzt die erfolgreiche Datenübernahme aller offenen
  Altprotokolle voraus, was der Betreiber bestätigen muss.
- Punkt V1 in `docs/OPEN_QUESTIONS.md` bleibt für das Übergabeprotokoll als offen vermerkt,
  bis der Betreiber den Anhang-B-Lauf im Bestandsprojekt ausführt.

## Zusammenfassung in zehn Zeilen

1. Das Übergabeprotokoll ist ein Bestandsprojekt der HVM ohne im Repo vorliegenden Quelltext.
2. Die Plattform hat den Zielzustand aus Abschnitt 13.4 bereits als Modul `handover` (M30)
   umgesetzt.
3. Zählerstände, Mängel, Dokumente und Vertragsereignisse werden bereits im Protokoll
   erfasst und verknüpft.
4. PDF-Erzeugung auf dem Briefbogen des Mandanten ist vorhanden.
5. Portalzugang je Beteiligtem ist umgesetzt, Einladungszustellung noch offen (M30-01).
6. Ein Importpfad für einen U-Protokoll-Datenbankexport existiert bereits (M30 Stufe 4).
7. Das genaue Datenmodell des Bestandsprojekts selbst ist nicht bekannt.
8. Eine Live-Schnittstelle des Bestandsprojekts ist nicht dokumentiert.
9. Kompatibilität des Exportformats mit dem vorhandenen Parser ist ungeprüft.
10. Nächster Schritt: Betreiber führt den Anhang-B-Prompt im Bestandsprojekt aus und bestätigt
    die Ablösereife.

## Ergänzung 01.10.2026 (GA09-02): Faktenstand aus dem Repo

Nur Angaben, die im Repo belegt sind (`apps/api/src/mhvp/handover/uprotokoll_import.py`,
`docs/plans/M30-uebergabeprotokoll.md`). Alles andere ist offen, [Betreiber-Erhebung offen, V1, AA16-03].

- Zweck: Wohnungsübergabe mit Protokollarten Miete, Verkauf und allgemein (`rental`, `sale`,
  `general`); Zählerstände, Schlüssel, Mängel, Räume, Positionen, Notizen, Dateien,
  Unterschriften, Versionen und E-Mails je Protokoll.
- Stack: PHP mit MariaDB, Quellrepository `github.com/v3ni94/UProtkoll`, Schema in
  `database/migrations/001_create_schema.sql` dieses Repositorys (laut Modulkopf des Importers).
  Hosting, Webserver und Betrieb: offen, [Betreiber-Erhebung offen, V1, AA16-03].
- Datenmodell: 13 Tabellen werden gelesen: `protocols`, `protocol_participants`,
  `protocol_bank_details`, `protocol_meters`, `protocol_rooms`, `protocol_defects`,
  `protocol_keys`, `protocol_items`, `protocol_notes`, `protocol_files`,
  `protocol_signatures`, `protocol_versions`, `protocol_emails`. Folgeprotokolle sind über
  `parent_protocol_id` verknüpft. Spaltenweise Belegung: offen, [Betreiber-Erhebung offen, V1, AA16-03].
- Schnittstellen: `mysqldump` (utf8mb4), gelesen ohne SQL-Ausführung, Vorschau vor Übernahme,
  Übernahme idempotent je Quell-ID (`uprotokoll:<protocols.id>`); Binärdateien aus einem
  ZIP des Speicherverzeichnisses, zugeordnet über Pfad oder SHA-256. Eine Live-Schnittstelle
  ist nicht belegt.
- Status: Zielmodul `handover` (M30) umgesetzt, Import Stufe 4 vorhanden, Bestandsprojekt
  nicht stillgelegt. Anhang-B-Lauf offen (AA16-03).
