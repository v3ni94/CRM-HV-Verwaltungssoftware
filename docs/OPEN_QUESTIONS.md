# Offene Fragen an den Betreiber

Stand: 23.09.2026. Grundlage: `docs/MASTER-PROMPT.md` (Version 2.0 Final), Abschnitt 0.1 Regel 3, Abschnitt 19.1, Anhang C.2 und Anhang E. Zu Beginn jeder Sitzung prüft der Coding-Agent den Status der für die Aufgabe relevanten Punkte (Abschnitt 19.1). Eine Konfiguration gilt nicht als Klärung. Kritische rechtliche, finanzielle oder datenschutzrechtliche Fragen sperren die betroffene produktive Aktion; an anderen Aufgaben wird weitergearbeitet.

Die Spalte „Vorschlag“ enthält nur Vorschläge, die der Master-Prompt selbst macht. Wo er keinen macht, steht „Vorschlag folgt nach Sichtung“. Wo der Master-Prompt keine Person benennt, steht „Betreiber (laut Abschnitt 19.1)“.

## 1. Startvoraussetzungen V1 bis V23 (Abschnitt 19.1)

| Nr | Punkt | Wofür nötig / betroffene Freigabe | Zuständigkeit | Vorschlag | Status | zuletzt geprüft |
| --- | --- | --- | --- | --- | --- | --- |
| V1 | Dossiers der sechs Bestandsprojekte (Müller FLOW, Immoware Hub Integrationsplattform, Mail optimierung, Übergabeprotokoll, Objektakte, smart-einzug) nach Anhang B, abgelegt unter `docs/integrations/<tool>.md` | Abschnitt 13, Entscheidung anbinden, übernehmen, ablösen; Version 1.2 dieses Prompts | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V2 | Bankliste: alle Konten der Mandanten HVM und Timo Müller mit Bank, BIC, Kontotyp (Miet-, WEG-, Rücklagen-, Kautions-, Geschäftskonto), geplantem Konnektor; Anfrage bei den Hauptbanken zu EBICS-Verträgen (Vorlauf mehrere Wochen) | Phase 2, M11 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V3 | Entscheidung Aggregator (finAPI, GoCardless Bank Account Data oder Alternative) nach Angebot und Auftragsverarbeitungsvertrag | M11 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V4 | Produktname und Marke (ersetzt Arbeitstitel MH Verwaltungsplattform), Domains für Fremdmandanten | Branding, Repo-Name, Login-Seiten | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V5 | Entwicklungsmodell: eigene Entwickler, externe Agentur oder Hybrid; daraus Aufwands- und Kostenschätzung je Phase | Planung, Budget | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V6 | Tatsächlichen Immoware24-Vertrag einschließlich Kündigung, Laufzeit, Export und Nutzungsgrenzen prüfen; öffentlich behauptete Standardfristen sind kein Beleg für den konkreten Vertrag. Ablösetermin aus bestätigten Unterlagen ableiten | Migrationsplan, Parallelbetrieb | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V7 | Mahnstufen, Gebühren, Verzugszinsregeln je Mandant, rechtlich geprüft | M16 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V8 | Kontenrahmen: Übernahme der Immoware24-Konten der HVM als Startvorlage, Bezeichnungen eigenständig formuliert | M10 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V9 | Migrationsstichtag je Objekt und Dauer des Parallelbetriebs | M8, Phase 2 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V10 | Auftragsverarbeitungsverträge mit Anthropic, OpenAI, Aggregator, Briefdienst; Bestätigung, dass keine Trainingsnutzung erfolgt | M7, M11, M23 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V11 | Google-Workspace-Konto und internes Cloud-Projekt je Mandant für die Drive-Anbindung; Paperless-Token je Mandant | M6 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen (HVM: ablage@muellerhv.de vorhanden) | 23.09.2026 |
| V12 | Steuerberater: E-Rechnungs-Ausstellungspflicht je Mandant (Umsatzgrenze, Startzeitpunkt), DATEV-Parameter (Berater-, Mandantennummer, Kontenlänge) | M13, M18 | Betreiber (laut Abschnitt 19.1) mit Steuerberater | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V13 | Rechtsanwalt: BFSG-Anwendbarkeit auf das Portal, WEG-Recht für virtuelle Versammlung und Umlaufbeschluss im Portal, GoBD-Verfahrensdokumentation | M21, M25 | Betreiber (laut Abschnitt 19.1) mit Rechtsanwalt | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V14 | Freigabe der CI-Werte je Mandant aus den tatsächlich verfügbaren Quellen hvm-ci, mhag-ci, tm-privat-ci; fehlende Quellen nicht durch erfundene Werte ersetzen | M2 Seeds | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V15 | Je Pilot-WEG: Teilungserklärung/Gemeinschaftsordnung, geltende Verteilungsschlüssel, Wirtschaftspläne, Sonderumlagen, maßgebliche Beschlüsse und Eigentümernachweise | G0/G4, W01 bis W13 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V16 | Verantwortliche fachkundige Person für unabhängige Buchungs-/Abrechnungssollwerte und Abnahme; Rechts-/Steuerprüfung bei Zweifelsfragen | G1/G3/G4 | Betreiber (laut Abschnitt 19.1), benennt die fachkundige Person | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V17 | Anwendbarkeits- und Aufbewahrungsmatrix je Rechtsträger, Unterlagenklasse, Frist und Sperrgrund; Belegeinsichtsverfahren auch ohne Portal | G1/G3/G4/G5 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V18 | Bank-/Zahlungsvollmachten, Rollen, Limits, zulässige Mandatsverfahren, Empfängerdatenkontrolle, Freigabeverfahren | G2 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V19 | Unterjährige Übernahme: belegte vollständige Jahresdaten und Überleitungsplan statt nur Anfangssalden | M8/M10/G3/G4 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V20 | Anhang-E-Entscheidungen (Rechtsträger-Buchungskreise, Zeit- und Statusmodell) | G0 | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | entschieden in Version 2.0, Bestätigung mit Startauftrag | 23.09.2026 |
| V21 | Steuerlicher Status und relevante Sonderfälle je GdWE/Eigentümer/Mandant; Prüfzuständigkeit für Umsatzsteuer, Bauleistungen und § 35a | M13 bis M18/G4 | Betreiber (laut Abschnitt 19.1), Prüfzuständigkeit ist Teil des Punkts | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V22 | Anonymisierte repräsentative Originalbelege, Vertrags-/Eigentümerwechsel, Rücklastschriften, Kostenverteilungen und Abrechnungen als freigegebene Testfälle | Anhang D | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| V23 | Quellen- und Aktualitätslücken P01 bis P05 aus Anhang C schließen; Rechtsstand zum jeweiligen Anwendungszeitpunkt belegen | betroffene Freigabe | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |

