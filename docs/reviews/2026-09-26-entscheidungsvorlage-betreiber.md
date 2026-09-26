# Entscheidungsvorlage für den Betreiber

Stand: 26.09.2026. Empfänger: Timo Müller, Geschäftsführer Hausverwaltung Müller GmbH, Vorstand Müller Holding AG (Betreiber der MH Verwaltungsplattform). Verfasser: Coding-Agent. Grundlage: `docs/OPEN_QUESTIONS.md` (Stand 26.09.2026), `docs/ASSUMPTIONS.md`, `docs/MASTER-PROMPT.md` Abschnitt 18.0 (Freigabestufen), 19.1 (Startvoraussetzungen), Anhang C.2 (Prüflücken), Anhang E.

Zweck: Alle offenen und teilweise gelösten Punkte sind hier nach Entscheidungsbedarf gebündelt. Je Punkt steht die Kennung aus `docs/OPEN_QUESTIONS.md`. Empfehlungen sind kaufmännische Vorschläge des Coding-Agents; rechtliche und steuerliche Aussagen sind ausdrücklich keine Prüfung, sondern benennen, wo Rechtsanwalt, Steuerberater, Bank oder Datenschutz einzubinden sind. Beträge, Fristen und Normen wurden nur übernommen, wo sie in den Unterlagen stehen.

Hinweis zum Status: Am 26.09.2026 wurden 60 Zeilen in `docs/OPEN_QUESTIONS.md` auf den Status "technisch umgesetzt, Entscheidung offen (26.09.2026)" gesetzt, weil die Funktion im Code vorhanden ist und nur noch eine Festlegung, Freigabe oder Eingabe des Betreibers fehlt. Die Liste steht in Abschnitt E dieser Vorlage.

---

## Kurzfassung: die zehn Entscheidungen, die den Echtbetrieb am meisten blockieren

| Nr | Entscheidung | Kennung | Wer entscheidet oder prüft | Warum blockierend |
| --- | --- | --- | --- | --- |
| 1 | Fachkundige Person für unabhängige Sollwerte und Abnahme benennen (Buchführung, Abrechnung) | V16, M10-04 | Betreiber | Ohne diese Person kann G1 nicht geöffnet werden; jede Abnahme nach Anhang D setzt sie voraus. Empfehlung: Buchhaltung der HVM plus Steuerberater als Zweitprüfer |
| 2 | Kontenrahmen freigeben: Immoware24-Kontenliste der HVM bereitstellen, Vorlage prüfen, Erlöskonten Miete und Vorauszahlungen ergänzen, Kontenattribute je Konto festlegen | V8, M10-01, M10-02, M13-03 | Betreiber mit Steuerberater | Ohne Kontenrahmen keine produktive Buchung, keine Sollstellung mit Steuer, kein DATEV-Export |
| 3 | Migrationsstichtag je Objekt und Dauer des Parallelbetriebs mit Immoware24 festlegen; Immoware24-Vertrag (Laufzeit, Kündigung, Exportrechte) prüfen | V6, V9, M8-03, M9-05 (Parallelbetrieb), V19 | Betreiber | Steuert die gesamte Übernahme; ohne Stichtag keine Anfangsbestände, keine Überleitung, keine Ablösung |
| 4 | Echte Immoware24-Exporte in Staging hochladen und Spaltenzuordnung gemeinsam festlegen; Referenzzahlen je Objekt liefern | M8-01, M8-02, M8-04, A-047 | Betreiber | Alle Importwege sind gebaut, aber mit synthetischen Daten geprüft; ohne echte Dateien keine Abnahme M8 und kein Abgleichbericht |
| 5 | Auftragsverarbeitungsverträge abschließen und Trainingsausschluss bestätigen: Anthropic, OpenAI, finAPI, Briefdienst, SMS, Telefonie | V10, M7-01, M7-02, M11-40, M12-01, M14-01, M20-02 | Betreiber mit Datenschutz | Ohne AVV bleiben alle KI-Aufgaben mit personenbezogenen Daten und der Bankabruf gesperrt; Regel 0.1.13 |
| 6 | finAPI-Vertrag und Lizenzumfang klären, § 34 ZAG mit Rechtsanwalt bewerten, Bankliste mit BIC und Kontotyp je Konto liefern | V2, M11-01, M11-40 bis M11-46 | Betreiber, Rechtsanwalt, Bank | Ohne Vertrag kein produktiver Kontoabruf; ohne Bankliste keine Zuordnung Konto zu Rechtsträger |
| 7 | Aufbewahrungsmatrix je Rechtsträger und Unterlagenklasse entwerfen und im Vier-Augen-Prinzip freigeben | V17, M6-04, M11-03, M6-03 | Betreiber mit Steuerberater | Ohne Profil ist jede Löschung gesperrt; Datenschutz und GoBD hängen daran; betrifft G1 bis G5 |
| 8 | Mahnwesen abschließen: Gebührenbetrag je Stufe, Basiszinssatz, vertragliche Grundlage der Weiterbelastung, Standardtexte, Bankkonto je Forderungsinhaber | V7, M16-01, M16-02, M16-03, M16-13, M16-12 | Betreiber, Rechtsanwalt für Gebührenhöhe und Verzugsaussagen | Stufenleiter und Buchungslogik sind fertig; ohne Beträge wirkt keine Gebühr, ohne Freigabe kein Versand |
| 9 | Serverhärtung ausführen und Backup vervollständigen: SSH-Schlüsselanmeldung, Offsite-Speicherort, echtes age-Schlüsselpaar, Alarmziel | M9-05 (SSH), M9-02, M9-04, M9-03 | Betreiber | Vor dem Import echter Daten zwingend (Betreiberentscheidung vom 25.09.2026); Datenschutz und Wiederherstellbarkeit |
| 10 | Freigabe- und Rollenordnung: zweiter Plattformadministrator, Freigabematrix mit Betragsgrenzen, Identitätsprüfung der Freigebenden, Bankvollmachten und Limits | M2-02, M14-03, M15-02, V18 | Betreiber, Bank | Vier-Augen-Prinzip ist technisch erzwungen; ohne benannte zweite Person kann keine Freigabestufe beantragt und genehmigt werden; G2 hängt an V18 |

Empfohlene Reihenfolge: 1, 9 und 10 sofort (organisatorisch, kein externer Vorlauf). 2, 3, 4 und 7 in den nächsten zwei Wochen mit dem Steuerberater. 5 und 6 parallel starten, weil Vertragsabschlüsse Vorlauf haben. 8 nach Rückmeldung des Rechtsanwalts zur Gebührenhöhe.

---

## A. Freigabestufen G1 bis G5 mit den V- und P-Punkten

Die Freigabestufen gelten je Mandant, sind standardmäßig geschlossen und werden über die Plattform beantragt und durch eine zweite Person genehmigt (ADR 0003, `mhvp.platform.gates`). Eine Freigabe deckt nur den dokumentierten Umfang. Die folgende Übersicht nennt je Stufe, was fachlich geprüft werden muss, durch wen, und welche Unterlagen die Plattform dafür liefert.

### G1 Produktive Buchführung

Betroffene Funktionen: Buchungen im Journal, Sollstellungsläufe mit Buchung, Zahlungszuordnung mit Buchung, Umsatzbuchung des Verwalterhonorars, Anfangsbestände aus der Migration.

