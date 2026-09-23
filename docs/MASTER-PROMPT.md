# MASTER-PROMPT: MH Verwaltungsplattform

Arbeitstitel: **MH Verwaltungsplattform** (Codename `mhvp`). Produktträger: Müller Holding AG. Erster Mandant: Hausverwaltung Müller GmbH. Zweiter Mandant: Timo Müller (Einzelunternehmen). Zielmarkt: mittelständische Immobilienverwalter in Deutschland (WEG, Miete, Sondereigentumsverwaltung).

Version **2.0 Final**, Stand **23.09.2026**. Konsolidierte Fassung aus Version 1.1.1 (Claude, Grundlage: Immoware24-Strukturanalyse WDB-07, Anforderungskatalog WDB-08, Marktrecherche), dem Fachreview 1.1.2 (ChatGPT, Schwerpunkt Buchhaltung, WEG-Recht, Belegprüfung, Abnahmefälle, Quellenregister) und der abschließenden Prüfung durch Claude, in der die im Fachreview offen gelassenen technischen Konflikte E01 bis E16 entschieden und in das Datenmodell übernommen wurden (Abschnitt 6.9 und Anhang E).

**Freigabestatus.** Dieses Dokument ist die freigegebene Arbeitsgrundlage für die Entwicklung ab Meilenstein M1. Die Freigabe zur Entwicklung ist getrennt von den Freigaben für produktive Buchführung, Zahlungen und Abrechnungen (Stufen G1 bis G5 in Abschnitt 18.0). Bestands-Repositories, Originalverträge und echte Abrechnungsdaten lagen weder dem Fachreview noch der Abschlussprüfung vor; die davon abhängigen Punkte stehen in Abschnitt 19 und Anhang C.2 mit Zuständigkeit.

**Lesepfad für den Coding-Agenten:** Abschnitt 0 (Regeln), 1 bis 5 (Ziel, Architektur, Stack, Mandanten), 6 (Datenmodell inklusive 6.9), 7 (Buchhaltung und Abrechnung), 8 bis 15 (Module), 18 (Umsetzungsplan mit Freigabestufen), Anhang D (Abnahmefälle), Anhang E (entschiedene Konflikte). Anhang C ist das Quellenregister für alle rechtlichen Regeln.

---

## 0. Anweisungen an den Coding-Agenten

### 0.1 Zuständigkeit, Arbeitsweise und Freigabe

Du bist der leitende Softwarearchitekt und Entwickler. Stack, Komponenten, Hosting, Repository-Aufteilung und technische Umsetzung bleiben in deiner Verantwortung. Dieses Fachreview definiert das erforderliche fachliche Verhalten, nicht neue Frameworks oder eine neue Architektur.

1. **Entwicklung ist freigegeben, Geld nicht.** Mit dem Startauftrag des Betreibers („Lies docs/MASTER-PROMPT.md und beginne mit Meilenstein M1“) legst du das Repo nach Abschnitt 17 an und arbeitest die Meilensteine aus Abschnitt 18 in Reihenfolge ab. Produktive Buchführung, echte Zahlungsaufträge, rechtlich maßgebliche Abrechnungen und Fremdmandanten bleiben bis zur jeweiligen Freigabestufe G1 bis G5 gesperrt (Feature-Flags je Mandant, Standard aus). Vorhandenen Code liest du zuerst und dokumentierst Abweichungen, bevor du änderst.
2. **Phasenfolge bleibt erhalten.** Nach Freigabe gilt Abschnitt 18. Die frühe fachliche WEG-Prüfung ist kein Auftrag, Phase 4 vorzuziehen. Die in Abschnitt 6.9 entschiedenen Schemaänderungen (Rechtsträger-Buchungskreise, Eigentumsdaten, Statusmodell der Abrechnung, Freigabeversionen) gehören zum Phase-1-Schema, damit die WEG-Logik in Phase 4 nicht an einem ungeeigneten Kernmodell scheitert. Darüber hinaus werden keine Felder auf Vorrat eingebaut.
3. **Unklarheit ist keine Rechtsgrundlage.** Gesetzesregeln, Zinsen, Umlagen, steuerliche Behandlung und Bankformate werden nicht erfunden. Fehlen entscheidende Informationen, protokolliere sie in `docs/OPEN_QUESTIONS.md`. Unkritische Annahmen dürfen mit Kennzeichnung in `docs/ASSUMPTIONS.md` den Entwurfsbetrieb ermöglichen. Bei Risiken für Geld, Forderungsbestand, Datenschutz, gesetzliche Fristen oder Beweiserhalt bleibt die betroffene Produktivaktion gesperrt. An anderen Aufgaben wird weitergearbeitet. Ein konfigurierbarer Wert oder Haftungshinweis ersetzt keine zulässige Regel.
4. **API-first bleibt bestehen.** Jede fachliche Funktion wird über die dokumentierte API angeboten; CRM und Portale nutzen diese. Freigabe- und Sperrregeln gelten auch für Jobs, Importe, Massenaktionen und Integrationen, nicht nur für die Oberfläche.
5. **Mandanten- und Rechtsträgertrennung.** Die bestehende technische Mandantentrennung bleibt unverändert. Zusätzlich müssen Forderungen, Guthaben, Bankguthaben, Rücklagen und Kautionen dem richtigen Rechtsträger zugeordnet sein. Eine Verwaltungsgesellschaft ist nicht automatisch Gläubigerin oder Eigentümerin verwalteter Gelder. Der Konflikt „ein Buchungskreis je Objekt“ bei WEG mit SEV wird ausdrücklich durch Claude geprüft, nicht hier durch ein neues Schema gelöst.
6. **KI liefert Vorschläge.** KI-Konfidenz ist weder Beweis für Richtigkeit noch Freigabe zur Zahlung oder Buchung. Standardmäßig erfolgen keine autonomen KI-Buchungen. Automatische Buchungen bleiben als Produktziel erhalten, aber nur über ausdrücklich aktivierte, fachlich freigegebene und deterministisch prüfbare Regeln nach Abschnitt 7.4. KI darf niemals allein neue Zahlungsempfänger, IBAN-Änderungen, WEG-Beschlüsse, Gebühren oder steuerliche Einordnungen verbindlich freigeben.
7. **Gebuchte Vorgänge bleiben nachvollziehbar.** Entwürfe sind von gebuchten Datensätzen zu unterscheiden. Nach der Buchung werden finanzielle Inhalte nicht überschrieben oder gelöscht; Korrekturen erfolgen nachvollziehbar durch Gegenbuchung und gegebenenfalls Neubuchung. Ein „Rückgängig“ bei Importen oder KI darf niemals diese Regel oder Aufbewahrungssperren umgehen.
8. **Unabhängige Soll-Ergebnisse.** Fachtests beruhen auf vorab festgelegten, nachrechenbaren Ergebnissen. Ein Vergleich mit Immoware24 ist ein zusätzlicher Migrationscheck, kein alleiniger Richtigkeitsnachweis. Die in Anhang D definierten Fälle sind Anforderungen an spätere Softwaretests, keine bereits bestandenen Tests.
9. **Technische Tests bleiben Pflicht.** Backend: pytest mit Happy Path, Berechtigung, Mandantentrennung und Validierung für die Endpunkte. Für Geldflüsse außerdem Konkurrenzzugriffe, Wiederholungen, Abbrüche, Rückabwicklung und historische Stichtage. Frontend: Komponententests und Playwright für Kernpfade. CI muss grün sein. Nicht ausgeführte Tests werden ausdrücklich als nicht ausgeführt bezeichnet.
10. **Sprache und Zahlen.** Code, Bezeichner, Commits, Kommentare und technische Dokumentation auf Englisch; UI, Fachbegriffe, Handbuch und dieses Pflichtenheft auf Deutsch. UI `TT.MM.JJJJ` und `1.234,56 EUR`, intern ISO 8601. Kein Float für Geld. Centgenaue Buchungsbeträge und die höhere nötige Genauigkeit von Zwischenrechnungen, Mengen, Quoten und Zinssätzen sind zu unterscheiden; die technische Umsetzung prüft Claude.
11. **Dokumentation.** Pro Modul README, Architekturentscheidungen als ADR, gemeinsame fachliche Quelle für `CLAUDE.md` und `AGENTS.md`. Neue oder geänderte Fachregeln erhalten Kennung, Geltungsbereich, Quellenstand, Abnahmefall und Änderungsgrund. Keine widersprüchlichen Parallelregelwerke.
12. **Je freigegebener Entwicklungsaufgabe:** zuerst Plan mit Dateien, Migrationen und Tests, dann kleine nachvollziehbare Umsetzung, Tests tatsächlich ausführen, Dokumentation und Ergebnisbericht. Keine unaufgeforderten großen Refactorings. Conventional Commits bleiben bestehen.
13. **Sicherheit.** Keine Geheimnisse im Code, kein Produktivdatenexport an KI ohne geprüfte Berechtigung und Datenverarbeitung. Bestehende technischen Sicherheitsvorgaben bleiben bestehen. „EU-Endpunkt“, `AVV=true`, eine Rolle oder ein Dokument-Hash sind für sich keine vollständigen Nachweise.
14. **Fertig heißt:** technische Definition of Done erfüllt, fachliche Abnahmefälle bestanden, erforderliche Rechts-/Steuerentscheidungen dokumentiert, relevante Sperren getestet, Originalbelege verknüpft, keine ungelösten kritischen Punkte für den konkret freigegebenen Funktionsumfang. Eine Bildschirmansicht oder ein grüner Testlauf allein reicht nicht.
15. **Wirtschaftlich arbeiten.** Suche gezielt, vermeide wiederholte Volltextausgaben und unnötige Agentenschleifen. Einfache Aufgaben durch günstige Modelle oder deterministische Werkzeuge; anspruchsvolle Modelle für Fachlogik, Architektur und Fehleranalyse. Wirtschaftlichkeit darf Belegprüfung, Sicherheitsprüfung oder erforderliche Tests nicht streichen.

### 0.2 Arten von Anforderungen

- **Rechtsgrundlage:** eine im Quellenregister bezeichnete Norm bzw. belastbar geprüfte Rechtsprechung; nur im zutreffenden sachlichen, persönlichen und zeitlichen Geltungsbereich anwenden.
- **Fachliche Umsetzung:** aus dem Verwaltungsprozess abgeleitete erforderliche Funktion, etwa getrennte Ausweisung bestehender Vorschussrückstände. Die konkrete Verbuchung und Sonderfälle benötigen freigegebene Regeln.
- **Produktschutz:** bewusst strengerer interner Standard, etwa Vier-Augen-Freigabe, unveränderliche Ergebnisschnappschüsse oder das Sperren ungeklärter automatischer Geldaktionen. Nicht als allgemeine gesetzliche Pflicht behaupten.
- **Offene Entscheidung:** ungeklärter Rechtsfall, fehlende Objektdokumentation oder technische Ausgestaltung. Zuständigkeit und betroffene Freigabe nennen; nicht durch eine Annahme als erledigt markieren.

Weder dieser Prompt noch ein Review von zwei KI-Systemen ist eine rechtliche Zertifizierung oder eine Prüfung des tatsächlichen Softwarebetriebs. Die vor produktiver Nutzung geforderte fachkundige Rechts-, Steuer- und Sicherheitsprüfung ist ein Projekt-Freigabestandard und keine Behauptung, jede WEG müsse ihre Jahresabrechnung durch einen Wirtschaftsprüfer testieren lassen.

### 0.3 Vorrang- und Konfliktregeln

Folgende verkürzte Aussagen aus den technischen Kapiteln der Version 1.1.1 gelten nur in der hier präzisierten Form. Die zugehörigen Entscheidungen stehen in Abschnitt 6.9 und Anhang E.

| Ausgangsaussage / Fundstelle | Verbindliche fachliche Präzisierung | Entscheidung |
| --- | --- | --- |
| Genau ein `ledger` je `property`; Abschnitte 2, 5, 6 | Keine Vermischung von GdWE-, SEV-, Eigentümer-, Mieter- oder Verwaltervermögen. Keine Gläubigerwechsel durch Kontenfilter. | E01 entschieden: Buchungskreis je Rechtsträger, nicht je Objekt (6.9.1). |
| Eigentumsverhältnis und Miete als gleicher technischer Vertragstyp; Abschnitt 6 | Rechtlicher Eigentumswechsel, Nutzen-/Lastenwechsel, Mietzeitraum und Forderungsschuldner sind nicht dasselbe. | E02 entschieden: getrennte Daten für Eigentumsübergang und Nutzen-/Lastenwechsel, Debitor je Partei (6.9.2). |
| `confirmed` erzeugt Abrechnungsbuchungen; Abschnitt 6 | WEG-Prüfung, Beschluss, Fälligkeit und Buchung sind eigenständige fachliche Schritte nach Abschnitt 7.8. | E03 entschieden: Statusmodell mit Beschlussbezug vor Ergebnisbuchung (6.9.3). |
| Automatik allein ab KI-Konfidenz; Abschnitte 9, 15 | Keine allein KI-gesteuerte Buchungs- oder Zahlungsfreigabe; Abschnitt 7.4 gilt. | E04 entschieden: Automatik nur über freigegebene Regeln, KI-Konfidenz ist Filter, nie Freigabe (7.4, 6.9.4). |
| Zehnjährige Backups/Bankdateien pauschal „GoBD“; Abschnitte 3.5, 8.2 | Backup ist nicht Archiv. Aufbewahrung je Unterlagenklasse, Rechtsträger, Fristbeginn und Sperrgrund nach Abschnitt 7.11. | E05 entschieden: Aufbewahrungsprofile je Unterlagenklasse, Backup 30 Tage plus Jahresstände nur als Betriebsabsicherung (6.9.5, 7.11). |
| `visibility` und Vertragsbezug als alleiniger Portalfilter; Abschnitte 3, 6, 9 | Gesetzliche GdWE-Unterlageneinsicht ist nicht auf eigene Einheit beschränkt; fremde WEG und private SEV-Akten bleiben getrennt. | E06 entschieden: Zugriffsmatrix mit GdWE-Einsichtsrecht je Eigentümer (6.9.6, 14). |
| Hash aus Betrag, Datum, IBAN und Verwendungszweck; Abschnitt 6 | Zwei wirtschaftlich echte, gleichlautende Umsätze bleiben zwei Umsätze. Wiederimport derselben Bankaufzeichnung erzeugt keine neue Buchung. | E07 entschieden: Bankreferenz als Primäridentität, Hash nur als Dublettenhinweis (6.9.7). |
| NUMERIC mit zwei Stellen für jede Rechenstufe; Abschnitte 0, 4, 6 | Buchungsbeträge in Cent; mathematische Zwischenschritte mit fachlich ausreichender Präzision. | E08 entschieden: Buchungsbeträge NUMERIC(14,2), Zwischenwerte und Quoten NUMERIC(20,8) (6.9.8). |
| Allgemeine Rollenfreigabe / `approved` | Rechnung sachlich geprüft, Rechnung gebucht, Zahlung freigegeben, Bank ausgeführt und Beirat geprüft sind unterschiedliche Tatsachen. | E09 entschieden: Freigabe bindet an Snapshot-Hash der zahlungsrelevanten Felder (6.9.9). |
| Historische Journale nur Trainingsbasis; Abschnitt 13 | Für unterjährige Übernahmen müssen erforderliche Jahresbewegungen und Belegketten auch fachlich auswertbar bleiben. | E10 entschieden: Migrationsjournal als auswertbare Vorperiode je Buchungskreis (6.9.10, 13.1). |

Bei einem neuen Widerspruch zwischen fachlicher Anforderung und technischer Lösung wird die fachliche Anforderung nicht abgeschwächt. Dokumentiere Konflikt, Auswirkung und minimalen Lösungsvorschlag als ADR und lege ihn dem Betreiber vor; bis zur Entscheidung bleibt die betroffene Funktion hinter einem Feature-Flag.

---

## 1. Vision und Geschäftskontext

### 1.0 Herkunft der Kontextangaben

Bestandszahlen, Marktbehauptungen, Wettbewerberfähigkeiten und Aussagen zu Immoware24 stammen aus der übergebenen Ausgangsfassung und wurden in diesem Fachreview nicht unabhängig verifiziert. Sie sind keine Zusicherung, kein Nachweis einer Schnittstelle und keine Erlaubnis, vertragliche oder technische Schutzmaßnahmen zu umgehen. Der fachliche Funktionsumfang wird aus den konkret beschriebenen Verwaltungsanforderungen abgeleitet. Reale Schnittstellen, Vertragsbedingungen und Bestandszahlen sind vor Umsetzung anhand verfügbarer Unterlagen zu bestätigen.

### 1.1 Ausgangslage

Die Hausverwaltung Müller GmbH (HVM) verwaltet rund 67 aktive Objekte mit rund 869 Einheiten (WEG-Verwaltung, Mietverwaltung, WEG mit Sondereigentumsverwaltung) in Nordrhein-Westfalen, Berlin/Brandenburg und weiteren Standorten. Sie nutzt Immoware24 als Verwaltungssoftware, Portal24 als Bewohnerportal und Paperless-ngx als DMS. Immoware24 hat keine öffentliche API und blockiert Automatisierung aktiv. Die Verwaltung arbeitet deshalb mit vielen manuellen Schritten: Postfach, Belegerfassung, Bankumsatzzuordnung, Objektübernahmen, Portaleinladungen.

Timo Müller ist Geschäftsführer der HVM und Vorstand der Müller Holding AG (MHAG). Er verwaltet zusätzlich als Einzelunternehmer eigene Objekte unabhängig von der HVM. Beide sind die ersten Mandanten der Plattform.

### 1.2 Ziel

Eine selbst gehostete, mandantenfähige Verwaltungsplattform, die

- Immoware24 vollständig ablöst (Stammdaten, Verträge, Buchhaltung, Banking, Abrechnung, WEG-Versammlung),
- drei Portale integriert (Mieter, Eigentümer inklusive Beirat, Dienstleister),
- KI in jeden Prozess einbaut (Onboarding per Chat, Kontierung, Postfach, Belege, Abrechnungsprüfung),
- eine offene API mit Webhooks als Kern hat,
- die bestehenden Programme der Müller-Gruppe einbindet (Objektakte, smart-einzug, Mailprogramm, Übergabeprotokoll, Flow),
- zunächst intern für die HVM und das Einzelunternehmen läuft und danach als Produkt der MHAG an fremde Verwalter vermarktet wird.

### 1.3 Alleinstellungsmerkmale (aus der Marktrecherche vom 23.09.2026)

| USP | Marktlage |
| --- | --- |
| Alles in einer Plattform: Buchhaltung, Verwaltung, drei Portale, DMS | Verwalter kombinieren heute ERP (Immoware24, Impower, Scalara, Haufe, Domus) mit Portalplattformen (casavi, etg24) und Handwerkerportalen (Craftware24, casavi relay) |
| KI-Onboarding per Chat (Kontaktlisten, Vorverwalterakten) | Kein Anbieter bietet das; Objektübernahmen sind der teuerste manuelle Prozess |
| Lernende KI-Kontierung je Mandant | Wettbewerber bieten Belegerkennung und statische Bankregeln |
| Offene API und Webhooks als Kern | Immoware24 ohne API; Impower und Scalara mit Partnerschnittstellen |
| Dienstleisterportal mit Auftrag, Angebot, Termin, Rechnung, Bewertung, integriert in die Buchhaltung | Nur als Zusatzprodukte am Markt |
| Selbst gehostet, White-Label je Mandant, transparente Preise je Einheit | Professionelle Anbieter: individuelle Angebote, 12 Monate Laufzeit |

### 1.4 Nicht-Ziele (Phase 1 bis 4)

- Kein Maklermodul, keine Immobilienvermarktung (nur Exposé und Leerstandsliste).
- Keine eigene Finanzbuchhaltung für die Verwaltungsgesellschaft selbst (Verwalterhonorar wird als Ausgangsrechnung erzeugt, die Gesellschaftsbuchhaltung bleibt beim Steuerberater bzw. in lexoffice).
- Keine native Mobile-App vor Phase 4 (responsive Web-App und PWA reichen).
- Keine eigene PSD2-Lizenz (Bankzugriff über EBICS-Verträge und lizenzierten Aggregator).

---

## 2. Leitprinzipien

1. **API-first, Portal-ready.** Alles, was die Verwaltung kann, kann die API. Portale sind nur andere Clients derselben API mit anderen Rollen.
2. **Mandant, Objekt, Buchungskreis.** Ein Mandant hat viele Objekte, jedes Objekt hat genau einen Buchungskreis (eigener Kontenrahmen, eigene Bankkonten, eigene Abrechnungszeiträume). Darüber liegen mandantenweite Sichten (Liquidität, Kreditoren, offene Posten, Mahnläufe).
3. **Vertrag als Drehscheibe.** Mietvertrag und Eigentumsverhältnis sind ein Vertragstyp (`contract` mit `kind = tenancy | ownership`). Der Vertrag verbindet Kontakt(e), Einheit, Zahlungen, Debitorenkonto, Bankmandat, Portalfreigaben.
4. **Zeitliche Gültigkeit überall.** Umlageschlüsselwerte, Zahlungen, Eigentumsverhältnisse, Mietverhältnisse, Preise, Einwilligungen haben `valid_from` und `valid_to`. Stichtagsabfragen sind Standard.
5. **Ereignisse als Rückgrat.** Jede fachliche Änderung erzeugt ein Domänenereignis (`domain_event`), das Audit-Trail, Webhooks, Benachrichtigungen, Regel-Engine und KI-Lernen speist.
6. **KI mit Konfidenz und Rückweg.** Jeder KI-Vorschlag hat Konfidenz, Begründung, Quelle, Modell und Kosten. Bestätigen, Ändern, Ablehnen sind eigene Aktionen, die als Trainingsbeispiele dienen.
7. **Deutsch als Fachsprache.** Domänenbegriffe sind im Glossar festgelegt. Die Oberfläche spricht die Sprache eines erfahrenen Verwalters, nicht die eines Entwicklers.
8. **Immoware24-Parität als Untergrenze.** Alles, was Immoware24 fachlich kann (siehe Anhang A), kann die Plattform am Ende von Phase 4 mindestens gleichwertig. Bedienung und Automatisierung müssen deutlich besser sein.

---

## 3. Systemarchitektur

### 3.1 Übersicht

```
                     Internet
                        |
                  [Traefik v3]  TLS, Routing, Rate-Limit
        ________________|________________________________
       |                |                |               |
 crm.<mandant>     portal.<mandant>   api.<mandant>   auth.<mandant>
 [web-crm]         [web-portal]       [api]           [api: /auth]
 Next.js           Next.js            FastAPI
       |________________|________________|
                        |
                 [api] FastAPI (REST, OpenAPI, Webhooks)
                        |
      __________________|__________________________________
     |            |            |             |             |
 [PostgreSQL 16] [Redis 7]  [MinIO]      [worker]      [ai-gateway]
  RLS, pgvector   Queue,     Objekt-      Celery:        Provider-
                  Cache      speicher     beat, io,      Abstraktion
                                          ocr, ai,       Anthropic /
                                          bank, mail     OpenAI
                        |
      __________________|__________________________________
     |                  |                  |               |
 [bank-adapter]   [dms-adapter]      [mail-adapter]   [integrations]
 EBICS, Aggregator Paperless-ngx,    IMAP/SMTP,       Objektakte,
 FinTS, CAMT/CSV   Google Drive      Gmail API        smart-einzug,
                                                      Bestandstools
```

Alle Komponenten laufen als Docker-Compose-Stack auf dem IONOS Dedicated Server (Ubuntu, 32 Kerne, 256 GB RAM, NVMe RAID 1). Traefik ist bereits vorhanden und terminiert TLS für alle Dienste der Müller-Gruppe.

### 3.2 Komponenten

| Komponente | Technik | Aufgabe |
| --- | --- | --- |
| `api` | Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2 | REST-API, Auth, Berechtigungen, Fachlogik, OpenAPI, Webhooks |
| `worker` | Celery 5 mit Redis-Broker, getrennte Queues `default`, `io`, `ocr`, `ai`, `bank`, `mail`, `beat` | Hintergrundjobs, Zeitpläne, Importe, Bankabruf, KI-Aufgaben, Dokumentenverarbeitung |
| `web-crm` | Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, react-hook-form, zod | Verwaltungsoberfläche (crm.mueller-holding.ag) |
| `web-portal` | gleicher Stack, eigenes Projekt im Monorepo, mobile-first, PWA | Mieter-, Eigentümer-, Dienstleisterportal (portal.muellerhv.de, portal.mueller-holding.ag) |
| `ai-gateway` | Python-Paket innerhalb `api`/`worker`, eigene Queue | Provider-Abstraktion, Prompt-Registry, strukturierte Ausgaben, Kostenzähler, RAG |
| `bank-adapter` | Python-Paket, Schnittstelle `BankConnector` | EBICS (fintech-Bibliothek von joonis), Aggregator (finAPI oder GoCardless Bank Account Data), FinTS (python-fints, Rückfall), Datei-Import CAMT.053/MT940/CSV |
| `dms-adapter` | Python-Paket, Schnittstelle `DocumentStore` | Paperless-ngx REST-API, Google Drive API, lokaler MinIO-Speicher |
| PostgreSQL 16 | Erweiterungen `pgcrypto`, `pg_trgm`, `pgvector`, `btree_gist` | Datenhaltung, RLS, Volltext, Embeddings |
| Redis 7 | | Queue, Cache, Rate-Limit, Sitzungen |
| MinIO | S3-kompatibel | Originaldokumente, generierte PDFs, Exporte, Bankdateien |
| Gotenberg | Docker | HTML zu PDF (Briefe, Abrechnungen) |
| OCRmyPDF oder Tesseract | Docker | OCR für Uploads ohne Textebene (Paperless erledigt OCR für seine Dokumente selbst) |
| Beobachtung | OpenTelemetry, Prometheus, Grafana, Loki, Uptime-Kuma, GlitchTip (Sentry-kompatibel) | Metriken, Logs, Fehler, Verfügbarkeit |

### 3.3 Domains und Routing

| Domain | Ziel | Bemerkung |
| --- | --- | --- |
| `crm.mueller-holding.ag` | web-crm, Produktoberfläche der Plattform im CI der Müller Holding AG | Verwaltungsoberfläche für alle Mandanten; Mandantenwechsel im Kopfbereich; Plattformadministration unter `/platform` |
| `api.mueller-holding.ag` | api | REST, OpenAPI unter `/api/v1/docs`, Webhook-Verwaltung |
| `portal.muellerhv.de` | web-portal, Mandant Hausverwaltung Müller GmbH | Mieter, Eigentümer, Dienstleister der HVM (ersetzt Portal24) |
| `portal.mueller-holding.ag` | web-portal, Mandant Timo Müller Einzelunternehmen bzw. MHAG-eigene Bestände | Portal des zweiten Mandanten |
| weitere Mandanten | `<kunde>.mhvp.mueller-holding.ag` oder Kundendomain per CNAME | Portal je Fremdmandant, Mandantenauflösung über Host-Header, hinterlegt in `tenant_domain` |

