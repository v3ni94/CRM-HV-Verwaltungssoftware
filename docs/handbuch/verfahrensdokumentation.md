# Verfahrensdokumentation (Entwurf für den Steuerberater)

Stand: 27.09.2026. Entwurf, keine steuerliche oder rechtliche Freigabe. Dieses Dokument ist
eine Arbeitsgrundlage für die Abstimmung mit dem Steuerberater beziehungsweise Wirtschafts-
prüfer zur GoBD-Konformität (Grundsätze zur ordnungsmäßigen Führung und Aufbewahrung von
Büchern, Aufzeichnungen und Unterlagen in elektronischer Form). Es ersetzt keine rechtliche
oder steuerliche Prüfung und keine Freigabe der Geschäftsführung. Lücken sind als
`[zu ergänzen]` gekennzeichnet; nur aus dem Repository belegbare Angaben sind ausgefüllt.

Produktive Buchführung ist gemäß den Freigabestufen G1 bis G5 (`docs/MASTER-PROMPT.md`
Abschnitt 18.0) gesperrt, solange der jeweilige Mandant sie nicht freigeschaltet hat
(Standard: aus). Diese Verfahrensdokumentation beschreibt das System, wie es technisch
angelegt ist; sie ist unabhängig vom Freigabestatus zu lesen und vor der ersten produktiven
Nutzung mit dem Steuerberater final abzustimmen.

## 1. Systembeschreibung

* Produkt: MH Verwaltungsplattform (Codename `mhvp`), selbst gehostete, mandantenfähige
  Software für Immobilienverwaltung (WEG, Miete, Sondereigentumsverwaltung), Betreiber Timo
  Müller.
* Mandanten (Stand 27.09.2026): Hausverwaltung Müller GmbH (erster Mandant), Timo Müller
  Einzelunternehmen (zweiter Mandant). Weitere Mandanten (Drittmandate) sind hinter
  Freigabestufe G5 gesperrt.
* Architektur: FastAPI-Backend (Python-Paket `mhvp`, `apps/api`), PostgreSQL als
  Datenbank, Next.js-Frontends `apps/web-crm` (Mitarbeiterinnen und Mitarbeiter) und
  `apps/web-portal` (Mieter, Eigentümer, Beirat, Dienstleister), Celery für asynchrone
  Aufgaben (Buchungsjobs, Postfachabruf, Sicherung). Objektspeicher für Dokumente:
  S3-kompatibel (Produktion: IONOS S3 Object Storage, `docs/runbooks/objektspeicher-ionos-s3.md`;
  Entwicklung: SeaweedFS-Container).
* Betrieb: ein IONOS Dedicated Server, Docker Compose, Traefik als Reverse Proxy
  (`docs/runbooks/server-setup.md`). Kein Hochverfügbarkeitscluster. `[zu ergänzen:
  Rechenzentrumsstandort und Auftragsverarbeitungsvertrag mit IONOS förmlich bestätigen]`.
* Datenmodell und Buchungslogik: `docs/MASTER-PROMPT.md` Abschnitt 6.9 (Datenmodell) und
  Abschnitt 7 (Rechnungswesen und Abrechnungen) sind bindend; Regeländerungen werden in
  `docs/rules/` mit Quellenstatus, ID und Änderungsgrund geführt.

## 2. Datenflüsse

* Erfassung: Stammdaten (Objekte, Einheiten, Verträge, Kontakte) werden manuell im
  Mitarbeiterportal `web-crm` erfasst oder aus Immoware24 importiert (Migrationsphase,
  `docs/runbooks/parallelbetrieb.md`). Banktransaktionen kommen über einen Kontoinformations-
  dienst (finAPI, Entscheidung V3 in `docs/OPEN_QUESTIONS.md`) oder per Datei-Upload.
  E-Mail-Kommunikation läuft über das Postfach `info@muellerhv.de` (Gmail-API-Anbindung).
* Verarbeitung: fachliche Vorgänge (Sollstellungen, Zahlungszuordnung, Abrechnungen) werden
  über die dokumentierte API des Backends abgebildet (API-first, Regel 0.1.4). Automatisierte
  KI-Vorschläge (z. B. Zuordnung von Zahlungen, Textentwürfe) sind ausdrücklich nur
  Vorschläge; es gibt keine automatische KI-Buchung ohne freigegebene, deterministisch
  überprüfbare Regel (Regel 0.1.6).