| Punkt | Was geprüft werden muss | Durch wen | Was die Plattform liefert |
| --- | --- | --- | --- |
| V16 | Benennung der fachkundigen Person für unabhängige Sollwerte und Abnahme | Betreiber | Testfälle nach Anhang D (`tests/`), Abnahmeprotokolle unter `docs/acceptance/` |
| V8, M10-01, M10-02 | Kontenrahmen-Vorlage: Vollständigkeit, Bezeichnungen, Erlöskonten Miete, Umlagefähigkeit, Abrechnungsart, Umsatzsteueroption je Konto | Betreiber mit Steuerberater | Vorlage aus Anhang A.1 in `mhvp.accounting` (Kategorie und Typ je Konto abgeleitet, A-023), Kontenattribute pflegbar |
| V19, M8-03 | Unterjährige Übernahme: vollständige Jahresdaten und Überleitungsplan statt Anfangssalden; Migrationsstichtag je Objekt | Betreiber mit Steuerberater | Rohzeilen Journal, Konten, offene Posten, Bankumsätze aus dem Import; Migrationsjournal nach 6.9.10 folgt nach Stichtag |
| V21 | Steuerlicher Status je GdWE, Eigentümer und Mandant; Prüfzuständigkeit Umsatzsteuer, Bauleistungen, § 35a | Steuerberater | Felder für Umsatzsteueroption je Buchungskreis und Konto; Steuerbehandlung wird nicht berechnet, solange keine Freigabe vorliegt |
| P03 | Aktuelle GoBD-Fassung, USt-Anwendungsregeln, § 15a UStG, § 35a, Bauabzugsteuer | Steuerberater, gegebenenfalls Rechtsanwalt | Prüfexport nach Abschnitt 7.7 (`POST /accounting/audit-exports`, ZIP mit CSV je Tabelle, SHA-256, Originalbelege) |
| M10-03, M12-03 | Verrechnung von Guthaben und Tilgungsfolge ohne Bestimmung (§§ 366, 367 BGB) | Rechtsanwalt | Plattform gleicht nur ausdrücklich zugeordnete Posten aus; ein Betragstreffer allein löst keinen Ausgleich aus (`mhvp.banking.matching.unambiguous`) |
| M13-01, M13-02, M13-03 | Zeitanteilige Sollstellung, nicht monatliche Intervalle, Feiertagskalender, Umsatzsteuer auf Sollstellungen | Betreiber mit Rechtsanwalt und Steuerberater | Positionen ohne freigegebene Regel erscheinen im Lauf als manuell und werden nicht gebucht |
| M14-02, M14-04 | Vorsteuerabzug und Aufteilung (§ 15 UStG), Reverse Charge, Bauabzugsteuer, § 35a-Aufteilung | Steuerberater | Werte werden erfasst und geprüft, nicht berechnet; §-35a-Anteil aus KI nie übernommen |
| M10-04 | Fachliche Abnahme nach Anhang D.3, Freigabe je Mandant | Betreiber mit fachkundiger Person | Gate-Antrag und Genehmigung in der Plattform, Testläufe in CI |
| M10-05 | Vergleichsbuchung im nicht führenden Buchungskreis beibehalten oder harte Sperre | Betreiber | Vergleichsbuchung ohne externe Wirkung ist umgesetzt (D52) |
| M16-14 | Zahlungserinnerung immer 0,00 EUR, Abnahme | Betreiber | Harte Sperre umgesetzt, vier Integrationstests umzustellen |
| M27-03 | Verfahrensdokumentation im Pilotbetrieb | Betreiber (RA und StB laut Entscheidung 24.09.2026) | Handbuch, Runbooks, ADRs, Regelregister |

Empfehlung: G1 zuerst für einen Mandanten (HVM) und einen begrenzten Objektkreis (zwei bis drei Pilotobjekte, davon eine WEG) öffnen, sobald V16, V8 und der Migrationsstichtag stehen. Alles andere bleibt Parallelbetrieb mit Vergleichsbuchung.

### G2 Zahlungsverkehr

Betroffene Funktionen: Download und Übermittlung von pain.001 und pain.008, Lastschrifteinzug, Zahlungsfreigabe, Bankkonto im Mahnschreiben.

| Punkt | Was geprüft werden muss | Durch wen | Was die Plattform liefert |
| --- | --- | --- | --- |
| V18 | Bank- und Zahlungsvollmachten, Rollen, Limits, zulässige Mandatsverfahren, Empfängerdatenkontrolle, Freigabeverfahren | Betreiber mit Bank, Rechtsanwalt | Vier-Augen-Freigabe mit getrennten Konten und Kontaktpersonen (MHVP-GATE-0002), IBAN-Freigabe durch zweite Person (`contacts:approve`) |
| V2, M11-01, M15-03 | Bankliste mit BIC und Kontotyp; EBICS-Verträge; Bank-Testsystem | Betreiber mit Bank | finAPI-Onboarding je Mandant, Datei-Upload CAMT.053 und MT940 |
| P05, M15-01 | SEPA-Formatversion je Bank, Zeichensatz, Einreichungsweg, Gläubiger-ID, Vorlauffristen FRST und RCUR, Vorabinformation, B2B-Verfahren | Bank, Rechtsanwalt | pain.001.001.09 und pain.008.001.02 werden erzeugt und abgelegt, nie übermittelt; strukturelle Prüfung, kein XSD im Repository |
| M15-02 | Identitätsprüfung der freigabeberechtigten Personen außerhalb der Plattform | Betreiber | Prüfung auf verschiedene E-Mail-Adressen und Kontaktpersonen umgesetzt (D36) |
| M3-02 | Verknüpfung Mandatsnachweis am Kontakt mit `contracts.SepaMandate`; Mandatstext, Pre-Notification-Frist | Rechtsanwalt | Mandatsnachweis erfasst (Referenz, Datum, Art, Dokument, Widerruf) |
| M11-40 bis M11-46 | finAPI-Vertrag, § 34 ZAG, API-Version, Feldschema, Update-Endpunkt, Trennung auf Providerseite, Mandator-Modell, Callback, Historientiefe | Betreiber mit finAPI-Support und Rechtsanwalt | `FinApiBankingProvider` read-only, verifizierte Endpunkte in `docs/integrations/finapi.md`, Diagnose je Verbindung |
| M16-13 | Freigabe des Bankkontos je Forderungsinhaber für Mahnschreiben | Betreiber | Schreiben verweist bis dahin auf "das Ihnen bekannte Konto" |
| M21-02 | Prüfschritte bei Bankänderung aus dem Portal in Bezug auf Lastschriftmandate | Betreiber | Übernahme nach Prüfung, keine automatische Mandatsprüfung |

Empfehlung: G2 erst nach G1 und erst für Überweisungen (pain.001) mit einer Bank und einem Testkonto; Lastschriften als zweiter Schritt nach Freigabe der Vorlauffristen und der Vorabinformation durch den Rechtsanwalt. Die Bank sollte schriftlich die akzeptierte pain-Version bestätigen.

### G3 Mietabrechnungen

Betroffene Funktionen: Ausgabe und Versand von Betriebs- und Heizkostenabrechnungen, Eigentümerabrechnung Miete und SEV, Mieterhöhungsschreiben.

