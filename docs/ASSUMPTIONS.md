# Annahmen

Stand: 29.09.2026 (A-089 ergänzt; A-084 bis A-088 ergänzt; zuvor A-080 ergänzt; zuvor 28.09.2026 mit A-074 bis A-079; zuvor 26.09.2026 mit A-048, A-049 und A-052). Grundlage: `docs/MASTER-PROMPT.md`, Abschnitt 0.1 Regel 3.

Hier stehen nur unkritische Annahmen, die den Entwurfsbetrieb ermöglichen. Keine dieser Annahmen berührt Geld, Forderungsbestand, Datenschutz, gesetzliche Fristen oder Beweiserhalt. Solche Punkte wären nach Regel 3 offene Fragen und stehen in `docs/OPEN_QUESTIONS.md`. Jede Annahme wird spätestens beim genannten Meilenstein überprüft und bei Bestätigung oder Widerlegung hier fortgeschrieben.

## A-001

| Feld | Inhalt |
| --- | --- |
| Annahme | Das Wurzelverzeichnis dieses Repositorys (CRM-HV-Verwaltungssoftware) ist die Wurzel `mhvp/` des Monorepos nach Abschnitt 17. |
| Begründung | Das Repository existiert bereits auf GitHub; ein zusätzliches Unterverzeichnis `mhvp/` brächte keinen Nutzen. Der Name selbst ist offen (M1-05, V4). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | gesamtes Repository, Pfade in Dokumentation und CI |
| Überprüfung spätestens bei Meilenstein | M2 |
| Datum | 23.09.2026 |

## A-002

| Feld | Inhalt |
| --- | --- |
| Annahme | CI läuft auf GitHub Actions. |
| Begründung | Abschnitt 4.3 nennt GitHub Actions und Gitea Actions nur für den Fall, dass das Repository dort liegt; das Repository liegt auf GitHub (M1-04). |
| Kennzeichnung | bestätigt durch Betreiberentscheidung 26.09.2026 (M1-04); Images werden ebenfalls dort gebaut und in die GitHub Container Registry `ghcr.io/v3ni94` geschoben (M1-03) |
| Betroffene Bereiche | `.github/workflows` (`ci.yml`, `images.yml`), Pinning nach ADR 0001 |
| Überprüfung spätestens bei Meilenstein | erledigt (M9, 26.09.2026); erneut nur bei Wechsel der Repository-Plattform |
| Datum | 23.09.2026, bestätigt 26.09.2026 |

## A-003

| Feld | Inhalt |
| --- | --- |
| Annahme | psycopg 3 ist der einzige Datenbanktreiber, asynchron für die API, synchron für Worker und Alembic. |
| Begründung | Ein Treiber verringert Abweichungen im Verhalten von Transaktionen und `set_config` (ADR 0001, ADR 0002). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | api, worker, Migrationen |
| Überprüfung spätestens bei Meilenstein | M2 |
| Datum | 23.09.2026 |

## A-004

| Feld | Inhalt |
| --- | --- |
| Annahme | Technische Dokumentation (ADR, Runbooks, README, Agentenregeln, Regelregister) ist auf Englisch; Betreiber- und Fachdokumente sind auf Deutsch. |
| Begründung | Abschnitt 0.1 Regel 10. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `docs/`, `README.md`, `CLAUDE.md`, `AGENTS.md` |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-005

| Feld | Inhalt |
| --- | --- |
| Annahme | Entwicklungshostnamen sind `crm.localhost`, `portal.localhost` und `api.localhost`. |
| Begründung | `*.localhost` löst ohne DNS-Eintrag lokal auf; die Produktionsdomains aus Abschnitt 3.3 werden dadurch nicht berührt. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `infra/compose.dev.yaml`, Traefik (nur Entwicklung) |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-006

| Feld | Inhalt |
| --- | --- |
| Annahme | Produktion nutzt den vorhandenen Traefik auf dem IONOS-Server über ein externes Docker-Netzwerk; es wird kein zweiter Traefik gestartet. |
| Begründung | Abschnitt 3.1: Traefik ist bereits vorhanden und terminiert TLS für alle Dienste der Müller-Gruppe. Netzwerkname, Entrypoint und Cert-Resolver sind offen (M1-02). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `infra/compose.prod.yaml` |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-007

| Feld | Inhalt |
| --- | --- |
| Annahme | Die Freigabestufen G1 bis G5 sind je Mandant geschlossen; es gibt keinen globalen Schalter und keine Umgebungsvariable zum Öffnen. Die Speicherung je Mandant folgt mit M2. |
| Begründung | Abschnitt 0.1 Regel 1, Abschnitt 18.0, Abschnitt 19.2; ADR 0003. Die Annahme betrifft nur den zeitlichen Ablauf der Persistenz, nicht die Sperrwirkung. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `mhvp.core.release_gates`, API, Jobs |
| Überprüfung spätestens bei Meilenstein | M2 |
| Datum | 23.09.2026 |

## A-008

| Feld | Inhalt |
| --- | --- |
| Annahme | Zeitstempel werden in UTC gespeichert (`TIMESTAMPTZ`); die Oberfläche zeigt Zeitstempel in der Zeitzone Europe/Berlin an. Fachliche Fristen (Fälligkeiten, Fristende, Zugang) werden in Europe/Berlin berechnet (Betreiberentscheidung 26.09.2026, M1-09). |
| Begründung | Abschnitt 4.1 legt UTC fest; die Anzeige betrifft nur die Darstellung. Der Kalendertag einer Frist ist der Tag in Europe/Berlin; welche Frist gilt, folgt weiterhin nur aus freigegebenen Regeln. |
| Kennzeichnung | bestätigt 26.09.2026; die Zeitzone ist je Modul fest hinterlegt (Celery `Europe/Berlin`, `workspace.services.local_today`, `automation.schedule.SCHEDULE_TZ`, SLA-Kalender), eine zentrale Einstellung gibt es nicht. Stellen, die noch den UTC-Kalendertag nutzen, sind in M1-09 aufgelistet und in einem eigenen Schritt umzustellen |
| Betroffene Bereiche | api, worker (Celery in Europe/Berlin, Speicherung UTC), Oberfläche |
| Überprüfung spätestens bei Meilenstein | bei der Umstellung der in M1-09 gelisteten Stellen |
| Datum | 23.09.2026, bestätigt 26.09.2026 |

## A-009

| Feld | Inhalt |
| --- | --- |
| Annahme | Paketverwaltung mit pnpm Workspaces (Node) und uv (Python). |
| Begründung | Beide erzeugen Lockfiles, die E16 verlangt (ADR 0001). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Monorepo, CI, Container-Builds |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-010

| Feld | Inhalt |
| --- | --- |
| Annahme | SeaweedFS 4.47 dient nur als S3-kompatibler Objektspeicher für Entwicklung, CI und e2e. Produktion und Staging nutzen seit der Entscheidung M1-01 (26.09.2026) IONOS S3 Object Storage, ohne Objektspeicher-Container im Stack. |
| Begründung | MinIO-Images sind auf Docker Hub nicht mehr verfügbar (laut ADR 0005, Prüfstand 23.09.2026). Die Anwendung nutzt nur die S3-API, deshalb ist der Wechsel zwischen SeaweedFS (dev) und IONOS S3 (prod) reine Konfiguration (`MHVP_S3_*`). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb; für Produktion durch Betreiberentscheidung ersetzt (ADR 0005 Nachtrag 26.09.2026) |
| Betroffene Bereiche | `infra/compose*.yaml`, `MHVP_S3_*`, `docs/runbooks/objektspeicher-ionos-s3.md` |
| Überprüfung spätestens bei Meilenstein | M6 (Object Lock je Aufbewahrungsprofil) |
| Datum | 26.09.2026 (zuvor 23.09.2026) |

## A-011

| Feld | Inhalt |
| --- | --- |
| Annahme | Next.js 15 bleibt, obwohl neuere Hauptversionen existieren. |
| Begründung | Abschnitt 4.2 legt Next.js 15 fest; der Stack wird nicht eigenmächtig geändert (Anhang E, Einleitung). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | web-crm, web-portal |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-012

| Feld | Inhalt |
| --- | --- |
| Annahme | Passwortregel: Länge 6 bis 128 Zeichen, keine Zusammensetzungsregeln, keine Leerzeichen am Anfang oder Ende; Kontosperre nach 10 Fehlversuchen für 15 Minuten. Zweiter Faktor (TOTP) freiwillig je Benutzer, gemerkte Geräte 90 Tage. |
| Begründung | Abschnitt 3.4 verlangt Passwortregeln nach BSI-Empfehlung und eine Kontosperre, nennt aber keine Werte. Ursprüngliche Annahme (23.09.2026): 12 Zeichen. Betreiberentscheidung 26.09.2026 (M2-01): Mindestlänge 6 Zeichen. Hinweis: 6 Zeichen liegen unter den üblichen Empfehlungen, das BSI empfiehlt längere Passwörter; die Entscheidung liegt beim Betreiber und wird in der Oberfläche nicht kommentiert. |
| Kennzeichnung | Betreiberentscheidung, keine Annahme mehr (M2-01 entschieden 26.09.2026); Prüfung gegen kompromittierte Passwörter offen (M2-09) |
| Betroffene Bereiche | Anmeldung |
| Überprüfung spätestens bei Meilenstein | M9 (vor Produktivbetrieb) |
| Datum | 23.09.2026 |

## A-013

| Feld | Inhalt |
| --- | --- |
| Annahme | Vertragsnummern sind sechsstellig mit führenden Nullen, fortlaufend je Mandant über alle Objekte; eine Vertragsversion behält die Nummer. Debitorenkonten erhalten je Rechtsträger fortlaufend Nummern ab 090000 bis 099999. |
| Begründung | Abschnitt 6.3 nennt `number` ohne Format. Der Debitorenbereich 090000 bis 099999 und das Kontoformat stammen aus Abschnitt 7.2 und Anhang A.1; Debitor je Partei und Einheit aus 6.9.2 (E02). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Verträge, später Buchhaltung (M10) |
| Überprüfung spätestens bei Meilenstein | M10 |
| Datum | 23.09.2026 |

## A-014

| Feld | Inhalt |
| --- | --- |
| Annahme | Ein SEPA-Firmenlastschriftmandat (B2B) wird nur erfasst, wenn alle Beteiligten der Vertragspartei als Unternehmen erfasst sind. Das Mandat braucht einen Nachweis (Dokument) und ein Konto eines Beteiligten. |
| Begründung | Produktschutz: Das Firmenlastschriftverfahren ist nicht für Verbraucher gedacht; die genaue Abgrenzung ist keine hier geprüfte Rechtsquelle. Einzug bleibt bis G2 gesperrt. |
| Kennzeichnung | Produktschutz, unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | SEPA-Mandate |
| Überprüfung spätestens bei Meilenstein | M12 (vor G2) |
| Datum | 23.09.2026 |

## A-015

| Feld | Inhalt |
| --- | --- |
| Annahme | Gläubiger eines Mietverhältnisses ist im Mietobjekt der zum Mietbeginn eingetragene Eigentümer, bei WEG mit SEV der Eigentümer der Einheit mit aktivem SEV-Eigentumsverhältnis; Gläubiger des Eigentumsverhältnisses ist die GdWE. Reine WEG-Objekte führen keine Mietverhältnisse (M5-03; Betreiberentscheidung 26.09.2026: Ablehnung bestätigt). |
| Begründung | Abschnitt 6.9.1 und 6.9.11: Forderungen gehören dem richtigen Rechtsträger, die Verwaltung ist nicht automatisch Gläubiger. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Verträge, Debitoren |
| Überprüfung spätestens bei Meilenstein | M10 |
| Datum | 23.09.2026 |

## A-016

| Feld | Inhalt |
| --- | --- |
| Annahme | Uploads bis 50 MB je Datei (`MHVP_DOCUMENT_MAX_BYTES`), zulässige Typen: PDF, JPEG, PNG, TIFF, HEIC, Text, CSV, XML, E-Mail, Office-Formate, ZIP. Der Inhalt muss zum angegebenen Typ passen (Signaturprüfung). Originale werden unverändert gespeichert; ein Duplikat (gleicher SHA-256) wird angezeigt, nicht abgewiesen. |
| Begründung | Abschnitt 6.7 und 11 nennen keine Grenzwerte. Unverändertes Original folgt aus 11.3 und D43. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Dokumente |
| Überprüfung spätestens bei Meilenstein | M11 (Belegeingang) |
| Datum | 23.09.2026 |

## A-017

| Feld | Inhalt |
| --- | --- |
| Annahme | Standardkategorien je Mandant sind die Dokumenttypen aus 11.4 zuzüglich Legitimationsunterlage. Zuordnung zu den Drive-Unterordnern: Rechnung und Abrechnung zu 03_Buchhaltung, Vertrag, Protokoll, Versicherung und Teilungserklärung zu 02_Stammakte, Legitimationsunterlage zu 01, übrige zu 06_Sonstiges. Mieter- und Eigentümerakte (04, 05) werden noch nicht automatisch gewählt. |
| Begründung | 11.2 legt die Ordnerstruktur fest, nicht die Zuordnung der Kategorien. |
| Kennzeichnung | unkritisch, je Mandant änderbar |
| Betroffene Bereiche | Dokumente, Drive-Spiegel |
| Überprüfung spätestens bei Meilenstein | M11 |
| Datum | 23.09.2026 |

## A-018

| Feld | Inhalt |
| --- | --- |
| Annahme | Briefe nach DIN 5008 Form B mit Briefbogen aus den Mandanteneinstellungen: Farbband (`letter_band`) oder Akzentlinie, Falz- und Lochmarken, Absenderzeile, Anschriftfeld, Infoblock, Fußzeile mit Firmen- und Registerangaben. Unterschriftsbilder werden nicht eingesetzt. Die Anrede wird nur aus erfasster Anrede und Nachname gebildet, sonst „Sehr geehrte Damen und Herren,". Das Briefdatum richtet sich nach Europe/Berlin. |
| Begründung | Briefbogen je Mandant laut M6 (Abschnitt 18); Kennlinie der HVM aus dem Skill hvm-ci; Pflichtangaben kommen aus den Firmendaten (V14). Kein Erraten von Geschlecht oder Titeln. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb; Versand erst mit M13 |
| Betroffene Bereiche | Briefe, Serienbriefe |
| Überprüfung spätestens bei Meilenstein | M13 |
| Datum | 23.09.2026 |

## A-019

| Feld | Inhalt |
| --- | --- |
| Annahme | Ein KI-Anbieter ist nur nutzbar, wenn AVV unterschrieben (mit Dokument), Trainings-Opt-out bestätigt, API-Schlüssel, Monatsbudget über 0 und Preise je Stufe hinterlegt sind und eine zweite Person freigegeben hat. Jede Änderung hebt die Freigabe auf. Kosten werden mit allen Eingabetoken zum Eingabepreis gerechnet (Obergrenze, auch bei Cache-Treffern). Bei erreichtem Budget ist jeder weitere Lauf gesperrt. |
| Begründung | Regel 0.1.13 und 9.1 (AVV als Pflichtfeld, harte Sperre); Produktschutz für die Freigabe. Preise nicht erfunden, sondern vom Betreiber einzutragen. |
| Kennzeichnung | Produktschutz, unkritisch |
| Betroffene Bereiche | KI-Gateway |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-020

| Feld | Inhalt |
| --- | --- |
| Annahme | Übernahmen aus KI-Vorschlägen: Kontakte je mit eigener Vertragspartei; Objekte im Status onboarding; Verträge nur mit Beginn aus den Unterlagen (bei Eigentum zugleich Eigentumsübergang, zur Prüfung); Zahlungen nur mit vom Nutzer bestätigtem Steuersatz. Rückgängig entfernt nur, was nicht später verknüpft oder geändert wurde; Kontakte werden weich gelöscht. |
| Begründung | 10.1 und 10.2; keine Teilanlage ohne Nutzeraktion; keine erfundenen Daten oder Steuerbehandlung (S01). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Onboarding, Import |
| Überprüfung spätestens bei Meilenstein | M10 |
| Datum | 23.09.2026 |

## A-021

| Feld | Inhalt |
| --- | --- |
| Annahme | Import aus Immoware24: Zuordnung über Objektnummer, Einheitennummer und die Kontakt-ID des Altsystems (`external_ids.immoware24`). Vorhandene Datensätze werden nie überschrieben (unverändert oder Konflikt zur Prüfung). Bankverbindungen aus dem Adressbuch gelten ab dem Importtag, weil der Export kein Gültigkeitsdatum trägt. Zahlungen brauchen einen Steuersatz aus der Datei; netto wird daraus gerechnet. Objektnummern werden nicht aufgefüllt (aus 7 wird nicht 007). |
| Begründung | 13.1: Mapping versioniert, unbekannte Spalten manuell zuordnen; keine erfundenen Daten. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Import |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-022

| Feld | Inhalt |
| --- | --- |
| Annahme | Arbeitsplatzfunktionen (Benachrichtigungen, Kalender, gespeicherte Filter) sind je Benutzer und Mandant getrennt. Geteilte Termine sieht jedes Mitglied des Mandanten. Die Erinnerung an Wartungen geht an den im Objekt hinterlegten Objektbetreuer, standardmäßig 14 Tage vor Fälligkeit, wenn keine Vorlaufzeit gesetzt ist. Massenaktionen betreffen nur Stammdaten ohne Geldwirkung (Schlagworte, Wartung erledigt) und laufen ganz oder gar nicht. |
| Begründung | Abschnitt 3.5 und 18 (M9): Dashboard, Benachrichtigungen, Kalender, Listenfilter, Massenaktionen; Regel 0.1.4 für Massenaktionen. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Arbeitsplatz, Wartung |
| Überprüfung spätestens bei Meilenstein | M19 |
| Datum | 23.09.2026 |

## A-023

| Feld | Inhalt |
| --- | --- |
| Annahme | Kontenrahmen-Entwurf nach Anhang A.1: Kategorie und Typ je Konto aus den Nummernbereichen in 7.2 abgeleitet (zum Beispiel 001400 Überzahlungen aus Vorjahren als technisches Passivkonto, 009000 Anfangsbestand als Passivkonto, 026000 Vorsteuerrückerstattungen als Steuerertrag). Konten mit dem Zusatz WEG oder Rücklage nur für GdWE-Buchungskreise. Geschäftsjahr wird mit dem Kalenderjahr seines Beginns bezeichnet. |
| Begründung | V8 offen; Vorlage bleibt bis zur Freigabe als Entwurf gekennzeichnet. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Buchhaltung |
| Überprüfung spätestens bei Meilenstein | G1 |
| Datum | 23.09.2026 |

