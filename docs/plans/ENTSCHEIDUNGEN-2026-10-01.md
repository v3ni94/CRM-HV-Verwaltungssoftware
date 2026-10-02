# Entscheidungsliste für den Vorstand, Stand 01.10.2026

Adressat: Timo Müller (Betreiber). Quelle: `docs/OPEN_QUESTIONS.md`, Punkte der Wellen 4 bis 7 (R, T, U, V) sowie S69-01-01, S16-03-02, M17-09-01, M11-09-01; ergänzend T08, S16-03-01 und M9-02-01 aus Welle 5. Neu ab Stand 1.58.0: 38 Fragen AA01-01 bis AB12-01 aus der zweiten Lückenanalyse (Wellen 12 und 13), eingearbeitet in den Abschnitten ab "Zweite Lückenanalyse" am Ende dieser Liste. Testnachweise je Paket: `docs/acceptance/PROTOKOLL-2026-10-01-WELLEN-4-7.md`; Wellen 11 bis 13: `docs/plans/BERICHT-2026-10-01-WELLEN-11-13.md`.

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
5. Gate-Zuschnitt klären (Wellen 12 und 13): AA01-01 (Einstufung der Routen ohne Gate), AA02-01 und AA02-02 (Checklisten, Granularität) in einem Termin; sie bestimmen, wie G1 bis G4 später geöffnet werden.
6. Steuerberater bündeln: AA12-01 (§ 13b UStG), AA17-01 (Rechnungsnummer), AA11-02 (§ 35a EStG), AA10-03 und AA10-01 (Regeln für Automatik) sowie die Fristenpunkte AA12-02, AA12-03 und AB10-01 mit der Rechtsprüfung.
7. Rechtsanwalt bündeln (G4 und G5): AA07-01, AA07-02, AA06-01, AA06-02, AA11-01, AA11-03, AA14-03.
8. Bestätigungen ohne Mehraufwand aus Welle 13: AB12-01 (kein Gate für Dienstleister-Freigaben), AA16-02 (Hub-Parser), AA03-01 (beide Ereignistypen), AA14-02 (Bewertungen intern).

Zusammenfassung: Die Liste umfasst nun 38 weitere Fragen. Verteilung nach Gate: G1 sechs (AA12-01, AA10-01, AA10-03, AA02-03, AA11-03, AA17-01), gateübergreifend drei, G2 eine, G3 sieben, G4 vier, G5 vier, ohne Gate dreizehn. Die zweite Lückenanalyse zählt 80 Befunde: 52 erledigt, 18 teilweise, 10 offen (docs/plans/LUECKENLISTE-2026-10-01.md). Alle Fragen sind Betreiber- oder Rechtsentscheidungen, technisch ist jeweils der sichere Zustand (Schalter aus, Gate geschlossen) umgesetzt.

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
Vermerk: technisch vorbereitet (Welle 16, AE37): Kopfzeilenerkennung, Spaltenvorschlag, gespeicherte Zuordnung je Mandant und Berichtstyp und Prüfbericht vor dem Speichern, ohne ein Exportformat anzunehmen. Die Anforderungsliste docs/integrations/immoware24-exporte.md führt je Berichtsart die benötigten Angaben, echte Exportdateien und Wertzuordnungen liefert der Betreiber (AE37-01).

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
Vermerk: technisch vorbereitet (Welle 16, AE23): EBICS-Grundgerüst hinter einem Mandantenschalter (Standard aus), private Schlüssel nur verschlüsselt mit protokollierter Rotation, Signaturschlüssel standardmäßig extern, Variante server vorbereitet. Es gibt keine echte EBICS-Übertragung, die Entscheidung zum serverseitigen Signaturschlüssel bleibt offen (AE23-05).

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
Vermerk: technisch vorbereitet (Welle 16, AE02): Mehrschlüsselverteilung je Vorlagenkonto pflegbar und geprüft, Abrechnungsart Heizkosten als Vorschlag mit Kennzeichen Freigabe offen, Prüfbericht zu Konten ohne Zuordnung. Die Festlegung je Konto bleibt beim Fachbereich WEG.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Liste je Konto durch Fachbereich, Mehrschlüssel je Objekt | mittel | gering |
| B Keine Vorbelegung, Pflege je Objekt | hoch (laufend) | mittel |
| C Pauschale Vorbelegung | gering | hoch, falsche Verteilung |

### V01-01 Sperre der Anfangsbestände einer Rücklage (Eigentümer Timo Müller), Folge von U15-03
Ergebnis: Sperre nach berechneter oder freigegebener Abrechnung, Korrektur nur per neuer Bewegung (Produktschutz).
Empfehlung: Sperre bestätigen.
Vermerk: technisch vorbereitet (Welle 16, AE07): Mandantenschalter opening_lock_mode mit den Varianten gesperrt (Standard), protokolliert und Vier Augen mit Änderungsprotokoll. Die Entscheidung bleibt offen, der Standard bleibt gesperrt.

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
Vermerk: technisch vorbereitet (Welle 16, AE29): Rechtstexte (Impressum, Datenschutz, Nutzungsbedingungen) je Mandant als Textbausteine mit Freigabe durch eine zweite Person, Anzeige im Portal-Footer. Logo und Texte für Fremdmandanten bleiben Entscheidung mit G5 (AE29-01).

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
Vermerk: technisch vorbereitet (Welle 16, AE27): Die Pflicht eines zweiten Faktors ist als Mandantenrichtlinie vorbereitet (Standard freiwillig gemäß M2-01, für Portalzugänge ein eigener Schalter, Standard aus). Die Entscheidung bleibt offen (AE27-01).

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

# Zweite Lückenanalyse, Wellen 12 und 13 (Fragen AA01-01 bis AB12-01)

Quelle: `docs/OPEN_QUESTIONS.md`, Zeilen AA01-01 bis AB12-01, Stand 01.10.2026. Die Empfehlungen sind kaufmännische Einschätzungen. Rechtsfragen sind mit Rechtsanwalt, steuerliche Fragen mit dem Steuerberater abzustimmen. Keine Entscheidung öffnet ein Gate.

## G1 Produktive Buchhaltung (Fortsetzung, zweite Lückenanalyse)

### AA12-01 Umsatzsteuer nach § 13b UStG, Fallkatalog und Freigaberolle (Eigentümer Timo Müller mit Steuerberater)
Frage: Welche Fälle sind einschlägig, wer gibt frei (zweite Person oder Steuerberater) und welche Quelle gilt für die Normzuordnung?
Gate: G1.
Ergebnis (technischer Stand): Kennzeichen Reverse Charge am Beleg, Prüfbefund und Steuerwarnung sind vorhanden, die Eingangsrechnung zeigt den Freigabepunkt. Keine Automatik, keine Buchungsfolge, keine verbindliche Sperre.
Empfehlung: Steuerberater legt den Fallkatalog und die Freigaberolle schriftlich fest. Erst danach eine verbindliche Sperre vor Freigabe ergänzen. Die steuerliche Einordnung trifft allein der Steuerberater.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Fallkatalog durch Steuerberater, dann Sperre vor Freigabe | gering | gering |
| B Bei Hinweis und Warnung bleiben, Prüfung manuell | keiner | mittel, Fehlbuchung möglich |
| C Pauschale Sperre aller Reverse-Charge-Belege | gering | mittel, Rückstau bei der Freigabe |

### AA10-01 Automatische Buchung des Rechnungsplans (Planflag oder Bankregel) (Eigentümer Timo Müller)
Frage: Genügt ein Kennzeichen am Plan den Anforderungen aus 6.9.4 und 7.4, oder muss die Automatik an eine aktive, freigegebene Bankregel gebunden werden?
Gate: G1.
Ergebnis (technischer Stand): Das Kennzeichen auto_post (Standard aus) ist nur mit freigeschaltetem Mandantenschalter setzbar. Die Plangenerierung erzeugt weiter nur Entwürfe, es wird nichts automatisch gebucht.
Empfehlung: Automatik an eine freigegebene Regel mit Vier-Augen-Freigabe und Betragsgrenze binden. Das entspricht dem Grundsatz, dass KI und Automatik nur über deterministisch prüfbare Regeln wirken. Das Planflag allein reicht aus kaufmännischer Sicht nicht.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Bindung an freigegebene Regel mit Betragsgrenze | mittel | gering |
| B Planflag genügt, Mandantenschalter als Schutz | keiner | mittel, Abweichung von 7.4 |
| C Automatik dauerhaft aus, nur Entwürfe | keiner | gering, Handarbeit bleibt |

### AA10-03 Standard-Bankregel je Dienstleister (Eigentümer Timo Müller)
Frage: Sind Standardpriorität 900 und Regelart creditor_payment ohne Betragsgrenze fachlich gewollt?
Gate: G1.
Ergebnis (technischer Stand): Die Standardregel entsteht nur als Vorschlag (Zustand proposed) und bucht nichts. Aktivierung ist nach Vier-Augen mit Betragsgrenze und Testnachweis hinter G1 vorgesehen.
Empfehlung: Priorität 900 bestätigen, aber die Aktivierung nur mit Betragsgrenze zulassen. Eine Regel ohne Betragsgrenze sollte nicht aktivierbar sein.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Priorität 900 bestätigen, Betragsgrenze verpflichtend | gering | gering |
| B Priorität und Regelart je Mandant konfigurierbar | mittel | gering |
| C Keine Standardregel, nur manuelle Regeln | keiner | gering, Mehraufwand in der Pflege |

### AA02-03 XRechnung-Validator im CI (Lizenz, Version, Prüfsummen) (Eigentümer Timo Müller)
Frage: Welche Version, Lizenz und Prüfsummen gelten für den KoSIT-Validator und die XRechnung-Konfiguration?
Gate: G1.
Ergebnis (technischer Stand): Der optionale CI-Job xrechnung-kosit läuft nur mit der Repository-Variable MHVP_KOSIT_ENABLED und gepinnten Download-URLs samt SHA-256. Ohne Festlegung bleibt er aus, XSD und Schematron liegen nicht im Repository.
Empfehlung: Version und Lizenz vor Aktivierung prüfen, Prüfsummen eintragen und den Job einschalten. Für G1 ist ein belegter Validierungsnachweis der Generatorrechnungen sinnvoll.
Vermerk: technisch vorbereitet (Welle 16, AE26): scripts/kosit.lock mit URLs und SHA-256 im Repository, make kosit-fetch, kosit-test und kosit-validate, der CI-Job xrechnung-kosit läuft ohne Repository-Variablen und ist mit MHVP_KOSIT_ENABLED=false abschaltbar. Version, Lizenz und Herkunft der Prüfsummen bleiben zu bestätigen (AE26-01).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Validator festlegen, pinnen und aktivieren | gering | gering |
| B Validierung nur manuell vor Versand | keiner | mittel |
| C Eigene XSD-Prüfung im Repository ablegen | mittel | mittel, Pflege der Schemata |

### AA11-03 WEG-Eigentümerwechsel in der Sollstellung (Eigentümer Timo Müller mit Rechtsanwalt)
Frage: Welcher Stichtag gilt für den Besitzübergang (Grundbuch oder Vereinbarung) und wie wird der Monat des Wechsels in der Sollstellung behandelt?
Gate: G1.
Ergebnis (technischer Stand): Eigentumsverträge mit Beginn, Ende oder Betragswechsel im Monat bleiben auch bei freigegebener Zeitanteilsregel manuelle Posten (Regel M13-01 korrigiert). Eine eigene WEG-Berechnung fehlt.
Empfehlung: Regel mit dem Rechtsanwalt festlegen und die Quelle aus Anhang C benennen. Bis dahin manuelle Posten beibehalten, das ist sicher und für die Fallzahl vertretbar.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Regel durch Rechtsanwalt, dann eigene WEG-Berechnung | mittel | gering |
| B Manuelle Posten dauerhaft beibehalten | keiner | gering, Aufwand je Wechsel |
| C Zeitanteilsregel auch für WEG nutzen | gering | hoch, ohne Rechtsgrundlage |