| Punkt | Was geprüft werden muss | Durch wen | Was die Plattform liefert |
| --- | --- | --- | --- |
| V22 | Anonymisierte repräsentative Testfälle: Belege, Vertragswechsel, Rücklastschriften, Kostenverteilungen, Abrechnungen | Betreiber | Testfälle nach Anhang D, Evaluationsdatensätze unter `tests/ai_eval` |
| M17-01 | Umlagefähigkeit je Kostenposition, Schlüssel bei vermietetem Wohnungseigentum, Wirtschaftlichkeit | Rechtsanwalt | Grundlage je Position Pflicht (Vertragsklausel), keine Ableitung aus Kontonamen |
| M17-02 | Heizkosten und CO2-Aufteilung: Messdienst, Dateiformat, amtliche CO2-Stufentabelle | Betreiber mit Messdienst, Rechtsanwalt | Übernahme externer Einzelbeträge, CO2-Hilfsberechnung (D10) zur Prüfung |
| M17-03 | Verfahren für offene Vorauszahlungen nach Abrechnungsreife | Rechtsanwalt | Abrechnung trennt fällige, gezahlte und offene Vorauszahlungen |
| M17-04 | Abrechnungsfrist § 556 Abs. 3 BGB, Ausnahmegründe und Nachweise | Rechtsanwalt | Orientierungsfrist, Zugangsdatum Pflicht, Sperre bei Nachforderung nach Fristablauf ohne erfasste Ausnahme |
| M17-05 | Eigentümerabrechnung Miete und SEV: Inhalte, Ausgabemuster, Honorarintervalle, Umsatzsteuer bei Option, Informationsblatt, §-35a-Nachweis, Anschreiben (A07) | Betreiber mit Steuerberater | Entwurf und Berechnung umgesetzt (`mhvp.billing.owner_statement`), Ausgabe gesperrt |
| M17-06 | Quellenpflicht und Freigabestatus für Umlageschlüssel | Betreiber | Schlüssel ohne Quelle und Freigabe derzeit sofort verwendbar; Vorschlag: Status vorgeschlagen und freigegeben |
| M26-01 | Mieterhöhung: Freigabe je Regel im Backend, Kappungsgebiete weiterer Länder, Prüfregeln § 558 Abs. 1 Satz 2, § 558a Abs. 3, § 558b Abs. 2 Satz 2 BGB | Rechtsanwalt (Werte am 24.09.2026 durch den Betreiber geprüft) | Regelentwurf `docs/rules/M26-rent-law.md`, NRW-Kappungsgebiete vorbefüllt |

Empfehlung: G3 für Mietabrechnungen mit einem Abrechnungsjahr eines Pilotobjekts öffnen, nachdem die fachkundige Person das Ergebnis gegen eine unabhängig erstellte Abrechnung (Immoware24 oder manuell) abgeglichen hat. Heizkosten bleiben Übernahme aus der Messdienstabrechnung.

### G4 WEG-Abrechnungen

Betroffene Funktionen: Jahresabrechnung, Einzelabrechnungen, Vermögensbericht, Beschlussfassung mit Rechtsfolge, Einsichtspakete.

| Punkt | Was geprüft werden muss | Durch wen | Was die Plattform liefert |
| --- | --- | --- | --- |
| V15 | Je Pilot-WEG: Teilungserklärung, Gemeinschaftsordnung, Verteilungsschlüssel, Wirtschaftspläne, Sonderumlagen, Beschlüsse, Eigentümernachweise | Betreiber | Erfassung je GdWE mit Fundstelle (Mehrheitsregeln, Umlageschlüssel, Beschlüsse) |
| P01 | Rechtsprechung zu Abrechnungsspitze, Eigentümerwechsel, Sondernachfolgerhaftung (BGH V ZR 113/11, V ZR 147/11) und Fortgeltung im heutigen § 28 WEG | Rechtsanwalt | Fall D15, Entscheidung M24-01 vom 24.09.2026 als Annahme umgesetzt |
| P02 | Geldfluss- und Heizkostenüberleitung (BGH V ZR 251/10), Folgen späterer Beschlusskorrektur | Rechtsanwalt | Fall D09, Überleitungsrechnung mit Erklärungscodes |
| M24-01 | Bestätigung der Betreiberentscheidung zum Eigentümerwechsel durch Rechtsberatung | Rechtsanwalt | Umsetzung als Zahlenfall vorhanden |
| M24-02 | Inhalt und Gliederung des Vermögensberichts | Rechtsanwalt | Rücklagenstand, offene Beiträge, Bankbestände (`mhvp.hoa.calc.asset_report`) |
| M24-03 | Darlehen in der Jahresabrechnung: Verteilung von Zins und Tilgung, Erklärungscodes, Versicherungsleistung und Regress | Rechtsanwalt und Steuerberater | Darlehensposten getrennt erfasst, nur ausgewiesen, keine automatische Verteilung |
| M25-01 | Inhalt der Mehrheitsregeln je Gemeinschaft | Betreiber mit Rechtsanwalt | Tabelle `hoa_majority_rule` je Mandant mit Override je GdWE, Prüfung nur als Anzeige |
| M25-02, M25-03 | Umlaufbeschluss mit geringerer Mehrheit; Einladungsfrist und Zugang | Rechtsanwalt | Allstimmigkeit in Textform, Dreiwochenfrist orientierend mit Dringlichkeitsvermerk |
| M25-05 | Einsichtsrechte außerhalb des Portals: Fristen, Umfang je Antragsteller, Form; Zugriffsmatrix § 18 Abs. 4 WEG | Rechtsanwalt | Einsichtsanfragen mit Freigabe je Anfrage (`mhvp.hoa.inspection`), keine Fristberechnung |
| V13 | WEG-Recht für virtuelle Versammlung und Umlaufbeschluss im Portal | Rechtsanwalt | Beschlussfrist mit Quelle (M9-07), Protokollentwurf als PDF ohne Rechtsfolge |
| W09-01 | Änderungsbeschluss erzeugt neue Version (entschieden 24.09.2026) | Betreiber | umgesetzt |

Empfehlung: G4 als letzte fachliche Stufe. Vorher eine Pilot-WEG mit vollständigem Unterlagensatz (V15) auswählen, die Jahresabrechnung parallel in Immoware24 und in der Plattform erstellen und die Differenzen durch die fachkundige Person erklären lassen. P01 und P02 sollten dem Rechtsanwalt als gebündelter Prüfauftrag gegeben werden.

### G5 Fremdmandanten und Marktstart

Betroffene Funktionen: Anlage weiterer Mandanten außerhalb der Gruppe, Lizenzabrechnung, Vermarktung.

| Punkt | Was geprüft werden muss | Durch wen | Was die Plattform liefert |
| --- | --- | --- | --- |
| V4, M1-05 | Produktname, Marke, Domains für Fremdmandanten, Repository-Name | Betreiber | Neutrale Tokens bis zur Entscheidung |
| V5 | Entwicklungsmodell und Kostenschätzung je Phase | Betreiber | Meilensteinpläne in `docs/plans/` |
| V13, P04 | BFSG-Anwendbarkeit auf das Portal, AVV- und Verantwortlichkeitslage, Vermarktungs- und KI-Pflichten, Verträge | Rechtsanwalt | Portal mit zweitem Faktor, Zugriffsmatrix M21 |
| V17 | Aufbewahrungsmatrix, Belegeinsichtsverfahren auch ohne Portal | Betreiber mit Steuerberater | Aufbewahrungsprofile je Unterlagenklasse pflegbar, Löschung ohne Profil gesperrt |
| M27-01 | Beträge und Umsatzsteuer der Lizenzentgelte | Betreiber (Müller Holding AG) mit Steuerberater | Preisliste je Modul und Einheit (`mhvp.platform.licensing`), Kontingent nur angezeigt |
| M27-02 | G5-Nachweise: Backup und Wiederherstellung, Penetrationstest-Bericht, Verfahrensdokumentation, Support- und Rückfallprozess | Betreiber, externe Prüfer falls Kunden oder Versicherer sie verlangen | Statusanzeige G5, Runbooks, Wiederherstellungstest vom 24.09.2026 |
| M11-44 | Mandator-Modell finAPI je SaaS-Mandant | Betreiber mit finAPI | `mandator_id` nur als Hinweis-Header |
| M18-02 | Zugriffsbereich für weitere Rollen (Beirat, externe Prüfer) | Betreiber | Zugriffsbereich Steuerberater je Mitgliedschaft umgesetzt |
| M2-05 | Rein lesende Übersicht über alle Mandanten | Betreiber | Mandantenwechsel mit Protokoll umgesetzt; übergreifende Sicht nicht gebaut |

Empfehlung: G5 nicht vor Abschluss von mindestens sechs Monaten Eigenbetrieb mit G1 bis G3. Vorher Preismodell mit Umsatzsteuer und Vertragsmuster (AGB, AVV, Leistungsbeschreibung) durch Rechtsanwalt und Steuerberater erstellen lassen.