## 2. Quellen- und Prüflücken P01 bis P05 (Anhang C.2)

Offen über V23. Keine erfundenen Quellen, Aktenzeichen oder Freigaben ergänzen.

| Nr | Punkt | Wofür nötig / betroffene Freigabe | Zuständigkeit | Vorgehen bis zur Klärung | Vorschlag | Status | zuletzt geprüft |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | Aktuelle Rechtsprechung zu WEG-Abrechnungsspitze, Eigentümerwechsel und Sondernachfolgerhaftung; insbesondere BGH 02.12.2011, V ZR 113/11 und BGH 09.03.2012, V ZR 147/11 sowie Fortgeltung im heutigen §-28-System | G4, Fälle D01, D15; Blockerklasse vor Miet-/WEG-Abrechnung | Betreiber (laut Abschnitt 19.1), fachkundige Person nach V16 | Keinen vollständig verifizierten amtlichen Rechtsprechungsabgleich behaupten. Regelfälle fachlich gegenprüfen; Sonderfälle bis Freigabe nicht automatisieren. | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| P02 | WEG-Geldfluss-/Heizkostenüberleitung, u. a. BGH 17.02.2012, V ZR 251/10, sowie Folgen späterer Beschlusskorrektur/gerichtlicher Ungültigkeit | G4, Fall D09 | Betreiber (laut Abschnitt 19.1), fachkundige Person nach V16 | Vor G4 vollständigen aktuellen fachlichen Regelstand und Testfall freigeben. Keine erfundenen Aktenzeichen zu neueren Entscheidungen ergänzen. | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| P03 | Vollständige aktuelle GoBD-Fassung, einschlägige USt-Anwendungsregeln, mögliche §-15a-Berichtigungsfälle, §-35a-WEG-Bescheinigung/zeitliche Zuordnung, weitere Bauabzugsteuerregeln | G1, G3, G4; M13 bis M18 | Rechts-/Steuerverantwortliche (laut Anhang C.2) | Rechts-/Steuerverantwortliche bestätigen Anwendbarkeit und Sollfälle. Spezialautomatiken bleiben bis dahin aus. | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| P04 | Konkrete Miet-, WEG-, Bank-, DMS-, Dienstleister- und Betreiberverträge; AVV-/Verantwortlichkeitslage, Portal/BFSG-Anwendbarkeit und gegebenenfalls weitere Vermarktungs-/KI-Pflichten | G5, Marktstart; M21 | Betreiber (laut Abschnitt 19.1) | Nur tatsächliche Unterlagen auswerten. Fehlende Verträge/Bestandsdossiers bleiben offene Voraussetzungen; keine Branchenannahmen als Tatsachen. | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| P05 | Aktuelle Bank-/SEPA-Scheme- und Formatspezifikationen, EBICS-Auftrags-/BTF-Varianten, zulässige Mandatsverfahren, Vorabinformation, Rückgaben, Empfängerprüfung sowie aktuelle DATEV-/Messdienst-/E-Rechnungsformate | G2, Marktstart; M11, M15, M18 | Coding-Agent anhand des gewählten Anbieters (laut Anhang C.2), Spezifikationen vom Betreiber | Prüfung anhand des konkret gewählten Anbieters und verbindlicher Spezifikationen. Die Architektur/Adapterauswahl wird nicht verändert. Keine Aussage „heutige Bankformate geprüft“, solange keine passenden Spezifikationen und Testdateien vorliegen. | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |

## 3. Blockerklassen (Anhang E, Schluss)

| Blockerklasse | Punkte | Status | zuletzt geprüft |
| --- | --- | --- | --- |
| vor abhängiger Datenmodellentscheidung | keine offen | erledigt laut Version 2.0 | 23.09.2026 |
| vor produktiver Finanzfunktion | V2, V3, V7, V8, V16, V18, V19, V21 | offen | 23.09.2026 |
| vor Miet-/WEG-Abrechnung | V15, V22, V23, P01 bis P03 | offen | 23.09.2026 |
| vor Marktstart | V4, V5, V13, V17, P04, P05 | offen | 23.09.2026 |

## 4. Neue Punkte aus Meilenstein M1

| Nr | Punkt | Wofür nötig / betroffene Freigabe | Zuständigkeit | Vorschlag | Status | zuletzt geprüft |
| --- | --- | --- | --- | --- | --- | --- |
| M1-01 | Objektspeicher für Produktion (ADR 0005). MinIO Community Edition ist archiviert, Images auf Docker Hub sind nicht mehr verfügbar. Entscheidung zwischen einer gepflegten S3-kompatiblen Alternative (der Entwicklungsstack nutzt SeaweedFS 4.47), einem selbst gebauten MinIO aus Quelltext oder einem verwalteten S3-Dienst in der EU | M6 und Produktivbetrieb; Aufbewahrungsprofile E05 | Betreiber (laut Abschnitt 19.1) | Bewertung nach den Kriterien in ADR 0005; bis zur Entscheidung keine Produktivdaten | offen | 23.09.2026 |
| M1-02 | Vorhandener Traefik auf dem IONOS-Server: Name des externen Docker-Netzwerks, Entrypoint, Name des Cert-Resolvers, vorhandene Middlewares. `compose.prod.yaml` erwartet `TRAEFIK_NETWORK`, `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER` | Staging und Produktion (M9) | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| M1-03 | Container-Registry: GitHub Container Registry oder lokale Registry (Abschnitt 4.3 lässt beides offen) | Deploy (M9) | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| M1-04 | CI-Plattform: angenommen GitHub Actions, weil das Repository auf GitHub liegt (Abschnitt 4.3 nennt alternativ Gitea Actions); siehe A-002 | M1 | Betreiber (laut Abschnitt 19.1) | GitHub Actions (Abschnitt 4.3, solange das Repository auf GitHub liegt) | Annahme, Bestätigung offen | 23.09.2026 |
| M1-05 | Repository-Name: Das Repository heißt CRM-HV-Verwaltungssoftware, der Codename laut Pflichtenheft ist `mhvp`. Eine Umbenennung hängt an V4 | Branding, Repo-Name | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| M1-06 | DNS-Einträge für crm.mueller-holding.ag, api.mueller-holding.ag, portal.muellerhv.de, portal.mueller-holding.ag und die staging-Subdomains über die IONOS-Nameserver | Staging und Produktion (M9) | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
| M1-07 | Entwicklungsumgebung Claude Code: Die Netzwerkrichtlinie der Cloud-Umgebung blockiert Downloads von Docker Hub (Host production.cloudfront.docker.com, 403). Folge: `make dev` konnte in der Build-Umgebung nicht vollständig gestartet werden | Abnahme M1 („`make dev` startet alles“) | Betreiber (laut Abschnitt 19.1) | In den Umgebungseinstellungen den Netzwerkzugriff erweitern oder den Host freigeben | offen | 23.09.2026 |
| M1-08 | CI-Werte der Produktoberfläche (crm.mueller-holding.ag im CI der Müller Holding AG): Freigabe der Werte aus mhag-ci, gehört zu V14. Bis dahin neutrale Tokens | M2 Seeds, Oberfläche | Betreiber (laut Abschnitt 19.1) | Vorschlag folgt nach Sichtung | offen | 23.09.2026 |