### AA17-01 Rechnungsnummernkreis je Mandant (Eigentümer Timo Müller mit Steuerberater)
Frage: Darf der Rechnungsnummernkreis je Mandant konfiguriert werden (Präfix, Stellenzahl, Jahresbezug) und welches Format erfüllt die Anforderung an die fortlaufende Rechnungsnummer?
Gate: G1.
Ergebnis (technischer Stand): Technisch vorbereitet und gesperrt (INVOICE_FORMAT_RELEASED). Das Modul accounting/rent_invoice.py nutzt weiter das feste Format. AB13 hat die Vertragsnummer-Konfiguration getestet, nicht die Rechnungsnummer.
Empfehlung: Steuerberater bestätigt Format und Eindeutigkeit, danach Schalter freigeben und die Rechnungserzeugung auf die Konfiguration umstellen. Bis dahin festes Format.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Format durch Steuerberater bestätigen, dann freigeben | gering | gering |
| B Festes Format dauerhaft behalten | keiner | gering |
| C Freie Konfiguration ohne Prüfung | gering | hoch, Lücken in der Nummernfolge |

## Gate-übergreifend (G1 bis G4)

### AA01-01 Einstufung der schreibenden Routen ohne Gate-Prüfung (Eigentümer Timo Müller)
Frage: Welche der im Test test_ga14_gate_coverage.py als REVIEWED_UNGATED geführten Routen (Buchen und Stornieren von Sätzen, Zahlungsaufträge, Zahlungsläufe als Vorschau, Versand dispatches, SEPA-Mandate) müssen hinter G1, G2, G3 oder G4, welche sind als Entwurf, Testbetrieb oder Stammdatenpflege zulässig?
Gate: G1 bis G4.
Ergebnis (technischer Stand): Das Verhalten ist unverändert. Neue Routen dieser Art lässt der Abdeckungstest nicht ungeprüft zu. AB01 weist die Ablehnung gegateter Routen zur Laufzeit nach.
Empfehlung: Einstufung in einem Termin je Route vornehmen, Maßstab ist die Wirkung: alles, was echte Buchung, Zahlung, Versand oder maßgebliche Abrechnung auslöst, hinter das Gate, reine Entwürfe und Stammdaten ohne Gate mit Begründung im Register. Das schließt die größte verbliebene Lücke im Gate-Konzept.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Einstufung nach Wirkung, danach Gates ergänzen | mittel | gering |
| B Alle Geld- und Versandrouten pauschal hinter Gate | gering | mittel, Entwurfsarbeit wird gesperrt |
| C Bestand unverändert lassen | keiner | mittel, Gates unvollständig |

### AA02-01 Mindestumfang der Gate-Checklisten (Eigentümer Timo Müller)
Frage: Reicht der Mindestumfang der Checkliste aus 18.0, oder sind je Stufe weitere Pflichtpunkte, ein benannter Verantwortlicher und bestimmte Abnahmefälle (D-Fälle, W01 bis W13) technisch zu prüfen?
Gate: G2, G3, G4.
Ergebnis (technischer Stand): Die Genehmigung erzwingt für G2, G3 und G4 die Checkliste (Codes in docs/plans/GATE-CHECKLISTEN.md) und ein Nachweisdokument. Der Inhalt der Nachweise wird nicht fachlich geprüft.
Empfehlung: Mindestumfang um einen benannten Verantwortlichen und die Abnahmefälle je Stufe erweitern. Die Prüfung der Inhalte bleibt bei der Geschäftsführung.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Verantwortlicher und Abnahmefälle als Pflicht | mittel | gering |
| B Mindestumfang genügt | keiner | mittel, Nachweis nur formal |
| C Alle D-Fälle technisch verknüpfen | hoch | mittel, Wartungsaufwand |

### AA02-02 Granularität begrenzter Gate-Freigaben (Eigentümer Timo Müller)
Frage: Gilt die Begrenzung auf Objekt, Rechtsträger oder Funktion, und welche Router sollen den Objektbezug durchreichen?
Gate: G1 bis G4.
Ergebnis (technischer Stand): Freigaben lassen sich begrenzen (Standard alle). AB02 reicht den Objektbezug an Buchungs- und Zahlungsrouten durch (führendes System, Sofortbuchung Ausgleich, Zahlungsdatei). Weitere Routen folgen dem Bedarf, bis dahin öffnet eine unbegrenzte Freigabe die Stufe.
Empfehlung: Granularität Objekt und Rechtsträger festlegen, Funktionscodes nur für den Pilotbetrieb. Das erlaubt einen kontrollierten Pilot mit einem Objekt.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Objekt und Rechtsträger, Funktionen für Pilot | mittel | gering |
| B Nur Mandantenebene | keiner | mittel, kein Pilot mit einem Objekt |
| C Alle drei Ebenen an allen Routen | hoch | mittel |

## G2 Zahlungsauslösung (Fortsetzung)

### AA10-02 Formatversionen pain.001 und pain.008 je Bank (Eigentümer Timo Müller)
Frage: Welche Version verlangt die jeweilige Bank und wann werden die Standards angehoben?
Gate: G2.
Ergebnis (technischer Stand): ADR 0020 pinnt pain.001.001.03 und .09 sowie pain.008.001.02 und .08 nebeneinander, Standard .09 und .02. Bankvorgaben sind nicht eingeholt.
Empfehlung: Bankvorgaben je Konto schriftlich einholen und die Standardversion je Bank setzen, vor G2. Bei Unklarheit die ältere, von der Bank bestätigte Version verwenden.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Bankvorgaben einholen, Version je Bank setzen | gering | gering |
| B Standard .09 und .02 für alle Konten | keiner | mittel, Ablehnung durch Bank möglich |
| C Ältere Versionen als Standard | keiner | mittel, Auslaufrisiko |

## G3 Mietabrechnung (Fortsetzung)

### AA12-02 Prüfpunkte HeizkostenV § 5 und § 12 (Eigentümer Timo Müller, Rechtsprüfung)
Frage: Welche amtlich geprüften Fristen, Wortlaute und Sonderfälle (zum Beispiel Wärmepumpen) gelten je Objekt?
Gate: G3.
Ergebnis (technischer Stand): Die Prüfpunkte sind als Entwurfseinträge im Regelregister angelegt (Endpunkt rule-versions/seed-checkpoints), das Datum ist das Anlegedatum und ohne Rechtsfolge. Siehe auch AB10-01.
Empfehlung: Rechtsprüfung benennt Fristen und Quellen, erst danach Inhalte eintragen. Die Entwurfseinträge nicht als geprüft behandeln.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Inhalte nach amtlicher Prüfung eintragen | gering | gering |
| B Entwurfseinträge unverändert lassen | keiner | mittel, Fristen unbelegt |
| C Eintragungen löschen, Pflege außerhalb | keiner | gering |

### AA12-03 CO2KostAufG §§ 5a bis 5d, Entwurfseinträge (Eigentümer Timo Müller, Rechtsprüfung)
Frage: Welche Verkündungsfassung, welche Anwendungszeitpunkte und welcher Heizungssachverhalt gelten?
Gate: G3.
Ergebnis (technischer Stand): Entwurfseinträge für 2028 und 2029 beruhen auf Platzhalterdaten aus dem Master-Prompt 7.10 H05. Die Berechnung ist unverändert.
Empfehlung: Daten durch Rechtsprüfung verifizieren, dann bestätigen oder zurückziehen. Keine Berechnung nach den Platzhalterdaten.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Verifizieren, dann bestätigen oder zurückziehen | gering | gering |
| B Platzhalter stehen lassen | keiner | mittel |
| C Einträge sofort zurückziehen | keiner | gering |

### AA12-04 Steuerung der Berechnung durch bestätigte Registereinträge (Eigentümer Timo Müller)
Frage: Soll ein bestätigter Registereintrag die Berechnung künftig steuern und wer bestätigt (zweite Person)?
Gate: G3.
Ergebnis (technischer Stand): Der Abrechnungs-Snapshot hält den wirksamen Registereintrag (Regel M17-betrkv-statement) fest, die Berechnung bleibt an die Codetabelle gebunden (AB10).
Empfehlung: Zunächst bei der Codetabelle bleiben. Steuerung über das Register nur mit Bestätigung durch eine zweite Person und Registerseite im CRM, sonst entstehen zwei Quellen der Wahrheit.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Codetabelle führend, Register nur Nachweis | keiner | gering |
| B Register steuert nach Vier-Augen-Bestätigung | mittel | mittel |
| C Register steuert ohne Bestätigung | gering | hoch |

### AA08-01 Wiederöffnung abgeschlossener Abrechnungszeiträume (Eigentümer Timo Müller)
Frage: Darf ein abgeschlossener Zeitraum mit Begründung und Vier-Augen wieder geöffnet werden und gehört die Sperre in die Periodensperre der Buchhaltung (P06-02)?
Gate: G3.
Ergebnis (technischer Stand): Ein abgeschlossener Zeitraum (closed, locked_at) lässt sich nicht zurücksetzen oder löschen.
Empfehlung: Wiederöffnung nur mit Begründung und Vier-Augen zulassen und protokollieren. Die Abstimmung mit der Periodensperre klärt der Steuerberater.
Vermerk: technisch vorbereitet (Welle 16, AE20): Periodensperre je Objekt und Zeitraum mit Mandantenschaltern (Standard aus), Aufhebung nur mit Schalter, Begründung und zweiter Person, die Zeile bleibt erhalten. Die Entscheidung bleibt offen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Wiederöffnung mit Begründung und Vier-Augen | mittel | gering |
| B Keine Wiederöffnung, Korrektur nur neu | keiner | mittel, Sackgasse bei Erfassungsfehlern |
| C Wiederöffnung durch Administrator | gering | hoch |

### AA11-01 Texte des Informationsblatts zur Betriebskostenabrechnung (Eigentümer Timo Müller mit Rechtsanwalt)
Frage: Welche Texte zu Belegeinsicht und Einwendungen werden freigegeben?
Gate: G3.
Ergebnis (technischer Stand): Das Blatt wird aus dem Snapshot erzeugt. Bis zur Freigabe druckt es den Platzhalter "Textbaustein vom Betreiber nicht freigegeben". Die Software formuliert keine Frist oder Rechtsfolge. Ablage am Abrechnungslauf hinter G3.
Empfehlung: Textbausteine durch den Rechtsanwalt prüfen lassen und als Mandanteneinstellung hinterlegen. Vor Freigabe kein Versand des Blatts.
Vermerk: technisch vorbereitet (Welle 16, AE16): Textbausteine für das Informationsblatt mit Freigabe durch eine zweite Person, Ausgabe nur freigegebener Texte, sonst Text nicht freigegeben. Den Wortlaut liefert der Betreiber mit dem Rechtsanwalt.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Texte durch Rechtsanwalt, dann hinterlegen | gering | gering |
| B Blatt ohne Texte nur intern nutzen | keiner | gering |
| C Eigene Texte ohne Prüfung | keiner | hoch |

### AA11-02 § 35a EStG in der Eigentümerabrechnung der Mietverwaltung (Eigentümer Timo Müller mit Steuerberater)
Frage: Ob und wie erfolgt ein Ausweis haushaltsnaher Leistungen für Vermieter, und wie lautet der Mustertext?
Gate: G3.
Ergebnis (technischer Stand): Umgesetzt ist die Übernahme belegter Lohnanteile aus der WEG-Einzelabrechnung für SEV-Eigentümer als Information (M24-05). Für die Mietverwaltung gibt es keine freigegebene Quelle. Der Hinweistext ist als "Text nicht freigegeben" gekennzeichnet.
Empfehlung: Steuerberater entscheidet, ob ein Ausweis für Vermieter erfolgt, und liefert den Mustertext. Bis dahin keine Ausweisung.
Vermerk: technisch vorbereitet (Welle 16, AE16): Textbausteine für Anschreiben-Hinweis und Erläuterung des Nachweises nach § 35a EStG mit Freigabe durch eine zweite Person, Ausgabe nur freigegebener Texte. Entscheidung und Mustertext liefert der Steuerberater, der Baustein im Mieteranschreiben ist noch nicht eingebunden.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Entscheidung und Mustertext durch Steuerberater | gering | gering |
| B Kein Ausweis für Mietverwaltung | keiner | gering |
| C Ausweis ohne Quelle | gering | hoch |