---

## B. Produktentscheidungen mit Empfehlung

Je Punkt: Frage, Optionen, kaufmännische Empfehlung, Aufwand (gering: Eingabe oder Konfiguration; mittel: bis zwei Entwicklertage; hoch: mehr), Risiko, betroffene Funktion.

### B.1 Mahnwesen und Forderungen

| Kennung | Frage | Optionen | Empfehlung | Aufwand | Risiko | Betroffene Funktion |
| --- | --- | --- | --- | --- | --- | --- |
| V7, M16-01 | Gebührenbetrag je Mahnstufe, Basiszinssatz, vertragliche Grundlage der Weiterbelastung | (a) Beträge nach Rückmeldung des Rechtsanwalts eintragen; (b) vorerst ohne Gebühr mahnen | (a); bis zur Rückmeldung Stufen ohne Gebühr laufen lassen, weil Ablauf und Texte damit bereits produktiv geübt werden können | gering (Eingabe unter Einstellungen, Mahnwesen) | Unzulässige Gebührenhöhe ist Haftungsrisiko; daher Rechtsanwalt einbinden | Mahnlauf, Sollstellung der Gebühr, Rechnung HVM an Forderungsinhaber |
| M16-02 | Freigabe der Standardtexte je Stufe; Versandweg und Zustellnachweis | (a) Standardtexte freigeben; (b) je Stufe eigene `letter_text` hinterlegen | (a) mit Durchsicht durch Rechtsanwalt, insbesondere ohne Verzugsaussage; Versand über M23-01 klären | gering | Fehlerhafte Verzugsaussage in Mahnung; Zustellung ohne Nachweis | Mahnschreiben PDF, Versand |
| M16-03 | Zusätzliche Sperrgründe (Zugang, Verbraucher, Ratenplan, bestritten, Prozess) | (a) Mahnsperre am Vertrag beibehalten; (b) strukturierte Sperrgründe ergänzen | (b) als kleine Erweiterung nach Rückmeldung des Rechtsanwalts | mittel | Mahnung trotz Ratenplan oder laufendem Verfahren | Mahnvorschau, Mahnlauf |
| M16-08 | Geschäftsjahresbeginn und Eröffnungsbestände des Verwalter-Buchungskreises; führendes System | (a) Januar, Eröffnungsbestände zum Migrationsstichtag; (b) abweichendes Geschäftsjahr | (a); Buchung eigener Erlöse erst mit G1 | gering | Doppelte Erlösbuchung bei parallelem Buchhaltungssystem der HVM | Verwalterhonorar, Gebührenrechnungen |
| M16-12 | Zahlungsfrist Stufe 4 (letzte Mahnung) | Wert in Tagen | 7 Tage wie Stufe 3, weil danach der Mahnbescheid vorbereitet wird | gering | keines | Mahnschreiben |
| M16-13 | Bankkonto je Forderungsinhaber im Mahnschreiben | (a) Konto je Rechtsträger freigeben; (b) Verweis auf bekanntes Konto beibehalten | (a), weil ein Schreiben ohne Konto Rückfragen und Fehlüberweisungen an die Verwaltung erzeugt | mittel (Freigabe je Rechtsträger, dann Ausgabe) | Konto der Verwaltung darf nie erscheinen | Mahnschreiben |
| M16-14 | Abnahme der Sperre "Zahlungserinnerung 0,00 EUR" | Abnahme | Abnehmen, Tests umstellen lassen | gering | keines | Mahnlauf |
| M12-03 | Ausgleich bei mehreren offenen Posten desselben Debitors | (a) manuelle Prüfung ohne ausdrückliche Bestimmung (aktueller Stand); (b) Betragstreffer genügen lassen | (a) beibehalten | keiner | Fehlzuordnung von Zahlungen | Zahlungszuordnung |
| M10-03 | Tilgungsfolge und Guthabenverrechnung | Regel durch Rechtsanwalt freigeben | Bis zur Freigabe manuell; Regel als konfigurierbare, quellenpflichtige Regel umsetzen | mittel | falsche Tilgung wirkt auf Verzug und Mahnung | offene Posten |
| M10-05 | Vergleichsbuchung im nicht führenden Buchungskreis | (a) beibehalten; (b) harte Sperre des Sollstellungslaufs | (a), weil der Abgleich gegen Immoware24 im Parallelbetrieb sonst entfällt | keiner | keines, externe Wirkung ist gesperrt | Parallelbetrieb |
| M5-02 | Kautionen: Verzinsung, Anlageform, Abrechnung bei Vertragsende | Regel mit Quelle freigeben | Rechtsanwalt beauftragen; bis dahin nur Erfassung | mittel nach Freigabe | Fehlerhafte Kautionsabrechnung ist Streitfall | Kautionsverwaltung |
| M5-03 | Mietverhältnisse in reinen WEG-Objekten ablehnen (A-015) | (a) Ablehnung beibehalten; (b) Verwaltungsart WEG mit SEV vorschreiben | (a) bestätigen | keiner | keines | Vertragsanlage |

### B.2 Rechnungseingang, E-Rechnung, Steuer

| Kennung | Frage | Optionen | Empfehlung | Aufwand | Risiko | Betroffene Funktion |
| --- | --- | --- | --- | --- | --- | --- |
| V12, M13-04 | USt-Status, Steuerdaten, Leitweg-ID, IBAN je Mandant; Leitweg-ID je Empfänger; Zahlungsziel; KoSIT-Validator in CI | Eingabe unter Einstellungen, Mandant; Leitweg-ID je Empfänger ergänzen oder je Mandant belassen | Werte mit Steuerberater eintragen; Leitweg-ID je Empfänger vorsehen, weil sie fachlich den Empfänger kennzeichnet; Zahlungsziel je Verwaltervertrag; Validator-Jar bereitstellen | gering (Eingabe), mittel (Leitweg-ID je Empfänger) | Fehlerhafte E-Rechnung wird abgelehnt; Pflichtangaben | Honorarrechnung XRechnung |
| M14-06 | Prüfung eingehender XRechnungen gegen XSD und Schematron vor G1; Gutschriften | (a) KoSIT-Validator anbinden; (b) strukturelles Lesen genügt | (b) für den Belegeingang, weil die Prüfung am Original ohnehin erfolgt; (a) nur für ausgehende Rechnungen | mittel für (a) | gering | Belegeingang |
| M14-01 | Feldkonfidenz vom Modell, Vollmaskierung, Mailansicht auf Belegentwurf | (1) Feldkonfidenz verlangen; (2) Vollmaskierung; (3) Umstellung Mailansicht | (3) umsetzen; (1) und (2) nach Datenschutzvorgabe | mittel | Personenname des Ausstellers geht an den Anbieter | Belegeingang, KI-Extraktion |
| M14-03 | Freigabematrix mit Betragsgrenzen je Objekt | Matrix festlegen | Zwei Stufen: bis 2.500,00 EUR eine Prüfung, darüber Vier-Augen; Beträge sind Vorschlag des Coding-Agents ohne Rechtsgrundlage und vom Betreiber festzulegen | mittel | Zahlung ohne ausreichende Prüfung | Rechnungsprüfung, Zahlungsfreigabe |
| M14-05 | Automatischer Rechnungs-Intake aktivieren; Kostengrenze je Entwurf | Schalter je Mandant, Kostengrenze | Nach AVV aktivieren, Kostengrenze je Lauf im KI-Budget setzen | gering | KI-Kosten ohne Deckel | Belegeingang aus E-Mail und Paperless |
| M14-02 | Vorsteuerregel und Steuerkonten je Rechtsträger | Steuerberater | Freigabe je Buchungskreis mit Option | gering nach Freigabe | falscher Vorsteuerabzug | Rechnungsbuchung |
| M14-04 | § 35a: welche Belege als Aufteilung genügen, Übergang in die Abrechnung | Steuerberater | Regel festlegen; bis dahin keine Ausweisung aus dem Belegeingang | mittel | falsche Bescheinigung gegenüber Mietern und Eigentümern | Belegeingang, Abrechnung |
| M18-01 | DATEV-Kennzahlen, Kontenzuordnung, Prüfexport-Layout, GoBD-Datenträgerüberlassung | Mit Steuerberater abstimmen | Termin mit Steuerberater: Beraternummer, Mandantennummer, SKR, Zuordnung als CSV, Prüfexport zeigen | gering (Eingabe), mittel (Zuordnung) | Export ohne Zuordnung bricht ab | DATEV-Export, Prüfexport |
| M18-02 | Zugriffsbereich für weitere Rollen; Steuerberater mit Zusatzrolle | (a) nur Steuerberater; (b) auch Beirat und externe Prüfer | (a) vorerst; (b) mit M21-03 Beiratsrolle | mittel für (b) | Einsicht über Rechtsträgergrenze hinweg | Benutzerverwaltung |

