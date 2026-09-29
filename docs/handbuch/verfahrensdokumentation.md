# Verfahrensdokumentation (Entwurf für den Steuerberater)

Stand: 27.09.2026, Kapitel 7 vom 29.09.2026. Entwurf, keine steuerliche oder rechtliche Freigabe. Dieses Dokument ist
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

## 7. Automatik der Buchhaltung (Regeln M12-04, M12-05, M12-06)

Stand 29.09.2026, aus dem Code abgeleitet (`apps/api/src/mhvp/banking/`: `proposals.py`,
`features.py`, `posting_proposal.py`, `levels.py`, `verifiers.py`, `runner.py`, `review.py`,
`learning.py`; Regeln in `docs/rules/M12-04-lernender-buchhalter.md`,
`M12-05-automatikstufen-runner.md`, `M12-06-gelernte-bankregeln.md`; ADR 0014 mit Nachtrag).
Die Automatik ist Produktschutz nach Kapitel 7.4 des Master-Prompts, keine Rechtsnorm. Sie
bucht nur über freigegebene, deterministisch nachprüfbare Regeln; Konfidenz einer Vorschlags-
engine oder eines KI-Modells ist nie Auslöser einer Buchung. Nichts in diesem Kapitel öffnet
eine Freigabestufe.

### 7.1 Grundsatz und Schalter

* Vorschlag statt Buchung: Jeder Bankumsatz erhält Vorschläge (Stufe 1, deterministisch aus
  offenen Posten, Bankregeln, Verlauf der Gegenpartei, verknüpften Rechnungen, Buchungstexten
  der Konten, Transferpaaren). Ein Vorschlag bucht nichts. Gebucht wird durch eine Person oder,
  ab Stufe L2, durch den Runner nach Prüfung durch den Verifier der Fallklasse.
* Mandantenschalter (alle Standard aus): `learning_bookkeeper_enabled` (Entscheidungsspeicher
  und Lernen; Änderung nur mit den Rechten Buchhaltung freigeben und Mandanteneinstellungen
  ändern, mit Grund, Ereignis `tenant.learning_bookkeeper_changed`, `PUT /banking/learning`),
  `auto_posting_enabled` (Runner), `auto_posting_outgoing_enabled` (Ausgänge gegen Sachkonto,
  `PUT /banking/automation/outgoing`). Schwellen der Regelvorschläge:
  `bank_rule_proposal_threshold` (Standard 5) und `bank_rule_recurring_threshold` (Standard 3,
  beide 2 bis 50, `PATCH /tenant/settings`).
* Datenschutz: Der Entscheidungsspeicher enthält Zahlerdaten nur pseudonym (IBAN-Fingerabdruck,
  Kennungen), keine Namen, keinen vollen Verwendungszweck, keine Klar-IBAN. Betreiberentscheidung
  vom 28.09.2026 (M12-06): Aufbewahrung 24 Monate, Löschung mit dem Kontakt, Leserecht auf
  Nachweise nur für die Buchhaltung. Der tägliche Löschlauf ist noch nicht umgesetzt, weil der
  Datenbank-Trigger jedes Löschen verbietet; bis zur Entscheidung über die Ausnahme bleibt der
  Schalter je Mandant aus (`docs/OPEN_QUESTIONS.md` M12-06, M12-09 Nr. 6).

### 7.2 Entscheidungsprotokoll je Bankumsatz (M12-04)

* Nach jedem Import (Datei, CSV, finAPI, FinTS) berechnet der Task `mhvp.banking.compute_proposals`
  je offenem Umsatz den Snapshot der Vorschläge und speichert ihn in der Tabelle
  `posting_decision` (Zustand `pending`) mit Engine-Version, Regelversion, Merkmalshash,
  Fallklasse, bester Quelle und Konfidenz. Je Umsatz gibt es höchstens eine offene Runde; ändert
  sich der Merkmalshash (neuer offener Posten, freigegebene Regel, freigegebene Zahler-IBAN),
  wird die alte Runde `expired` und eine neue mit Verweis angelegt.