## A-024

| Feld | Inhalt |
| --- | --- |
| Annahme | Bankumsatz-Identität: Bankreferenz ist AcctSvcrRef, ersatzweise NtryRef oder TxId aus CAMT. Umsätze ohne jede Referenz mit gleichem Inhalt kommen in die Prüfung und werden nie verworfen. Interne Umbuchung wird verknüpft, wenn die Gegen-IBAN ein eigenes Konto desselben Rechtsträgers ist, der Betrag entgegengesetzt gleich ist und die Buchungstage höchstens 5 Tage auseinanderliegen. Vorgemerkte Umsätze (Status nicht BOOK) werden nicht übernommen. |
| Begründung | 6.9.7, D04, D05; Zeitfenster als Produktstandard, nur Verknüpfung ohne Buchung. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Bank |
| Überprüfung spätestens bei Meilenstein | M12 |
| Datum | 23.09.2026 |

## A-025

| Feld | Inhalt |
| --- | --- |
| Annahme | Automatische Buchung nur, wenn Mandant freigeschaltet, eine aktive Regel (von einer zweiten Person freigegeben, mit Betragsgrenze und Testnachweis) passt und genau ein Kandidat mit mehr als IBAN- und Betragsindiz den offenen Posten vollständig ausgleicht. Teil-, Sammel- und Überzahlungen, Fremdzahler und Umbuchungen bleiben manuell. Überzahlungen verbleiben als Guthaben auf dem Personenkonto. |
| Begründung | 7.4 Nr. 2 und 4, 6.9.4, D07. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Bank, Buchhaltung |
| Überprüfung spätestens bei Meilenstein | G1 |
| Datum | 23.09.2026 |

## A-026

| Feld | Inhalt |
| --- | --- |
| Annahme | Sollstellungslauf: Vorschau speichert einen Hash der Grundlagen; Buchen erstellt nur die bereiten Positionen und nur, wenn der Hash unverändert ist. Je Vertrag, Zahlungsart und Monat höchstens eine gebuchte Position (Datenbank-Eindeutigkeit). Buchungstag der Sollstellung ist der Fälligkeitstag. Negative Beträge (Mietminderung) werden nicht automatisch gebucht. |
| Begründung | 7.3 Sollstellung, 7.5, B08. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Sollstellung |
| Überprüfung spätestens bei Meilenstein | G1 |
| Datum | 23.09.2026 |

## A-027

| Feld | Inhalt |
| --- | --- |
| Annahme | Rechnungen in Buchungskreisen ohne Umsatzsteueroption werden mit dem Bruttobetrag als Kosten gebucht. Schlussrechnungen buchen nur die verbleibende Wirkung nach Abzug gebuchter Abschläge desselben Ausstellers. Kreditorenkonten werden je Aussteller ab 070000 fortlaufend angelegt. Skonto wird erst bei Zahlung berücksichtigt; der offene Posten bleibt bis dahin in voller Höhe. |
| Begründung | 7.2, 7.3 Eingangsrechnung und Abschlag/Schlussrechnung, D12. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Rechnungseingang |
| Überprüfung spätestens bei Meilenstein | G1 |
| Datum | 23.09.2026 |

## A-028

| Feld | Inhalt |
| --- | --- |
| Annahme | Zahlungsauftrag nur aus gebuchter, freigegebener Rechnung mit bestätigter IBAN, vom Konto desselben Rechtsträgers, nie vom Kautionskonto. Skonto wird bei Ausführung bis zum Skontodatum abgezogen und bei Ausführung gegen Konto 027000 gebucht. Ausführung gilt nur mit importiertem Bankumsatz als Nachweis; Teilbelastung gleicht teilweise aus; Rückgabe storniert die Zahlungsbuchung. |
| Begründung | 7.5 Zahllauf, 6.9.9, D06; Konto 027000 aus Anhang A.1. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Zahllauf |
| Überprüfung spätestens bei Meilenstein | G2 |
| Datum | 23.09.2026 |

## A-029

| Feld | Inhalt |
| --- | --- |
| Annahme | Mahnvorschau: überfällige offene Forderungen je Personenkonto; nächste Stufe ist die zuletzt versandte Stufe plus eins, wenn die älteste Fälligkeit die Mindesttage erreicht. Ausgeschlossen mit Grund: fehlende Stufen, Mahnsperre, Betrag unter Mahngrenze, höchste Stufe erreicht, Buchungskreis nicht führend. Freigabe nur durch eine zweite Person und nur, wenn alle vorgeschlagenen Fälle im führenden System liegen. Der Job am 5. erzeugt nur Vorschauen. |
| Begründung | 7.5 Mahnwesen, 6.9.10 D52, 13.1, 15.1. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Mahnwesen |
| Überprüfung spätestens bei Meilenstein | G1 |
| Datum | 23.09.2026 |

## A-030

| Feld | Inhalt |
| --- | --- |
| Annahme | Nutzerwechsel und Leerstand: Kosten mit Umlageschlüssel werden nach Schlüsselwert mal Tagen je Nutzungszeitraum verteilt; Leerstandszeiträume erhalten ihren Anteil, der beim Eigentümer bleibt. Heizkosten werden nicht tageweise verteilt, sondern nur aus externen Einzelbeträgen übernommen. Restcents nach dem Verfahren des größten Rests, bei Gleichstand nach Einheitennummer und Nutzerschlüssel. |
| Begründung | A05, 6.9.8, D08. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Betriebskostenabrechnung |
| Überprüfung spätestens bei Meilenstein | G3 |
| Datum | 23.09.2026 |

## A-031

| Feld | Inhalt |
| --- | --- |
| Annahme | Tickets erhalten fortlaufende Nummern je Mandant, Routing und Checkliste aus der Vorlage der Kategorie, SLA aus der Vorlage oder sonst aus der Priorität. Aufträge durchlaufen Entwurf, Anfrage, Angebot, Freigabe, Termin, Ausführung, Rechnung, Abnahme; ein Angebot über dem Budget sperrt die Freigabe. Verknüpfte Rechnungen durchlaufen unverändert die Rechnungsprüfung (M14). |
| Begründung | 6.6, 18 M19. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Tickets, Aufträge |
| Überprüfung spätestens bei Meilenstein | M22 |
| Datum | 23.09.2026 |

## A-032

| Feld | Inhalt |
| --- | --- |
| Annahme | Portalnutzer sind Benutzer mit der Rolle portal_user ohne CRM-Rechte. Zugriffsrechte werden aus Verträgen abgeleitet (Vertrag und Einheit für die Vertragspartei; Rechtsträger der GdWE für Eigentümer) und gelten im Vertragszeitraum. Dokumente sind sichtbar, wenn sie mit einem berechtigten Bereich verknüpft und für die Rolle der Berechtigung freigegeben sind. Dienstleister sehen Aufträge, bei denen sie Auftragnehmer sind. |
| Begründung | 6.9.6, 14. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Portal |
| Überprüfung spätestens bei Meilenstein | G5 |
| Datum | 23.09.2026 |

## A-033

| Feld | Inhalt |
| --- | --- |
| Annahme | Zustellweg: ausdrücklich gewählter Weg, sonst bevorzugter Kanal des Kontakts, sonst Post. Zugang gilt nur mit Nachweisart und Referenz oder Beleg als erfasst. Im Portal-Posteingang erscheinen nur per Portal zugestellte Dokumente und eigene Uploads, nicht jedes mit dem Kontakt verknüpfte Dokument. |
| Begründung | M23, 11.3. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Kommunikation, Portal |
| Überprüfung spätestens bei Meilenstein | M27 |
| Datum | 23.09.2026 |

## A-034

| Feld | Inhalt |
| --- | --- |
| Annahme | Im Test wird der beschlossene Jahresvorschuss als eine Monatssollstellung gebucht. Die Berechnung summiert alle gebuchten Sollstellungen des Jahres je Einheit und Komponente; die Stückelung ändert das Ergebnis nicht. |
| Begründung | M24, D01 bis D03 |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | WEG |
| Überprüfung spätestens bei Meilenstein | M24 |
| Datum | 23.09.2026 |

## A-035

| Feld | Inhalt |
| --- | --- |
| Annahme | Beim Kopfprinzip zählt jede Eigentümerpartei eine Stimme, auch bei mehreren Einheiten; uneinheitliche Stimmabgabe derselben Partei wird abgelehnt. Die Auszählung ist ein Vorschlag, maßgeblich ist die Verkündung durch die Versammlungsleitung, die bei einfacher Mehrheit nicht von der Auszählung abweichen darf. |
| Begründung | M25, R05 |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | WEG-Versammlung |
| Überprüfung spätestens bei Meilenstein | M25 |
| Datum | 23.09.2026 |

## A-036

| Feld | Inhalt |
| --- | --- |
| Annahme | Die Übernahme einer Mieterhöhung beendet die bisherige Mietzeile am Vortag der Wirksamkeit und legt eine neue Zeile mit Grund Erhöhung und Zustimmungsnachweis an. Bestehen bereits künftige Mietzeilen, wird abgebrochen und manuell geprüft. Leerstand zählt ab dem Tag nach dem letzten Vertragsende, Einheiten ohne früheren Vertrag ohne Dauer. |
| Begründung | M26 |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Vermietung |
| Überprüfung spätestens bei Meilenstein | M26 |
| Datum | 23.09.2026 |

## A-037

| Feld | Inhalt |
| --- | --- |
| Annahme | Nutzungszähler: Einheiten sind alle nicht fiktiven Einheiten des Mandanten, Benutzer die aktiven Mitgliedschaften, KI-Kosten die Summe des Monats, Speicher der Dokumentbestand zum Zählzeitpunkt. Lizenz und Nutzungszähler sind Plattformtabellen ohne RLS und nur für Plattformadministratoren erreichbar. |
| Begründung | M27, 5.3, 6.8 |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Plattform |
| Überprüfung spätestens bei Meilenstein | M27 |
| Datum | 23.09.2026 |

## A-038

| Feld | Inhalt |
| --- | --- |
| Annahme | Sonderumlagen werden je Rate als Vertragszahlung der Zahlungsart Sonderumlage für genau einen Monat angelegt; Rundungsrest auf die letzte Rate. Zwei übernommene Sonderumlagen derselben Gemeinschaft dürfen sich zeitlich nicht überschneiden, weil Sollstellungen gleicher Zahlungsart sonst in der Auswertung nicht trennbar sind. Verwendete Mittel sind die gebuchten Salden auf dem gewählten Verwendungskonto ab der ersten Fälligkeit. |
| Begründung | W09 |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | WEG |
| Überprüfung spätestens bei Meilenstein | W09 |
| Datum | 23.09.2026 |

## A-039

| Feld | Inhalt |
| --- | --- |
| Annahme | Jeder aktive Benutzer des CRM darf sich über den Plattform-OIDC-Anbieter bei einer registrierten Relying Party (zum Beispiel der Statusseite) anmelden. Die Relying Party erhält Identität (sub, email, name) und den gewählten Mandanten, keine Rollen. Eine Freigabe je Benutzer oder Rolle ist nicht vorgesehen. |
| Begründung | Auftrag 25.09.2026 (Statusseite für alle CRM-Benutzer sichtbar); Relying Parties sind interne Werkzeuge des Betreibers |
| Kennzeichnung | unkritisch, bei Anbindung externer Dienste mit Kundendaten zu überprüfen |
| Betroffene Bereiche | Plattform, Anmeldung |
| Überprüfung spätestens bei Meilenstein | M30 Folgeausbau |
| Datum | 25.09.2026 |

## A-040

| Feld | Inhalt |
| --- | --- |
| Annahme | Mitarbeiter (Mandanten-Mitglieder mit hinterlegter Mobilnummer) benötigen für eine WhatsApp-Nachricht der SLA-Eskalation keine erfasste Einwilligung nach dem Kontakt-Einwilligungsmodell (`ConsentKind.WHATSAPP`); sie gelten als interner Kanal, wie bereits bei SMS und E-Mail der Eskalation. Eine Einwilligung ist nur für den Versand an Kontakte (Mieter, Eigentümer) vorgesehen (`mhvp.sla.whatsapp.has_whatsapp_consent`), wird aber von der SLA-Eskalation aktuell nicht aufgerufen, da diese ausschließlich Mitarbeiter und Bereitschaft benachrichtigt. |
| Begründung | Auftrag 25.09.2026 (WhatsApp-Kanal neben SMS); gleiche Einordnung wie die bestehenden internen Eskalationskanäle, keine eigenständige rechtliche Prüfung des arbeitsrechtlichen Einzelfalls |
| Kennzeichnung | unkritisch für den jetzigen Umfang (nur interne Eskalation); bei künftiger Nutzung des Kanals für Kontakt-Benachrichtigungen zu überprüfen |
| Betroffene Bereiche | SLA-Eskalation, WhatsApp-Kanal (docs/rules/M21-05.md) |
| Überprüfung spätestens bei Meilenstein | vor einer Erweiterung auf Kontakt-Benachrichtigungen außerhalb der SLA-Eskalation |
| Datum | 25.09.2026 |

## A-041

| Feld | Inhalt |
| --- | --- |
| Annahme | Der Standardtext des Mahnschreibens (`mhvp.accounting.dunning_letters`) ist neutral: er listet die offenen Posten mit Fälligkeit, nennt den Forderungsinhaber ("im Auftrag von"), bittet um Ausgleich und enthält den Hinweis, dass sich das Schreiben bei zwischenzeitlicher Zahlung erledigt. Er behauptet keinen Verzug, nennt keine Rechtsfolgen und keine Bankverbindung. Ein Zahlungsdatum erscheint nur, wenn je Stufe `payment_days` hinterlegt ist (Briefdatum plus Tage, Kalendertage ohne Feiertagsprüfung); ein hinterlegter `letter_text` je Stufe ersetzt nur den Aufforderungsabsatz. Jedes Schreiben trägt "Entwurf, kein Versand". Ergänzung 26.09.2026 (A33): die Standardtexte je Stufe (`STANDARD_TEXTS`, Zahlungserinnerung, 1., 2., 3. Mahnung) verweisen im Einleitungsabsatz auf die vorherige Stufe ("trotz unserer Zahlungserinnerung"), weil eine Stufe nur nach manueller Versandmarkierung steigt; die Forderungsaufstellung nennt als Posten den Buchungstext des offenen Postens. |
| Begründung | Aufgabe 26.09.2026 (Mahnschreiben als PDF-Entwurf); Textbausteine je Stufe sind nicht freigegeben (M16-02), daher nur ein Text ohne rechtliche Aussagen. Gebühr und Zins erscheinen ausschließlich aus den wirksamen Einstellungen (docs/rules/M16-01.md, M16-02.md). |
| Kennzeichnung | unkritisch, solange der Versand gesperrt bleibt; vor Freigabe des Versands sind Textbausteine, Zahlungsfrist und Bankverbindung zu entscheiden (M16-02, M16-12, M16-13) |
| Betroffene Bereiche | Mahnwesen, Mahnschreiben (docs/rules/M16-02.md) |
| Überprüfung spätestens bei Meilenstein | vor Freigabe G1 und vor dem Versand von Mahnschreiben (M23) |
| Datum | 26.09.2026 |

## A-042

| Feld | Inhalt |
| --- | --- |
| Annahme | Beim KI-Lauf `contact_master_data_change` (docs/rules/M19-05.md) werden vor dem Anbieteraufruf nur IBAN, E-Mail-Adressen und Telefonnummern maskiert (`mask_identifiers`), nicht die Personennamen. Die bestehende Vollmaskierung `mask_text` (M35-02) würde den Namen entfernen, der hier der Gegenstand der Erkennung ist. Die Mail eines Absenders enthält damit denselben Umfang an Namen wie die bereits bestehenden Mail-Läufe `classify_email` und `draft_reply`, die den Mailtext unmaskiert übergeben. |
| Begründung | Betreiberauftrag 26.09.2026 (lernendes Ticketsystem: Namensänderung nach Hochzeit erkennen); Regel 0.1.13 nennt Kennungen wie IBAN ausdrücklich, die Maskierung deckt diese und die Kontaktkennungen ab |
| Kennzeichnung | unkritisch, solange der Anbieter mit Auftragsverarbeitung und Trainingsausschluss freigegeben ist (Vier-Augen-Freigabe in `ai_provider_config`); bei einer strengeren Datenschutzvorgabe ist der Lauf auf die deterministische Stufe zu beschränken (Anbieter nicht freigeben) |
| Betroffene Bereiche | Tickets, Mail-Eingang, KI-Gateway (docs/rules/M19-05.md) |
| Überprüfung spätestens bei Meilenstein | vor Freigabe G5 (Drittmandanten) und bei der Datenschutzprüfung vor Produktivbetrieb |
| Datum | 26.09.2026 |

## A-043

| Feld | Inhalt |
| --- | --- |
| Annahme | Im Belegeingang (M14, `mhvp.receipts`) sieht der KI-Anbieter keine IBAN. IBAN-Kandidaten werden vor der Maskierung deterministisch im Belegtext erkannt, verschlüsselt am Entwurf gespeichert, nur maskiert angezeigt (erste vier und letzte vier Zeichen, Prüfziffernstatus) und ausschließlich durch Eingabe und ausdrückliche Bestätigung der prüfenden Person (`iban_confirmed=true`) in den Rechnungsentwurf übernommen. Fehlt eine Währung im Beleg, wird EUR mit Konfidenz 0,5 und Hinweis angenommen; eine Fremdwährung sperrt die Anlage wie bisher. |
| Begründung | Regel 0.1.6 (KI genehmigt nie allein eine IBAN), Regel 0.1.13 (Maskierung vor externem Aufruf); der bestehende Anlagepfad `mhvp.ai.imports.apply_invoice` bleibt unverändert |
| Kennzeichnung | unkritisch; die Prüfziffer ist nur ein Hinweis für die prüfende Person, kein Nachweis der Richtigkeit |
| Betroffene Bereiche | Belegeingang, Rechnungseingang, KI-Gateway |
| Überprüfung spätestens bei Meilenstein | vor Freigabe G1 (produktive Buchhaltung) und G2 (Zahlungsauslösung) |
| Datum | 26.09.2026 |