* Ausgabe: Auswertungen, Abrechnungen und Schreiben werden im jeweiligen Corporate Design
  erzeugt (Skills `hvm-ci`, `mhag-ci`, `tm-privat-ci`) und als Entwurf gekennzeichnet, bis eine
  Freigabestufe die produktive, rechtlich bindende Ausgabe erlaubt.
* Schnittstellen zu Dritten: Banking (finAPI), E-Mail (Gmail API), Messdienstleister
  (`docs/integrations/messdienstleister.md`, Stand: mehrere Anbieter ohne technische
  Endpunktdokumentation, siehe M40-01 bis M40-03 in `docs/OPEN_QUESTIONS.md`).
  `[zu ergänzen: vollständige Liste aller produktiv angebundenen Drittsysteme zum Zeitpunkt der
  Steuerberaterabstimmung]`.

## 3. Aufbewahrung

* Aufbewahrungsprofile sind fachlich in `docs/rules/M6-04-aufbewahrungsprofile.md` geregelt
  (Quellenstatus dort einsehen); Löschsperren nach Aufbewahrungsprofil verhindern die Löschung
  vor Fristablauf.
* Buchungssätze: nach Regel 0.1.7 werden gebuchte Datensätze nach dem Buchen weder
  überschrieben noch gelöscht; Korrekturen erfolgen ausschließlich durch Stornierung und, wo
  nötig, Neubuchung. Entwürfe sind von Buchungen technisch unterschieden.
* Dokumente: Objektspeicher mit Aufbewahrungsprofilen; ein Löschjournal protokolliert
  rechtmäßige Löschungen und wird nach einer Wiederherstellung erneut angewendet, damit
  gelöschte Dokumente nicht wieder erscheinen (D47, siehe Abschnitt 5 unten und
  `apps/api/src/mhvp/documents/deletion_journal.py`).
* Datensicherung: tägliche verschlüsselte Sicherung von Datenbank, WAL-Archiv und
  Dokumentenspeicher, Off-site-Kopie beim Betreiber (Hetzner Object Storage), siehe
  `docs/runbooks/backup.md`. Aufbewahrung der Sicherungen selbst (GFS-Rotation): 14 tägliche,
  8 wöchentliche, 12 monatliche Läufe; das ist eine Betriebssicherung, kein Ersatz für die
  steuerliche Aufbewahrungsfrist der Aufbewahrungsprofile.
* Aufbewahrungsfristen für steuerlich relevante Unterlagen (z. B. 6 oder 10 Jahre nach § 147
  AO) sind fachlich in den Aufbewahrungsprofilen zu hinterlegen. `[zu ergänzen: verbindliche
  Bestätigung der Fristen je Belegart durch den Steuerberater; die Plattform berechnet Fristen
  nur als Orientierung, siehe Regel 0.1.3]`.

## 4. Zugriffsrechte

* Technische Mandantentrennung: Row Level Security (RLS) auf jeder mandantenbezogenen
  Tabelle (`mhvp.core.db.rls.tenant_rls_statements()`); die zur Laufzeit verwendete
  Datenbankrolle ist nie Superuser, nie `BYPASSRLS`, nie Owner (ADR 0002).
  Rechtsträgertrennung (welcher Gesellschaft Forderungen, Guthaben, Bankmittel, Rücklagen und
  Kautionen zugeordnet sind) ist eine zweite, von der Mandantentrennung unabhängige Achse
  (Abschnitt 6.9.1, E01 des Master-Prompts) und wird je `legal_entity` geführt.
* Rollen- und Rechtemodell im Anwendungscode: `[zu ergänzen: aktuelle Rollenliste und
  Rechtematrix aus dem Code oder aus docs/rules zum Zeitpunkt der Abstimmung einfügen, z. B.
  Verweis auf die Zugriffsmatrix aus Meilenstein M21]`.
* Serverzugriff: SSH-Zugang zum Betriebsserver ist auf den Betreiber beschränkt; die
  Härtung (Schlüsselanmeldung, siehe `docs/runbooks/server-recovery-und-haertung.md` und der
  Vorschlag in `infra/hardening/`) ist Stand 27.09.2026 teilweise umgesetzt, die vollständige
  Umstellung ist als M9-05 in `docs/OPEN_QUESTIONS.md` offen.