### AB10-01 Befüllung der Prüfpunkte für Nachrüst- und Übergangsfristen der HeizkostenV (Eigentümer Steuerberater oder Rechtsberatung, Timo Müller)
Frage: Welche amtlich geprüften Fristen, Daten und Wortlaute sind je Fall einzutragen (R12, R14)?
Gate: G3.
Ergebnis (technischer Stand): Die Prüfpunkte sind als konfigurierbare Einträge im Regelregister vorbereitet, Standard leer. Fällige Punkte erscheinen über rule-versions/due-checkpoints als Hinweis ohne Rechtsfolge. Eine CRM-Fälligkeitsliste steht noch aus.
Empfehlung: Gemeinsam mit AA12-02 erledigen: Fristen und Quellen nennen lassen, dann erfassen. Ohne Befüllung bleibt die Funktion wirkungslos, das ist unschädlich.
Vermerk: technisch vorbereitet (Welle 16, AE19): Die Prüfpunkte sind im CRM pflegbar (Datum, Bezeichnung, Quelle, Notiz, Stand, Vorfrist), Standard bleibt leer. Fristen und Quellen nennt die Rechtsberatung.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Gemeinsame Befüllung mit AA12-02 | gering | gering |
| B Leer lassen | keiner | gering, Fristen nicht überwacht |
| C Eigene Recherche eintragen | gering | hoch |

## G4 WEG-Abrechnung (Fortsetzung)

### AA07-01 Zuordnung des Abrechnungsergebnisses bei Eigentümerwechsel in Sonderfällen (Eigentümer Timo Müller mit Rechtsanwalt)
Frage: Wem wird das Abrechnungsergebnis bei Ersterwerb, Erbfall, Zwangsversteigerung, Schenkung und Sondernachfolgehaftung zugeordnet (Eigentümer zum Beschlussdatum, Rechtsvorgänger, Erwerber nach Zeitraum)?
Gate: G4.
Ergebnis (technischer Stand): Umgesetzt ist der Freigabeschritt mit Zuordnungsvorschlag als Text. Die Fälle erscheinen mit deutscher Bezeichnung in Befund und Freigabeliste. Die Berechnung bleibt bei der Annahme M24-01.
Empfehlung: Regel je Erwerbsart durch den Rechtsanwalt festlegen und die Quelle aus Anhang C benennen, danach Zahlenfall und Anpassung in hoa/calc.py. Bis dahin entscheidet die Verwaltung im Einzelfall.
Vermerk: technisch vorbereitet (Welle 16, AE10): Mandantenregel je Erwerbsart (manuelle Freigabe als Standard, Zuordnung nach Fälligkeit oder nach Abrechnungsbeschluss), bisher angewendet auf den Schuldnervorschlag der Sonderumlagen-Differenz, Berechnung beim Standard unverändert. Die Regel je Erwerbsart legt der Rechtsanwalt fest.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Regel je Erwerbsart durch Rechtsanwalt | mittel | gering |
| B Einzelfallentscheidung bei Freigabe beibehalten | keiner | mittel |
| C Pauschal Eigentümer zum Beschlussdatum | gering | hoch |

### AA07-02 Verfügbarmachung des Vermögensberichts, Portal oder Brief (Eigentümer Timo Müller mit Rechtsanwalt)
Frage: Ersetzt der Abruf im Eigentümerportal die Verfügbarmachung nach § 28 Abs. 4 WEG oder ist zusätzlich ein Versand per Brief nötig?
Gate: G4.
Ergebnis (technischer Stand): Das Bereitstellungsprotokoll ist nur ein Indiz. Seit 1.58.0 kann der Bericht je Eigentümer zusätzlich per Brief über den bestehenden Versand bereitgestellt werden (hinter G4, Standard nur ohne Portalabruf).
Empfehlung: Rechtsanwalt bewertet, ob der Portalabruf genügt. Bis dahin Brief für Eigentümer ohne Portalabruf nutzen. Die Einstufung ist eine Rechtsfrage und hier nur eine Einschätzung.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Portal und Brief ohne Abruf, Bewertung durch Rechtsanwalt | gering | gering |
| B Immer Brief zusätzlich | mittel | gering, Mehrkosten |
| C Nur Portal | keiner | mittel |

### AA06-01 Status void der Beschluss-Sammlung (Eigentümer Timo Müller mit Rechtsanwalt)
Frage: Bleibt void neben annulled bestehen oder wird er je Eintrag in deleted oder irrelevant überführt?
Gate: G4.
Ergebnis (technischer Stand): deleted und irrelevant sind als Vermerk ergänzt, void bleibt zulässig, es gibt keine Datenübernahme.
Empfehlung: void zunächst belassen und eine Datenübernahme erst nach Entscheidung per Migration umsetzen. Eine Überführung darf Bestandseinträge nicht verfälschen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A void belassen, Entscheidung je Eintrag später | keiner | gering |
| B Alle void zu annulled überführen | mittel | mittel |
| C Alle void zu deleted überführen | mittel | hoch, Beweiswert |

### AA06-02 Höchstdauer des Grundlagenbeschlusses virtueller Versammlungen (Eigentümer Timo Müller mit Rechtsanwalt)
Frage: Gilt die Höchstdauer von drei Jahren (7.8 W13 Satz 4) ohne Ausnahme und welchen Inhalt und Anwendungsbereich hat die Übergangsregel des § 48 Abs. 6 WEG?
Gate: G4.
Ergebnis (technischer Stand): Umgesetzt ist ein dauerhafter Hinweis in der Versammlungsdetailansicht. Die Sperre ist nur mit dem Mandantenschalter hoa_virtual_basis_term_lock_enabled (Standard aus) aktiv.
Empfehlung: Rechtliche Prüfung mit Quelle aus Anhang C, danach Schalter setzen oder Regel anpassen. Bis dahin Hinweis ohne Sperre.
Vermerk: technisch vorbereitet (Welle 16, AE12): Stichtag der Übergangsregel als Mandantenfeld (vom Betreiber einzutragen, ohne Rechtswirkung und ohne Sperre), Fristhinweise im Versammlungsdetail und CRM-Maske für den Online-Versammlungsschalter. Die rechtliche Prüfung bleibt offen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Prüfung durch Rechtsanwalt, dann Schalter | gering | gering |
| B Hinweis ohne Sperre dauerhaft | keiner | mittel |
| C Sperre sofort einschalten | keiner | mittel, Fehlsperre möglich |

## G5 Fremdmandanten (Fortsetzung)

### AA17-03 Kundendomain per DNS prüfen und gesperrte Mandanten (Eigentümer Timo Müller)
Frage: Soll die Kundendomain beim Anlegen per DNS (CNAME) geprüft werden und soll ein gesperrter Mandant (suspended) die Anmeldung verhindern?
Gate: G5.
Ergebnis (technischer Stand): Der Status wird gesetzt, aber in der Anmeldung nicht ausgewertet. Plattformaktionen sind seit 1.58.0 im Plattformaudit festgeschrieben (Migration 0332).
Empfehlung: Beide Punkte vor Aufnahme von Drittmandanten umsetzen: Sperre in der Anmeldung zwingend, DNS-Prüfung als Warnung. Ohne Sperre ist der Status wirkungslos.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Sperre erzwingen, DNS-Prüfung als Warnung | mittel | gering |
| B Beides unverändert | keiner | mittel |
| C DNS-Prüfung als Pflicht | mittel | mittel, Anlage erschwert |

### AA14-02 Bewertungen von Dienstleistern im Portal (Eigentümer Timo Müller)
Frage: Soll der Dienstleister seine Bewertungen (Auftragsbewertung der Verwaltung) im Portal sehen?
Gate: G5.
Ergebnis (technischer Stand): Die Bewertung ist intern. Eine Anzeige berührt Persönlichkeits- und Geschäftsinteressen. Nicht umgesetzt.
Empfehlung: Bewertungen intern lassen. Eine Anzeige nur nach Abstimmung mit dem Datenschutz und mit sachlichem, begründetem Inhalt.
Vermerk: technisch vorbereitet (Welle 16, AE30): Bewertungen von Dienstleistern hinter dem Mandantenschalter provider_rating_display (Standard aus), Übersicht nur für die Verwaltung ohne Freitext, Dienstleister und Dritte sehen nichts. Die Entscheidung bleibt offen (AE30-02).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Intern lassen | keiner | gering |
| B Nur Sterne und Freitext freigeben nach Prüfung | mittel | mittel |
| C Vollständige Anzeige | gering | hoch |

### AA14-03 Rollen und Unterlagenklassen im Portal (Eigentümer Timo Müller mit Rechtsanwalt)
Frage: Welche Rollen (Beirat, Mieter mit Belegrecht) erhalten welche Unterlagenklassen und gilt die Freigabe zusätzlich zur Verknüpfung mit dem Rechtsträger oder objektweit?
Gate: G5.
Ergebnis (technischer Stand): Umgesetzt ist die Freigabe je Rechtsträger und Klasse (Migration 0316). Die Zuordnung ist eine Entscheidung der Verwaltung, keine Rechtsregel. Eine Voreinstellung je Rolle fehlt.
Empfehlung: Voreinstellung eng wählen (nur eigene Einheit und eigener Rechtsträger), Erweiterungen je Objekt bewusst freigeben. Rechtsfragen zum Belegrecht klärt der Rechtsanwalt.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Enge Voreinstellung, Erweiterung bewusst | gering | gering |
| B Objektweite Freigabe als Standard | keiner | mittel, Datenschutz |
| C Keine Voreinstellung | keiner | gering, Pflege je Fall |

### AB12-01 Gate G5 für Dienstleister-Freigaben (Eigentümer Timo Müller)
Frage: Fallen Klassenfreigaben und Verfügbarkeitsfenster der Dienstleister im Portal unter G5?
Gate: G5.
Ergebnis (technischer Stand): Die Freigaben sind mandanteninterne Konfiguration und öffnen weder Geld noch Abrechnung. 18.0 und ADR 0003 ordnen G5 dem Betrieb für Drittmandanten zu. Technisch kein Gate gesetzt.
Empfehlung: Kein zusätzliches Gate. Ein Gate würde die Pflege auch für den ersten Mandanten sperren. Fremdmandanten sind ohnehin durch G5 insgesamt geschützt.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Kein Gate | keiner | gering |
| B Gate nur für Drittmandanten bei Erteilung | gering | gering |
| C Gate immer | gering | mittel, sperrt den ersten Mandanten |

## Ohne Gate (Fortsetzung)

### AA16-01 HeiWaKo Stammdatenlieferung (Satzart A) (Eigentümer Timo Müller, Anbieterauskunft)
Frage: Erwarten Techem, Brunata Minol und BRUNATA-METRONA eine Stammdatenlieferung in diesem Format und welche Satzarten (L, M, B, K) wären zu liefern?
Gate: keins.
Ergebnis (technischer Stand): write_a_records schreibt DTA310_*.DAT und ist nicht an eine Übermittlung angebunden. L und M liegen für Lesen und seit 1.58.0 für Schreiben mit Roundtrip-Test vor, B und K sind nicht beschrieben.
Empfehlung: Die Anbieter nach dem Eingangsformat fragen. Ohne Bedarf die Abweichung als entschieden dokumentieren. Kein Bau für nicht beschriebene Satzarten.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Anbieter fragen, sonst dokumentieren | gering | gering |
| B Satzarten B und K nach Annahme bauen | mittel | hoch |
| C Funktion entfernen | gering | gering |

### AA16-02 Hub-Parser (13.4 letzter Satz) (Eigentümer Timo Müller)
Frage: Wird die Abweichung bestätigt, dass mhvp.imports die Immoware24-Exporte als Neubau liest und der Hub nicht angebunden wird, oder sollen die Hub-Parser (PHP) für einen Abgleich bereitgestellt werden?
Gate: keins.
Ergebnis (technischer Stand): Dokumentiert in docs/integrations/immoware-hub.md, Abschnitt Abgleich. Die Hub-Parser verbleiben bis zur Ablösung im Hub.
Empfehlung: Abweichung bestätigen. Mit B27 ist Immoware24 nur einmalige Datengrundlage, ein Abgleich per Parser lohnt den Aufwand nicht.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Abweichung bestätigen | keiner | gering |
| B Hub-Parser für Abgleich bereitstellen | mittel | gering |
| C Parser portieren | hoch | mittel |