* Die Entscheidung einer Person schließt die Runde genau einmal: `accepted_unchanged` (genau
  der gewählte Vorschlag), `modified` (Abweichung als Diff aus Posten, Gegenkonto und Skonto),
  `rejected` (Pflichtgrund, mindestens drei Zeichen), `ignored`, `reversed` (Storno als
  Gegenbeispiel). Massenbestätigungen tragen `bulk = true`. Eine veraltete Runde wird mit 409
  `MHVP-BANK-0021` abgewiesen, nichts wird gebucht.
* Unveränderlichkeit: Der Trigger `mhvp_posting_decision_guard` verbietet das Löschen, erlaubt
  nur den Übergang von `pending` in einen Endzustand und sperrt geschlossene Zeilen vollständig
  (Regel B03 für das Protokoll).
* Lernquelle sind ausschließlich Entscheidungen von Personen an nicht stornierten Buchungen.
  Automatikbuchungen, das Immoware24-Journal, Importrohzeilen, Migrationsjournal, Entwürfe und
  nicht gebuchte Modellantworten sind nie Lernquelle (7.4 Nr. 6).

### 7.3 Fallklassen und Stufen (M12-05)

Jeder Bankumsatz wird deterministisch einer Fallklasse zugeordnet (`levels.classify`):

| Klasse | Bedeutung | Höchste Stufe |
| --- | --- | --- |
| `debtor_full` | Eingang gleicht genau einen offenen Posten voll aus | L3 |
| `debtor_collective` | Eingang gleicht genau eine Kombination offener Posten aus | L1 |
| `creditor_invoice` | Ausgang zu einer verknüpften gebuchten Rechnung | L2 |
| `recurring_expense` | Ausgang gegen Sachkonto nach Regel der Art `posting` | L2, nur mit `auto_posting_outgoing_enabled` |
| `transfer_pair` | Umbuchung zwischen eigenen Konten (Fall D04) | L3 |
| `excluded` | Rückläufer, Kaution, Teil- und Überzahlung, unklar | L0 |

Stufen je Mandant und Klasse (`tenant_settings.bookkeeping_automation`, Standard L0):

* L0: nur Vorschlag.
* L1: Schaltfläche Übernehmen (`POST /banking/transactions/{id}/accept`) und Vorauswahl
  deterministisch geprüfter Vorschläge in der Massenbestätigung. Jede Buchung bleibt eine
  manuelle Buchung der Person (`created_by` gesetzt); Verlaufs- und KI-Vorschläge werden nie
  vorausgewählt.
* L2: Der Runner bucht nach jedem Import und Sync; Nachkontrolle am nächsten Werktag;
  überfällige Nachkontrollen sperren die Klasse.
* L3: Gleicher Buchungspfad; Nachkontrolle nur für die deterministische Stichprobe (Hash der
  Umsatzkennung, 10 Prozent, Fälligkeit 7 Tage), nur `debtor_full` und `transfer_pair`;
  produktiv erst nach M12-08 und G1.

Anhebung einer Stufe: nur eine Stufe je Antrag, Antrag mit Eignungsbericht als Nachweis
(`POST /banking/automation/level-requests`, Tabelle `bookkeeping_level_request`), Freigabe durch
eine andere Person (`.../approve`, kein Plattformadministrator), Ereignisse
`bookkeeping_level.requested` und `bookkeeping_level.changed`. Absenkung durch eine Person
sofort (`PUT /banking/automation/levels`). Eignungsschwellen (Produktschutz, Annahme A-085,
`levels.ELIGIBILITY`): L1 ab 20 entschiedenen Fällen in 90 Tagen mit manueller Präzision
mindestens 0,95; L2 zusätzlich 30 Tage auf L1, 50 Fälle, Präzision mindestens 0,98; L3
zusätzlich 60 Tage auf L2, mindestens 100 Automatikbuchungen und Fehlerquote höchstens 0,005.
Automatische Herabstufung (Nachtjob `mhvp.banking.levels_refresh`, nur abwärts): Fehlerquote
der Automatik über 30 Tage größer 0,02 (L3: 0,01) senkt eine Stufe; drei Korrekturen einer
L1-Klasse in 30 Tagen senken auf L0. Oberfläche: Einstellungen, Buchhaltung, Automatikstufen.