### B.3 KI und Datenschutz

| Kennung | Frage | Optionen | Empfehlung | Aufwand | Risiko | Betroffene Funktion |
| --- | --- | --- | --- | --- | --- | --- |
| V10, M7-01, M7-02 | AVV mit Anthropic und OpenAI, Trainingsausschluss, Endpunktregion, Schlüssel, Preise je Stufe, Freigabe durch zweite Person | Verträge abschließen, Werte eintragen | Beide Anbieter mit AVV, Anthropic zuerst als Strategie; ohne AVV bleibt nur der Regel-Fallback | gering (Eingabe), Vorlauf für Verträge | Personenbezogene Daten ohne Rechtsgrundlage beim Anbieter | Alle KI-Aufgaben |
| M7-07 | Endpunkt-URL je Anbieter und Region | (a) URL festlegen und Übergabe in der Factory umsetzen; (b) Region als unwirksam kennzeichnen | (a) nach Klärung, ob der AVV den Endpunkt abdeckt; bis dahin (b) | mittel | Eingetragene EU-Region ist derzeit ohne Wirkung | KI-Anbieterkonfiguration |
| M7-03 | Einbettungen für RAG: OpenAI oder lokales Modell | (a) lokales Modell (Ollama); (b) OpenAI-Einbettungen | (a), weil keine Daten den Server verlassen und der Server (32 Kerne) Reserven hat; Volltextsuche bleibt bis dahin | hoch | gering | Kontext-Chat, Portal-Chat |
| M7-04 | Lernbeispiele je Mandant: Datenminimierung oder Pseudonymisierung | (a) nur strukturelle Merkmale; (b) pseudonymisierte Volltexte | (a) | mittel | Datenschutz | KI-Qualität |
| M7-05 | Live-Evaluation nach Anbieterfreigabe | einmaliger Lauf | Nach M7-01 einmal ausführen, Antworten aufzeichnen | gering | keines | Stufenwechsel, Prompt-Änderungen |
| M7-09, M12-01 | KI-Kontierung `propose_posting` freischalten | Schalter `ai_posting_enabled` nach AVV | Erst nach AVV und Evaluationsdatensatz mit mindestens 20 Fällen | gering (Schalter), mittel (Datensatz) | Vorschläge bleiben Vorschläge (7.4), Risiko gering | Zahlungszuordnung |
| M12-02 | Unabhängiger Testbestand für M12 | 100 bis 200 anonymisierte Umsätze mit Sollzuordnung | Buchhaltung beauftragen, zwei Stunden Aufwand | gering | keines | Abnahme M12 |
| M20-02 | KI-Klassifikation und Antwortentwürfe mit Anbieter | nach AVV freigeben | Regel-Fallback läuft bereits; nach AVV freischalten | gering | gering | Postfach |
| M34-01 | Freigabeworkflow für KI-Wissenseinträge | (a) Vier-Augen wie Playbooks; (b) frei pflegbar | (a), weil Einträge in KI-Antworten an Dritte fließen | mittel | Falsche Auskunft im Portal-Chat | KI-Wissensbasis |
| M9-09 | Katalog der KI-Aufgaben aus Regeln; Budget je Regel | (a) Katalog beibehalten, Budget wie manuelle Läufe; (b) Obergrenze je Regel und Tag | (a), (b) bei Bedarf | gering | Budgetverbrauch durch Regeln | Regel-Engine |
| M26-04 | Speicherdauer und Datenschutzhinweis für Interessenten | Datenschutzberatung | Frist festlegen, Hinweistext freigeben | gering | DSGVO | Interessentenverwaltung |
| M2-06 | Benutzerfoto | (a) Initialen beibehalten; (b) Foto-Upload | (a), kein Bedarf, kein Löschkonzept nötig | keiner | keines | Benutzermenü |
| M30-04 | Pillow als direkte Abhängigkeit; Altbilder bereinigen; Ortsermittlung | (a) Pillow aufnehmen, Altbilder einmalig bereinigen, keine Ortsermittlung | (a) | gering | Metadaten in Altbildern | Übergabeprotokoll Fotos |

### B.4 Portal, Kommunikation, Kanäle

