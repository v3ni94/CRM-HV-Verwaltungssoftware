# Fachliche Abnahmefälle D01 bis D58

**Status:** Testanforderungen, keine ausgeführten Softwaretests.

Quelle: `docs/MASTER-PROMPT.md`, Anhang D (Version 2.0 Final, Stand 23.09.2026). Die Spalten „Eingabe und ausdrückliche Annahmen“, „Erwartetes Ergebnis / verbotener Fehler“, „Zu prüfender Fall“ und „Mindestkriterium“ sind wörtlich übernommen. Ergänzt sind Meilenstein, Freigabestufe, Konfliktbezug und Status. Die Zuordnung ist aus Abschnitt 18 und Anhang E abgeleitet (Entscheidung der Projektleitung vom 23.09.2026). Bei Abweichungen zwischen dieser Datei und dem Master-Prompt gilt der Master-Prompt.

Wortlaut der Statuszeile aus Anhang D: Zahlen sind bewusst einfache, eigenständig nachrechenbare Modellfälle. Genannte fachliche Annahmen sind Bestandteil des Falls; sie ersetzen nicht die Prüfung realer Vertrags-/Beschlussunterlagen. Fach-/Rechtsverantwortliche bestätigen die Umsetzung und Sonderfälle vor Produktivfreigabe. Technische Testdateien, Frameworks und Schemaabbildung bestimmt Claude im bestehenden Stack.

Ein Testfall darf nicht nachträglich an das Ist-Ergebnis angepasst werden (Anhang D.3). „ohne eigene Stufe“ bedeutet: der Fall gilt als Querschnittsanforderung in jedem betroffenen Meilenstein.

## D.1 Rechenfälle