### 7.4 Verifier (deterministische Nachprüfung)

Vor jeder Automatikbuchung berechnet der Verifier der Klasse (`verifiers.py`,
`VERIFIER_VERSION 2026.09.29-1`) den Fall zum Buchungszeitpunkt neu und antwortet mit
Erlaubnis oder Ablehnung, der exakten Buchung, den Gründen und einem Fingerprint (SHA-256 über
Verifier-, Engine- und Regelversion, Merkmalshash, Regel, Klasse und Buchung). Gemeinsame
Prüfungen aller Klassen:

* aktive Bankregel des Rechtsträgers, Betrag innerhalb `max_amount` der Regel;
* Chronologie: bei Debitoren muss der ausgeglichene Posten der älteste offene Posten des
  Schuldners sein, sonst bleibt die Zahlung manuell (D39);
* Konto-Sperrkriterien: Gegenkonto und Debitorenkonto ohne Umsatzsteueroption, ohne
  Vorsteuerregel, ohne Kennzeichen § 35a und ohne Prüfstatus Entwurf (keine steuerliche
  Einordnung aus Mustern, M14-02);
* Periodensperre: ein Buchungstag in der festgeschriebenen Periode wird gezählt und
  übersprungen, nie umdatiert.

Je Klasse zusätzlich: `debtor_full` verlangt Vertragsnummer oder Mandatsreferenz im Nachweis
(IBAN, Betrag und Periodenhinweis allein bleiben manuell), Betrag gleich Rest, kein
Kautionsposten; `creditor_invoice` verlangt Rechnungsbetrag gleich Zahlbetrag, Empfänger-IBAN
wie Rechnung, Kontierung aus der Rechnung; `recurring_expense` verlangt Historie gleich
Regelkonto, Betrag in der beobachteten Spanne, keine abweichende offene Verbindlichkeit und die
Belegkette B05 (verknüpfter Beleg oder Kennzeichen `no_receipt_required` einer Person), sonst
entsteht ein Klärungsereignis `bank_transaction.clarification_needed` statt einer Buchung;
`transfer_pair` verlangt, dass das Partnerkonto ein Bankkonto des Buchungskreises ist.

### 7.5 Runner

Der Runner (`runner.py`) läuft nach jedem Import und Sync (`tasks.compute_proposals_once`) und
auf `POST /banking/auto-post`, je Mandant durch eine Advisory-Transaktionssperre serialisiert, je
Umsatz im Savepoint mit Zeilensperre. Voraussetzungen, alle im Runner geprüft und nie durch
Konfidenz ersetzt: Schalter `auto_posting_enabled` und `learning_bookkeeper_enabled`, Klasse auf
L2 oder L3 und nicht durch überfällige Nachkontrolle gesperrt, Freigabestufe G1 offen oder
Buchungskreis nicht führend (Betreiberentscheidung M12-07 vom 28.09.2026: Vergleichsbuchungen
im nicht führenden Buchungskreis sind erlaubt), aktive Regel mit bestandenem Verifier.
Fallgrenzen (Annahme A-087): 50 Buchungen je Regel und Tag, 200 je Lauf, 500 je Mandant und
Tag; Erreichen stoppt den Lauf mit Ereignis `bank_auto_post.run_stopped`. Jede Automatikbuchung
erzeugt: Buchung ohne Person (`created_by` leer, Quelle Bankimport), Entscheidung `auto_posted`
mit Fingerprint und Fälligkeit der Nachkontrolle, Nachkontrolle-Item, Ereignis
`bank_transaction.auto_posted`, Zähler `auto_*` im Sync-Lauf.

### 7.6 Nachkontrolle und Korrektur

