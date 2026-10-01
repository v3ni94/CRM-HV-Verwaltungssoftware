# Entscheidungsliste für den Vorstand, Stand 01.10.2026

Adressat: Timo Müller (Betreiber). Quelle: `docs/OPEN_QUESTIONS.md`, Punkte der Wellen 4 bis 7 (R, T, U, V) sowie S69-01-01, S16-03-02, M17-09-01, M11-09-01; ergänzend T08, S16-03-01 und M9-02-01 aus Welle 5. Testnachweise je Paket: `docs/acceptance/PROTOKOLL-2026-10-01-WELLEN-4-7.md`.

Lesart:
- Je Frage zuerst Ergebnis (Stand der Technik) und Empfehlung, danach drei Alternativen. Alternative A entspricht der Empfehlung.
- Aufwand und Risiko sind eine Einschätzung der Entwicklung (gering, mittel, hoch), keine Kostenschätzung.
- Rechtliche und steuerliche Punkte sind keine Rechtsauskunft. Sie sind als Einschätzung formuliert und vor einer Entscheidung mit Rechtsanwalt oder Steuerberater abzustimmen.
- Keine Entscheidung öffnet ein Gate. G1 bis G5 bleiben geschlossen, bis die jeweilige Freigabe nach Abschnitt 18.0 vorliegt.

## Priorität für die nächste Sitzung

1. G1 vorbereiten: T04-01 und T03-01 an den Steuerberater, M11-09-01 und T10-01 Musterdateien aus Immoware24 liefern.
2. G4 vorbereiten: R05-01, T13-02, T13-03 und V05-01 gebündelt an den Rechtsanwalt; U07-01/V10-01 an Fachbereich WEG.
3. Datenschutz bündeln: T01-01/V04-01, U15-04, M9-02-01 in einem Termin mit dem Datenschutz.
4. Reine Bestätigungen ohne Mehraufwand: U04-02, U15-01, U15-02, V01-01, T13-01, R09-02, S16-03-01.

## G1 Produktive Buchhaltung

### T04-01 Umsatzsteuer auf das Verwalterhonorar (Eigentümer Timo Müller, Steuerberater)
Ergebnis: Optionale USt-Konten je Seite sind technisch vorhanden; ohne Konto wird brutto auf Aufwand oder Erlös gebucht.
Empfehlung: Steuerberater benennt Konten und USt-Behandlung je Rechtsträgerart (Gemeinschaft, vermietender Eigentümer, Verwalter); danach Kontenzuordnung hinterlegen. Steuerliche Einordnung nur durch den Steuerberater.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Konten je Rechtsträgerart durch Steuerberater festlegen, dann hinterlegen | gering (Pflege) | gering |
| B Bruttobuchung vorerst beibehalten, G1 ohne Honorarbuchung | keiner | mittel, Honorar bleibt manuell |
| C Einheitliche Kontenvorgabe für alle Buchungskreise | gering | hoch, Vorsteuer je Buchungskreis evtl. falsch |

### T03-01 Aufbewahrungsklasse der Bankrohdaten (Eigentümer Timo Müller mit Steuerberatung)
Ergebnis: Bankrohdaten liegen in Klasse accounting_records (10 Jahre, Entwurf), Pfadschema umgesetzt.
Empfehlung: Profil accounting_records nach Bestätigung durch den Steuerberater freigeben.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Profil wie Entwurf freigeben nach Bestätigung | gering | gering |
| B Abweichende Klasse benennen lassen | gering | gering |
| C Ohne Freigabe weiterlaufen | keiner | mittel, G1 bleibt blockiert |

### M11-09-01 Immoware24-Umsatzexport (Eigentümer Timo Müller)
Betreiberhinweis 01.10.2026 (B27): Immoware24 ist nur einmalige Datengrundlage, das CRM führt die Buchhaltung später allein. Damit ist Alternative A bestätigt, eine Rücknahme von Bankimporten über Immoware24 entfällt.
Ergebnis: Import mit Vorschau und generischem Mapping; Spaltennamen, Dezimal- und Datumsformat sind mangels Beispieldatei nicht belegt. Bankdatei-Importe haben keine Rücknahme über den Import-Undo.
Empfehlung: Eine echte Exportdatei bereitstellen; Rücknahme von Bankimporten vorerst nicht bauen, da Buchungen ohnehin nur per Storno korrigiert werden.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Beispieldatei liefern, festes Mapping ableiten, keine Rücknahme | gering | gering |
| B Generisches Mapping mit Vorschau dauerhaft nutzen | keiner | mittel, Fehlzuordnung je Import |
| C Zusätzlich Rücknahme für Bankimporte entwickeln | mittel | mittel, Abgrenzung zu gebuchten Daten |