| Kennung | Frage | Optionen | Empfehlung | Aufwand | Risiko | Betroffene Funktion |
| --- | --- | --- | --- | --- | --- | --- |
| M21-01 | Priorität der Portalfunktionen (Magic-Link, QR-Einladung, Chat, digitales SEPA-Mandat) | Reihenfolge festlegen | Schwarzes Brett, Formulare, Lesebestätigung und PWA sind mit Version 1.22.0 vorhanden (`mhvp.portal`); als nächstes QR-Einladung (M21-08) und Magic-Link; SEPA-Mandat erst mit G2 | mittel je Funktion | gering | Portal |
| M21-03 | Standardfreigabe von Dokumenten für Mieter auf keine ändern; Rollen Beirat und Vertreter | (a) Standard auf keine Freigabe; (b) Standard beibehalten | (a) vor produktiver Portalnutzung; Beiratsrolle mit M25 | gering für (a), mittel für Rollen | Unbeabsichtigte Einsicht | Dokumente, Portal |
| M21-08 | QR-Code im Einladungs-PDF (Abhängigkeit `segno`) | (a) `segno` aufnehmen; (b) Link als Text | (a) nach Lizenzprüfung (reines Python) | gering | keines | Einladung |
| M30-05 | Zweiter Faktor für Portalnutzer und Gehilfen | (a) TOTP beibehalten; (b) Code per E-Mail für Portalnutzer | (b) für Portalnutzer ohne Freigaberechte, weil die Hürde sonst die Nutzung verhindert; CRM bleibt TOTP | mittel | Schwächerer Faktor im Portal | Anmeldung Portal |
| M20-03 | Direktversand einfacher Antworten ohne Vier-Augen | (a) Freigabe beibehalten; (b) Direktversand nur für unveränderte Antwortvorlagen ohne Anhänge mit Protokoll | (b) mit Mandantenschalter, Standard aus | mittel | Fehlerhafte Erklärung an Mieter oder Eigentümer | Tickets, Postausgang |
| M20-01 | Google-OAuth-Client anlegen, Zustimmung für info@muellerhv.de | Betreiberaktion | Sofort ausführen, Anleitung in `docs/plans/M20.md` | gering | keines | Postfach |
| M23-03 | Postfächer für Kalender-Schreibrecht neu verbinden; Button am Übergabeprotokoll | Betreiberaktion | Neu verbinden; Button bei Bedarf | gering | keines | Kalender |
| M23-01 | Brief- und Postversand: Dienstleister oder eigene Poststelle | (a) Druckdienstleister mit AVV; (b) eigene Poststelle mit Nachweisdokumentation | (b) bis zum Marktstart, weil das Volumen der HVM überschaubar ist; (a) mit G5 | gering für (b), hoch für (a) | Zustellnachweis bei Fristen | Zustellung |
| M23-06 | Telefonie: Anbieter, Adapter, AVV | Anbieter wählen | Nur wenn die Telefonanlage Webhooks liefern kann; sonst zurückstellen | mittel | Rufnummernverarbeitung ohne AVV | Anrufnotizen |
| M35-08 | SMS-Anbieter für SLA-Eskalation | Anbieter wählen | Anbieter mit AVV in der EU wählen, Zugangsdaten hinterlegen; Beispielvorlage seven.io liegt vor | gering | keines | SLA-Eskalation |
| M21-06 | WhatsApp-Kanal: Meta-Geschäftskonto, Nummer, Vorlagen | Freigabe bei Meta beantragen | Nur wenn Mieter den Kanal nachfragen; SMS bleibt Rückfall | mittel (Freigabeprozess bei Meta) | Datenschutz, Kosten je Vorlage | SLA-Eskalation, Notfall |
| M19-01 | SLA je Ticketkategorie; Feiertage NRW | Werte festlegen | Presets übernehmen, Feiertagsliste einmal jährlich pflegen | gering | keines | Tickets |
| M19-02 | Beiratsbeteiligung bei Aufträgen: Wertgrenzen je GdWE | Wertgrenzen | Grenzen aus den Beschlüssen je GdWE erfassen; Rechtsanwalt bei Unsicherheit | gering | Auftrag ohne Beschlussgrundlage | Aufträge |
| M22-01 | Drei Dienstleister für den Pilot benennen | Auswahl | Handwerker mit regelmäßigem Rechnungsvolumen wählen | gering | keines | Dienstleisterportal |
| M9-06 | Dienstleisterverträge mit Laufzeit und Kündigungsfrist (umgesetzt als `ServiceContract`) | Bestätigung des Modells | Bestätigen, Verträge nachpflegen | gering | verpasste Kündigungsfrist | Fristenliste |
| M9-08 | Wiederholungsplan für Regel-Webhooks | (a) ohne Wiederholung; (b) Wiederholungsplan wie Abonnements | (a) | keiner | Empfänger muss idempotent sein | Regel-Engine |
| M9-10 | Kennzeichnung automatisch erzeugter Briefe als Entwurf | (a) Kategorie "Entwurf aus Regel"; (b) keine Kennzeichnung | (a) | gering | Entwurf wird versehentlich versendet | Regel-Engine, Dokumente |
| M34-03 | Mehrdeutige Rollen in der Mail-Vorbereitung | (a) Warnung bei mehreren aktiven Verträgen; (b) letzter Vertrag | (a) | gering | falsche Anrede oder Zuordnung | Mail-Vorbereitung |

### B.5 WEG und Versammlung

| Kennung | Frage | Optionen | Empfehlung | Aufwand | Risiko | Betroffene Funktion |
| --- | --- | --- | --- | --- | --- | --- |
| M25-01 | Inhalt der Mehrheitsregeln je GdWE | Erfassung mit Fundstelle | Je Pilot-WEG aus Teilungserklärung erfassen, Rechtsanwalt prüft | gering je GdWE | falsche Verkündung; Verkündung bleibt bei der Versammlungsleitung | Beschlussfassung |
| M25-02 | Umlaufbeschluss mit geringerer Mehrheit | (a) Bedarf verneinen; (b) umsetzen nach Rechtsrat | (a) bis eine GdWE es beschließt | hoch für (b) | Rechtsfehler | Umlaufbeschluss |
| M25-03 | Einladungsfrist und Zugang | Rechtsanwalt bestätigt Fristlogik | Bestätigen lassen, Zugangsdatum immer erfassen | gering | Anfechtbarkeit | Versammlung |
| M25-04 | Protokollvorlage und Einsichtsablauf | Vorlage freigeben | Vorlage mit Rechtsanwalt durchsehen; Einsichtsanfragen laufen über `mhvp.hoa.inspection` | gering | Protokoll ohne Rechtsfolge, gering | Protokoll |
| M25-05 | Einsichtsrechte: Kategorien, Fristen, Form | Rechtsanwalt | Freigabe je Anfrage beibehalten; Regel erst nach Bestätigung | mittel | Verweigerung berechtigter Einsicht | Einsichtsanfragen |
| M24-02 | Gliederung Vermögensbericht | Rechtsanwalt | Gliederung nach § 28 Abs. 4 WEG prüfen lassen (Rechtsprüfung nötig, keine eigene Aussage) | gering | Formfehler | Vermögensbericht |
| M24-03 | Darlehen, Erklärungscodes, Versicherungsfälle | Rechtsanwalt und Steuerberater | Bis zur Entscheidung nur ausweisen; unerklärte Differenz sperrt das Paket | mittel | Fehlerhafte Verteilung | Jahresabrechnung |
| M1-09 | Zeitzone Europe/Berlin für Fristen | bestätigen | Bestätigen; im Code bereits so verwendet | keiner | keines | Fristen |

### B.6 Vermietung und Makler

| Kennung | Frage | Optionen | Empfehlung | Aufwand | Risiko | Betroffene Funktion |
| --- | --- | --- | --- | --- | --- | --- |
| M26-02 | OpenImmo-XSD (Lizenz), Kontaktfeld je Anzeige, Bildsortierung | (a) XSD beschaffen; (b) Validierung gegen Zielportal | (b) beim ersten Portal; Bildsortierung mit Titelbild ergänzen | mittel | Export wird vom Portal abgelehnt | Anzeigenexport |
| M26-03 | Pflichtangaben in Immobilienanzeigen (Energieausweis) | Rechtsanwalt | Pflichtfelder bestätigen, dann Vollständigkeitsprüfung schärfen | gering | Bußgeld bei fehlenden Pflichtangaben (Rechtsprüfung nötig) | Exposé, Anzeige |
| M28-01 | Müller FLOW und FLOWFACT: Quellcode, API-Dokumentation, Zugangsdaten | bereitstellen oder Bereich Makler zurückstellen | Zurückstellen bis nach G3; ohne Dokumentation kein Bau | hoch | keines | Makler |

### B.7 Lizenz und Marktstart

| Kennung | Frage | Optionen | Empfehlung | Aufwand | Risiko | Betroffene Funktion |
| --- | --- | --- | --- | --- | --- | --- |
| M27-01 | Beträge und Umsatzsteuer der Lizenzentgelte; Durchsetzung des Kontingents | Preise eintragen; (a) Kontingent nur anzeigen; (b) technisch durchsetzen | Preise mit Steuerberater (Umsatzsteuer) festlegen; (a) im Pilot, (b) mit G5 | gering (Eingabe), mittel (b) | Umsatzsteuerfehler bei Rechnungen der Müller Holding AG | Lizenzabrechnung |
| M27-02 | G5-Nachweise Backup und Wiederherstellung; Penetrationstest-Bericht | Nachweise ablegen | Wiederherstellungstest vom 24.09.2026 als Nachweis ablegen; Bericht des KI-gestützten Tests ablegen; unabhängige Prüfung vor Fremdmandanten prüfen | gering | Kunden oder Versicherer verlangen Drittprüfung | G5 |
| M27-03 | Verfahrensdokumentation im Pilotbetrieb | Umsetzung | Ab G1 laufend fortschreiben | mittel | GoBD | G1, G5 |
| V4, V5, M1-05 | Produktname, Domains, Entwicklungsmodell, Repository-Name | Entscheidung | Bis G5 nicht blockierend; Arbeitstitel beibehalten | gering | keines | Branding |

---

## C. Betrieb und Server