Mandantenauflösung im Portal: Der Host-Header wird gegen `tenant_domain` aufgelöst; zusätzlich trägt jedes Zugriffstoken die `tenant_id`. Stimmen beide nicht überein, wird der Zugriff abgelehnt. In der Verwaltungsoberfläche (`crm.mueller-holding.ag`) bestimmt die Mitgliedschaft des Benutzers die erreichbaren Mandanten; Plattformadministratoren wechseln ausdrücklich und protokolliert. Alle Domains werden über die IONOS-Nameserver auf den Dedicated Server geführt; Traefik terminiert TLS (Let's Encrypt) und routet nach Host.

### 3.4 Authentifizierung und Autorisierung

- Eigener Auth-Dienst in `api` (Authlib): E-Mail plus Passwort (Argon2id), TOTP-Zweifaktor Pflicht für Verwaltungsrollen, WebAuthn/Passkeys optional, Magic-Link und Einladungscode für Portalnutzer, Passwortregeln nach BSI-Empfehlung, Kontosperre nach Fehlversuchen, Sitzungsverwaltung mit Geräteliste.
- Token: kurzlebige JWT-Access-Token (15 Minuten) mit `tenant_id`, `user_id`, `roles`, `scopes`; Refresh-Token als rotierende, widerrufbare Datenbankeinträge.
- OIDC-Provider-Fähigkeit (Authorization Code mit PKCE), damit Bestandstools (Objektakte, Mailprogramm, Flow) per Single Sign-on anbinden.
- API-Keys für Systemintegrationen (je Mandant, Scopes, Ablauf, letzte Nutzung, Widerruf).
- Berechtigungsmodell: `role` je Mandant mit `permission`-Matrix (Ressource × Aktion: `read`, `create`, `update`, `delete`, `approve`, `export`), Rollenvererbung, optional Objektzuordnung (Objektverwalter sieht nur zugeordnete Objekte), Vier-Augen-Prinzip für Zahlungsfreigaben (`approve` durch zweiten Benutzer erzwingbar). Vordefinierte Rollen siehe Anhang A.4.
- Portalrollen: `tenant_resident` (Mieter), `owner` (Eigentümer), `board_member` (Beirat, zusätzlich zu owner), `service_provider` (Dienstleister), abgeleitet aus Verträgen und Dienstleisterverhältnissen, nie manuell ohne Bezug.

### 3.5 Verschlüsselung und Geheimnisse

- Transport: TLS über Traefik, HSTS, interne Netze im Docker-Netzwerk.
- Ruhende Daten: Datenbank auf verschlüsseltem Volume; besonders sensible Felder (Bankzugangsdaten, EBICS-Schlüssel, Aggregator-Token, KI-API-Schlüssel, IBAN optional) feldweise verschlüsselt mit je Mandant abgeleitetem Schlüssel (`tenant_key`, Envelope-Verschlüsselung, Master-Schlüssel aus Umgebungsvariable oder Vaultwarden/SOPS, niemals in der Datenbank).
- Backups: verschlüsselt, täglich vollständig (pg_dump plus MinIO-Sync), stündlich WAL-Archiv, Aufbewahrung 30 Tage rollierend, monatlicher Wiederherstellungstest; Langzeitaufbewahrung erfolgt über Aufbewahrungsprofile im Archiv (6.9.5), nicht über Backups als Job mit Protokoll.

---

## 4. Technologie-Stack und Konventionen

### 4.1 Backend

- Python 3.12, FastAPI, Uvicorn/Gunicorn, SQLAlchemy 2.x (Mapped Dataclasses), Alembic, Pydantic v2, Celery 5, Redis, httpx, Authlib, python-multipart, WeasyPrint oder Gotenberg für PDF, openpyxl für Excel, `sepaxml`/`fintech.sepa` für pain-Dateien, `fintech.ebics` für EBICS, `python-fints` als Rückfall, `pdfplumber`/`pypdf` für PDF-Text, `pgvector` für Embeddings, `structlog` für Logging, `opentelemetry` für Tracing.
- Paketstruktur nach Domänen (`apps/api/src/mhvp/<domain>/{models,schemas,services,routers,tests}`), keine technische Schichtung über alle Domänen.
- Geldbeträge: `Decimal` mit `NUMERIC(14,2)`, Währung immer `EUR` als Feld vorhanden.
- Zeit: alle Zeitstempel `TIMESTAMPTZ` in UTC, Fachdaten mit Datum als `DATE`.
- IDs: UUID v7 (zeitlich sortierbar) als Primärschlüssel, zusätzlich fachliche Nummern (Objektnummer, Vertragsnummer, Belegnummer) als eindeutige, mandantenweite Sequenzen.
- Fehler: RFC 9457 Problem Details (`application/problem+json`), Fehlercodes im Format `MHVP-<Domäne>-<Nummer>` mit deutschem Benutzertext und englischem Entwicklertext.
- Qualität: ruff (Format und Lint), mypy strict für Fachlogik, pytest mit `pytest-asyncio`, `factory_boy`, Testdatenbank per Testcontainers oder Compose-Service, Abdeckung mindestens 80 Prozent für Fachlogik.

### 4.2 Frontend

- Next.js 15 App Router, React 19, TypeScript strict, Tailwind CSS, shadcn/ui (Radix), TanStack Query und Table, react-hook-form mit zod, `openapi-typescript` und `openapi-fetch` zur Client-Generierung aus der OpenAPI-Datei (Build bricht bei Schemaänderung ohne Regenerierung).
- Internationalisierung mit `next-intl`, Standard `de-DE`, Englisch vorbereitet. Zahlen- und Datumsformat über `Intl`.
- Design: ruhig, dicht, tastaturbedienbar. Globale Suche (`Strg+K`), Kontextwechsel ohne „Objekt öffnen“ (Objekt ist Filter, nicht Modus), Listen mit gespeicherten Filtern, Detailseiten mit Reitern, Aktionen rechts oben, Massenaktionen in Listen. Dunkelmodus. Barrierefreiheit nach WCAG 2.1 AA (Portale fallen möglicherweise unter das Barrierefreiheitsstärkungsgesetz, siehe `docs/OPEN_QUESTIONS.md`).
- White-Label: Farb- und Logo-Tokens je Mandant aus der API (`/api/v1/tenant/branding`), CSS-Variablen zur Laufzeit, Briefbogen als HTML-Vorlage je Mandant.
- Tests: Vitest für Komponenten, Playwright für Kernpfade (Login, Kontakt anlegen, Objekt anlegen, Vertrag anlegen, Buchung, Bankumsatz zuordnen, Ticket, Portal-Login).

### 4.3 Infrastruktur

- Docker Compose je Umgebung (`compose.yaml`, `compose.prod.yaml`, `compose.dev.yaml`), Images über GitHub Container Registry oder lokale Registry, Deploy per `make deploy` (SSH, `docker compose pull && up -d`, Alembic-Migration als Init-Job, Health-Checks).
- Traefik-Labels je Dienst, Let's Encrypt, Middleware für Security-Header, Rate-Limit auf `/auth/*` und `/api/*`.
- Umgebungen: `dev` (lokal, Compose), `staging` (auf dem Server, eigener Compose-Stack, Subdomain `staging.`), `prod`.
- CI: GitHub Actions (oder Gitea Actions, falls das Repo dort liegt): Lint, Typen, Tests, Build, Trivy-Scan, OpenAPI-Diff, Migration-Check (Alembic autogenerate darf keine Differenz zeigen).

---

## 5. Mandantenmodell

### 5.1 Ebenen

| Ebene | Entität | Beschreibung |
| --- | --- | --- |
| Plattform | `platform` (Singleton) | Betreiber Müller Holding AG. Plattformadministratoren legen Mandanten an, verwalten Lizenzen, sehen Betriebsmetriken, nie Fachdaten ohne protokollierten Mandantenwechsel. |
| Mandant | `tenant` | Eine Verwaltungsgesellschaft (Hausverwaltung Müller GmbH, Timo Müller Einzelunternehmen, später Fremdverwalter). Eigenes CI, eigene Benutzer, Rollen, Kataloge, Muster, Bankzugänge, KI-Schlüssel, DMS-Konfiguration, Domains, Lizenz. |
| Objekt | `property` | Verwaltungsmandat mit Verwaltungsart, Buchungskreis, Bankkonten, Abrechnungszeiträumen. |
| Benutzer | `user` mit `membership` je Mandant | Ein Benutzer kann mehreren Mandanten angehören (Timo Müller in Mandant 1 und 2) und wechselt im Kopfbereich. Rollen gelten je Mitgliedschaft. |

### 5.2 Mandantenkonfiguration (`tenant_settings`)

Stammdaten der Gesellschaft (Firma, Rechtsform, Anschrift, Registergericht, Registernummer, Geschäftsführung, USt-IdNr., Telefon, E-Mail, Website), Pflichtangaben für Briefe und E-Mails, Branding (Logo hell/dunkel, Primär- und Sekundärfarbe, Schrift), Briefbogen (HTML-Vorlage mit Kopf, Fuß, Falzmarken nach DIN 5008), E-Mail-Signaturen, Standard-Zustellweg, Nummernkreise (Objekt, Vertrag, Beleg, Ticket, Rechnung), Kataloge (Objektarten, Gebäudearten, Bauarten, Zählerarten, Vertragsarten, Ticketkategorien), Muster (Kontenrahmen, Umlageschlüssel, Verwalterhonorar, Mahneinstellungen, monatliche Zahlungsarten), KI-Konfiguration (Provider, Modelle je Aufgabe, Budget je Monat, Konfidenzschwellen), DMS-Konfiguration (Paperless-URL und Token, Google-Drive-Konto und Wurzelordner, Ordnerschema), Banking (Konnektoren, Abrufplan), Automatisierungen (Sollstellungstag, Mahntag, Zahllauftag), Portal (aktivierte Funktionen je Rolle, Formulare, Chat aktiv).

Für die HVM werden die CI-Angaben aus dem vorhandenen Skill `hvm-ci` übernommen (Logo, Farben, Signatur, Pflichtangaben), für die MHAG aus `mhag-ci`, für Timo Müller aus `tm-privat-ci` bzw. `ci-timo-mueller-einzelunternehmen`. Der Agent legt in `apps/api/src/mhvp/tenant/seeds/` je Mandant eine Seed-Datei an, deren Werte aus diesen CI-Quellen zu übernehmen sind (nicht erfinden; fehlende Werte als `TODO` markieren).

### 5.3 Technische Umsetzung

- Jede Fachtabelle: `tenant_id UUID NOT NULL REFERENCES tenant(id)`, Index `(tenant_id, ...)` als führende Spalte.
- RLS: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY; CREATE POLICY tenant_isolation ON <table> USING (tenant_id = current_setting('app.tenant_id')::uuid);` Die API setzt je Request `SET LOCAL app.tenant_id` in der Transaktion. Der Anwendungs-Datenbankbenutzer ist kein Superuser und kein Tabelleneigentümer, damit RLS nicht umgangen wird. Migrationen laufen mit eigenem Benutzer.
- Plattformtabellen (`platform_*`, `tenant`, `user`, `license`) ohne RLS, nur über Plattformrollen erreichbar.
- Verschlüsselte Felder: Typ `EncryptedText` (SQLAlchemy TypeDecorator) mit Schlüsselableitung je Mandant.
- Mandantenexport: vollständiger Datenexport eines Mandanten (JSON plus Dokumente) als Job, für Datenportabilität und Kündigung.

---

## 6. Domänenmodell

Notation: Tabelle in Backticks, Felder mit Typ, Pflicht (P) oder optional (O). Alle Tabellen haben `id UUID`, `tenant_id`, `created_at`, `updated_at`, `created_by`, `updated_by`. Zeitlich gültige Tabellen haben `valid_from DATE (P)`, `valid_to DATE (O)`. Weiche Löschung nur, wo angegeben (`deleted_at`).

### 6.1 Kontakte und Identität

`contact` (Person oder Firma)
- `kind ENUM(person, company)` P; `salutation`, `title`, `first_name`, `last_name`, `company_name`, `legal_form`, `position`, `date_of_birth` (nur wenn fachlich nötig, z. B. Vermieterbescheinigung), `language` (Standard `de`), `notes`, `preferred_channel ENUM(post, email, portal)`, `blocked BOOLEAN`, `data_sharing_consent` (Verweis auf `consent`), `external_ids JSONB` (Immoware24-ID, lexoffice-ID), `completeness ENUM(complete, incomplete)` (KI-Rudimentäranlage), `deleted_at`.
- Volltext-Spalte `search_vector` (Name, Firma, E-Mail, Telefon, IBAN-Ende).

`contact_address` (`label ENUM(postal, private, work, public)`, `street`, `house_number`, `postal_code`, `city`, `country`, `addition`, `is_primary`), `contact_phone` (`label ENUM(work, mobile, private, fax, other)`, `number` E.164, `is_primary`), `contact_email` (`label`, `email`, `is_primary`, `is_portal_login`), `contact_identifier` (`kind ENUM(tax_number, vat_id, sepa_creditor_id, registry_number, customer_number)`, `value`), `contact_bank_account` (`label`, `iban` verschlüsselt mit Klartext-Suffix, `bic`, `bank_name`, `holder`, `valid_from`, `valid_to`).

`contact_type` (Zuordnung Kontakt zu Typen: `tenant`, `prospect`, `owner`, `service_provider`, `broker`, `manager`, `bank`, `board_member`, `authority`, `other`); Typen entstehen automatisch aus Verträgen und Beziehungen und können manuell ergänzt werden.

`contact_tag` (freie Labels je Mandant), `contact_note` (`category`, `body`, `pinned`), `contact_relation` (Kontakt zu Kontakt: `kind ENUM(spouse, representative, heir, guarantor, employee_of, authorized_person)`, Zeitraum).

`party` (Vertragspartei bzw. Haushalt): fasst mehrere Kontakte zu einer Vertragspartei zusammen (`name` generiert, z. B. „Eheleute A und B“). `party_member` (`contact_id`, `role ENUM(primary, co_party, guarantor, legal_representative)`, `share_percent` optional). Verträge referenzieren `party`, nie direkt einen Kontakt.

`consent` (`contact_id`, `kind ENUM(data_sharing, portal_terms, email_delivery, marketing)`, `granted_at`, `revoked_at`, `source`, `document_id`).

`portal_account` (`user_id`, `contact_id`, `roles`, `invited_at`, `activated_at`, `last_login_at`, `status ENUM(not_invited, invited, active, locked, expired)`); Portalidentität ist vom Kontakt getrennt, ein Kontakt hat höchstens ein Portalkonto je Mandant.

### 6.2 Objekte, Gebäude, Einheiten

`property` (Objekt)
- `number` P (dreistellig, mandantenweit eindeutig, Format wie HVM „NNN“), `name` P, `management_type ENUM(rental, hoa, hoa_with_sev)` P, `management_mode ENUM(own, third_party)`, `property_type_id` (Katalog), `street`, `house_number`, `postal_code`, `city`, `state`, `country`, `municipality_code`, `latitude`, `longitude`, `land_registry_district`, `land_registry_sheet`, `parcel` (Gemarkung, Flur, Flurstück), `built_area_sqm`, `unbuilt_area_sqm`, `sealed_area_sqm`, `garden_use ENUM(none, yes, partial)`, `garden_notes`, `renovation_flag`, `renovation_notes`, `allocation_loss_risk_percent` (Umlageausfallwagnis), `notes`, `images` (Dokumentverweise), `owner_party_id` (bei Mietverwaltung der Eigentümer des Objekts, mit Zeitraum in `property_owner`), `manager_user_id` (Objektverwalter), `status ENUM(onboarding, active, terminated)`, `managed_from`, `managed_to`, `custom_fields JSONB`.

`property_owner` (Objekteigentümer bei Mietverwaltung: `party_id`, Zeitraum, `share_percent`).

`property_contact` (Ansprechpartner: `contact_id`, `category` (Katalog: Hausmeister, Beirat, Notdienst, Versorger), Zeitraum, `visible_in_portal_for ARRAY(tenant, owner, provider)`).

`building` (`property_id`, `name`, `street`, `house_number`, `built_area_sqm`, `sealed_area_sqm`, `roof_area_sqm`, `construction_year`, `renovation_level`, `construction_type_id`, `building_type_id`, `floors`, `windows`, `total_area_sqm`, `living_commercial_area_sqm`, `heated_area_sqm`, `window_area_sqm`, `hallway_area_sqm`, `gross_floor_area_sqm`, `elevator BOOLEAN`, `cellar_rooms`, `heritage_protection BOOLEAN`, `heritage_notes`, `notes`, `energy_certificate` (Dokument, Typ, Kennwert, Gültig bis), `custom_fields`).

`unit` (Verwaltungseinheit)
- `property_id` P, `building_id` P, `number` P (VE-Nummer je Objekt), `label` (z. B. „WE 01“), `location` (z. B. „EG links“), `unit_type ENUM(apartment, commercial, office, parking, garage, storage, garden, other)`, `internal_name`, `rooms NUMERIC(4,1)`, `bedrooms`, `bathrooms`, `total_area_sqm`, `living_area_sqm`, `floor`, `last_modernization_year`, `is_fictional BOOLEAN` (Hilfseinheit für Umlagen), `cellar_number`, `features` (Text), `commission`, `commission_notes`, `deposit_amount_default`, `street`, `house_number`, `postal_code`, `city` (abweichend), `vacancy_vat_option` (Historie in `unit_vat_option`), `custom_fields`.

`allocation_key` (Umlageschlüssel je Objekt): `property_id`, `code`, `name`, `unit_of_measure` (m², Anzahl, Personen, MEA, EUR, cbm, kWh, m³), `default_value`, `kind ENUM(static, consumption, fixed_amount, fixed_share)`, `meter_type_id` (bei Verbrauch), `sort_order`, `is_template_derived`. Standardliste siehe Anhang A.2.

`unit_allocation_value` (zeitlich gültiger Wert je Einheit und Schlüssel: `unit_id`, `allocation_key_id`, `value NUMERIC(14,4)`, `valid_from`, `valid_to`, `source ENUM(manual, contract, import, ai)`). Vertragsbezogene Werte (z. B. Personen) liegen zusätzlich in `contract_allocation_value` und überlagern die Einheitenwerte für die Vertragslaufzeit.

`unit_vat_option` (`unit_id`, `valid_from`, `valid_to`, `option ENUM(none, commercial_no_vat, commercial_full_vat, commercial_reduced_vat)`, `occupant ENUM(vacancy, contract)`).

`meter` (`property_id`, `unit_id` optional, `meter_type_id` (Gas, Heizung, Kaltwasser, Warmwasser, Strom, Wasser gewerblich, Wasser nicht gewerblich, Wärmemengenzähler, Heizkostenverteiler), `number`, `malo_id`, `name`, `connection ENUM(main, sub)`, `location`, `calibration_due_date`, `remote_readable BOOLEAN`, `valid_from`, `valid_to`, `notes`), `meter_reading` (`meter_id`, `read_at`, `value`, `estimated BOOLEAN`, `source ENUM(manual, portal, provider_import, ai)`, `photo_document_id`, `notes`).

`maintenance_item` (Sanierung, Wartung, Prüfpflicht: `property_id`, `unit_id` optional, `kind ENUM(modernization, maintenance, inspection, warranty)`, `title`, `due_date`, `remind_before ENUM(14d, 1m, 3m, 6m)`, `interval` (für wiederkehrende Prüfungen), `provider_relation_id`, `documents`, `status`).

`service_provider_relation` (Dienstleisterverhältnis: `property_id`, `contact_id`, `contract_type_id` (Katalog: Hausmeister, Reinigung, Winterdienst, Wartung Heizung, Aufzug, Versicherung, Messdienst, Energie), `valid_from`, `valid_to`, `notice_period`, `creditor_account_id` (Kreditorenkonto im Buchungskreis), `bank_account_id`, `create_default_bank_rule BOOLEAN`, `categories ARRAY`, `notes`, `documents`, `custom_fields`).

`property_bank_account` (`property_id`, `kind ENUM(rent, hoa, reserve, deposit, hoa_fee, other)`, `iban`, `bic`, `bank_name`, `holder`, `ledger_account_id`, `bank_connection_id`, `notes`, `valid_from`, `valid_to`).

`billing_period` (Abrechnungszeitraum je Objekt: `property_id`, `kind ENUM(operating_costs, hoa_fee, reserve, owner_statement)`, `start_date`, `end_date`, `status ENUM(open, results_created, confirmed, closed)`, `locked_at`).

`notice_board_post` (Schwarzes Brett: `property_id`, `title`, `body`, `category`, `type ENUM(neutral, info, warning, danger)`, `visible_from`, `visible_to`, `audience ARRAY(tenant, owner, provider)`, `attachments`, `read_receipts` in `notice_board_read`).

### 6.3 Verträge und Zahlungen

`contract` (Vertrag, RUCR)
- `kind ENUM(tenancy, ownership)` P, `property_id`, `unit_id` P, `party_id` P, `number` (Vertragsnummer), `start_date` P, `end_date`, `termination_date`, `termination_reason`, `debtor_account_id` (Debitorenkonto, wird automatisch angelegt), `direct_debit BOOLEAN`, `sepa_mandate_id`, `dunning_block BOOLEAN`, `dunning_block_reason`, `rent_increase_block_until` (MEH-Sperre), `user_change_fee BOOLEAN`, `allocation_loss_risk BOOLEAN`, `vat_option ENUM(none, commercial_no_vat, commercial_full_vat, commercial_reduced_vat)`, `sev_enabled BOOLEAN` (nur ownership), `sev_fee_debtor_party_id` (Eigentümer als Schuldner der SE-Verwaltergebühr, siehe 6.9.11), `title_transfer_date`, `benefit_burden_date`, `acquisition_kind`, `special_succession_liability` (nur ownership, siehe 6.9.2), `notes`, `version INTEGER`, `supersedes_contract_id` (Vertragsversionierung: Änderungen mit neuem Wirksamkeitsdatum erzeugen eine neue Version, alte Version erhält `end_date`), `custom_fields`.
- Regeln: Eine Einheit hat zu jedem Zeitpunkt höchstens einen aktiven `tenancy` und einen aktiven `ownership` (Ausnahme: Eigentumsanteile über `party_member.share_percent`). Bei `hoa_with_sev` hängt der Mietvertrag an der Einheit, die Eigentümerpartei ist Empfänger der SE-Verwaltergebühr und der Eigentümerabrechnung.

`contract_payment` (monatliche Zahlung: `contract_id`, `payment_type_id` (Katalog je Mandant: Miete, Betriebskosten-VZ, Heizkosten-VZ, Garage, Stellplatz, Mietminderung, Hausgeld, Erhaltungsrücklage, Sonderumlage, sonstige), `revenue_account_id` (Ertragskonto), `net NUMERIC`, `vat_percent`, `gross NUMERIC`, `valid_from`, `valid_to`, `reason ENUM(initial, index, graduated, increase, adjustment_from_statement, other)`, `document_id`).

`payment_schedule` (Zahlungsintervall und Fälligkeit: `contract_id`, `interval ENUM(monthly, quarterly, semiannual, annual)`, `due_day_rule ENUM(day, workday, last_day, day_next_month)`, `due_day INTEGER`, `valid_from`, `valid_to`).

`sepa_mandate` (`party_id`, `contact_bank_account_id`, `reference` (eindeutig je Gläubiger), `creditor_id`, `signed_at`, `type ENUM(core, b2b)`, `sequence ENUM(first, recurring, one_off)`, `valid_until`, `status ENUM(active, revoked, expired)`, `document_id`, `last_used_at`).

`deposit` (Kaution: `contract_id`, `kind ENUM(cash, savings_book, insurance, guarantee, fixed_deposit, letter_of_comfort, other)`, `amount_due`, `installments`, `valid_from`, `valid_to`, `bank_account_id` (Kautionskonto), `interest_rule`, `status`, `documents`), `deposit_movement` (`deposit_id`, `date`, `amount`, `kind ENUM(payment, interest, payout, offset)`, `posting_id`).

`rent_increase_case` (Mieterhöhungsprozess: `contract_id`, `basis ENUM(mietspiegel, comparison, modernization, index, graduated)`, `current_rent`, `target_rent`, `cap_limit_percent`, `earliest_effective_date`, `status`, `documents`, `ai_check_id`).

### 6.4 Buchhaltung

`ledger` (Buchungskreis, genau einer je Objekt: `property_id`, `fiscal_year_start_month`, `vat_mode`, `locked_until DATE` (Festschreibung), `template_id`).

`ledger_account` (Konto: `ledger_id`, `number` (sechsstellig nach Immoware24-Konvention, Anhang A.1), `name`, `category ENUM(bank, cash, reserve, loan, technical, revenue, cost, debtor, creditor, transit, tax, opening_balance)`, `type ENUM(asset, liability, income, expense)`, `vat_option`, `deductible_vat_rule ENUM(none, fixed_percent, commercial_share)`, `deductible_vat_percent`, `relevant_for_cash_report BOOLEAN`, `visible BOOLEAN`, `booking_texts ARRAY`, `allocation_category ENUM(allocable_heating, allocable_water, allocable_other, non_allocable_heating, non_allocable_water, non_allocable_other, none)`, `statement_kind ENUM(hoa_fee, reserve, operating_costs, none)`, `section_35a_eligible BOOLEAN`, `contact_id` (bei Debitor/Kreditor), `contract_id` (bei Debitor), `is_system BOOLEAN`).

`ledger_account_allocation` (Verteilung eines Kostenkontos: `ledger_account_id`, `allocation_key_id`, `share_percent`, Summe je Konto 100).

`journal_entry` (Buchungssatz, Kopf: `ledger_id`, `number` (fortlaufend je Buchungskreis und Jahr), `booking_date`, `value_date`, `due_date`, `accrual_date`, `text`, `kind ENUM(receivable, invoice, custom, bank_transfer, cost_transfer, opening_balance, debtor_payment, creditor_payment, reversal, statement_result, dunning_fee, interest)`, `reference` (Belegnummer), `document_id`, `bank_transaction_id`, `invoice_id`, `contract_id`, `reversed_by_id`, `reverses_id`, `locked BOOLEAN`, `source ENUM(manual, auto_receivable, bank_import, ai, statement, migration)`, `ai_proposal_id`).

`journal_line` (Buchungszeile: `journal_entry_id`, `account_id`, `debit NUMERIC`, `credit NUMERIC` (genau eines > 0), `vat_percent`, `vat_amount`, `net_amount`, `cost_center` optional, `unit_id` optional, `allocation_key_override_id` optional, `text`). Invariante: Summe Soll = Summe Haben je Buchungssatz, geprüft in der Datenbank (Trigger) und im Service.

`open_item` (offener Posten: `ledger_id`, `account_id` (Debitor oder Kreditor), `journal_entry_id`, `due_date`, `amount`, `remaining`, `kind ENUM(receivable, payable)`, `status ENUM(open, partially_paid, paid, dunned, written_off)`), `open_item_settlement` (`open_item_id`, `journal_entry_id`, `amount`, `date`).

`receivable_run` (Sollstellungslauf: `tenant_id`, `period_month`, `scope ENUM(all, property, contract)`, `distribution ENUM(tenant, owner)`, `status ENUM(preview, posted, reversed)`, `preview_json`, `posted_at`, `journal_entry_ids`).

`invoice` (Eingangsrechnung: `ledger_id`, `creditor_account_id`, `provider_contact_id`, `number`, `invoice_date`, `due_date`, `gross`, `net`, `vat`, `discount_percent`, `discount_until`, `payment_method ENUM(transfer, direct_debit_by_creditor, already_paid)`, `document_id`, `e_invoice_xml_document_id`, `e_invoice_format ENUM(none, xrechnung, zugferd)`, `status ENUM(draft, in_approval, approved, posted, paid, rejected)`, `approval_workflow_id`, `ai_extraction_id`, `duplicate_of_id`), `invoice_line` (`invoice_id`, `account_id`, `amount`, `vat_percent`, `accrual_date`, `section_35a_amount`, `unit_id` optional, `text`).

`approval_workflow` (`subject_type`, `subject_id`, `steps JSONB` (Rolle oder Benutzer je Stufe, Betragsgrenzen), `current_step`, `status`), `approval_decision` (`workflow_id`, `step`, `user_id`, `decision ENUM(approved, rejected, delegated)`, `comment`, `decided_at`).

`recurring_invoice_plan` (Rechnungsplan: Kreditor, Konto, Betrag, Intervall, Laufzeit, nächste Fälligkeit, automatische Buchung ja/nein).

`admin_fee_setting` (Verwalterhonorar: `property_id`, `manager_contact_id`, `contract_document_id`, `start_date`, `end_date`, `termination_date`, `recipient_party_id`, `min_amount`, `max_amount`, `interval`, `due_day_rule`, `vat_option`, `amounts_per_unit_type JSONB` (Wohneinheit, Gewerbeeinheit, Optionsfläche, Garage, Stellplatz, Garten), `account_id`, `sev_fee_amount`, `sev_fee_recipient ENUM(owner)`), `admin_fee_invoice` (erzeugte Honorarrechnung, Ausgangsrechnung des Mandanten, E-Rechnungs-fähig).

`dunning_settings` (je Mandant, überschreibbar je Objekt: Stufen mit `min_days_overdue`, `fee`, `interest_rule` (Basiszins plus Prozentpunkte, konfigurierbar, Rechtsprüfung durch Nutzer), `threshold_amount`, `template_id`, `channel`), `dunning_run` (`tenant_id`, `run_date`, `scope`, `status ENUM(preview, approved, sent)`, `created_by`, `approved_by`), `dunning_case` (`dunning_run_id`, `contract_id`, `debtor_account_id`, `level`, `open_items`, `fee_amount`, `interest_amount`, `letter_document_id`, `delivery_channel`, `delivered_at`, `read_at`).

`bank_connection` (`tenant_id`, `connector ENUM(ebics, aggregator_finapi, aggregator_gocardless, fints, file_import)`, `bank_name`, `bic`, `credentials` verschlüsselt, `consent_valid_until`, `last_sync_at`, `sync_schedule`, `status`, `error_message`), `bank_transaction` (`property_bank_account_id`, `booking_date`, `value_date`, `amount`, `currency`, `counterpart_name`, `counterpart_iban`, `counterpart_bic`, `purpose`, `end_to_end_id`, `mandate_reference`, `creditor_id`, `transaction_code`, `hash` (Dublettenschutz aus IBAN, Datum, Betrag, Verwendungszweck, E2E), `raw JSONB` (CAMT-Original), `status ENUM(new, proposed, booked, ignored, split)`, `journal_entry_id`, `ai_proposal_id`, `matched_rule_id`), `bank_rule` (`tenant_id`, `property_id` optional, `contract_id` optional, `match JSONB` (IBAN, Name enthält, Verwendungszweck-Regex, Betrag von/bis, Intervall), `action JSONB` (Konto, Debitor, Aufteilung), `priority`, `hit_count`, `last_hit_at`, `learned_from_ai BOOLEAN`).

`payment_order` (Zahlungsauftrag: `property_bank_account_id`, `kind ENUM(transfer, direct_debit)`, `amount`, `counterpart`, `purpose`, `execution_date`, `invoice_id` oder `contract_id`, `mandate_id`, `pre_notification_sent_at`, `status ENUM(draft, approved, exported, submitted, executed, rejected)`, `approved_by`, `second_approver_id`, `batch_id`), `payment_batch` (pain.001 oder pain.008 Datei, `document_id`, `submitted_via ENUM(ebics, file)`, `status`, `bank_response`).

`export_run` (DATEV-Buchungsstapel, Journal-CSV, GoBD-Export: Zeitraum, Format, Datei).

### 6.5 Abrechnung und WEG

`operating_cost_statement` (Betriebskostenabrechnung: `billing_period_id`, `name`, `include_heating BOOLEAN`, `interim BOOLEAN`, `alternative_start`, `alternative_end`, `status`, `settings JSONB` (Anschreiben Guthaben/Nachzahlung, Format, gebündelt), `results JSONB` (Statistik, Summen), `correction_of_id`), `statement_line` (je Abrechnung, Konto und Vertrag: Kostensumme, Anteil, Schlüssel, Wert, Zeitraum), `statement_result` (je Vertrag: Kosten, Vorauszahlungen, Saldo, neue Vorauszahlung, Dokument, Zustellung).

`owner_statement` (Abrechnung Mietobjekt für Fremdverwaltung: Zeitraum, brutto/netto, Altschulden, Belege anfügen, Auszahlung, Dokument).

`economic_plan` (Wirtschaftsplan: `billing_period_id`, `name`, `as_of_date`, `basis_statement_id`, `basis_plan_id`, `status ENUM(draft, confirmed, obsolete)`, `plan_lines` (Konto, Plangrundlage, Planwert, Abweichung), `owner_advances` (je Vertrag: verteilte Kosten, Vorschuss gesamt, monatlich), `difference_check` (Plan gegen hinterlegte Zahlungen)).

`hoa_fee_statement` (Hausgeldabrechnung: `billing_period_id`, `economic_plan_id`, Reiter Einnahmen-Ausgaben-Rechnung, Vermögensbericht, Konten, Debitoren, §35a, Kennzahlen: verteilungsrelevante Kosten, verteilte Kosten, HG-Vorschuss Soll und Ist, Abrechnungsspitze, Zahlungsrückstand, Abrechnungssaldo), `reserve` (Rücklagenposition: Name, Konten, Entwicklung), `reserve_statement`, `reserve_plan`, `special_levy` (Sonderumlage: Bezeichnung, Verwendungszweck, Betrag, Stichtag, Umlageschlüssel, Fälligkeit, Ertragskonto, erzeugte Sollstellungen), `sub_community` (Untergemeinschaft mit Einheiten und Schlüsseln).

`heating_cost_import` (externe Heizkostenabrechnung des Messdiensts: Zeitraum, Datei (ARGE HeiWaKo D-Format), Ergebnisse je Einheit, CO2-Aufteilung), `consumption_info` (unterjährige Verbrauchsinformation je Einheit und Monat für das Portal).

`meeting` (Eigentümerversammlung: `property_id`, `name`, `kind ENUM(ordinary, extraordinary, repeat, continuation, partial, circular_resolution)`, `starts_at`, `ends_at`, `location`, `presence ENUM(on_site, hybrid, virtual)`, `virtual_resolution_valid_until` (Beschluss zur virtuellen Versammlung, höchstens drei Jahre), `invitation_template_id`, `proxy_template_id`, `ballot_template_id`, `public_description`, `internal_description`, `status ENUM(preparing, invited, running, follow_up, closed)`), `agenda_item` (TOP: `meeting_id`, `number`, `title`, `proposal_text`, `resolution_rule ENUM(simple_majority, qualified_majority, unanimous, all_owners)`, `voting_principle ENUM(per_head, per_share, per_unit)`, `result ENUM(accepted, rejected, deferred, no_vote)`, `votes_yes`, `votes_no`, `votes_abstain`, `minutes_text`), `meeting_attendance` (Eigentümer, anwesend/vertreten/online, Vollmacht-Dokument), `vote` (je TOP und Eigentümer, Kanal Präsenz/online/Umlauf, Zeitstempel), `resolution` (Beschluss-Sammlung: `property_id`, `number`, `agenda_item_id`, `text`, `kind`, `date`, `location`, `result`, `status ENUM(positive, negative, final, contested, annulled, deleted, legally_binding, irrelevant)`, `court_notes`, `entered_at`, `documents`), `board_audit` (Verwaltungsbeiratsprüfung: Zeitraum, Belege, Prüfvermerke, Freigabe).

### 6.6 Tickets, Aufträge, Kommunikation

`ticket` (`property_id`, `building_id`, `unit_id`, `category_id` (Katalog mit Vorlagen), `title`, `public_description`, `internal_description`, `status ENUM(new, in_progress, waiting, done, closed, rejected)`, `priority ENUM(low, normal, high, urgent, immediate)`, `assignee_user_id`, `team_id`, `initiator_contact_id`, `parent_ticket_id`, `start_date`, `due_date`, `follow_up_date`, `external_comments ENUM(none, to_manager, open)`, `external_attachments ENUM(none, initiator_only, open)`, `visible_for ARRAY(initiator, provider, owner)`, `source ENUM(manual, email, portal, chat, phone, ai, form)`, `sla_due_at`, `time_spent_minutes`, `custom_fields`), `ticket_comment` (`internal BOOLEAN`, `author`, `body`, `attachments`), `ticket_event` (Statuswechsel, Zuweisung), `ticket_template` (Kategorie, Vorbelegung, Checkliste, Standardzuweisung, SLA).

`work_order` (Auftrag: `ticket_id`, `property_id`, `provider_relation_id`, `description`, `budget_limit`, `requires_board_approval BOOLEAN`, `status ENUM(draft, requested, quoted, approved, scheduled, in_progress, done, invoiced, accepted, rejected, cancelled)`, `quote_document_id`, `quote_amount`, `approval_workflow_id`, `scheduled_at`, `completion_report`, `photos`, `invoice_id`, `rating`, `rating_comment`), `work_order_event`.

`message` (E-Mail, Portalnachricht, Brief, SMS: `channel`, `direction`, `contact_id`, `ticket_id`, `subject`, `body`, `attachments`, `sent_at`, `delivered_at`, `read_at`, `provider_message_id`, `thread_id`, `ai_classification`), `mailbox` (IMAP/SMTP oder Gmail-API-Konfiguration je Mandant und Postfach), `form_definition` (Portalformular: Name, Kategorie, Elemente JSON, Zustellung als Ticket oder E-Mail, Freigabe je Rolle, Anhänge erlaubt), `form_submission`.

`template` (Dokumentvorlage: `category`, `name`, `body_html`, `master_template_id` (Briefbogen), `placeholders_used`, `context_types ARRAY(contact, contract, unit, property, meeting, statement, ticket)`, `version`), `template_block` (Baustein), `generated_document` (erzeugtes Dokument mit Kontext, Empfänger, Zustellweg, Zustellnachweis).

`notification` (Benutzerbenachrichtigung), `calendar_event` (Termine mit Bezug zu Ticket, Versammlung, Frist, Wartung; ICS-Export, optional Google-Kalender-Sync).

### 6.7 Dokumente

`document` (`title`, `filename`, `mime_type`, `size`, `sha256`, `storage ENUM(minio, paperless, google_drive)`, `storage_ref` (Objektschlüssel, Paperless-ID, Drive-ID), `category_id` (Kategoriebaum je Mandant), `ocr_text` (Volltext), `embedding VECTOR(1536)` optional, `source ENUM(upload, generated, email, scan, portal, import)`, `retention_until`, `visibility ARRAY(tenant, owner, provider, board)`, `read_receipts`), `document_link` (Verknüpfung zu beliebiger Entität: `document_id`, `entity_type`, `entity_id`, `role ENUM(attachment, evidence, original, generated)`), `document_category` (Baum, Zuordnung zu Paperless-Tags oder Drive-Ordnern).

### 6.8 Plattform, Ereignisse, KI

`domain_event` (append-only: `tenant_id`, `type` (z. B. `contract.created`, `bank_transaction.booked`, `ticket.status_changed`), `entity_type`, `entity_id`, `payload JSONB`, `actor_user_id`, `occurred_at`, `correlation_id`), `audit_log` (Feldänderungen alt/neu je Entität, aus Ereignissen abgeleitet), `webhook_subscription` (`url`, `event_types`, `secret`, `active`, `last_delivery`), `webhook_delivery` (Versuche, Antwortcode, Retry mit exponentiellem Backoff bis 24 Stunden).

`automation_rule` (Regel-Engine: `trigger` (Ereignistyp oder Zeitplan), `conditions JSONB`, `actions JSONB` (Ticket anlegen, E-Mail senden, Buchung vorschlagen, Aufgabe erzeugen, Webhook), `enabled`, `last_run`), `scheduled_job` (Zeitpläne je Mandant: Bankabruf, Sollstellung, Mahnlauf, Zahllauf, Erinnerungen).

`ai_provider_config` (je Mandant: `provider ENUM(anthropic, openai)`, `api_key` verschlüsselt, `models JSONB` (Aufgabe zu Modell), `monthly_budget_eur`, `spent_eur_month`, `data_processing_agreement_signed BOOLEAN`), `ai_task_run` (`task ENUM(extract_contacts, extract_property, classify_email, propose_posting, extract_invoice, draft_reply, check_statement, answer_question, summarize)`, `provider`, `model`, `prompt_version`, `input_ref` (Dokument, Text, Hash), `output JSONB`, `confidence`, `tokens_in`, `tokens_out`, `cost_eur`, `duration_ms`, `status`, `error`), `ai_proposal` (fachlicher Vorschlag: `task_run_id`, `entity_type`, `proposed JSONB`, `decision ENUM(pending, accepted, modified, rejected)`, `decided_by`, `decided_at`, `final JSONB`), `ai_example` (Lernbeispiel je Mandant und Aufgabe: Eingabemerkmale, akzeptiertes Ergebnis, Embedding für Ähnlichkeitssuche), `import_run` (Onboarding- oder Migrationslauf: Quelle, Dateien, Mapping, erzeugte Entitäten mit IDs, Status, Rückgängig-Möglichkeit).

`license` (Plattform: Mandant, Modul, Einheitenkontingent, gültig bis, Preis je Einheit), `usage_counter` (Einheiten, Nutzer, KI-Kosten, Speicher je Mandant und Monat).

---

### 6.9 Entscheidungen aus der Abschlussprüfung (verbindliche Schemaänderungen gegenüber 1.1.1)

Diese Änderungen lösen die im Fachreview 1.1.2 benannten Konflikte E01 bis E16 mit dem kleinsten notwendigen Eingriff. Sie gehören zum Phase-1-Schema (M2 bis M5), auch wenn die Buchungslogik erst in Phase 2 folgt.

**6.9.1 Buchungskreis je Rechtsträger (E01, B01, W01).** `ledger` hängt nicht mehr direkt an `property`, sondern an einem `legal_entity` (neue Tabelle: `kind ENUM(hoa, rental_owner, sev_owner, manager)`, `name`, `party_id` optional, `property_id` optional). Ein Objekt mit Verwaltungsart `hoa` hat genau einen Buchungskreis der GdWE. Ein Objekt `rental` hat einen Buchungskreis des Objekteigentümers (bei mehreren Eigentümern der Eigentümergemeinschaft als Partei). Ein Objekt `hoa_with_sev` hat den GdWE-Buchungskreis plus je SEV-Eigentümer einen eigenen Buchungskreis, in dem dessen Mietforderungen, Mieteinnahmen, Kosten und die SE-Verwaltergebühr gebucht werden. Hausgeldforderungen der GdWE gegen den SEV-Eigentümer stehen ausschließlich im GdWE-Buchungskreis. Bankkonten (`property_bank_account`) referenzieren `ledger_id` und damit den Rechtsträger; Kautionskonten sind eigene Konten im Buchungskreis des Vermieters mit Kennzeichen `segregated = true` und dürfen in Liquiditätssichten nicht als freie Mittel erscheinen (D56). Mandantenweite Sichten aggregieren nur zur Anzeige, nie zur Verrechnung.

**6.9.2 Eigentum, Nutzen und Lasten (E02, W07).** `contract` mit `kind = ownership` erhält `title_transfer_date` (rechtlicher Eigentumsübergang laut Grundbuch, Pflicht), `benefit_burden_date` (Nutzen-/Lastenwechsel laut Kaufvertrag, optional), `acquisition_kind ENUM(purchase, first_acquisition, inheritance, foreclosure, gift, other)` und `special_succession_liability BOOLEAN`. Debitorenkonten werden je `party` und Einheit angelegt, nicht je Vertragsversion; ein Eigentümerwechsel erzeugt ein neues Debitorenkonto für den Erwerber, alte offene Posten bleiben beim Veräußerer (D15). Die Adressierung der Abrechnungsspitze folgt Regel W07 und ist in `hoa_fee_statement.addressing_rule_version` protokolliert. Überlappende Eigentumsperioden je Einheit werden durch Datenbank-Constraint (`btree_gist` Exclusion) verhindert, Miteigentum über `party_member.share_percent`.

**6.9.3 Statusmodell der Abrechnungen (E03, A01, W06).** Alle Abrechnungsobjekte (`operating_cost_statement`, `hoa_fee_statement`, `reserve_statement`, `economic_plan`, `owner_statement`) verwenden das Statusmodell `draft → calculated → internally_approved → board_reviewed (optional) → resolved (nur WEG, mit Pflichtverweis `resolution_id`) → issued (Versand, Zustellnachweis) → due → posted → locked`. Jeder Übergang ist ein Ereignis mit Urheber und Zeit. `calculated` erzeugt einen unveränderlichen Ergebnis-Snapshot (`statement_snapshot`: Eingaben, Schlüsselwerte, Belegliste, Regelversion, Ergebnisse als JSONB plus Hash). `posted` ist nur aus `due` erreichbar, bei WEG zusätzlich nur mit `resolution.status IN (positive, final, legally_binding)`. Eine Änderung nach `calculated` erzeugt eine neue Version mit `supersedes_id`; ein Beschluss ist an eine Snapshot-Version gebunden (D14). Das frühere Feld `status ENUM(open, results_created, confirmed, closed)` entfällt.

**6.9.4 Kontrollierte Automatik (E04).** `bank_rule` erhält `approval_state ENUM(proposed, approved, active, disabled)`, `approved_by`, `approved_at`, `max_amount`, `test_evidence_document_id`. Nur Regeln im Zustand `active` dürfen buchen. `ai_proposal` kann eine Regel im Zustand `proposed` erzeugen, nie `approved`. Die frühere Konfidenzschwelle 0,95 als alleiniger Auslöser entfällt; Konfidenz filtert nur, welche Vorschläge einer aktiven Regel überhaupt vorgelegt werden. Automatik je Mandant global abschaltbar (`tenant_settings.auto_posting_enabled`, Standard false).

**6.9.5 Aufbewahrung und Löschung (E05, S04, S05).** Neue Tabelle `retention_profile` (`document_class`, `legal_entity_kind`, `legal_basis`, `retention_years`, `start_rule ENUM(end_of_year_created, end_of_year_last_entry, contract_end, statement_issued)`), `document.retention_profile_id`, `document.retention_hold_reason` (Rechtsstreit, Steuerverfahren, Beweissicherung). Löschjobs prüfen Profil und Sperre; Löschung wird in Index, MinIO, Paperless und Drive gleich behandelt und protokolliert. Backups: 30 Tage rollierend plus Wiederherstellungstest; die frühere Formulierung „Monatsstände 10 Jahre“ entfällt, Langzeitnachweis leistet das Archiv über Aufbewahrungsprofile, nicht das Backup.

**6.9.6 Zugriffsmatrix (E06, PÜ10 bis PÜ13).** Neue Tabelle `access_grant` (`subject` Portalkonto oder Rolle, `scope_type ENUM(unit, contract, property, legal_entity, document_class)`, `scope_id`, `right ENUM(read, download, comment)`, `legal_basis ENUM(contract, hoa_member_right, tenant_receipt_right, board, explicit_grant)`, `valid_from`, `valid_to`). Eigentümer erhalten automatisch `hoa_member_right` auf Unterlagen ihrer GdWE (Legal Entity), nicht nur auf ihre Einheit; Mieter erhalten `tenant_receipt_right` auf Belege ihrer Abrechnung. SEV-Akten und andere GdWE bleiben ausgeschlossen (D29, D30). Die Matrix gilt für UI, API, Downloads, RAG-Suche und Exporte gleichermaßen; jeder dieser Pfade hat einen Test je Rolle.

**6.9.7 Identität von Bankumsätzen (E07, B08).** `bank_transaction` erhält `bank_reference` (Entry Reference, Account Servicer Reference oder Transaction ID aus CAMT, eindeutig je Konto) als Primäridentität für den Wiederimport. Der bisherige `hash` bleibt als `possible_duplicate_of_id`-Hinweis, der nie automatisch verwirft; zwei Umsätze mit gleichem Hash und verschiedener Bankreferenz sind zwei Umsätze (D05). Interne Umbuchungen zwischen eigenen Konten werden als Paar mit `transfer_pair_id` verknüpft (D04).

**6.9.8 Präzision (E08, B06).** `journal_line.debit/credit`, alle Zahlungs- und Forderungsbeträge `NUMERIC(14,2)`; Quoten, MEA, Flächen, Verbrauchswerte, Steuersätze, Zwischenergebnisse `NUMERIC(20,8)`. Rundung erst bei Bildung des Buchungsbetrags, Rundungsverfahren je Rechenwerk in `billing/rules` dokumentiert; Restcentverteilung nach stabiler Sortierung (Einheitennummer, Partei-ID), nie nach Bildschirmreihenfolge (D08).

**6.9.9 Freigabeversionen (E09, D35, D36).** `approval_decision` erhält `subject_snapshot_hash` über die zahlungsrelevanten Felder (Betrag, Empfänger, IBAN, Ausführungsdatum, Rechnung, Bankkonto). Ändert sich eines dieser Felder, wird die Freigabe automatisch `invalidated` und der Vorgang fällt in den Zustand vor Freigabe zurück. Vier-Augen-Prüfung verlangt zwei verschiedene `user_id` mit verschiedener verifizierter E-Mail-Domain-unabhängiger Identität (kein zweites Konto derselben Person; Plattformadministratoren zählen nicht als zweite Instanz). `invoice.status` wird getrennt in `review_status` (PÜ05) und `posting_status`; `payment_order.status` unterscheidet `exported`, `submitted`, `accepted_by_bank`, `executed`, `rejected`, `partially_executed`; Ausgleich offener Posten erst bei `executed` mit Bankbestätigung (D06, D37).

**6.9.10 Migration mit Jahresvollständigkeit (E10, W04, D11).** Neue Tabellen `migrated_journal_entry` und `migrated_journal_line` je Buchungskreis mit `source = immoware24`, vollständigem Kalenderjahr der Übernahme, Belegverweisen und Überleitungskennzeichen. Abrechnungen des Übernahmejahres lesen Vorperiode aus dem Migrationsjournal und Nachperiode aus dem aktiven Journal, ohne Doppelzählung (Anfangsbestand ist Bestandskonto, keine Ausgabe). Im Parallelbetrieb ist je Buchungskreis genau ein System als führend gekennzeichnet (`ledger.leading_system ENUM(immoware24, mhvp)`); nur das führende System darf mahnen und einziehen (D52).

**6.9.11 SE-Verwaltergebühr (E13, D58).** `contract.sev_fee_recipient_party_id` wird ersetzt durch `sev_fee_debtor_party_id` (Eigentümer als Zahlungsschuldner). Zahlungsempfänger ist immer der Mandant (Verwalter); Rechnung wird im SEV-Buchungskreis des Eigentümers als Kreditorenrechnung gebucht und im Mandanten als Ausgangsrechnung geführt. `admin_fee_setting.recipient_party_id` heißt `invoice_debtor_party_id`.

**6.9.12 Beiratsprüfung (E14, PÜ06 bis PÜ09).** `board_audit` wird zu `audit_engagement` (GdWE, Zeitraum, Zweck, Prüfer, Population, Stichprobenmethode, Datenstand, Snapshot-Bezug) mit `audit_item` (Beleg oder Buchung, Prüfstatus, Vermerk, Rückfrage, Antwort der Verwaltung, Version) und `audit_report` (versionierter Bericht mit geprüfter Anzahl und Wert, offenen Positionen, Empfehlung). Eine neue Snapshot-Version setzt betroffene `audit_item` auf `outdated`.

**6.9.13 Offene Posten und Stichtage (E15, B07, D49).** `open_item.remaining` wird nicht mehr gespeichert, sondern aus `open_item_settlement` zum Stichtag berechnet (Materialized View für Performance, periodisch aktualisiert). Bulk-Endpunkte im Rechnungswesen arbeiten je Geschäftsvorfall transaktional; Teilerfolg ist je Vorfall, nie innerhalb eines Buchungssatzes.

**6.9.14 Versionen (E16).** Konkrete Versionen von Frameworks, Bankbibliotheken, Formaten (CAMT, pain, XRechnung, ZUGFeRD, HeiWaKo D-Format) werden bei M1 bzw. beim jeweiligen Meilenstein festgelegt, in `docs/adr/` begründet und in Lockfiles gepinnt; Aktualisierung nur mit Kompatibilitätstest.

---

## 7. Buchhaltungskern

Die Buchhaltung ist das prioritäre Fachmodul. Die doppelte Buchungslogik des technischen Entwurfs bleibt erhalten. Sie ist eine Produktentscheidung und bedeutet nicht, dass jede GdWE handelsrechtlich bilanzierungspflichtig wäre. WEG-Jahresabrechnung, mietrechtliche Betriebskostenabrechnung, Eigentümerabrechnung der Mietverwaltung und steuerliche Auswertungen sind **verschiedene Rechenwerke**. Keine Einheitsformel für alle vier.

Anwendbare Pflichten sind je Rechtsträger und Vorgang zu dokumentieren; insbesondere §§ 9a, 16, 18, 21, 28, 29 WEG, mietrechtliche Vorschriften, HeizkostenV, CO2KostAufG sowie bei steuerlicher Anwendbarkeit AO, GoBD, HGB und UStG. Primärquellen und Prüfgrenzen stehen in Anhang C. Die folgenden Audit- und Automatikschutzregeln sind teilweise bewusst strengere Produktstandards.

### 7.1 Grundregeln und prüfbare Invarianten

**B01 Richtiger Rechtsträger.** Jede Forderung, Verbindlichkeit, Zahlung, Rücklage, Kaution und Abrechnung muss eindeutig ihrem Gläubiger, Schuldner und verwalteten Vermögen zuordenbar sein. Mandantenweite Sichten dürfen zusammen anzeigen, aber weder Gelder noch Gegenforderungen verschiedener Rechtsträger vermengen. Aus einer Eigentümer-Mietforderung wird keine Forderung der GdWE oder des Verwalters. Ein Kontenname ist kein ausreichender Nachweis dieser Trennung.

**B02 Entwurf und Buchung.** Bearbeitbare Entwürfe eindeutig kennzeichnen. Ein gebuchter Satz besitzt mindestens zwei Zeilen; Sollsumme und Habensumme stimmen exakt überein. Geschäftsvorfall, Buchungszeilen und zugehörige OP-Wirkungen werden fachlich vollständig oder gar nicht übernommen. Die konkrete technische Transaktionsgrenze liegt bei Claude. Ein Fehler darf keine halbe Buchung hinterlassen.

**B03 Korrektur statt Überschreiben.** Gebuchte finanzielle Inhalte werden nicht geändert oder gelöscht. Storno und Neubuchung tragen Bezug, Begründung, Urheber und Zeit. Ergänzende Notizen sind getrennt und versioniert. Bei gesperrter Periode ist das zulässige Korrekturverfahren mit offenem Buchungsdatum zu verwenden; der ursprüngliche Sachverhaltszeitraum bleibt erkennbar. Eine neue Abrechnung ist nicht automatisch ein Anlass, bereits wirksam beschlossene Forderungen ohne Rechtsgrund auszubuchen.

**B04 Eindeutige Nummern.** Fortlaufendes Buchungsregister je festgelegtem Nummernkreis, keine Wiederverwendung oder stille nachträgliche Umnummerierung. Fehlgeschlagene Vergaben und relevante Lücken müssen prüfbar sein. Eine Datenbanksequenz allein ist kein Nachweis garantierter Lückenlosigkeit. Ob zusätzlich ein streng lückenloses Vergabeverfahren als Produktstandard eingerichtet wird, entscheidet Claude mit begründeter technischer Umsetzung; keine unbelegte Behauptung, jede Nummernlücke verletze automatisch die GoBD.

**B05 Belegkette.** Quelle, Urheber, Originalbeleg bzw. zulässiger Eigenbeleg, Belegnummer und alle relevanten Bezugsvorgänge bleiben verknüpft. Eine Sollstellung kann durch Vertrag/Beschluss und Laufnachweis belegt sein; nicht jeder Satz erfordert eine externe Rechnung. Fehlender Rechnungsbeleg wird nicht durch einen von der KI erfundenen Beleg ersetzt. Begründete Nachbuchungen/ungeklärte Bankbewegungen erhalten sichtbaren Klärungsstatus und verantwortliche Aufgabe.

**B06 Präzision.** Kein Float für Geld. Gebuchte Summen sind centgenau, Zwischenwerte für Flächen, MEA, Verbrauch, Steuern und Zinsen ausreichend präzise. Rundungsort und Rundungsart sind je Rechenwerk dokumentiert. Der bisherige Produktstandard ROUND_HALF_UP gilt nur, soweit die konkret anzuwendende Vorschrift/Formatspezifikation nichts anderes verlangt. Verteilungsdifferenzen werden deterministisch ausgeglichen und ausgewiesen; bei Gleichstand muss die Zuordnung stabil sein. Keine wechselnden Cent-Ergebnisse bei anderer Zeilenreihenfolge.

**B07 Stichtagswahrheit.** Historische Salden und offene Posten werden aus den bis zum Stichtag wirksamen Vorgängen reproduziert. Spätere Zahlung, Storno oder Stammdatenänderung darf einen früheren Kontenstand nicht rückwirkend verfälschen. Leistungsdatum, Rechnungsdatum, Buchungstag, Wertstellung, Fälligkeit und rechtlicher Wirksamkeitszeitpunkt werden nicht gleichgesetzt.

**B08 Keine doppelte wirtschaftliche Wirkung.** Wiederholung eines Imports, Sollstellungslaufs, Freigabeklicks, Hintergrundjobs oder Bank-Callbacks erzeugt nicht erneut Forderung, Zahlung oder Abrechnungsergebnis. Zwei echte gleichlautende Geschäftsvorfälle dürfen andererseits nicht als Dublette verschwinden. Korrektur, Skonto, Teilzahlung, Überzahlung und Rücklastschrift bleiben bis zum Ursprungsfall nachvollziehbar.

**B09 Abstimmung.** Für jeden Bank-/Kassenbestand ist Anfangsbestand plus Zugänge minus Abgänge gleich Endbestand. Bankabstimmung erfolgt anhand verlässlicher Kontoauszugs-/Bankinformationen. Differenzen sind sichtbar und dürfen nicht durch eine automatisch erfundene Ausgleichsbuchung beseitigt werden. Die Summe passender Nebenbuchposten stimmt mit der zugehörigen Hauptbuchauswertung überein; dieselbe OP-Forderung wird nicht mehrfach summiert.

### 7.2 Kontenrahmen

Jeder Buchungskreis wird aus einer mandantenweiten Kontenrahmen-Vorlage erzeugt (`chart_of_accounts_template`), die der Immoware24-Konvention folgt (Anhang A.1), damit Migration und Vergleichbarkeit einfach bleiben. Nummernkreise:

| Bereich | Nummern | Kategorie |
| --- | --- | --- |
| Bank und Kasse | 001200 bis 001999 | `bank`, `cash` |
| Rücklagen, Darlehen | 008000 bis 008999 | `reserve`, `loan` |
| Technische Konten | 009000 bis 009999 | `opening_balance`, `transit` |
| Finanzerträge, Rücklagenbewegung, Steuer | 026000 bis 039999 | `revenue`, `tax`, `technical` |
| Kosten | 040000 bis 059999 | `cost` mit Abrechnungskategorie und Verteilung |
| Erträge (Sollstellungen) | 060000 bis 069999 | `revenue` je Zahlungsart (Hausgeld, Rücklage, Miete, BK-VZ, HK-VZ, Garage, Stellplatz) |
| Kreditoren | 070000 bis 079999 | `creditor` je Dienstleister, automatisch bei Dienstleisterverhältnis |
| Debitoren | 090000 bis 099999 | `debtor` je Vertrag, automatisch bei Vertragsanlage, Name „Einheit Vertragspartei“ |

Kostenkonten tragen `allocation_category` (umlagefähig/nicht umlagefähig, jeweils Heizung/Warmwasser, Wasser, Sonstige), `statement_kind` (Hausgeld, Rücklage, Betriebskosten) und eine Verteilung über einen oder mehrere Umlageschlüssel mit Prozentanteilen (Summe 100). Konten können je Objekt ergänzt werden; Konten mit Buchungen können nicht gelöscht, nur deaktiviert werden.

**Ergänzende Einordnung:** Die Kontonummern sind eine Migrations- und Produktkonvention, kein gesetzlich vorgeschriebener WEG-Kontenrahmen. Attribute an Konten liefern Vorschläge. Die tatsächliche Umlagefähigkeit, Umsatzsteuerbehandlung, Rücklagenwirkung und Zuordnung zum Rechenwerk müssen zusätzlich zum Vorgang, Vertrag, Rechtsträger und Zeitraum passen. Ein Kostenkonto kann in WEG- und Mietabrechnung unterschiedlich behandelt werden. Die Kurzfelder aus Abschnitt 6 dürfen fachlich zulässige Mehrfachzuordnungen nicht verhindern; Prüfung durch Claude.

### 7.3 Buchungstypen und Geschäftsvorfälle

| Vorgang | Erforderliches fachliches Verhalten | Abnahmehinweis |
| --- | --- | --- |
| Sollstellung | Forderung aus nachgewiesener Vertrags-/Beschlussgrundlage, Zahlungskomponente und Fälligkeit. Zahlungskomponenten getrennt halten; Vorschüsse sind nicht ohne fachliche Prüfung endgültiger Ertrag. | Einmaligkeit je Rechtsgrund, Zeitraum, Schuldner und Komponente. |
| Eingangsrechnung | Kosten-/Bestands-/Steuerzuordnung gegen Kreditor entsprechend Sachverhalt; formelle, sachliche und steuerliche Prüfung getrennt. | Buchung einer Rechnung ist weder Bankzahlung noch automatisch WEG-Ausgabe des Zahlungsjahres. |
| Debitorenzahlung | Bankbewegung mit korrekter Partei und Tilgungsbestimmung verknüpfen; zulässiger OP-Ausgleich. | Teilbeträge, Fremdzahler, Überzahlung und Rückabwicklung nachweisbar. |
| Kreditorenzahlung | Ausgeführte Bankbewegung gegen Verbindlichkeit ausgleichen. | Export oder Einreichung eines Zahllaufs allein setzt keinen Posten auf „bezahlt“. |
| Bankumbuchung | Beide Kontobewegungen derselben Vermögenssphäre zusammenführen; Zwischenstatus möglich. | Kein Aufwand/Ertrag und keine doppelte Wirkung durch Abruf beider Konten. |
| Kostenkorrektur | Fehlerhafte Kontierung mit nachvollziehbaren Korrekturbuchungen berichtigen. | Kein stilles Ändern einer gebuchten Zeile; Steuer- und Abrechnungsfolgen berücksichtigen. |
| Anfangsbestand/Jahreswechsel | Nachgewiesene, abgestimmte Übernahme von Beständen und OP. | Keine erneute Zahlung oder Jahresausgabe durch Anfangsbestand. |
| Rücklage | Beschlossene Zuführung, tatsächlicher Beitragseingang, Rücklagenbestand, Bankanlage und Mittelverwendung getrennt führen. | Transfer auf ein Rücklagenbankkonto ist nicht für sich eine Ausgabe zur Kostentragung. |
| Abrechnungsergebnis | Nur die fachlich und rechtlich entstandene neue Forderung/Gutschrift buchen; bestehende Forderungen nicht duplizieren. | Für WEG erst nach dokumentierter wirksamer Grundlage gemäß 7.8; interne Bestätigung genügt nicht. |
| Guthabenauszahlung/Verrechnung | Anspruchsinhaber, Gegenforderung, Freigabe und gegebenenfalls zulässige Aufrechnung prüfen. | Keine Verrechnung fremder Personen, GdWE oder Vermögen. |
| Skonto/Gutschrift/Storno | Ursprungsbezug, Restforderung, Steuer- und Kostenkorrektur sowie Zahlungswirkung abbilden. | Keine pauschale Differenzbuchung ohne Grundlage. |
| Abschlag/Schlussrechnung | Bereits berechnete und bezahlte Abschläge eindeutig zuordnen; Schlussrechnung nur mit verbleibender Wirkung. | Keine doppelte Erfassung der Gesamtleistung. |
| Rücklastschrift/Erstattung | Ursprüngliche Zahlung/Zuordnung auflösen bzw. korrigieren, Rückgabedatum und tatsächliche Gebühren belegen. | OP wird nachvollziehbar wieder offen; keine automatische neue Fantasiegebühr. |

### 7.4 Zahlungszuordnung und kontrollierte Automatisierung

1. **Original und Identität sichern.** Bankquelle, Originaldatensatz, Konto, rechtlicher Kontoinhaber, gegebenenfalls Bankreferenz und Importlauf festhalten. Technisch erkannte Wiederholungen von wirtschaftlich getrennten identischen Zahlungen unterscheiden. Bei unsicherer Dublette prüfen statt still überspringen.
2. **Deterministische Kandidaten.** Mandats- und End-to-End-Referenz, Rechnungs-/Vertragsnummer, Bankkonto, Betrag und Zahlungszweck zusammen bewerten. IBAN allein beweist weder Vertrag noch Schuldner. Zahlungen für beendete Verträge, Zahlungen Dritter und mehrere Verträge mit gleichem Konto unterstützen. Kein Ausschluss nur wegen inaktiver Vertragsversion.
3. **KI als Vorschlag.** Modell, Quelle, Kosten, Kandidaten, Begründung und Konfidenz anzeigen. Eine selbst angegebene Konfidenz von 0,95 ist keine nachgewiesene Trefferwahrscheinlichkeit. Unbekannte Zuordnungen, widersprüchliche Zwecke und fehlende Belege werden nicht durch höhere Modellkosten zu bestätigten Tatsachen.
4. **Opt-in-Automatik als Produktschutz.** Standard ist manuelle Bestätigung. Automatik nur für vorab fachlich freigegebene Regeln mit eindeutigem Rechtsträger, Konto, Vorgang, Betrag, zulässiger Tilgung und bestandenem unabhängigen Test. Festgelegte Betrags-/Fallgrenzen, Protokoll, Abschaltmöglichkeit und Nachkontrolle sind Pflicht. KI darf eine Regel vorschlagen, aber nicht selbst deren Produktivfreigabe erteilen. Teilzahlungen, Sammelzahlungen, Überzahlungen, neue Empfänger und unklare Eigentümerwechsel bleiben zunächst manuell.
5. **Tilgung.** Eine maßgebliche Zahlungsbestimmung des Schuldners ist zu beachten. Ohne Bestimmung gilt die für den konkreten Fall einschlägige gesetzliche/vereinbarte Tilgungsfolge; §§ 366, 367 BGB sind zu berücksichtigen [R09]. Freie Kontenprioritäten dürfen diese nicht verdrängen. Unklare, angefochtene oder abweichend bestimmte Tilgung geht in die Prüfung. Guthaben ist nicht automatisch Ertrag.
6. **Rückweg.** Vor Buchung kann der Vorschlag verworfen werden; nach Buchung nur nachvollziehbare Korrektur. Lernen aus tatsächlich bestätigtem Ergebnis, nicht ungeprüft aus altem Journal oder bloßer Modellantwort. Trainings-/Evaluationsnutzung muss datenschutzrechtlich zulässig sein.

Massenbestätigung ohne fachliches Seitenlimit bleibt Ziel. Vor Bestätigung Summen, Zahl der Vorgänge, Rechtsträger und Ausnahmen anzeigen. Teilerfolgsverhalten darf Buchungssätze oder Zahlungsveranlassungen nicht zerlegen. Automatisierungsquote ist eine betriebliche Kennzahl, kein Sicherheitsnachweis.

### 7.5 Sollstellung, Mahnwesen, Zahllauf und Liquidität

**Sollstellung.** Zeitpläne und Vorschau bleiben bestehen. Vertrags-/Beschlussversion, Geltungsbeginn, Zahlungskomponente und Fälligkeit sind nachzuweisen. Zeitanteilige Mietberechnung nach freigegebener Vertragsregel; ein frei wählbares 30/360-Verfahren ist keine allgemeine Rechtsgrundlage. WEG-Eigentümerwechsel werden nicht wie tageweise Mietwechsel behandelt. Nachträgliche Planänderungen erzeugen nachvollziehbare Differenzvorgänge statt doppelter Monate.

**Mahnwesen.** Fälligkeit und Verzug sind getrennt. Verzugsbeginn, Verantwortlichkeit, Zugang einer erforderlichen Mahnung, Verbrauchereigenschaft, Rechtsgrund und Hemmnisse sind zu prüfen. Zinssätze werden mit Gültigkeitszeitraum aus nachvollziehbarer Quelle geführt; Änderungen des Basiszinses während des Verzugs berücksichtigen. Nicht pauschal neun Prozentpunkte oder 40 EUR auf alle WEG-/Mietforderungen anwenden. § 288 unterscheidet Anspruchsarten und Beteiligte; Mahnkosten benötigen eine tragfähige Grundlage, nicht nur eine freigegebene Konfiguration [R10]. Laufende Ratenpläne, bestrittene Posten, Aufrechnungen, Prozessstatus und Sperren berücksichtigen. Frist-/Verjährungshinweise sind Prüfhinweise, keine automatische Rechtsverfolgung. Mahnbescheid/Klage nur nach gesondertem Nutzerauftrag und fallbezogener Prüfung.

**Zahllauf.** Freigegebene Rechnungen und zulässige Lastschriften als Vorschau, getrennt nach rechtlichem Konto-/Gläubigerkontext. Vier-Augen-Freigabe ist der Projektstandard für echte Zahlungsveranlassung. Freigabe bezieht sich auf einen unveränderlichen Stand von Betrag, Empfänger, IBAN, Ausführungsdatum, Rechnung und Bankkonto. Änderung eines zahlungsrelevanten Feldes entwertet die vorherige Freigabe. Keine Selbstfreigabe über Zweitkonto derselben Person. Konto-/Banklimits und vorhandene bankseitige Empfängerprüfung berücksichtigen.

**SEPA.** Gültigkeit und Nachweis des Mandats, richtiger Gläubiger samt Kennung/Referenz, zugelassenes Verfahren, Vorabinformation und vereinbarte Frist, Einreichungsfristen und Rückgabeverfahren prüfen. Die im Ausgangsentwurf genannten 14 Tage sind nur mit der für das gewählte Verfahren aktuell geprüften Spezifikation bzw. wirksamer abweichender Vereinbarung als Standard zu verwenden. CORE/B2B nicht austauschbar behandeln; eine Portal-Checkbox allein ist kein ausreichender Nachweis aller Mandatsvoraussetzungen. Bankantworten, Ablehnungen, Rückgaben und tatsächlich ausgeführte Beträge mit offenen Posten abstimmen. Aktuelle Formatversionen prüft Claude anhand Bank-/Scheme-Dokumentation [P05].

**Liquiditätsvorschau.** 90 Tage wie im Ausgangsentwurf. Ist-Bestände, erwartete Einzahlungen, verfügbare freie Mittel und zweckgebundene Rücklagen getrennt ausweisen. Eine offene Forderung oder geplante Lastschrift ist keine vorhandene Liquidität. Keine pauschale Finanzierung eines Eigentümers/Objekts aus Geldern anderer Eigentümer oder Gemeinschaften.

### 7.6 Abrechnungsablauf, Miete und Eigentümerabrechnung

**A01 Ergebnisstand.** Abrechnungsentwurf, nachgerechneter Ergebnisstand, interne Freigabe, gegebenenfalls Beiratsstellungnahme, erforderlicher Beschluss, Versand/Zugang, Fälligkeit, Ergebnisbuchung und Periodensperre sind fachlich getrennt. Jede erteilte Abrechnung konserviert Eingabedaten, Schlüssel, Belegauswahl, Rechts-/Regelversion, Rechenweg und Dokumentfassung. Spätere Stammdaten- oder Regeländerungen verändern die ausgegebene Fassung nicht. Korrektur über neue Version mit Bezug und Differenzbericht.

**A02 Betriebskosten Miete.** Vertragliche Umlagevereinbarung, Betriebskostenart, Objekt-/Nutzerkreis, Wirtschaftlichkeitsgrundsatz und passender Verteilungsschlüssel sind zu prüfen. Verwaltung, Instandhaltung und Instandsetzung werden bei Wohnraum nicht pauschal als Betriebskosten übernommen. Mischrechnungen werden nachvollziehbar getrennt. Alte Kontobezeichnungen wie „Kabel-TV“ sind kein Nachweis heutiger Umlagefähigkeit [R06, R07]. Gewerbemietverträge sind gesondert einzuordnen; Wohnraumschutzregeln nicht unterschiedslos anwenden.

**A03 Schlüssel.** Vertragsregel und zwingendes Recht beachten. Bei vermietetem Wohnungseigentum ist § 556a Abs. 3 BGB ausdrücklich zu berücksichtigen: ohne abweichende Vereinbarung grundsätzlich der WEG-Verteilungsmaßstab, vorbehaltlich billigem Ermessen. Deshalb weder automatisch immer Wohnfläche noch automatisch jede WEG-Kostenposition an den Mieter weiterreichen. Einzelne neue bzw. geänderte Schlüssel brauchen Quelle, Geltungsbeginn und nachvollziehbare Zulässigkeit [R07].

**A04 Vorauszahlungen und Fristen.** Tatsächlich zuzuordnende Vorauszahlungen, offene Vorschüsse, Erstattungen und bereits ausgeglichene Beträge getrennt darstellen; keine doppelte Inanspruchnahme aus Vorschuss und Abrechnung. Das Verfahren für noch offene Mietvorauszahlungen nach Abrechnungsreife ist vor Freigabe fachlich zu bestätigen. Bei Wohnraum die Abrechnungs- und Einwendungsfristen des § 556 Abs. 3 BGB mit Ausnahmegründen und Nachweisen abbilden. Das Fristende betrifft Zugang/Mitteilung, nicht nur PDF-Erzeugung. Keine automatische Nachforderung bei erkennbar abgelaufener Ausschlussfrist ohne geprüfte Ausnahme. Anpassung der Vorauszahlungen nach § 560 BGB ist ein eigener Vorgang [R06, R08].

**A05 Nutzerwechsel, Leerstand, Heizkosten.** Zeitlich gültige Verträge und Verbrauchsdaten verwenden; Leerstandsanteile nicht auf verbleibende Mieter verteilen. Heizkosten nicht unterschiedslos tageweise berechnen, sondern Abschnitt 7.10 anwenden. Unterjährige Abrechnungen nur mit ausgewiesenem Zweck und zulässiger Grundlage.

**A06 Eigentümerabrechnung Miete/SEV.** Einnahmen, Ausgaben, Verwalterhonorar, Auszahlungen, offene Mietforderungen, Kautionen und freie Liquidität getrennt. Hausgeldzahlung des Eigentümers an die GdWE ist nicht identisch mit mietrechtlich umlagefähigen Betriebskosten. Die SEV-Abrechnung enthält eine nachvollziehbare Überleitung von WEG-Einzelabrechnung zu Mietabrechnung und Eigentümerbelastung. Kein Vermischen von GdWE-Vorschüssen und Mieteinnahmen.

**A07 Bedienung.** Anschreiben für Guthaben/Nachzahlung, Informationsblatt, gebündelte Ausgabe, §-35a-Nachweis und neue Vorauszahlungsvorschläge bleiben als Funktionen erhalten. Entscheidende Angaben müssen aus freigegebenen Daten stammen. KI-Erklärtexte dürfen keine Beträge, Rechtsfolgen oder Fristen hinzufügen, die das Rechenwerk nicht trägt.

### 7.7 Auswertungen, Exporte und Verfahrensnachweise

Summen-/Saldenliste, Kontenblatt, Journal, OP zum Stichtag, Monatsmatrix, Soll-/Ist-Mieterträge, Bankkontoabrechnung, Liquidität und steuerliche Auswertungen bleiben erhalten. Jede Auswertung nennt Rechtsträger, Zeitraum, Stichtag, Datenstand, Filter und gegebenenfalls Entwurfsstatus. Eine WEG-Einnahmen-/Ausgabenrechnung ist keine steuerliche EÜR; eine Objekt-USt-Auswertung ist keine eigenständige Steuererklärung ohne Prüfung des Unternehmers.

DATEV-Export nach der tatsächlich eingesetzten offiziellen Formatspezifikation, Journal-CSV/Excel und maschinell auswertbarer Prüfexport mit verknüpften Originalbelegen. Umfang: Konten, Buchungen, OP-Ausgleich, Eröffnungsbestände, relevante Stammdatenhistorie, Freigaben, Änderungs-/Stornobeziehungen, Schlüssel-/Regelstände und ein lesbares Inhalts-/Verknüpfungsverzeichnis. Export muss wieder nachvollziehbar auswertbar sein; ein ZIP voller PDFs genügt nicht für eine maschinelle Buchhaltungsprüfung.

Verfahrensdokumentation beschreibt den **tatsächlich betriebenen** Ablauf von Eingang über Kontrollen und Korrekturen bis Archiv und Export, Rollen, Systemwechsel und Löschung. Automatisch erzeugte Dokumentation ist ein Entwurf, kein Ersatz für Übereinstimmung mit dem Betrieb. Quellen: §§ 146, 147 AO, § 257 HGB und aktuelle GoBD in ihrem Anwendungsbereich [R17–R19].

### 7.8 WEG-Buchhaltung und WEG-Abrechnung im Detail

**W01 Eigene Gemeinschaft.** GdWE als Rechtsträger, Verwalter als handelnde Verwaltung und einzelne Eigentümer als Beteiligte unterscheiden. Bank-/Rücklagenkonten, Forderungen, Verträge und Vollmachten müssen zur richtigen Gemeinschaft passen. Keine automatische Gesamtsaldierung mit privaten SEV-Konten [R01].

**W02 Wirtschaftsplan.** Kalenderjahr, erwartete Einnahmen/Ausgaben, Kosten- und Rücklagenvorschüsse je Einheit, Schlüssel, Gesamt-/Einzelplan und Beschlussgrundlage. Beschlossene Beträge, Zahlungsrhythmus, Fälligkeit, Wirksamkeitsbeginn und gegebenenfalls Fortgeltung dokumentieren. Der Entwurf ändert noch keine Sollstellung. Änderungen im Jahr sind nachvollziehbar; kein doppeltes Nachfordern bereits gebuchter Monate [R04].

**W03 Kostenverteilung.** Teilungserklärung/Gemeinschaftsordnung, wirksame Vereinbarungen, einschlägige Beschlüsse und gesetzliche Vorgaben mit dokumentiertem Geltungsbereich beachten. MEA als gesetzlicher Ausgangspunkt nach § 16 WEG ist nicht in jedem Einzelfall der anzuwendende Schlüssel. Kosten baulicher Veränderungen nach § 21 WEG eigenständig einordnen. Untergemeinschaften, einzelne Hauseingänge und Nutzerkreise benötigen belegte Zuständigkeit/Zuordnung; ein frei angelegter Filter schafft keine Beschlusskompetenz [R02]. Fehlende Grundlage sperrt die betroffene endgültige Verteilung.

**W04 Jahresabrechnung als nachvollziehbare Überleitung.** Gesamtgeldfluss mit Bank-/Kassenabstimmung und verteilungsrelevante Kosten der Einzelabrechnungen getrennt. Geschäftsjahr der WEG ist für § 28 das Kalenderjahr. Rechnungsbuchung im Kreditorenbuch, tatsächliche Zahlung und abrechnungsfähiger Verbrauch können unterschiedliche Zeitbezüge haben. Unterschiede, insbesondere bei Heizkosten, sind über eine Überleitungsrechnung verständlich zu erklären. Keine WEG-Gesamtabrechnung als bloße Gewinn-/Verlustrechnung aus dem Hauptbuch. Jahresbewegungen aus der Vorverwaltung müssen enthalten sein, auch bei Übernahme mitten im Jahr [R04; Rechtsprechungsprüfung P01/P02].

**W05 Abrechnungsspitze und Rückstände.** Kostenbezogenes Abrechnungsergebnis gegen die **beschlossenen Soll-Vorschüsse** ermitteln, nicht gegen zufällig tatsächlich geleistete Zahlungen. Rücklagenkomponenten und andere zweckgebundene Vorschüsse werden separat geführt und abgeglichen. Vorschussrückstände bleiben mit ursprünglichem Rechtsgrund, Fälligkeit und Schuldner eigenständig. Ein zusätzlich angezeigter Abrechnungssaldo aus Spitze plus Rückständen ist als Information zu kennzeichnen und darf die Rückstände nicht nochmals als neue Abrechnungsforderung erzeugen. Guthabenprüfung entsprechend spiegelbildlich. Zahlenfälle D01/D02 sind verbindliche fachliche Abnahmeanforderungen [R04; P01].

**W06 Beschluss und Buchung.** Eigentümer beschließen nach § 28 Abs. 2 WEG über Nachschüsse bzw. Anpassung beschlossener Vorschüsse, nicht durch den internen UI-Knopf „Abrechnung bestätigen“. Nachweis: genaue Beschlussfassung, zugehörige Ergebnisversion, Betrag je Beteiligtem, zuständiges Organ, Zeitpunkt, erfasster Wirksamkeitsstatus und Fälligkeit. Der Beschluss kann zunächst aus einer extern durchgeführten Versammlung übernommen werden; ein fertiges Online-Versammlungsmodul ist keine Voraussetzung für den Nachweis. Beiratsprüfung ersetzt keinen Beschluss. Anfechtung, Nichtigkeit, gerichtliche Ungültigerklärung und Bestandskraft nicht gleichsetzen; eine bloße Anfechtung hebt einen ansonsten gültigen Beschluss nicht automatisch auf [R04, R05].

**W07 Eigentümerwechsel.** Kostenverteilungszeitraum, rechtlicher Eigentumsübergang, Nutzen-/Lastenwechsel aus Kaufvertrag, Vorschussschuldner bei Fälligkeit und Anspruchsinhaber/-schuldner der später beschlossenen Abrechnung sind getrennte Tatsachen. Nicht einfach die WEG-Abrechnung tagesgenau zwischen Verkäufer und Käufer teilen oder Verkäufer-OP auf das neue Konto kopieren. Außenverhältnis zur GdWE und privater Ausgleich aus Kaufvertrag bleiben getrennt. Regelfall und Ausnahmen einschließlich erster Erwerber, Erbfall, Zwangsversteigerung, Sondernachfolgerhaftung und konkret abweichender Gemeinschaftsgrundlagen sind fachlich freizugeben. Keine starre Regel „immer Datum im Mietvertrag“ oder „immer Abrechnungsjahr-Eigentümer“. Für den gewöhnlichen rechtsgeschäftlichen Erwerb ohne Sonderhaftung ist als durch P01 zu bestätigender Regelfall vorzusehen: Der bei Beschlussfassung rechtlich maßgebliche Eigentümer wird aus der Abrechnungsspitze berechtigt/verpflichtet, während alte Vorschussrückstände nicht allein durch den Erwerb auf ihn übergehen. Eine abweichende Adressierung der historischen Abrechnung ersetzt nicht die Schuldnerprüfung. Vollständiger amtlicher Rechtsprechungsabgleich bleibt Freigabepunkt P01.

**W08 Erhaltungsrücklagen.** Je zweckgebundener Position mindestens Anfangsbestand, beschlossene Soll-Zuführung, tatsächliche Zuführung, offene Beiträge, Entnahmen/Mittelverwendung, Zinsen, Steuern/Gebühren und Endbestand, jeweils mit Belegen. Rücklagenentwicklung mit Finanzkonten abstimmen und Abweichungen erklären. Bankanlage auf einem gesonderten Konto und buchhalterischer Rücklagenbestand sind nicht gleichbedeutend. Eine beschlossene, aber unbezahlte Zuführung ist kein vorhandenes Geld. Eine Umgliederung zwischen Bankkonten ist keine zweite Rücklagenzuführung. Finanzierung aus Rücklage und zugrunde liegende Ausgabe nicht doppelt belasten.

**W09 Sonderumlagen und Maßnahmen.** Zweck, Gesamtsumme, Verteilungsgrundlage, betroffene Einheiten, Beschluss, Fälligkeit/Raten und Verwendung führen. Noch offene Sonderumlage, eingegangene Mittel, verwendete Mittel und verbleibender zweckgebundener Bestand getrennt auswerten. Sonderumlage ist nicht automatisch frei verfügbares laufendes Hausgeld. Nicht mehr benötigte Mittel nur auf geprüfter Grundlage umwidmen/erstatten. Beschlussänderung erzeugt dokumentierte Differenzen.

**W10 Darlehen, Versicherungen, größere Maßnahmen.** Darlehensauszahlung, Tilgung, Zins und Gebühren getrennt; keine Darlehensaufnahme als Mietertrag oder Tilgung als laufende Mietbetriebskosten. Versicherungsleistung/Erstattung, Schadenskosten, Selbstbehalt, Regress und Zahlungen an einzelne Eigentümer belegbar verbinden; keine intransparente Verrechnung. Steuer-/Umlagebehandlung und Beschlussgrundlage im konkreten Fall freigeben. Abgrenzung Erhaltung/bauliche Veränderung anhand Sachverhalt und Rechtsgrund, nicht allein KI-Kontierung.

**W11 Vermögensbericht.** Nach Kalenderjahr eigenständiger Bericht nach § 28 Abs. 4 WEG über Rücklagen und wesentliches Gemeinschaftsvermögen, jedem Eigentümer verfügbar zu machen. Als Produktumfang zusätzlich liquide Mittel, wesentliche Forderungen, Verbindlichkeiten und Darlehen transparent nachweisen. Unterscheiden zwischen gesetzlichen Mindestangaben und ergänzenden Projektangaben. Nicht mit Jahresabrechnung, Handelsbilanz oder „Summe aller Bankkonten“ verwechseln [R04].

**W12 Abrechnungspaket.** Gesamt-/Einzelabrechnungen, Schlüssel und Rechenwege, Soll-/Ist-Vorschüsse, gesonderte Rückstände, Rücklagenentwicklung, Vermögensbericht, gegebenenfalls steuerlicher Ausweis, Beschlussvorlage und Prüfbericht. Jeder Betrag ist zur Einzelposition und zum verfügbaren Beleg rückverfolgbar. Fehlt ein Beleg, wird dies sichtbar; kein stilles Entfernen des zugrunde liegenden Bankumsatzes. Negative oder null Schlüsselgesamtsummen, Überlappungen von Eigentumsperioden, fehlende Einheiten und ungeklärte Geldflussdifferenzen blockieren die betroffene Freigabe.

**W13 Beirat und Versammlung.** Beiratsprüfung nach Abschnitt 7.9 vor den einschlägigen §-28-Beschlüssen vorsehen, ohne einen nicht vorhandenen Beirat zu erfinden. Keine Gleichsetzung von fachlicher Prüfung, Entlastung, Zahlungsfreigabe und Beschluss. Fristen, Vollmachten, Kopf-/Objekt-/Wertstimmrecht, gemeinschaftliches Stimmrecht, Stimmrechtsausschlüsse und Mehrheitsbasis nach §§ 23–25 WEG und gültiger Gemeinschaftsregel abbilden. Virtuelle Versammlung: belegter Grundlagenbeschluss, zulässige Mehrheit, höchstens dreijährige Geltung und vergleichbare Rechteausübung; Übergangsregel des § 48 Abs. 6 prüfen. Umlaufbeschluss grundsätzlich Zustimmung aller in Textform, abweichende Mehrheit nur bei zulässiger Grundlage für den einzelnen Gegenstand. Beschluss-Sammlung revisionsfähig fortführen; Status „gelöscht“ ist kein Auftrag zur physischen Beseitigung vorgeschriebener Historie [R05].

### 7.9 Rechnungskontrolle, Beiratsprüfung und Belegeinsicht

Diese drei Vorgänge sind getrennte Funktionen, können aber dieselbe unveränderte Belegbasis nutzen. Das folgende Verfahren beschreibt den gewünschten Produktumfang, nicht eine gesetzliche Pflicht zu genau dieser Oberfläche.

#### 7.9.1 Laufende Rechnungskontrolle

**PÜ01 Vollständigkeit.** Originalrechnung einschließlich Seiten/Anhängen, bei E-Rechnung strukturierter Teil und relevante Anlagen, Rechnungsaussteller/-empfänger, Leistungsort/-zeit, Nummer, Beträge, Steuerangaben und Bezug zu Auftrag/Vertrag. Fehlende Pflichtangaben oder Rechnung an falschen Rechtsträger sichtbar kennzeichnen; begründete steuerliche Ausnahmen getrennt behandeln. Dauerrechnung, Vertrag, Abschlag, Gutschrift und Schlussrechnung unterscheiden.

**PÜ02 Sachliche Prüfung.** Leistung tatsächlich erbracht? Richtiger Auftrag, Objekt-/Einheitenbezug, Preis-/Mengenabgleich, Nachträge, Aufmaß/Arbeitsnachweise, Abnahme oder Mängel? Auftrag/Beschluss/Budget vorhanden und Zuständigkeit gedeckt? Wiederkehrende Kosten mit Vertrag und Leistungszeitraum prüfen. Verbundene Unternehmen/Interessenkonflikte anzeigen. Eine erfolgreiche XML-Prüfung beantwortet diese Fragen nicht.

**PÜ03 Rechnerische/steuerliche Prüfung.** Positionen, Netto/Brutto, Steuer, Skonto, Teilzahlungen, Anzahlungen, Sicherheitseinbehalte und Gesamtbetrag nachrechnen. §-35a-Anteil aus belegbarer Aufteilung, nicht erfundener KI-Schätzung. Reverse Charge/Bauabzugsteuer und Vorsteuerberechtigung bei einschlägigem Sachverhalt zur Fachprüfung. Steuerliche Richtigkeit ist von formaler Dateigültigkeit getrennt [R20–R24].

**PÜ04 Dubletten/Betrugsrisiko.** Gleiche Lieferantenrechnung über E-Mail und DMS erkennen; korrigierte Version und zweite echte Leistung nicht verschlucken. Zahlungsdaten mit freigegebenen Stammdaten und Vorversion abgleichen. Geänderte IBAN gesondert bestätigen; Aufforderungen in Dokumenten dürfen keine Systemanweisung werden. Keine Zahlung nur aufgrund eines neuen QR-Codes oder eines vermeintlich überzeugenden E-Mail-Textes.

**PÜ05 Prüfentscheidungen.** Pro Prüfschritt Person, Zeitpunkt, geprüfte Version, Umfang, Ergebnis und Begründung. Status mindestens fachlich unterscheidbar: offen, teilweise geprüft, Rückfrage, beanstandet, mit Vorbehalt abgeschlossen, ohne festgestellte Beanstandung abgeschlossen. Rechnungsfreigabe, Buchungsfreigabe und Zahlungsfreigabe besitzen getrennte Bedeutung. Delegation und Vier-Augen-Prinzip sind dokumentiert. Kein Prüfstatus wird ohne tatsächliche Prüfung automatisch „grün“.

#### 7.9.2 Digitaler Prüfungsraum für Beirat und beauftragte Prüfer

**PÜ06 Prüfauftrag.** GdWE, Kalenderjahr/Zeitraum, Prüfzweck, Berechtigung, Prüfer, Gesamtpopulation, Stichprobe/Vollprüfung, einbezogene Konten und Datenstand festhalten. Beirat unterstützt und überwacht; Wirtschaftsplan und Jahresabrechnung sollen vor den einschlägigen Beschlüssen geprüft und mit Stellungnahme versehen werden (§ 29 WEG). Beiratsstellungnahme ist kein uneingeschränktes Testat [R03].

**PÜ07 Nachvollziehbare Navigation.** Von Gesamtabrechnung/Einzelabrechnung über Kostenkonto, Buchung und Verteilung zum Originalbeleg und zur Zahlung; Rückweg ebenso. Nebeneinander Beleg, Kontierung, Auftrag/Vertrag, Betrag, Empfänger, Leistungszeit, Zahlung, Umlageschlüssel, Rücklagen-/Steuerkennzeichen, Vorjahresvergleich und vorhandene Freigaben. Auch Dauerbelege, Kontoauszüge, relevante Verträge und fehlende Unterlagen müssen auffindbar sein; nicht ausschließlich Rechnungs-PDFs.

**PÜ08 Prüfen und nachfordern.** Filter nach Konto, Betrag, Lieferant, Datum, fehlendem Beleg, Risikohinweis und Prüfstatus. Prüfer kann positions-/seitenbezogene Vermerke und Rückfragen erfassen. Verwaltung antwortet nachvollziehbar, ergänzt Unterlagen und weist Änderungen aus. Keine eigenständigen Buchungen durch reine Prüfrolle. Neue Abrechnungsversion invalidiert betroffene alte Prüffreigaben oder markiert deren eingeschränkte Aussagekraft.

**PÜ09 Aussagekräftiger Abschlussbericht.** Geprüfte und ungeprüfte Positionen, Stichprobenmethode/Umfang, fehlende Belege, Feststellungen, Erläuterungen, offene Beanstandungen und Empfehlung als datierter versionierter Bericht. Zahl und Wert der tatsächlich geprüften Positionen getrennt anzeigen. „Alle ausgewählten Belege geprüft“ darf nicht „gesamte Abrechnung geprüft“ bedeuten. Bericht optional unterzeichnen/bestätigen; eine qualifizierte elektronische Signatur nicht pauschal als gesetzlich zwingend behaupten.

#### 7.9.3 Eigentümer- und Mietereinsicht

**PÜ10 Eigentümer.** Einsichtsrecht in Verwaltungsunterlagen nach § 18 Abs. 4 WEG gilt für jeden berechtigten Eigentümer und ist kein Beiratsprivileg. Die Einsicht kann gemeinschaftsbezogene Unterlagen außerhalb der eigenen Einzelabrechnung betreffen. Datenschutz ist kein pauschaler Ausschlussgrund, verlangt aber zweckbezogene Berechtigung und erforderlichen Schutz. Keine Freigabe von Daten einer anderen GdWE oder privater, sachfremder SEV-/Mieterakten [R01, R25].

**PÜ11 Mieter.** Belegeinsicht in die seiner Abrechnung zugrunde liegenden Belege nach § 556 Abs. 4 BGB; elektronische Bereitstellung ist ausdrücklich vorgesehen. Erforderliche Verträge, Rechnungen und zugehörige Zahlungs-/Verteilungsnachweise im zutreffenden Umfang zugänglich machen. Keine pauschale Verweigerung aller Vergleichs-/Verteilungsinformationen wegen anderer Namen, aber auch keine unbeschränkte Öffnung sämtlicher privaten Akten. Schwärzungen mit Grund, Umfang und nachvollziehbarem Bearbeitungsschritt; Original bleibt geschützt erhalten [R06, R25].

**PÜ12 Praktischer Zugang.** Zeitlich/inhaltlich berechtigte Einladungen oder bestehende Konten, Leserechte, Suche, sortierte Belegliste, verknüpfte Anzeige und vom Berechtigungsumfang gedeckter Einzel-/Sammel-Download. Bereitstellungspaket mit Index und prüfbaren Dateiverweisen auch außerhalb des Portals erzeugen können. Kein Portalzwang als generelle Voraussetzung gesetzlicher Einsicht: Anfragen, Termin-/Vertretungsnachweise und alternative Einsicht dokumentieren. Ob Kopien, Fernzugriff oder besondere Form verlangt werden können, ist vom gesetzlichen Anspruch und Einzelfall zu unterscheiden; die Komfortfunktionen sind Produktleistungen.

**PÜ13 Protokoll ohne Rechtsfiktion.** Antrag, Umfang, Freigabe, Benachrichtigung, Bereitstellung, tatsächlicher Abruf, Rückfragen und Antwort protokollieren. Ein Klick, Lesestatus oder Schweigen ist keine Anerkennung der Abrechnung, kein Verzicht auf Einwendungen und nicht automatisch gerichtsfester Zugangsnachweis. Berechtigungen bei Rollen-/Eigentümerwechsel prüfen; berechtigte historische Ansprüche nicht pauschal durch Vertragsende abschneiden. Alte Freigabelinks dürfen keine fortdauernde unkontrollierte Einsicht eröffnen.

### 7.10 Heizkosten, CO₂ und § 35a EStG

**H01 Messdienst oder Eigenberechnung.** Externe Heizkostenabrechnung vollständig mit GdWE/Objekt, Zeitraum, Nutzer-/Einheitenmapping, Kostenbestandteilen, Summen, Verbrauch, CO₂-Aufteilung und Dateiversion prüfen. Unbekanntes proprietäres Format wird nicht erfunden. Rechenimport plus Originalrechnung/Abrechnung erhalten. Keine doppelte Erfassung von Heizkosten aus Rechnungsbuch und Messdienstsumme. Eigene Heizkostenberechnung nur im ausdrücklich fachlich freigegebenen Umfang; bis dahin Import und kontrollierte Überleitung.

**H02 HeizkostenV.** Anwendbarkeit/Ausnahmen, Nutzergruppen, verbrauchsabhängiger Anteil, verbrauchsunabhängiger Anteil, Warmwassertrennung, Schätzung, Nutzerwechsel und Pflichtinformationen unterscheiden. Nicht stets frei zwischen 50/50 und 30/70 wählen: § 7 enthält Fälle mit verpflichtendem Verbrauchsanteil. Zwischenablesung und Gradtags-/Zeitanteile nach § 9b berücksichtigen. Kürzungsrechte nach § 12 nicht unbesehen aus dem Mietverhältnis auf Eigentümer gegen die GdWE übertragen [R11–R14].

**H03 Laufende Pflichten.** Bei einschlägiger fernablesbarer Ausstattung unterjährige Verbrauchsinformationen nach § 6a bereitstellen; technische Phase 4 verschiebt keine bestehende Pflicht. Falls Portalmodul noch fehlt, dokumentierten Ersatzprozess mit dem Messdienst/Verwalter verlangen. Nachrüst-/Übergangsfristen des § 5 und Sonderfälle wie Wärmepumpen nach § 12 als datierte Prüfpunkte führen, nicht pauschal aus alten Vorlagen übernehmen [R12, R14].

**H04 CO₂-Regeln mit Geltungsstand.** Gebäude-/Nutzungsart, Versorgungsart, Anwendbarkeit, Heizwert-/Mengenangaben, Emissionen, Fläche, Abrechnungsdauer, Kosten und erforderliche Nachweise erfassen. Wohngebäude: zutreffende Stufe der gesetzlichen Tabelle; Nichtwohngebäude: gesonderte gesetzliche Regel; öffentlich-rechtliche Beschränkungen und Selbstversorgung gesondert. Vermieteranteil nicht dem Mieter belasten. Fehlende Angaben bleiben sichtbar, nicht Null setzen. Grenzwerte, Rundungen und zeitliche Hochrechnung benötigen genaue Normzuordnung und Tests [R15].

**H05 Bereits veröffentlichte spätere Regeln.** Die am 23.09.2026 abgerufene CO2KostAufG-Gesamtfassung enthält die Änderung vom 23.07.2026, einschließlich §§ 5a–5d und späterer Anwendungszeitpunkte insbesondere 2028/2029. Diese werden im Rechtsregister als datierte Prüf-/Umsetzungsanforderung geführt, nicht vorzeitig auf die Abrechnung 2026 angewendet. Ebenso ist eine im Gesetz angekündigte künftige Reform kein selbst erfundenes aktuelles Berechnungsmodell. Vor Umsetzung Wortlaut, Inkrafttreten und konkreten Heizungs-/Gebäudesachverhalt erneut amtlich prüfen [R16].

**H06 § 35a.** Begünstigungsart, belegbarer Arbeits-/Dienstleistungsanteil, nicht begünstigte Bestandteile, Zahlung, Kostenträger und Verteilung nachvollziehbar ausweisen. Keine erfundenen Lohnanteile, kein Ausweis allein wegen einer unbezahlten Rechnung oder Rücklagenzuführung, keine Mehrfachbescheinigung derselben getragenen Aufwendungen. Selbstnutzung/Vermietung und steuerliche persönliche Voraussetzungen nicht durch eine Konto-Checkbox entscheiden. Die Bescheinigung stellt Nachweisdaten bereit; die individuelle Steuerermäßigung wird nicht garantiert [R24].

### 7.11 Steuern, E-Rechnung, Aufbewahrung und Datenschutz

**S01 Steuerlicher Kontext.** Unternehmer/Rechtsträger, Tätigkeit, Steuerbefreiung/Option, Rechnungsempfänger, Vorsteuerberechtigung und Leistungszeitraum feststellen. USt-Option nicht automatisch aus „Gewerbeeinheit“ ableiten. Direkt zuordenbare Vorsteuer und sachgerechte Aufteilung gemischter Eingangsleistungen unterscheiden. Eine frei gewählte Gewerbeflächenquote ist nicht stets zulässig. § 13b UStG, Bauabzugsteuer/Freistellungsbescheinigung (§§ 48 ff. EStG) und mögliche Vorsteuerberichtigung sind bei einschlägigen Fällen gesonderte Freigabepunkte, keine pauschalen Automatiken [R20, R23; P03].

**S02 E-Rechnung.** Empfang, lesbare Darstellung, sachliche Verarbeitung und unveränderte Aufbewahrung strukturierter Rechnungen unterstützen. PDF allein nicht mit einer strukturierten E-Rechnung gleichsetzen. XRechnung/ZUGFeRD nach tatsächlich gültiger Spezifikation und zulässigem Profil prüfen; Variante, Validatorversion und Ergebnis speichern. Ausstellungs-/Empfangspflicht je Beteiligtem/Umsatz samt Ausnahme und Übergangsfrist bewerten, nicht alle Eigentümer/WEG pauschal als gleiche Unternehmer behandeln. Formale Validität beweist weder Leistung noch Zahlungsberechtigung. Korrekturrechnung mit Ursprungsbezug statt Überschreiben [R21, R22].

**S03 Original und Verarbeitung.** Strukturierte empfangene Rechnungsdaten unversehrt erhalten; ein extrahiertes JSON oder nachträglich erzeugtes PDF ersetzt sie nicht. Bei hybriden Rechnungen relevante zusätzliche/abweichende Angaben ebenfalls erhalten. Als Produktstandard kann die komplette empfangene Datei samt benötigten Anlagen archiviert werden; dies nicht als pauschale gesetzliche Pflicht zur Speicherung jedes Bildteils ausgeben. OCR, Darstellung, Schwärzung und Kompression bleiben abgeleitete Versionen und zerstören keine aufbewahrungspflichtige Ursprungsinformation [R19, R21].

**S04 Differenzierte Fristen.** Keine pauschale Regel „alle Belege zehn Jahre“ oder „alles nach acht Jahren löschen“. Bei Anwendbarkeit unterscheiden AO/HGB unter anderem zehnjährige Buch-/Organisationsunterlagen, achtjährige Buchungsbelege und sechsjährige weitere Unterlagen; Sonderregeln, Übergänge und Fristbeginn sind zu prüfen. § 14b UStG enthält für Unternehmer eine achtjährige Rechnungsaufbewahrung. Daraus folgt keine identische pauschale steuerliche Pflicht jeder GdWE. Profile nach Rechtsgrund, Rechtsträger, Unterlagenart, Fristbeginn, Ende und Sperrgrund führen [R17, R18, R21].

**S05 WEG-Dauerunterlagen, Sperren und Löschung.** Teilungserklärung, Gemeinschaftsordnung, Beschlüsse, Rechtsstreit-/Gewährleistungsnachweise und andere weiter benötigte Unterlagen dürfen nicht wegen eines Buchungsbeleg-Standardprofils verschwinden. Aufbewahrungsbedarf und Rechtsgrund dokumentieren. Offene steuerliche Verfahren, Rechtsstreit, Beweissicherung und sonstige maßgebliche Sperren prüfen. Löschung in Index, DMS-Spiegel, Ableitungen und Wiederherstellungsabläufen konsistent behandeln. Backups sind Betriebsabsicherung, kein Ersatz für geordnetes, jederzeit nutzbares Archiv. Ein pauschales zehnjähriges Backup aller personenbezogenen Daten bedarf eigener Rechtfertigung [R17–R19, R25].

**S06 Datenschutz und Auskunft.** Rechtsgrundlage, Verantwortlichkeiten zwischen GdWE/Verwalter/Betreiber, erforderliche Auftragsverarbeitung, Unterauftragnehmer, Zugriffe und Drittlandübermittlungen vor Produktivbetrieb prüfen. Pflichtverarbeitung nicht ausschließlich auf widerrufliche Einwilligung stützen. Auskunftsexport darf nicht ungeprüft Geheimnisse oder Daten anderer Personen enthalten. KI-Zugriff nur im zulässigen Umfang; ein AVV-Häkchen oder abgeschaltetes Training genügt nicht. Dokumentierte Löschungssperren stehen einer pauschalen „alles löschen“-Aktion entgegen, ohne unnötige Daueraufbewahrung zu rechtfertigen [R25].

### 7.12 Fachliche Abnahme und Pflege

Für jede finanzrelevante Funktion: Anforderung → maßgebliche Quelle/Objektgrundlage → Entscheidung/Regelversion → Test mit Sollwert → Protokoll der tatsächlichen Ausführung → Freigabe. Anhang D definiert den Mindestumfang. Anforderungen vor Veröffentlichung gegen den dann gültigen Rechts-/Spezifikationsstand prüfen; keine rückwirkende Änderung bereits versandter Abrechnungen durch ein Update. Gesetzliche Neuregelungen erhalten Wirksamkeitsdaten und betroffene Fallgruppen.

Eine zuständige, fachkundige Person bestätigt den Buchungs-/Abrechnungsstandard mit repräsentativen Fällen. Bei unklarer Rechtsauslegung ist anwaltliche, bei Steuerfragen steuerliche Klärung einzuholen. Claude bestimmt nicht eigenständig eine strittige Rechtsregel, nur um die Tests grün zu bekommen. Die operative Freigabe erfolgt pro Funktionsumfang und Objektgruppe, nicht pauschal für die gesamte Plattform.

---

## 8. Bank-Adapter

### 8.1 Schnittstelle

```python
class BankConnector(Protocol):
    def list_accounts(self) -> list[BankAccountInfo]: ...
    def fetch_transactions(self, account: BankAccountInfo, since: date, until: date) -> list[RawTransaction]: ...
    def fetch_balance(self, account: BankAccountInfo) -> Balance: ...
    def submit_payment_batch(self, batch: PaymentBatch) -> SubmissionResult: ...   # nur EBICS
    def consent_status(self) -> ConsentStatus: ...                                  # Aggregator
```

Implementierungen: `EbicsConnector` (fintech.ebics, Kontoauszüge als CAMT.053 über Auftragsart C53, Zahlungen als pain.001 CCT und pain.008 CDD, VEU-Freigabe optional), `FinApiConnector` und `GoCardlessConnector` (Kontoinformationsdienst, OAuth-Zustimmungsfluss des Kontoinhabers in der Oberfläche, Erinnerung vor Ablauf der Zustimmung), `FintsConnector` (python-fints, PIN/TAN, nur als Rückfall mit manueller TAN-Freigabe in der Oberfläche), `FileImportConnector` (CAMT.053 XML, MT940, CSV der gängigen Banken, Immoware24-Umsatzexport).

Alle Konnektoren liefern `RawTransaction` in einheitlichem Schema (ISO-20022-Feldnamen), die Normalisierung in `bank_transaction` inklusive Hash erfolgt zentral.

### 8.2 Abrufplan und Fehlerbehandlung

- Job `bank.sync_all` täglich 06:00 Uhr je Mandant (konfigurierbar, zusätzlich manuell), je Konto eigener Task mit Wiederholung bei temporären Fehlern (3 Versuche, exponentiell).
- Aggregator-Zustimmungen: Ablaufdatum in `bank_connection.consent_valid_until`; Benachrichtigung 10 Tage vorher an Buchhaltung; geführter Erneuerungsfluss.
- Bankantworten und Rohdaten werden im MinIO abgelegt (`bank/<tenant>/<account>/<date>.xml`) und 10 Jahre aufbewahrt.
- Sync-Protokoll je Lauf: Anzahl neu, Dubletten, automatisch gebucht, Vorschläge, Fehler.

### 8.3 Empfehlung und Einrichtung

EBICS für die Hauptbanken (Firmenkundenverträge je Bank erforderlich, Einrichtung mit INI/HIA-Briefen, Bankschlüssel-Verifikation, Dokumentation in `docs/runbooks/ebics-setup.md`), Aggregator für alle übrigen Konten (Anbieterentscheidung nach Angebot, Konnektor austauschbar). FinTS nur, wenn beides nicht verfügbar ist. Die Liste aller Bankkonten je Mandant mit Bank, Kontotyp und geplantem Konnektor liegt in `docs/OPEN_QUESTIONS.md` als Aufgabe für den Betreiber.

---

## 9. KI-Gateway

### 9.1 Architektur

- Paket `mhvp.ai` mit `ProviderClient` für Anthropic (Messages API, Tool Use, strukturierte Ausgaben) und OpenAI (Responses API, Structured Outputs). Beide Anbieter sind je Mandant hinterlegbar; die Zuordnung Aufgabe zu Modell steht in `ai_provider_config.models` (z. B. Extraktion mit starkem Modell, Klassifikation mit kleinem Modell). Fallback auf den zweiten Anbieter bei Fehler oder Budgetgrenze.
- **Prompt-Registry**: Prompts als versionierte Dateien in `apps/api/src/mhvp/ai/prompts/<task>/<version>.md` mit Systemanweisung, Ausgabeschema (JSON Schema, Pydantic), Beispielen. Jede Ausführung protokolliert `prompt_version`.
- **Strukturierte Ausgaben**: Jede Aufgabe definiert ein Pydantic-Schema; Antworten werden validiert, bei Schemafehlern einmal mit Fehlermeldung wiederholt, dann als Fehler protokolliert.
- **Kontext**: Werkzeuge (Tool Use) für Nachschlagen in Fachdaten (Kontakte suchen, Verträge eines Objekts, Kontenplan, offene Posten), damit das Modell nicht rät, sondern nachschlägt. Werkzeuge sind nur lesend; Schreiben erfolgt ausschließlich über bestätigte Vorschläge.
- **RAG**: Dokumente und Freitexte werden je Mandant in Abschnitte zerlegt, eingebettet (`pgvector`) und für Fragen im Kontext-Chat und im Portal-Chat abgerufen; Zugriff nur auf Dokumente, die der Fragende sehen darf (Berechtigungsfilter vor der Ähnlichkeitssuche).
- **Lernen je Mandant**: `ai_example` speichert bestätigte Ergebnisse (Eingabemerkmale, Ergebnis, Embedding). Vor jeder Aufgabe werden die k ähnlichsten Beispiele des Mandanten als Few-Shot-Kontext geladen (Standard k=8). Kein Fine-Tuning in Phase 1 bis 3; die Schnittstelle ist so gebaut, dass später ein mandanteneigenes Modell eingehängt werden kann.
- **Kosten und Grenzen**: Token- und Kostenzähler je Aufgabe, Budget je Mandant und Monat, harte Sperre bei Überschreitung mit Benachrichtigung, Kostenanzeige im Admin-Dashboard.
- **Datenschutz**: Datenminimierung je Aufgabe (nur benötigte Felder), Pseudonymisierung von Namen und IBANs, wo die Aufgabe es zulässt (Kontierung braucht Zahlername; Textentwürfe brauchen nur Anrede), Auftragsverarbeitungsvertrag je Anbieter als Pflichtfeld in der Konfiguration, EU-Endpunkte bevorzugen, keine Trainingsnutzung durch Anbieter (Opt-out bestätigen).
- **Evaluation**: Für jede Aufgabe ein Goldstandard-Datensatz in `apps/api/tests/ai_eval/<task>/` (anonymisiert) mit Zielmetrik (Genauigkeit, Feld-F1); `make ai-eval` läuft vor jeder Prompt-Änderung und in CI (mit aufgezeichneten Antworten, keine Live-Aufrufe in CI).

### 9.2 Aufgaben

| Aufgabe | Eingabe | Ausgabe (Schema) | Verwendung |
| --- | --- | --- | --- |
| `extract_contacts` | Tabelle oder Dokumenttext | Liste Kontakte mit Typ, Adressen, Telefonen, E-Mails, Bankverbindungen, Bezug (Einheit, Rolle), Konfidenz je Feld, Rückfragen | Onboarding-Chat Kontakte |
| `extract_property` | Teilungserklärung, Eigentümerliste, Mieterliste, Abrechnung, Wirtschaftsplan | Objekt, Gebäude, Einheiten mit MEA, Flächen, Lage; Vertragsparteien mit Beginn; Zahlungen; Bankverbindungen; Rückfragen | Onboarding-Chat Objekt |
| `propose_posting` | Bankumsatz, Kandidatenlisten (Verträge, Debitoren, Kreditoren, Konten), ähnliche Beispiele | Konto, Debitor/Kreditor, Objekt, Aufteilung, Konfidenz, Begründung | Kontierung |
| `extract_invoice` | Rechnungs-PDF oder E-Rechnungs-XML | Kreditor, Nummer, Datum, Fälligkeit, Beträge, Positionen mit Kostenkonto-Vorschlag, Objektbezug, Skonto, §35a-Anteil, Dublettenverdacht | Belegeingang |
| `classify_email` | E-Mail mit Anhängen | Kategorie, Objekt, Kontakt, Dringlichkeit, Ticketvorlage, Zusammenfassung, Terminbezug | Postfach |
| `draft_reply` | Ticket oder E-Mail, Kontext, Mandanten-Stilvorgaben | Antwortentwurf, Tonfall, Platzhalter | Kommunikation |
| `check_statement` | Abrechnungsergebnis, Vorjahr, Konten | Auffälligkeiten mit Schwere und Erklärung, Erklärtexte für Empfänger | Abrechnung |
| `answer_question` | Frage, Rolle, Kontext (RAG) | Antwort mit Quellenverweisen, vorgeschlagene Aktion (Ticket) | Kontext-Chat, Portal-Chat |
| `summarize` | Dokument oder Verlauf | Zusammenfassung, offene Punkte | überall |

### 9.3 Modellstufen und Kostenoptimierung

Jede KI-Aufgabe wird einer Modellstufe zugeordnet; die konkrete Modellbezeichnung je Stufe und Anbieter steht in `ai_provider_config.models` und ist ohne Code-Änderung austauschbar.

| Stufe | Einsatz | Beispiele (Aufgaben) |
| --- | --- | --- |
| `embedding` | Ähnlichkeitssuche, RAG, Lernbeispiele | alle Embeddings; optional lokal (Ollama auf dem Server, CPU) |
| `small` | Klassifikation, Routing, Zusammenfassung, einfache Extraktion, Antwortvorschläge im Portal | `classify_email`, `summarize`, `propose_posting` bei klaren Fällen, Vorfilter für `extract_invoice` |
| `large` | komplexe Extraktion aus langen Dokumenten, Abrechnungsprüfung, Kontierung mit niedriger Konfidenz, Onboarding aus Vorverwalterakten | `extract_property`, `check_statement`, Eskalationen |

Regeln: Kaskade (erst `small`, bei Konfidenz unter Schwelle oder Schemafehler `large`); Prompt-Caching für wiederkehrende Systemanweisungen und Kontexte (Kontenrahmen, Kataloge); Batch-Verarbeitung für nicht zeitkritische Läufe (nächtliche Klassifikation, Historienanalyse) über die Batch-Schnittstellen der Anbieter; Deduplizierung identischer Anfragen über Hash; deterministische Vorverarbeitung ohne KI, wo möglich (IBAN-Abgleich, Regex für Vertragsnummern, Tabellenerkennung in Excel); Kontext knapp halten (nur benötigte Felder, Kandidatenlisten statt Gesamtdaten); Kosten je Aufgabe und Mandant im Dashboard mit Monatsbudget und Warnstufe bei 80 Prozent; Evaluation vor jedem Stufenwechsel, damit Einsparungen nicht die Genauigkeit senken.

### 9.4 Sicherheitsregeln

- Keine Zahlungsfreigabe, keine Vertragsänderung, keine Buchung ohne Konfidenzschwelle und keine rechtsverbindliche Erklärung durch KI.
- Prompt-Injection-Schutz: Dokumentinhalte werden als Daten markiert, Systemanweisungen verbieten das Befolgen von Anweisungen aus Dokumenten; Werkzeuge sind nur lesend; Ausgaben sind Schema-validiert.
- Jede KI-Ausgabe in der Oberfläche ist als Vorschlag gekennzeichnet (Symbol, Konfidenz, „Warum?“ mit Begründung und Quellen).

---

## 10. Onboarding-Chat

Der Onboarding-Chat ist die zentrale KI-Funktion für Objektübernahmen und Datenerfassung. Er ist an drei Stellen verfügbar: global (Kontakte, mehrere Objekte), am Objekt (Reiter „Assistent“) und am Kontakt.

### 10.1 Ablauf Kontaktliste

1. Nutzer lädt Datei (Excel, CSV, PDF, Foto) hoch oder fügt Text ein und schreibt z. B. „Lege die Eigentümer aus dieser Liste für Objekt 342 an“.
2. System erkennt Format, extrahiert Tabelle (Excel direkt, PDF über Text oder OCR), ruft `extract_contacts` mit dem Objektkontext auf.
3. Rückfragen bei Unklarheiten in einer Nachricht gesammelt (z. B. „Spalte D enthält Telefonnummern ohne Vorwahl. Soll ich +49 ergänzen?“, „Drei Zeilen enthalten zwei Namen. Als eine Vertragspartei mit zwei Personen anlegen?“).
4. Vorschau als Tabelle mit Ampel: neu, vorhanden (Dublette mit Ähnlichkeitswert), unvollständig. Nutzer kann Zeilen ausschließen, Dubletten zusammenführen, Rolle ändern.
5. Bestätigung erzeugt `import_run` mit allen erzeugten Entitäten. „Rückgängig“ darf nur noch nicht rechtlich/finanziell gebundene Anlagen unter Beachtung von Referenzen, Audit und Aufbewahrung zurücknehmen. Gebuchte Inhalte werden nicht gelöscht; verknüpfte Originale und gesperrte Unterlagen bleiben erhalten. Vor Rücknahme werden Folgen und nicht rücknehmbare Bestandteile angezeigt.
6. Nach Anlage bietet der Chat Folgeschritte an: Portaleinladungen versenden, Verträge anlegen, fehlende Daten per Formular anfordern.

### 10.2 Ablauf Objekt aus Vorverwalterakte

1. Nutzer lädt Unterlagen hoch (Teilungserklärung, Aufteilungsplan, Eigentümerliste, Mieterliste, letzte Abrechnung, Wirtschaftsplan, Kontenliste, Bankverbindungen) und schreibt „Lege dieses Objekt mit allen Einheiten an“.
2. System klassifiziert Dokumente (Anbindung an die Objektakte-Klassifikation, Abschnitt 13.2), extrahiert mit `extract_property`: Objektstammdaten, Gebäude, Einheiten (Nummer, Lage, Typ, Fläche, MEA), Eigentümer je Einheit mit Beginn, Mieter je Einheit mit Beginn und Zahlungen, Umlageschlüssel und Werte, Bankkonten, Verwalterhonorar, Abrechnungszeitraum.
3. Rückfragen gesammelt, Vorschau als Baum (Objekt, Gebäude, Einheiten, Verträge) mit Konfidenzen je Feld und Quellenverweis (Dokument, Seite).
4. Personen werden gegen das Adressbuch abgeglichen (Name, Adresse, IBAN, E-Mail; Schwellwerte konfigurierbar); Treffer werden verknüpft, Nichttreffer als `completeness = incomplete` angelegt (Mindestfelder: Name, Rolle, Bezug).
5. Bestätigung legt alles in einer Transaktion an: Objekt mit Buchungskreis aus Vorlage, Gebäude, Einheiten, Umlageschlüssel und Werte, Verträge mit Debitorenkonten, Zahlungen, Bankkonten, Dokumente im DMS mit Verknüpfungen. Status des Objekts `onboarding` bis der Nutzer es aktiviert.
6. Der Chat führt eine Checkliste „Objektübernahme“ (Legitimationsunterlagen, Bankvollmachten, Versicherungen, Dienstleisterverträge, Zähler, Rücklagenstände, offene Posten der Vorverwaltung) und erzeugt Aufgaben für fehlende Punkte.

### 10.3 Technische Vorgaben

- Chat-Verlauf je Sitzung gespeichert (`ai_conversation`, `ai_message`), Dateien im MinIO, Bezug zu `import_run`.
- Antwortzeit: Extraktion asynchron über Worker mit Fortschrittsanzeige; Rückfragen synchron.
- Alle Anlagen sind Vorschläge bis zur Bestätigung; keine Teilanlage ohne Nutzeraktion.
- Der Chat kann Aktionen ausführen (Werkzeuge): Kontakt suchen, Objekt anlegen (Vorschlag), Ticket anlegen, Dokument ablegen, Portaleinladung vorbereiten, Brief aus Vorlage erzeugen. Jede Aktion erfordert Bestätigung im Chat.

---

## 11. DMS-Anbindung

### 11.1 Grundsatz

Die Plattform hat einen eigenen Dokumentenindex (`document`, `document_link`, Volltext, Embeddings) und speichert Originale im MinIO. Zusätzlich kann je Mandant ein externes DMS als Spiegel oder als Primärspeicher konfiguriert werden: Paperless-ngx (bevorzugt, bereits bei der Müller-Gruppe unter dms.muellerhv.de im Einsatz) und/oder Google Drive (Ordnerstruktur der Objektakte). Beide gleichzeitig sind erlaubt (z. B. Paperless für Belege, Drive für Objektakten).

### 11.2 Schnittstelle

```python
class DocumentStore(Protocol):
    def put(self, doc: DocumentPayload, meta: DocumentMeta) -> StorageRef: ...
    def get(self, ref: StorageRef) -> bytes: ...
    def update_meta(self, ref: StorageRef, meta: DocumentMeta) -> None: ...
    def delete(self, ref: StorageRef) -> None: ...   # nur wenn Aufbewahrungsfrist abgelaufen
    def search(self, query: DocumentQuery) -> list[StorageRef]: ...
    def subscribe_changes(self) -> Iterator[ChangeEvent]: ...   # Paperless Webhook / Drive Changes API
```

- `PaperlessStore`: REST-API von Paperless-ngx (Token je Mandant), Zuordnung: Mandant und Objekt als Tags (`mhvp:tenant:<slug>`, `objekt:<nummer>`), Kontakt als Korrespondent, Dokumenttyp aus `document_category`, Custom Fields für `entity_type`/`entity_id`; Post-Consume-Webhook von Paperless meldet neue Dokumente, die dann klassifiziert und verknüpft werden (Belegeingang). Paperless erledigt OCR; der Volltext wird per API übernommen.
- `GoogleDriveStore`: technisches Workspace-Konto (bei der HVM `ablage@muellerhv.de`, OAuth über internes Cloud-Projekt), Wurzelpfad je Mandant, Objektordner „NNN Ort, Straße Hausnummer“, Unterordner `01_Legitimationsunterlagen`, `02_Stammakte`, `03_Buchhaltung`, `04_Mieterakte`, `05_Eigentümerakte`, `06_Sonstiges` (verbindliche Struktur der Objektakte); Drive-ID wird als `storage_ref` gespeichert; Änderungen über die Changes-API abgeholt.
- `MinioStore`: Standard für generierte Dokumente und Uploads; Lebenszyklusregeln für temporäre Dateien.

### 11.3 Regeln

- Jedes generierte Dokument (Brief, Abrechnung, Mahnung, Protokoll, Rechnung) wird automatisch abgelegt und mit allen betroffenen Entitäten verknüpft; es gibt kein manuelles „in DMS speichern“.
- Portalfreigaben beachten zusätzlich den nachgewiesenen Objekt-/Rechtsträgerbezug und gesetzlichen Einsichtsumfang nach Abschnitt 7.9 und 14. Bereitstellung, Benachrichtigung, Versand, Abruf und rechtlich bewerteter Zugang werden unterschieden; Lesebestätigungen sind Indizien und nicht automatisch ein abschließender Zustellnachweis.
- Aufbewahrung nach freigegebenem Profil je Unterlagenklasse, Rechtsträger, Rechtsgrund, Zeitraum und Löschungssperre gemäß Abschnitt 7.11. Keine pauschale Zehnjahresfrist für alle Buchhaltungsbelege. Originale, E-Rechnungsdaten, Anhänge und relevante Verarbeitungsstände nachvollziehbar erhalten; Löschung nur über geprüfte Profile mit Protokoll und Sperrkontrolle.
- Volltextsuche über `pg_trgm` und `tsvector`; semantische Suche über Embeddings für Kontext-Chat und Portal-Chat.

### 11.4 Allgemeiner Upload und Posteingang

Es gibt einen zentralen Upload (Ablagezone in der Kopfleiste, per E-Mail-Weiterleitung an eine Mandantenadresse, per Scan-Ordner in Paperless, per Drive-Eingangsordner). Jedes eingehende Dokument durchläuft dieselbe Pipeline: Text gewinnen (vorhandene Textebene, sonst OCR), Klassifikation (Dokumenttyp: Rechnung, Vertrag, Protokoll, Schreiben, Abrechnung, Versicherung, Teilungserklärung, Foto, sonstiges), Zuordnung (Objekt über Objektnummer, Adresse oder Einheit; Kontakt über Name, IBAN, Kundennummer; Vertrag über Einheit und Zeitraum), Ablage nach dem Ordnerschema des Mandanten (Objektordner und Unterordner `01` bis `06` in Drive, Tags und Korrespondent in Paperless), Verknüpfung in `document_link`, Auslösen des Folgeprozesses (Rechnung an Belegeingang und Freigabe, Schadensfoto an Ticket, Vertrag an Vertragsakte, Protokoll an Versammlung). Sichere Zuordnungen (Konfidenz über Schwelle, eindeutige Objektnummer) werden direkt abgelegt und dem Nutzer als „automatisch abgelegt“ gemeldet; unsichere landen in einer Prüfliste mit Vorschlag. Der Nutzer kann im Upload-Dialog Objekt und Kategorie vorgeben, dann entfällt die Zuordnung. Massenupload (ZIP, Ordner) wird als `import_run` verarbeitet. Rücknahme nur unter den Grenzen aus Abschnitt 10.1; gebuchte, für Prüfungen gebundene oder aufbewahrungspflichtige Unterlagen werden nicht durch pauschales „Rückgängig“ gelöscht. Automatische Ablage ist keine Freigabe von Zahlung, Buchung, steuerlicher Behandlung oder Einsichtsrechten.

---

## 12. API-Design und Webhooks

- Basis `https://api.<domain>/api/v1`, OpenAPI 3.1 automatisch aus FastAPI, Dokumentation unter `/api/v1/docs` (deutsch beschriftete Fachbegriffe, englische Feldnamen).
- Ressourcen im Plural, verschachtelt höchstens eine Ebene (`/properties/{id}/units`), sonst Filter (`/contracts?property_id=`).
- Standardparameter: `page`, `page_size` (max 200), `sort`, `filter[feld]=wert`, `as_of=YYYY-MM-DD` für zeitlich gültige Daten, `include=` für eingebettete Relationen, `fields=` für sparsame Antworten.
- Idempotenz: `Idempotency-Key`-Header für alle schreibenden Endpunkte; Wiederholungen liefern dieselbe Antwort.
- Optimistische Sperre: `version` in Ressourcen, `If-Match`/`ETag`.
- Fehler nach RFC 9457 mit Feldfehlern.
- Auth: Bearer-Token (Benutzer) oder API-Key (`X-API-Key`), Scopes wie `contacts:read`, `accounting:write`, `portal:tenant`.
- Rate-Limits je Token, Header `X-RateLimit-*`.
- Massenendpunkte: `/bulk` mit Teilerfolgsbericht.
- Dateien: Upload über signierte MinIO-URLs (Presigned), Download ebenso.
- Webhooks: Abonnement je Mandant auf Ereignistypen (`domain_event.type`), Signatur `X-MHVP-Signature` (HMAC-SHA256 über Body und Zeitstempel), Zustellung mit Wiederholung (1 min, 5 min, 30 min, 2 h, 6 h, 24 h), Protokoll und manuelle Neuzustellung in der Oberfläche.
- SDK: TypeScript-Client wird generiert (`packages/api-client`); Python-Client optional generiert für Bestandstools.
- Änderungsregeln: Additive Änderungen ohne Versionswechsel, Entfernungen nur mit `v2`, Deprecation-Header mindestens 6 Monate.

Ereignistypen (Auswahl, alle im Format `<entity>.<action>`): `contact.created|updated|merged`, `property.created|activated`, `unit.updated`, `contract.created|changed|terminated`, `contract_payment.changed`, `bank_transaction.imported|booked|ignored`, `journal_entry.posted|reversed`, `invoice.received|approved|paid`, `dunning_case.created|sent`, `ticket.created|status_changed|commented`, `work_order.created|quoted|approved|completed`, `document.created|shared`, `meeting.invited|closed`, `statement.confirmed`, `ai_proposal.decided`, `portal_account.invited|activated`.

---

## 13. Integrationen

### 13.1 Migration aus Immoware24

Immoware24 bietet keine API und blockiert Browser-Automation; die Migration läuft über Exporte, die ein Nutzer im Browser erzeugt, plus Dokumentenexport. Baue in Phase 1 einen Import-Assistenten (`/imports/immoware24`) mit Staging-Tabellen, Mapping, Validierungsbericht und Testlauf.

| Quelle in Immoware24 | Export | Ziel |
| --- | --- | --- |
| Reports: Objektliste, Belegungsliste, Mietverträge, Eigentümerverträge, Kautionen, Umlageschlüssel, Energieausweise, Adressbuch, Eigentümer, Mieter, Dienstleister, Portalnutzer, Zähler | Excel je Report (global oder je Objekt) | `property`, `building`, `unit`, `contract`, `party`, `contact*`, `deposit`, `allocation_key`, `unit_allocation_value`, `meter`, `portal_account` (Status) |
| Buchungen: Journal, Konten, offene Posten | Export je Objekt und Jahr (Excel/CSV) | `chart_of_accounts` je Objekt, Anfangsbestände zum Migrationsstichtag, historische Journale als `migrated_journal` (nur lesend, Trainingsbasis für KI-Kontierung, nicht in den aktiven Buchungskreis) |
| Bankumsätze | Export aus Banking oder Kontoauszüge der Banken (CAMT/CSV) | `bank_transaction` historisch mit Zuordnung aus Journal (Trainingsbasis) |
| Verträge: monatliche Zahlungen, Intervalle, SEPA-Übersicht | Report „Liste vereinbarter Zahlungen“, SEPA-Übersicht je Objekt | `contract_payment`, `payment_schedule`, `sepa_mandate` |
| Vorlagen, Platzhalter | Kopie der Texte (Urheberrecht beachten, eigene Formulierungen) | `template` neu erstellt |
| DMS | Download je Kategorie oder über Portal-Freigaben; Paperless bereits vorhanden | `document` mit Verknüpfung über Objektnummer und Vertragsbezug |
| Tickets | Export je Filter (PDF/Excel) | `ticket` historisch (nur lesend) |

Regeln: Migrationsstichtag je Objekt, belegte Anfangsbestände, Parallelbetrieb mit täglichem Abgleichbericht (Kontensalden, Debitoren-/Kreditoren-OP, Rücklagen, Bankstände, Zahlungen), dokumentierter Rückfallplan. Die vorhandenen Anhang-A-Bezeichnungen sind Referenzbegriffe, keine vollständige verifizierte Export-Schemaspezifikation. Unbekannte Spalten anhand echter Exportdateien prüfen, manuell zuordnen und das Mapping versionieren.

**Verbindliche Ergänzung zur Finanzmigration:**

- Pro Objekt/Rechtsträger, Datum und Vorgangstyp ist genau ein führendes System für Sollstellungen, Mahnungen, Lastschriften und Zahlungsaufträge festzulegen. Ein lesender Vergleichsbetrieb darf keine doppelte externe Wirkung auslösen. Schreibadapter des Immoware Hub sind entsprechend gesperrt oder kontrolliert freizugeben.
- Anfangsbestände allein genügen nicht für eine vollständige Jahresabrechnung nach unterjähriger Übernahme. Erforderliche Jahresbewegungen, Schlüsselstände, Beschlüsse, Belege, Soll-/Ist-Vorschüsse und Rücklagenentwicklung müssen für die Abrechnung beweisbar auswertbar bleiben. Ob aus aktiven Daten oder einer dokumentierten historischen Überleitung, entscheidet Claude. Historie ist nicht nur KI-Trainingsmaterial. Eröffnungsbestand plus importierte Bewegung dürfen keinen Sachverhalt doppelt zählen.
- Übernehmen und abstimmen: rechtliche Parteien/Schuldner, Eigentums-/Vertragswechsel, offene Posten mit Ursprungsfälligkeit und Teilzahlungen, vorhandene Guthaben, gesonderte Kautionen, Rücklagen-/Darlehensstände, Sonderumlagen, gebundene Zahlungen, relevante Steuerdaten, wirksame Zahlungs-/Mandatsgrundlagen, Abrechnungs- und Beschlussversionen sowie Originalbelege.
- Bereits versandte/beschlossene alte Abrechnungen bleiben historische Dokumente. Geänderte heutige Stammdaten dürfen deren Inhalt nicht rekonstruierend überschreiben. Fehlende Belege, nicht abgestimmte Bankstände und nicht erklärbare Differenzen sind Freigabehindernisse für betroffene Rechenwerke.
- Abnahme durch Summenabgleich UND unabhängige fachliche Soll-Ergebnisse. Differenzen zum Altsystem dürfen begründet sein; Null-Differenz beweist nicht allein Richtigkeit. Prüfumfang, verantwortliche Personen und nicht migrierbare Daten dokumentieren. Kein Löschen/Stilllegen des Altzugangs vor gesichertem Archiv- und Auskunftskonzept.

### 13.2 Objektakte (uebernahme.muellerhv.de)

Bestehende Anwendung der HVM: Python, Docker Compose, MariaDB, Redis, Celery-Worker (OCR, IO, NLP, Control, Beat), Verarbeitungsjobs je Objekt (discover, hash, ocr_chunk, merge_pages, render_previews, classify, file_to_drive), KI-Klassifikation (lokales Modell plus externe KI), Ablage in Google Drive je Objekt mit der Sechs-Ordner-Struktur, Review Center, Requirement Engine, automatisch erzeugte Eigentümer- und Mieterlisten (Excel und PDF). Verarbeitet 1 bis 4 Objekte je Tag mit 1.000 bis 10.000 Seiten.

Integration:
- Die Objektakte bleibt eigenständiger Dienst für Massen-OCR und Klassifikation von Übernahmeakten. Die Plattform ruft sie über eine interne REST-Schnittstelle (`POST /jobs` mit Objektnummer und Dateiliste, Webhook bei Fertigstellung) auf und übernimmt die klassifizierten Dokumente samt Metadaten in `document`/`document_link`.
- Der Onboarding-Chat (Abschnitt 10.2) nutzt die Klassifikationsergebnisse und die generierten Eigentümer- und Mieterlisten als Eingabe für `extract_property`.
- Single Sign-on über den OIDC-Provider der Plattform; gemeinsame Objektnummern; Drive-Ordnerstruktur ist die gemeinsame Konvention.
- Der Agent dokumentiert nach Sichtung des Objektakte-Repos die konkreten Endpunkte in `docs/integrations/objektakte.md`. Bis dahin gilt der hier beschriebene Vertrag als Zielbild.

### 13.3 smart-einzug (lexoffice-Einzug)

Bestehendes Projekt auf einem separaten VPS (nicht Teil des Serverumzugs). Zweck laut Bezeichnung: Zahlungseinzug in Verbindung mit lexoffice, das die HVM für Eigentümer- und Kundendaten nutzt. Integration: Kontaktänderungen von Eigentümern werden per Webhook (`contact.updated`) an smart-einzug bzw. lexoffice gespiegelt; Verwalterhonorar-Rechnungen können als Ausgangsrechnung an lexoffice übergeben werden. Details nach Sichtung des Repos in `docs/integrations/smart-einzug.md`.

### 13.4 Mailprogramm, Übergabeprotokoll, Flow, Immoware Hub

Diese Bestandsprogramme liegen als Claude-Code-Projekte des Betreibers vor: „Müller FLOW: Fable 5.1 und Ultracode Strategie“ (Flow), „Immoware Hub Integrationsplattform“ (Integrationsschicht zu Immoware24 mit eigener REST-API, Lesespiegel aus Exporten und Schreibadapter, Stand 09/2026) und „Mail optimierung“ (Mailprogramm). Das Übergabeprotokoll ist ein weiteres Bestandsprojekt. Dem Autor dieses Prompts liegen die Quelltexte noch nicht vor. Der Betreiber erzeugt je Projekt mit dem Prompt aus Anhang B ein Integrationsdossier (`docs/integrations/<tool>.md`) und stellt es dem Plattform-Repo bereit. Bis dahin gilt:

- **Mailprogramm („Mail optimierung“)**: Zielbild ist, dass die Plattform Postfächer selbst anbindet (IMAP/SMTP und Gmail API) und E-Mails Kontakten, Objekten und Tickets zuordnet. Das bestehende Programm wird entweder als Quelle (klassifizierte Mails per Webhook) oder als Client der Plattform-API angebunden; Klassifikationslogik und Textbausteine werden übernommen, wenn sie besser sind als der Neubau.
- **Übergabeprotokoll**: Wohnungsübergabe (Einzug, Auszug) mit Zählerständen, Schlüsseln, Mängeln, Fotos, Unterschriften. Zielbild: Übernahme als Modul der Plattform oder Anbindung per API (Protokoll erzeugt `meter_reading`, `ticket` für Mängel, `document`, Vertragsereignis Einzug/Auszug).
- **Flow („Müller FLOW“)**: Prozess- und Automatisierungssoftware. Zielbild: Anbindung an die Regel-Engine (Abschnitt 15) und das Ticketsystem über Webhooks; Übernahme bewährter Abläufe als `automation_rule`-Vorlagen; Ablösung, sobald die Regel-Engine den Zweck erfüllt.
- **Immoware Hub**: Während des Parallelbetriebs liefert der Hub Lesespiegel aus Immoware24 (Exporte) an den Import-Assistenten (Abschnitt 13.1) und kann Schreibvorgänge nach Immoware24 auslösen, solange dort noch gebucht wird. Nach der Ablösung wird der Hub stillgelegt; seine Export-Parser werden in `mhvp.imports` übernommen.

Der Agent legt für jedes Bestandstool nach Erhalt des Dossiers eine Datei `docs/integrations/<tool>.md` an mit: Zweck, Stack, Datenmodell, Schnittstellen, Entscheidung (anbinden, übernehmen, ablösen), Migrationsschritte.

### 13.5 Weitere Schnittstellen

E-Post oder gleichwertiger Briefdienst (Postversand mit Statusrückmeldung), Messdienst-Datenaustausch (ARGE HeiWaKo, Import D-Format, Export Stammdaten), E-Rechnung (XRechnung/ZUGFeRD lesen und erzeugen), DATEV (Buchungsstapel), Kalender (ICS, optional Google Calendar API), Telefonie (Rufnummernerkennung per Webhook aus TAPI/SIP-Anbieter, Anrufnotiz zu Kontakt), Immobilienportale (OpenImmo-Export für Leerstände, Phase 4), lexoffice (Kontakte, Ausgangsrechnungen).

---

## 14. Portale

Ein Portal (`web-portal`) mit rollenabhängiger Navigation, mobile-first, PWA, mehrsprachig (Deutsch, Englisch, weitere über Übersetzungsdateien), White-Label je Mandant, Login per E-Mail und Passwort oder Magic-Link, Einladung per E-Mail und QR-Code, Zweifaktor optional. Struktur wie bei Portal24 dreistufig (Verwalter, Objekt, eigene Einheit bzw. eigene Aufträge), aber mit Self-Service.

| Rolle | Phase 3 | Phase 4 |
| --- | --- | --- |
| Mieter | Dokumente mit Lesebestätigung, Schadensmeldung mit Foto und Standort als Ticket, Ticketverlauf mit Kommentaren, Stammdaten und Bankverbindung ändern (mit Freigabe durch Verwaltung), SEPA-Mandat digital, Zählerstand mit Foto melden, Kontoauszug des Mietkontos mit offenen Posten, Schwarzes Brett, Chat mit Verwaltung (KI-Vorqualifizierung), Formulare | Verbrauchsinformation monatlich, Nebenkostenabrechnung mit Erklärtexten, Terminbestätigung mit Handwerkern |
| Eigentümer | rollenspezifischer Self-Service für eigene Rechtsverhältnisse, Hausgeldkonto, Objektinformationen, Ansprechpartner, Beschluss-Sammlung (lesend), Dokumente im gesetzlichen/vertraglichen Einsichtsumfang; keine automatische Übernahme aller Mieterrechte | Wirtschaftsplan und Hausgeldabrechnung mit Erklärungen, Versammlung online (Einladung, Vollmacht, Teilnahme per Video, Wortmeldung, Abstimmung, Protokoll), Umlaufbeschluss digital, komfortable Belegeinsicht, Eigentümerreporting für Kapitalanleger |
| Beirat | Prüfungsraum mit Belegprüfung, Rückfragen und Prüfvermerk; Rechnungsfreigabe nur bei nachgewiesener gesonderter Zuständigkeit/Befugnis | Jahresprüfung mit ausgewiesenem Umfang, Feststellungen und versionierter Stellungnahme; keine automatische Entlastung oder Zahlungsfreigabe |
| Dienstleister | Aufträge annehmen oder ablehnen, Angebot hochladen, Termin mit Bewohner abstimmen (Terminvorschläge, Bestätigung), Ausführung mit Fotos dokumentieren, Rechnung einreichen (PDF oder E-Rechnung), Status für Verwaltung und Bewohner sichtbar | Bewertungen, Rahmenverträge, Verfügbarkeitskalender |

Fachliche Zugriffsvorgaben: Rollen, Mandant, Rechtsträger, Objektbezug, zeitliche Berechtigung, Vertretungsnachweis und sachlicher Einsichtsumfang gemeinsam prüfen. Mieter sehen ihre einschlägigen Vorgänge und Abrechnungsunterlagen; Dienstleister ihre berechtigten Auftragsinformationen. Eigentümer dürfen die ihnen zustehenden Verwaltungsunterlagen ihrer GdWE auch dann einsehen, wenn diese nicht nur die eigene Einheit betreffen (§ 18 Abs. 4 WEG). Beirat ist kein Monopol für Belegeinsicht. Private SEV-/Mieterakten und andere Gemeinschaften sind dadurch nicht allgemein freigegeben. Die technische Umsetzung der vorhandenen Rechteverwaltung bleibt bei Claude.

Freigabesteuerung je Dokumentkategorie, Berechtigungszweck und Rolle; Tests je Zugriffspfad einschließlich Direkt-Download, API, Export und RAG. Portalseitige Änderung von Bankverbindung/Stammdaten und Zählerständen erfolgt als prüfbarer Vorschlag, nicht als selbst freigegebener produktiver Geldweg. Ticketanlage und Kommentare bleiben im berechtigten Umfang direkt möglich. Chat liest ausschließlich den für die Person freigegebenen Inhalt.

**Phasengrenze:** Die Komfortoberfläche für Belegeinsicht bleibt wie geplant später. Bei früherer produktiver Abrechnung/Verwaltung muss die gesetzlich geschuldete Einsicht bereits über einen funktionierenden alternativen Prozess mit Belegpaket/Termin/Anfragebearbeitung gewährleistet sein. Ebenso darf das späte Portalmodul eine bereits fällige Verbrauchsinformation nicht aussetzen. Ein nicht erreichbares Portal ist kein Ersatz für Fristenkontrolle und erforderliche Zustellung.

---

## 15. Automatisierung und Regel-Engine

### 15.1 Standardzeitpläne je Mandant (konfigurierbar)

| Zeitpunkt | Job | Ergebnis |
| --- | --- | --- |
| täglich 06:00 | `bank.sync_all` | Kontoauszüge abrufen, Dubletten, KI-Kontierung, automatische Buchungen, Vorschlagsliste, Sync-Protokoll |
| täglich 06:30 | `documents.process_inbox` | Neue Dokumente aus Paperless, Drive, E-Mail-Postfächern klassifizieren, extrahieren, verknüpfen, Freigabeworkflows starten |
| täglich 07:00 | `tasks.digest` | Tagesübersicht je Benutzer: fällige Tickets, Freigaben, Fristen, KI-Vorschläge |
| monatlich 1., 05:00 | `accounting.receivable_run` | Sollstellungen für alle Objekte, Vorschau oder automatische Buchung |
| monatlich 5., 06:00 | `accounting.dunning_run` | Mahnläufe Mieter und Eigentümer, Entwürfe zur Freigabe |
| wöchentlich Mo 08:00 | `payments.payment_run` | Zahllauf aus freigegebenen Rechnungen und fälligen Lastschriften, Pre-Notifications |
| täglich 20:00 | `compliance.deadlines` | Fristen: Vertragsenden, Eichfristen, Kündigungsfristen Dienstleister, Zustimmungsablauf Bank, Beschlussfristen virtuelle Versammlung |
| monatlich 3. | `heating.consumption_info` | Verbrauchsinformationen aus Messdienstdaten ins Portal |
| täglich 02:00 | `ops.backup_verify` | Backup prüfen, monatlich Wiederherstellungstest |

**Freigabevorbehalt aller Zeitpläne:** Die Zeitpläne führen nur fachlich freigegebene Regeln aus. Sie übergehen weder Rechtsgrund-/Beschlussprüfung noch Vier-Augen-Freigabe, Dublettenschutz, Fristenprüfung oder Sperren. Ein planmäßig gestarteter Job darf bei fehlender Grundlage einen Entwurf/Prüffall erzeugen, aber keine unbegründete Forderung oder Zahlung. Wiederholung, Zeitzonen-/Sommerzeitwechsel und parallele manuelle Läufe sind auf doppelte Wirkung zu testen.

### 15.2 Regel-Engine

`automation_rule` mit Auslöser (Ereignistyp oder Zeitplan), Bedingungen (JSON-Logik über Ereignisfelder und nachgeladene Fachdaten) und Aktionen (Ticket anlegen mit Vorlage, E-Mail/Brief aus Vorlage, Aufgabe an Benutzer, Feld setzen, Webhook, KI-Aufgabe starten, Benachrichtigung). Oberfläche als Formular („Wenn Ticket mit Kategorie Wasserschaden erstellt, dann Priorität hoch, an Team Objektbetreuung, Dienstleister Sanitär informieren“). Jede Ausführung protokolliert; Regeln können im Testmodus laufen (nur Protokoll).

---

## 16. Nicht-funktionale Anforderungen

| Bereich | Anforderung |
| --- | --- |
| Leistung | Listen mit 10.000 Zeilen paginiert unter 300 ms (P95), Detailseiten unter 500 ms, Sollstellungslauf für 1.000 Verträge unter 2 Minuten, Abrechnungslauf für ein Objekt mit 100 Einheiten unter 1 Minute, Bankabruf für 100 Konten unter 10 Minuten |
| Skalierung | Zielgröße Phase 4: 50 Mandanten, 50.000 Einheiten, 10 Millionen Buchungszeilen; Worker horizontal skalierbar; Datenbank mit Partitionierung von `journal_line` und `bank_transaction` nach Jahr vorbereitet |
| Verfügbarkeit | 99,5 Prozent im Monat, Wartungsfenster angekündigt, Health-Checks, automatischer Neustart, Statusseite |
| Sicherheit | OWASP ASVS Level 2 als Ziel, Security-Header, CSRF-Schutz, Rate-Limits, Passwortregeln, 2FA, Sitzungsverwaltung, Abhängigkeits-Scans, Penetrationstest vor Marktstart |
| Datenschutz | Auskunftsexport je Kontakt (alle Daten, Dokumente, Protokolle) als Job, Löschprofile mit Fristen je Datenart, Einwilligungsprotokoll, Auftragsverarbeiter-Register, Verarbeitungsverzeichnis als generiertes Dokument, EU-Hosting, Pseudonymisierung in Logs |
| Buchführungs-/Aufbewahrungsnachweis | In einschlägigem Anwendungsbereich GoBD/AO/HGB: nachvollziehbares Buchungsregister, Unveränderbarkeit gebuchter Inhalte, kontrollierte Festschreibung, Belegketten, tatsächliche Verfahrensdokumentation, maschinelle Auswertbarkeit; keine pauschale Software-Zertifizierungsbehauptung |
| Barrierefreiheit | WCAG 2.1 AA für Portale (BFSG-Prüfung offen), Tastaturbedienung, Kontraste, Screenreader-Labels |
| Beobachtbarkeit | Strukturierte Logs mit Korrelations-ID, Metriken je Job, Tracing, Alarme bei Fehlern in Bankabruf, Zahllauf, Mahnlauf, Backups |
| Backup | Technisches Ausgangsziel aus Abschnitt 3.5 bleibt Prüfbasis: tägliche Sicherung, stündlich WAL, Wiederherstellungstest, RTO unter 4 Stunden. Dauer/Speicherumfang langfristiger Sicherungen mit rechtmäßigem Aufbewahrungs-/Löschkonzept abstimmen; Backup ersetzt kein Archiv. Claude prüft Widerspruch E05 vor Produktivbetrieb. |
| Mehrsprachigkeit | Deutsch Standard, Englisch vollständig, Portal weitere Sprachen über Übersetzungsdateien |
| Dokumentation | Benutzerhandbuch als generierte Seiten aus Markdown im Repo (`docs/handbuch/`), Admin-Runbooks, API-Referenz aus OpenAPI |

---

## 17. Repository-Struktur und Entwicklungsablauf

```
mhvp/
  CLAUDE.md                 Arbeitsanweisungen für Claude Code (Verweis auf diesen Prompt, Befehle, Konventionen)
  AGENTS.md                 dasselbe für Codex
  README.md
  docs/
    MASTER-PROMPT.md        dieses Dokument
    OPEN_QUESTIONS.md       Fragen an den Betreiber mit Vorschlag und Status
    ASSUMPTIONS.md          getroffene Annahmen mit Datum
    adr/                    Architekturentscheidungen
    integrations/           je Bestandstool und Fremdsystem
    runbooks/               Betrieb: Deploy, Backup, EBICS-Setup, Incident
    handbuch/               Benutzerdokumentation (Deutsch)
  apps/
    api/                    FastAPI, Alembic, Celery (Python-Paket mhvp)
      src/mhvp/
        core/               Auth, Tenancy, RLS, Audit, Events, Webhooks, Settings
        contacts/           Kontakte, Parteien, Einwilligungen, Portalkonten
        properties/         Objekte, Gebäude, Einheiten, Umlageschlüssel, Zähler, Dienstleisterverhältnisse
        contracts/          Verträge, Zahlungen, Mandate, Kautionen
        accounting/         Buchungskreis, Konten, Buchungen, offene Posten, Sollstellung, Mahnwesen, Zahlläufe, Exporte
        banking/            Konnektoren, Umsätze, Regeln, Matching
        billing/            Abrechnungen, Wirtschaftsplan, Rücklagen, Sonderumlagen, Heizkosten
        hoa/                Versammlungen, Beschlüsse, Beirat
        tickets/            Tickets, Aufträge, Vorlagen
        documents/          Dokumente, DMS-Adapter, Vorlagen, Generierung
        communication/      Postfächer, Nachrichten, Formulare, Benachrichtigungen, Kalender
        ai/                 Gateway, Prompts, Aufgaben, Beispiele, Evaluation, Chat
        automation/         Regel-Engine, Zeitpläne
        imports/            Immoware24-Import, Onboarding-Läufe
        portal/             Portal-spezifische Endpunkte und Berechtigungsfilter
        platform/           Mandantenverwaltung, Lizenzen, Nutzung
      tests/
      alembic/
    web-crm/                Next.js Verwaltung
    web-portal/             Next.js Portale
  packages/
    api-client/             generierter TypeScript-Client
    ui/                     gemeinsame Komponenten (Design-Tokens, Formulare, Tabellen)
    config/                 gemeinsame ESLint/TS-Konfiguration
  infra/
    compose.yaml, compose.prod.yaml, compose.dev.yaml
    traefik/                dynamische Konfiguration, Middlewares
    postgres/               init, Erweiterungen, RLS-Rollen
    grafana/, prometheus/, loki/
  scripts/                  make-Ziele, Seed, Import-Helfer
  Makefile
```

Befehle (Makefile): `make dev` (Compose dev hochfahren), `make migrate`, `make seed` (Demo-Mandant mit anonymisierten Daten: 3 Objekte, 40 Einheiten, 60 Kontakte, 12 Monate Buchungen, 200 Bankumsätze), `make test`, `make lint`, `make typecheck`, `make openapi` (Schema exportieren, Client generieren), `make ai-eval`, `make deploy ENV=staging|prod`, `make backup-verify`.

Arbeitsablauf je Meilenstein: Issue oder Aufgabe lesen, Plan in `docs/plans/<meilenstein>.md`, Feature-Branch, Umsetzung in kleinen Commits, Tests, OpenAPI-Diff prüfen, README aktualisieren, Pull Request mit Zusammenfassung und offenen Punkten, CI grün, Merge, Deploy auf Staging, Abnahme durch Betreiber anhand der Abnahmekriterien.

---

## 18. Umsetzungsplan

**Reihenfolge und Meilensteinnummern bleiben unverändert.** Die folgenden Abnahmeergänzungen verschieben keine Architektur und ziehen die WEG-Implementierung nicht eigenmächtig vor. G0 ist mit dieser Version abgeschlossen; die WEG-relevanten Modellentscheidungen stehen in Abschnitt 6.9 und gelten ab M2. Rechtliche Pflichten eines bereits genutzten Teilprodukts gelten unabhängig von der späteren Komfortoberfläche.

### 18.0 Freigabestufen zusätzlich zu den Meilensteinen

| Stufe | Voraussetzung | Ohne Freigabe nicht zulässig |
| --- | --- | --- |
| G0 Startauftrag | Mit Version 2.0 erfüllt: Konflikte E01 bis E16 entschieden (Anhang E), Phase-1-Schemaumfang festgelegt (6.9), Zuständigkeiten in Abschnitt 19. Der Betreiber erteilt den Startauftrag für M1. | Ohne Startauftrag kein Repo und keine Migration. |
| G1 Produktive Buchführung | B01–B09 und einschlägige Tests bestanden; unabhängige Sollwerte, Belegketten, Rechtsträgertrennung, dokumentierte Korrektur und geprüfte Migration. | Keine echten Bestände/Sollstellungen als führende Buchhaltung. |
| G2 Zahlungsveranlassung | Bankvertrag, Berechtigungen, Mandats-/Empfängerprüfung, Freigabeversionierung, Wiederholungs-/Rückgabeabläufe und Abstimmung geprüft. | Keine echten Überweisungen/Lastschriften aus der Plattform. |
| G3 Mietabrechnung | Vertrags-/Umlagegrundlagen, Heiz-/CO₂-Regeln, Vorauszahlungen, Fristen, Zugang und Belegeinsicht anhand freigegebener Fälle geprüft. | Keine rechtlich maßgeblichen Mietabrechnungen aus ungeprüfter Funktion. |
| G4 WEG-Abrechnung | W01–W13, unabhängige Zahlenfälle, Eigentümerwechsel, Beschlussgrundlage, Rücklagen, Beiratsprozess und Einsicht geprüft. | Keine rechtlich maßgebliche WEG-Abrechnung oder Ergebnisforderung. |
| G5 Fremdmandanten | Betriebs-/Datenschutz-/Sicherheitsprüfung, Leistungsumfang, Grenzen, Verfahrensnachweise und Support-/Rückfallprozesse freigegeben. | Keine Vermarktung als fertig für ungeprüfte Fallgruppen. |

Eine Stufe gilt nur für den dokumentierten Funktionsumfang. Offene seltene Sonderfälle dürfen ausdrücklich ausgeschlossen und gesperrt bleiben, sofern dadurch der für den konkreten Mandanten notwendige Leistungsumfang nicht als vollständig ausgegeben wird.

### Phase 1: Kern (Ziel: lauffähiger Kern mit echten HVM-Daten, ohne Buchhaltung)

| Meilenstein | Inhalt | Abnahmekriterien |
| --- | --- | --- |
| M1 Fundament | Repo-Skelett, Compose, Traefik, PostgreSQL mit RLS-Rollen, Redis, MinIO, CI, Logging, Health, `CLAUDE.md`, `AGENTS.md`, `OPEN_QUESTIONS.md` | `make dev` startet alles; CI grün; Health-Endpunkte; ADR 0001 (Stack), 0002 (Mandantentrennung) |
| M2 Plattform und Mandanten | `tenant`, `user`, `membership`, Rollen und Rechte, Auth (Passwort, 2FA, Refresh, API-Keys, OIDC-Provider), Plattformadmin, Mandantenkonfiguration, Branding, Audit, Ereignisse, Webhooks | Zwei Mandanten (HVM, Timo Müller) angelegt aus Seeds mit CI-Werten; Benutzerwechsel zwischen Mandanten; RLS-Tests; Webhook-Zustellung getestet |
| M3 Kontakte | Kontakte, Adressen, Kommunikationskanäle, Identifikatoren, Bankverbindungen, Typen, Tags, Notizen, Parteien, Einwilligungen, Dublettensuche, globale Suche | CRUD über API und Oberfläche; Dublettenvorschlag; Volltextsuche; Export je Kontakt (DSGVO-Auskunft) |
| M4 Objekte und Einheiten | Objekte, Gebäude, Einheiten, Umlageschlüssel und Werte, Zähler, Ansprechpartner, Dienstleisterverhältnisse, Bankkonten, Wartung, Kataloge und Muster, benutzerdefinierte Felder | Objekt mit Gebäuden und Einheiten anlegen; Schlüsselwerte mit Zeitraum; Stichtagsabfrage; Objektstatus |
| M5 Verträge | Verträge (Miete, Eigentum, SEV), Zahlungen, Intervalle, Mandate, Kautionen, Versionierung, Debitorenkonto-Reservierung (Konto wird angelegt, Buchungen erst Phase 2) | Vertrag anlegen, ändern (neue Version), beenden; Zahlungshistorie; Belegungsliste; SEPA-Übersicht |
| M6 Dokumente und DMS | `document`, Kategorien, MinIO, Paperless-Adapter, Google-Drive-Adapter, Vorlagen mit Platzhaltern und Briefbogen je Mandant, PDF-Erzeugung, Serienbrief | Dokument hochladen, verknüpfen, in Paperless und Drive spiegeln; Brief aus Vorlage im HVM-CI erzeugen; Volltextsuche |
| M7 KI-Gateway und Onboarding-Chat | Provider-Konfiguration, Prompt-Registry, Aufgaben `extract_contacts`, `extract_property`, `answer_question`, `summarize`, Beispiele, Kosten, Chat-Oberfläche global und am Objekt, `import_run` mit Rückgängig | Kontaktliste (Excel) wird per Chat in Kontakte überführt; Eigentümer- und Mieterliste eines Objekts erzeugt Objekt, Einheiten, Verträge; Rückgängig funktioniert; Evaluationsdatensatz mit mindestens 20 Fällen je Aufgabe |
| M8 Immoware24-Import | Import-Assistent für Reports und Verträge, Mapping-Vorlagen, Validierungsbericht, Testlauf, Journal- und Bankumsatz-Historie als Trainingsbasis | Vollständiger Bestand der HVM (67 Objekte, 869 Einheiten, Kontakte, Verträge) importiert; Abgleichbericht gegen Immoware24-Reports ohne offene Differenzen |
| M9 Oberfläche und Betrieb | Dashboard, globale Suche, Listenfilter, Massenaktionen, Dunkelmodus, Benachrichtigungen, Kalender, Staging und Produktion auf dem IONOS-Server, Backups, Monitoring, Handbuch Phase 1 | HVM arbeitet parallel zu Immoware24 mit Stammdaten in der Plattform; Backup-Wiederherstellung getestet |

### Phase 2: Buchhaltung, Banking, Mahnwesen, Abrechnung Miete

| Meilenstein | Inhalt | Abnahmekriterien |
| --- | --- | --- |
| M10 Buchungskreis | Kontenrahmen-Vorlage, Konten je Objekt, Buchungssätze, Storno, Festschreibung, Nummern, OP, Journal, Kontenblätter, Saldenliste, geprüfte Anfangsbestände | B01–B09 und relevante D-Tests bestanden; Rechtsträger/WEG-SEV-Trennung nachgewiesen; Historie, Konkurrenzzugriffe, Abbruch und Wiederholung geprüft; G1 dokumentiert |
| M11 Bank-Adapter | Konnektoren EBICS, Aggregator, FinTS-Rückfall, Datei-Import; `bank_connection`, `bank_transaction`, Identität/Dublettenprüfung, Sync-Job, Zustimmungsverwaltung | Vereinbarte HVM-Konten angebunden; Wiederimport erzeugt keine Zusatzwirkung, zwei echte identische Zahlungen bleiben erhalten; Bankabstimmung und Sync-Protokoll |
| M12 Matching und KI-Kontierung | Bankregeln, zulässige Tilgung, `propose_posting`, Konfidenzanzeige, Vorschlagsliste, Massenbestätigung, kontrolliertes Lernen und Regelvorschläge | Unabhängiger Testbestand mit falschen/mehrdeutigen Treffern; Fehlerquote und Abdeckungsgrad separat; Automatik nur nach 7.4. Über 80 Prozent Automatisierung bleibt Optimierungsziel, keine Pflicht zulasten der Richtigkeit und kein Sicherheitsbeweis |
| M13 Sollstellung und Verwalterhonorar | Sollstellungslauf mit Vorschau, zeitanteilig, Sonderumlage, Verwalterhonorar-Einstellungen und Rechnungen (E-Rechnung), SE-Verwaltergebühr | Monatslauf für alle Objekte unter 2 Minuten; Rechnungen als XRechnung valide (Validator) |
| M14 Belegeingang und Kreditoren | Rechnungen aus Paperless, E-Mail, Upload; `extract_invoice`; sachliche, rechnerische, steuerliche Prüfung; zuständige Freigaben; Kreditoren; Rechnungspläne; Dubletten | PÜ01–PÜ05; Original-/Zahlungs-/Auftragsbezug, Änderungsfolgen, Skonto, Abschlag/Schlussrechnung und geänderte IBAN getestet; keine Zahlung allein aus Beiratsstatus |
| M15 Zahlläufe | Überweisungen, Lastschriften mit geprüften Mandaten/Vorabinformation, Vier-Augen-Freigabe, vereinbarte Bankformate, Einreichung und Statusabgleich | Test-/Sandboxabläufe: Freigabeänderung, Doppelaufruf, Ablehnung, Teil-/Nichtausführung, Rücklastschrift und Bankbestätigung; Dateigültigkeit allein reicht nicht; G2 |
| M16 Mahnwesen | Einstellungen, Mahnlauf am 5., Fälle, Schreiben im CI, Zustellung, Gebühren- und Zinsbuchung, Sammelmahnlauf | Mahnlauf für alle Objekte mit Freigabe; Mahnsperren beachtet; Zustellnachweise |
| M17 Abrechnung Miete | Abrechnungszeiträume, Betriebskosten mit Heizkostenimport, Leerstand, Nutzerwechsel, CO₂, geprüfte USt-/§-35a-Behandlung, Eigentümerabrechnung, Informationsblatt, KI-Plausibilität | Unabhängig bestätigte Sollwerte für repräsentative Fälle aus Anhang D, Fristen und Belegeinsicht; Vergleich mit Altsoftware zusätzlich, Differenzen erklärt; G3 |
| M18 Auswertungen und Exporte | Liquiditätsvorschau, offene Posten stichtagsbezogen, Zahlungen je Debitor, Mieterträge, DATEV, GoBD-Export, Steuerberaterzugang | Steuerberater kann DATEV-Stapel importieren; GoBD-Export vollständig |

### Phase 3: Tickets, Aufträge, Portale, Kommunikation

| Meilenstein | Inhalt | Abnahmekriterien |
| --- | --- | --- |
| M19 Tickets und Aufträge | Ticketsystem mit Vorlagen, Teams, SLA, Routing, Aufträge mit Angebot, Freigabe, Termin, Ausführung, Rechnung, Bewertung | Ticket zu Auftrag zu Rechnung durchgängig |
| M20 Postfach | IMAP/SMTP und Gmail-API, `classify_email`, `draft_reply`, Zuordnung, Terminerkennung, Vorgangsliste | info@-Postfach der HVM läuft über die Plattform |
| M21 Portal Mieter und Eigentümer | Login, Einladung, Dokumente, Tickets, Stammdaten-Self-Service mit Freigabe, SEPA-Mandat digital, Zählerstand, Kontoauszug, Schwarzes Brett, Chat, Formulare | Berechtigungen einschließlich gesetzlicher Einsicht, Vertreter und Rollenwechsel getestet; Ablösung nur für tatsächlich abgenommene Funktionen, WEG-Phase-4-Lücken ausdrücklich kenntlich |
| M22 Portal Dienstleister | Aufträge, Angebote, Termine, Ausführungsdokumentation, Rechnungseinreichung | Drei Dienstleister der HVM arbeiten produktiv im Portal |
| M23 Kommunikation | Brief- und Postversand, Zustellnachweise, Serienbriefe je Zustellweg, Benachrichtigungen, Kalender-Sync | Vollständige Kommunikationshistorie je Kontakt |

### Phase 4: WEG

| Meilenstein | Inhalt | Abnahmekriterien |
| --- | --- | --- |
| M24 Wirtschaftsplan und Hausgeldabrechnung | Pläne, Abrechnungen, Vermögensbericht, Rücklagen, Sonderumlagen, Untergemeinschaften und nachvollziehbare Ergebnis-/Beschlusszuordnung | W01–W13 und unabhängige WEG-Fälle aus Anhang D, insbesondere Soll/Ist, Eigentümerwechsel, Geldflüsse und Rücklagen; Altvergleich ergänzend; G4 |
| M25 Versammlung | Vorbereitung, Einladung, Vollmachten, Präsenz/hybrid/virtuell, Umlaufbeschluss, Protokoll, Beschluss-Sammlung und Beiratsprüfung | Rechtsgrundlage/Mehrheitsbasis, Rechteausübung und Ausfälle getestet; PÜ06–PÜ13 mit Prüfbericht und unveränderlicher Bezugsversion; keine bloße Video-Demo als Fachabnahme |
| M26 Mieterhöhung und Vermietung | Mieterhöhungsprüfung mit Mietspiegel, Prozess, Leerstandsmanagement, Exposé, OpenImmo-Export, Interessenten | Mieterhöhungsprozess durchgängig |
| M27 Marktreife | Lizenzmodell, Nutzungszähler, Onboarding, Preisliste, Dokumentation, Sicherheits-/Datenschutz-/Fachprüfung, tatsächliche Verfahrensdokumentation | G5 erfüllt; erster Fremdmandant nur im ausdrücklich geprüften Leistungsumfang produktiv |

---

## 19. Offene Punkte und Startvoraussetzungen

### 19.1 Voraussetzungen vor Projektstart (Betreiber)

Diese Punkte liegen beim Betreiber bzw. den benannten Fachverantwortlichen und sind vor dem betroffenen Freigabeschritt zu erledigen. Claude prüft zu Beginn einer Sitzung den offenen Status. Unkritische Annahmen dürfen Entwürfe ermöglichen; kritische rechtliche, finanzielle oder Datenschutzfragen sperren die betroffene produktive Aktion gemäß Abschnitt 0. Eine Konfiguration gilt nicht als Klärung.

| Nr | Punkt | Wofür nötig | Status |
| --- | --- | --- | --- |
| V1 | Dossiers der sechs Bestandsprojekte (Müller FLOW, Immoware Hub Integrationsplattform, Mail optimierung, Übergabeprotokoll, Objektakte, smart-einzug) nach Anhang B, abgelegt unter `docs/integrations/<tool>.md` | Abschnitt 13, Entscheidung anbinden, übernehmen, ablösen; Version 1.2 dieses Prompts | offen |
| V2 | Bankliste: alle Konten der Mandanten HVM und Timo Müller mit Bank, BIC, Kontotyp (Miet-, WEG-, Rücklagen-, Kautions-, Geschäftskonto), geplantem Konnektor; Anfrage bei den Hauptbanken zu EBICS-Verträgen (Vorlauf mehrere Wochen) | Phase 2, M11 | offen |
| V3 | Entscheidung Aggregator (finAPI, GoCardless Bank Account Data oder Alternative) nach Angebot und Auftragsverarbeitungsvertrag | M11 | offen |
| V4 | Produktname und Marke (ersetzt Arbeitstitel MH Verwaltungsplattform), Domains für Fremdmandanten | Branding, Repo-Name, Login-Seiten | offen |
| V5 | Entwicklungsmodell: eigene Entwickler, externe Agentur oder Hybrid; daraus Aufwands- und Kostenschätzung je Phase | Planung, Budget | offen |
| V6 | Tatsächlichen Immoware24-Vertrag einschließlich Kündigung, Laufzeit, Export und Nutzungsgrenzen prüfen; öffentlich behauptete Standardfristen sind kein Beleg für den konkreten Vertrag. Ablösetermin aus bestätigten Unterlagen ableiten | Migrationsplan, Parallelbetrieb | offen |
| V7 | Mahnstufen, Gebühren, Verzugszinsregeln je Mandant, rechtlich geprüft | M16 | offen |
| V8 | Kontenrahmen: Übernahme der Immoware24-Konten der HVM als Startvorlage, Bezeichnungen eigenständig formuliert | M10 | offen |
| V9 | Migrationsstichtag je Objekt und Dauer des Parallelbetriebs | M8, Phase 2 | offen |
| V10 | Auftragsverarbeitungsverträge mit Anthropic, OpenAI, Aggregator, Briefdienst; Bestätigung, dass keine Trainingsnutzung erfolgt | M7, M11, M23 | offen |
| V11 | Google-Workspace-Konto und internes Cloud-Projekt je Mandant für die Drive-Anbindung; Paperless-Token je Mandant | M6 | offen (HVM: ablage@muellerhv.de vorhanden) |
| V12 | Steuerberater: E-Rechnungs-Ausstellungspflicht je Mandant (Umsatzgrenze, Startzeitpunkt), DATEV-Parameter (Berater-, Mandantennummer, Kontenlänge) | M13, M18 | offen |
| V13 | Rechtsanwalt: BFSG-Anwendbarkeit auf das Portal, WEG-Recht für virtuelle Versammlung und Umlaufbeschluss im Portal, GoBD-Verfahrensdokumentation | M21, M25 | offen |
| V14 | Freigabe der CI-Werte je Mandant aus den tatsächlich verfügbaren Quellen hvm-ci, mhag-ci, tm-privat-ci; fehlende Quellen nicht durch erfundene Werte ersetzen | M2 Seeds | offen |
| V15 | Je Pilot-WEG: Teilungserklärung/Gemeinschaftsordnung, geltende Verteilungsschlüssel, Wirtschaftspläne, Sonderumlagen, maßgebliche Beschlüsse und Eigentümernachweise | G0/G4, W01–W13 | offen |
| V16 | Verantwortliche fachkundige Person für unabhängige Buchungs-/Abrechnungssollwerte und Abnahme; Rechts-/Steuerprüfung bei Zweifelsfragen | G1/G3/G4 | offen |
| V17 | Anwendbarkeits- und Aufbewahrungsmatrix je Rechtsträger, Unterlagenklasse, Frist und Sperrgrund; Belegeinsichtsverfahren auch ohne Portal | G1/G3/G4/G5 | offen |
| V18 | Bank-/Zahlungsvollmachten, Rollen, Limits, zulässige Mandatsverfahren, Empfängerdatenkontrolle, Freigabeverfahren | G2 | offen |
| V19 | Unterjährige Übernahme: belegte vollständige Jahresdaten und Überleitungsplan statt nur Anfangssalden | M8/M10/G3/G4 | offen |
| V20 | Anhang-E-Entscheidungen (Rechtsträger-Buchungskreise, Zeit- und Statusmodell) | G0 | entschieden in Version 2.0, Abschnitt 6.9 und Anhang E; Betreiber bestätigt mit Startauftrag |
| V21 | Steuerlicher Status und relevante Sonderfälle je GdWE/Eigentümer/Mandant; Prüfzuständigkeit für Umsatzsteuer, Bauleistungen und § 35a | M13–M18/G4 | offen |
| V22 | Anonymisierte repräsentative Originalbelege, Vertrags-/Eigentümerwechsel, Rücklastschriften, Kostenverteilungen und Abrechnungen als freigegebene Testfälle | Anhang D | offen |
| V23 | Quellen- und Aktualitätslücken P01–P05 aus Anhang C schließen; Rechtsstand zum jeweiligen Anwendungszeitpunkt belegen | betroffene Freigabe | offen |

### 19.2 Startanweisung für den Coding-Agenten

Startbefehl des Betreibers: „Lies docs/MASTER-PROMPT.md vollständig, lege docs/OPEN_QUESTIONS.md aus Abschnitt 19.1 und Anhang C.2 an, lege docs/ASSUMPTIONS.md an und beginne mit Meilenstein M1. Arbeite tokensparend nach Regel 15.“ Danach: Repo nach Abschnitt 17, dieses Dokument als `docs/MASTER-PROMPT.md`, Anhang D als `docs/acceptance/D-cases.md` mit Zuordnung zu Meilensteinen, Feature-Flags für G1 bis G5 je Mandant (Standard aus). Die Freigabe zur Programmierung ist nicht zugleich Freigabe für echte Zahlungen oder produktive Abrechnungen.

### 19.3 Nächste Version dieses Prompts

Version 2.1 entsteht, sobald V1 (Dossiers) vorliegt: Abschnitt 13 wird mit konkreten Endpunkten, Datenmodellen und Entscheidungen je Bestandstool gefüllt, Abschnitt 18 um Migrationsmeilensteine für übernommene Tools ergänzt. Version 2.2 folgt nach V2, V3 und V5 mit Banking-Konfiguration und Aufwandsschätzung je Phase. Rechts- und Steuerfreigaben (V7, V12, V13, V16, V21, V23) werden im Quellenregister mit Datum und Verantwortlichem nachgetragen, nicht durch Versionswechsel behauptet.

## 20. Glossar (Deutsch, Englisch im Code)

| Deutsch | Code | Bedeutung |
| --- | --- | --- |
| Mandant | `tenant` | Verwaltungsgesellschaft als Nutzer der Plattform (nicht zu verwechseln mit Mieter) |
| Objekt | `property` | Verwaltungsmandat, Liegenschaft |
| Gebäude | `building` | Haus innerhalb eines Objekts |
| Verwaltungseinheit (VE) | `unit` | Wohnung, Gewerbe, Stellplatz usw. |
| Miteigentumsanteil (MEA) | `co_ownership_share` | Anteil am Gemeinschaftseigentum |
| Umlageschlüssel | `allocation_key` | Verteilungsmaßstab für Kosten |
| Vertrag (Mietvertrag, Eigentumsverhältnis) | `contract` (`tenancy`, `ownership`) | Verbindung Partei zu Einheit |
| Vertragspartei, Haushalt | `party` | Eine oder mehrere Personen als Vertragspartner |
| Mieter | `tenant_resident` (Rolle), `contract.kind = tenancy` | Bewohner mit Mietvertrag |
| Eigentümer | `owner` | Wohnungseigentümer oder Objekteigentümer |
| Sondereigentumsverwaltung (SEV) | `sev` | Mietverwaltung für einzelne Eigentümer innerhalb einer WEG |
| Wohnungseigentümergemeinschaft (WEG) | `hoa` | Gemeinschaft der Eigentümer |
| Hausgeld | `hoa_fee` | Vorschuss der Eigentümer an die WEG |
| Erhaltungsrücklage | `reserve` | Rücklage der WEG |
| Wirtschaftsplan | `economic_plan` | Jahresplan der WEG |
| Hausgeldabrechnung | `hoa_fee_statement` | Jahresabrechnung der WEG |
| Betriebskostenabrechnung | `operating_cost_statement` | Nebenkostenabrechnung Miete |
| Abrechnung Mietobjekt | `owner_statement` | Eigentümerabrechnung in der Fremdverwaltung |
| Sollstellung | `receivable` | Forderungsbuchung aus Vertragszahlung |
| Offener Posten | `open_item` | unbezahlte Forderung oder Verbindlichkeit |
| Debitor, Kreditor | `debtor`, `creditor` | Schuldner (Vertrag), Gläubiger (Dienstleister) |
| Buchungskreis | `ledger` | Buchhaltung eines Objekts |
| Buchungssatz, Buchungszeile | `journal_entry`, `journal_line` | doppelte Buchführung |
| Festschreibung | `lock` | GoBD-Sperre einer Periode |
| Mahnung, Mahnlauf | `dunning_case`, `dunning_run` | Zahlungserinnerung und Mahnstufen |
| Zahllauf | `payment_run` | Sammelausführung von Zahlungen |
| Kaution | `deposit` | Mietsicherheit |
| Eigentümerversammlung (ETV) | `meeting` | Versammlung der WEG |
| Tagesordnungspunkt (TOP) | `agenda_item` | Beschlussgegenstand |
| Beschluss-Sammlung | `resolution` | Register der Beschlüsse |
| Verwaltungsbeirat | `board` | Unterstützt und überwacht den Verwalter; Prüfung und Stellungnahme nach § 29 WEG, keine automatische Vertretungs-/Zahlungsbefugnis |
| Ticket, Auftrag | `ticket`, `work_order` | Vorgang, Handwerkerauftrag |
| Dienstleister, Handwerker | `service_provider` | externer Auftragnehmer |
| Messdienst | `metering_service` | externer Abrechnungsdienst für Heizkosten |
| Verwalterhonorar | `admin_fee` | Vergütung der Verwaltung |
| Zustellweg | `delivery_channel` | Post, E-Mail, Portal |
| Schwarzes Brett | `notice_board` | Aushang im Portal |
| GdWE / Gemeinschaft der Wohnungseigentümer | fachlicher Rechtsträger, technische Abbildung durch Claude | Trägerin gemeinschaftlicher Rechte/Pflichten; nicht identisch mit Verwaltungsgesellschaft oder Einzeleigentümer |
| Abrechnungsspitze | bestehende Codebegriffe prüfen, nicht ungefragt umbenennen | Abrechnungsanpassung auf Basis beschlossener Soll-Vorschüsse; getrennt von offenen Vorschussforderungen |
| Vorschussrückstand | bestehende OP-Logik | Nicht gezahlter Vorschuss mit eigenem Ursprung, Schuldner und Fälligkeit |
| Abrechnungssaldo | Informationsauswertung | Zusammenfassende Saldoanzeige, kein eigener zusätzlicher Anspruch neben bereits gebuchten Bestandteilen |
| Belegeinsicht | Berechtigungs-/Dokumentenfunktion | Zugriff auf Unterlagen im gesetzlichen/vertraglichen Umfang; nicht gleich fachliche Prüfung |
| Belegprüfung | Prüfprozess | Tatsächlich dokumentierte Prüfung mit Umfang, Ergebnis und Version |
| Beiratsstellungnahme | Prüfbericht | Aussage des Beirats mit ausgewiesenem Prüfungsumfang; kein pauschales Testat und keine Entlastung |
| Zahlungsfreigabe | bestehender Payment-Workflow | Autorisierung eines bestimmten unveränderlichen Zahlungsstands; nicht Bankausführung |
| Archiv / Backup | bestehende DMS-/Betriebsfunktionen | Geordnete beweisbare Aufbewahrung / Wiederherstellbarkeit; unterschiedliche Zwecke |

---

## Anhang A: Immoware24-Referenz (Parität)

**Einordnung:** Aus der Ausgangsfassung übernommene Produkt-/Migrationsreferenz. Bezeichnungen, Status und Schlüssel sind keine gesetzlichen Vorgaben. Historische Konten wie „Kabel-TV“, Status „gelöscht“ und pauschale Portalansichten dürfen nur innerhalb der fachlich zulässigen Regeln dieser Fassung verwendet werden. Eigene Formulierungen, eigener Code und zulässige Exportquellen; keine pauschale Übernahme fremder geschützter Inhalte.

### A.1 Kontenrahmen (Auszug der HVM-Konvention)

001200 WEG-Konto, 001201 Rücklagenkonto, 001300 Kasse, 001400 Überzahlungen aus Vorjahren, 008000 Rücklage Erhaltungsrücklage, 008500 Darlehen, 008600 Hypotheken, 009000 Anfangsbestandskonto, 009999 Durchlaufposten WEG, 026000 Vorsteuerrückerstattungen, 027000 Durchlaufposten Skonti, 028100 Zinseinnahmen WEG-Konto, 028101 Zinseinnahmen Erhaltungsrücklage, 029100 Entnahme Erhaltungsrücklage, 030000 Zuführung Erhaltungsrücklage, 040100 Hausmeisterkosten, 040200 Hausmeistergehalt, 040300 Reinigungskosten, 040400 Gartenarbeiten bzw. Pflege Außenanlagen, 040500 Winterdienst, 041000 Brennstoffkosten, 041100 Schornsteinfeger, 041200 Emissionsmessung, 041300 Wartung Heizung, 041400 Heizungsreparaturen, 041500 Miete Heizungszähler, 041600 Miete Kaltwasserzähler, 041700 Miete Warmwasserzähler, 041800 Servicekosten Heizkostenabrechnung, 041801 Servicekosten Wasserabrechnung, 041805 Rauchwarnmelder, 042000 Wasser allgemein, 042100 Trinkwasser, 042200 Abwasser, 042300 Niederschlagswasser, 043000 Allgemeinstrom, 060100 Hausgeld, 060200 Erhaltungsrücklage, 09xxxx Debitoren je Vertrag. Kontoattribute: Kategorie, Typ, USt-Option (ohne, voll, ermäßigt), anrechenbare USt (fester Prozentsatz oder Gewerbeanteil), EÜR/USt-Relevanz, Sichtbarkeit, drei Buchungstexte, Art der Abrechnung (Hausgeld, Rücklage), Kategorie (umlagefähig Mieter Heizung/Warmwasser, Wasser, Sonstige; nicht umlagefähig je dito), Verteilung über mehrere Schlüssel.

### A.2 Umlageschlüssel (Standardliste)

Wohnfläche (m²), Heizfläche (m²), Warmwasserfläche (m²), umbauter Raum (cbm), Miteigentumsanteil (Anzahl), Anzahl Einheit (Einh.), Personen, Kabel-TV (Einh.), Müllentsorgung (m²), Aufzugsnutzung (m²), Festumlage (EUR), extern berechnete Wasser-/sonstige Kosten (EUR), extern berechnete Heizkosten (EUR); verbrauchsbasiert: Gas, Heizung, Kaltwasser, Warmwasser, Strom, Wasser gewerblich, Wasser nicht gewerblich, Mieterwechsel ohne Zähler; individuelle Schlüssel je Objekt (z. B. Aufzug je Hauseingang und Etage in MEA).

### A.3 Buchungstypen, Zahlungsarten, Statuslisten

Buchungstypen: Sollstellung, Rechnung, benutzerdefinierte Buchung, Bankumbuchung, Kostenumbuchung, Anfangsbestandsbuchung, Zahlung Debitor. Zahlungsarten: Hausgeld, Erhaltungsrücklage, Miete, Betriebskosten-VZ, Heizkosten-VZ, Garagenmiete, Stellplatzmiete, sonstige Miete/Mietminderung; Intervalle monatlich, quartalsweise, halbjährlich, jährlich; Fälligkeit Tag, Werktag, letzter Tag, Tag im Folgemonat. Ticketstatus: neu, in Bearbeitung, wartend, ausgeführt, abgeschlossen, abgewiesen; Priorität niedrig, normal, hoch, dringend, sofort. Beschlussstatus: positiv, negativ, bestandskräftig, angefochten, aufgehoben, gelöscht, rechtskräftig, bedeutungslos. Versammlungstypen: ordentliche ETV, außerordentliche ETV, Wiederholungs-, Fortsetzungs-, Teilversammlung, Umlaufbeschluss, Gerichtsbeschluss (nur Beschluss-Sammlung). Kautionstypen: Kautionsversicherung, Sparbuch, Barkaution, Bürgschaft, Festgeld, Patronatserklärung, andere. Zählerarten: Gas, Heizung, Kaltwasser, Warmwasser, Strom, Wasser gewerblich, Wasser nicht gewerblich, Mieterwechsel ohne Zähler.

### A.4 Rollen (Vorlage für Systemrollen)

Administrator, Standard, nur Lesezugriff, nur Lesezugriff Stammdaten, Sachbearbeiter ohne Löschen, Sachbearbeiter ohne Buchhaltung, Buchhalter ohne Onlinebanking, Buchhalter mit Onlinebanking, Hausmeister, technischer Sachbearbeiter, Support, Versicherungsmakler; zusätzlich in der Plattform: Plattformadministrator, Mandantenadministrator, Steuerberater (lesend Buchhaltung), Beirat (Portal), Dienstleister (Portal).

### A.5 Portal24-Funktionen (Untergrenze für Phase 3)

Verwalteransicht: Datenquelle mit White-Label, Rechtliches, Farbset, Bilder, Features (Datenschutz, Chat-Bot, Ticketanbindung), Kommunikation, Nutzerverwaltung mit Einladung und Support-Login, Statistiken, Formularbaukasten (Kategorien, Zustellung als Ticket oder E-Mail, Freigabe je Rolle, 20 Elementtypen). Eigentümeransicht: alle Mieterträge, Formulare, Dokumente (Kontext, Status neu/gelesen), Tickets, Objektübersicht mit Ansprechpartnern und Schwarzem Brett, Mieterträge je Objekt, Versammlungen, Beschluss-Sammlung, beschlossene Zahlungen mit SEPA-Informationen, Geltungsdauer Zahlungen, Umlageeigenschaften, Verbrauchsinformationen, Chat.

### A.6 Bekannte Schwächen, die nicht übernommen werden

Objekt muss „geöffnet“ werden; Buchhaltung ohne mandantenweite Sicht; Bankumsätze nur seitenweise zu 25; kein Lernen aus Zuordnungen; manuelles „in DMS speichern“; keine API; Portal ohne Self-Service; Dienstleisterportal als separates Produkt; Versammlungsunterlagen nicht automatisch im Portal; Nutzer ohne E-Mail nicht einladbar; Desktop-Banking-Client als Einzelplatzabhängigkeit.

## Anhang B: Prompt zur Erhebung der Bestandstools

Diesen Prompt führt der Betreiber in jedem Claude-Code-Projekt der Bestandstools aus („Müller FLOW: Fable 5.1 und Ultracode Strategie“, „Immoware Hub Integrationsplattform“, „Mail optimierung“, Übergabeprotokoll, Objektakte, smart-einzug). Das Ergebnis wird als `docs/integrations/<tool>.md` in das Plattform-Repo übernommen und zusätzlich als WDB-Eintrag in der Wissensdatenbank abgelegt.

```
Erstelle ein Integrationsdossier dieses Projekts für die geplante MH Verwaltungsplattform (mandantenfähige Immobilienverwaltungssoftware, Python/FastAPI, PostgreSQL, Next.js, REST-API mit Webhooks, OIDC-Login). Arbeite tokensparend: lies README, Konfiguration, Datenmodell, API-Definitionen und Einstiegspunkte; lies keine Testdaten, Logs oder generierten Dateien. Schreibe das Ergebnis nach docs/integrations/DOSSIER.md in deutscher Sprache, ohne Gedankenstriche, mit folgenden Abschnitten:

1. Zweck und Nutzer: Was tut die Software, wer nutzt sie, welche Geschäftsprozesse deckt sie ab.
2. Technik: Sprache, Frameworks, Datenbank, Hosting (Server, Docker-Dienste, Domains), Abhängigkeiten zu externen Diensten (Google, Immoware24, lexoffice, KI-Anbieter), Konfigurationsvariablen (Namen, ohne Werte).
3. Datenmodell: Tabellen oder Entitäten mit Feldern, Schlüssel, Beziehungen; welche Felder Objekte, Einheiten, Kontakte, Verträge oder Dokumente beschreiben und wie sie identifiziert werden (z. B. Objektnummer).
4. Schnittstellen: vorhandene REST-Endpunkte oder Funktionen mit Ein- und Ausgabe, Webhooks, Dateiformate, Zeitpläne, Authentifizierung.
5. Fachlogik, die erhalten bleiben soll: Klassifikationsregeln, Prompts, Textbausteine, Zuordnungslogik, Workflows, mit Verweis auf Dateien.
6. Bekannte Probleme und technische Schulden.
7. Empfehlung: anbinden (als eigenständiger Dienst über API und Webhooks), übernehmen (als Modul der Plattform) oder ablösen; Begründung; Aufwand grob in Tagen; Reihenfolge der Schritte; welche Daten migriert werden müssen.
8. Offene Fragen an den Betreiber.

Halte das Dossier unter 3.000 Wörtern. Nenne keine personenbezogenen Daten aus Datenbeständen, nur Strukturen. Gib am Ende eine Zusammenfassung in zehn Zeilen aus.
```

---

## Anhang C: Rechts-, Quellen- und Anwendungsregister

### C.1 Umgang mit diesem Register

**Rechercheabruf: 23.09.2026.** „Geprüft“ bedeutet hier, dass der angegebene Text für die benannten Anforderungen eingesehen wurde, nicht, dass alle denkbaren Sachverhalte oder die tatsächliche Umsetzung rechtlich abschließend geprüft wären. Maßgeblich ist die zum konkreten Vorgang passende Fassung. Bereits verkündete spätere Regeln und historische Abrechnungsjahre benötigen eigene Wirksamkeitszeiträume. Vor produktiver Freigabe sind Änderungen seit dem Abruf erneut zu prüfen.

Die folgende Matrix ist ein fachlich zugeschnittener Ausgangskatalog, keine Behauptung einer abschließenden Aufzählung sämtlicher Vorschriften. Hinzu kommen je Objekt insbesondere Gemeinschaftsordnung, Teilungserklärung, konkrete Beschlüsse, Verwalter-/Miet-/Dienstleisterverträge sowie örtliche, steuerliche und technische Sonderfälle. Unbekannte Grundlagen bleiben offen.

| ID | Primärgrundlage / geprüfter Schwerpunkt | Betroffene Anforderungen und Anwendungsgrenze |
| --- | --- | --- |
| R01 | [§ 9a WEG](https://www.gesetze-im-internet.de/woeigg/__9a.html), [§ 18 WEG](https://www.gesetze-im-internet.de/woeigg/__18.html) | GdWE als Rechtsträger; Eigentümereinsicht in Verwaltungsunterlagen. B01, W01, PÜ10. Keine automatische Öffnung anderer Gemeinschaften oder privater fremder Akten. |
| R02 | [§ 16 WEG](https://www.gesetze-im-internet.de/woeigg/__16.html), [§ 21 WEG](https://www.gesetze-im-internet.de/woeigg/__21.html) | Kostenverteilung und bauliche Veränderungen; objektspezifische Grundlagen und Entscheidungskompetenz prüfen. W03, W09, W10. |
| R03 | [§ 29 WEG](https://www.gesetze-im-internet.de/woeigg/__29.html) | Aufgaben des Beirats und Prüfung/Stellungnahme. PÜ06–PÜ09. Kein gesetzliches Totaltestat und keine automatische Bankvollmacht. |
| R04 | [§ 28 WEG](https://www.gesetze-im-internet.de/woeigg/__28.html) | Kalenderjähriger Wirtschaftsplan, Beschluss über Vorschüsse/Nachschüsse bzw. Anpassungen, Fälligkeit, Vermögensbericht. A01, W02, W04–W06, W11. Rechtsprechungsdetails zusätzlich P01/P02. |
| R05 | [§ 23 WEG](https://www.gesetze-im-internet.de/woeigg/__23.html), [§ 24 WEG](https://www.gesetze-im-internet.de/woeigg/__24.html), [§ 25 WEG](https://www.gesetze-im-internet.de/woeigg/__25.html), [§ 48 WEG](https://www.gesetze-im-internet.de/woeigg/__48.html) | Beschlüsse, Einladung, Versammlung, Vollmacht, Stimmrecht, Sammlung, virtuelle Teilnahme und Übergangsregel. W06/W13. Konkrete Gemeinschaftsregeln und Verfahrenslage bleiben zu prüfen. |
| R06 | [§ 556 BGB](https://www.gesetze-im-internet.de/bgb/__556.html) | Betriebskostenvereinbarung, Abrechnung/Fristen, Wirtschaftlichkeit und ausdrücklich elektronische Belegeinsicht nach Abs. 4. A02/A04, PÜ11. Nicht pauschal auf WEG-Jahresabrechnungen oder jede Gewerbemiete übertragen. |
| R07 | [BGB-Gesamtfassung, § 556a](https://www.gesetze-im-internet.de/bgb/BJNR001950896.html), [§ 1 BetrKV](https://www.gesetze-im-internet.de/betrkv/__1.html), [§ 2 BetrKV](https://www.gesetze-im-internet.de/betrkv/__2.html) | Mietrechtlicher Verteilungsmaßstab einschließlich vermieteter Eigentumswohnung, Kostenarten und Ausschlüsse. A02/A03. § 556a wurde wegen gestörtem Einzelabruf im Gesamttext geprüft. |
| R08 | [§ 560 BGB](https://www.gesetze-im-internet.de/bgb/__560.html) | Änderungen von Betriebskosten/Vorauszahlungen im zutreffenden Vertragskontext. A04. Keine unbesehene Planänderung durch Bestätigen der Abrechnung. |
| R09 | [§ 366 BGB](https://www.gesetze-im-internet.de/bgb/__366.html), [§ 367 BGB](https://www.gesetze-im-internet.de/bgb/__367.html) | Tilgungsbestimmung und Reihenfolge. 7.4.5. Vertragliche Besonderheiten und zulässige Reaktionen auf abweichende Bestimmung prüfen. |
| R10 | [§ 286 BGB](https://www.gesetze-im-internet.de/bgb/__286.html), [§ 288 BGB](https://www.gesetze-im-internet.de/bgb/__288.html), [BGB-Gesamtfassung](https://www.gesetze-im-internet.de/bgb/BJNR001950896.html) | Fälligkeit versus Verzug, Zins-/Pauschalbedingungen; Basiszins und historische Änderungen gesondert amtlich belegen. 7.5. Keine harte Zinskonstante aus Modellwissen. |
| R11 | [§ 7 HeizkostenV](https://www.gesetze-im-internet.de/heizkostenv/__7.html), [§ 9b HeizkostenV](https://www.gesetze-im-internet.de/heizkostenv/__9b.html) | Verbrauchs-/Grundanteile, besondere 70-Prozent-Fälle, Nutzerwechsel. H01/H02. Weitere für konkrete Anlage relevante Vorschriften (§§ 1–4, 6, 8–11) vor eigener Berechnung ergänzen. |
| R12 | [§ 6a HeizkostenV](https://www.gesetze-im-internet.de/heizkostenv/__6a.html) | Unterjährige Informationen und Abrechnungsinformationen. H03. Bestehende Pflichten warten nicht auf die spätere Portalphase. |
| R13 | [§ 12 HeizkostenV](https://www.gesetze-im-internet.de/heizkostenv/__12.html) | Kürzungsrechte, Ausnahme für einzelner Eigentümer/GdWE, Übergänge. H02/H03. Kürzungsfälle nicht blind kumulieren oder pauschal übertragen. |
| R14 | [§ 5 HeizkostenV](https://www.gesetze-im-internet.de/heizkostenv/__5.html), [§ 12 HeizkostenV](https://www.gesetze-im-internet.de/heizkostenv/__12.html) | Ausstattung, Fernablesbarkeit und Übergangs-/Sonderfälle. H03. Konkreten Geräte-/Gebäudebestand und Ausnahmen prüfen. |
| R15 | [CO2KostAufG § 5](https://www.gesetze-im-internet.de/co2kostaufg/__5.html), [§ 8](https://www.gesetze-im-internet.de/co2kostaufg/__8.html), [§ 9](https://www.gesetze-im-internet.de/co2kostaufg/__9.html), [Anlage](https://www.gesetze-im-internet.de/co2kostaufg/anlage.html) | Wohn-/Nichtwohngebäude, Stufen, Beschränkungen. Ergänzend §§ 2–7 und 11 in Gesamtfassung R16 für Anwendbarkeit, Informationen, Selbstversorgung und Übergänge. H04. |
| R16 | [CO2KostAufG-Gesamtfassung](https://www.gesetze-im-internet.de/co2kostaufg/BJNR215400022.html) | Abgerufener Text weist Änderung vom 23.07.2026 und §§ 5a–5d mit späteren Anwendungsterminen aus. H05: datierter Umsetzungsauftrag, keine pauschale Aktivierung in 2026. Die Fundstelle weist auf noch nicht abschließend dokumentarisch bearbeitete Änderung hin; vor Implementierung Verkündungsfassung und Übergang erneut abgleichen. |
| R17 | [§ 146 AO](https://www.gesetze-im-internet.de/ao_1977/__146.html), [AO-Gesamtfassung, § 147](https://www.gesetze-im-internet.de/ao_1977/BJNR006130976.html), [BMF-AO-Handbuch § 147, Ausgabe 2025](https://ao.bundesfinanzministerium.de/ao/2025/Abgabenordnung/Vierter-Teil/Zweiter-Abschnitt/Erster-Unterabschnitt/Paragraf-147/inhalt.html) | Ordnung, Nachvollziehbarkeit, Aufbewahrung/Fristbeginn und Datenzugriff im steuerlichen Anwendungsbereich. B03/B05, 7.7, S04/S05. § 147 im aktuellen Gesamttext gegengeprüft; Handbuch zusätzlich. |
| R18 | [§ 257 HGB](https://www.gesetze-im-internet.de/hgb/__257.html) | Differenzierte Aufbewahrungsfristen im handelsrechtlichen Anwendungsbereich und Sonderfälle. S04. Keine automatische HGB-Pflicht jeder GdWE. |
| R19 | [BMF, GoBD-Änderung vom 14.07.2025 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Weitere_Steuerthemen/Abgabenordnung/2025-07-14-GoBD-2-aenderung.pdf?__blob=publicationFile&v=4) | Strukturierte Rechnungsdaten, zusätzliche Bildinformationen und Datenzugriff; vier Seiten eingesehen. 7.7/S03. Die im Schreiben bezeichnete Basisfassung 28.11.2019 und Änderung 11.03.2024 vor abschließender Verfahrensfreigabe vollständig mitprüfen, nicht dieses Änderungsschreiben als gesamte GoBD ausgeben. |
| R20 | [§ 9 UStG](https://www.gesetze-im-internet.de/ustg_1980/__9.html), [§ 15 UStG](https://www.gesetze-im-internet.de/ustg_1980/__15.html) | Option und Vorsteuer einschließlich Zuordnung/Aufteilung. S01/PÜ03. Unternehmereigenschaft, Steuerbefreiung, Leistungsart und tatsächliche Verwendung fallbezogen. |
| R21 | [§ 14 UStG](https://www.gesetze-im-internet.de/ustg_1980/__14.html), [§ 14b UStG](https://www.gesetze-im-internet.de/ustg_1980/__14b.html) | Rechnung und strukturierte Rechnungsdaten; Aufbewahrung. S02–S04. Ausnahmen, Übergänge und Rechnungspflicht des konkreten Beteiligten gesondert einordnen. |
| R22 | [BMF-FAQ E-Rechnung, Stand März 2026](https://www.bundesfinanzministerium.de/Content/DE/FAQ/e-rechnung.html) | Empfang seit 2025, Ausstellungsübergänge bis Ende 2026/gegebenenfalls 2027, Formate und Abgrenzung technischer Validierung zur steuerlichen Anerkennung. S02. Keine Zusammenfassung ersetzt den gesetzlichen Einzelfall-/Zeitbezug. |
| R23 | [§ 13b UStG](https://www.gesetze-im-internet.de/ustg_1980/__13b.html), [§ 48 EStG](https://www.gesetze-im-internet.de/estg/__48.html), [§ 48b EStG](https://www.gesetze-im-internet.de/estg/__48b.html) | Sonderprüfung Bauleistungen/Steuerschuldnerschaft/Freistellung. PÜ03/S01. Keine automatische Anwendung auf jede Handwerkerrechnung; bei Anwendung übrige erforderliche Vorschriften ergänzen. |
| R24 | [§ 35a EStG](https://www.gesetze-im-internet.de/estg/__35a.html) | Nachweisdaten für begünstigte Aufwendungen; Arbeitsanteile, Zahlung und persönliche Voraussetzungen unterscheiden. H06. Verwaltungspraxis zu WEG-Bescheinigungen/zeitlicher Zuordnung zusätzlich P03. |
| R25 | [DSGVO, konsolidierter Text auf EUR-Lex](https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:02016R0679-20160504) | Insbesondere Art. 5, 6, 15, 17, 28, 32 und Kapitel V als Prüfumfang; Zugriff, Zweck, Auskunft, Löschung, Verantwortlichkeiten und Übermittlung. PÜ10–PÜ13/S05/S06. Konkrete Rollen-/Vertragsprüfung erforderlich; kein AVV-Häkchen als Gesamtbeleg. |

**Ergänzender unmittelbar geprüfter Baustein:** [§ 551 BGB](https://www.gesetze-im-internet.de/bgb/__551.html) für Wohnraummietsicherheiten: zulässige Sicherung, Teilzahlungen, Vermögenstrennung und Zinszuordnung in den Kautionsfunktionen. Keine automatische Verwendung einer Kaution zur laufenden Finanzierung oder pauschaler Abzug strittiger Forderungen ohne Prüfung.

### C.2 Offen zu schließen: keine erfundenen Quellen oder Freigaben

| ID | Noch erforderliche Prüfung | Vorgehen bis zur Klärung |
| --- | --- | --- |
| P01 | Aktuelle Rechtsprechung zu WEG-Abrechnungsspitze, Eigentümerwechsel und Sondernachfolgerhaftung; insbesondere BGH 02.12.2011 – V ZR 113/11 und 09.03.2012 – V ZR 147/11 sowie Fortgeltung im heutigen §-28-System. | Auszüge des Entscheidungstexts V ZR 113/11 waren als [Textwiedergabe über dejure](https://dejure.org/dienste/vernetzung/rechtsprechung?Aktenzeichen=V+ZR+113%2F11&Datum=02.12.2011&Gericht=BGH) einsehbar; amtliche Volltextabrufe waren in dieser Recherche gestört. Keinen vollständig verifizierten amtlichen Rechtsprechungsabgleich behaupten. Regelfälle fachlich gegenprüfen; Sonderfälle bis Freigabe nicht automatisieren. |
| P02 | WEG-Geldfluss-/Heizkostenüberleitung, u. a. BGH 17.02.2012 – V ZR 251/10, sowie Folgen späterer Beschlusskorrektur/gerichtlicher Ungültigkeit. | Offizielle Presse-/Entscheidungsfundstellen gefunden, Volltextabruf eingeschränkt. [Amtliche Pressefundstelle](https://www.bundesgerichtshof.de/SharedDocs/Pressemitteilungen/DE/2012/2012025.html). Vor G4 vollständigen aktuellen fachlichen Regelstand und Testfall freigeben. Keine erfundenen Aktenzeichen zu neueren Entscheidungen ergänzen. |
| P03 | Vollständige aktuelle GoBD-Fassung, einschlägige USt-Anwendungsregeln, mögliche §-15a-Berichtigungsfälle, §-35a-WEG-Bescheinigung/zeitliche Zuordnung, weitere Bauabzugsteuerregeln. | Rechts-/Steuerverantwortliche bestätigen Anwendbarkeit und Sollfälle. Spezialautomatiken bleiben bis dahin aus. [§ 15a UStG](https://www.gesetze-im-internet.de/ustg_1980/__15a.html) ist als Prüfquelle notiert; Einzelnormabruf war hier nicht erfolgreich. |
| P04 | Konkrete Miet-, WEG-, Bank-, DMS-, Dienstleister- und Betreiberverträge; AVV-/Verantwortlichkeitslage, Portal/BFSG-Anwendbarkeit und gegebenenfalls weitere Vermarktungs-/KI-Pflichten. | Nur tatsächliche Unterlagen auswerten. Fehlende Verträge/Bestandsdossiers bleiben offene Voraussetzungen; keine Branchenannahmen als Tatsachen. |
| P05 | Aktuelle Bank-/SEPA-Scheme- und Formatspezifikationen, EBICS-Auftrags-/BTF-Varianten, zulässige Mandatsverfahren, Vorabinformation, Rückgaben, Empfängerprüfung sowie aktuelle DATEV-/Messdienst-/E-Rechnungsformate. | Claude prüft anhand des konkret gewählten Anbieters und verbindlicher Spezifikationen. Die Architektur/Adapterauswahl wird hier nicht verändert. Keine Aussage „heutige Bankformate geprüft“, solange keine passenden Spezifikationen und Testdateien vorliegen. |

Für jede Regel sind mindestens Quelle, Fassungs-/Abrufdatum, Geltungsbeginn/-ende, Betroffenheit, fachlicher Verantwortlicher, Testfälle und Freigabestatus festzuhalten. Gesetzesänderung, Veröffentlichungsdatum und Anwendungsbeginn sind nicht gleichzusetzen.

## Anhang D: Fachliche Abnahmefälle mit Soll-Ergebnissen

**Status:** Testanforderungen, keine ausgeführten Softwaretests. Zahlen sind bewusst einfache, eigenständig nachrechenbare Modellfälle. Genannte fachliche Annahmen sind Bestandteil des Falls; sie ersetzen nicht die Prüfung realer Vertrags-/Beschlussunterlagen. Fach-/Rechtsverantwortliche bestätigen die Umsetzung und Sonderfälle vor Produktivfreigabe. Technische Testdateien, Frameworks und Schemaabbildung bestimmt Claude im bestehenden Stack.

### D.1 Rechenfälle

| ID | Eingabe und ausdrückliche Annahmen | Erwartetes Ergebnis / verbotener Fehler |
| --- | --- | --- |
| D01 WEG-Spitze/Rückstand | Kostenanteil 3.000,00 EUR; beschlossene, kostenbezogene Soll-Vorschüsse 2.800,00 EUR; darauf gezahlt 2.500,00 EUR. Kein Eigentümerwechsel, keine Rücklagen-/Sonderumlagenkomponente, keine sonstige Korrektur. Wirksame einschlägige Beschlussgrundlage wird im Test später gesetzt. | Abrechnungsspitze 200,00 EUR; bestehender Vorschussrückstand 300,00 EUR; nach einschlägiger Beschlusswirkung Gesamtbelastung aus beiden 500,00 EUR. Verboten: neue Abrechnungsforderung 500,00 EUR plus nochmals alter Rückstand 300,00 EUR. |
| D02 WEG-Anpassung/Guthaben | Kostenanteil 2.500,00 EUR; Soll-Vorschüsse 2.800,00 EUR; gezahlt 2.500,00 EUR; im Übrigen wie D01. | Abrechnungsanpassung −300,00 EUR, Vorschussrückstand 300,00 EUR getrennt. Rechnerisch 0,00 EUR Gesamtübersicht, aber keine automatische Auszahlung von 300,00 EUR oder unbegründete Löschung der Altforderung. Rechtlich zulässige Verrechnung eigenständig prüfen. |
| D03 Tatsächliche Rücklage | Anfang 20.000,00 EUR; Soll-Zuführung 6.000,00 EUR, tatsächlich eingegangen 4.500,00 EUR; aus Rücklage finanzierte Mittelverwendung 3.000,00 EUR; der Rücklage rechtmäßig zugeordneter Nettozins 100,00 EUR; keine weiteren Bewegungen. | Tatsächlicher Rücklagenbestand 21.600,00 EUR; offene Beiträge 1.500,00 EUR separat, nicht verfügbare Liquidität. Bestand nicht auf 23.100,00 EUR aufblasen. Bank-/Mittelzuordnung zusätzlich abstimmen. |
| D04 Interner Banktransfer | Gemeinschaft hat auf Bank A 10.000,00 EUR und auf Bank B 20.000,00 EUR. Transfer 1.000,00 EUR von A nach B, keine Gebühr. Beide Bankauszüge werden importiert. | A 9.000,00 EUR, B 21.000,00 EUR, Gesamtsumme weiterhin 30.000,00 EUR. Keine Ausgabe/Einnahme und keine zweite Wirkung des Transfers. Nicht automatisch eine neue Rücklagenzuführung. |
| D05 Echte Gleichzahlungen | Zwei durch ihre Bankdatensätze unterscheidbare tatsächliche Zahlungen von je 400,00 EUR, identischer Zahler, Tag und Verwendungszweck. Anschließend beide Originaldatensätze nochmals importieren. | Zunächst zwei wirtschaftliche Zahlungen, zusammen 800,00 EUR; nach Wiederimport weiterhin 800,00 EUR, weder 400,00 EUR noch 1.600,00 EUR. |
| D06 Zahlung nicht bei Export | Freigegebene Rechnung 1.190,00 EUR. Zahlungsdatei exportiert, dann eingereicht, später tatsächlich ausgeführt. Keine sonstigen Zahlungsvorgänge. | Bei Export/Einreichung bleibt Zahlungsverbindlichkeit offen und Bankbestand unverändert; Ausführung/Nachweis führt einmalig zum Ausgleich 1.190,00 EUR. Doppelte Rückmeldung erzeugt keinen zweiten Ausgleich. |
| D07 Teil-/Überzahlung | Fällige Forderung 1.000,00 EUR; erste zugeordnete Zahlung 600,00 EUR; zweite tatsächliche Zahlung 450,00 EUR. Eindeutiger Schuldner und Tilgungszweck. | Nach Zahlung 1 Rest-OP 400,00 EUR; danach Forderung ausgeglichen und 50,00 EUR gesondertes Guthaben. Guthaben nicht als zusätzlicher Ertrag. Folgefälle Rückgabe/Erstattung separat. |
| D08 Centverteilung | 100,00 EUR, drei identische Verteilungsgewichte, keine abweichende Vorschrift. Produktstandard gleicht den Rest nach stabiler vorab bestimmter Zuordnung aus. | Ein Anteil 33,34 EUR, zwei Anteile 33,33 EUR, Summe 100,00 EUR. Umordnen der Bildschirmzeilen darf nicht den begünstigten/belasteten Datensatz wechseln. |
| D09 Heizkostenüberleitung | Modellfall eines rechtlich freigegebenen Brennstoffbestandsverfahrens: Zahlung für Brennstoff 10.000,00 EUR; in der Periode verbrauchter zurechenbarer Brennstoff 8.000,00 EUR; sonst keine Heizkosten. | Gesamtgeldfluss zeigt Zahlung 10.000,00 EUR; Verbrauchsverteilung 8.000,00 EUR; Unterschied 2.000,00 EUR wird erklärt, nicht weggerechnet. Freigabe P02 erforderlich; keine Behauptung einer universellen Formel für jedes Heizsystem. |
| D10 CO₂-Stufengrenze | Volljähriger Wohngebäude-Regelfall nach § 5/Anlage, keine Ausnahmen oder späteren Sonderregeln; spezifischer Ausstoß 12,0 kg CO₂/m²/Jahr, CO₂-Kosten 100,00 EUR. | Stufe 12 bis unter 17: 90,00 EUR Mieteranteil, 10,00 EUR Vermieteranteil. Vergleichsfall mit freigegebenem spezifischem Wert unter 12: 100/0. Gesetzliche Berechnung/Rundung des Eingangswerts separat testen; kein vorzeitiges Abrunden zur besseren Stufe. |
| D11 Unterjährige Jahresvollständigkeit | Zu übernehmendes Kalenderjahr: 400,00 EUR belegte Ausgaben vor Übernahme und 600,00 EUR danach, beide nach fachlich freigegebener Zuordnung abrechnungsrelevant. Anfangsbestand wird zusätzlich importiert. | Jahresausgaben 1.000,00 EUR. Anfangsbestand ist keine zusätzliche Ausgabe; Daten vor Übernahme fehlen nicht. Belegkette für alle 1.000,00 EUR verfügbar. |
| D12 Abschlag/Schlussrechnung | Gesamte vereinbarte Leistung 5.950,00 EUR brutto; bereits ordnungsgemäß abgerechneter und bezahlter Abschlag 2.380,00 EUR; Schlussrechnung weist beide korrekt aus; keine weiteren Besonderheiten. | Verbleibende Zahlungsverpflichtung 3.570,00 EUR; Leistungssumme insgesamt 5.950,00 EUR, nicht 8.330,00 EUR. Je maßgeblichem Rechenwerk Buchung/Steuer/Zahlung gesondert testen. |

### D.2 Prozess-, Rechtsgrund- und Negativtests

| ID | Zu prüfender Fall | Mindestkriterium |
| --- | --- | --- |
| D13 | WEG-Ergebnis intern bestätigt, aber kein wirksamer Beschluss erfasst | Keine neue nach § 28 Abs. 2 beschlussabhängige Forderung und keine damit begründete Lastschrift. |
| D14 | Ergebnisversion nach erfasster Beschlussfassung geändert | Beschluss wird nicht automatisch auf andere Zahlen umgehängt; Differenz und erneuter rechtlicher Entscheidungsschritt sichtbar. |
| D15 | Alter Eigentümer mit offenen Vorschüssen; neuer Eigentümer; spätere Abrechnung | Im gewöhnlichen Erwerbsfall ohne Sonderhaftung: alter Vorschussrückstand beim bisherigen Schuldner; Abrechnungsspitze beim rechtlich maßgeblichen Eigentümer zur Beschlussfassung. Kaufvertragsausgleich getrennt; P01-Regelstand und Sonderfälle ausdrücklich freigeben. |
| D16 | Nutzen-/Lastenwechsel weicht von rechtlichem Eigentumswechsel ab | Kein stilles Gleichsetzen der Daten; Außen-/Innenverhältnis und jeweiligen Zeitpunkt ausweisen. |
| D17 | Eine Person besitzt zwei Einheiten; eine Einheit gehört mehreren Personen | Zulässige Partei-/Stimmrechtszuordnung ohne doppelte Kopfstimme oder doppelte Forderung; Gemeinschaftsregel berücksichtigen. |
| D18 | Kostenverteilung für einzelne Untergemeinschaft ohne belegte Grundlage | Keine endgültige Abrechnung nur wegen eines angelegten Filters; Prüfhinweis und betroffener Freigabestopp. |
| D19 | Rücklagenzuführung beschlossen, aber unbezahlt; Rücklagenkonto weist anderen Stand aus | Soll, Ist, Bankanlage und Rückstand separat; Differenz erklärt statt automatische Ausgleichsbuchung. |
| D20 | Sonderumlage wird in mehreren Raten eingezogen und später teilweise erstattet | Zweck, Soll/Ist, Verwendung, Fälligkeiten und Erstattungsgrund bleiben erhalten; keine doppelte Kostenerfassung. |
| D21 | Vermietetes Wohnungseigentum ohne abweichenden Miet-Verteilungsschlüssel | § 556a Abs. 3 und Billigkeitsprüfung im Regelwerk; nicht automatisch allgemeine m²-Regel verwenden. |
| D22 | Mischrechnung Verwaltung/Instandsetzung/laufender Betrieb | Nicht umlagefähige Anteile bleiben aus der Wohnraum-Betriebskostenbelastung; Aufteilung belegt. |
| D23 | Mietabrechnung wird kurz vor Fristende erzeugt, gelangt aber nicht rechtzeitig zum Empfänger | Erstellung nicht als Zugang werten; Nachforderungs-/Ausnahmeprüfung und Alternativprozess. |
| D24 | Mietvorauszahlungen offen, Abrechnung wird erteilt | Kein doppelter wirtschaftlicher Anspruch; Behandlung nach fachlich bestätigter Abrechnungsreife-/Vorschussregel. |
| D25 | Nutzerwechsel im Winter mit vorhandener Zwischenablesung | Verbrauchs-/Grundanteile nach passenden HeizkostenV-Regeln; keine pauschale Ganzjahres-Tagesverteilung. |
| D26 | Pflichtige Verbrauchsinformation, Portal noch nicht entwickelt | Nachgewiesener funktionierender Ersatzprozess; kein Verweis auf spätere Phase als Erfüllung. |
| D27 | Gemischte/abweichende CO₂-Sachverhalte, Selbstversorgung, fehlende Lieferangaben | Richtige Regelgruppe oder ausdrücklicher Prüfstatus; keine erfundenen Emissionswerte oder Nullkosten. |
| D28 | Neue, bereits veröffentlichte Rechtsregel gilt erst in späterem Zeitraum | Kein Eingriff in 2026-/Alt-Abrechnungen; Versions-/Stichtagsauswahl getestet. |
| D29 | Eigentümer beantragt GdWE-Unterlagen außerhalb eigener Einzelabrechnung | Gesetzlich gedeckter Zugriff nicht pauschal durch eigenen Vertragsfilter blockiert. |
| D30 | Derselbe Nutzer fordert fremde GdWE/private SEV-Akte ohne Rechtsgrund | Zugriff auch über API, Download, Suche, RAG und Sammel-Export verweigert. |
| D31 | Mieter beantragt notwendige Abrechnungsbelege mit Angaben Dritter | Zweckbezogene Einsicht/erforderliche Schwärzung, keine pauschale Vollverweigerung oder Vollfreigabe fremder Akten. |
| D32 | Beirat prüft nur ausgewählte Belege | Bericht zeigt Stichprobe, Anzahl/Wert, offene/ungeprüfte Positionen; keine Vollprüfungsbehauptung. |
| D33 | Rechnung nach Beiratsprüfung geändert | Betroffene Prüfung als veraltet/eingeschränkt markieren; kein unverändert grüner Gesamtstatus. |
| D34 | Lesebestätigung oder Ablauf einer Portal-Einladung | Keine automatische Anerkennung, kein Verzicht und keine ohne Grundlage ausgelöste Rechtsfrist. |
| D35 | Zahlbetrag oder Empfänger-IBAN nach Zahlungsfreigabe geändert | Alte Freigabe unwirksam für neuen Zahlungsstand; erneute erforderliche Prüfung/Freigabe. |
| D36 | Ein Nutzer versucht, Zahlungsfreigabe mit eigener zweiter Identität zu umgehen | Organisatorisch/technisch definierte unabhängige Freigabe kontrollieren; kein scheinbares Vier-Augen-Prinzip. |
| D37 | Bank lehnt Auftrag ab oder führt nur Teile aus | Nur tatsächlich bestätigte Teilbeträge ausgeglichen; Fehler und Restposten nachvollziehbar. |
| D38 | Bereits zugeordnete Zahlung wird zurückgegeben | Ursprüngliche Zuordnung nachvollziehbar korrigiert; OP wieder richtig offen; Gebühren nur belegt/geprüft. |
| D39 | Eindeutige Tilgungsbestimmung widerspricht freier Kontenpriorität | Rechtskonforme Zuordnung/Prüfung statt stiller Anwendung beliebiger interner Reihenfolge. |
| D40 | Mahnung ohne nachgewiesenen Verzug; ungeeigneter Zins-/40-EUR-Standard | Keine automatische unberechtigte Zusatzforderung; Anspruchsart und Beteiligte prüfen. |
| D41 | Formal valide E-Rechnung über nicht erbrachte Leistung | Technisch valide, sachlich beanstandet; keine automatische Zahlungsfreigabe. |
| D42 | Hybridrechnung: XML und PDF widersprechen sich | Widerspruch sichtbar; strukturierte maßgebliche Daten und relevante Zusatzinformationen erhalten; Zahlungsprüfung statt stiller Auswahl. |
| D43 | Rechnung wird ausschließlich als OCR-Text gespeichert; Original soll gelöscht werden | Aufbewahrungs-/Beweissicherung verhindert unzulässigen Verlust; OCR/JSON ersetzt nicht Original. |
| D44 | §-35a-Anteil fehlt oder ist nur KI-Schätzung | Keine als belegt ausgewiesene Fantasiesumme; Nachforderung/Prüfung. |
| D45 | Steuerliche Option/Gewerbequote ohne passenden Steuerstatus | Keine automatische Vorsteuer-/USt-Buchung nach bloßer Flächenbelegung; Freigabe/Sperre. |
| D46 | Laufende Aufbewahrung/Sperre gegen Löschwunsch oder Import-Rücknahme | Rechtmäßig gesperrte Unterlagen bleiben erhalten; Ablehnung/Teillöschung begründet und protokolliert. |
| D47 | Wiederherstellung eines Backups nach bereits erfolgter rechtmäßiger Löschung | Wiederherstellungsprozess berücksichtigt Lösch-/Sperrentscheidungen, ohne Beweisdaten unzulässig zu zerstören. |
| D48 | Gleichzeitiger Sollstellungslauf, Retry nach Abbruch und doppelter API-Aufruf | Nur eine vollständige wirtschaftliche Wirkung; keine halben Buchungen oder doppelten OP. |
| D49 | Historischer OP-Stichtag wird nach späterer Zahlung/Storno erneut abgefragt | Derselbe historische Bestand wie zum Stichtag; spätere Ereignisse werden nicht rückwirkend eingerechnet. |
| D50 | Nutzer kann nur lesen, versucht Finanzänderung über Massenendpunkt/Job/API-Key | Berechtigung und Freigabe serverseitig wirksam; UI-Verstecken allein genügt nicht. |
| D51 | Unbekannte Rechts-/Verteilungsregel wird als Konfiguration eingetragen | Keine automatische Produktivfreigabe; Quelle, Geltung, Entscheidung und Tests erforderlich. |
| D52 | Umstellung im Parallelbetrieb mit altem Schreibadapter | Genau ein führender Geldprozess je Scope; keine Doppelmahnung/-lastschrift aus beiden Systemen. |
| D53 | Virtuelle Versammlung ohne gültige Grundlage/mit falscher Mehrheit oder technischer Störung | Regel- und Rechteprüfung; dokumentierter Umgang mit Ausfall, nicht einfach erfolgreiches Videotreffen behaupten. |
| D54 | Streit/Anfechtung gegen Beschluss wird erfasst | Kein pauschales sofortiges Löschen/Ausbuchen; rechtlicher Wirksamkeitsstatus und tatsächlich nötige Folgeschritte unterscheiden. |
| D55 | Steuerberater-/Prüfexport und anschließende Auswertung | Buchungen, Schlüssel, Historie, Freigaben und Originalbelege nachvollziehbar verbunden; keine nur optisch schöne PDF-Sammlung. |
| D56 | Private Kaution und GdWE-/Miet-Bankmittel nebeneinander | Kaution bleibt ihrer Vermögenssphäre/Zinszuordnung zugeordnet; kein Zugriff als frei verfügbares Objektgeld. |
| D57 | KI-Ausgabe enthält Anweisung zu neuer IBAN, eigener Freigabe oder Datenexport | Keine Ausführung aus Dokumenttext/Modellantwort; nur geprüfter zulässiger Fachworkflow. |
| D58 | Gebührenrechnung der Verwaltung für SEV | Zahler, Rechnungsempfänger und Zahlungsempfänger korrekt unterschieden; kein irrtümlicher Honorarfluss an Eigentümer durch missverständliches `recipient`-Feld. |

### D.3 Abnahmeprotokoll

Pro Test mindestens Kennung, geprüfte Regelversion, fachliche Annahmen, anonymisierte Eingaben, erwartetes Ergebnis, tatsächlich beobachtetes Ergebnis, Differenz, ausgeführter Testbefehl bzw. manueller Prüfablauf, Softwarestand, Prüfer und Status. Ein Testfall darf nicht nachträglich nur deshalb an das Ist-Ergebnis angepasst werden, damit er besteht. Fachlich begründete Änderungen brauchen dokumentierte neue Soll-Ergebnisse und erneute Prüfung.

## Anhang E: Entschiedene technische Konflikte E01 bis E16

Das Fachreview 1.1.2 hat sechzehn Konflikte zwischen Fachanforderung und Ausgangsentwurf benannt und deren Entscheidung Claude überlassen. Die Abschlussprüfung hat sie wie folgt entschieden; die Umsetzung steht in Abschnitt 6.9, die Tests in Anhang D. Der Stack (Abschnitte 3, 4, 17) bleibt unverändert.

| ID | Konflikt | Entscheidung | Umsetzung | Meilenstein | Tests |
| --- | --- | --- | --- | --- | --- |
| E01 | Ein Buchungskreis je Objekt vermischt bei WEG mit SEV GdWE- und Eigentümervermögen | Buchungskreis je Rechtsträger (`legal_entity`), Kautionen segregiert | 6.9.1 | M4, M5, M10 | D56, B01 |
| E02 | Eigentumsübergang, Nutzen/Lasten und Vertragszeit gleichgesetzt | Getrennte Daten am Eigentumsvertrag, Debitor je Partei, Exclusion-Constraint | 6.9.2 | M5 | D15, D16, D17 |
| E03 | `confirmed` löst Ergebnisbuchung aus | Statusmodell mit Snapshot und Pflichtbeschluss vor `posted` | 6.9.3 | M5 (Schema), M17, M24 | D13, D14, D54 |
| E04 | KI-Konfidenz als Buchungsauslöser | Automatik nur über freigegebene, aktive Regeln; Konfidenz filtert | 6.9.4, 7.4 | M12 | D51, D57 |
| E05 | Backup als Archiv, pauschal 10 Jahre | Aufbewahrungsprofile je Unterlagenklasse, Backup 30 Tage | 6.9.5, 7.11 | M6, M18 | D43, D46, D47 |
| E06 | Portalfilter nur eigener Vertrag | `access_grant` mit GdWE-Mitgliedsrecht und Mieterbelegrecht | 6.9.6, 14 | M21 | D29, D30, D31 |
| E07 | Hash als Dublettenschutz | Bankreferenz als Identität, Hash nur Hinweis, Transferpaare | 6.9.7 | M11 | D04, D05 |
| E08 | Zwei Nachkommastellen für alle Rechenstufen | 14,2 für Beträge, 20,8 für Zwischenwerte, stabile Restcentverteilung | 6.9.8 | M10 | D08 |
| E09 | Pauschale Freigabe, Export gleich Zahlung | Snapshot-gebundene Freigabe, getrennte Prüf-/Buchungs-/Zahlungsstatus | 6.9.9 | M14, M15 | D06, D35, D36, D37, D38 |
| E10 | Historie nur Training | Migrationsjournal als auswertbare Vorperiode, führendes System je Buchungskreis | 6.9.10, 13.1 | M8, M10 | D11, D52 |
| E11 | Phase-1-Schema und späte WEG-Phase | 6.9 ist Phase-1-Schema; Reihenfolge der Phasen unverändert | 6.9, 18 | M2 bis M5 | Migrations-Check in CI |
| E12 | Sicherheitsannahmen nur behauptet | Testpflicht je Pfad (UI, API, Worker, Export, RAG, Webhook) mit RLS-Negativtests; Penetrationstest vor G5 | 0.1 Regel 9, 16 | jeder Meilenstein | D50 |
| E13 | `recipient`-Felder mehrdeutig | Umbenennung in `sev_fee_debtor_party_id`, `invoice_debtor_party_id` | 6.9.11 | M5, M13 | D58 |
| E14 | `board_audit` zu kurz | `audit_engagement`, `audit_item`, `audit_report` | 6.9.12 | M25 (Schema M5 optional) | D32, D33 |
| E15 | Mutable OP-Summen, Bulk-Teilerfolg | Berechnete OP zum Stichtag, Transaktion je Geschäftsvorfall | 6.9.13 | M10 | D48, D49 |
| E16 | Komponentenversionen unbestimmt | Pinning und ADR je Meilenstein | 6.9.14 | M1 ff. | CI |

Blockerklassen für Restpunkte: vor abhängiger Datenmodellentscheidung (keine offen), vor produktiver Finanzfunktion (V2, V3, V7, V8, V16, V18, V19, V21), vor Miet-/WEG-Abrechnung (V15, V22, V23, P01 bis P03), vor Marktstart (V4, V5, V13, V17, P04, P05).

---

Ende des Master-Prompts. Änderungen an diesem Dokument werden versioniert (`docs/MASTER-PROMPT.md`, Changelog am Ende) und gelten ab Commit für alle folgenden Aufgaben.

## Changelog

- 2.0 Final (23.09.2026): Konsolidierung durch Claude. Prüfmodus aufgehoben, Entwicklung ab M1 freigegeben, Geldfunktionen weiter hinter G1 bis G5. Konflikte E01 bis E16 entschieden und als Schemaänderungen in 6.9 übernommen (Buchungskreis je Rechtsträger, Eigentumsdaten, Statusmodell mit Beschlussbezug, Regel-Automatik statt Konfidenzschwelle, Aufbewahrungsprofile, Zugriffsmatrix, Bankreferenz-Identität, Präzision, Freigabe-Snapshots, Migrationsjournal, Feldumbenennungen, Beiratsprüfung, berechnete OP). Anhang E in Entscheidungstabelle umgewandelt, Abschnitt 18.0 und 19 angepasst, Gedankenstriche entfernt. Fachliche Inhalte des Reviews 1.1.2 (Abschnitt 7, Anhänge C und D, Abschnitte 10, 11, 13, 14) inhaltlich übernommen.
- 1.1.2-Fachreview (23.09.2026): Fachliche Überarbeitung auf Basis 1.1.1; rechtliche Anwendungsgrenzen, getrennte WEG-Beschluss-/Abrechnungslogik, Belegprüfungsraum, Einsicht, Finanzmigration, Steuer-/Aufbewahrungsprofile, datierte Quellen, Abnahmefälle und Claude-Konfliktprüfung. Architektur-/Schemaabschnitte 2–6, 8, 9, 12 und 17 textlich unverändert. Prüfstand ohne Implementierungs-/Produktivfreigabe.

- 1.0 (23.09.2026): Erstfassung auf Basis der Immoware24-Strukturanalyse, des Anforderungskatalogs und der Marktrecherche.
- 1.1.1 (23.09.2026): Abschnitt 19 neu gefasst als Startvoraussetzungen V1 bis V14 mit Status, Startanweisung und Versionsplanung.
- 1.1 (23.09.2026): Domains korrigiert (crm.mueller-holding.ag, portal.muellerhv.de, portal.mueller-holding.ag), Modellstufen und Kostenoptimierung (9.3), Regel 13 Wirtschaftlichkeit, allgemeiner Upload (11.4), Bestandstools mit Projektnamen (13.4), Anhang B Erhebungsprompt.