### AA16-03 Anhang-B-Läufe der Dossiers (Eigentümer Timo Müller)
Frage: Wann werden die Läufe für Müller FLOW, Übergabeprotokoll und smart-einzug ausgeführt?
Gate: keins.
Ergebnis (technischer Stand): Die Dossiers haben seit 1.58.0 einen Abschnitt Faktenstand. Die Dossiers mueller-flow.md und uebergabeprotokoll.md sowie die Wissensdatenbank-Einträge stehen nach den Läufen aus (V1).
Empfehlung: Läufe in einer ruhigen Phase ansetzen, da ohne Bezug zu Gates. Niedrige Priorität.
Vermerk: technisch vorbereitet (Welle 16, AE38): Dossier-Vorlage docs/integrations/DOSSIER-VORLAGE.md und Checkliste docs/integrations/CHECKLISTE-BESTANDSTOOLS.md sind angelegt. Die Läufe führt der Betreiber aus (AE38-02).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Läufe nach G1 Vorbereitung | gering | gering |
| B Läufe sofort | gering | gering |
| C Dossiers ohne Lauf belassen | keiner | gering, Wissenslücke |

### AA03-01 Ereignistypen der Verträge (Eigentümer Timo Müller)
Frage: Sollen die Ereignistypen langfristig auf contract.changed und contract_payment.changed vereinheitlicht werden (ADR) oder bleiben die detaillierten Typen führend?
Gate: keins.
Ergebnis (technischer Stand): Derzeit werden beide Typen erzeugt, Tests prüfen Erzeugung, Signatur und Nutzlast.
Empfehlung: Beide Typen beibehalten, solange keine externen Abnehmer bekannt sind. Entfernen würde Abnehmer brechen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Beide beibehalten | keiner | gering |
| B Vereinheitlichen mit ADR und Übergangsfrist | mittel | mittel |
| C Detaillierte Typen entfernen | gering | mittel |

### AA13-01 Direktablage sicherer Zuordnungen im Dokumenteingang (Eigentümer Timo Müller)
Frage: Soll die Direktablage produktiv freigegeben werden, ab welcher Schwelle und für welche Quellen (Paperless, Drive, Postfach)?
Gate: keins.
Ergebnis (technischer Stand): Schalter document_intake_auto_file (Standard aus), Schwelle ab 0,5, Standard 0,9. Wirkung nur Verknüpfung mit dem Objekt, Rücknahme per revert-auto. Weicht von Regel 0.1.6 ab, solange nicht entschieden. Tests in beiden Schalterzuständen vorhanden.
Empfehlung: Pilot je Mandant mit Schwelle 0,9 und nur einer Quelle, Auswertung der Rücknahmen nach vier Wochen. Danach entscheiden. Die Verknüpfung ist ohne Geldwirkung und rücknehmbar.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Pilot mit Schwelle 0,9 und einer Quelle | gering | gering |
| B Dauerhaft aus, nur Vorschläge | keiner | gering |
| C Alle Quellen ab 0,5 | keiner | hoch |

### AA05-01 Freigabe-Workflow für Aufträge (Eigentümer Timo Müller)
Frage: Ersetzt die Beiratsabstimmung den Freigabeablauf und entfällt die Spalte work_order.approval_workflow_id oder entsteht ein allgemeiner Workflow (Entität, Stufen, Rollen)?
Gate: keins.
Ergebnis (technischer Stand): Die Spalte ist optional, ohne Fremdschlüssel und ohne Wirkung, am Auftrag pflegbar. Maßgeblich bleibt requires_board_approval.
Empfehlung: Bei der Beiratsfreigabe bleiben, bis ein zweiter Anwendungsfall einen allgemeinen Workflow rechtfertigt. Spalte danach entfernen oder verwenden.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Beiratsfreigabe beibehalten, Spalte später entscheiden | keiner | gering |
| B Allgemeiner Workflow | hoch | mittel |
| C Spalte sofort entfernen | gering | gering |

### AA05-02 Textbausteine (template_block) (Eigentümer Timo Müller)
Frage: Welche Bausteine soll es geben, wie werden sie in Vorlagen eingebunden und gelten sie je Mandant?
Gate: keins.
Ergebnis (technischer Stand): Die Tabelle template_block ist nicht angelegt.
Empfehlung: Zuerst drei bis fünf konkrete Bausteine benennen (zum Beispiel Grußformel, Fußtext). Danach Mandantenbezug und Include entwerfen. Ohne Anforderung nichts bauen.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Anforderung benennen, dann bauen | mittel | gering |
| B Verzicht, Vorlagen kopieren | keiner | gering, Pflegeaufwand |
| C Allgemeine Bausteinverwaltung sofort | hoch | mittel |

### AA05-03 Abstandsgrenzwert für Lernbeispiele (Eigentümer Timo Müller)
Frage: Gilt der Abstandsgrenzwert 0,8 (MAX_COSINE_DISTANCE) auch für Lernbeispiele oder braucht die Auswahl einen eigenen Wert?
Gate: keins.
Ergebnis (technischer Stand): Beispiele werden nur eingebettet und genutzt, wenn die Einbettungsroute freigegeben ist (Stufe embedding, Vier-Augen, AVV-Nachweis, Opt-out).
Empfehlung: Wert 0,8 beibehalten und nach Auswertung mit make ai-eval an echten, freigegebenen Daten prüfen. Der Wert ist keine Rechtsfrage.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A 0,8 beibehalten, nach Auswertung anpassen | gering | gering |
| B Eigener strengerer Wert | gering | gering |
| C Beispiele deaktivieren | keiner | gering |

### AA15-01 Demo-Mandant (Eigentümer Timo Müller)
Frage: Ist ein separater Demo-Mandant gewünscht, soll er ein Kennzeichen demo erhalten (Schemaänderung) und in Staging dauerhaft bestehen?
Gate: keins.
Ergebnis (technischer Stand): make seed-demo legt demo-muster mit erfundenen Daten an, nur in dev, test und staging mit MHVP_DEMO_SEED=1.
Empfehlung: Demo-Mandant nur in Staging, ohne neues Kennzeichen, bis Vorführungen im größeren Umfang anstehen. Keine Schemaänderung auf Vorrat.
Vermerk: technisch vorbereitet (Welle 16, AE36): Mandantenkennzeichen tenant.is_demo mit Ausschluss aus Plattformabrechnung, Mandantenexport, Journal-Export und DATEV, make seed-demo nur mit synthetischen IBANs (Alternative B). Die Entscheidung bleibt offen (AE36-02).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Nur Staging, ohne Kennzeichen | keiner | gering |
| B Kennzeichen demo und dauerhaft in Staging | mittel | gering |
| C Kein Demo-Mandant | keiner | gering |

### AA15-02 Ansprechpartner im Incident-Runbook (Eigentümer Timo Müller, Rechtsanwalt)
Frage: Wer sind Datenschutzbeauftragter und Rechtsanwalt als Ansprechpartner und ist der Ablauf samt Meldefristen rechtlich geprüft?
Gate: keins.
Ergebnis (technischer Stand): docs/runbooks/incident.md nennt bewusst keine Namen und Telefonnummern.
Empfehlung: Ansprechpartner im Betreiberhandbuch benennen und den Ablauf durch den Rechtsanwalt prüfen lassen. Meldefristen sind zu verifizieren und nicht aus dem Runbook allein abzuleiten.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Benennen und Ablauf prüfen lassen | gering | gering |
| B Nur Ansprechpartner benennen | keiner | mittel |
| C Runbook belassen | keiner | mittel |

### AA04-01 If-Match für Geldflüsse verpflichtend (Eigentümer Timo Müller)
Frage: Soll If-Match für Geldflüsse (Bank, Mahnung, Abrechnung) per Mandantenschalter verpflichtend werden (Antwort 428) und ab wann sendet das CRM die Kopfzeile?
Gate: keins.
Ergebnis (technischer Stand): ETag und If-Match sind an weiteren Ressourcen ergänzt (AB04), nach ADR 0012 freiwillig. Seit 1.58.0 prüfen mehrere Listen die Kopfzeile.
Empfehlung: Pflicht je Mandant einführen, aber erst nachdem das CRM die Kopfzeile an allen Geldflussmasken sendet. Das schützt vor Überschreiben bei gleichzeitiger Bearbeitung.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Mandantenschalter, CRM zuerst anpassen | mittel | gering |
| B Freiwillig lassen | keiner | mittel |
| C Sofort verpflichtend | gering | mittel, externe Clients brechen |

### AA17-02 Nummernformat für Objekt-, Beleg- und Ticketnummern (Eigentümer Timo Müller)
Frage: Sollen weitere Nummern über die Mandantenkonfiguration formatiert werden?
Gate: keins.
Ergebnis (technischer Stand): Die Konfiguration wirkt bisher nur bei Vertragsnummern.
Empfehlung: Nur bei konkretem Bedarf eines Mandanten ausweiten. Belegnummern berühren Buchhaltung und sind zusammen mit AA17-01 zu bewerten.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Zunächst nicht ausweiten | keiner | gering |
| B Objekt und Ticketnummern ausweisen, Beleg nach AA17-01 | mittel | gering |
| C Alle Nummern sofort | mittel | mittel |

### AA14-01 Formularelementtypen des Portals (Eigentümer Timo Müller)
Frage: Entsprechen die sechs ergänzten Typen (Anschrift, Standort, Unterschrift als Name, Einwilligung, Betrag, Trennlinie) der Typenliste des bisherigen Portals (Portal24)?
Gate: keins.
Ergebnis (technischer Stand): Die Typen sind umgesetzt, die Typenliste des Altportals liegt nicht vor.
Empfehlung: Typenliste aus dem Altportal liefern, Abweichungen danach anpassen. Geringer Aufwand.
Vermerk: technisch vorbereitet (Welle 16, AE30): Die 20 Elementtypen sind final mit Typregister, Prüfregel je Typ und Vorschau im CRM. Offen bleibt der Abgleich mit der Typenliste des Altportals (AE30-01).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Typenliste liefern und abgleichen | gering | gering |
| B Typen belassen | keiner | gering |
| C Typen nach Rückmeldung der Nutzer anpassen | gering | gering |

## Welle 19, Paket AH14: Entscheidungsvorlagen für die Geschäftsführung (02.10.2026)

Hinweis: Die folgenden Vorlagen entscheiden nichts. Alle Schalter bleiben auf dem konservativen Standard, die Gates G1 bis G5 bleiben geschlossen. Die Fragen stehen zusätzlich in docs/OPEN_QUESTIONS.md (AH14-01 bis AH14-07).

### AH14-01 Umfang Versicherungs-Router (GAG-18, GAC-07) (Eigentümer Timo Müller)
Sachverhalt: Die Rolle Versicherungsmakler hält `insurance:read` und `claims:read` nur bei gesetztem Mandantenschalter `insurance_broker_access` (Standard aus). Es gibt keinen eigenen Fach-Router für Versicherungsverträge und Schadenfälle; der Umfang dessen, was ein Makler sehen darf, ist nicht festgelegt.
Varianten: A kein eigener Router, Makler bleibt ohne Zugriff (Schalter aus); B lesender Router nur für Verträge und Schadenfälle der zugeordneten Objekte, ohne Personendaten der Mieter; C lesender Router einschließlich Schadenbeteiligter und Dokumente.
Risiko: Datenschutz (Weitergabe personenbezogener Daten an Dritte braucht Rechtsgrundlage und gegebenenfalls Vertrag mit dem Makler); kein Geldbezug.
Empfehlung: Variante A bis zur Klärung der Rechtsgrundlage, danach B mit Objektbindung und Datenminimierung.
Gate: keins (Datenschutzfreigabe durch den Betreiber).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Kein Router, Schalter aus | keiner | gering |
| B Lesend, objektgebunden, ohne Mieterdaten | mittel | gering |
| C Lesend mit Beteiligten und Dokumenten | mittel | hoch (Datenschutz) |

### AH14-02 Masken für Zahlungsläufe (GAG-19, M15-01) (Eigentümer Timo Müller)
Sachverhalt: Die Endpunkte payment-batches (Erzeugen, Download, Einreichung) und payment-bank-config haben keine CRM-Maske. Zahlungsformat, Zeichensatz und Einreichungsweg mit den Banken sind nach M15-01 nicht bestätigt; ein Schema-Abgleich gegen das offizielle XSD fehlt.
Varianten: A keine Maske bis M15-01 entschieden; B Maske nur lesend (Liste, Vorschau, Status), Erzeugen und Einreichen hinter G2 gesperrt; C vollständige Maske mit Erzeugen und Download, Einreichung hinter G2.
Risiko: Geld (fehlerhafte oder doppelte Zahlungsdateien, falsches Auftraggeberkonto, Rechtsträgertrennung).
Empfehlung: Variante B; Variante C erst nach Bankbestätigung und XSD-Prüfung (P05).
Gate: G2.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Keine Maske | keiner | gering |
| B Nur lesend, Aktionen hinter G2 | mittel | gering |
| C Vollständig, Einreichung hinter G2 | hoch | mittel |