### T10-01 Immoware24-Berichte ohne belegte Spalten (Eigentümer Timo Müller)
Ergebnis: Sechs Berichtsarten (Kaution, Umlageschlüssel, Zähler, Energieausweis, Dienstleister, Portalnutzer) arbeiten mit frei zuordenbaren Spalten.
Empfehlung: Echte Exportkopfzeilen und Wertzuordnungen liefern; Portalnutzer aus dem Altsystem nicht automatisch einladen, sondern je Objekt entscheiden.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Exportdateien liefern, Zuordnungen festlegen, keine Masseneinladung | gering | gering |
| B Freie Zuordnung je Import beibehalten | keiner | mittel |
| C Portalnutzer aus Altsystem gesammelt einladen | gering | mittel, Datenschutz und Kontaktqualität |

### U11-01 Löschsperren für Steuerverfahren und Rechtssachen (Eigentümer Betreiber und Steuerberater)
Ergebnis: Automatische Sperre bei Prozess oder Insolvenz aus der Mahnsperre, Vier-Augen-Aufhebung und Startregel Beschluss (Annahme A-V03-01) sind umgesetzt. Fristwerte der Profile bleiben Entwurf.
Empfehlung: Fristwerte durch den Steuerberater bestätigen lassen; Datenmodell für Steuerverfahren und Rechtssachen in einem Folgepaket documents umsetzen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Fristwerte bestätigen, Folgepaket documents planen | mittel | gering |
| B Sperren außerhalb der Buchhaltung manuell setzen | gering | mittel, Sperre kann vergessen werden |
| C Nur Fristwerte freigeben, kein Folgepaket | gering | mittel |

### U15-02 Objektgleichheit der Rechnungsprüfung (Eigentümer Timo Müller)
Ergebnis: In Welle 7 (V01) umgesetzt.
Empfehlung: Als erledigt bestätigen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Bestätigen | keiner | gering |
| B Zusätzlich Warnung statt Ablehnung | gering | gering |
| C Rücknahme der Prüfung | gering | mittel, Befunde gegen fremde Daten |

## G2 Zahlungsauslösung

### S16-03-02 Ablage von EBICS-Schlüsseln (Eigentümer Timo Müller)
Ergebnis: EBICS ist nicht implementiert, es gibt keine gespeicherten Schlüssel. Bei Umsetzung sind verschlüsselte Ablage und erfasste Rotation Pflicht. Die Bibliothek fintech ist lizenzpflichtig (V2).
Empfehlung: Bis zur EBICS-Entscheidung beim Datei-Upload bleiben; EBICS erst nach Bankliste und Bankverträgen beauftragen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Datei-Upload beibehalten, EBICS nach Bankverträgen | keiner | gering, manuelle Einreichung |
| B EBICS mit lizenzierter Bibliothek umsetzen | hoch | mittel, Schlüsselverwaltung |
| C Zahlungsauslösung über den Aggregator prüfen | mittel | mittel, Vertrag offen |

## G3 Mietabrechnung

### S69-01-01 Freigabestufe der Eigentümerabrechnung (Eigentümer Timo Müller)
Ergebnis: Eigentümerabrechnung (Miete, SEV) hinter G3, Rücklagenabrechnung hinter G4. Offen ist, welche Buchung die Abrechnung als gebucht abschließt.
Empfehlung: G3 für Miete und SEV beibehalten; Abschluss durch die Auszahlungsbuchung festlegen, sobald G2 vorliegt.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A G3 für Miete und SEV, Abschluss durch Auszahlung | gering | gering |
| B SEV zusätzlich hinter G4 | gering | gering, spätere Freigabe |
| C Abschluss durch Honorarbuchung | gering | mittel, Auszahlung nicht abgebildet |