## A-044

| Feld | Inhalt |
| --- | --- |
| Annahme | Der Differenzimport aus objektakte (Stufe 5, `mhvp.objektakte.objektakte_import.run_differential_import`) liest die Quellspalte `updated_at` als UTC (Django `USE_TZ=True`) und vergleicht mit dem Wasserstand per größer oder gleich; Zeilen genau am Wasserstand werden erneut gelesen, ändern aber nichts. Die Löschung der letzten Zeile einer Tabelle ist in einem mysqldump nicht erkennbar (keine INSERT-Zeilen) und wird erst erkannt, wenn die Tabelle wieder Zeilen enthält. Löschungen werden nie physisch übernommen, sondern nur als Markierung (`objektakte_source_deletion`) geführt. |
| Begründung | objektakte ist eine Django-Anwendung mit Zeitzonenunterstützung; ein Dump ohne Zeilen unterscheidet nicht zwischen leerer und nicht exportierter Tabelle; Regel 0.1.7 (keine Löschung finanz- oder beweisrelevanter Daten) |
| Kennzeichnung | unkritisch; im Zweifel bleibt ein Datensatz erhalten und wird nur markiert |
| Betroffene Bereiche | objektakte-Übernahme, Dokumente, Kontakte, Objekte |
| Überprüfung spätestens bei Meilenstein | vor Abschaltung von objektakte (Stufe 6) |
| Datum | 26.09.2026 |

## A-045

| Feld | Inhalt |
| --- | --- |
| Annahme | Regelversionen der Betriebskostenabrechnung (`mhvp.billing.calc.RULE_VERSIONS`) werden nach dem ersten Tag des Abrechnungszeitraums gewählt: Es gilt die Version mit dem spätesten Geltungsbeginn, der nicht nach dem Periodenbeginn liegt. Der Snapshot speichert die verwendete Version; eine später eingetragene Version verändert berechnete oder ausgegebene Abrechnungen nicht, auch nicht bei einer neuen Version derselben Abrechnung (D28). Ob eine Regel mit Geltungsbeginn innerhalb eines Zeitraums anteilig oder erst ab der Folgeperiode gilt, ist damit nicht entschieden. |
| Begründung | 7.6 A01 (Regelversion konserviert), Anhang D Fall D28; bislang gibt es nur eine Version, die Stichtagswahl ist als Mechanismus testbar |
| Kennzeichnung | unkritisch, solange nur eine Regelversion existiert; vor Eintrag einer zweiten Version fachlich zu bestätigen |
| Betroffene Bereiche | Betriebskostenabrechnung Miete (M17) |
| Überprüfung spätestens bei Meilenstein | G3 |
| Datum | 26.09.2026 |

## A-046

| Feld | Inhalt |
| --- | --- |
| Annahme | Beim MT940-Import erhält ein Umsatz ohne `//`-Bankreferenz in `:61:` eine abgeleitete Referenz aus Auszugsnummer (`:28C:`), laufender Zeilennummer und Valutadatum (`raw.reference_source = derived:28C/line/value_date`). Ein Wiederimport derselben Datei wird damit als Dublette erkannt und hat keine Zusatzwirkung; zwei gleiche Zahlungen in verschiedenen Auszügen oder Zeilen bleiben zwei Zahlungen (D05). Die Annahme ist, dass eine Bank die Auszugsnummer je Konto nicht innerhalb eines Jahres wiederverwendet und die Zeilenreihenfolge beim erneuten Abruf desselben Auszugs stabil ist. |
| Begründung | MT940 kennt keine verbindliche eindeutige Umsatzkennung; ohne Referenz würde jeder Wiederimport neue Umsätze zur Prüfung anlegen. Die Ableitung ist deterministisch und im Rohdatensatz gekennzeichnet, nichts wird erfunden |
| Kennzeichnung | unkritisch für Entwicklung und Tests; vor produktivem Einsatz mit echten Auszügen der jeweiligen Bank zu prüfen (M11-02) |
| Betroffene Bereiche | Bankumsatzimport MT940 (M11), Dublettenprüfung (D05) |
| Überprüfung spätestens bei Meilenstein | Abnahme M11 mit echten Beispieldateien |
| Datum | 26.09.2026 |

## A-047

| Feld | Inhalt |
| --- | --- |
| Annahme | Für den täglichen Abgleichbericht des Parallelbetriebs (A68, `mhvp.imports.reconciliation`) werden die Rohzeilen der Immoware24-Exporte Journal und Bankumsätze mit folgenden Standardspalten gelesen: Journal `Objekt`, `Konto`, `Datum`, `Betrag` (Soll positiv, Haben negativ), ersatzweise `Soll` und `Haben`; Bankumsätze `Objekt`, `IBAN`, `Datum`, `Betrag` (Gutschrift positiv), optional `Saldo` (Saldo nach Buchung). Kontonummern mit weniger als sechs Stellen werden links mit Nullen aufgefüllt (1200 wird 001200), ein- und zweistellige Objektnummern auf drei Stellen. Die Kontoart eines Quellkontos (Bank, Debitor, Kreditor, Rücklage) wird über das gleichnamige Konto im Buchungskreis der Plattform bestimmt; ohne Treffer bleibt das Konto ohne Kontoart und geht nur in den Kontosaldenvergleich ein. |
| Begründung | Die Spaltennamen der Immoware24-Exporte sind nicht spezifiziert (13.1); die Zuordnung ist je Mandant über `PUT /api/v1/imports/reconciliation-reports/columns` änderbar. Der Bericht liest und vergleicht nur, er bucht und korrigiert nichts; eine falsche Zuordnung führt zu ausgewiesenen Abweichungen, nie zu einer Buchung. Keine Kontenklassen oder Vorzeichenregeln werden erfunden, die Kontoart kommt aus dem Buchungskreis. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb; vor Nutzung im Parallelbetrieb mit echten Exporten zu prüfen (M8-01, M8-02) |
| Betroffene Bereiche | Abgleichbericht `POST /api/v1/imports/reconciliation-reports`, Beat-Job `mhvp.imports.reconciliation_all`, CRM-Seite Importe, Abgleichbericht |
| Überprüfung spätestens bei Meilenstein | Abnahme M8 mit echten Exportdateien (M8-01) |
| Datum | 26.09.2026 |

## A-048

| Feld | Inhalt |
| --- | --- |
| Annahme | Anruf-Mails der Telefonassistenz Hallo Heidi (`mhvp.tickets.call_assistant`) werden ohne Mandanteneinstellung an den Absendermustern `hallo-heidi`, `halloheidi`, `hallo.heidi` und am Kennwort `hallo heidi` im Betreff erkannt. Deutsche Rufnummern mit +4915, +4916 und +4917 gelten als Mobilnummern (Label `mobile`), alle übrigen als `other`. Eine Objektnummer im Protokoll ist dreistellig wie im Immoware24-Bestand. |
| Begründung | Das Mailformat der Telefonassistenz ist nicht spezifiziert; die Muster stammen aus dem Betreiberauftrag vom 26.09.2026 und sind je Mandant unter Einstellungen, Postfächer änderbar (`tenant_settings.call_assistant`). Das Label steuert nur die Anzeige der Rufnummer am Kontakt, keine Kommunikation. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb; Datenschutzfragen stehen unter M19-03 |
| Betroffene Bereiche | Ticketvorschläge aus Anruf-Mails, Einstellungen Postfächer, Regel M19-08 |
| Überprüfung spätestens bei Meilenstein | Abnahme M20 mit echten Protokollmails des Anbieters |
| Datum | 26.09.2026 |

## A-049

| Feld | Inhalt |
| --- | --- |
| Annahme | Der Vertragsbeginn der aus der Immoware24-Objektliste erzeugten Miet- und Eigentumsverträge (`mhvp.imports.zuordnung`, Listenimport Zuordnung) ist der 1. Januar des laufenden Jahres, wenn im Aufruf oder auf der Importseite kein Datum angegeben wird. Der Bericht kennzeichnet das Datum als angenommen (`start_date_assumed`). |
| Begründung | Die Objektliste enthält den aktuellen Eigentümer und Mieter mit vereinbartem Zahlbetrag, aber keinen Vertragsbeginn. Ein Datum im laufenden Jahr erzeugt keine rückwirkenden Sollstellungen über den Übernahmezeitraum hinaus; produktive Sollstellungen bleiben hinter G1 gesperrt. Der wahre Beginn ist je Vertrag im CRM nachzutragen. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb; vor G1 mit dem Migrationsstichtag je Objekt (V9) abzugleichen |
| Betroffene Bereiche | `POST /imports/immoware24/lists/zuordnung`, CLI `python -m mhvp.imports.zuordnung`, Verträge und Zahlungspläne aus der Übernahme |
| Überprüfung spätestens bei Meilenstein | Abnahme M8 mit echten Exporten (M8-01), spätestens G1 |
| Datum | 26.09.2026 |

## A-050

| Feld | Inhalt |
| --- | --- |
| Annahme | Paperless-Gesellschaftsfilter (Immoware Hub 7.2, `mhvp.documents.paperless_search`): Ein Paperless-Auswahlfeld wird über `custom_field_query` mit `[<Feld-ID>, "exact", "<Options-ID>"]` gefiltert, verglichen wird der Wert, den Paperless im Auswahlfeld eines Dokuments speichert. Liefert Paperless die Zusatzfelder in der Trefferliste mit, prüft das CRM Objektnummer und Gesellschaft dort nach und verwirft abweichende Treffer; die Gesamtzahl wird dabei nur um die auf der aktuellen Seite verworfenen Treffer gekürzt. Ohne `custom_fields` in der Antwort gilt allein der Filter von Paperless. |
| Begründung | Die Filtersyntax ist laut Dossier aus der öffentlichen Paperless-Dokumentation abgeleitet und am Hub-Server nur für die Objektsuche geprüft (Abschnitt 6). Die Nachprüfung verhindert, dass ein anders auslegender Server fremde Dokumente an ein Objekt oder eine Gesellschaft hängt; lieber zu wenig als falsch zugeordnet. Feld-ID und Zuordnung sind Einstellungen mit leerem Standard, keine ID ist im Code hinterlegt. |
| Kennzeichnung | unkritisch, nur lesend; am Paperless-Server `dms.muellerhv.de` mit echten Feld- und Options-IDs zu bestätigen |
| Betroffene Bereiche | `GET /api/v1/dms-documents`, `GET /api/v1/dms-documents/companies`, Parameter `company` an `/properties/{id}/dms-documents` und `/tickets/{id}/dms-documents`, Paperless-Ansicht an Objekt und Ticket |
| Überprüfung spätestens bei Meilenstein | Abschaltung des Immoware Hub (Dossier 7, Schritt 4) |
| Datum | 26.09.2026 |

## Ausdrücklich nicht angenommen

Die folgenden Punkte sind in M1 bewusst nicht entschieden und dürfen nicht als stillschweigende Annahme in Code oder Dokumentation eingehen:

| Punkt | Grund | Zuständig für spätere Festlegung |
| --- | --- | --- |
| Rundungsverfahren (etwa ROUND_HALF_UP) je Rechenwerk | Abschnitt 6.9.8 verlangt die Dokumentation je Rechenwerk in `billing/rules`; betrifft Geld | Festlegung mit M10 und freigegebener Regel |
| Restcentverteilung über D08 hinaus | betrifft Geld; nur der Produktstandard aus 6.9.8 und D08 ist vorgegeben | M10 |
| Verzugszinsen, Mahngebühren, Mahnstufen | V7 offen | M16 |
| Aufbewahrungsfristen und Löschregeln | V17 offen, E05 | M6, M18 |
| Fachliche Fristberechnung (Zeitzone, Feiertage, Zugang) | betrifft gesetzliche Fristen; offen als M1-09 | jeweiliger Fachmeilenstein |
| Kontenrahmen | V8 offen | M10 |

## A-050

| Feld | Inhalt |
| --- | --- |
| Annahme | Für plattformweite Schalter gab es bis zum 26.09.2026 keinen persistenten Mechanismus (nur Umgebungsvariablen in `mhvp.core.config.Settings` und Mandanteneinstellungen je Mandant). Für den Schalter `gate_superadmin_bypass` (ADR 0011) wurde deshalb die einzeilige Plattformtabelle `platform_settings` (Migration 0135, ohne Mandantenbezug, ohne RLS, Pflege nur durch Plattformadministratoren über `GET`/`PATCH /api/v1/platform/settings`) angelegt. Änderungen werden im Anwendungsprotokoll mit Akteur, altem und neuem Wert und Version festgehalten; ein eigenes plattformweites Änderungsprotokoll (Tabelle) existiert nicht, da das Änderungsprotokoll (`audit_log`) mandantenbezogen ist. |
| Begründung | ADR 0003 Nr. 2 verbietet Umgebungsvariablen als Gate-Schalter; eine Mandanteneinstellung wäre je Mandant und nicht durch Plattformadministratoren allein kontrolliert. |
| Kennzeichnung | unkritisch, ermöglicht die Umsetzung von ADR 0011; Standard des Schalters ist aus |
| Betroffene Bereiche | Plattformverwaltung, Freigabestufen G1 bis G5 |
| Überprüfung spätestens bei Meilenstein | M9 (Betrieb), spätestens vor G1 |
| Datum | 26.09.2026 |

## A-051

| Feld | Inhalt |
| --- | --- |
| Annahme | Die Ähnlichkeitssuche über Einbettungen (`mhvp.ai.embeddings`, M7-03) bietet nur Treffer mit Kosinusdistanz bis 0,8 an (`MAX_COSINE_DISTANCE`); darüber gilt ein Dokument als nicht einschlägig und der Aufrufer fällt auf die Schlüsselwortsuche zurück. Texte werden in Fenster von 1500 Zeichen mit 200 Zeichen Überlappung zerlegt, höchstens 200 Fenster je Quelle; ein Aufruf beim Anbieter umfasst bis zu 64 Fenster. Die Werte sind technische Vorgaben ohne Rechtsbezug. |
| Begründung | Der Master-Prompt nennt keine Schwelle und keine Fenstergröße (Abschnitt 9.1 verlangt nur Zerlegung, Einbettung je Mandant und Berechtigungsfilter vor der Suche). Ein Grenzwert verhindert, dass bei kleinen Beständen beliebig unpassende Dokumente in den Kontext gelangen. |
| Kennzeichnung | unkritisch, Konstanten in `mhvp.ai.embeddings`; Änderung ohne Migration möglich, gespeicherte Vektoren bleiben gültig |
| Betroffene Bereiche | Kontext-Chat (answer_question), Wissensbasis in der Mail-Vorbereitung |
| Überprüfung spätestens bei Meilenstein | M20 (Portal-Chat), nach den ersten Auswertungen mit echten Dokumenten |
| Datum | 26.09.2026 |

## A-052

| Feld | Inhalt |
| --- | --- |
| Annahme | Der Vollabruf des Gmail-Posteingangs (`mhvp.communication.backfill`, Betreiberauftrag 26.09.2026) nimmt Altbestand nur mit Ticketzuordnung, Thread- und TNR-Erkennung auf; die KI-Rechnungserfassung (M14-05), die Rechnungsweiterleitung und die Archivierung werden für rückwirkend geholte Mails nicht ausgelöst. Der Ticketabschluss per letzter erledigter Mail nutzt die Erledigungsart `auskunft_erteilt`; ist sie deaktiviert, bleibt das Ticket offen. |
| Begründung | Der Betreiber hat Ticketzuordnung und TNR-Erkennung ausdrücklich verlangt und die rückwirkende Archivierung ausgeschlossen; KI-Läufe für hunderte alte Mails verursachten Kosten ohne Auftrag (Regel 0.1.6, Vorschläge nur auf Anforderung). Die Erledigungsart ist die vom Betreiber genannte. |
| Kennzeichnung | unkritisch, kein Geldfluss; jederzeit über einen erneuten Vollabruf mit erweitertem Umfang änderbar |
| Betroffene Bereiche | `POST /mail/mailboxes/{id}/backfill`, CLI `python -m mhvp.communication.backfill`, `services.complete_message`, Regel M20-07 |
| Überprüfung spätestens bei Meilenstein | Abnahme M20 (info@ läuft über die Plattform) |
| Datum | 26.09.2026 |

## A-053

| Feld | Inhalt |
| --- | --- |
| Annahme | Der Energieausweis wird nur am Gebäude geführt (Betreiberentscheidung 26.09.2026). Migration 0149 kopiert vorhandene Werte der Objektebene in jedes Gebäude des Objekts, dessen Ausweisfelder leer sind, und entfernt die Objektspalten. Bei Objekten mit mehreren Gebäuden erhalten damit alle Gebäude denselben Ausweis, weil die Quelle nicht sagt, zu welchem Gebäude er gehört; der Betreiber korrigiert das je Gebäude. Der bisherige einzelne Energieträger wird zur Liste `energy_sources` mit einem Eintrag, `energy_certificate_value` heißt am Gebäude jetzt `energy_final_heat_kwh`. Inserate übernehmen bei Anlage die Werte des Gebäudes der Einheit; ein Ausweis mit mehreren Energieträgern wird im Inserat als ein Text (höchstens 32 Zeichen) geführt. |
| Begründung | Ergänzung 27.09.2026 Abschnitt 4.3 ordnet den Ausweis dem Gebäude zu; die Doppelführung (A63 am Objekt, M26) wäre widersprüchlich. Ein Ausweis ohne Gebäudezuordnung ist im Altbestand nicht rekonstruierbar. |
| Kennzeichnung | unkritisch, kein Geldfluss; Werte bleiben erhalten und sind je Gebäude änderbar (`PUT /buildings/{id}`) |
| Betroffene Bereiche | `mhvp.properties` (Gebäude), `mhvp.letting` (Exposé, Inserat-Vorbelegung, OpenImmo-Prüfung), Oberfläche `EnergyCertificateForm` (Anpassung an Gebäude offen, AP8) |
| Überprüfung spätestens bei Meilenstein | Abnahme P1 AP2, spätestens vor M26-03 |
| Datum | 26.09.2026 |

## A-054