| ID | Bezeichnung | Eingabe und ausdrückliche Annahmen | Erwartetes Ergebnis / verbotener Fehler | Meilenstein | Freigabestufe | Konfliktbezug (Anhang E) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D01 | WEG-Spitze/Rückstand | Kostenanteil 3.000,00 EUR; beschlossene, kostenbezogene Soll-Vorschüsse 2.800,00 EUR; darauf gezahlt 2.500,00 EUR. Kein Eigentümerwechsel, keine Rücklagen-/Sonderumlagenkomponente, keine sonstige Korrektur. Wirksame einschlägige Beschlussgrundlage wird im Test später gesetzt. | Abrechnungsspitze 200,00 EUR; bestehender Vorschussrückstand 300,00 EUR; nach einschlägiger Beschlusswirkung Gesamtbelastung aus beiden 500,00 EUR. Verboten: neue Abrechnungsforderung 500,00 EUR plus nochmals alter Rückstand 300,00 EUR. | M24 | G4 | keiner | nicht ausgeführt |
| D02 | WEG-Anpassung/Guthaben | Kostenanteil 2.500,00 EUR; Soll-Vorschüsse 2.800,00 EUR; gezahlt 2.500,00 EUR; im Übrigen wie D01. | Abrechnungsanpassung −300,00 EUR, Vorschussrückstand 300,00 EUR getrennt. Rechnerisch 0,00 EUR Gesamtübersicht, aber keine automatische Auszahlung von 300,00 EUR oder unbegründete Löschung der Altforderung. Rechtlich zulässige Verrechnung eigenständig prüfen. | M24 | G4 | keiner | nicht ausgeführt |
| D03 | Tatsächliche Rücklage | Anfang 20.000,00 EUR; Soll-Zuführung 6.000,00 EUR, tatsächlich eingegangen 4.500,00 EUR; aus Rücklage finanzierte Mittelverwendung 3.000,00 EUR; der Rücklage rechtmäßig zugeordneter Nettozins 100,00 EUR; keine weiteren Bewegungen. | Tatsächlicher Rücklagenbestand 21.600,00 EUR; offene Beiträge 1.500,00 EUR separat, nicht verfügbare Liquidität. Bestand nicht auf 23.100,00 EUR aufblasen. Bank-/Mittelzuordnung zusätzlich abstimmen. | M24 | G4 | keiner | nicht ausgeführt |
| D04 | Interner Banktransfer | Gemeinschaft hat auf Bank A 10.000,00 EUR und auf Bank B 20.000,00 EUR. Transfer 1.000,00 EUR von A nach B, keine Gebühr. Beide Bankauszüge werden importiert. | A 9.000,00 EUR, B 21.000,00 EUR, Gesamtsumme weiterhin 30.000,00 EUR. Keine Ausgabe/Einnahme und keine zweite Wirkung des Transfers. Nicht automatisch eine neue Rücklagenzuführung. | M10/M11 | G1 | E07 | nicht ausgeführt |
| D05 | Echte Gleichzahlungen | Zwei durch ihre Bankdatensätze unterscheidbare tatsächliche Zahlungen von je 400,00 EUR, identischer Zahler, Tag und Verwendungszweck. Anschließend beide Originaldatensätze nochmals importieren. | Zunächst zwei wirtschaftliche Zahlungen, zusammen 800,00 EUR; nach Wiederimport weiterhin 800,00 EUR, weder 400,00 EUR noch 1.600,00 EUR. | M11 | G1 | E07 | nicht ausgeführt |
| D06 | Zahlung nicht bei Export | Freigegebene Rechnung 1.190,00 EUR. Zahlungsdatei exportiert, dann eingereicht, später tatsächlich ausgeführt. Keine sonstigen Zahlungsvorgänge. | Bei Export/Einreichung bleibt Zahlungsverbindlichkeit offen und Bankbestand unverändert; Ausführung/Nachweis führt einmalig zum Ausgleich 1.190,00 EUR. Doppelte Rückmeldung erzeugt keinen zweiten Ausgleich. | M15 | G2 | E09 | nicht ausgeführt |
| D07 | Teil-/Überzahlung | Fällige Forderung 1.000,00 EUR; erste zugeordnete Zahlung 600,00 EUR; zweite tatsächliche Zahlung 450,00 EUR. Eindeutiger Schuldner und Tilgungszweck. | Nach Zahlung 1 Rest-OP 400,00 EUR; danach Forderung ausgeglichen und 50,00 EUR gesondertes Guthaben. Guthaben nicht als zusätzlicher Ertrag. Folgefälle Rückgabe/Erstattung separat. | M10/M12 | G1 | keiner | nicht ausgeführt |
| D08 | Centverteilung | 100,00 EUR, drei identische Verteilungsgewichte, keine abweichende Vorschrift. Produktstandard gleicht den Rest nach stabiler vorab bestimmter Zuordnung aus. | Ein Anteil 33,34 EUR, zwei Anteile 33,33 EUR, Summe 100,00 EUR. Umordnen der Bildschirmzeilen darf nicht den begünstigten/belasteten Datensatz wechseln. | M10 | G1 | E08 | nicht ausgeführt |
| D09 | Heizkostenüberleitung | Modellfall eines rechtlich freigegebenen Brennstoffbestandsverfahrens: Zahlung für Brennstoff 10.000,00 EUR; in der Periode verbrauchter zurechenbarer Brennstoff 8.000,00 EUR; sonst keine Heizkosten. | Gesamtgeldfluss zeigt Zahlung 10.000,00 EUR; Verbrauchsverteilung 8.000,00 EUR; Unterschied 2.000,00 EUR wird erklärt, nicht weggerechnet. Freigabe P02 erforderlich; keine Behauptung einer universellen Formel für jedes Heizsystem. | M17/M24 | G3/G4 (Freigabe P02) | keiner | nicht ausgeführt |
| D10 | CO₂-Stufengrenze | Volljähriger Wohngebäude-Regelfall nach § 5/Anlage, keine Ausnahmen oder späteren Sonderregeln; spezifischer Ausstoß 12,0 kg CO₂/m²/Jahr, CO₂-Kosten 100,00 EUR. | Stufe 12 bis unter 17: 90,00 EUR Mieteranteil, 10,00 EUR Vermieteranteil. Vergleichsfall mit freigegebenem spezifischem Wert unter 12: 100/0. Gesetzliche Berechnung/Rundung des Eingangswerts separat testen; kein vorzeitiges Abrunden zur besseren Stufe. | M17 | G3 | keiner | nicht ausgeführt |
| D11 | Unterjährige Jahresvollständigkeit | Zu übernehmendes Kalenderjahr: 400,00 EUR belegte Ausgaben vor Übernahme und 600,00 EUR danach, beide nach fachlich freigegebener Zuordnung abrechnungsrelevant. Anfangsbestand wird zusätzlich importiert. | Jahresausgaben 1.000,00 EUR. Anfangsbestand ist keine zusätzliche Ausgabe; Daten vor Übernahme fehlen nicht. Belegkette für alle 1.000,00 EUR verfügbar. | M8/M10 | G1 | E10 | nicht ausgeführt |
| D12 | Abschlag/Schlussrechnung | Gesamte vereinbarte Leistung 5.950,00 EUR brutto; bereits ordnungsgemäß abgerechneter und bezahlter Abschlag 2.380,00 EUR; Schlussrechnung weist beide korrekt aus; keine weiteren Besonderheiten. | Verbleibende Zahlungsverpflichtung 3.570,00 EUR; Leistungssumme insgesamt 5.950,00 EUR, nicht 8.330,00 EUR. Je maßgeblichem Rechenwerk Buchung/Steuer/Zahlung gesondert testen. | M14 | G1 | keiner | nicht ausgeführt |