### M17-09-01 Heizkostenimport und CO2-Vermieteranteil (Eigentümer Timo Müller, Messdienst)
Ergebnis: Annahme A-M17-09-01 (Beträge einschließlich CO2-Anteil, Abzug bei Übernahme), Toleranz ein Cent je Nutzer.
Empfehlung: Annahme beibehalten, Ausweis bei den eingesetzten Messdiensten schriftlich bestätigen lassen und Musterdateien anfordern. Die Aufteilung des CO2-Anteils ist rechtlich zu prüfen (Rechtsanwalt).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Annahme beibehalten, Messdienste bestätigen, Formate nach Mustern | gering | gering |
| B Nur ARGE HeiWaKo D-Format fest unterstützen | mittel | gering |
| C Beträge ohne Prüfung übernehmen | keiner | hoch, doppelter oder fehlender Abzug |

### R10-01 Verzinsung von Kautionen (Eigentümer Betreiber, Rechtsanwalt)
Ergebnis: Das Modul rechnet nur mit eingegebenen Sätzen, ohne hinterlegte Rechtsgrundlage.
Empfehlung: Verzinsungspflicht je Anlageform, Zinseszins und Ausweis vom Rechtsanwalt klären lassen; bis dahin nur Entwurfsberechnung.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Rechtliche Klärung, danach Regel hinterlegen | gering | gering |
| B Eingegebene Sätze als Entwurf weiterführen | keiner | mittel, keine Abnahme B15 |
| C Einheitlichen Satz für alle Anlageformen | gering | hoch, rechtlich ungeprüft |

### R09-01 Schalter der automatischen KI-Läufe (Eigentümer Timo Müller)
Ergebnis: Schalter liegen im JSON der Mandanteneinstellungen, Standard aus.
Empfehlung: Standard aus bestätigen (Kosten, Datenschutz); eigene Spalten erst, wenn die Schalter dauerhaft bleiben.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Standard aus bestätigen, JSON beibehalten | keiner | gering |
| B Eigene Spalten per Migration | gering | gering |
| C Standard an | keiner | mittel, Kosten und Datenschutz |

### U12-01 Qualität der Schwärzung (Eigentümer Betreiber), zusammen mit R02-01
Ergebnis: Schwärzung erfolgt außerhalb des Systems; das CRM verwaltet Upload, Vier Augen, Verknüpfung und Sichtbarkeit, nicht die Qualität.
Empfehlung: Prüfverfahren festlegen (zweite Person prüft die geschwärzte Kopie gegen Checkliste), Schwärzung nicht im System bauen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Schriftliches Prüfverfahren außerhalb des Systems | gering | gering |
| B Schwärzung im System mit Nachweis der Unwiderruflichkeit | hoch | mittel |
| C Ohne Prüfverfahren | keiner | hoch, Datenschutz |

## G4 WEG-Abrechnung

### R05-01 Standardfrist der Einsichtspakete (Eigentümer Timo Müller, Rechtsanwalt)
Ergebnis: Einstellbar, Standard ohne Ablauf.
Empfehlung: 14 Tage (Vorschlag P08-02) erst nach Rechtsprüfung setzen, einschließlich Umgang mit historischen Ansprüchen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Nach Rechtsprüfung 14 Tage setzen | gering | gering |
| B Ohne Ablauf belassen | keiner | gering, Zugriff bleibt offen |
| C Kürzere Frist ohne Prüfung | keiner | mittel |

### T13-02 Beiratsprüfung zu Tagesordnungspunkten (Eigentümer Timo Müller mit Rechtsanwalt)
Ergebnis: Kein Verweis auf eine Beiratsprüfung, keine Sperre der Verkündung.
Empfehlung: Bedarf und Gegenstände mit dem Rechtsanwalt festlegen, dann optionaler Verweis als Hinweis ohne Sperre.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Optionaler Hinweis nach Klärung | gering | gering |
| B Keine Verknüpfung | keiner | gering |
| C Sperre der Verkündung ohne Prüfung | mittel | hoch, rechtlich nicht belegt |