| Feld | Inhalt |
| --- | --- |
| Annahme | Ein CSV-Umsatzimport ohne erkanntes Bankformat und ohne eigene IBAN-Spalte (z. B. DKB) wird nur importiert, wenn Konto oder Mapping ausdrücklich angegeben werden; ohne diese Angabe liefert die Vorschau nur Zeilenzahl und Fehler, ohne zu importieren. Der Dublettenschutz nutzt denselben Inhalts-Hash wie CAMT/MT940 (IBAN, Datum, Betrag, Verwendungszweck, End-to-End-Referenz); eine Bankreferenz gibt es bei CSV meist nicht, daher greift überwiegend die Hash-Prüfung mit Status "zur Prüfung" bei Übereinstimmung, nie automatisches Verwerfen (D05). |
| Begründung | Ein CSV-Format ohne eigene IBAN darf nicht raten, welchem Konto ein Umsatz gehört (Rechtsträgertrennung, Abschnitt 8); Regel 0.1.3 verbietet erfundene Kontobezüge. |
| Kennzeichnung | unkritisch, kein Geldfluss (nur Bankdatenimport, kein Zahlungsauftrag, G2 bleibt zu) |
| Betroffene Bereiche | `mhvp.banking.csv_formats`, `POST /banking/imports/csv`, `POST /banking/imports/csv/preview` |
| Überprüfung spätestens bei Meilenstein | Abnahme M11 (Umsatzimport) |
| Datum | 27.09.2026 |

## A-055

| Feld | Inhalt |
| --- | --- |
| Annahme | Der lexoffice-Belegimport (`mhvp.integrations.lexoffice`, M13-lexoffice) legt je gefundenem Voucher zunächst die rohe lexoffice-JSON als Dokument ab (`mime_type application/json`), nicht die eigentliche PDF-Datei, weil die Verknüpfung eines Vouchers mit seiner Datei in der erreichbaren Dokumentation nicht bestätigt ist. Der `ReceiptDraft` übernimmt nur unverifizierte Rohdaten mit einer Warnung; Export-Payloads (Voucher, Kontakt) werden von diesem Modul nicht selbst gebaut, sondern unverändert vom Aufrufer durchgereicht. |
| Begründung | Rule 0.1.3: kein erfundenes Feldschema für Eingangsrechnungs-Voucher oder Kontakte, da die WebFetch-Recherche dafür keine vollständige Referenz lieferte (docs/integrations/lexoffice.md). |
| Kennzeichnung | kritisch für den produktiven lexoffice-Export (Geldwirkung, Gate G1 zusätzlich zum Feature-Flag gesperrt); Import selbst unkritisch (nur Belegentwurf, keine Buchung) |
| Betroffene Bereiche | `mhvp.integrations.lexoffice`, `mhvp.integrations.routers`, `mhvp.receipts` (`ReceiptDraftSource.LEXOFFICE`) |
| Überprüfung spätestens bei Meilenstein | vor Freigabe G1 für einen Mandanten mit aktivierter lexoffice-Anbindung |
| Datum | 27.09.2026 |

## A-056

| Feld | Inhalt |
| --- | --- |
| Annahme | Die Heizkosten-Vorrechnung (M17-02) verwendet als Entwurfswerte: Verbrauchsanteil 70 Prozent, Warmwasserformel mit Faktor 2,5 kWh/(m³·K) und Bezugstemperatur 10 °C, CO2-Stufentabelle Wohngebäude aus der Code-Fassung vom 23.09.2026 und eine leere Gradtagstabelle (Grundkosten bei Nutzerwechsel nach Zeitanteil mit Hinweis). Der Import aus `mhvp.metering` ordnet Periodenverbräuche mit den Kennungen `heating` und `hot_water` zu. |
| Begründung | Rule 0.1.3: keine erfundenen Rechtsregeln; alle Werte sind je Mandant konfigurierbar (`heating_rule_table`, Einstellungen je Abrechnung) und tragen den Status zu prüfen. Das Ergebnis ist ein Entwurf ohne Geldwirkung; die Ausgabe der Abrechnung bleibt hinter G3. |
| Kennzeichnung | unkritisch für den Entwurfsbetrieb; kritisch vor Ausgabe an Mieter (G3), siehe OPEN_QUESTIONS M17-02 |
| Betroffene Bereiche | `mhvp.billing.heating_calc`, `mhvp.billing.heating_services`, `mhvp.billing.heating_routers`, CRM `HeatingPanel` |
| Überprüfung spätestens bei Meilenstein | vor Freigabe G3 für den ersten Mandanten |
| Datum | 27.09.2026 |

## A-057

| Feld | Inhalt |
| --- | --- |
| Annahme | Bei nicht monatlichen Zahlungsplänen gilt der am Vertrag erfasste Betrag je Monat (`amount_basis = per_month`); die Rate ist die Summe der Monatsbeträge des Ratenzeitraums. Ratenzeiträume beginnen mit dem Monat des Zahlungsplanbeginns. Bei der Regel "voller Monat" gilt der am letzten erfassten Tag des Monats gültige Betrag. |
| Begründung | Bestandsdaten aus Immoware24 führen Beträge je Monat; ein Betrag je Rate ist je Zahlungsplan wählbar (`per_instalment`). Die Regeln wirken nur nach Freigabe je Mandant (M13-01, M13-02) und hinter G1, bis dahin bleiben die Posten manuell. |
| Kennzeichnung | unkritisch für den Entwurfsbetrieb, geldwirksam erst nach Freigabe |
| Betroffene Bereiche | `mhvp.accounting.proration`, `mhvp.accounting.receivables`, `PaymentSchedule.amount_basis`, `docs/rules/M13-01.md`, `docs/rules/M13-02.md` |
| Überprüfung spätestens bei Meilenstein | G1 (Betreiber mit Steuerberatung, OPEN_QUESTIONS M13-02) |
| Datum | 27.09.2026 |

## A-058

| Feld | Inhalt |
| --- | --- |
| Annahme | Fristbeginn der Aufbewahrungsmatrix (M6-04): bei `end_of_year_created` das Jahresende des Entstehungsjahres; bei `contract_end`, `end_of_year_last_entry` und `statement_issued` das Jahresende des Jahres des Basisdatums am Dokument (`retention_base_on`); bei `purpose_end` das Basisdatum tagesgenau; `permanent` ohne Datum. Fehlt das Basisdatum, wird keine Frist berechnet und das Dokument bleibt gesperrt. Der Löschvorschlagslauf läuft monatlich am 2. um 04:20 |
| Begründung | Rule 0.1.3: keine erfundene Rechtsregel. Das Jahresende als Beginn verlängert die Frist gegenüber einem tagesgenauen Beginn und verkürzt sie nie; bei personenbezogenen Daten mit Zweckende wird nicht verlängert, damit keine Daten ohne Zweck länger als nötig bleiben. Die Werte und Startregeln je Profil sind je Mandant änderbar und tragen den Status zu prüfen durch Steuerberater (OPEN_QUESTIONS M6-04) |
| Kennzeichnung | unkritisch für Entwurfsprofile (kein freigegebenes Profil, keine Löschung); kritisch vor Freigabe eines Profils je Mandant |
| Betroffene Bereiche | `mhvp.documents.retention`, `mhvp.documents.services.deletion_blocker`, CRM Einstellungen Aufbewahrung, Dokumente Löschvorschläge |
| Überprüfung spätestens bei Meilenstein | vor Freigabe des ersten Aufbewahrungsprofils je Mandant (V17) |
| Datum | 27.09.2026 |

## A-057

| Feld | Inhalt |
| --- | --- |
| Annahme | Die Ableitung des Verzugsbeginns je Modus (docs/rules/M16-03.md) verwendet als Entwurfsregeln: "kalendermäßig bestimmt" beginnt am Tag nach der Vertragsfälligkeit; "30 Tage nach Fälligkeit und Zugang" beginnt am Tag nach Ablauf von 30 Tagen ab dem späteren von Fälligkeit und erfasstem Zugang der Zahlungsaufforderung; "erst nach Mahnung" beginnt am Tag nach dem erfassten Zugang der Mahnung. Welche Alternative für welche Forderungsart (Hausgeld, Miete, Nachzahlung aus Abrechnung) und welchen Beteiligten (Verbraucher, Unternehmer) gilt, ist nicht abgebildet; der Betreiber wählt den Modus je Mandant |
| Begründung | Rule 0.1.3: keine erfundenen Rechtsregeln. Die Plattform leitet nur aus erfassten Tatsachen ab und lässt den Verzugsbeginn offen, wenn die Tatsache fehlt. Verzugszinsen bleiben informatorischer Entwurf hinter G1 (M16-01); das Mahnschreiben behauptet keinen Verzug |
| Kennzeichnung | kritisch vor jeder Geltendmachung von Verzugszinsen oder Verzugsschaden (G1, Mahnbescheid); unkritisch für die Anzeige in der Vorschau, solange der Modus nicht gesetzt ist |
| Betroffene Bereiche | `mhvp.accounting.dunning.default_start`, `DunningSettings.default_start_mode`, CRM Mahnwesen Einstellungen und Mahnlauf-Seite |
| Überprüfung spätestens bei Meilenstein | vor Freigabe G1 (Betreiber mit Rechtsanwalt, OPEN_QUESTIONS M16-03) |
| Datum | 27.09.2026 |

## A-059

| Feld | Inhalt |
| --- | --- |
| Annahme | Gültigkeitsfristen und Ratenbegrenzung der Magic-Link-Anmeldung des Kundenportals (M21-01) sind Produktschutz, keine Rechtsregel: Anmeldelink 15 Minuten, einmal nutzbar; optionaler E-Mail-Code (zweiter Faktor) 10 Minuten, einmal nutzbar; QR-Einladungscode für den postalischen Brief 90 Tage; höchstens fünf Linkanfragen je E-Mail-Adresse und Stunde |
| Begründung | Rule 0.1.3: keine erfundene Rechtsregel, kalkulierte Sicherheitsfristen nach Üblichkeit vergleichbarer Anmeldeverfahren (Passwort-Reset, Magic-Link-Anbieter); der Betreiber kann die Werte in einer künftigen Konfiguration je Mandant ändern, aktuell fest im Code (`mhvp.portal.magic_link`, `mhvp.portal.routers.QR_INVITE_DAYS`) |
| Kennzeichnung | unkritisch: kein Geld-, Beweis- oder Fristbezug im Rechtssinn; betrifft nur die technische Anmeldesicherheit |
| Betroffene Bereiche | `mhvp.portal.magic_link`, `mhvp.portal.routers` (`invitation-letter`, `magic-link/*`), `apps/web-portal` Anmeldeseite |
| Überprüfung spätestens bei Meilenstein | vor G5 (dritte Parteien im Portal), Sicherheitsreview |
| Datum | 27.09.2026 |

## A-060

| Feld | Inhalt |
| --- | --- |
| Annahme | Die automatisierten Prüfungen zu V13 (Barrierefreiheit, `axe-core` über `vitest-axe` auf den Kernkomponenten des Portals: Navigation, Übersicht, Aushänge, Meldung, Kontoauszug/Hausgeldkonto) sind ein technisches Hilfsmittel gegen WCAG 2.1 AA, keine vollständige Konformitätsprüfung nach EN 301 549 und kein Ersatz für eine externe Prüfung oder Nutzertests mit assistierender Technologie. Server-Komponenten (RSC-Seiten) werden nicht direkt gerendert, sondern über ihre client-seitigen Kernbausteine geprüft |
| Begründung | Rule 0.1.9/0.1.14: Tests belegen den technischen Befund, nicht die rechtliche Erfüllung des BFSG; Werkzeuggrenzen (automatisierte Prüfung erkennt nur einen Teil möglicher Barrieren) offen ausweisen |
| Kennzeichnung | unkritisch für den Portalbetrieb; kritisch nur im Zusammenhang mit der BFSG-Erklärung unter `/barrierefreiheit`, deren rechtliche Freigabe (M21-09) noch aussteht |
| Betroffene Bereiche | `apps/web-portal/src/components/portal/Accessibility.axe.test.tsx`, `apps/web-portal/src/app/barrierefreiheit/page.tsx` |
| Überprüfung spätestens bei Meilenstein | vor G5, bei externer Barrierefreiheitsprüfung (M21-09) |
| Datum | 27.09.2026 |

## A-061

| Feld | Inhalt |
| --- | --- |
| Annahme | Einladungsfrist der Eigentümerversammlung: Entwurfswert 3 Wochen je Mandant (`tenant_settings.hoa_invitation_weeks`), spätester Versand = Versammlungstag minus Wochen, ohne Regel zu Fristbeginn (Absendung oder Zugang) und Zählweise. Hybride Versammlungen (Präsenz mit Online-Teilnahme) sind ohne Schalter und ohne zulassenden Beschluss anlegbar; nur die rein virtuelle Form ist gesperrt (Schalter je Mandant, Beschluss mit Gültigkeitsende). Einwahldaten gelten als vertraulich und werden nur Eigentümern der GdWE im Portal gezeigt. |
| Begründung | Rule 0.1.3: keine erfundene Rechtsregel; der Wert ist je Mandant einstellbar, die Prüfung warnt nur und verlangt einen dokumentierten Grund, der im Protokoll steht. Ob hybride Versammlungen einen Beschluss brauchen, ist nicht geprüft (OPEN_QUESTIONS M25-03, V13). |
| Kennzeichnung | unkritisch für die Planung; kritisch vor produktivem Einsatz virtueller Versammlungen (Anfechtbarkeit von Beschlüssen, G4) |
| Betroffene Bereiche | `mhvp.hoa.meeting_rules`, `mhvp.hoa.meetings`, `mhvp.hoa.protocol`, `mhvp.portal.owner_meetings`, `mhvp.workspace.services.derived_dates`, CRM `MeetingFormPanel`, `MeetingSettings`, Portal `/versammlungen` |
| Überprüfung spätestens bei Meilenstein | vor Freigabe des Schalters `hoa_virtual_meetings_enabled` für den ersten Mandanten, vor G4 |
| Datum | 27.09.2026 |

## A-061

| Feld | Inhalt |
| --- | --- |
| Annahme | Steuerentwürfe des Rechnungseingangs (M14-02/03/04): Der Vorsteuerabzug wird als Vorsteuerbetrag mal Umsatzschlüssel des Objekts (Prozentsatz, vom Betreiber gepflegt) berechnet; Einheiten mit gültiger Option gelten als optiert. Der Einbehalt Bauabzugsteuer wird mit einem Entwurfswert von 15 Prozent des Bruttobetrags vorgeschlagen, wenn ein als Bauleistung gekennzeichneter Lieferant am Rechnungsdatum keine Freistellungsbescheinigung mit Dokument hat. Der § 35a-Ausweis je Mietvertrag zählt Positionen mit Einheit voll und übrige Positionen mit einem vom Aufrufer übergebenen Verteilungsanteil. Alle Werte sind Vorschläge hinter Mandantenschaltern (Standard aus). |
| Begründung | 7.2, 7.9.1 (PÜ03), 0.1.3 und 0.1.6: Entwurfsbetrieb ohne Rechtsbehauptung; die fachliche Freigabe der Sätze, Schlüssel und Belege liegt beim Steuerberater (OPEN_QUESTIONS M14-02, M14-03, M14-04). |
| Kennzeichnung | unkritisch, solange die Schalter aus sind; kritisch vor Aktivierung je Mandant |
| Betroffene Bereiche | Rechnungseingang, Betriebskostenabrechnung (§ 35a), Zahllauf (Einbehalt als Merkposten) |
| Überprüfung spätestens bei Meilenstein | G1 (Vorsteuer, Grenzen), G3 (§ 35a-Ausweis), G2 (Einbehalt) |
| Datum | 27.09.2026 |

## A-062

| Feld | Inhalt |
| --- | --- |
| Annahme | bved Standard-Datenaustausch 3.10 (Messdienstleister, Dateiadapter M40-02): Datumsfelder sind sechsstellig TTMMJJ ohne Jahrhundertregel im Standard (Q14). Der Parser liest zweistellige Jahre 00 bis 69 als 2000 bis 2069 und 70 bis 99 als 1970 bis 1999. Der Betrag eines Abrechnungsergebnisses ist wie beim bved Billing Result der Bruttogesamtbetrag der Kostenart (D-Satz Feld 8); Saldo und Vorauszahlungen bleiben nachrichtlich im Payload. Endet der Nutzungszeitraum eines D-Satzes nach dem Abrechnungszeitraum des L-Satzes, wird der Zeitraum auf das Ende des L-Satzes begrenzt. |
| Begründung | 0.1.3: keine erfundene Regel; die Jahrhundertregel ist nur Interpretation eines Formatfelds und wird an echten Beispieldateien bestätigt (OPEN_QUESTIONS M40-02). Es wird nichts gespeichert, solange die Vorschau nicht freigeschaltet ist. |
| Kennzeichnung | unkritisch (nur Vorschau, keine Speicherung, keine Geldwirkung) |
| Betroffene Bereiche | Messdienstleister, Dateiimport bved 3.10 |
| Überprüfung spätestens bei Meilenstein | Freischaltung der Übernahme von Abrechnungsergebnissen aus Dateien (M40-02), vor G3 und G4 |
| Datum | 27.09.2026 |

## A-063

| Feld | Inhalt |
| --- | --- |
| Annahme | Vier-Augen-Prinzip beim Mailversand (M20-04, `mhvp.communication.mail_approval`): (1) Der Kompetenzkatalog kennt bisher nur den Kontakttyp `authority` (Behörde); bis zu einer eigenen Kontaktkategorie für Gericht und Investor gelten zusätzlich die Kontakt-Tags `gericht`/`gerichte` und `investor`/`investoren` als externe Empfänger im Sinne des Modus `external_only`. Eine Nachricht ohne verknüpften Kontakt gilt vorsorglich als externer Empfänger. (2) Es existiert kein eigenes Abwesenheits- oder Vertretungsmodul; die Vertretungsregel bei Abwesenheit wird über eine eigene, schlanke Tabelle (`mail_approval_deputy`: abwesender Nutzer, Stellvertreter, Zeitraum, Grund als Freitext) geführt, ohne Verknüpfung zu einer Kalender- oder Urlaubsplanung. (3) Die Re-Authentifizierung (Passwort oder TOTP) gilt für die Freigabe durch eine zweite Person und den Superadmin-Bypass (ADR 0011); ein reiner Direktversand einer eigenen Ticketantwort ohne zweite Person (M20-03, Modus `off`, Ticket-Ausnahme) braucht keinen erneuten Nachweis, da hier keine zweite Freigabe stattfindet. |
| Begründung | 0.1.3: keine erfundene Rechtsregel, nur ein Produktschutz-Notbehelf, bis der Betreiber eine eigene Kontaktkategorie und ein Abwesenheitsmodul entscheidet (siehe `docs/OPEN_QUESTIONS.md` M20-04). Geldwirkung besteht nicht; das Risiko ist Fehlversand oder Kontoübernahme, dagegen wirken Re-Auth und Vier-Augen unabhängig von der genauen Kategorisierung. |
| Kennzeichnung | unkritisch für den Betrieb (Standardmodus `external_only` bleibt konservativ, da ein Kontakt ohne Kontakt als extern gilt); zu prüfen vor einer harten Zusage an Behörden/Gerichte, dass die Tag-Erkennung lückenlos ist |
| Betroffene Bereiche | Kommunikation, Mailversand, Vier-Augen-Prinzip |
| Überprüfung spätestens bei Meilenstein | Entscheidung eines eigenen Kontakttyps Gericht/Investor und eines Abwesenheits-/Vertretungsmoduls (M20-04) |
| Datum | 27.09.2026 |