| Kennung | Frage | Empfehlung | Aufwand | Risiko | Wer |
| --- | --- | --- | --- | --- | --- |
| M9-05 (SSH) | Schlüsselanmeldung, Passwortanmeldung deaktivieren, cloud-init stilllegen, IONOS-Firewall, Ursachenprüfung Zugangsverlust | Runbook `docs/runbooks/server-recovery-und-haertung.md` und `scripts/server/harden-ssh.sh` ausführen; Version 1.22.1 lässt Passwortanmeldung standardmäßig aktiv, daher bewusst umschalten, vorher zweiten Schlüssel testen | gering | Zugangsverlust bei Fehlbedienung; unbefugter Zugriff bei Passwortanmeldung | Betreiber |
| M9-02 | Offsite-Speicherort für Backups, echtes age-Schlüsselpaar, WAL-Archivierung | Speicherort in der EU außerhalb IONOS (zweiter Anbieter), Schlüssel getrennt verwahren, WAL-Archivierung als zweite Stufe | gering (Ziel), mittel (WAL) | Datenverlust bei Serverausfall | Betreiber |
| M9-03 | Löschjournal: Aufbewahrungsort und Frist, Prüfer des Replay-Berichts, Umgang mit `kept_hold` und `kept_mirrored`, Verfahren ohne Journal | Verfahren nach Runbook durch Datenschutz freigeben; Prüfer: Betreiber, Vertretung zweiter Administrator | gering | Wiederauftauchen rechtmäßig gelöschter Daten | Betreiber mit Datenschutz |
| M9-04 | Alarmziel (E-Mail, Telefon) für Health-Check | Webhook auf E-Mail und SMS-Gateway (M35-08) legen | gering | Ausfall bleibt unbemerkt | Betreiber |
| M1-01 | Objektspeicher für Produktion (MinIO archiviert) | SeaweedFS wie im Entwicklungsstack, sofern Produktion es bereits nutzt; sonst verwalteter S3-Dienst in der EU; Bewertung nach ADR 0005 | mittel | Ungepflegte Software im Produktivbetrieb | Betreiber |
| M1-02 | Traefik-Parameter des Servers (Netzwerk, Entrypoint, Cert-Resolver) | Werte aus der laufenden Produktion (M9-01) in `.env` dokumentieren und bestätigen | gering | keines | Betreiber |
| M1-03 | Container-Registry | Ohne Registry (Build aus Git-Tag) beibehalten | keiner | keines | Betreiber |
| M1-04 | CI-Plattform GitHub Actions bestätigen | bestätigen | keiner | keines | Betreiber |
| M1-06 | DNS-Einträge, insbesondere portal.muellerhv.de und Staging | Prüfen, ob alle Einträge gesetzt sind (crm, api, portal.mueller-holding.ag laufen laut M9-01) | gering | keines | Betreiber |
| M1-07 | Netzwerkrichtlinie der Entwicklungsumgebung (Docker Hub) | Host freigeben | gering | keines | Betreiber |
| M2-01 | Passwortregel und Kontosperre (A-012) bestätigen | bestätigen, Quelle der BSI-Empfehlung im Handbuch nachtragen | gering | keines | Betreiber |
| M2-02 | Zweiten Plattformadministrator benennen | Person benennen, weil ohne sie keine Freigabestufe genehmigt werden kann | gering | Alleinentscheidung ohne Kontrolle | Betreiber |
| M2-03 | Seed-Werte: USt-IdNr., Telefon, E-Mail, Logo, c/o-Anschrift des Einzelunternehmens | Unter Einstellungen, Mandant eintragen; Eignung der c/o-Anschrift für Impressum und Rechnungen mit Steuerberater prüfen | gering | Pflichtangaben auf Rechnungen fehlen | Betreiber |
| V14, M1-08 | CI-Werte je Mandant aus hvm-ci, mhag-ci, tm-privat-ci freigeben | Werte aus den Skills übernehmen, keine erfundenen Werte | gering | keines | Betreiber |
| M30-01 | OIDC-Client für die Statusseite anlegen | Runbook `docs/runbooks/oidc-relying-parties.md` ausführen | gering | keines | Betreiber |
| M11-45 | finAPI-Callback und Ratenlimits | nach Vertragsabschluss nachziehen | mittel | keines | Betreiber, Coding-Agent |
| V11, M6-01, M6-02 | Paperless-Token und Custom Fields; Google-OAuth-Client und Wurzelordner je Mandant; AVV Google | Token und IDs bereitstellen; Drive erst nach AVV-Nachweis | gering | Übertragung personenbezogener Dokumente ohne AVV | Betreiber mit Datenschutz |
| M6-03 | Löschung in den Spiegeln, Bereinigung verwaister Objekte | Mit V17 umsetzen | mittel | gespiegelte Kopien überleben die Löschung | Coding-Agent nach V17 |
| M29-01 | Schnittstelle im Repository objektakte (Token, Webhook) | Auftrag erteilen oder DMS-Reiter zurückstellen | mittel | keines | Betreiber |
| M35-01 bis M35-07 | objektakte-Migration: Klassifikationsmodell, Vorschaubilder, Schlüsselübergabe, OCR, Parallelbetrieb, Drive-Quota, Archiv | Neustart mit Regeln statt Modellübernahme; Vorschaubilder neu rendern; Schlüsselübergabe im Vier-Augen-Termin; OCR über Paperless; Archiv als verschlüsselter Dump mit Aufbewahrung nach V17 | hoch insgesamt | Datenschutz bei Schlüsselübergabe | Betreiber mit Datenschutz |

---

## D. Daten und Import

### D.1 Immoware24

| Kennung | Frage | Empfehlung | Aufwand | Risiko | Wer |
| --- | --- | --- | --- | --- | --- |
| V6 | Immoware24-Vertrag: Laufzeit, Kündigung, Exportrechte, Nutzungsgrenzen | Vertrag heraussuchen, Kündigungstermin mit Vorfrist eintragen; Ablösetermin erst aus dem Vertrag ableiten | gering | Doppelte Kosten bei verpasster Kündigung; Datenverlust bei Exportgrenzen | Betreiber |
| V9, M8-03, M9-05 (Parallelbetrieb) | Migrationsstichtag je Objekt, Dauer des Parallelbetriebs | Stichtag zum Beginn eines Abrechnungsjahres (01.01.) für WEG, zum Monatsersten für Mietobjekte; Parallelbetrieb drei Monate mit täglichem Abgleichbericht | gering | Überleitungslücken | Betreiber mit Steuerberater |
| M8-01 | Echte Exporte (Objektliste, Belegungsliste, Adressbuch, Mietverträge, Eigentümerverträge, Zahlungen) in Staging | Dateien hochladen, Vorlagen je Report gemeinsam anlegen, Testlauf | gering | keines, Staging | Betreiber |
| M8-02 | Referenzzahlen aus Immoware24 (Objekte, Einheiten, Summen Sollstellungen) | Summenreport je Objekt bereitstellen | gering | keines | Betreiber |
| M8-04 | Mehrpersonen-Parteien (Eheleute, Erbengemeinschaften) | An echten Exporten prüfen, dann Zuordnung ergänzen | mittel | Falsche Debitorenzuordnung | Betreiber, Coding-Agent |
| M11-02 | Bankspezifische CSV und Immoware24-Umsatzexport | Je Bank eine anonymisierte Beispieldatei bereitstellen | gering (Datei), mittel (Umsetzung) | keines | Betreiber |
| M12-02 | Anonymisierter Umsatzbestand mit Sollzuordnung | 100 bis 200 Umsätze | gering | keines | Betreiber |
| M13-05 | Lasttest mit importiertem Bestand | Nach M8-01 wiederholen | gering | keines | Coding-Agent |
| M32-02 | DAV-Modul bei Immoware24 gebucht? Basis-URL, Benutzerpfad | Beim Support nachfragen; bis dahin bleibt der Weg ohne Wirkung | gering | keines | Betreiber |
| V1 | Dossiers Müller FLOW, Übergabeprotokoll, Objektakte, smart-einzug | Übergabeprotokoll und Objektakte sind über M30 und M35 in Arbeit; FLOW mit M28 zurückstellen; smart-einzug bewerten | gering | keines | Betreiber |
| M30-02, M30-03 | Übergabeprotokoll: Beweiswert und Einwilligungstext; Export aus uprotokoll.muellerhv.de, Versionsverknüpfung, E-Mail-Historie | Rechtsanwalt zum Beweiswert; Export nach Anleitung erstellen; Versionen verknüpfen, E-Mail-Historie als Dokument übernehmen | mittel | Beweiskraft im Streitfall | Betreiber mit Rechtsanwalt |