### T13-03 Statusname retrieved bei Abrechnungsabruf (Eigentümer Timo Müller, Rechtsanwalt)
Ergebnis: retrieved entsteht beim Abruf durch ein Konto mit hoa:update; keine Anerkennung.
Empfehlung: Wortlaut als reinen Abrufvermerk vom Rechtsanwalt bestätigen lassen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Wortlaut bestätigen | keiner | gering |
| B Andere Bezeichnung wählen | gering | gering |
| C Status entfernen | gering | mittel, Nachweis des Abrufs fehlt |

### V05-01 Frist für das Versammlungsprotokoll (Eigentümer Timo Müller mit Rechtsanwalt), Folge von R07-01
Ergebnis: Protokollabschluss umgesetzt (V05), nur Hinweistext ohne Frist.
Empfehlung: Frist aus Gesetz, Gemeinschaftsordnung oder Verwaltervertrag rechtlich klären lassen und als Wiedervorlage ohne Sperre hinterlegen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Nach Klärung Wiedervorlage je Objekt | gering | gering |
| B Nur Hinweistext | keiner | mittel, Frist kann versäumt werden |
| C Feste Sperre | mittel | mittel, rechtlich nicht belegt |

### U07-01 und V10-01 Vorbelegung des Kontenrahmens (Eigentümer Fachbereich WEG mit Steuerberatung)
Ergebnis: Nur eindeutige Konten vorbelegt. Offen sind Mehrschlüsselverteilungen, 041805 Rauchwarnmelder, Bankkonten 001200 und 001201, Konten ohne BetrKV-Bezug und die Art Hausgeld oder Rücklage.
Empfehlung: Fachbereich WEG legt je Konto Art und Standardschlüssel fest; Mehrschlüsselverteilungen bleiben Objektentscheidung.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Liste je Konto durch Fachbereich, Mehrschlüssel je Objekt | mittel | gering |
| B Keine Vorbelegung, Pflege je Objekt | hoch (laufend) | mittel |
| C Pauschale Vorbelegung | gering | hoch, falsche Verteilung |

### V01-01 Sperre der Anfangsbestände einer Rücklage (Eigentümer Timo Müller), Folge von U15-03
Ergebnis: Sperre nach berechneter oder freigegebener Abrechnung, Korrektur nur per neuer Bewegung (Produktschutz).
Empfehlung: Sperre bestätigen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Sperre bestätigen | keiner | gering |
| B Protokollierte Änderung zulassen | gering | mittel, rückwirkende Abweichung |
| C Änderung mit Vier Augen | mittel | gering |

## G5 Fremdmandanten

### T01-01 und V04-01 Mandantenexport (Eigentümer Timo Müller mit Datenschutz)
Ergebnis: Unverschlüsseltes ZIP im Objektspeicher; Aufbewahrung je Mandant einstellbar, Standard ohne automatische Löschung.
Empfehlung: Mit dem Datenschutz eine kurze Standardaufbewahrung festlegen und Verschlüsselung vor Herausgabe an Dritte vorsehen; Rechtsgrundlage der Herausgabe prüfen lassen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Systemstandard mit Löschung, Verschlüsselung vor Herausgabe | mittel | gering |
| B Nur Mandantenvorgabe, keine Verschlüsselung | keiner | mittel |
| C Unverändert ohne Löschung | keiner | hoch, personenbezogene Daten liegen dauerhaft |

### R10-03 und R10-04 Branding und Rechtstexte im Portal (Eigentümer Betreiber)
Ergebnis: Farben, Logo, Name, Impressum und Datenschutz je Mandant; Manifest neutral. Pflege der Rechtstexte liegt beim Mandanten.
Empfehlung: Für HVM und Timo Müller abnehmen; für Fremdmandanten erst mit G5 entscheiden.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Abnahme für eigene Mandanten, Fremdmandanten mit G5 | keiner | gering |
| B Manifest je Mandant dynamisch | gering | gering |
| C Logo für Fremdmandanten jetzt freigeben | keiner | mittel, G5 nicht freigegeben |

### T13-01 Erneute Portaleinladung (Eigentümer Betreiber)
Ergebnis: In U12 umgesetzt (neues Token, Ablauf zurückgesetzt).
Empfehlung: Fachlich bestätigen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Bestätigen | keiner | gering |
| B Nur durch Administratoren | gering | gering |
| C Zurücknehmen | gering | gering, manueller Aufwand |