### AH14-03 Eigener Sperrcode für B2B-Lastschriftläufe (GAG-20, AF07-01) (Eigentümer Timo Müller)
Sachverhalt: B2B-Mandate werden bei Erfassung mit `MHVP-CONT-0033` abgewiesen. Ein Lastschriftlauf mit Instrument B2B hat keinen eigenen 409-Code; ob B2B-Läufe überhaupt angeboten werden, ist nach AF07-01 offen (Bankvereinbarung, Vorlauffrist, kein Erstattungsanspruch des Zahlers).
Varianten: A beim Status quo bleiben (Abweisung schon bei Mandatserfassung genügt); B zusätzlicher 409-Code im Lastschriftlauf als zweite Sperre; C B2B-Läufe nach Bankvereinbarung technisch umsetzen.
Risiko: Geld und Recht (Lastschrift ohne wirksames B2B-Mandat, Rückgabe, Haftung gegenüber dem Zahler).
Empfehlung: Variante B als reine Schutzsperre ohne Rechtsentscheidung; Variante C erst nach Bankvereinbarung und rechtlicher Prüfung.
Gate: G2.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Status quo | keiner | gering |
| B Zweite Sperre im Lauf (409) | gering | gering |
| C B2B umsetzen | hoch | mittel |

### AH14-04 Vier-Augen-Antrag der Ausgangsautomatik (GAG-21, M12-05) (Eigentümer Timo Müller, Buchhaltung)
Sachverhalt: Seit Welle 18 (AG19) läuft das Einschalten der Ausgangsautomatik nur über einen Antrag mit Ziel `outgoing`, Freigabe durch eine zweite Person und G1; `PUT /banking/automation/outgoing` schaltet nur aus (`MHVP-BANK-0064`). Offen ist die fachliche Freigabe der Ausgangsautomatik selbst (Stufe L2b, Regel M12-05) und ob der bestehende Antrag als eigener Vier-Augen-Antrag genügt.
Varianten: A bestehenden Antrag als ausreichend festlegen; B eigenen Antragstyp je Regel (Kreditor, Sachkonto, Höchstbetrag) mit getrennter Freigabe; C Ausgangsautomatik bis nach G1 nicht freigeben, nur Vorschläge.
Risiko: Geld und Recht (automatische Buchungen gegen Sachkonto ohne Einzelprüfung, Nachvollziehbarkeit, B01 bis B09).
Empfehlung: Variante C bis G1; danach Variante B, weil der Höchstbetrag und die Regel selbst freigabepflichtig sein sollten.
Gate: G1.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Bestehender Antrag genügt | keiner | mittel |
| B Antrag je Regel | mittel | gering |
| C Nur Vorschläge bis G1 | keiner | gering |

### AH14-05 download-url und mirror als Integrations-API (GAG-27) (Eigentümer Timo Müller)
Sachverhalt: `GET /documents/{id}/download-url` (signierte Download-URL) und `POST /documents/{id}/mirror` (Spiegelung erneut anstoßen) werden weder im CRM noch im Portal aufgerufen. Offen ist, ob beide nur als Integrations-API für externe Systeme dienen.
Varianten: A als reine Integrations-API dokumentieren, kein UI; B Spiegelung erneut anstoßen als Aktion im CRM (Dokumentdetail), Download-URL nur Integration; C beides im CRM und Portal anbieten.
Risiko: Datenschutz (signierte URLs sind ohne Anmeldung nutzbar, Weitergabe außerhalb der Mandantentrennung bis zum Ablauf); kein Geldbezug.
Empfehlung: Variante B mit kurzer Gültigkeit der URL und Protokollierung jedes Abrufs.
Gate: keins.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Nur Integrations-API | gering | gering |
| B Mirror im CRM, URL nur Integration | gering | gering |
| C Beides in CRM und Portal | mittel | mittel (Datenschutz) |

### AH14-06 KI-Vorqualifizierung von Portalanliegen (GAG-33) (Eigentümer Timo Müller, Datenschutz)
Sachverhalt: `POST /portal/tickets/{id}/prequalify` hat keinen Aufruf im Portal; der Schalter `chat_ai_prequalification_enabled` existiert nur in portal/types.ts. Die Vorqualifizierung würde Inhalte von Mietern und Eigentümern an einen KI-Anbieter geben.
Varianten: A nicht im Portal anbieten, nur CRM-seitig als Vorschlag für Mitarbeitende; B im Portal mit ausdrücklichem Hinweis und Einwilligung, Ergebnis nur als Vorschlag; C automatisch für jedes Anliegen.
Risiko: Datenschutz (Übermittlung an Anbieter, AVV, Maskierung, Transparenz gegenüber Betroffenen); Recht, falls Vorqualifizierung Fristen oder Mängelanzeigen beeinflusst.
Empfehlung: Variante A; Variante B erst nach geprüftem AVV und Datenschutzhinweis. Variante C nicht empfohlen (Regel 0.1.6, nur Vorschläge).
Gate: keins (Datenschutzfreigabe, KI-Freigabeschalter bleiben aus).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Nur CRM, Portal ohne KI | keiner | gering |
| B Portal mit Einwilligung | mittel | mittel |
| C Automatisch | gering | hoch |

### AH14-07 Ausführungsprotokoll Anhang D (GAG-37) (Eigentümer Timo Müller, fachkundige Person V16)
Sachverhalt: docs/acceptance/abnahme-anhang-d.md führt D01 bis D58 ohne Ergebnis, Datum und Name. Testbezug in apps/api/tests ist nach Regel 0.1.8 kein bestandener Fall. Für die Abnahme liegt jetzt die Vorlage docs/acceptance/PROTOKOLL-ANHANG-D-VORLAGE.md mit den Spalten Ergebnis, Datum, Name und Nachweis vor.
Varianten: A Abnahme aller 58 Fälle in einem Termin; B gestuft je Gate, zuerst die 23 G1-Fälle samt D50, D51, D57; C Abnahme nur durch den Betreiber ohne fachkundige Person.
Risiko: Geld und Recht (Öffnung von G1 bis G4 ohne nachgewiesene fachliche Abnahme).
Empfehlung: Variante B; Variante C nicht empfohlen, weil Anhang D.3 die fachkundige Bestätigung der Sollwerte verlangt.
Gate: G1 bis G4 (Voraussetzung jeder Öffnung).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Alle Fälle in einem Termin | hoch | gering |
| B Gestuft je Gate | mittel | gering |
| C Nur Betreiber | gering | hoch |

## Welle 20: Entscheidungsvorlagen AI17 (02.10.2026)

Hinweis: Die folgenden Vorlagen entscheiden nichts. Alle Schalter bleiben auf dem konservativen Standard, die Gates G1 bis G5 bleiben geschlossen. Normen sind nur genannt, soweit Anhang C sie führt. Die Fragen stehen zusätzlich in docs/OPEN_QUESTIONS.md (AI17-01 bis AI17-13).

### AI17-01 Zahlungskriterium und Mehrfachbescheinigung § 35a EStG (GAH-101, H06, D44, R24, P03) (Eigentümer Steuerberater)
Sachverhalt: Der Ausweis nimmt alle markierten Rechnungszeilen nach Rechnungsdatum; Zahlungsstatus, Zahlungsdatum und Kostenträger werden nicht geprüft. Der Anteil `share_percent` ist frei eingebbar. Mehrere Ausweise für dieselbe Einheit und dasselbe Jahr sind möglich. AI18 bereitet den Schalter `tax_35a_basis` (invoice_date Standard, payment_date) technisch vor.
Varianten: A Rechnungsdatum (heutiges Verhalten); B nur bezahlte Rechnungen mit Zahlungsdatum im Jahr; C wie B und zusätzlich Anteil aus der Verteilung abgeleitet, Sperre gegen zweiten Ausweis ohne Stornovermerk.
Risiko: Recht und Steuer (unzutreffende Bescheinigung gegenüber Mietern und Eigentümern, Haftung).
Empfehlung: Variante C nach Bestätigung durch den Steuerberater (R24 nennt Zahlung als Unterscheidungsmerkmal, P03 die WEG-Bescheinigung und zeitliche Zuordnung); bis dahin Ausweis nur als Entwurf.
Gate: G3, G4.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Rechnungsdatum | keiner | hoch |
| B Zahlungsdatum | mittel | mittel |
| C Zahlungsdatum, Anteil aus Verteilung, Sperre | hoch | gering |

### AI17-02 Pflichtanteil Verbrauch HeizkostenV (GAH-108, H02, R11, R13) (Eigentümer Rechtsanwalt)
Sachverhalt: Der Verbrauchsanteil ist frei zwischen 50 und 70 Prozent wählbar. Anwendbarkeit, Ausnahmen und Fälle mit verpflichtendem Verbrauchsanteil (§ 7 HeizkostenV nach R11) werden nicht erfasst.
Varianten: A Status quo mit Hinweis im Handbuch; B Pflichtfeld Begründung des gewählten Anteils, Prüfhinweis ohne Sperre; C Erfassung der Gebäudemerkmale je Anlage mit Sperre unzulässiger Anteile nach geprüftem Regelwerk.
Risiko: Recht (fehlerhafte Heizkostenabrechnung, Kürzungsrecht nach R13).
Empfehlung: Variante B sofort als Produktschutz, Variante C nach Bestätigung der Fallgruppen und Ausnahmen durch den Rechtsanwalt (R11 verlangt Ergänzung der für die Anlage relevanten Vorschriften).
Gate: G3.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Status quo | keiner | hoch |
| B Begründungspflicht, Hinweis | gering | mittel |
| C Merkmale und Sperre | hoch | gering |

### AI17-03 CO2-Aufteilung Nichtwohngebäude und Teiljahre (GAH-109, H04, H05, D27, R15, R16) (Eigentümer Rechtsanwalt, Messdienst)
Sachverhalt: Nichtwohngebäude, gemischte Nutzung und Selbstversorgung liefern nur den Status "prüfen"; bei Teiljahren wird keine Hochrechnung gerechnet.
Varianten: A Status quo (kein freigebbarer Rechenweg, manuelle Aufteilung außerhalb); B manuelle Eingabe des Aufteilungsergebnisses mit Belegpflicht und Vier-Augen-Freigabe; C eigene Regelgruppe mit Hochrechnung nach bestätigter Quelle und Rundung.
Risiko: Recht (falsche Kostenaufteilung Vermieter und Mieter).
Empfehlung: Variante B als Übergang, Variante C erst nach Quellenbestätigung (R15, R16; H05 verbietet vorzeitige Anwendung späterer Regeln) und Eintrag im Regelregister.
Gate: G3.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Status quo | keiner | gering |
| B Manuelle Eingabe mit Beleg | mittel | gering |
| C Regelgruppe | hoch | mittel |

### AI17-04 Prüfhinweis Kaution § 551 BGB (GAH-111, Anhang C) (Eigentümer Rechtsanwalt)
Sachverhalt: Kautionsbetrag und Ratenzahl (1 bis 12) werden nicht gegen die Grenzen für Wohnraum geprüft. AI18 bereitet den Schalter `deposit_limit_hint_enabled` (Standard aus) mit konfigurierbarem Faktor und Hinweistext ohne Normzitat vor.
Varianten: A kein Hinweis; B nicht sperrender Prüfhinweis bei Wohnraum mit vom Rechtsanwalt freigegebenem Wortlaut; C Sperre oberhalb der Grenze.
Risiko: Recht (unzulässige Sicherheit, Rückforderung).
Empfehlung: Variante B, Wortlaut und Werte nur nach Freigabe; Variante C nicht empfohlen, weil Sonderfälle (Bürgschaft, Gewerbe, Mischmietverhältnis) eine starre Sperre falsch machen können.
Gate: G3.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Kein Hinweis | keiner | mittel |
| B Prüfhinweis | gering | gering |
| C Sperre | gering | mittel |