### D.2 Objekt 2911

Der Import der Objektliste (Handbuch `docs/handbuch/import-objektdaten.md`) führt dreistellige Objektnummern. Für die Liste vom 26.09.2026 hat der Betreiber die Zuordnungen `10012=012`, `10013=013`, `10014=014`, `999999=999` festgelegt. Objekt 2911 (Schadestraße 3) bleibt ausgenommen, weil die Nummer 291 durch Schadestraße 3a belegt ist.

Entscheidung: freie dreistellige Nummer für Objekt 2911 benennen. Empfehlung: die nächste freie Nummer im Bereich der Nachbarobjekte wählen (der Coding-Agent nennt keine Nummer, weil die Belegung nur aus der aktuellen Objektliste hervorgeht) und die Zuordnung mit `--number-map 2911=<Nummer>` beim Übernahmelauf mitgeben. Bis dahin fehlt das Objekt in Plattform, Abgleichbericht und Fristenliste. Aufwand gering, Risiko keines.

### D.3 Spaltenannahmen des Abgleichberichts (A-047)

Der tägliche Abgleichbericht des Parallelbetriebs (`mhvp.imports.reconciliation`, `POST /api/v1/imports/reconciliation-reports`) liest die Immoware24-Exporte Journal und Bankumsätze mit angenommenen Standardspalten: Journal `Objekt`, `Konto`, `Datum`, `Betrag` (Soll positiv, Haben negativ), ersatzweise `Soll` und `Haben`; Bankumsätze `Objekt`, `IBAN`, `Datum`, `Betrag` (Gutschrift positiv), optional `Saldo`. Kontonummern werden auf sechs Stellen, Objektnummern auf drei Stellen aufgefüllt. Die Kontoart kommt aus dem gleichnamigen Konto des Buchungskreises. Die Zuordnung ist je Mandant über `PUT /api/v1/imports/reconciliation-reports/columns` änderbar. Der Bericht liest nur, bucht nichts.

Entscheidung: Die Annahme ist mit den echten Exportdateien (M8-01, M8-02) zu prüfen. Empfehlung: Beim ersten Testlauf in Staging die tatsächlichen Spaltennamen und Vorzeichenkonvention (Soll/Haben oder signierter Betrag) an den Exportdateien ablesen, die Zuordnung je Mandant eintragen und den Bericht gegen einen bekannten Monat kontrollieren (Summen je Objekt gegen den Immoware24-Summenreport). Erst danach gilt der Bericht als Abgleichsgrundlage für den Parallelbetrieb. Aufwand gering, Risiko: eine falsche Zuordnung führt zu ausgewiesenen Abweichungen, nie zu Buchungen.

### D.4 Aufbewahrung und Löschung

| Kennung | Frage | Empfehlung | Wer |
| --- | --- | --- | --- |
| V17, M6-04 | Aufbewahrungsmatrix je Rechtsträger und Unterlagenklasse, Sperrgründe, Belegeinsicht ohne Portal | Entwurf durch den Coding-Agent aus Anhang C (R17, R18, R21) vorbereiten lassen, Steuerberater prüft Fristen, Freigabe im Vier-Augen-Prinzip | Betreiber mit Steuerberater |
| M11-03 | Dokumentkategorie Kontoauszug mit Aufbewahrungsprofil | Mit der Matrix anlegen | Betreiber |
| M35-07 | Archiv des objektakte-Stacks | Frist und Ablageort nach der Matrix | Betreiber |
| M26-04 | Speicherdauer Interessenten | Frist und Hinweistext durch Datenschutzberatung | Betreiber |

---

## E. Statusänderungen vom 26.09.2026 in `docs/OPEN_QUESTIONS.md`

Die folgenden 60 Zeilen wurden auf "technisch umgesetzt, Entscheidung offen (26.09.2026)" gesetzt; der bisherige Statustext wurde jeweils mit "zuvor:" beibehalten. Grundlage war eine Prüfung gegen den Code (Module, Endpunkte, Migrationen, Tests) am 26.09.2026.

V7, V11, M1-02, M1-03, M1-04, M1-09, M2-01, M2-02, M2-03, M5-03, M6-01, M6-02, M6-04, M7-01, M7-02, M9-03, M9-04, M9-05 (SSH-Härtung), M9-06, M9-08, M9-09, M9-10, M10-01, M10-02, M10-04, M10-05, M11-03, M12-03, M13-04, M14-01 (extract_invoice), M14-05, M14-06, M15-02, M16-01, M16-08, M16-12, M16-14, M17-03, M17-04, M18-02, M19-01, M20-01, M20-02, M20-03, M21-06, M22-01, M23-03, M23-06, M24-02, M25-01, M25-03, M25-04, M25-05, M26-03, M26-04, M27-01, M30-01 (Statusseite), M30-02, M34-01, M35-08.

Nicht geändert wurden Punkte, die noch Entwicklungsarbeit nach der Entscheidung brauchen (zum Beispiel M7-07, M7-03, M10-03, M13-01 bis M13-03, M16-13, M17-06, M21-08, M26-02), Punkte mit externem Vorlauf (Bank, finAPI, Immoware24-Support, Meta) und alle V- und P-Punkte, die eine Rechts- oder Steuerprüfung ohne technischen Anteil sind.

Hinweis zu M7-07: Der Client `mhvp.ai.providers` kennt inzwischen `base_url`, die Factory `default_factory` übergibt sie aber weiterhin nicht. Der Punkt bleibt daher offen.

---

## F. Vorgeschlagene Termine

| Termin | Inhalt | Teilnehmer |
| --- | --- | --- |
| Woche 1 | Kurzfassung Nr. 1, 9, 10: fachkundige Person, zweiter Administrator, Serverhärtung, Alarmziel | Betreiber |
| Woche 1 bis 2 | Steuerberater: Kontenrahmen, DATEV-Parameter, E-Rechnung, Aufbewahrungsmatrix, Vorsteuer, § 35a | Betreiber, Steuerberater |
| Woche 2 | Rechtsanwalt: Mahngebühren und Verzug, Kaution, Tilgungsfolge, Abrechnungsfristen, WEG-Punkte P01, P02, M24, M25 als gebündelter Prüfauftrag | Betreiber, Rechtsanwalt |
| Woche 2 bis 4 | AVV Anthropic, OpenAI, finAPI, Google; finAPI-Vertrag und § 34 ZAG | Betreiber, Datenschutz, Rechtsanwalt |
| Woche 3 | Immoware24-Exporte in Staging, Spaltenzuordnung, Objekt 2911, Referenzzahlen, Migrationsstichtag | Betreiber, Buchhaltung HVM |
| nach Woche 4 | Antrag G1 für Pilotobjekte | Betreiber, zweiter Administrator |

Alle Fristen und Termine in dieser Vorlage sind Planungsvorschläge und keine Rechtsfristen. Vertragliche Kündigungsfristen (V6) sind aus den Originalunterlagen zu ermitteln und mit Vorfrist einzutragen.