## Ohne Gate: Datenschutz und Sicherheit

### U15-04 Inhalt der Benachrichtigungsmails (Eigentümer Timo Müller, Datenschutz)
Ergebnis: Titel und Text gehen im Klartext an aktive Mitglieder.
Empfehlung: Nur Hinweis mit Link versenden.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Hinweis mit Link | gering | gering |
| B Gekürzter Inhalt | gering | mittel |
| C Unverändert | keiner | mittel, personenbezogene Daten per Mail |

### M9-02-01 Tracing-Backend (Eigentümer Betreiber)
Ergebnis: Tracing technisch fertig, Schalter aus.
Empfehlung: Schalter aus lassen, bis Backend und Datenschutz (Statementtexte, AVV) entschieden sind.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Aus lassen bis Entscheidung | keiner | gering |
| B Selbst betriebenes Backend ohne Statementtexte | mittel | gering |
| C Externes Backend mit Statementtexten | gering | hoch, Datenschutz |

### U04-01 Passkeys (Eigentümer Timo Müller)
Ergebnis: Umgesetzt hinter Schalter, Standard aus; Protokollprüfung im eigenen Code.
Empfehlung: Sicherheitsprüfung beauftragen oder auf geprüfte Bibliothek wechseln (P14-02), RP ID und Origins festlegen, Test mit echten Geräten.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Prüfung beauftragen, dann je Umgebung freischalten | mittel | gering |
| B Wechsel auf geprüfte Bibliothek | mittel | gering |
| C Ohne Prüfung freischalten | keiner | hoch, Anmeldesicherheit |

### U04-02 Portal nur zweiter Faktor (Eigentümer Timo Müller)
Ergebnis: In V02 serverseitig umgesetzt (Kennzeichen V02-01).
Empfehlung: Kennzeichen fachlich bestätigen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Bestätigen | keiner | gering |
| B Anderes Kennzeichen festlegen | gering | gering |
| C Nur im BFF sperren | keiner | mittel, Umgehung über API |

### R10-02 Zweiter Faktor im Portal (Eigentümer Betreiber)
Ergebnis: Option required für Anmeldung per Link; erzwungene TOTP bei Passwortanmeldung fehlt, widerspräche M2-01 (freiwillig).
Empfehlung: Bei freiwilliger TOTP (M2-01) bleiben.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Freiwillig belassen | keiner | gering |
| B Je Mandant erzwingbar | gering | gering |
| C Generell erzwingen | gering | mittel, Supportaufwand |

### S16-03-01 Altzeilen der Selbstauskunft-Token (Eigentümer Timo Müller)
Ergebnis: Umstellungsjob in V02 umgesetzt, einmalige Auslösung nach Deployment.
Empfehlung: Job nach dem nächsten Deployment auslösen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Job auslösen | gering | gering |
| B Altzeilen auslaufen lassen | keiner | mittel |
| C Altlinks ungültig machen | gering | gering, erneuter Versand |

### R02-01 Schwärzung im System
Siehe U12-01. Empfehlung: außerhalb des Systems belassen.

### R02-02 Direkter Browser-Upload (Eigentümer Timo Müller)
Ergebnis: Je Mandant aus, bis Objektspeicher mit CORS für PUT festgelegt und geprüft ist.
Empfehlung: Aus lassen bis zur Betriebsprüfung (Runbook Objektspeicher, Abschnitt 9).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Aus bis zur Prüfung | keiner | gering |
| B Endpunkt jetzt einrichten und prüfen | mittel | gering |
| C Ohne Prüfung einschalten | keiner | mittel |

## Ohne Gate: Fachliche Abläufe

### R02-03 Hub-Mandant des gemeinsamen Postfachs (Eigentümer Timo Müller)
Ergebnis: Verteilung nach Token setzt einen Hub-Mandanten voraus.
Empfehlung: Festlegen, welcher Mandant Hub ist; Absenderlisten je Mandant im Betrieb prüfen. Die Quellen enthalten keinen Vorschlag.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Hub festlegen, Absenderlisten prüfen | gering | gering |
| B Getrennte Postfächer je Mandant | gering | gering |
| C Verteilung aus | keiner | mittel, manuelle Zuordnung |