### AI17-05 Zeitstempel im Webhook der Objektakte (GAH-202) (Eigentümer Timo Müller, Betreiber Objektakte)
Sachverhalt: Der Webhook prüft nur HMAC über den Body, ohne Zeitstempel und Zeitfenster; Replay bleibt möglich. Die Größenprüfung liest den Body vor der Prüfung.
Varianten: A Status quo; B Header X-MHVP-Timestamp wie bei Paperless, signiert, Zeitfenster, Übergangszeit mit Annahme alter Aufrufe hinter Schalter; C sofortige Pflicht ohne Übergang.
Risiko: Sicherheit (Wiederholung von Ereignissen wie `object.taken_over`); Vertragsänderung mit dem externen Dienst.
Empfehlung: Variante B nach Abstimmung mit dem Dienst; Content-Length-Vorabprüfung unabhängig davon umsetzen.
Gate: keins.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Status quo | keiner | mittel |
| B Zeitstempel mit Übergang | mittel | gering |
| C Sofortige Pflicht | gering | mittel (Ausfall der Integration) |

### AI17-06 Dauerhaft fehlschlagende ausgehende Webhooks (GAH-206) (Eigentümer Timo Müller)
Sachverhalt: Endgültig fehlgeschlagene Zustellungen lösen keine Meldung aus, das Abonnement bleibt aktiv, ein Zähler aufeinanderfolgender Fehlschläge fehlt.
Varianten: A Status quo; B Zähler und Benachrichtigung an Administratoren ab Schwellwert, Abonnement bleibt aktiv; C wie B und automatische Deaktivierung ab zweitem Schwellwert.
Risiko: Betrieb (unbemerkter Ausfall von Integrationen); kein Geldbezug.
Empfehlung: Variante B; Schwellwerte als Mandanteneinstellung, Werte vom Betreiber festzulegen. Variante C erst nach Erfahrung mit B.
Gate: keins.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Status quo | keiner | mittel |
| B Melden | mittel | gering |
| C Melden und deaktivieren | mittel | gering (Datenlücke beim Empfänger) |

### AI17-07 Obergrenze der Seitengröße (GAH-208, Abschnitt 12) (Eigentümer Timo Müller)
Sachverhalt: 44 Parameter `limit` oder `page_size` erlauben mehr als 200, `/postal/jobs` hat keine Obergrenze; nur ein kleiner Teil der Listen bietet `page_size`.
Varianten: A Status quo; B einheitlich höchstens 200, Ausnahmen je Endpunkt (Exporte) dokumentiert; C höchstens 200 ohne Ausnahme, Exporte über eigene Exportjobs.
Risiko: Robustheit (Last, Zeitüberschreitung); Rückwirkung auf CRM-Aufrufe mit höheren Limits.
Empfehlung: Variante B mit Ausnahmeliste und Abgleich der CRM-Aufrufe vorab; `/postal/jobs` sofort begrenzen.
Gate: keins.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Status quo | keiner | mittel |
| B 200 mit Ausnahmeliste | mittel | gering |
| C 200 ohne Ausnahme | hoch | mittel (Bruch von Aufrufen) |

### AI17-08 Pflicht zu If-Match und ETag (GAH-210, Abschnitt 12) (Eigentümer Timo Müller)
Sachverhalt: If-Match ist bei 23 von 237 PUT/PATCH-Operationen deklariert, ETag auf GET-Antworten in OpenAPI nirgends. Beispiele ohne Sperre: `PATCH /parties/{id}`, `DELETE /contacts/{id}`, `DELETE /documents/{id}`, Einstellungen.
Varianten: A Status quo; B Pflicht zuerst für Ressourcen mit Geld-, Rechts- oder Stammdatenbezug (Parteien, Verträge, Bankverbindungen, Einstellungen), übrige in Stufen, Header zunächst optional und dann Pflicht; C sofortige Pflicht für alle Änderungen.
Risiko: Recht und Geld (verlorene Änderungen bei parallelem Bearbeiten).
Empfehlung: Variante B mit Ressourcenliste und Zeitplan durch den Betreiber; CRM sendet If-Match vor Umstellung auf Pflicht.
Gate: keins (Voraussetzung für G1 bei Finanzressourcen zu prüfen).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Status quo | keiner | mittel |
| B Gestuft nach Ressourcenliste | hoch | gering |
| C Sofort für alle | hoch | mittel (Bruch von Clients) |

### AI17-09 Verlust des zweiten Faktors (GAH-301, Abschnitt 3.4 und 16) (Eigentümer Timo Müller, Datenschutz)
Sachverhalt: Es gibt keine Wiederherstellungscodes und kein Zurücksetzen von TOTP durch Administratoren; bei Mandantenpflicht bleibt ein Benutzer dauerhaft ausgesperrt.
Varianten: A Status quo (Rücksetzung nur über Datenbank durch Betreiber); B Wiederherstellungscodes bei Einrichtung, einmalig nutzbar, gehasht; C zusätzlich Zurücksetzen durch Administrator mit Identitätsprüfung, Vier-Augen-Freigabe und Protokoll.
Risiko: Datenschutz und Sicherheit (Kontoübernahme bei schwacher Rücksetzung, Aussperrung).
Empfehlung: Variante B und C kombiniert; Administrator-Rücksetzung nur mit zweiter Person und Benachrichtigung des Benutzers.
Gate: keins.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Status quo | keiner | mittel |
| B Wiederherstellungscodes | mittel | gering |
| C B plus Administrator-Rücksetzung | mittel | gering |

### AI17-10 Abgleich Abschnitt 17 mit ADR 0024 (GAH-314) (Eigentümer Timo Müller)
Sachverhalt: Abschnitt 17 nennt `infra/grafana/`, `infra/prometheus/`, `infra/loki/` und GlitchTip; ADR 0024 entscheidet auf OTel und Uptime-Kuma. Eine Sentry-kompatible Fehlererfassung ist weder in Compose noch im Runbook beschrieben.
Varianten: A ADR 0024 gilt, Abweichung im Abschnitt 17 per Vermerk und in docs/runbooks/monitoring.md dokumentieren, Fehlererfassung über OTel; B zusätzlich GlitchTip in Compose aufnehmen; C Stack nach Abschnitt 17 vollständig nachbauen.
Risiko: Betrieb (Fehler bleiben unbemerkt); kein Geldbezug.
Empfehlung: Variante A, Variante B nur bei Bedarf nach Betriebserfahrung. Änderung des Master-Prompts nur durch den Betreiber (Regel 0.3).
Gate: keins.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Dokumentieren | gering | gering |
| B GlitchTip ergänzen | mittel | gering |
| C Vollständiger Stack | hoch | gering |

### AI17-11 Anzeigegenauigkeit Zählerstände (GAH-411, AH17) (Eigentümer Timo Müller, Messdienst)
Sachverhalt: Die CRM-Anzeige rundet Zählerstände per `formatDecimal` auf drei Nachkommastellen. Ob gespeicherte Werte mehr Stellen haben dürfen, ist nicht geprüft; Anzeige und gespeicherter Wert können abweichen.
Varianten: A Status quo; B Anzeige mit der gespeicherten Genauigkeit ohne Rundung; C Anzeige gerundet mit Hinweis und vollem Wert im Tooltip.
Risiko: Recht und Geld (Nachvollziehbarkeit der Verbrauchsabrechnung).
Empfehlung: Variante B nach Prüfung der Speichergenauigkeit im Modell; keine Änderung der gespeicherten Werte.
Gate: keins (Bezug G3).

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Status quo | keiner | mittel |
| B Volle Genauigkeit | gering | gering |
| C Tooltip | gering | gering |

### AI17-12 OCR-Cache je Importlauf und Rechtestufe (GAH-414, AH08) (Eigentümer Timo Müller)
Sachverhalt: Der OCR-Cache wird mandantenweit geleert, weil `ImportRun.document_ids` leer ist; die Zuordnung Dokument zu Lauf braucht eine Schemaänderung. Die Rechtestufe ist `objektakte:update` statt `write`.
Varianten: A Status quo (mandantenweit, Hinweis in der Maske); B Zuordnungstabelle Lauf zu Dokument (neue Migration), Leeren nur je Lauf; C Leeren nur je Einzeldokument.
Risiko: Verlust abgeleiteter Texte anderer Läufe (Originale bleiben unberührt); kein Geldbezug.
Empfehlung: Variante B in einer Welle mit reservierter Migrationsnummer; Rechtestufe `update` beibehalten und im Rechtekatalog dokumentieren.
Gate: keins.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Status quo | keiner | mittel |
| B Zuordnungstabelle | mittel | gering |
| C Je Dokument | gering | gering |

### AI17-13 Zahler-IBAN in propose_posting und Rundung ohne Verfahren (GAH-2 Zusatz, 9.1, R25; GAH-115) (Eigentümer Timo Müller, Datenschutz)
Sachverhalt: `propose_posting` übermittelt die Zahler-IBAN im Klartext an den KI-Anbieter (bewusste Ausnahme in `ai/gateway.py:70-76`); 9.1 verlangt Pseudonymisierung, wo die Aufgabe es zulässt. Daneben runden rund 100 `quantize`-Aufrufe ohne ausdrückliches Verfahren (docs/rules/RUNDUNG.md).
Varianten IBAN: A Status quo; B Platzhalter statt IBAN, lokaler Abgleich der IBAN mit dem Kontaktstamm vor und nach dem Anbieteraufruf; C Aufruf ohne IBAN-Feld.
Varianten Rundung: A Status quo; B ausdrückliches Verfahren je Fundstelle nach fachlicher Festlegung mit Test.
Risiko: Datenschutz (Übermittlung personenbezogener Daten, R25 Art. 5 und 28); Geld (Centabweichung).
Empfehlung: IBAN Variante B, weil die Zuordnung lokal deterministisch erfolgen kann; KI-Schalter bleiben aus. Rundung Variante B.
Gate: keins (Datenschutzfreigabe); Rundung Bezug G1, G3, G4.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| IBAN A Status quo | keiner | hoch |
| IBAN B Platzhalter, lokaler Abgleich | mittel | gering |
| IBAN C Ohne IBAN | gering | mittel (schlechtere Vorschläge) |

## Lückenanalyse GAI (Welle 21): Entscheidungsvorlagen AJ30-01 bis AJ30-28

Hinweis: Die folgenden Vorlagen entscheiden nichts. Grundlage sind alle Befunde der Lückenanalyse GAI (GAI-101 bis GAI-623) mit Entscheidungsbedarf "ja". Wo ein Paket der Welle 21 bereits eine Frage angelegt hat (AJ01-01 bis AJ15-05), verweist die Vorlage darauf, statt sie zu doppeln. Alle Schalter stehen auf dem konservativen Standard (aus, nichts bucht, nichts versendet, nichts löscht), G1 bis G5 bleiben geschlossen. Rechtliche und steuerliche Punkte sind Einschätzungen und vor der Entscheidung mit Rechtsanwalt oder Steuerberater abzustimmen. Normen, Fristen und Werte werden hier nicht festgelegt. Die Fragen stehen zusätzlich in docs/OPEN_QUESTIONS.md (AJ30-01 bis AJ30-28).

Priorität: zuerst Geld und Fristen (AJ30-06, AJ30-08, AJ30-11, AJ30-12, AJ30-13, AJ30-27), dann Datenschutz gebündelt (AJ30-19, AJ30-21 bis AJ30-23, AJ30-26), dann Sicherheit und Betrieb (AJ30-14 bis AJ30-16), zuletzt Doku und Pflege.