## A-064

| Feld | Inhalt |
| --- | --- |
| Annahme | Preisstruktur (M27-01, `mhvp.platform.market_readiness.DEFAULT_PRICING`): Stufen S bis XL mit den Einheitenbereichen 1 bis 100, 101 bis 500, 501 bis 2.000 und ab 2.001, Zusatzmodule WEG, Buchhaltung, Banking, Portal, KI, eine Testphase ohne Dauer. Beträge sind nicht gesetzt. |
| Begründung | Regel 0.1.3: keine erfundenen Zahlen. Die Bereiche sind nur eine editierbare Ausgangsstruktur, damit der Betreiber Beträge und Grenzen pflegen kann; ein Angebot bleibt Entwurf, solange Beträge fehlen. |
| Kennzeichnung | unkritisch (kein Betrag, keine Geldwirkung); vor dem ersten Angebot an einen Drittmandanten durch den Betreiber zu bestätigen (OPEN_QUESTIONS M27-01-01) |
| Betroffene Bereiche | `mhvp.platform.market_readiness`, CRM `/plattform/preisliste`, Angebots-PDF |
| Überprüfung spätestens bei Meilenstein | vor G5 des ersten Drittmandanten |
| Datum | 27.09.2026 |

## A-065

| Feld | Inhalt |
| --- | --- |
| Annahme | Mietrechnung mit Umsatzsteuerausweis (M13-04a): Nummernkreis je Rechtsträger und Jahr mit dem festen Präfix `MR` (`MR-JJJJ-000001`), Steuerkennung des Rechtsträgers aus den Kontaktkennungen der Partei (USt-IdNr. vor Steuernummer), Rechnungsdatum standardmäßig der Erstellungstag, Dauerrechnung als eine Position je Monat aus den Sollstellungsposten |
| Begründung | 0.1.3: keine erfundene Rechtsregel; die Werte sind technische Vorgaben, damit der Entwurf abnehmbar ist. Präfix und Feldliste entscheidet der Betreiber mit dem Steuerberater (OPEN_QUESTIONS M13-04a) |
| Kennzeichnung | unkritisch, solange G1 geschlossen ist (nur Entwurf mit Wasserzeichen, kein Versand, keine Buchung); vor G1 zu bestätigen |
| Betroffene Bereiche | `mhvp.accounting.rent_invoice`, `rent_invoice_number_counter`, CRM Vertragsseite (Mietrechnungen) |
| Überprüfung spätestens bei Meilenstein | G1 des ersten Mandanten mit Gewerbemietverträgen mit Option |
| Datum | 27.09.2026 |

## A-066

| Feld | Inhalt |
| --- | --- |
| Annahme | Kontierungsvorschlag `is_deposit` (M12-01 Restpunkt, Kontierungsagent-Befund 22.09.2026): `open_item` trägt keine Forderungsart, die eine Kaution von Miete oder Hausgeld unterscheidet (`OpenItemKind` kennt nur receivable/payable, die Spalte `component` wird von `_apply_open_items` nie befüllt). `mhvp.banking.posting_proposal.stage1_for_transaction` leitet `is_deposit` stattdessen über den Vertrag ab: ein offener `Deposit`-Datensatz (`mhvp.contracts.models.Deposit`, Status `open`) desselben Vertrags mit exakt gleichem `amount_due` wie der offene Posten. Keine neue Spalte angelegt. |
| Begründung | 0.1.3/18.2: additive Spalten nur nach Rücksprache; die Ableitung über den Vertrag ist eine Heuristik (Betragsübereinstimmung), kein sicherer Fremdschlüssel, und kann bei zwei gleich hohen offenen Posten desselben Vertrags danebengreifen. |
| Kennzeichnung | unkritisch (nur ein Vorschlag, keine Buchung, 0.1.6); vor einer verlässlicheren Verknüpfung (z. B. `open_item.deposit_id`) durch den Betreiber zu bestätigen |
| Betroffene Bereiche | `mhvp.banking.posting_proposal` (`_is_deposit_item`, `stage1_for_transaction`) |
| Überprüfung spätestens bei Meilenstein | vor G2 (Zahlungsauslösung), wenn Kautionsvorschläge häufiger automatisiert bestätigt werden |
| Datum | 27.09.2026 |


## A-067

| Feld | Inhalt |
| --- | --- |
| Annahme | E-Mail-Signatur je Nutzer (Betreiberwunsch 27.09.2026, Migration 0215, `mhvp.communication.signatures`): Die Standardsignatur wird aus den Firmendaten des Mandanten-Seeds gerendert (HVM: Name, Position, Firma, Anschrift, Telefon und E-Mail nur wenn hinterlegt, Registerzeile "Amtsgericht Düsseldorf HRB 104762, Geschäftsführer Timo Müller", Website; Einzelunternehmen Timo Müller: Wortmarke, kurze Akzentlinie, c/o-Anschrift, ohne Funktionsbezeichnung und Registerangaben). Das Einzelunternehmen wird über `legal_form` (enthält "Einzelunternehm") erkannt. Ein Logo erscheint nur, wenn in der Signaturvorlage eine öffentliche https-URL hinterlegt ist; das als Dokument hochgeladene Briefbogenlogo wird nicht automatisch eingebettet (kein öffentlicher Abruf, kein CID-Anhang). Steuernummern und Bankverbindungen sind nie Teil der Signatur. Nachtrag Review 1.36.0: Die Signatur steht im gespeicherten Entwurfstext; bei Antwortentwurf, übernommenem Vorschlag, Playbook und Ticketantwort wird sie beim Anlegen eingefügt, bei allen anderen Entwürfen spätestens beim Einreichen. Der Versand hängt nichts an, die Freigabe zeigt genau den versendeten Text; vor 1.36.0 eingereichte Entwürfe gehen ohne Signatur hinaus. Beim Anlegen gilt die Signatur als vorhanden, wenn ihr gerenderter Text mit normalisiertem Leerraum im Entwurf steht; beim Einreichen zusätzlich, wenn der Entwurf eine Standardtrennzeile `-- ` als eigene Zeile enthält. Ein bearbeiteter Signaturblock oder eine seit dem Anlegen geänderte Position, Durchwahl, Vorlage oder Postfach führt so nicht zu einer zweiten Signatur; enthält ein noch nicht signierter Entwurf eingefügten Fremdtext mit Trennzeile, wird beim Einreichen keine Signatur angefügt, was vor der Freigabe im Text sichtbar ist. Zitierte Trennzeilen (`> -- `) und `--` ohne Leerzeichen zählen nicht. Die E-Mail-Zeile zeigt die Adresse des sendenden Postfachs; in der Vorschau genau ein freigegebenes persönliches Postfach des Nutzers im Mandanten, sonst entfällt sie. Die Mobilnummer der SMS-Bereitschaft (`membership.mobile_phone`) wird nicht verwendet, der Platzhalter {mobile} bleibt leer. Vorlagen kennen nur die bekannten Platzhalter, unbekannte werden beim Speichern abgelehnt und in bereits gespeicherten Vorlagen leer gerendert und mit Namen, ohne Werte, protokolliert; {{ und }} stehen für geschweifte Klammern. Versendet wird nur Klartext, die HTML-Signatur ist Vorschau. |
| Begründung | Vollständigkeit der Pflichtangaben in Geschäfts-E-Mails ist Gegenstand der Freigabe V14 (Firmendaten des Seeds, Telefon und E-Mail dort nicht hinterlegt); die Signatur ist eine Textvorlage, keine Rechtsprüfung. |
| Kennzeichnung | unkritisch (kein Geldfluss); Freigabe der Standardtexte und der Pflichtangaben durch die Geschäftsführung vor produktivem Versand (V14) |
| Betroffene Bereiche | `mhvp.communication.signatures`, `membership.position`/`phone`, `tenant_settings.signature_template`/`position_catalogue_extra`, Einstellungen Profil, Benutzer, Mandant |
| Überprüfung spätestens bei Meilenstein | vor G5 (Drittmandanten) und mit V14 |
| Datum | 27.09.2026 |

## A-068

| Feld | Inhalt |
| --- | --- |
| Annahme | Zuordnungsprüfung mit Rückfrage (Betreiberwunsch 27.09.2026, Migration 0216, `mhvp.communication.assignment` und `assignment_review`): Deterministische Regeln bewerten je Mail und Ticket Kontakt, Verwaltungsobjekt und Einheit mit festen Konfidenzen (Absenderadresse eindeutig 1,0, geteilt 0,6; Kundennummer 0,95; Telefonnummer 0,7; Vor- und Nachname 0,7, nur Nachname 0,5; Objektnummer 1,0; Straße mit Hausnummer 0,85, nur Straße 0,6; einziges Objekt aus Vertrag oder Objektbeziehung des Kontakts 0,8, mehrere 0,5; Einheitennummer 0,9; Wohnungslage 0,6; einzige Einheit aus Vertrag 0,85; bei Mails ohne Treffer der Absenderadresse ist der Kontakt auf 0,85 begrenzt, also stets Rückfrage). Ab 0,9 mit eindeutigem Spitzenkandidaten wird automatisch zugeordnet, zwischen 0,4 und 0,9 erfolgt die Rückfrage (Ja oder Nein), darunter kein Treffer. Ein KI-Vorschlag ergänzt nur Hinweise. Entscheidungen werden protokolliert und nur bei eingeschaltetem Schalter `ai_learning_examples_enabled` als Lernbeispiel gespeichert (ADR 0010). Nachtrag Review 1.36.0: Sicher ist ein Kontakt nur bei eindeutiger Absenderadresse eines aktiven Kontakts; jeder andere Kontaktkandidat und jede Einheit ohne Vertrag des Kontakts ist auf 0,85 begrenzt. Die Einheitennummer zählt nur nach einem Einheitenwort (Einheit, WE, Whg., Wohnung, Wohneinheit, Stellplatz, TG, optional mit Nr.) mit 0,6, eine einzige Einheit aus Vertrag 0,85, mehrere 0,5 (ersetzt den Startwert 0,9). Namen werden aus den ersten beiden Zeilen und dem Signaturblock gelesen; in Anredezeilen entfallen die Namen eigener aktiver Mitglieder, Anredewörter (zum Beispiel Damen, Herren, Morgen, Abend, Zusammen, Team, Familie) zählen nie als Name. Bei Mails zählt nur der Text ohne zitierte frühere Mails (Zeilen mit „>“ entfallen, der Text endet an Antwortmarken oder einem echten Kopfblock Von/From mit weiteren Kopfzeilen); Kundennummer und Telefonnummer werden im ganzen Text gesucht. Beim Eingang wird der Kontakt nur vorbelegt, wenn genau ein aktiver Kontakt die Absenderadresse trägt. Die Abrufe (GET) rechnen nur und speichern nichts; nicht gespeicherte Zeilen tragen eine feste, aus Vorgang und Dimension abgeleitete Kennung. Jede gespeicherte Zeile führt den Feldwert, gegen den sie gerechnet wurde (basis_id), getrennt von der Entscheidung (chosen_id). Eine Entscheidung sendet den gesehenen Feldwert (seen_value) und bei Ja den bestätigten Kandidaten (candidate_id); weicht der aktuelle Feldwert davon oder von basis_id ab, oder ist der Kandidat nicht Teil der Rückfrage, antwortet die API mit 409 (MHVP-COMM-0003 „Zuordnung inzwischen geändert“) und speichert nichts. Ein Ja korrigiert auch eine falsche Vorgabe, ist aber endgültig: jede weitere Entscheidung auf der Zeile endet mit 409, nur dasselbe Ja bei unverändertem Feld wird ohne Änderung bestätigt. Ein Nein sperrt die Zeile nicht. Nur eine offene Rückfrage wird überholt (superseded), wenn das Feld inzwischen anders gesetzt ist, und bleibt es. Jede gespeicherte automatische Zuordnung erzeugt einmal das Ereignis `assignment_review.auto`, bei Tickets zusätzlich einen Eintrag im Ticketverlauf. Die Sammelliste offener Rückfragen folgt der Postfachsichtbarkeit. Nachtrag 1.37.0 (sichere Kette, Betreiberauftrag 27.09.2026, Regel A80-01): Ist der Kontakt sicher (automatisch oder durch ein Ja bestätigt) und hat er genau einen aktiven Mietvertrag oder genau eine aktive Eigentümerschaft einer Einheit, werden deren Einheit und Objekt automatisch übernommen, nur in ein leeres Feld, mit Grund "eindeutiger Vertrag" beziehungsweise "eindeutiges Eigentum". Mehrere Verträge oder Einheiten, oder ein Mietvertrag und eine Eigentümerschaft auf verschiedenen Einheiten, bleiben die gewohnte Rückfrage mit diesen Kandidaten; Hinweise im Text (Einheitennummer nach einem Einheitenwort, Wohnungslage) ordnen die Kandidaten dort nur um, sie lösen nie selbst eine automatische Zuordnung aus. Ein unsicherer Kontakt leitet weiterhin weder Objekt noch Einheit ab. Ein bereits gesetztes Feld bleibt unangetastet; hält es bereits genau den Wert der Kette, bestätigt die Prüfung ihn erneut als `auto`. Ein Ja auf die Kontakt-Rückfrage löst die Prüfung von Objekt und Einheit sofort erneut aus. |
| Begründung | Produktschutz: Schwellen sind Startwerte ohne Rechtsbezug; sie sollen Fehlzuordnungen (Datenschutz, falsche Empfänger) vermeiden und werden anhand der protokollierten Entscheidungen nachjustiert. Die sichere Kette (1.37.0) ist eine reine Vereinfachung bei eindeutiger Vertrags- oder Eigentumslage, ohne die Sicherheitsregeln zum Kontakt zu lockern. |
| Kennzeichnung | unkritisch (kein Geldfluss); Schwellenwerte und Regelgewichte vom Betreiber nach Erfahrungswerten zu bestätigen |
| Betroffene Bereiche | `assignment_review`, `assignment.contact_sure_chain`, `POST /mail/ingest`, Gmail-Abruf, `POST /tickets`, `PATCH /tickets/{id}`, Komponente `AssignmentPrompt`, Komponente `ContactRoleBadges` (Mail- und Ticketdetail), `POST .../assignment-review/decide` |
| Überprüfung spätestens bei Meilenstein | vor G5 (Drittmandanten) |
| Datum | 27.09.2026 |

## A-069

| Feld | Inhalt |
| --- | --- |
| Annahme | Postfach-Übersicht (Betreiberwünsche 27.09.2026, Migration 0213, `mhvp.communication.duplicates` und `progress`): (1) Ein Postfach gilt als Sammelpostfach, wenn der lokale Teil der Adresse (vor dem @, bis zum ersten Punkt, Plus oder Bindestrich) info, post, buchhaltung, office, kontakt, verwaltung, rechnung, rechnungen, mail, service, zentrale, hausverwaltung, support, kundenservice, bewerbung oder team lautet; alle anderen Postfächer gelten als persönlich. Das Kennzeichen `mailbox.is_collective` wird beim Anlegen nach dieser Regel vorbelegt (bestehende Postfächer per Migration) und ist je Postfach änderbar. (2) Dieselbe Mail in mehreren eigenen Postfächern wird an der Message-ID erkannt, ersatzweise an Absender, Betreff, Zeitstempel und Text-Hash; die Kopie im persönlichen Postfach führt, bei zwei gleichartigen Postfächern die zuerst gespeicherte. Die Kopie im Sammelpostfach bleibt erhalten (Archivierung, Nachweis), erscheint nicht in der Übersicht und teilt Ticket und Thread. Kopien mit bereits verschiedenen Tickets werden im Wartungslauf nicht zusammengeführt, sondern gezählt. (3) "In Bearbeitung" gilt ab zugewiesenem Bearbeiter am Ticket, internem Ticketkommentar oder eingereichter Antwort (Status pending, sending, sent); ein nicht eingereichter Entwurf zählt nicht. Bearbeiter ist der zugewiesene Nutzer, sonst der Nutzer des jüngeren Ereignisses aus Antwort und Kommentar; angezeigt wird `User.display_name`. Nachtrag Review 1.36.0 zu (2): Eine gleiche Message-ID gilt nur dann als dieselbe Mail, wenn ein Inhaltsfingerabdruck aus Absender, Betreff, Text und Anhängen (Anzahl und SHA-256) übereinstimmt; sonst wird die Mail als eigene Nachricht gespeichert, auch wenn ein Verteiler sie verändert zustellt. Der Eingang serialisiert je Mandant und Mailschlüssel über eine Advisory-Sperre (`pg_advisory_xact_lock`), sodass parallele Abrufe zweier eigener Postfächer nur eine führende Mail anlegen. Meldet PostgreSQL dabei einen Deadlock, wird nur diese Mail im Savepoint zurückgerollt und in `mailbox_sync_retry` vermerkt; der nächste Lauf nimmt sie als verknüpfte Kopie auf, höchstens bis `MAX_ATTEMPTS` (5) Versuche erreicht sind. Weiterleitungssperre: eine Rechnung wird weder automatisch noch manuell erneut an die Buchhaltung weitergeleitet, wenn eine andere Eingangsmail des Mandanten mit derselben Message-ID bereits vorgemerkt oder versendet ist (Status „duplicate“ bzw. 409 ohne Übersteuerung); eine Weiterleitung ohne Gmail-Postfach erhält den Status „not_sent“ und sperrt nicht. Verwendet ein Lieferantensystem dieselbe Message-ID für verschiedene Rechnungen, ist die zweite Rechnung außerhalb des Systems an die Buchhaltung zu geben. Produktschutz gegen doppelte Zahlung, keine Rechtsgrundlage. |
| Begründung | Betreiberwunsch vom 27.09.2026 ohne Vorgabe zur Adressregel und zur Definition des Bearbeitungsbeginns; Regeln sind rein organisatorisch und ohne Geldwirkung. |
| Kennzeichnung | unkritisch; Bestätigung der Adressliste und der Bearbeitungsdefinition durch den Betreiber |
| Betroffene Bereiche | `mailbox.is_collective`, `message.duplicate_of_id`, `GET /mail/messages` (Felder `in_progress`, `handler_user_id`, `handler_display_name`, Parameter `include_duplicates`), `POST /mail/maintenance/link-duplicates`, CRM Postfachliste, `mhvp.communication.sync_retry`, `POST /mail/messages/{id}/forward-invoice`, Nachlaufjob `forward_queued` |
| Überprüfung spätestens bei Meilenstein | vor G5 (Drittmandanten) |
| Datum | 27.09.2026 |