### R03-01 Übernahmestand im Eigentümerportal (Eigentümer Timo Müller)
Ergebnis: Portal zeigt Bezeichnung, Status, Fälligkeit, ohne Notizen.
Empfehlung: Mandantenschalter, Standard aus.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Schalter, Standard aus | gering | gering |
| B Immer anzeigen | keiner | gering |
| C Nicht anzeigen | gering | gering |

### R03-02 und V06-01 Onboarding Konten und Tickets (Eigentümer Timo Müller)
Ergebnis: Rechtsträger je Konto wählbar (V06). Offen: Standardteam, Zuständiger, Sammelkonto je Eigentümer bei Mietobjekten mit mehreren Eigentümern.
Empfehlung: Standardteam und Zuständigen benennen; Konten je Eigentümer, da Gelder dem richtigen Rechtsträger zuzuordnen sind (CLAUDE.md Abschnitt 8).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Team benennen, Konto je Eigentümer | gering | gering |
| B Ein Sammelkonto je Objekt | gering | hoch, Rechtsträgertrennung |
| C Manuell je Fall | keiner | mittel |

### R08-01 und T14-01 Objektzuordnung eingeschränkter Mitglieder (Eigentümer Betreiber)
Ergebnis: Objektzuordnung wirkt in fast allen Bereichen; Restpfade (Importe ohne Zielobjekt, Abgleichberichte, Vollmachten, Kontakte) mandantenweit.
Empfehlung: Restpfade mandantenweit lassen, Importe ohne Ziel über Rollenrecht steuern, Kontakte vorerst mandantenweit (Vorschlag der Quellen).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Vorschlag der Quellen übernehmen | gering | gering |
| B Kontakte objektbezogen filtern | mittel | gering |
| C Importe für eingeschränkte Mitglieder sperren | gering | gering |

### T05-01 Sachliche Rechnungsprüfung (Eigentümer Timo Müller)
Ergebnis: Toleranz 0 %, Budgetabgleich brutto, Mengenabgleich gegen Auftrag fehlt (kein Positionsmodell im Ticketmodul).
Empfehlung: Standard 0 und brutto beibehalten; Positionsmodell nur bei Bedarf beauftragen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Standard beibehalten | keiner | gering |
| B Toleranz je Mandant setzen | gering | gering |
| C Positionsmodell im Ticketmodul | hoch | gering |

### T03-02 finAPI-Zustimmungsablauf (Eigentümer Timo Müller)
Ergebnis: Feldname in der finAPI-Antwort unbestätigt; täglicher Abgleich ohne Nutzeraktion hängt daran.
Empfehlung: Feldname und Version aus finAPI-Doku und Vertrag (M11-41) liefern.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Feldname liefern | gering | gering |
| B Abgleich nur mit Nutzeraktion | keiner | gering |
| C Feldname annehmen | keiner | mittel, Abbruch des Abgleichs |

### T12-01 Stilfelder des Postfachs (Eigentümer Betreiber)
Ergebnis: Tonfall und Freitextregeln; R09-02 mit Migration 0296 erledigt.
Empfehlung: Anrede und Grußformel je Gesellschaft als Felder ergänzen, da die Gesellschaften getrennt zeichnen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Felder Anrede und Grußformel | gering | gering |
| B Freitextregeln genügen | keiner | gering |
| C Vorlagen je Gesellschaft | mittel | gering |

### R09-03 Historienanalyse (Eigentümer Timo Müller)
Ergebnis: Ohne fachliche Definition im Masterprompt 9.3, nicht angeschlossen.
Empfehlung: Nicht umsetzen, bis eine fachliche Definition vorliegt.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Zurückstellen | keiner | gering |
| B Definition schreiben, dann umsetzen | mittel | gering |
| C Ohne Definition anschließen | mittel | mittel, Kosten ohne Nutzen |

### T08 Benachrichtigungen ohne Standardpostfach (Eigentümer Timo Müller)
Ergebnis: Das Verhalten des Mailversands ohne Standardpostfach (Paket T08) ist fachlich nicht bestätigt.
Empfehlung: Standardpostfach je Mandant verpflichtend einrichten statt Ersatzweg.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Standardpostfach einrichten | gering | gering |
| B Ersatzweg (Systemabsender) | mittel | gering |
| C Unverändert | keiner | mittel, Benachrichtigungen fehlen |