## D.2 Prozess-, Rechtsgrund- und Negativtests

| ID | Bezeichnung | Zu prüfender Fall | Mindestkriterium | Meilenstein | Freigabestufe | Konfliktbezug (Anhang E) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D13 |  | WEG-Ergebnis intern bestätigt, aber kein wirksamer Beschluss erfasst | Keine neue nach § 28 Abs. 2 beschlussabhängige Forderung und keine damit begründete Lastschrift. | M24 (Schema M5) | G4 | E03 | nicht ausgeführt |
| D14 |  | Ergebnisversion nach erfasster Beschlussfassung geändert | Beschluss wird nicht automatisch auf andere Zahlen umgehängt; Differenz und erneuter rechtlicher Entscheidungsschritt sichtbar. | M24 (Schema M5) | G4 | E03 | nicht ausgeführt |
| D15 |  | Alter Eigentümer mit offenen Vorschüssen; neuer Eigentümer; spätere Abrechnung | Im gewöhnlichen Erwerbsfall ohne Sonderhaftung: alter Vorschussrückstand beim bisherigen Schuldner; Abrechnungsspitze beim rechtlich maßgeblichen Eigentümer zur Beschlussfassung. Kaufvertragsausgleich getrennt; P01-Regelstand und Sonderfälle ausdrücklich freigeben. | M5 Schema, M24 Logik | G4 | E02 | nicht ausgeführt |
| D16 |  | Nutzen-/Lastenwechsel weicht von rechtlichem Eigentumswechsel ab | Kein stilles Gleichsetzen der Daten; Außen-/Innenverhältnis und jeweiligen Zeitpunkt ausweisen. | M5 | G4 | E02 | nicht ausgeführt |
| D17 |  | Eine Person besitzt zwei Einheiten; eine Einheit gehört mehreren Personen | Zulässige Partei-/Stimmrechtszuordnung ohne doppelte Kopfstimme oder doppelte Forderung; Gemeinschaftsregel berücksichtigen. | M5/M25 | G4 | E02 | nicht ausgeführt |
| D18 |  | Kostenverteilung für einzelne Untergemeinschaft ohne belegte Grundlage | Keine endgültige Abrechnung nur wegen eines angelegten Filters; Prüfhinweis und betroffener Freigabestopp. | M24 | G4 | keiner | nicht ausgeführt |
| D19 |  | Rücklagenzuführung beschlossen, aber unbezahlt; Rücklagenkonto weist anderen Stand aus | Soll, Ist, Bankanlage und Rückstand separat; Differenz erklärt statt automatische Ausgleichsbuchung. | M24 | G4 | keiner | nicht ausgeführt |
| D20 |  | Sonderumlage wird in mehreren Raten eingezogen und später teilweise erstattet | Zweck, Soll/Ist, Verwendung, Fälligkeiten und Erstattungsgrund bleiben erhalten; keine doppelte Kostenerfassung. | M13/M24 | G4 | keiner | nicht ausgeführt |
| D21 |  | Vermietetes Wohnungseigentum ohne abweichenden Miet-Verteilungsschlüssel | § 556a Abs. 3 und Billigkeitsprüfung im Regelwerk; nicht automatisch allgemeine m²-Regel verwenden. | M17 | G3 | keiner | nicht ausgeführt |
| D22 |  | Mischrechnung Verwaltung/Instandsetzung/laufender Betrieb | Nicht umlagefähige Anteile bleiben aus der Wohnraum-Betriebskostenbelastung; Aufteilung belegt. | M17 | G3 | keiner | nicht ausgeführt |
| D23 |  | Mietabrechnung wird kurz vor Fristende erzeugt, gelangt aber nicht rechtzeitig zum Empfänger | Erstellung nicht als Zugang werten; Nachforderungs-/Ausnahmeprüfung und Alternativprozess. | M17 | G3 | keiner | nicht ausgeführt |
| D24 |  | Mietvorauszahlungen offen, Abrechnung wird erteilt | Kein doppelter wirtschaftlicher Anspruch; Behandlung nach fachlich bestätigter Abrechnungsreife-/Vorschussregel. | M17 | G3 | keiner | nicht ausgeführt |
| D25 |  | Nutzerwechsel im Winter mit vorhandener Zwischenablesung | Verbrauchs-/Grundanteile nach passenden HeizkostenV-Regeln; keine pauschale Ganzjahres-Tagesverteilung. | M17 | G3 | keiner | nicht ausgeführt |
| D26 |  | Pflichtige Verbrauchsinformation, Portal noch nicht entwickelt | Nachgewiesener funktionierender Ersatzprozess; kein Verweis auf spätere Phase als Erfüllung. | M17 | G3 (Ersatzprozess H03) | keiner | nicht ausgeführt |
| D27 |  | Gemischte/abweichende CO₂-Sachverhalte, Selbstversorgung, fehlende Lieferangaben | Richtige Regelgruppe oder ausdrücklicher Prüfstatus; keine erfundenen Emissionswerte oder Nullkosten. | M17 | G3 | keiner | nicht ausgeführt |
| D28 |  | Neue, bereits veröffentlichte Rechtsregel gilt erst in späterem Zeitraum | Kein Eingriff in 2026-/Alt-Abrechnungen; Versions-/Stichtagsauswahl getestet. | M17 | G3 | keiner | nicht ausgeführt |
| D29 |  | Eigentümer beantragt GdWE-Unterlagen außerhalb eigener Einzelabrechnung | Gesetzlich gedeckter Zugriff nicht pauschal durch eigenen Vertragsfilter blockiert. | M21 (Grundlage M6) | G3/G4 | E06 | nicht ausgeführt |
| D30 |  | Derselbe Nutzer fordert fremde GdWE/private SEV-Akte ohne Rechtsgrund | Zugriff auch über API, Download, Suche, RAG und Sammel-Export verweigert. | M21 (Grundlage M6) | G3/G4 | E06 | nicht ausgeführt |
| D31 |  | Mieter beantragt notwendige Abrechnungsbelege mit Angaben Dritter | Zweckbezogene Einsicht/erforderliche Schwärzung, keine pauschale Vollverweigerung oder Vollfreigabe fremder Akten. | M21 | G3 | E06 | nicht ausgeführt |
| D32 |  | Beirat prüft nur ausgewählte Belege | Bericht zeigt Stichprobe, Anzahl/Wert, offene/ungeprüfte Positionen; keine Vollprüfungsbehauptung. | M25 | G4 | E14 | nicht ausgeführt |
| D33 |  | Rechnung nach Beiratsprüfung geändert | Betroffene Prüfung als veraltet/eingeschränkt markieren; kein unverändert grüner Gesamtstatus. | M25 | G4 | E14 | nicht ausgeführt |
| D34 |  | Lesebestätigung oder Ablauf einer Portal-Einladung | Keine automatische Anerkennung, kein Verzicht und keine ohne Grundlage ausgelöste Rechtsfrist. | M21 | G3/G4 | keiner | nicht ausgeführt |
| D35 |  | Zahlbetrag oder Empfänger-IBAN nach Zahlungsfreigabe geändert | Alte Freigabe unwirksam für neuen Zahlungsstand; erneute erforderliche Prüfung/Freigabe. | M14/M15 | G2 | E09 | nicht ausgeführt |
| D36 |  | Ein Nutzer versucht, Zahlungsfreigabe mit eigener zweiter Identität zu umgehen | Organisatorisch/technisch definierte unabhängige Freigabe kontrollieren; kein scheinbares Vier-Augen-Prinzip. | M15 | G2 | E09 | nicht ausgeführt |
| D37 |  | Bank lehnt Auftrag ab oder führt nur Teile aus | Nur tatsächlich bestätigte Teilbeträge ausgeglichen; Fehler und Restposten nachvollziehbar. | M15 | G2 | E09 | nicht ausgeführt |
| D38 |  | Bereits zugeordnete Zahlung wird zurückgegeben | Ursprüngliche Zuordnung nachvollziehbar korrigiert; OP wieder richtig offen; Gebühren nur belegt/geprüft. | M15 | G2 | E09 | nicht ausgeführt |
| D39 |  | Eindeutige Tilgungsbestimmung widerspricht freier Kontenpriorität | Rechtskonforme Zuordnung/Prüfung statt stiller Anwendung beliebiger interner Reihenfolge. | M12 | G1 | keiner | nicht ausgeführt |
| D40 |  | Mahnung ohne nachgewiesenen Verzug; ungeeigneter Zins-/40-EUR-Standard | Keine automatische unberechtigte Zusatzforderung; Anspruchsart und Beteiligte prüfen. | M16 | G1 | keiner | nicht ausgeführt |
| D41 |  | Formal valide E-Rechnung über nicht erbrachte Leistung | Technisch valide, sachlich beanstandet; keine automatische Zahlungsfreigabe. | M14 | G1 | keiner | nicht ausgeführt |
| D42 |  | Hybridrechnung: XML und PDF widersprechen sich | Widerspruch sichtbar; strukturierte maßgebliche Daten und relevante Zusatzinformationen erhalten; Zahlungsprüfung statt stiller Auswahl. | M14 | G1 | keiner | nicht ausgeführt |
| D43 |  | Rechnung wird ausschließlich als OCR-Text gespeichert; Original soll gelöscht werden | Aufbewahrungs-/Beweissicherung verhindert unzulässigen Verlust; OCR/JSON ersetzt nicht Original. | M6/M14 | G1 | E05 | nicht ausgeführt |
| D44 |  | §-35a-Anteil fehlt oder ist nur KI-Schätzung | Keine als belegt ausgewiesene Fantasiesumme; Nachforderung/Prüfung. | M14/M17 | G3 | keiner | nicht ausgeführt |
| D45 |  | Steuerliche Option/Gewerbequote ohne passenden Steuerstatus | Keine automatische Vorsteuer-/USt-Buchung nach bloßer Flächenbelegung; Freigabe/Sperre. | M13/M14/M17 | G1/G3 | keiner | nicht ausgeführt |
| D46 |  | Laufende Aufbewahrung/Sperre gegen Löschwunsch oder Import-Rücknahme | Rechtmäßig gesperrte Unterlagen bleiben erhalten; Ablehnung/Teillöschung begründet und protokolliert. | M6/M7 | G1 | E05 | nicht ausgeführt |
| D47 |  | Wiederherstellung eines Backups nach bereits erfolgter rechtmäßiger Löschung | Wiederherstellungsprozess berücksichtigt Lösch-/Sperrentscheidungen, ohne Beweisdaten unzulässig zu zerstören. | M9 | G1 | E05 | nicht ausgeführt |
| D48 |  | Gleichzeitiger Sollstellungslauf, Retry nach Abbruch und doppelter API-Aufruf | Nur eine vollständige wirtschaftliche Wirkung; keine halben Buchungen oder doppelten OP. | M10/M13 | G1 | E15 | nicht ausgeführt |
| D49 |  | Historischer OP-Stichtag wird nach späterer Zahlung/Storno erneut abgefragt | Derselbe historische Bestand wie zum Stichtag; spätere Ereignisse werden nicht rückwirkend eingerechnet. | M10 | G1 | E15 | nicht ausgeführt |
| D50 |  | Nutzer kann nur lesen, versucht Finanzänderung über Massenendpunkt/Job/API-Key | Berechtigung und Freigabe serverseitig wirksam; UI-Verstecken allein genügt nicht. | ab M2 in jedem Meilenstein | ohne eigene Stufe | E12 | nicht ausgeführt |
| D51 |  | Unbekannte Rechts-/Verteilungsregel wird als Konfiguration eingetragen | Keine automatische Produktivfreigabe; Quelle, Geltung, Entscheidung und Tests erforderlich. | M12 und jede Regelkonfiguration | ohne eigene Stufe | E04 | nicht ausgeführt |
| D52 |  | Umstellung im Parallelbetrieb mit altem Schreibadapter | Genau ein führender Geldprozess je Scope; keine Doppelmahnung/-lastschrift aus beiden Systemen. | M8/M10 | G1 | E10 | nicht ausgeführt |
| D53 |  | Virtuelle Versammlung ohne gültige Grundlage/mit falscher Mehrheit oder technischer Störung | Regel- und Rechteprüfung; dokumentierter Umgang mit Ausfall, nicht einfach erfolgreiches Videotreffen behaupten. | M25 | G4 | keiner | nicht ausgeführt |
| D54 |  | Streit/Anfechtung gegen Beschluss wird erfasst | Kein pauschales sofortiges Löschen/Ausbuchen; rechtlicher Wirksamkeitsstatus und tatsächlich nötige Folgeschritte unterscheiden. | M24/M25 | G4 | E03 | nicht ausgeführt |
| D55 |  | Steuerberater-/Prüfexport und anschließende Auswertung | Buchungen, Schlüssel, Historie, Freigaben und Originalbelege nachvollziehbar verbunden; keine nur optisch schöne PDF-Sammlung. | M18 | G1 | keiner | nicht ausgeführt |
| D56 |  | Private Kaution und GdWE-/Miet-Bankmittel nebeneinander | Kaution bleibt ihrer Vermögenssphäre/Zinszuordnung zugeordnet; kein Zugriff als frei verfügbares Objektgeld. | M4/M5/M10 | G1 | E01 | nicht ausgeführt |
| D57 |  | KI-Ausgabe enthält Anweisung zu neuer IBAN, eigener Freigabe oder Datenexport | Keine Ausführung aus Dokumenttext/Modellantwort; nur geprüfter zulässiger Fachworkflow. | M7/M12/M14 | ohne eigene Stufe | E04 | nicht ausgeführt |
| D58 |  | Gebührenrechnung der Verwaltung für SEV | Zahler, Rechnungsempfänger und Zahlungsempfänger korrekt unterschieden; kein irrtümlicher Honorarfluss an Eigentümer durch missverständliches `recipient`-Feld. | M5/M13 | G1 | E13 | nicht ausgeführt |