### Vermerk zu AI17-13a (Rundungsteil von AI17-13) (Eigentümer Timo Müller, Geschäftsführung)
Stand: Die Varianten zur Rundung in AI17-13 (A Status quo, B ausdrückliches Verfahren je Fundstelle) sind technisch in Richtung Variante B vorbereitet, nicht entschieden. Grundlage ist die Arbeitsvorgabe der Welle 21 (Cent-Rundung kaufmännisch ROUND_HALF_UP, Verteilungen summentreu).
Umgesetzt: zentrale Funktionen in `mhvp.core.money` (round_cents, distribute_cents, AJ02); alle quantize in billing und hoa mit ROUND_HALF_UP, Rücklagenaufteilung und Eigentümerabrechnung von HALF_EVEN auf HALF_UP, Verteilung negativer Summen summentreu (AJ01); Kappungsgrenze, check_amounts und Importe (AJ02). Register: docs/rules/RUNDUNG.md, Abschnitte Welle 21.
Nicht umgesetzt: Außerhalb von billing, hoa, letting und contracts runden weiter Aufrufe ohne ausdrückliches Verfahren, unter anderem ai/imports.py:947 (Netto aus Brutto, nur Vorschlag) und platform/licensing.py:696. Eine grep-Zählung einzeiliger quantize-Aufrufe ohne Verfahrensangabe ergibt 77 Treffer (teils mehrzeilig mit Verfahren auf der Folgezeile, nicht einzeln geprüft). Der Abschnitt "Befund: Rundung ohne ausdrückliches Verfahren" in RUNDUNG.md beschreibt noch den Stand vor Welle 21.
Wirkung: Ergebnisse ändern sich in Grenzfällen um einen Cent (x,xx5). Vor Wirkung auf produktive Abrechnungen ist die Freigabe der Geschäftsführung nötig; G1, G3 und G4 bleiben geschlossen.
Empfehlung: ROUND_HALF_UP als Produktstandard (Produktschutz, keine Rechtsregel) bestätigen, Restfundstellen in einer Folgewelle mit unabhängigen Sollwerten angleichen, RUNDUNG.md Befundabschnitt fortschreiben. Der IBAN-Teil von AI17-13 (AI17-13b) bleibt unverändert offen.
Gate: keins (Bezug G1, G3, G4). Technischer Stand: vorbereitet (Welle 21, AJ01, AJ02).

### AJ30-01 Fachliches Heute in Europe/Berlin (GAI-102) (Eigentümer Timo Müller)
Frage: Gilt als fachlicher Kalendertag für Stichtage, Gültigkeit, Protokolldatum und Sperrprüfungen einheitlich Europe/Berlin, oder braucht es eine Zeitzone je Mandant?
Varianten: A Europe/Berlin fest für alle Mandanten; B Zeitzone je Mandant (Schemaänderung); C UTC-Tag beibehalten.
Empfehlung: A. Alle Mandanten sitzen in Deutschland, eine Einstellung je Mandant wäre Aufwand ohne Nutzen. Fristberechnungen selbst bleiben Gegenstand der jeweiligen Rechtsprüfung.
Risiko: C erzeugt zwischen 00:00 und 02:00 Uhr Ortszeit das Vortagsdatum (Fristen, Belegdatum).
Gate: keins (Bezug Fristen G1, G4). Technischer Stand: vorbereitet (Welle 21, AJ09), Annahme AJ09-01 in docs/ASSUMPTIONS.md.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Europe/Berlin fest | keiner | gering |
| B Je Mandant | mittel | gering |
| C UTC | keiner | mittel |

### AJ30-02 Stackabweichungen (GAI-108) (Eigentümer Timo Müller)
Frage: Werden reportlab statt WeasyPrint oder Gotenberg, eigene SEPA-XML statt Bibliothek sowie fehlendes TanStack und shadcn per ADR 0026 freigegeben oder angeglichen?
Varianten: A ADR 0026 freigeben, SEPA-Erzeugung vor G2 gesondert gegen Schemata prüfen; B Angleichung an die Spezifikation (Umbau); C ohne Dokumentation weiter.
Empfehlung: A. Ein Umbau bindet viel Entwicklungszeit ohne fachlichen Mehrwert; das Risiko liegt allein bei der SEPA-Datei und ist über Schemaprüfung vor G2 beherrschbar.
Risiko: Zahlungsdateien fehlerhaft bei Variante C. Gate: keins, Bezug G2. Technischer Stand: vorbereitet (Welle 21, AJ14), Frage GAI-108-01.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A ADR freigeben | gering | gering |
| B Umbau | hoch | mittel |
| C Nichts | keiner | mittel |

### AJ30-03 Glossar und Codebegriffe (GAI-117) (Eigentümer Timo Müller)
Frage: Genügt die Abbildungstabelle docs/rules/GLOSSAR-ZUORDNUNG.md, oder wird im Code umbenannt?
Varianten: A Tabelle beibehalten; B Umbenennung im Code; C nichts.
Empfehlung: A. Umbenennungen berühren Schema und API und bringen Migrationsrisiko ohne Fachnutzen.
Risiko: gering. Gate: keins. Technischer Stand: vorbereitet (Welle 21, AJ15), Frage AJ15-02.

### AJ30-04 Dossiers der Bestandsprojekte (GAI-118) (Eigentümer Timo Müller)
Frage: Wann führt der Betreiber die Erhebungen nach Anhang B für Flow, Smart Einzug und Übergabeprotokoll durch, um die Platzhalter zu schließen?
Varianten: A Termin je Projekt festlegen, Dossiers danach füllen; B Platzhalter belassen, Integrationen bleiben auf Vorbereitung; C Integrationen ohne Dossier anbinden.
Empfehlung: A, gebündelt mit den Lieferungen zu V1. C ist nicht vertretbar, weil Schnittstellen ohne belegte Formate Datenfehler erzeugen.
Risiko: C mittel. Gate: keins. Technischer Stand: teilweise vorbereitet (Welle 21, AJ15), Bezug AA16-03.

### AJ30-05 Führende Statusquelle V1 bis V23 (GAI-119) (Eigentümer Timo Müller)
Frage: Master-Prompt als Version 2.1 aktualisieren oder OPEN_QUESTIONS als führende Statusquelle festlegen?
Varianten: A OPEN_QUESTIONS führend, Hinweis in der nächsten Prompt-Version; B sofort Version 2.1; C zwei Quellen belassen.
Empfehlung: A, weil OPEN_QUESTIONS laufend gepflegt wird und eine Prompt-Version nur gebündelt sinnvoll ist.
Risiko: C führt zu widersprüchlichen Arbeitsständen. Gate: keins. Technischer Stand: vorbereitet (Welle 21, AJ15), Frage AJ15-03.

### AJ30-06 Negative Heizkosten verteilen (GAI-202) (Eigentümer Geschäftsführung, Steuerberater)
Frage: Werden Gutschriften und Erstattungen des Versorgers nach denselben Schlüsseln verteilt oder gesondert ausgewiesen?
Varianten: A `distribute` (vorzeichensymmetrisch) nach fachlicher Bestätigung; B `legacy_warn` (Standard: Nullanteile mit Warnhinweis); C gesonderter Ausweis außerhalb der Verteilung.
Empfehlung: A, sofern Rechtsanwalt oder Steuerberater die Verteilung nach den Heizkostenschlüsseln bestätigt; bis dahin B. Kaufmännisch muss die Summe der Einheiten den Gesamtbetrag treffen, sonst bleibt ein nicht erklärter Rest in der Abrechnung.
Risiko: Geld und Recht (Abrechnungsergebnis je Mieter). Gate: G3. Technischer Stand: vorbereitet (Welle 21, AJ01), Frage AJ01-01; dauerhafte Speicherung je Mandant braucht Schemaänderung.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Verteilen | gering (Schema) | gering nach Bestätigung |
| B Warnung | keiner | mittel |
| C Gesonderter Ausweis | mittel | gering |

### AJ30-07 Kappungsgrenze einheitlich runden (GAI-203) (Eigentümer Timo Müller)
Frage: Bestätigung, dass beide Prüfwege der Kappungsgrenze kaufmännisch (ROUND_HALF_UP) runden.
Varianten: A bestätigen; B abweichendes Verfahren benennen.
Empfehlung: A. Die Prüfung ist Produktschutz; die rechtliche Zulässigkeit einer Mieterhöhung bleibt Sache der Rechtsprüfung.
Risiko: gering (ein Cent). Gate: keins, Bezug Mieterhöhung. Technischer Stand: vorbereitet (Welle 21, AJ02), siehe Vermerk AI17-13a.

### AJ30-08 Toleranz Brutto gegen Netto und Steuer (GAI-204) (Eigentümer Timo Müller, Steuerberater)
Frage: Bleibt 1 Cent Toleranz oder gilt 0 Cent?
Varianten: A 1 Cent für Importe aus dem Altsystem, 0 Cent für neu erfasste Belege; B 1 Cent überall; C 0 Cent überall.
Empfehlung: A nach Rücksprache mit dem Steuerberater. Altdaten mit abweichender Rundung würden bei C abgewiesen und Nacharbeit erzeugen; neue Belege sollen exakt sein.
Risiko: Geld und Steuer (Vorsteuerausweis). Gate: G1. Technischer Stand: vorbereitet (Welle 21, AJ02), Frage AJ02-01; Variante A braucht einen Mandantenschalter.

### AJ30-09 Spaltenformat bei Importen (GAI-205) (Eigentümer Timo Müller)
Frage: Soll je Importvorlage ein Zahlenformat (deutsch oder englisch) wählbar sein? Mehrdeutige Werte wie 12.500 werden derzeit abgelehnt.
Varianten: A Format je Vorlage wählbar, Standard deutsch; B Ablehnung beibehalten; C automatische Erkennung je Datei.
Empfehlung: A. Die Ablehnung schützt vor Faktor-1000-Fehlern, ein Format je Vorlage vermeidet aber Handkorrekturen bei Zählerständen und MEA.
Risiko: C mittel (Fehlerkennung). Gate: keins. Technischer Stand: vorbereitet (Welle 21, AJ02), Frage AJ02-02.

### AJ30-10 Formatvorgabe Maklerportal (GAI-208) (Eigentümer Timo Müller)
Frage: Welche Formatvorgabe gilt bei FLOW für Preis, Fläche und Zimmer?
Varianten: A Vorgabe beim Anbieter einholen und umsetzen; B verlustfreie JSON-Zahl beibehalten.
Empfehlung: A, bis dahin B. Gate: keins. Technischer Stand: vorbereitet (Welle 21, AJ02), Frage AJ02-03.

### AJ30-11 Datenbankschutz für Geldtabellen (GAI-209, GAI-210, GAI-211) (Eigentümer Timo Müller, Steuerberater)
Frage: Welche Felder offener Posten bleiben änderbar, wirkt die Objektsperre zusätzlich als Datenbanktrigger, und gilt der Statusschutz für Zahlungsaufträge, Kautionsbewegungen und Sollstellungsposten als Produktstandard?
Varianten: A Stand Migration 0444 bestätigen und Objektsperre als Trigger ergänzen; B Stand 0444 bestätigen, Objektsperre nur in der Anwendung; C Schutz wieder lockern.
Empfehlung: A. Ein Schutz in der Datenbank verhindert, dass künftige Importe oder Direktzugriffe gesperrte Perioden ändern; die Korrektur mit offenem Buchungsdatum ist vorher mit dem Steuerberater festzulegen.
Risiko: Nachweis und Geld bei C hoch. Gate: G1 und G2. Technischer Stand: vorbereitet (Welle 21, AJ03), Fragen AJ03-01 bis AJ03-03.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Stand 0444 plus Trigger Objektsperre | mittel | gering |
| B Stand 0444 | keiner | mittel |
| C Lockern | gering | hoch |

### AJ30-12 Rundung Eigentümerabrechnung und WEG (GAI-213, GAI-614) (Eigentümer Geschäftsführung)
Frage: Wird ROUND_HALF_UP je Einzelwert in Eigentümerabrechnung, Wirtschaftsplan und Planänderung als Produktstandard bestätigt?
Varianten: A bestätigen; B HALF_EVEN beibehalten (Stand vor Welle 21).
Empfehlung: A, einheitlich mit dem übrigen System (siehe Vermerk AI17-13a). Gate: keins, Bezug G3, G4. Technischer Stand: vorbereitet (Welle 21, AJ01).

### AJ30-13 Restcent der Hausgeld-Monatsrate (GAI-214) (Eigentümer Geschäftsführung, Rechtsanwalt)
Frage: Wird die Differenz zwischen Jahresbetrag und zwölf Monatsraten im ersten oder letzten Monat ausgeglichen oder nur ausgewiesen?
Varianten: A `last_month`; B `first_month`; C `report_only` (Standard).
Empfehlung: A als Einschätzung, weil die Summe der Raten dann dem beschlossenen Jahresbetrag entspricht und die laufenden Raten gleich bleiben; ob dies mit dem Beschluss über den Wirtschaftsplan vereinbar ist, prüft der Rechtsanwalt.
Risiko: C lässt Cent-Differenzen in Sollstellungen stehen. Gate: G4. Technischer Stand: vorbereitet (Welle 21, AJ01), Frage AJ01-02; Speicherung je Mandant braucht Schemaänderung.