### U08-01 Leistungsmessung (Eigentümer Betreiber)
Ergebnis: Sollstellungslauf 1.000 Verträge 48,3 s, Abrechnungsausgabe 1,7 s unter Last; Staging-Messung offen.
Empfehlung: Messung auf Staging mit produktionsnaher Datenmenge vor G1 durchführen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Staging-Messung vor G1 | gering | gering |
| B Werte als ausreichend annehmen | keiner | mittel |
| C Messung erst im Betrieb | keiner | mittel |

### R09-02, R07-01, U15-01 Bereits technisch erledigt
R09-02 (Migration 0296), R07-01 (Protokollabschluss V05) und U15-01 (Prüfsumme V01) sind umgesetzt. Empfehlung: als erledigt bestätigen; offene Restfrage zu R07-01 siehe V05-01.

## Sonstige Entscheidungen ohne Gate-Bezug

### V06-02 Sammelkonto bei Mietobjekten mit mehreren Eigentümern (Eigentümer Timo Müller)
Ergebnis: Standard-Zuständiger und -Team der Übernahme-Tickets sind Mandanteneinstellung (leer = ohne Zuweisung) in Welle 9 (X02) umgesetzt. Offen ist nur, ob bei Mietobjekten mit mehreren Eigentümern ein Sammelkonto je Eigentümer angelegt werden soll.
Empfehlung: Vorerst ohne Sammelkonto, da die Entscheidung fachlich offen ist; bei Bedarf in einem Folgepaket umsetzen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Keine Sammelkonten, Entscheidung später | keiner | gering |
| B Sammelkonto je Eigentümer standardmäßig anlegen | mittel | mittel, ggf. nicht genutzt |
| C Sammelkonto optional über Mandanteneinstellung | mittel | gering |

### W01-01 WebAuthn-Sicherheitsprüfung und Freischaltung (Eigentümer Timo Müller)
Ergebnis: Sicherheitsprüfung vom 01.10.2026 abgeschlossen (`docs/reviews/WEBAUTHN-2026-10-01.md`), sieben Befunde behoben und mit Negativtests belegt (Welle 8, W01). Mengenbegrenzung für Passkey-Optionen je Client-Adresse (60) und je Benutzer (20) pro 300 Sekunden (429 MHVP-CORE-0006, Welle 9, X01).
Empfehlung: Unabhängige Zweitprüfung durch externe Sicherheit durchführen oder auf eine geprüfte Bibliothek wechseln (P14-02), danach Tests mit echten Geräten (iOS, Android, Windows Hello, Sicherheitsschlüssel) und RP ID Konfiguration je Umgebung vor Aktivierung des Schalters MHVP_WEBAUTHN_ENABLED.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Externe Sicherheitsprüfung, dann Freischaltung | mittel | gering |
| B Wechsel auf externe geprüfte Bibliothek | hoch | gering |
| C Freischaltung nach internen Tests | gering | mittel, Restrisiko |

### W04-01 Trigramm-Indizes der Portal-Belegsuche unter Row Level Security (Eigentümer Betreiber)
Ergebnis: Portal-Belegsuche mit LIKE und Trigramm-Indizes implementiert (Welle 8, W04). Die Indizes werden unter RLS nicht automatisch genutzt, da lower() und LIKE unter RLS nicht leakproof sind. Index-Nutzung per EXPLAIN in den Leistungsmessungen dokumentiert.
Empfehlung: Leistung bei produktionsnaher Datenmenge auf Staging prüfen; ggf. separate nicht-RLS-Indizes (mit Datenschutzvorkehrung) in einem Folgepaket planen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Staging-Messung vor Go-live, ggf. Folgepaket für optimierte Indizes | gering | gering |
| B Suche ohne Indizes im jetzigen Zustand akzeptieren | keiner | mittel, Antwortzeit bei großer Datenmenge |
| C Separate nicht-RLS-Indizes sofort umsetzen | mittel | mittel, Datenschutzprüfung erforderlich |