## A-070

| Feld | Inhalt |
| --- | --- |
| Annahme | Folgevorgang statt Wiedereröffnung (Regel M19-10, Migration 0219, `mhvp.tickets.follow_up`): Die Frist `tenant_settings.ticket_reopen_window_days` (Standard 30) zählt Kalendertage in der Betreiberzeitzone zwischen dem Tag von `ticket.resolved_at` und dem Tag des Maileingangs, die Grenze zählt mit; Zeilen ohne `resolved_at` nutzen die letzte Änderung. Das Folgeticket übernimmt Objekt, Einheit und Kontakt des Vorgängers vor den Werten aus der Mail (die Mail füllt nur Lücken, eine Einheit nie ohne Objekt des Vorgängers), nicht aber Bearbeiter, Priorität, Vorlage oder Thema; diese folgen den Regeln eines neuen Mailtickets. Ein zusammengeführtes Ticket führt zum Zielticket, ein abgeschlossenes Ticket mit Folgeticket zum Folgeticket; je Ticket höchstens ein Folgeticket. Eine automatische Antwort wird ausschließlich an den Kopfzeilen `Auto-Submitted` (Wert nicht `no`), `X-Autoreply`, `X-Autorespond` oder `Precedence: auto_reply` erkannt, an das Ticket des Vorgangs gehängt und öffnet weder wieder noch legt sie ein Folgeticket an; Betreff und Text (zum Beispiel "Abwesenheitsnotiz") werden bewusst nicht ausgewertet, um keine echte Kundenmail zu verschlucken. |
| Begründung | Betreiberentscheidung vom 28.09.2026 zur Frist (30 Tage, je Mandant änderbar), getroffen durch den Lead im Rahmen des Mandats "alle Entscheidungen selbst abwägen"; Zählweise, Vorbelegung und Erkennung automatischer Antworten sind nicht vorgegeben und rein organisatorisch. |
| Kennzeichnung | unkritisch (kein Geldfluss, keine gesetzliche Frist, keine Löschung); Bestätigung der Zählweise und der Kopfzeilenliste durch den Betreiber |
| Betroffene Bereiche | `POST /mail/ingest`, Gmail-Abruf, `GET /tickets/{id}` (`follow_up_of`, `follow_ups`, `follow_up_of_ticket_id`), `GET`/`PATCH /tenant/settings` (`ticket_reopen_window_days`), CRM Ticketdetail und Einstellungen Mandant |
| Überprüfung spätestens bei Meilenstein | vor G5 (Drittmandanten) |
| Datum | 28.09.2026 |

## A-071

| Feld | Inhalt |
| --- | --- |
| Annahme | Lern-Workflow (Regel M9-11, Migration 0218): (1) Ein Regelvorschlag entsteht nach 5 gleichen manuellen Entscheidungen für denselben Absender ohne widersprechende Entscheidung dazwischen (Mandanteneinstellung `rule_proposal_threshold`, zulässig 2 bis 50). (2) Absender eines Tickets ist die Adresse seiner ersten eingehenden Mail. (3) Ein Domainmuster gilt nur für Domains, die kein öffentlicher Maildienst sind (gmail.com, gmx.de, web.de, t-online.de, outlook.com und weitere, Liste `SHARED_MAIL_DOMAINS` in `mhvp.automation.learning`) und keinem eigenen Postfach gehören, und nur mit Entscheidungen von mindestens zwei Adressen. (4) Als Ticketkategorie im Sinne des Betreiberwunsches gilt das Ticketthema (`topic`), weil nur dieses per PATCH manuell gewählt wird; die Vorlagenkategorie bleibt unberührt. (5) Abgelehnte Vorschläge erscheinen erst bei doppelter Anzahl gleicher Entscheidungen wieder. |
| Begründung | Betreiberwunsch vom 27.09.2026 ("etwa fünfmal"); ohne Vorgabe zu Domainregel und Wiedervorlage. Der Vorschlag wirkt nie selbst, erst die Annahme durch ein Mitglied legt eine Regel an; kein Geldfluss, keine Freigabestufe betroffen. |
| Kennzeichnung | unkritisch; Schwelle, Domainliste und Wiedervorlage vom Betreiber zu bestätigen |
| Betroffene Bereiche | `automation_rule_proposal`, `tenant_settings.rule_proposal_threshold`, `GET /automation/rule-proposals`, `POST /automation/rule-proposals/{id}/accept`, `POST /automation/rule-proposals/{id}/reject`, Aktion `assign_record`, Ereignis `ticket.topic_changed`, CRM `/einstellungen/regelvorschlaege` |
| Überprüfung spätestens bei Meilenstein | vor G5 (Drittmandanten) |
| Datum | 27.09.2026 |

## A-072

| Feld | Inhalt |
| --- | --- |
| Annahme | Schadenbearbeiter (Regel INT-SDT-01, Migration 0222): (1) Statusabbildung lokal nach extern `new` zu `open`, `in_progress` zu `in_progress`, `waiting` zu `waiting`, `done` zu `resolved`, `closed` zu `closed`; `rejected` wird nicht gesendet; empfangene Werte werden roh gespeichert und ändern den lokalen Status nie. (2) Antwortfelder der Gegenseite werden tolerant gelesen (`id` oder `mdvId`, `commentId` oder `id`, `attachmentId` oder `id`, `downloadUrl`), eine Liste als `items` oder als bloßes Array. (3) `entityId` eines Ticketereignisses ist die Ticket-ID der Gegenseite, sonst `payload.ticketId`. (4) Die Einheit geht als zusätzliches optionales Feld `unitExternalId` mit (Vertrag Abschnitt 11 erlaubt neue optionale Felder). (5) Der Abgleich läuft alle 15 Minuten mit `updatedSince` gleich dem jüngsten gesehenen `updatedAt` abzüglich 5 Minuten Überlappung. (6) Eingehende Kommentare werden als interne Kommentare gespeichert (nicht im Portal sichtbar). (7) Downloads nur vom Host der Basisadresse, höchstens 25 MB. |
| Begründung | Der Vertragsentwurf nennt Felder, aber keine vollständigen Schemas und keine Statusliste; die Annahmen sind so gewählt, dass nichts automatisch geändert, gelöscht oder übermittelt wird, was ein Mitglied nicht ausdrücklich gewählt hat. |
| Kennzeichnung | unkritisch (kein Geldfluss, keine Frist); Datenschutz über SDT-01 gesperrt, Feldnamen und Statusliste über SDT-02 und SDT-03 zu bestätigen |
| Betroffene Bereiche | `mhvp.integrations.schadenstool`, `/integrations/schadenstool/*`, CRM `/einstellungen/schnittstellen/schadenbearbeiter`, Ticketdetail |
| Überprüfung spätestens bei Meilenstein | vor produktiver Aktivierung der Anbindung |
| Datum | 28.09.2026 |

## A-073

| Feld | Inhalt |
| --- | --- |
| Annahme | Erfassungsstandards (Regeln ES-01 bis ES-11): (1) Als Fristen mit verantwortlicher Person gelten die Fälligkeiten offener Tickets (`ticket.due_on` mit Bearbeiter `assignee_user_id`); abgeleitete Fristen der Fristenliste und eigene Kalendereinträge fallen nicht darunter. (2) Die Namensheuristik (Komma, Vorname im Nachnamen, Firmenbestandteile) ist bewusst einfach und darf Fehlalarme erzeugen, weil sie nur warnt. (3) Die harte PLZ Prüfung gilt nur für das Land DE, nur bei Anlage oder Änderung von PLZ oder Land über die API; Importe übernehmen Werte unverändert und erscheinen im Bericht. (4) Der Bericht verlangt das Recht Kontakte lesen und zeigt je Abschnitt höchstens 200 Einträge. |
| Begründung | Die Standards sollen Daten angleichen, ohne Arbeit zu blockieren oder bestehende Daten zu verändern; eine eigene verantwortliche Person gibt es im Datenmodell nur am Ticket. |
| Kennzeichnung | unkritisch (kein Geldfluss, keine Rechtsfrist, keine automatische Änderung) |
| Betroffene Bereiche | `mhvp.dataquality`, `POST/PUT/PATCH /properties`, `GET /data-quality/report`, `POST /data-quality/check`, CRM Objekt, Kontakt und Ticketformulare, `/einstellungen/datenqualitaet` |
| Überprüfung spätestens bei Meilenstein | vor G5 (Drittmandanten) |
| Datum | 28.09.2026 |

## A-074

| Feld | Inhalt |
| --- | --- |
| Annahme | Rückkanal Gmail zu Plattform (Regel M20-08): (1) Das Sammelpostfach entscheidet über die Erledigung; mehrere Sammelpostfächer entscheiden gemeinsam (UND); ohne Sammelpostfach müssen alle Kopien archiviert sein. (2) Papierkorb zählt wie Archiv, endgültiges Löschen erledigt die Mail ohne Ticketabschluss. (3) Spam entscheidet nie und blockiert nicht. (4) Standardstufe `record_only`; Beruhigungsfrist 600 Sekunden; Karenz des Abgleichs 300 Sekunden; Abgleich stündlich, 90 Tage rückwirkend, höchstens 200 Einzelabfragen je Lauf. (5) Gmail nennt keinen Urheber einer Archivierung; bei gemeinsam genutztem Postfach ist der Nutzer nicht erkennbar. (6) Eine Wiederherstellung in Gmail außerhalb des Wiedereröffnungsfensters lässt das Ticket geschlossen und hält nur die Mail offen; nie ein Folgeticket. (7) Ein wieder geöffnetes Ticket ist in Bearbeitung und damit vor einem erneuten automatischen Abschluss geschützt, solange `gmail_close_assigned_tickets` aus ist. |
| Begründung | Betreiberstandard vom 28.09.2026 (info@ und timo@); die Werte sind konservativ gewählt, damit Rückgängig, Zurückstellen und Doppelbearbeitung keine Fehlabschlüsse erzeugen. |
| Kennzeichnung | unkritisch (kein Geldfluss, keine Rechtsfrist; Beschäftigtendatenschutz und Löschkonzept als offene Punkte M20-08-Q7 und M20-08-Q8) |
| Betroffene Bereiche | `mhvp.communication.gmail_state`, `mhvp.communication.gmail_done`, `PATCH /tenant/settings`, `/mail/messages`, `/mail/mailboxes`, CRM Mailübersicht, Maildetail, Einstellungen Mandant und Postfächer |
| Überprüfung spätestens bei Meilenstein | vor dem Umschalten auf `done` beim Mandanten HVM (Spike, Abschnitt 13 der Regel) |
| Datum | 28.09.2026 |

## A-075

| Feld | Inhalt |
| --- | --- |
| Annahme | Beim Eigentümerwechsel werden die am Eigentumsübergang gültigen Sollbeträge (Zahlungen), der Zahlungsplan und die vertragsbezogenen Umlagewerte des Veräußerers als unveränderte Kopie ab dem Übergang auf den Vertrag des Erwerbers übernommen (abwählbar). Das ist eine Datenübernahme: Der Erwerber setzt die laufenden Vorschüsse in bisheriger Höhe fort, bis der Wirtschaftsplan etwas anderes vorsieht. Vertragsbezogene Umlagewerte des Veräußerers enden am Vortag; Werte mit Beginn nach dem Ende bleiben unverändert. |
| Begründung | Ohne Übernahme mussten Hausgeld und Rücklage nach jedem Wechsel von Hand nacherfasst werden (Lücke laut Anleitung Eigentümerwechsel). Die Kopie trifft keine Aussage über Vorschussschuldner oder Abrechnungsspitze (Regel W07 nicht freigegeben, P01 offen, M24-01); Rückstände werden nicht umgebucht. |
| Kennzeichnung | unkritisch (kein Geldfluss, keine Buchung, G1 und G4 geschlossen; Übernahme in der Vorschau sichtbar und abwählbar) |
| Betroffene Bereiche | `POST /contracts/{id}/ownership-transfer`, `GET /contracts/{id}/ownership-transfer/preview`, CRM Vertrags- und Einheitenseite (`OwnershipTransfer`), `docs/rules/M5-03-eigentuemerwechsel-sollbetraege.md` |
| Überprüfung spätestens bei Meilenstein | vor G4 (WEG-Abrechnung), zusammen mit W07 und P01 |
| Datum | 28.09.2026 |

## A-076

| Feld | Inhalt |
| --- | --- |
| Annahme | Fristtypen und eigene Fristen (Regel WS-01): (1) Das Vertragsmodell trägt keine Kündigungsfrist; die Prüfung beim Beenden nutzt die vom Benutzer eingegebenen Monate und Tage (Vorbelegung des Formulars drei Monate zum Monatsende, nur als Eingabehilfe, kein Rechtswert) und addiert Kalendermonate mit Begrenzung auf die Monatslänge. (2) Die Dauer eines Fristtyps wird als Auslösedatum plus Monate plus Tage berechnet; ein Typ ohne Dauer verlangt die Eingabe der Fälligkeit. (3) Die verantwortliche Person einer Frist erhält die Vorfristbenachrichtigung allein; ohne Person gehen sie wie bei allen Fristarten an die Inhaber von `tickets:update`. (4) Die Checkliste Verwalterwechsel bildet die zehn Punkte der Handlungsanweisung ab; je Objekt ist eine offene Liste dieser Art möglich. |
| Begründung | Die Handbuchlücken verlangen Fristtypen und Prüfungen ohne Rechtsaussage; ein Vertragsfeld für die Kündigungsfrist ist eine offene Betreiberentscheidung (WS-01-Q2). |
| Kennzeichnung | unkritisch (kein Geldfluss, keine Rechtsfrist, keine Sperre) |
| Betroffene Bereiche | `mhvp.workspace.deadlines`, `mhvp.workspace.deadline_routers`, CRM Fristen, Einstellungen Fristtypen, Vertrag beenden, Objektseite, Mieterhöhungsfall |
| Überprüfung spätestens bei Meilenstein | Entscheidung WS-01-Q1 und WS-01-Q2 |
| Datum | 28.09.2026 |

## A-077

| Feld | Inhalt |
| --- | --- |
| Annahme | Schwellen und Fenster des lernenden Buchhalters (ADR 0014, Fahrplan M12 Abschnitt 3.3 und 3.4) sind Produktschutz-Standards ohne empirische Basis: Stufe L1 ab 20 Entscheidungen in 90 Tagen und precision_manual 0,95; Stufe L2 nach 30 Tagen L1, 50 Entscheidungen, 0,98; Stufe L3 nach 60 Tagen L2, 100 Automatikbuchungen, Fehlerquote 0,005; Regelvorschlag ab 5 gleichen bestätigten Entscheidungen (tenant_settings.bank_rule_proposal_threshold, Bereich 2 bis 50, folgt in S5); Konfidenz einer Regel 0,9 mal 0,5 hoch Widersprüche der letzten 90 Tage; Historie Stufe 1d 0,4 plus 0,1 je konsistentem Fall, Deckel 0,85, Mindestnachweis zwei; Verfall von Regeln ohne Treffer nach 180 Tagen. Je Mandant nur nach oben veränderbar. In S0 und S1 sind noch keine dieser Schwellen wirksam; jede Runde des Entscheidungsprotokolls trägt fest die Stufe L0. |
| Begründung | Der Fahrplan legt die Werte vorab fest (Regel 0.1.8: Sollwerte vor dem Ergebnis), eine empirische Grundlage entsteht erst mit dem anonymisierten HVM-Testbestand (M12-02) und dem Entscheidungsprotokoll; bis dahin ist konservativ besser als kalibriert. |
| Kennzeichnung | unkritisch, solange keine Stufe über L0 aktiv ist (kein Geldfluss); vor Aktivierung von L1 bis L3 mit dem Testbestand neu bewerten und nie als Rechtsanforderung darstellen |
| Betroffene Bereiche | `mhvp.banking.proposals` (Feld `level`), spätere Module `levels.py`, `learning.py`, `verifiers.py`, `docs/rules/M12-04-lernender-buchhalter.md` |
| Überprüfung spätestens bei Meilenstein | S4 (Stufe L1) und vor dem G1-Antrag |
| Datum | 28.09.2026 |

## A-078