## D.3 Abnahmeprotokoll

Wortlaut Anhang D.3: Pro Test mindestens Kennung, geprüfte Regelversion, fachliche Annahmen, anonymisierte Eingaben, erwartetes Ergebnis, tatsächlich beobachtetes Ergebnis, Differenz, ausgeführter Testbefehl bzw. manueller Prüfablauf, Softwarestand, Prüfer und Status. Ein Testfall darf nicht nachträglich nur deshalb an das Ist-Ergebnis angepasst werden, damit er besteht. Fachlich begründete Änderungen brauchen dokumentierte neue Soll-Ergebnisse und erneute Prüfung.

Vorlage je Testausführung (kopieren und ausfüllen):

| Feld | Eintrag |
| --- | --- |
| Kennung (D-Nr.) | |
| Geprüfte Regelversion | |
| Fachliche Annahmen | |
| Anonymisierte Eingaben | |
| Erwartetes Ergebnis | |
| Tatsächlich beobachtetes Ergebnis | |
| Differenz | |
| Ausgeführter Testbefehl bzw. manueller Prüfablauf | |
| Softwarestand (Commit, Version) | |
| Prüfer | |
| Datum (TT.MM.JJJJ) | |
| Status (bestanden, nicht bestanden, nicht ausgeführt) | |