* `GET /banking/auto-posting/reviews` listet offene Nachkontrollen mit Fälligkeit; die
  Entscheidung `ok` braucht das Recht `accounting:review` (Oberfläche: Bank, Nachkontrolle).
* Korrektur ausschließlich nach Regel B03: `POST /banking/transactions/{id}/correct` storniert
  die gültige Buchung mit Grundcode (`input_error`, `wrong_assignment`, `wrong_amount`,
  `wrong_date`, `duplicate`, `bank_return`, `run_reversal`, `automation_error`, `other`) und
  Freitext, schließt die Nachkontrolle als `corrected` und bucht den Umsatz in derselben
  Transaktion neu als manuelle Buchung der Person (neue Entscheidungsrunde). Ein gebuchter Satz
  wird nie geändert. Ein Storno über den Buchungskreis ohne Neubuchung schließt die
  Nachkontrolle als `cancelled`.
* Der Watermark-Job (`events_consumer.py`, Beat `mhvp.banking.process_events`) schreibt das
  Gegenbeispiel, zählt den Widerspruch an der Regel (`contradiction_count`) und stuft die Regel
  bei Grundcode `automation_error` von aktiv auf freigegeben zurück; ein zweiter Fall schaltet
  sie ab (`bank_rule.downgraded`).

### 7.7 Gelernte Bankregeln (M12-06)

* Nach jeder Entscheidung einer Person bildet `learning.observe` die neueste widerspruchsfreie
  Folge gleicher Entscheidungen derselben Gegenpartei, desselben Rechtsträgers und derselben
  Richtung (Kontomuster ohne Bankkonto). Gewicht 1 je Entscheidung, 0,5 je Massenbestätigung.
  Erreicht die Folge die Schwelle (5, bei identischen Beträgen 3), entsteht ein Vorschlag
  `bank_rule_proposal` mit Nachweis (Entscheidungs- und Umsatzkennungen, Zeitraum, Beträge),
  Betragsspanne, Zwecktoken (in jedem Fall enthalten, höchstens fünf, keine Namen und
  Stoppwörter) und Aktionsart. Splits werden nicht gelernt; bestehende Regeln gleichen Schlüssels
  verhindern den Vorschlag.
* Widerspruch (anderes Konto, Ablehnung, Storno) zieht den Vorschlag zurück; nach einer
  Ablehnung erscheint das Muster erst bei doppeltem Nachweis erneut.
* Annahme (`POST /banking/rule-proposals/{id}/accept`, Recht Buchhaltung freigeben) erzeugt die
  Bankregel im Zustand vorgeschlagen; verengen ist erlaubt, erweitern wird mit 422
  `MHVP-BANK-0024` abgewiesen. Die annehmende Person darf die Regel nicht freigeben. Freigabe und
  Aktivierung folgen dem bestehenden Vier-Augen-Pfad mit `max_amount` und Testnachweis (D51);
  die Aktivierung ersetzt ältere gelernte Regeln desselben Schlüssels (`bank_rule.superseded`).
  Oberfläche: Bank, Regeln.

### 7.8 Nachweise und Prüfexport

Der Prüfexport (Kapitel 3 und `mhvp.accounting.audit_export`, Fall D55) enthält die Tabellen
`entscheidungen` (Entscheidungsprotokoll mit Fingerprint), `nachkontrolle`, `automatikstufen`
(Anträge und Entscheidungen), `regelvorschlaege` und `bankregeln` neben Journal, Belegen und
Freigaben. Ereignisse: `bank_transaction.booked` (mit Entscheidungskennung, Quelle, Skonto,
Bulk), `bank_transaction.proposal_rejected`, `bank_transaction.reopened`,
`bank_transaction.posting_reversed`, `bank_transaction.auto_posted`,
`bank_transaction.clarification_needed`, `bank_transaction.corrected`, `bank_auto_post.run_stopped`,
`auto_posting_review.decided`, `bookkeeping_level.requested`, `bookkeeping_level.changed`,
`bank_rule.proposed`, `bank_rule.approved`, `bank_rule.activated`, `bank_rule.disabled`,
`bank_rule.superseded`, `bank_rule.downgraded`, `bank_rule_proposal.created`, `.withdrawn`,
`.accepted`, `.rejected`, `tenant.learning_bookkeeper_changed`,
`tenant.auto_posting_outgoing_changed`.