| Feld | Inhalt |
| --- | --- |
| Annahme | Merkmale und Snapshot des Entscheidungsprotokolls (`mhvp.banking.features`, Regel M12-04): (1) Der Merkmalshash umfasst Umsatz (Betrag, Buchungstag, Zweck, Gegenname, IBAN-Fingerabdruck, Mandats- und End-to-End-Referenz, Gläubiger-ID, Transaktionscode), die freigegebenen und aktiven Regeln des Rechtsträgers, die offenen Forderungen mit Nachweismerkmalen und die offenen Verbindlichkeiten zum Buchungstag; jede Änderung dieser Fakten macht einen offenen Snapshot veraltet (Zustand expired, neue Runde). (2) Gespeichert wird nur eine minimierte Zusammenfassung (Betrag, Richtung, Buchungstag, IBAN-Fingerabdruck, Kennungen von Regeln, Posten und Rechnungen, Vorhandensein von Mandats- und End-to-End-Referenz, Transaktionscode); Gegenname und Verwendungszweck stehen nur am Umsatz selbst. (3) Der Buchungstext zählt beim Diff nicht als Änderung, gewertet werden Posten, Beträge, Gegenkonto und Skonto. (4) Ohne gewählten Vorschlag gilt der Vorschlag mit der höchsten Konfidenz als Referenz; die Wahl eines anderen Vorschlags ist Wahl, keine Änderung. (5) Massenbestätigungen werden mit Kennzeichen bulk erfasst und zählen später mit geringerem Gewicht. |
| Begründung | Ein Snapshot ist nur als Grundwahrheit brauchbar, wenn erkennbar ist, ob die Person dieselben Fakten sah wie das System (Hash), und wenn der Speicher so wenig Personenbezug wie möglich trägt (M12-06). |
| Kennzeichnung | unkritisch (kein Geldfluss, nur Protokoll); Datenschutz über M12-06 gesperrt |
| Betroffene Bereiche | `mhvp.banking.features`, `mhvp.banking.decisions`, `mhvp.banking.proposals`, `posting_decision` |
| Überprüfung spätestens bei Meilenstein | S3 (Gedächtnis Stufe 1d) und Datenschutzprüfung M12-06 |
| Datum | 28.09.2026 |

## A-079

| Feld | Inhalt |
| --- | --- |
| Annahme | Ereignisverbrauch und Grundcodes (ADR 0014, B03): (1) Der Watermark-Job `mhvp.banking.process_events` läuft jede Minute mit 5 Sekunden Nachlauf und verarbeitet höchstens 500 Ereignisse je Mandant und Lauf; die erste Ausführung positioniert nur den Wasserstand, ältere Ereignisse sind Verlauf. (2) Ein Storno im Buchungskreis setzt den zugehörigen Bankumsatz auf offen; die Satznummer bleibt als Verlauf am Umsatz, eine zweite Neubuchung ist erst nach erneutem Storno möglich. (3) Bankrückgaben (`payments.record_return`) erzeugen kein Ereignis `journal_entry.reversed` und setzen den ursprünglichen Ausgang nicht zurück. (4) Der Grundcode eines Stornos ist eine geschlossene Liste (input_error, wrong_assignment, wrong_amount, wrong_date, duplicate, bank_return, run_reversal, automation_error, other) mit Standard other für bestehende Aufrufer. (5) Generische Gegenpartei-Namen (Liste je Mandant) und die Werktagslogik der Nachkontrolle (nächster Werktag nach dem bundeseinheitlichen Kalender, ohne Landesfeiertage) werden erst mit S5 und S6 eingeführt und dann hier ergänzt. |
| Begründung | Buchungskreis und Bankseite dürfen sich nicht gegenseitig importieren; die asynchrone Verarbeitung mit Wasserstand ist das bestehende Muster (M9-02) und hält die Buchungstransaktion frei von Bankseiteneffekten. |
| Kennzeichnung | unkritisch (Storno und Neubuchung bleiben Handlungen einer Person; kein Geldfluss durch den Job) |
| Betroffene Bereiche | `mhvp.banking.events_consumer`, `mhvp.banking.tasks`, `mhvp.accounting.services.reverse`, `mhvp.banking.matching.book_payment` |
| Überprüfung spätestens bei Meilenstein | S6 (Runner und Nachkontrolle) |
| Datum | 28.09.2026 |

## A-080

| Feld | Inhalt |
| --- | --- |
| Annahme | Gedächtnis Stufe 1d und Kreditorverlauf (`mhvp.banking.history`, Fahrplan M12 S3 und S7): (1) Je Vorschlag werden höchstens die 20 jüngsten bestätigten Entscheidungen von Personen derselben Gegenpartei (IBAN-Fingerabdruck oder Gläubiger-ID), desselben Rechtsträgers und derselben Richtung gelesen; das Muster ist die Menge der Gegenkonten der Buchung ohne das Bankkonto. (2) Konfidenz 0,4 plus 0,1 je konsistentem Fall (Massenbestätigung 0,05), Deckel 0,85, mal 0,5 je Widerspruch (Storno desselben Musters, anderes Muster), mindestens zwei konsistente Fälle, nie eindeutig; das zuletzt gewählte Muster gilt als Referenz. (3) Periodizität wird nur genannt (mindestens drei datierte Fälle, alle Abstände höchstens 7 Tage vom Medianabstand, Klassen monatlich, zweimonatlich, vierteljährlich, halbjährlich, jährlich) und löst nichts aus. (4) Ein Vertrag hinter dem ersten ausgeglichenen Posten einer Entscheidung, der vor dem Buchungstag endete, schließt den Fall aus; dasselbe gilt für Regeln mit Vertragsbindung. (5) Eine verknüpfte gebuchte Rechnung ergibt die Quelle invoice mit Kreditorenkonto, offenem Posten und Kostenkonten der Positionen (Konfidenz nach match_basis: Betrag und Rechnungsnummer 0,9, durch eine Person 0,9, Betrag und IBAN 0,7; eindeutig nur bei vollem Restbetrag und nicht bei Betrag und IBAN allein); mehrere verknüpfte Rechnungen ergeben unklar. (6) Die End-to-End-Referenz eines eigenen Zahlungsauftrags derselben Rechnung oder desselben Postens zählt als starkes Nachweismerkmal des Verbindlichkeitsabgleichs; Buchungstexte von Sachkonten sind nur ein Hinweis (0,3) und nur bei genau einem passenden Konto; ein erkanntes Transferpaar schlägt das Bankkonto der Partnerseite vor (0,9, nie eindeutig). (7) Belegeingang: je Rechnungsposition höchstens drei Konten aus den 50 jüngsten Rechnungen des Ausstellers im Buchungskreis (Dubletten und ersetzte Versionen ausgenommen) und den Gegenkonten seiner bestätigten Bankbuchungen; Reihenfolge gleicher Positionstext, gleiche Position, Häufigkeit; Umlagefähigkeit, Kostenart, § 35a und Umsatzsteuer werden nie übernommen. |
| Begründung | Der Fahrplan legt Basis, Schritt, Deckel und Mindestnachweis fest (Regel 0.1.8); Lesegrenzen, Gewichte von Widersprüchen und Massenbestätigungen, Toleranz der Periodizität und die Rangfolge im Belegeingang sind Produktschutz-Standards ohne empirische Basis und werden mit dem Testbestand M12-02 neu bewertet. |
| Kennzeichnung | unkritisch (nur Vorschläge, kein Geldfluss, keine Buchung; nur mit Mandantenschalter `learning_bookkeeper_enabled` sichtbar, Datenschutzauflagen unter M12-06) |
| Betroffene Bereiche | `mhvp.banking.history`, `mhvp.banking.posting_proposal`, `mhvp.banking.features`, `GET /banking/transactions/{id}/posting-proposals`, `GET /receipts/drafts/{id}` mit `ledger_id` und `provider_contact_id`, `POST /receipts/drafts/{id}/confirm`, CRM Belegeingang (Quelle Verlauf) |
| Überprüfung spätestens bei Meilenstein | S5 (Regelvorschläge) und Testbestand M12-02 |
| Datum | 29.09.2026 |

## A-081

| Feld | Inhalt |
| --- | --- |
| Annahme | Bankoberfläche BK-2 (Regel UI-BANK-01): (1) Die Umsatzliste lädt 50 Umsätze je Seite über `limit` und `offset`; die Schnittstelle liefert keine Gesamtzahl, deshalb gilt eine Seite als letzte, sobald weniger als 50 Zeilen kommen. (2) Der Richtungsfilter (Eingang, Ausgang) wirkt auf die geladene Seite, weil `GET /banking/transactions` keinen Richtungsparameter kennt. (3) Die Massenbestätigung nimmt höchstens 200 Umsätze je Auswahl (Schnittstelle erlaubt 1.000) und nur Vorschläge der Stufe 1 mit `unambiguous` oder Quelle `rule`; Historie- und KI-Vorschläge werden nie vorausgewählt. (4) Als Gegenkonto werden aktive Konten ohne `is_system`, ohne `property_bank_account_id` und ohne Kategorie `bank` angeboten; bei Transferpaaren nur fremde Bankkonten desselben Buchungskreises. (5) Offene Posten werden zum heutigen Stichtag geladen. (6) MT940-Dateien werden beim Upload mit dem Typ `text/plain`, CSV mit `text/csv` an den Dokumentenspeicher übergeben, weil Browser für `.sta` keinen zulässigen Typ senden; der Dateiname bleibt erhalten und steuert die Formaterkennung. (7) Namen der Rechtsträger für Summen und Regelanlage stammen aus `GET /banking/accounts` (Recht `accounting:read`), nicht aus `GET /tenant/legal-entities` (Recht `members:read`). |
| Begründung | Die Oberfläche ändert die Schnittstelle nicht (Auftrag BK-2); die Werte sind Bedienstandards ohne Geldwirkung und lassen sich später serverseitig ersetzen (Richtungsfilter, Gesamtzahl). |
| Kennzeichnung | unkritisch (keine Buchung ohne Bestätigung einer Person, kein Gate, keine Frist) |
| Betroffene Bereiche | `apps/web-crm/src/components/banking/*`, `/bank`, `/bank/regeln`, `/bank/abstimmung`, BFF-Allowlist |
| Überprüfung spätestens bei Meilenstein | Plan M12 Schritt S4 (Klassenrouter und Ein-Klick-Übernahme) |
| Datum | 28.09.2026 |

## A-082

| Feld | Inhalt |
| --- | --- |
| Annahme | Lexware Office (Regel INT-LEXO-01): (1) Die Postanschrift (`label=postal`, sonst die primäre Anschrift) ist die Rechnungsadresse in Lexware Office. (2) Die primäre E-Mail und das primäre Telefon werden nach Label zugeordnet (`work` zu `business`, `mobile`, `fax`, `private`, sonst `other`); beim Aktualisieren wird die Liste ersetzt, die in Lexware Office bereits belegt ist. (3) Warteschlangeneinträge in Endzuständen werden nach 90 Tagen gelöscht. (4) Die verwaltende Gesellschaft (`LegalEntityKind.MANAGER`) ist für die Rechnungsart Hausverwaltung vorbelegt; Makler und Beratung werden vom Betreiber zugeordnet. (5) Eine Standardkonfiguration ohne Gesellschaft bleibt als Alias der bisherigen Endpunkte bestehen. |
| Begründung | Die Herstellerdokumentation kennt je Kontakt genau eine Rechnungs und Lieferadresse und Listen je Art; ohne eine Zuordnung kann keine Änderung übertragen werden. Die Fristen und Vorbelegungen sind Betriebsentscheidungen ohne Geldbezug. |
| Kennzeichnung | unkritisch (kein Geldfluss, keine Rechtsfrist; Bankdaten sind ausgeschlossen) |
| Betroffene Bereiche | `mhvp.integrations.lexoffice_ext`, Migration 0233, Einstellungen Schnittstellen Lexware Office |
| Überprüfung spätestens bei Meilenstein | Freigabe ADR 0015 (docs/OPEN_QUESTIONS.md LEXO-06, LEXO-09, LEXO-12) |
| Datum | 29.09.2026 |

## A-083

| Feld | Inhalt |
| --- | --- |
| Annahme | Der Wissenskontext eines KI-Laufs (`mhvp.ai.knowledge`) umfasst höchstens 30 freigegebene Einträge, 20.000 Zeichen insgesamt und 2.000 Zeichen je Eintrag (längere Einträge werden sichtbar gekürzt). Ein freigegebener Eintrag gilt nach 180 Tagen ohne Änderung als "lange nicht geprüft" (`STALE_AFTER_DAYS`); das ist ein Hinweis in der Oberfläche ohne Folge für Status oder Verwendung. Die Playbook-Zuordnung erhält einen Bonus von 0,2 auf den Schlagwortwert, wenn die deterministische Mailkategorie der Playbook-Kategorie entspricht. |
| Begründung | Der Master-Prompt nennt keine Obergrenzen für den Kontext und keine Prüffrist für Wissenseinträge. Ohne Obergrenze wächst der Prompt mit der Wissensbasis (Produktionsfehler 29.09.2026, Eingabe über 272.000 Token). Die Prüffrist ist Produktschutz, kein Rechtsbezug. |
| Kennzeichnung | unkritisch, Konstanten in `mhvp.ai.knowledge` und `mhvp.communication.suggest`; Änderung ohne Migration möglich |
| Betroffene Bereiche | Kontext-Chat (answer_question), Mail-Vorbereitung, KI-Vorschlag je Mail |
| Überprüfung spätestens bei Meilenstein | nach den ersten Auswertungen der Rückmeldungen (hilfreich / nicht hilfreich) mit echten Daten |
| Datum | 29.09.2026 |

## A-084

| Feld | Inhalt |
| --- | --- |
| Annahme | Das CRM darf als installierbare Hülle (Manifest, Service Worker, Offline Seite) auf dem Home Bildschirm abgelegt werden, obwohl der Master-Prompt in Abschnitt 3.1 nur das Portal als PWA nennt. Der Service Worker hält ausschließlich die Offline Seite und die Icons vor; API Antworten, Seiten und Dokumente werden nie zwischengespeichert. Der Middleware Matcher wird nur um sw.js, offline.html, manifest.webmanifest und PNG Dateien direkt unter icons/ erweitert. Fotos werden im Portal vor dem Hochladen clientseitig auf höchstens 1.600 Pixel Kantenlänge verkleinert (JPEG, Qualität 0,85); Dateien unter 400 KB und nicht dekodierbare Dateien (zum Beispiel HEIC auf Android) gehen unverändert an den Server, der die Metadaten entfernt (M30-04). |
| Begründung | Betreiberentscheidung M30-08 vom 28.09.2026 (Plan M31, offene Entscheidung 5); Produktschutz für die Arbeit vor Ort auf Tablet und Handy, keine Rechtspflicht. Ohne Datencache entsteht kein neuer Speicherort für personenbezogene oder finanzielle Daten auf dem Gerät (Regel 0.1.3, 0.1.13). Die Verkleinerung spart Datenvolumen im Mobilfunk; die Grenzwerte sind Erfahrungswerte, keine fachliche Vorgabe. |
| Kennzeichnung | unkritisch (kein Geldfluss, keine Rechtsfrist; kein lokaler Entwurf, keine Offline Erfassung, siehe M30-07) |
| Betroffene Bereiche | `apps/web-crm/public/sw.js`, `apps/web-crm/src/app/manifest.ts`, `apps/web-crm/src/middleware.ts`, `apps/web-portal/src/lib/image-downscale.ts`, ADR 0017 |
| Überprüfung spätestens bei Meilenstein | Abnahme M31 durch den Betreiber auf Android Chrome und iPad Safari; Entscheidung M30-07 (Offline Erfassung) und M31 Entscheidung 6 (Thumbnail Caching) |
| Datum | 29.09.2026 |

## A-085

| Feld | Inhalt |
| --- | --- |
| Annahme | Eignungsschwellen der Automatikstufen (Regel M12-05, `mhvp.banking.levels.ELIGIBILITY`): L1 ab 20 Entscheidungen von Personen in 90 Tagen und Präzision der gezeigten Vorschläge von mindestens 0,95; L2 zusätzlich 30 Tage auf L1, 50 Entscheidungen und 0,98; L3 zusätzlich 60 Tage auf L2, 100 Automatikbuchungen und Fehlerquote höchstens 0,005. Automatische Herabstufung bei Fehlerquote über 0,02 (L3 0,01) in 30 Tagen oder drei Korrekturen einer L1-Klasse. Anhebung nur eine Stufe je Antrag. |
| Begründung | Fahrplan Abschnitt 3.3 und 3.4 nennt die Werte als Produktschutz-Standards ohne empirische Basis; der Master-Prompt verlangt Nachkontrolle und Grenzen, keine Zahlen. |
| Kennzeichnung | unkritisch für Geld: die Stufen buchen nur unter aktiver Regel mit Verifier; je Mandant nur nach oben veränderbar; nie als Rechtsanforderung dargestellt |
| Betroffene Bereiche | Automatikstufen, Kennzahlen je Klasse, Nachtjob `levels_refresh` |
| Überprüfung spätestens bei Meilenstein | Neubewertung mit dem anonymisierten HVM-Testbestand (M12-02) vor dem G1-Antrag |
| Datum | 29.09.2026 |

## A-086

| Feld | Inhalt |
| --- | --- |
| Annahme | Regelvorschläge aus Wiederholung (Regel M12-06): Schwelle `bank_rule_proposal_threshold` Standard 5 gleiche Entscheidungen, für wiederkehrende Muster (gleiche Gegenpartei, in jedem Fall identischer Betrag) `bank_rule_recurring_threshold` Standard 3; beide je Mandant zwischen 2 und 50 einstellbar. Massenbestätigungen zählen 0,5. Zwecktoken: Buchstabenfolgen ab vier Zeichen, die in jedem Nachweisfall vorkommen, ohne Namens- und Stoppwörter (Zahlung, Überweisung, Rechnung, Lastschrift, SEPA, Mandat, Betrag, Dank), höchstens fünf. Muster mit mehreren Konten werden nicht gelernt. |
| Begründung | Der Betreiber nennt 90 Prozent monatlich oder jährlich wiederkehrende Buchungen; drei identische Fälle (ein Quartal) sind für eine Regel im Zustand vorgeschlagen ausreichend, weil Freigabe, Aktivierung mit Betragsgrenze und Testnachweis unverändert folgen. Fahrplan 3.3 nennt 5 als Standard. |
| Kennzeichnung | unkritisch: ein Vorschlag bucht und aktiviert nichts; Betreiber kann die Schwellen anheben |
| Betroffene Bereiche | `mhvp.banking.learning`, Seite Bankregeln |
| Überprüfung spätestens bei Meilenstein | nach den ersten 90 Tagen mit Entscheidungsprotokoll der HVM |
| Datum | 29.09.2026 |

## A-087

| Feld | Inhalt |
| --- | --- |
| Annahme | Fallgrenzen des Runners (Regel M12-05, `mhvp.banking.runner`): 50 Automatikbuchungen je Regel und Tag, 200 je Lauf, 500 je Mandant und Tag; Stichprobe L3 10 Prozent nach Hash der Umsatz-ID mit 7 Tagen Frist. Erreichen einer Grenze stoppt den Lauf mit Ereignis, der Rest bleibt offen. |
| Begründung | 7.4 Nr. 4 verlangt Betrags- und Fallgrenzen ohne Zahlen; die Werte liegen deutlich über dem Tagesvolumen eines Objekts und unter dem, was eine Fehlregel an einem Tag anrichten dürfte. |
| Kennzeichnung | unkritisch, Konstanten; Änderung ohne Migration |
| Betroffene Bereiche | Runner, Sync-Zähler |
| Überprüfung spätestens bei Meilenstein | vor dem G1-Antrag mit dem Volumen der HVM |
| Datum | 29.09.2026 |