* Protokollierung von Zugriffen und Änderungen: `[zu ergänzen: Audit-Log-Umfang und
  Aufbewahrungsdauer der Zugriffsprotokolle beschreiben, sobald abschließend umgesetzt]`.

## 5. Sicherung

* Regelmäßige Sicherung: `scripts/backup.sh` (täglich, verschlüsselt mit `age`), Off-site-
  Kopie nach Hetzner Object Storage (`scripts/backup-offsite.sh`), WAL-Archivierung für
  Point-in-Time-Recovery in der Produktion (`docs/runbooks/backup.md`).
* Wiederherstellungsprüfung: monatlicher lokaler Test (`make backup-verify`,
  `scripts/backup-verify.sh`), vierteljährliche vollständige Point-in-Time-Recovery-Probe und
  die hier neu eingeführte Restore-Übung `infra/scripts/restore-drill.sh` (Datenbank UND
  Objektspeicher gegen die Produktion abgeglichen, Protokoll unter
  `docs/reviews/restore-YYYY-MM-DD.md`), siehe `docs/runbooks/backup.md` Abschnitt
  "Restore-Übung".
* Löschjournal und Wiederherstellung (D47): wird eine Sicherung eingespielt, die rechtmäßig
  gelöschte Dokumente wieder enthält, wird das exportierte Löschjournal erneut angewendet,
  bevor Anwenderinnen und Anwender Zugriff erhalten (`apps/api/src/mhvp/documents/
  deletion_journal.py`, Test `apps/api/tests/integration/test_m9_restore_replay.py`).
* Notfallzugriff auf den Server (Verlust der SSH-Anmeldung, Kompromittierungsverdacht):
  `docs/runbooks/server-recovery-und-haertung.md` Abschnitt A und B.

## 6. Änderungsverfahren (Verfahren zur Software- und Regeländerung)

* Quellcodeverwaltung: Git, Repository `CRM-HV-Verwaltungssoftware`, Commits nach
  Conventional Commits, Versionierung in `VERSION` und `CHANGELOG.md` bei jeder
  ausgelieferten Änderung (semantische Versionierung, siehe `CLAUDE.md` Abschnitt
  "Versionierung").
* Migrationspfad der Datenbank: Alembic, jede Migration erhält eine feste, aufsteigende
  Nummer und ist idempotent (Spalten- und Tabellenprüfung vor Änderung); die Kette bleibt
  linear (`apps/api/alembic/versions/`).
* Fachliche Regeländerungen (z. B. neue oder geänderte Berechnungslogik) werden in
  `docs/rules/` mit ID, Geltungsbereich, Quellenstatus (Anhang C des Master-Prompts),
  Abnahmefall (Anhang D) und Änderungsgrund dokumentiert, bevor sie produktiv wirksam werden.
* Freigabeverfahren: neue produktive, geldwirksame Funktionen bleiben hinter den
  Freigabestufen G1 bis G5 gesperrt, bis der Betreiber sie je Mandant freischaltet
  (`docs/MASTER-PROMPT.md` Abschnitt 18.0, ADR 0003: keine globale Freischaltung).
* Test- und Freigabeschritte je Änderung: automatisierte Tests (pytest für das Backend,
  Playwright-Kernpfade für die Oberflächen), Pull-Request-Verfahren, danach Bereitstellung auf
  einer Staging-Umgebung vor der Produktivnahme (`CLAUDE.md` Abschnitt "Per task workflow").
* `[zu ergänzen: formales Freigabeprotokoll der Geschäftsführung für produktive
  Softwareänderungen an buchungsrelevanten Modulen, sofern vom Steuerberater verlangt]`.

## 7. Grenzen dieses Entwurfs

Dieses Dokument beschreibt den technischen und organisatorischen Stand des Repositorys am
27.09.2026. Es ist keine abschließende Verfahrensdokumentation im Sinne der GoBD und keine
Ersatzprüfung durch einen Steuerberater oder Wirtschaftsprüfer (Master-Prompt Abschnitt 0.2).
Vor produktiver Buchführung sind mindestens zu klären: die mit `[zu ergänzen]` markierten
Punkte, die noch offenen Betreiberentscheidungen zu Bankanbindung und Objektspeicher
(`docs/OPEN_QUESTIONS.md`, Abschnitte 1 und 4) sowie die Freigabe der Gates G1 bis G5 je
Mandant.