### 7.9 Versionen

| Kennung | Wert | Bedeutung |
| --- | --- | --- |
| `ENGINE_VERSION` | `2026.09.28-2` | Vorschlagsengine Stufe 1 (`posting_proposal.propose`) |
| `RULE_VERSION` | `2026.09.28-2` | Merkmalsextraktion (`features.collect`), Teil des Merkmalshashs |
| `VERIFIER_VERSION` | `2026.09.29-1` | Verifier je Fallklasse, Teil des Fingerprints |
| Migrationen | `0232`, `0241` | Entscheidungsspeicher; Stufen, Anträge, Nachkontrolle, Regelvorschläge |

Jede Änderung der Merkmale, der Engine oder des Verifiers erhöht die jeweilige Kennung; alte
Entscheidungen behalten ihre Kennungen, so dass jede Automatikbuchung dem geprüften Stand
zugeordnet bleibt.

### 7.10 Verantwortlichkeiten

| Aufgabe | Verantwortlich | Recht in der Software |
| --- | --- | --- |
| Schalter lernender Buchhalter und Ausgangsautomatik | Betreiber Buchhaltung, nach Datenschutzfreigabe M12-06 | `accounting:approve` und `tenant_settings:update` |
| Antrag auf Anhebung einer Stufe | Buchhaltung (eine Person) | `accounting:update` |
| Freigabe der Anhebung | andere Person der Buchhaltung, kein Plattformadministrator | `accounting:approve` |
| Absenkung einer Stufe | jede Person der Buchhaltung, sofort | `accounting:update` |
| Nachkontrolle der Automatikbuchungen | Buchhaltung, täglich am Werktag | `accounting:review` |
| Korrektur (Storno mit Grundcode und Neubuchung) | Buchhaltung | `accounting:update` |
| Annahme, Freigabe und Aktivierung von Regelvorschlägen | zwei verschiedene Personen | `accounting:approve` |
| Prüfexport für Steuerberatung und Prüfung | Buchhaltung | `accounting:export` |
| Freigabestufe G1 | Antrag Betreiber, Entscheidung zweite Person auf der Plattform | `release_gates:create`, Plattformadministrator |

Offene Punkte (Stand 29.09.2026): Ausschluss nicht nachkontrollierter Automatikbuchungen aus
Mahnlauf, Tilgungsvorschlag und Lastschriftlauf (bis dahin keine Stufe L2 für Mandanten mit
produktivem Mahn- oder Lastschriftlauf); Rückläufer als Nachkontrolle-Item; Feiertage in der
Fälligkeit; Löschlauf 24 Monate; Kennzeichnung von Regeln ohne Treffer seit 180 Tagen. Die
Öffnungsliste steht in `docs/OPEN_QUESTIONS.md` M12-09 und in der Software unter Einstellungen,
Buchhaltung, G1 Öffnung.

## 8. Grenzen dieses Entwurfs

Dieses Dokument beschreibt den technischen und organisatorischen Stand des Repositorys am
27.09.2026 (Kapitel 7: 29.09.2026). Es ist keine abschließende Verfahrensdokumentation im Sinne der GoBD und keine
Ersatzprüfung durch einen Steuerberater oder Wirtschaftsprüfer (Master-Prompt Abschnitt 0.2).
Vor produktiver Buchführung sind mindestens zu klären: die mit `[zu ergänzen]` markierten
Punkte, die noch offenen Betreiberentscheidungen zu Bankanbindung und Objektspeicher
(`docs/OPEN_QUESTIONS.md`, Abschnitte 1 und 4) sowie die Freigabe der Gates G1 bis G5 je
Mandant.