## A-088

| Feld | Inhalt |
| --- | --- |
| Annahme | Fälligkeit der Nachkontrolle: nächster Werktag Montag bis Freitag ohne bundesweite Feiertage und ohne die Feiertage Nordrhein-Westfalens (Fronleichnam, Allerheiligen), deterministische Tabelle `mhvp.banking.holidays` (Ostern nach der Gaußschen Osterformel in der Form von Lichtenberg), kein externer Dienst, kein Feiertag anderer Länder, keine regionalen Sonderfälle (etwa Augsburger Friedensfest). |
| Begründung | Der Master-Prompt verlangt eine Tagesprüfung; beide Mandanten haben ihren Sitz in NRW. Die Tabelle dient nur der Fälligkeit der Nachkontrolle, nie einer gesetzlichen Frist. |
| Kennzeichnung | unkritisch: eine Nachkontrolle, die auf einen nicht tabellierten Feiertag fällt, sperrt die Klasse einen Tag früher, nie später. Fortschreibung 29.09.2026: zuvor ohne Feiertagskalender. |
| Betroffene Bereiche | Nachkontrolle, Runner-Sperre, Rückläufer-Items |
| Überprüfung spätestens bei Meilenstein | mit dem Feiertagskalender der Fristenverwaltung (Bundesland je Mandant) |
| Datum | 29.09.2026 |

## A-089

| Feld | Inhalt |
| --- | --- |
| Annahme | Kopfzeilen des Immoware24-Journal-Exports für das Migrationsjournal (`mhvp.imports.migration.DEFAULT_JOURNAL_COLUMNS`): Buchungsnummer, Objekt, Konto, Datum, Betrag (Soll positiv) oder Soll und Haben, Buchungstext, Referenz, Beleg. Saldenliste für Eröffnungssalden: Spalten Konto und Saldo (Soll positiv), optional Bezeichnung. |
| Begründung | Die Spaltennamen sind nicht spezifiziert (13.1, M8-01). Die Standardwerte folgen A-047 und sind je Mandant über `PUT /api/v1/imports/migration/journal-columns` ersetzbar; die Saldenliste akzeptiert die Schreibweisen Konto, Kontonummer, Konto-Nr, Sachkonto, Personenkonto und Saldo, Betrag, Saldo EUR. |
| Kennzeichnung | unkritisch: eine falsche Zuordnung führt zu Warnungen oder abgewiesenen Zeilen, nie zu geratenen Werten; die Nulldifferenzprüfung sperrt die Umstellung |
| Betroffene Bereiche | Migrationsjournal, Eröffnungssalden aus Saldenliste, Abgleichbericht Migration |
| Überprüfung spätestens bei Meilenstein | Übernahme des echten HVM-Journals (M8-01) |
| Datum | 29.09.2026 |

## A-P05-01

| Feld | Inhalt |
| --- | --- |
| Annahme | Verzugszinsentwürfe verwenden das Systemkonto 489100 "Verzugszinsen" im Buchungskreis des Forderungsinhabers (analog Mahngebühren 489000) und die Tagesberechnung Tage durch 365 je Basiszinssatzzeitraum, je Zeitraum auf Cent gerundet |
| Begründung | Kontonummer und Zinstagezählung sind im Masterprompt nicht festgelegt (7.5); der Entwurf wird nie automatisch gebucht |
| Kennzeichnung | unkritisch: nur Buchungsentwurf, Buchung erst über Vier-Augen-Freigabe hinter G1, Konto im Kontenrahmen änderbar |
| Betroffene Bereiche | Mahnwesen, Zinsentwurf, Mahnbescheid-Vorbereitung |
| Überprüfung spätestens bei Meilenstein | Öffnung G1 (Abnahme M16) |
| Datum | 30.09.2026 |

## A-P10-01

| Feld | Inhalt |
| --- | --- |
| Annahme | Das Soll der Forderungs-Auswertung ist die Summe der offenen Posten der Art Forderung mit Fälligkeit (ersatzweise Buchungstag) im Zeitraum; das Ist ist deren Ausgleich bis Zeitraumende. |
| Begründung | Die Sollstellungen werden als offene Posten geführt, der Ausgleich ist je Posten nachvollziehbar (B07). Es wird keine Rechtsfolge abgeleitet, die Auswertung ist ein Entwurf. |
| Betroffene Bereiche | Auswertungen, Soll/Ist |
| Überprüfung spätestens bei Meilenstein | Öffnung G1 |
| Datum | 30.09.2026 |

## A-P02-01

| Feld | Inhalt |
| --- | --- |
| Annahme | Der Leistungszeitraum einer Verwalterhonorar-Rechnung ist kalenderbezogen je Intervall: Monat, Kalenderquartal, Kalenderhalbjahr oder Kalenderjahr, in dem der angegebene Tag liegt. Die Einheitenzahl wird zum Ende des Zeitraums (höchstens Stichtag) ermittelt. |
| Begründung | 18 M13 verlangt einen periodischen Honorarlauf ohne Festlegung der Zeiträume; kalenderbezogene Zeiträume sind eindeutig und verhindern Doppelausstellung. Ein abweichender Verwaltervertrag (zum Beispiel Wirtschaftsjahr) ist nicht abgebildet. |
| Betroffene Bereiche | Verwalterhonorar, Honorarrechnungen |
| Überprüfung spätestens bei Meilenstein | Abnahme M13 |
| Datum | 30.09.2026 |

## A-P02-02

| Feld | Inhalt |
| --- | --- |
| Annahme | Verbrauchsinformation (15.1 `heating.consumption_info`): der Job läuft wie spezifiziert am 3. des Monats um 05:40. Die bisherige Umsetzung (Beat an den Tagen 1 bis 3, Lauf am ersten Werktag) war eine undokumentierte Abweichung und ist auf die Spezifikation angeglichen. Die Lieferung für den Vormonat erfolgt damit am 3., auch wenn dieser auf ein Wochenende fällt. |
| Begründung | Befund S15-05 der Lückenliste 30.09.2026; die Spezifikation nennt den 3. Eine Werktagsregel ist fachlich nicht festgelegt. |
| Betroffene Bereiche | Heizkosten, Portal Verbrauchsinformation (Regel H03) |
| Überprüfung spätestens bei Meilenstein | Abnahme H03 |
| Datum | 30.09.2026 |

## A-012-2

| Feld | Inhalt |
| --- | --- |
| Annahme | Nachtrag zu A-012: Passwortregel 12 bis 128 Zeichen und Offline-Prüfung gegen kompromittierte Passwörter (Regel M2-05). Bestehende kürzere Passwörter bleiben bis zur nächsten Änderung gültig, eine Zwangsänderung erfolgt nicht. |
| Begründung | Betreiberentscheidung 9 a vom 30.09.2026 (Lückenliste 30.09.2026, M2-05) ersetzt die Mindestlänge 6 aus M2-01. Eine Zwangsänderung ist nicht entschieden. |
| Kennzeichnung | Betreiberentscheidung; Verzicht auf Zwangsänderung ist Annahme |
| Betroffene Bereiche | Anmeldung, Mitgliederverwaltung, Portal Einladung |
| Überprüfung spätestens bei Meilenstein | M9 (vor Produktivbetrieb) |
| Datum | 30.09.2026 |

## A-P13-1

| Feld | Inhalt |
| --- | --- |
| Annahme | Portal Chat, KI-Vorqualifizierung und Support-Sicht sind je Mandant standardmäßig aus. Die Einwilligung in die Support-Sicht gilt höchstens 72 Stunden und ist jederzeit widerrufbar. |
| Begründung | Produktschutz nach Betreiberentscheidungen 6 a und 7 a vom 30.09.2026; die Grenzen sind Annahmen des Betreibers, keine Rechtsregel. |
| Kennzeichnung | Produktschutz |
| Betroffene Bereiche | Portal (Chat, Support-Sicht), Regel P13 |
| Überprüfung spätestens bei Meilenstein | M9 (vor Produktivbetrieb) |
| Datum | 30.09.2026 |

## A-P12-01

| Feld | Inhalt |
| --- | --- |
| Annahme | Der erste IMAP-Abruf eines Postfachs übernimmt nur Mails der letzten 30 Tage (Suche SINCE); ältere Mails bleiben auf dem Server und können als .eml hochgeladen werden. Abruf alle 120 Sekunden, höchstens 50 Mails je Lauf. |
| Begründung | Unkritische technische Annahme zur Begrenzung der Erstübernahme; keine Rechtsregel. |
| Kennzeichnung | Annahme (technisch) |
| Betroffene Bereiche | Postfach IMAP, Regel M20-09 |
| Überprüfung spätestens bei Meilenstein | M20-Abnahme durch den Betreiber |
| Datum | 30.09.2026 |

## A-P15-01

| Feld | Inhalt |
| --- | --- |
| Annahme | Die Testphase der Abrechnungsvorschau (Zeile trial, Tage) zählt ab Lizenzbeginn; ein Monat ist frei, wenn sein letzter Tag vor Lizenzbeginn plus Tage liegt, ein angebrochener Monat wird voll berechnet. |
| Begründung | Die Struktur nennt nur die Dauer in Tagen. Es ist eine Vorschau ohne Rechnung, die Entscheidung über Teilmonate trifft der Betreiber (M27-01). |
| Betroffene Bereiche | Plattform, Abrechnungsvorschau |
| Überprüfung spätestens bei Meilenstein | Öffnung G5 |
| Datum | 30.09.2026 |

## P09 Annahmen (30.09.2026)

- A-P09-1 (Produktschutz): Wiederholung des Kontoabrufs nur bei "Anbieter nicht erreichbar" und "Ratenlimit", drei Versuche mit 60, 120 und 240 Sekunden Abstand; Zugangs-, Zustimmungs- und Validierungsfehler werden nicht wiederholt, um Bankzugänge nicht zu sperren.
- A-P09-2 (Produktschutz): Ohne Eintrag gilt 06:00 Uhr (Europe/Berlin) als Abrufzeit; eine andere Stunde wird vom stündlichen Job bedient.
- A-P09-3 (Produktschutz): Die B09-Kopplung des Wochendigests verlangt je beteiligtem Konto mindestens einen Auszug mit Abschluss im Vormonat ohne Differenz; fehlt ein Auszug, gilt die Abstimmung als nicht erfolgt.
- A-P09-4 (Produktschutz): Betragsklassen der KI-Beispiele: bis 100, bis 500, bis 2.000, bis 10.000, über 10.000 EUR; höchstens acht Beispiele, neueste zuerst, Gegenbeispiele (abgelehnt, storniert) eingeschlossen.
- A-P16-1 (Produktschutz): Statusmodell der Kaution: `open` bis zur Erfassung, `active` während der Verwahrung, `settled` nach der Abrechnung (endgültig, nur noch Dokumente ergänzbar). Betrag und Raten sind nur vor der ersten Kautionsbewegung änderbar.
- A-P16-2 (Produktschutz): Eine Zahlungsposition oder ein Zahlungsplan, auf die eine gebuchte Sollstellung verweist, ändert Betrag, Zeitraum und Art nicht mehr; Korrektur durch neue Position und Storno im Buchungskreis.
- A-P16-3 (Produktschutz): Ein beendetes Bankkonto eines Objekts verliert das Standardkennzeichen; IBAN, Art und Rechtsträger bleiben unveränderlich.
- A-Q10-01 (Fachliche Umsetzung): Ticket `external_comments` und `external_attachments` haben für Bestandstickets und neue Tickets den Standard `open` (Migration 0279), damit das bisherige Portalverhalten unverändert bleibt; Einschränkung je Ticket durch die Verwaltung (M19-03).
- A-Q15-1 (Produktschutz): Honorarlauf und Rechnungsdokument versenden und buchen nichts; die Nummernvergabe je Rechnung läuft in einem eigenen Savepoint, damit ein Fehler keine Nummer verbraucht.
- A-Q15-2 (Fachliche Umsetzung): Die Jahresübernahme bildet zum Beginn des Folgejahres einen Abschlussentwurf und einen Anfangsbestandsentwurf gegen das Anfangsbestandskonto, weil die Salden im System kumulativ aus allen gebuchten Zeilen entstehen und ein einzelner Anfangsbestand sie verdoppeln würde. Zu bestätigen (OPEN_QUESTIONS Q15-02).
- A-Q12-1 (Fachliche Umsetzung): Das Ereignis `invoice.paid` entsteht, sobald verknüpfte Bankumsätze des Rechnungsabgleichs den Bruttobetrag der Eingangsrechnung decken. Es ist ein Hinweis auf den Zahlungsnachweis, keine Buchung und kein Ausgleich eines offenen Postens.
- A-Q12-2 (Fachliche Umsetzung): `invoice.approved` bedeutet abgeschlossene sachliche Prüfung (Prüfstatus closed_ok oder closed_with_reservation); Buchung und Zahlungsfreigabe bleiben getrennte Schritte.
- A-Q12-3 (Produktschutz): Der Jobschalter `banking-sync-all` wirkt zusätzlich zur Abrufstunde der Bankeinstellungen; eine abweichende Startzeit im Jobschalter und eine andere Abrufstunde schließen sich aus, der Abruf entfällt dann. Empfehlung: Startzeit nur über die Abrufstunde der Bankeinstellungen steuern.
- A-Q05-01 (Fachliche Umsetzung): Die Belegungsliste im CRM zeigt mit leerem Stichtag den Tag der Abfrage (vom API berechnet); ein Stichtag in der Vergangenheit liefert die damals gültigen Verträge ohne Rücksicht auf spätere Korrekturen.
- A-Q05-02 (Produktschutz): Die Sammelzuweisung der Ticketliste ist für alle markierten Tickets ganz oder gar nicht wirksam (Verhalten der API); das Limit von zehn Tickets ohne Freigaberecht gilt wie bei der Sammelstatusänderung auch für die Sammelzuweisung.
- A-Q14-01 (Produktschutz): Automatischer Postauftrag bei Kanal post gilt nur mit dem Anbieter manuell oder bei freigegebenem externen Dienst und vorhandenem Recht communication:approve; sonst bleibt die Zustellung vorbereitet. Bilder im Exposé: höchstens 8, nur PNG und JPEG.
- A-Q03-01 (Fachliche Umsetzung): Die Rechtsträgerart eines Dokuments für das Aufbewahrungsprofil und die WEG-Dauerunterlage ergibt sich aus einem direkt verknüpften Rechtsträger; ohne diesen aus dem verknüpften Objekt (Verwaltungsart WEG oder WEG mit SEV gleich GdWE, Miete gleich Vermieter). Mehrere Arten behalten das Kategorieprofil.
- A-Q03-02 (Produktschutz): Signierte Upload- und Download-URLs gelten 300 Sekunden; temporäre Uploads werden nach einem Tag entfernt. Der ZIP-Massenupload nimmt höchstens 200 Dateien an.
- A-Q04-01 (Produktschutz): Die Ausführung einer Kontakt-Zusammenführung verlangt eine zweite Person als Antragsteller (Vier-Augen) und das Recht contacts:approve; die Quelle wird über `deleted_at` ausgeblendet und über `merged_into_id` dem Ziel zugeordnet. Leere Felder des Ziels werden aus der Quelle ergänzt, vorhandene Werte bleiben.
- A-Q04-02 (Produktschutz): Verweise, die beim Ziel an einer Eindeutigkeit scheitern, bleiben an der Quelle und werden im Ergebnis der Zusammenführung als Doppelung ausgewiesen, damit nichts überschrieben oder gelöscht wird.

- A-Q08-01 (Produktschutz): Nennt die SEPA-Übersicht keine Mandatssequenz, wird ein übernommenes Mandat als `recurring` erfasst (Altmandate sind im Altsystem bereits genutzt). Der Einzug bleibt bis G2 gesperrt; die Sequenz ist vor der ersten Lastschrift zu prüfen.
- A-Q08-02 (Produktschutz): Historische Bankumsätze aus dem Altsystem erhalten den Status `ignored`, damit Abgleich und Buchungsautomatik sie nicht erneut verarbeiten; sie liegen nur bis zum Migrationsstichtag des Buchungskreises vor.

- A-Q09-01 (Produktschutz): Die Zweckbindung der Sollstellung an eine Rücklage wird nur gesetzt, wenn der gesamte Rücklagenvorschuss einer Einheit laut Plan in genau eine Rücklage fließt. In allen anderen Fällen bleibt er ungebunden und wird nicht nach Planverhältnis aufgeteilt, damit keine Zuordnung entsteht, die kein Beschluss trägt.
- A-Q09-02 (Produktschutz): Die Übernahme vierteljährlicher oder jährlicher Vorschüsse ersetzt einen stehenden Zahlungsplan des Vertrags mit anderer Zahlweise ab Planbeginn (Vortag als Ende des alten). Die Fälligkeit liegt im ersten Monat der Periode (im Voraus), der Vertragsbetrag gilt je Monat. Beginn nur zum Monatsersten, weil die Perioden daran ankern.
- A-Q09-03 (Produktschutz): Die Gesamtabrechnung als PDF wird nur mit vollständigen Firmendaten des Mandanten erzeugt und als Entwurf gekennzeichnet; es gibt keine Ersatzdaten für den Briefbogen.
- A-Q06-01 (Produktschutz): Die Kaskade gilt für Einzelaufrufe; zerlegte Extraktion und Schnellimport eskalieren weiter nur nach Kontextgröße. Die zweite Stufe nutzt das Budget desselben Anbieters.
- A-Q06-02 (Produktschutz): Die KI-Prüfung des Mieterhöhungsfalls prüft nur die innere Stimmigkeit der erfassten Angaben; der Prompt nennt keine Norm, keine Frist und keinen Betrag.
- A-Q06-03 (Produktschutz): Die Benachrichtigung bei Budgetsperre geht an alle Mitglieder mit `tenant_settings:update`; sie hat kein Sprungziel, weil der Arbeitsbereich für `ai_usage` keine Route kennt.