### AJ30-14 Rechtematrix schreibender Endpunkte mit Leserecht (GAI-301) (Eigentümer Timo Müller)
Frage: Erhalten die 17 zustandsändernden Endpunkte (Messdatenübertragung, Vertretungen der Mailfreigabe, Ticket- und Antwortvorlagen, SLA-Quittierung, Playbook, Wissensfeedback, Kalender-Token) eigene Schreibrechte mit Rollenmigration?
Varianten: A eigene update-Rechte, Rollenmigration so, dass bisherige Bearbeiterrollen sie erhalten; B nur Vertretungen der Mailfreigabe und Messdatenübertragung umstellen; C Status quo.
Empfehlung: A. Die Vertretung der Mailfreigabe berührt das Vier-Augen-Prinzip beim Versand, die Messdatenübertragung Abrechnungsgrundlagen; der Aufwand ist überschaubar.
Risiko: C hoch (Umgehung von Freigaben mit Leserecht). Gate: keins. Technischer Stand: nicht vorbereitet.

| Alternative | Aufwand | Risiko |
| --- | --- | --- |
| A Alle 17 | mittel | gering |
| B Teilweise | gering | mittel |
| C Status quo | keiner | hoch |

### AJ30-15 Rate-Limit über BFF und bei Redis-Ausfall (GAI-311, GAI-312) (Eigentümer Timo Müller, Sicherheit)
Frage: Vertraut die API X-Forwarded-For nur aus dem Stacknetz, und gilt für Token- und Code-Routen bei Redis-Ausfall ein Notzähler statt Fail open?
Varianten: A beide Schalter nach Test auf Staging aktivieren; B nur Weitergabe der Adresse; C Status quo.
Empfehlung: A. Ohne Adresse je Client kann ein einzelner Angreifer alle Anmeldungen blockieren; der Notzähler betrifft nur Token-Routen und gefährdet die Verfügbarkeit kaum.
Risiko: C hoch (Sperrung aller Anmeldungen, Durchprobieren von Token). Gate: keins. Technischer Stand: vorbereitet (Welle 21, AJ07), Fragen AJ07-01, AJ07-02; Limit je Route offen.

### AJ30-16 Zeitlimits und Worker-Aufteilung Celery (GAI-316, GAI-319) (Eigentümer Timo Müller, Betrieb)
Frage: Werden die konservativ gesetzten Zeitlimits je Taskklasse bestätigt, und wird ein zweiter Worker für ai, ocr und bank betrieben?
Varianten: A Limits nach Messung auf Staging bestätigen, zweiten Worker und Volume für die Beat-Zeitplandatei einrichten; B nur Limits; C Status quo.
Empfehlung: A. Lange KI- oder Bankläufe sollen Versand und Fristenaufgaben nicht blockieren; der Mehrbedarf an Speicher ist vorher auf dem Server zu prüfen.
Risiko: C mittel (Verzögerung von Fristenaufgaben, Doppelläufe). Gate: keins. Technischer Stand: vorbereitet (Welle 21, AJ11); compose.yaml unverändert.

### AJ30-17 Zahllauf-Vorschau speichern und Auszahlung ohne Beleg (GAI-401, GAI-402) (Eigentümer Geschäftsführung)
Frage: Werden gespeicherte Zahllauf-Vorschauen vor G2 gebraucht, und soll die Auszahlung ohne Rechnung eine Oberfläche erhalten?
Varianten: A Vorschau speichern als Maske jetzt, Auszahlung ohne Beleg erst mit G2 und Vier-Augen-Freigabe; B beides erst mit G2; C beides jetzt.
Empfehlung: B. Vor G2 entsteht kein Zahlungsfluss, der Nutzen der gespeicherten Vorschau ist gering; ein Geldabfluss ohne Beleg braucht ohnehin eine Freigaberegel der Geschäftsführung.
Risiko: C hoch (Geldabfluss ohne Beleg). Gate: G2. Technischer Stand: API vorhanden, keine Maske.

### AJ30-18 Masken für Versand und Freigaben hinter Gates (GAI-408, GAI-409, GAI-410) (Eigentümer Geschäftsführung)
Frage: Werden Mahnversand, PDF und Zustellung der Abrechnungen sowie die Freigabe der Kautionsabrechnung schon jetzt als gesperrte Masken gebaut?
Varianten: A Masken bauen, sichtbar gesperrt mit Hinweis auf das Gate; B erst mit Gateöffnung; C ohne Sperre.
Empfehlung: A. Der Abnahmeweg vor Gateöffnung wird testbar, ohne Rechtswirkung auszulösen; die Sperre bleibt serverseitig.
Risiko: C nicht zulässig (Rechtswirkung, Fristen, Auszahlung). Gate: G1 (Mahnung), G3 (Abrechnung, Kaution). Technischer Stand: API gesperrt vorhanden, keine Maske.

### AJ30-19 Einwilligungsregeln des Mandanten (GAI-414) (Eigentümer Timo Müller, Datenschutz)
Frage: Erhält consent-policy eine Einstellungsmaske, und welche Rechtsgrundlagen sind je Zweck hinterlegt?
Varianten: A Maske bauen, Inhalte erst nach Datenschutzberatung pflegen; B nur API; C Maske mit Vorbelegung.
Empfehlung: A. Eine Vorbelegung ohne Beratung wäre eine erfundene Rechtsgrundlage.
Risiko: Datenschutz. Gate: keins. Technischer Stand: nicht umgesetzt (AJ13).

### AJ30-20 Interne Kennungen in Oberflächentexten (GAI-425) (Eigentümer Timo Müller)
Frage: Bleiben Kennungen offener Entscheidungen in Klammern am Textende sichtbar?
Varianten: A Kennung in Klammern nur bei Betreiberentscheidungen (Stand AJ18); B ganz entfernen; C Stand vor Welle 21.
Empfehlung: A, weil der Betreiber den Bezug zur offenen Frage braucht, Mitarbeitende aber keine Pfade.
Risiko: gering. Gate: keins. Technischer Stand: vorbereitet (Welle 21, AJ18).

### AJ30-21 Löschfristen und Löschpfade je Datenart (GAI-501, GAI-503, GAI-504, GAI-505, GAI-520, GAI-522) (Eigentümer Timo Müller mit Rechtsanwalt und Steuerberater)
Frage: Welche Fristen, welcher Fristbeginn und welcher Löschweg gelten je Datenart (Kommunikation, Tickets, Portalzugänge, Ereignisprotokoll, Plattformbenutzer, Bankrohdaten, Bankverbindungen)?
Varianten: A V17-Matrix je Rechtsträger ausfüllen lassen, danach auto_propose je Datenart freigeben; B nur Kontakte freigeben, übrige Datenarten später; C ohne Fristen weiter.
Empfehlung: A in einem gebündelten Termin. Bis dahin löscht das System nichts automatisch; der Nachweis nach der Rechenschaftspflicht fehlt aber, solange keine Fristen festgelegt sind.
Risiko: Datenschutz hoch bei C. Gate: G5, Bezug G1, G3, G4. Technischer Stand: vorbereitet (Welle 21, AJ12, AJ15), Fragen AJ12-01, AJ15-04, Bezug V17, M20-08-Q7.

### AJ30-22 Umfang der Auskunft (GAI-506) (Eigentümer Timo Müller, Datenschutz)
Frage: Umfasst die Auskunft Tickets, Kommunikation, Dokumente, Portalkonto und Vertrags- und Zahlungsdaten, und wird ein Eingangsdatensatz für Anträge angelegt?
Varianten: A alle Quellen nach Beratung aktivieren, Eingangsdatensatz in der nächsten Migrationswelle; B Status quo.
Empfehlung: A. Gate: keins. Technischer Stand: vorbereitet (Welle 21, AJ13), Fragen AJ13-01, AJ13-03, Bezug AC07-01.

### AJ30-23 Verzeichnis der Verarbeitungstätigkeiten vor G1 (GAI-510) (Eigentümer Timo Müller)
Frage: Wird ein geklärter Verzeichniseintrag für alle aktiv genutzten Dienste Bedingung der G1-Checkliste?
Varianten: A ja; B nur informativ.
Empfehlung: A, weil die Auswertung vorhanden ist und den Datenschutznachweis vor produktiver Buchhaltung sichert. Gate: G1. Technischer Stand: vorbereitet (Welle 21, AJ13), Frage AJ13-02, Bezug AE32-01.

### AJ30-24 Nummernfolge der B-Regeln (GAI-519) (Eigentümer Timo Müller)
Frage: B10 bis B14 frei lassen oder B15 umbenennen?
Empfehlung: frei lassen, keine Umbenennung im Code. Risiko: keins. Gate: keins. Technischer Stand: vorbereitet (Welle 21, AJ15), Frage AJ15-01.

### AJ30-25 finAPI Prüfplan (GAI-521) (Eigentümer Timo Müller)
Frage: Wird der Prüfplan mit Testzugang (Vertrag, Zustimmungsablauf, Update, Trennen, Mandator) als Abnahmeschritt vor G1 übernommen, und gilt die Aufteilung M11-42a und M11-42b?
Empfehlung: ja, beides; ohne Testzugang bleiben Ablaufdatum und Trennen unbestätigt. Gate: G1 (Bankabruf). Technischer Stand: vorbereitet (Welle 21, AJ15), Frage AJ15-05, Bezug M11-40 bis M11-44.

### AJ30-26 Wiederherstellung des zweiten Faktors (GAI-603) (Eigentümer Timo Müller, Sicherheit)
Frage: Wiederherstellungscodes, Rücksetzung durch zwei Administratoren oder beides?
Varianten: A Rücksetzung durch zwei Personen (Maske vorhanden) plus einmalig angezeigte Wiederherstellungscodes; B nur Rücksetzung; C nur Codes.
Empfehlung: A. Codes vermeiden Betriebsaufwand, die Rücksetzung mit zweiter Person deckt den Verlust der Codes ab.
Risiko: Sicherheit mittel. Gate: keins. Technischer Stand: vorbereitet (Welle 21, AJ08), Schalter Admin-Rücksetzung Standard aus, Frage AI09-01.

### AJ30-27 Tageszählung Verzugszins (GAI-606) (Eigentümer Geschäftsführung, Rechtsanwalt)
Frage: Welche Tageszählung gilt für Verzugszinsen als Nebenforderung?
Varianten: Tageszählungen act_365_fixed und act_act sind als Einstellung vorhanden; Standard unverändert.
Empfehlung: Festlegung durch den Rechtsanwalt; bis dahin Standard beibehalten. Keine Einschätzung zur Rechtslage in dieser Vorlage.
Risiko: Geld und Recht (Höhe der Nebenforderung). Gate: G1. Technischer Stand: vorbereitet (Welle 21, AJ04), Frage AI03-01.

### AJ30-28 Stichtagsabfrage für Personen (GAI-607) (Eigentümer Timo Müller)
Frage: Erhält party Gültigkeitsspalten valid_from und valid_to für as_of-Abfragen?
Varianten: A ja, mit Migration, sobald ein konkreter Fachfall (etwa Rechtsnachfolge) es verlangt; B nein, Historie über Beziehungen mit Gültigkeit abbilden.
Empfehlung: B bis ein Fachfall belegt ist; Regel 2 erlaubt keine Felder auf Vorrat.
Risiko: gering. Gate: keins. Technischer Stand: nicht vorbereitet.

### AJ21-01 Rechtematrix für schreibende Routen mit Leserecht (GAI-301)
Frage: Reichen die bestehenden Schreibrechte (`communication:update`, `sla:update`, `ai:create`) oder sollen eigene Rechte und eine Rollenmigration folgen? Bleibt das Kalender-Abo als persönlicher Token mit Leserecht?
Varianten: A bestehende Rechte (umgesetzt, keine neuen Rollen); B eigene Rechte je Aktion mit Rollenmigration.
Empfehlung: A, B nur bei konkretem Bedarf einer Rolle, die quittieren, aber nicht verwalten soll.
Risiko: gering. Gate: keins. Technischer Stand: A umgesetzt, Test tests/unit/test_aj21_write_with_read_permission.py.
