# Annahmen

Stand: 23.09.2026. Grundlage: `docs/MASTER-PROMPT.md`, Abschnitt 0.1 Regel 3.

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
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `.github/workflows`, Pinning nach ADR 0001 |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

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
| Annahme | Zeitstempel werden in UTC gespeichert (`TIMESTAMPTZ`); die Oberfläche zeigt Zeitstempel in der Zeitzone Europe/Berlin an. Die Zeitzone für fachliche Fristberechnung ist nicht angenommen, sondern offen (M1-09). |
| Begründung | Abschnitt 4.1 legt UTC fest; die Anzeige betrifft nur die Darstellung. Fristberechnungen folgen erst mit freigegebenen Regeln. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | api, worker (Celery in UTC), Oberfläche |
| Überprüfung spätestens bei Meilenstein | M2 |
| Datum | 23.09.2026 |

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
| Annahme | SeaweedFS 4.47 dient nur als S3-kompatibler Objektspeicher für Entwicklung und CI, bis M1-01 entschieden ist. |
| Begründung | MinIO-Images sind auf Docker Hub nicht mehr verfügbar (laut ADR 0005, Prüfstand 23.09.2026). Die Anwendung nutzt nur die S3-API. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `infra/compose*.yaml`, `MHVP_S3_*` |
| Überprüfung spätestens bei Meilenstein | M6 |
| Datum | 23.09.2026 |

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
| Annahme | Passwortregel: Länge 12 bis 128 Zeichen, keine Zusammensetzungsregeln, keine Leerzeichen am Anfang oder Ende; Kontosperre nach 10 Fehlversuchen für 15 Minuten. |
| Begründung | Abschnitt 3.4 verlangt Passwortregeln nach BSI-Empfehlung und eine Kontosperre, nennt aber keine Werte. Konkrete Zahlen sind hier nicht aus einer geprüften Quelle übernommen. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb; Bestätigung offen (M2-01) |
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
| Annahme | Gläubiger eines Mietverhältnisses ist im Mietobjekt der zum Mietbeginn eingetragene Eigentümer, bei WEG mit SEV der Eigentümer der Einheit mit aktivem SEV-Eigentumsverhältnis; Gläubiger des Eigentumsverhältnisses ist die GdWE. Reine WEG-Objekte führen keine Mietverhältnisse (M5-03). |
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
