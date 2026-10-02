# Buchhaltung

## Zweck und Freigabestufen

Der Bereich Buchhaltung (Menü Finanzen) führt je Rechtsträger einen Buchungskreis mit
Kontenrahmen, Journal, Saldenliste und offenen Posten, erzeugt Sollstellungen aus den
Verträgen, gleicht Bankumsätze ab, bereitet Mahnungen vor und begleitet Eingangsrechnungen
bis zum Zahlungsauftrag.

Im Parallelbetrieb bleibt Immoware24 das führende System. Alle Buchungen der Plattform
sind bis zur jeweiligen Freigabestufe nicht die führende Buchhaltung; die Freigabestufen
gelten je Mandant und sind standardmäßig geschlossen:

| Stufe | Gibt frei | Bis dahin |
| --- | --- | --- |
| G1 | produktive Buchführung (Plattform als führendes System) | Buchungen sind Parallelbuchungen; Mahnläufe lassen sich nicht freigeben; Mahnschreiben werden nicht versendet; die Startseite zeigt keine Geldkennzahlen |
| G2 | Zahlungsauslösung | Zahlungsaufträge werden freigegeben, aber keine Zahlungsdatei erzeugt; kein Export, keine Einreichung |
| G3 | Mietabrechnungen und Eigentümerabrechnungen an Empfänger | Ausgabe als PDF und Versand gesperrt, Mieterhöhungsschreiben nicht versendbar |
| G4 | WEG-Abrechnungen | Ausgabe und Buchung von Hausgeldabrechnungen gesperrt |
| G5 | Fremdmandanten | nur eigene Gesellschaften |

Ein Hinweis auf der Seite Buchhaltung (Parallelbetrieb: Führend ist weiterhin Immoware24)
erinnert daran. Die Freigabe einer Stufe ist eine Betreiberentscheidung nach den
dokumentierten Voraussetzungen; sie wird nicht in der Oberfläche erteilt.

## Buchungskreis je Rechtsträger

Die Übersicht listet je Buchungskreis den Rechtsträger, das führende System (Immoware24
oder Plattform) und Festgeschrieben bis. Jeder Rechtsträger (GdWE, Eigentümer,
SEV-Eigentümer, Verwalter) hat einen eigenen Buchungskreis; Forderungen, Bankguthaben,
Rücklagen und Kautionen gehören immer dem Rechtsträger, nie automatisch der Verwaltung.

Buchungskreise werden über die Schnittstelle aus einer Kontenrahmen-Vorlage angelegt (ein
Entwurf nach dem Kontenrahmen der Spezifikation steht bereit und wird vom Betreiber
freigegeben). Debitorenkonten lassen sich aus den Verträgen übernehmen; das Erlöskonto je
Zahlungsart (zum Beispiel Miete, Hausgeld) wird je Buchungskreis zugeordnet und ist
Voraussetzung für die Sollstellung.

Die Vorlage enthält seit dem 26.09.2026 zusätzlich die Erlöskonten der Mietverwaltung als
Vorschlag: 060300 Miete, 060400 Betriebskostenvorauszahlung, 060500
Heizkostenvorauszahlung, 060600 Garagenmiete, 060700 Stellplatzmiete und 060800 Sonstige
Erlöse. Sie gelten für Buchungskreise von Eigentümern und SEV-Eigentümern, nicht für
Gemeinschaften. Jedes dieser Konten trägt das Prüfkennzeichen Entwurf mit dem Vermerk
"Freigabe durch Steuerberatung offen"; das Kennzeichen erscheint in der Kontenliste des
Buchungskreises. Es ist ein Hinweis auf die ausstehende Prüfung, keine Sperre. Umlagefähigkeit,
Abrechnungsart und Umsatzsteueroption sind bei diesen Konten nicht gesetzt und werden mit
der Steuerberatung festgelegt. Das erneute Anlegen der Vorlage ergänzt nur fehlende Konten
und verändert vorhandene Zeilen nicht. Ein Konto für Kautionen als Verbindlichkeit ist nicht
vorbelegt, weil der Kontenrahmen der Spezifikation dafür keinen Nummernbereich vorsieht;
Mietforderungen laufen über die Debitorenkonten je Vertrag.

Die Kostenkonten der Vorlage sind seit dem 26.09.2026 als Entwurf nach der
Betriebskostenverordnung vorbelegt: Konten, die einer Betriebskostenart des Katalogs
entsprechen (zum Beispiel Hausmeister, Reinigung, Gartenpflege, Winterdienst, Allgemeinstrom,
Brennstoff, Wartung Heizung, Zählermiete, Wasser, Abwasser), sind als umlagefähig mit der
Abrechnungsart Betriebskosten eingeordnet. Der übliche Schlüssel steht als Vorschlag an der
Vorlagenzeile: Wohnfläche für die meisten Kostenarten, Verbrauch für Heizung, Warmwasser und
Wasser, sofern Zähler vorhanden sind; ohne Zähler ist der Schlüssel je Objekt festzulegen.
Heizungsreparaturen sind als nicht umlagefähig eingeordnet. Das Konto Rauchwarnmelder bleibt
ohne Einordnung, weil es Miete und Wartung mischt. Die Umsatzsteueroption ist bei keinem
Kostenkonto gesetzt. Jede vorbelegte Zeile trägt das Prüfkennzeichen Entwurf mit dem Vermerk
"Freigabe durch Steuerberatung offen". Das erneute Anlegen der Vorlage füllt nur Felder, die
noch nicht gesetzt sind, und verändert eigene Einträge nicht; bestehende Buchungskreise
bleiben unverändert. Die Vorbelegung ersetzt nicht die Einordnung je Objekt: die
Betriebskostenabrechnung prüft weiterhin je Position, ob das Konto im Buchungskreis als
umlagefähig eingeordnet ist, und der Verteilungsschlüssel wird je Objekt erfasst. Die
Zuordnungstabelle steht in Regel M10-02.

Die Detailseite eines Buchungskreises zeigt:

- Saldenliste zum Tagesdatum mit Konto, Soll, Haben und Saldo.
- Offene Posten mit Zahlungsart, Betrag, Fälligkeit, Konto, offenem Rest und Summe offen.
- Journal mit Nr., Buchungstag, Text und Status (Entwurf, gebucht, storniert).

Buchungssätze entstehen als Entwurf und werden mit festgeschriebener Nummer gebucht; ein
gebuchter Satz wird nie geändert oder gelöscht, Korrekturen erfolgen nur per Storno.
Anfangsbestände prüft eine zweite Person. Festschreiben bis Datum sperrt den Zeitraum. Eine
Konsistenzprüfung (Summen, Bankabstimmung, offene Posten) steht über die Schnittstelle
bereit.

## Sollstellung

Buchhaltung, Sollstellungen: Monat wählen, Vorschau erstellen. Die Vorschau listet je
Vertrag Zahlungsart, Betrag, Fälligkeit, Status und Hinweis:

| Status | Bedeutung |
| --- | --- |
| bereit | wird gebucht |
| manuell | kein monatlicher Betrag oder ohne freigegebene Regel (Zeitanteil, abweichendes Intervall, Werktagsregel, Umsatzsteuer); von Hand zu erfassen |
| blockiert | Voraussetzung fehlt, zum Beispiel kein Erlöskonto oder kein Buchungskreis |

Die Schaltfläche Sollstellungen buchen nennt Anzahl und Summe der bereiten Posten (zum
Beispiel 12 Sollstellungen buchen (6.480,00 EUR)) und verlangt eine Bestätigung. Ein Lauf je
Monat; gebuchte Sollstellungen werden nur per Storno des Laufs korrigiert. Der Lauf lässt
sich auf ein Objekt oder einen Vertrag eingrenzen (Schnittstelle).

Frühere Läufe laden zeigt alle Läufe des gewählten Monats; Öffnen lädt die Posten. Jeder
Posten nennt seine Grundlage (gültig ab, Vertragsversion). Wurde ein Betrag nach der Buchung
geändert, erscheint ein manueller Posten mit der Differenz zur gebuchten Sollstellung; er wird
nicht gebucht, die Korrektur erfolgt per Storno des Laufs und neuer Sollstellung. Auf Wunsch
erstellt das System am 1. des Monats um 05:00 eine Vorschau (Mandanteneinstellung, Standard
aus); gebucht wird immer von Hand.

## Offene Posten und Bankabgleich

Offene Posten entstehen aus Sollstellungen und gebuchten Eingangsrechnungen und werden
durch bestätigte Bankumsätze ausgeglichen. Der Bankabgleich (Menü Bank) zeigt Umsätze aus
CAMT.053-Dateien oder finAPI, schlägt Zuordnungen mit Begründung vor und bucht nur nach
Bestätigung; ohne passenden Posten wird ein Umsatz mit Begründung ignoriert. Bankregeln
für die Automatik werden vorgeschlagen, von einer zweiten Person fachlich freigegeben und
mit Betragsgrenze aktiviert; die Automatik ist je Mandant abgeschaltet, bis der Betreiber
sie einschaltet. Einzelheiten im Kapitel Banking.

### Ausgleich nach gesetzlicher Reihenfolge (Vorschlag)

Zahlt ein Schuldner ohne Tilgungsbestimmung und hat mehrere offene Posten, kann die Plattform
auf der Seite des Buchungskreises (Abschnitt Offene Posten, Karte „Ausgleich nach gesetzlicher
Reihenfolge“) einen Vorschlag berechnen. Eingaben: Personenkonto, Bankkonto, Zahlbetrag und
der Verwendungszweck. Nennt der Verwendungszweck einen Posten (Sollstellungs- oder
Rechnungsnummer, Monat, Quartal), gilt diese Bestimmung des Zahlers zuerst. Ohne Bestimmung
ordnet der Vorschlag in der gesetzlichen Reihenfolge: fällige vor nicht fälligen Posten, unter
den fälligen die mit geringerer Sicherheit, dann die lästigeren (in einem versandten
Mahnvorgang), dann die älteren; Kosten vor Zinsen vor Hauptforderung. Ein Rest, der keinen
Posten mehr findet, bleibt Guthaben auf dem Personenkonto und wird nie Ertrag.

Der Vorschlag ist mit „Vorschlag nach gesetzlicher Reihenfolge, Rechtsprüfung vor G1 offen“
gekennzeichnet und ändert nichts. Erst „Vorschlag bestätigen“ legt einen Buchungsentwurf
(Bank an Personenkonto) mit dem Ausgleichsplan an; die Bestätigung wird mit Regel und
Regelversion im Ereignisprotokoll festgehalten. Haben sich die offenen Posten zwischen
Berechnung und Bestätigung geändert, lehnt die Plattform die Bestätigung ab und der Vorschlag
ist neu zu berechnen. Gebucht wird der Entwurf wie jeder andere im Journal; für die
produktive Buchführung gilt die Freigabestufe G1. Weder Importe noch Automatiken wenden den
Vorschlag ohne Bestätigung an (Regel M10-03).

## Mahnwesen

Buchhaltung, Mahnwesen: Stichtag wählen, Vorschau erstellen. Der Mahnlauf ist zunächst
Vorschau und listet je Fall Stufe, Betrag, Mahngebühr, Status (vorgeschlagen,
ausgeschlossen, versandt) und Begründung. Ausgeschlossen sind unter anderem Fälle mit
Mahnsperre am Vertrag, unter der Mahngrenze und alle Fälle eines Buchungskreises, der nicht
führend ist. Solange G1 geschlossen ist, ist deshalb kein Fall vorgeschlagen und die
Schaltfläche Mahnlauf freigeben erscheint nicht; die Freigabe müsste ohnehin eine zweite
Person erteilen (nicht der Ersteller des Laufs).

Hat der Schuldner im Kontakt einen Bevollmächtigten mit Zustellregel (Kontakte,
Bevollmächtigte), folgt das Mahnschreiben dieser Regel: bei "beide" enthält das PDF je
Empfänger eine Kopie, die Kopie an den Bevollmächtigten trägt die Zeile "für
<Vollmachtgeber>". Erhält nur der Bevollmächtigte, zeigt die Vorschau am Fall das Kennzeichen
"Nur Bevollmächtigter, Zugang rechtlich zu klären"; die Warnung steht auch in der
Begründung des Falls. Ob die Mahnung damit dem Schuldner zugeht, ist vor dem Versand mit dem
Rechtsanwalt zu klären (Betreiberentscheidung 27.09.2026, M23-07).

Je vorgeschlagenem Fall stehen bereit: Mahnschreiben als PDF-Entwurf (Vorschau) und Entwurf
ablegen, Als versendet markieren mit Versandweg (Post, E-Mail, Portal), auf der höchsten
Stufe Mahnbescheid vorbereiten (Export als JSON oder PDF für Rechtsanwalt oder
Online-Mahnantrag; die Plattform stellt keinen Antrag). Nur ein als versendet markierter
Fall steigt beim nächsten Lauf in die nächste Stufe. Versand aus der Plattform findet nicht
statt.

Mahnstufen und Gebühren (Schaltfläche auf der Mahnwesen-Seite): je Stufe Tage nach
Fälligkeit, Bezeichnung, Gebühr in EUR (leer bedeutet keine Gebühr), Gebühr ab Stufe,
Mahngrenze, Zahlungsfrist in Tagen, eigener Brieftext mit Platzhaltern, Verzugszins mit
Basiszinssatz (vom Betreiber halbjährlich zu pflegen) und Aufschlag (Verbraucher 5,
Unternehmer 9 Prozentpunkte). Die Einstellung gilt als Mandantenvorgabe und kann je Objekt
überschrieben werden; Vorschlagswerte laden füllt die Stufen ohne Beträge. Beträge und
Zinssatz sind eine kaufmännische Einstellung, keine rechtliche Freigabe; ohne Wert bleibt
die Position 0,00 EUR.

### Zustellnachweis, Sperren je Posten und Zinsen

Zu einem als versendet markierten Fall lassen sich Zustellnachweise erfassen (Einschreiben,
Postnachweis, E-Mail-Nachweis, Portalzustellung, Sonstiges) mit Datum, Referenz und
optional einem abgelegten Dokument. Einzelne offene Posten lassen sich mit Grund sperren
(Ratenplan, bestrittener Posten, Aufrechnung, Prozess, Insolvenz); gesperrte Posten gehen in
keinen Mahnlauf ein, die Sperre wird aufgehoben, nicht gelöscht. Basiszinssätze pflegt die
Buchhaltung mit Gültigkeitsbeginn und Quelle; ändert sich der Satz während des Verzugs,
zeigt der Fall die Zinsen je Zeitraum. Nach Freigabe des Laufs kann eine berechtigte Person
die Zinsen als Buchungsentwurf anlegen; gebucht wird nur über die Vier-Augen-Freigabe bei
geöffnetem G1. Jeder Fall zeigt Prüfhinweise zu Verjährung und Fristen sowie einen
Vorschlag für den Zinsaufschlag aus dem Verbraucherkennzeichen des Schuldners; beides ist
durch den Rechtsanwalt zu prüfen und wird nicht automatisch angewendet.

## Rechnungseingang

Menü Rechnungen: Eingangsrechnungen mit Buchungskreis, Aussteller, Rechnungsnummer, Datum,
Leistungszeitraum, Netto, Steuersatz, Kostenkonto und Auftrag oder Vertrag. Rechnungen
entstehen von Hand, aus dem Belegeingang (KI-Entwurf, Kapitel Belegeingang) oder aus
Paperless. Die weitere Bearbeitung ist getrennt in:

1. Prüfschritte Vollständigkeit, sachliche Prüfung, rechnerische und steuerliche Prüfung
   mit Ergebnis (ohne Beanstandung, mit Vorbehalt, Rückfrage, beanstandet) und
   Begründung. Automatische Prüfungen liefern nur Hinweise.
2. Abweichende IBAN bestätigen: nur nach Rückruf beim Aussteller, gesondert protokolliert.
3. Rechnung freigeben (zweite Person): die Freigabe ist an die Rechnungsversion gebunden;
   jede Änderung erzeugt eine neue Version und hebt Freigaben auf.
4. Buchen: Kreditor und offener Posten; Korrektur nur per Storno. Skonto zum Zahltag wird
   angezeigt.

Rechnungspläne erzeugen fällige Dauerrechnungen als Entwurf. Der Abgleich einer Rechnung
mit Bankumsätzen (Betrag, Rechnungsnummer oder IBAN) ist lesend.

## Zahlläufe

Aus einer gebuchten Rechnung entsteht ein Zahlungsauftrag als Entwurf (Menü Bank,
Zahlungsaufträge) mit Ausführung, Empfänger, Verwendungszweck und Betrag. Freigabe durch
zwei verschiedene Personen (Anzeige 1 von 2 Freigaben); jede Änderung hebt Freigaben auf;
Verwerfen mit Bestätigung. Die Zahlungsdatei wird erst mit G2 erzeugt. Weitere Status
(exportiert, eingereicht, von Bank angenommen, ausgeführt, teilweise ausgeführt, abgelehnt,
zurückgegeben) entstehen aus der Bankrückmeldung; Export oder Einreichung gilt nie als
ausgeführte Zahlung. SEPA-Lastschriften werden nicht eingezogen, solange G2 geschlossen ist.

## Auswertungen und Export

Je Buchungskreis (Schaltfläche Auswertungen): Liquiditätsvorschau 90 Tage (freie Mittel,
Rücklagen, getrennt verwahrte Mietkautionen, erwartete Ein- und Auszahlungen, projizierte
freie Mittel), Zahlungen je Debitor und Erträge je Erlöskonto für einen Zeitraum sowie der
Prüfexport (ZIP je Rechtsträger und Zeitraum mit CSV je Tabelle und SHA-256-Prüfsumme, im
Hintergrund erstellt). Über die Schnittstelle zusätzlich Journal-Export als CSV mit
Prüfsumme und DATEV-Buchungsstapel, sofern Beraterdaten und Kontenzuordnung hinterlegt
sind (Einstellungen, Buchhaltung, DATEV; Kapitel Einstellungen).

## Verwalterhonorar

Das Verwalterhonorar wird je Rechtsträger eingerichtet; die Honorarrechnung lässt sich als
Entwurf berechnen und als XRechnung ausstellen (Rechnungsnummer im Format
KÜRZEL-JJJJ-000001, Umsatzsteuerstatus aus den Mandanteneinstellungen). Rechnungssteller
ist immer der angemeldete Mandant.

Buchhaltung, Verwalterhonorar: Honorar je Objekt mit Beginn, Intervall, Steuersatz und
Beträgen je Einheitsart einrichten. Beenden setzt das letzte Honorardatum; ein Honorar mit
Rechnungen wird nicht gelöscht. Unter Stichtag für fällige Zeiträume stehen je Honorar der
Leistungszeitraum (Monat, Quartal, Halbjahr oder Jahr), der Betrag und ob er schon abgerechnet
ist. Ausstellen vergibt die Rechnungsnummer; je Zeitraum gibt es eine Rechnung. In der Liste
der Honorarrechnungen: Freigeben, XRechnung laden, Prüfen (Strukturprüfung), Ablegen
(Dokumentenablage) und Stornieren. Stornieren verlangt einen Grund und erzeugt eine
Gutschrift mit eigener Nummer; danach kann der Zeitraum neu abgerechnet werden. Nichts wird
versendet und nichts gebucht.

## Buchen im CRM (Lückenliste 30.09.2026)

* Buchungssatz erfassen: Im Buchungskreis unter Journal den Vorgang wählen (Buchungssatz, Kostenkorrektur oder Zinsbuchung), Buchungstag, Text und Beträge eintragen und als Entwurf speichern. Soll und Haben müssen gleich sein.
* Buchen: In der Journalzeile auf Buchen klicken. Gebuchte Sätze bleiben unverändert, Korrekturen erfolgen nur über Stornieren mit Angabe eines Grundes.
* Anfangsbestand: Eine zweite Person bestätigt über Anfangsbestand prüfen, erst danach ist Buchen möglich.
* Festschreiben: Unten auf der Seite ein Datum wählen und bestätigen. Das Festschreiben kann nicht zurückgenommen werden.
* Kontenplan: Über die Schaltfläche Kontenplan Konten ergänzen, umbenennen, Buchungstexte, Umsatzsteueroption und Sichtbarkeit ändern oder deaktivieren. Kreditorenkonten aus Dienstleisterverhältnissen legt die Schaltfläche Kreditorenkonten aus Dienstleistern anlegen an.
* Kontenblatt: Die Kontonummer im Kontenplan öffnet das Kontenblatt mit Laufsaldo für den gewählten Zeitraum. Bei Kostenkonten steht dort die Verteilung auf Umlageschlüssel, die Summe muss genau 100 % ergeben.
* Zinsbuchung: Gebucht wird der eingegebene Betrag. Einbehaltene Steuer wird nicht automatisch berücksichtigt.
* Solange Immoware24 führend ist (Freigabestufe G1 geschlossen), sind Buchungen in der Plattform Parallelbetrieb und nicht die führende Buchhaltung.

## Weitere Auswertungen und Excel

Unter Buchhaltung, Auswertungen, Abschnitt "Weitere Auswertungen und Excel" wählen Sie die
Ansicht (Kontenblatt, Saldenliste, Offene Posten, Monatsmatrix, Soll/Ist der Forderungen,
Bankkontoabrechnung, Umsatzsteuer und Vorsteuer als Entwurf, Einnahmen und Ausgaben) und
Stichtag oder Zeitraum. Jede Ansicht zeigt oben Rechtsträger, Zeitraum, Stichtag, Datenstand,
Filter und den Status Entwurf. "Als Excel laden" erzeugt die Arbeitsmappe und protokolliert
den Abruf. "Verfahrensdokumentation (Entwurf)" lädt einen aus dem Betrieb erzeugten Text mit
Lücken, die mit dem Steuerberater zu klären sind. Die steuerlichen Ansichten sind keine
Voranmeldung und keine EÜR. Das Kennzeichen "USt" oder "EÜR" je Konto setzt nur eine Person
mit Freigaberecht.

## Häufige Fehler

- Sollstellung blockiert: Erlöskonto je Zahlungsart oder Buchungskreis des Rechtsträgers
  fehlt.
- Sollstellung für diesen Zeitraum wurde bereits gebucht: je Monat und Vertrag nur ein
  gebuchter Lauf; Korrektur per Storno.
- Alle Mahnfälle ausgeschlossen mit Begründung nicht führend: erwartetes Verhalten bis G1.
- Die Freigabe muss eine andere Person erteilen: Ersteller und Freigebender müssen
  verschieden sein (Mahnlauf, Rechnung, Zahlungsauftrag, Anfangsbestand).

## Verwalterhonorar (Seite Buchhaltung, Verwalterhonorar)

Die Seite führt durch die Honorarabrechnung je Objekt.

- "Honorar einrichten": Objekt, Beginn, optional Ende, Intervall (monatlich, vierteljährlich, halbjährlich, jährlich), USt-Satz und Beträge je Einheitentyp erfassen. Eingerichtete Honorare lassen sich mit einem letzten Tag beenden.
- Mit einem Stichtag werden die fälligen Leistungszeiträume samt Bruttobetrag angezeigt. Je Zeitraum wird die Rechnung einmal ausgestellt; die Rechnungsnummer wird nach Bestätigung fest vergeben.
- Unter "Honorarrechnungen" lassen sich Rechnungen freigeben, als XRechnung prüfen (nur Strukturprüfung, die amtliche Prüfung läuft außerhalb der Plattform), ablegen und stornieren. Das Stornieren erzeugt eine Gutschrift mit eigener Nummer und verlangt einen Grund.
- Eine ausgestellte Rechnung wird nie geändert. Nichts wird versendet; die Buchung des Honorars bleibt bis zur Freigabestufe G1 offen.

## Konten und Kontenblatt (Seite Buchhaltung, Buchungskreis, Konten)

Der Kontenplan eines Buchungskreises wird unter Buchhaltung, Buchungskreis, Konten gepflegt.

- "Konto ergänzen": Kontonummer, Bezeichnung, Kontoart, Kontotyp, Umsatzsteuer (keine, Regelsatz, ermäßigt), Relevanz für den Kassenbericht und bis zu drei Buchungstexte.
- Bestehende Konten lassen sich ändern sowie deaktivieren und wieder aktivieren. Konten mit Buchungen werden nur deaktiviert, nie gelöscht. Deaktivierte Konten stehen für neue Buchungen nicht zur Auswahl.
- "Kreditorenkonten aus Dienstleistern anlegen" erzeugt fehlende Kreditorenkonten je Dienstleisterverhältnis und meldet, wie viele angelegt und zugeordnet wurden.
- Je Konto öffnet das Kontenblatt. Es zeigt für einen wählbaren Zeitraum (Von, Bis) den Anfangssaldo, die Buchungen mit Laufsaldo sowie Summen und Endsaldo. Ein Link führt zurück zum Kontenplan.

## Mahnwesen: Hinweise, Zinsen, Zustellnachweise und Sperren

Im Mahnlauf öffnet der Aufklapper "Prüfhinweise, Zins, Zustellnachweise und Sperren" je Fall die Prüfhinweise zu Verjährung und Fristen (nur Hinweise, die Plattform berechnet kein Verjährungsdatum), den Vorschlag für den Zinsaufschlag aus dem Verbraucherkennzeichen (die Einstellung ändert sich nicht), die Zinsberechnung je Basiszinssatzzeitraum und den Knopf "Zinsentwurf anlegen". Der Zinsentwurf ist keine Buchung; Freigabe nur über die Vier-Augen-Buchung bei geöffnetem Gate G1, Zinssatz und Anspruchsgrundlage sind anwaltlich zu prüfen. Zustellnachweise (Einschreiben, Posteinlieferung, E-Mail, Portal) werden mit Datum und Referenz am Fall erfasst. Je Posten lässt sich eine Mahnsperre mit Grund (Ratenplan, bestrittener Posten, Aufrechnung, Prozess, Insolvenz) setzen und aufheben. Auf der Startseite des Mahnwesens steht die Basiszinssatzhistorie; Sätze sind Betreibereingaben mit Quelle, ohne Satz für den Zeitraum wird kein Zins berechnet.

Unter der Basiszinssatzhistorie zeigt die Startseite des Mahnwesens die gewählte Zinstagemethode. Ist für das laufende Halbjahr (ab 01.01. oder 01.07.) noch kein Satz gepflegt, erscheint der Hinweis "Basiszinssatz prüfen" mit den nächsten Änderungsterminen; die Vorschau rechnet bis zur Pflege mit dem zuletzt gepflegten Satz. Der Knopf "Prüfpunkte 01.01. und 01.07. anlegen" legt für die nächsten zwei Termine je einen Prüfpunkt im Fristenregister an (Vorfrist laut Prüfpunktliste, Standard 30 Tage). Die Zinstagemethode (Tage durch 365 fest oder durch die tatsächlichen Jahrestage) stellen Sie unter Einstellungen, Fachliche Regeln ein; der Standard bleibt 365, die Entscheidung ist offen (AI03-01) und anwaltlich zu klären. Jede Zinsberechnung nennt die verwendete Methode.

## Honorarlauf, Rechnungsdokument und Jahreswechsel (Q15)

- Honorarlauf: "Fällige Honorare ausstellen" zeigt zuerst die Vorschau aller fälligen Leistungszeiträume. Erst mit Bestätigung wird je Honorar eine Rechnung mit eigener, lückenloser Nummer ausgestellt; ein Fehler bei einem Honorar stoppt die übrigen nicht und verbraucht keine Nummer. Bereits abgerechnete Zeiträume werden übersprungen. Nichts wird versendet oder gebucht.
- Rechnungsdokument: Zu jeder Honorarrechnung und jeder Gutschrift kann das lesbare Dokument als PDF auf dem Briefbogen des Mandanten abgelegt werden. Ein zweiter Aufruf liefert dasselbe Dokument. Die Gutschrift lässt sich zusätzlich als XRechnung ablegen. Es gelten dieselben Pflichtangaben wie bei der XRechnung.
- USt-Übersicht je Objekt: Die Auswertung gliedert die Umsatzsteuer und die Vorsteuer vor Abzug nach Objekt (Objekt der Buchungszeile aus Angabe, Einheit oder Vertrag, seit Welle 16) und Kostenstelle. Zeilen ohne Objekt stehen unter "ohne Objekt". Entwurf, keine Voranmeldung.
- Jahreswechsel: Unter Buchungskreis zeigt "Schlussbestand übernehmen" die Schlussbestände des beendeten Geschäftsjahres. Die Übernahme erzeugt zwei Entwürfe zum Beginn des Folgejahres, die nicht gebucht sind. Der Anfangsbestand braucht die Prüfung durch eine zweite Person. Übernommen werden nur Bank, Kasse, Rücklage, Darlehen und Durchlaufkonten; Personenkonten behalten ihre offenen Posten.

## Freigabeentscheidungen, Personenhinweis und offene Posten zum Stichtag (Q01)

- Jede Freigabe einer Rechnung oder eines Zahlungsauftrags wird mit dem Stand des Vorgangs
  gespeichert. Wird der Vorgang danach geändert, steht die Freigabe dauerhaft als ungültig im
  Verlauf (`GET /accounting/approval-decisions`), eine neue Freigabe ist nötig.
- Geben zwei Benutzerkonten frei, deren getrennte Kontakte auf dieselbe Person hindeuten (gleiche
  E-Mail-Adresse, gleicher Name mit gleichem oder fehlendem Geburtsdatum), zeigt die Seite
  Bank, Zahlungen einen Hinweis. Die Freigabe wird nicht gesperrt; bitte die Personen prüfen.
- Offene Posten zum Stichtag werden nachts als Lesekopie berechnet und lassen sich für einen
  beliebigen Stichtag neu berechnen (`POST /accounting/ledgers/{id}/open-item-balances/refresh`).
  Maßgeblich bleibt die Liste der offenen Posten.
- Beim Anlegen eines Dienstleisterverhältnisses entsteht das Kreditorenkonto automatisch.
- Einstellungen, Sollstellungsagent: Schalter für die monatliche Vorschau der Sollstellungen
  (nur Entwürfe, Standard aus).

## Jahresübernahme und Honorarlauf

Auf der Seite eines Buchungskreises zeigt "Jahresübernahme" nach Eingabe des Geschäftsjahres die Schlussbestände. "Als Entwurf übernehmen" legt Schlussbestand und Anfangsbestand als Buchungsentwürfe an; diese werden wie jede Buchung geprüft und von einer zweiten Person freigegeben. Unter "Verwalterhonorar" stellt der "Honorarlauf" alle fälligen Honorare eines Zeitraums gesammelt aus: zuerst "Vorschau", dann "Rechnung(en) ausstellen" nach Bestätigung (die Rechnungsnummern werden fest vergeben). Zu jeder Honorarrechnung erzeugt "PDF erzeugen" das Rechnungsdokument auf dem Briefbogen und bietet es danach zum Herunterladen an. Nichts wird versendet.

## Art der Abrechnung und Verteilung je Konto

Im Kontenplan zeigt die Spalte "Art der Abrechnung" je Konto Hausgeld, Rücklage, Betriebskosten, Sonderumlage, Heizkosten oder keine. Bei Kostenkonten blendet "Verteilung" die hinterlegte Mehrschlüsselverteilung mit Anteilen und Summe ein. Die Pflege der Verteilung erfolgt weiterhin über die API.

## Vermerke zu gebuchten Sätzen und Prüfbericht (AA01)

Im Journal hat jeder gebuchte Satz die Schaltfläche **Vermerke**. Dort lassen sich ergänzende
Hinweise erfassen, etwa ein nachgereichter Beleg. Ein Vermerk ändert den Buchungsinhalt nicht.
Wer einen Vermerk ändern möchte, wählt **Neue Version**; die frühere Fassung bleibt
durchgestrichen sichtbar. Entwürfe haben keine Vermerke, sie werden direkt geändert.

Die Konsistenzprüfung des Buchungskreises meldet zusätzlich Lücken in der Nummernfolge je
Geschäftsjahr und Abweichungen des Nummernzählers. Der Nebenbuchabgleich zeigt je Debitor und
Kreditor den Kontensaldo, den Restbetrag der offenen Posten und die Differenz zum Stichtag.
Eine Differenz ist ein Prüfhinweis, zum Beispiel für eine noch nicht zugeordnete Zahlung.

Den Nebenbuchabgleich finden Sie unter **Buchhaltung, Auswertungen** im Abschnitt
**Nebenbuchabgleich (Prüfbericht)**, getrennt nach Debitoren und Kreditoren. Der Stichtag ist
der oben gewählte Stichtag. Konten mit Differenz sind hervorgehoben. Der Prüfexport (ZIP)
enthält denselben Abgleich als Tabelle `nebenbuchabgleich.csv` zum Ende des Exportzeitraums.

## Honorarfelder, Rechnungsplan und Standard-Bankregel (AB09)

**Verwalterhonorar, weitere Angaben.** Im Formular Verwalterhonorar (Buchhaltung, Verwalterhonorar) steht unter "Weitere Honorarangaben": Verwalterkontakt (Suche, nur Name), Kündigungsdatum, Fälligkeitsregel (fester Tag im Monat, letzter Tag, fester Tag im Folgemonat), Tag, Erlöskonto (ID) und Honorar je SE-Einheit netto. Alle Angaben sind optional. Das Kündigungsdatum begrenzt den Honorarlauf, die Fälligkeitsregel gilt für künftig ausgestellte Rechnungen. Die Liste zeigt Kündigung, Fälligkeit und SE-Betrag. Es wird nichts gebucht und nichts versendet.

**Rechnungsplan, automatische Buchung ja oder nein.** In der Planliste (Kreditoren, Rechnungspläne) zeigt die Spalte "Automatische Buchung" das Kennzeichen. Nein: Der Lauf erzeugt nur Rechnungsentwürfe. Ja kann nur angefordert werden, wenn der Mandant die Automatik freigeschaltet hat; gebucht wird trotzdem nichts, solange die Freigabestufe G1 geschlossen ist und keine aktive, freigegebene Regel besteht. Nach "Entwurf erzeugen" meldet die Oberfläche den Sperrgrund.

**Standard-Bankregel.** Wird ein Dienstleisterverhältnis mit der Option Standard-Bankregel angelegt (Bankverbindung und Kreditorenkonto vorhanden), entsteht eine Vorschlagsregel (Zustand vorgeschlagen, Priorität 900). Sie bucht nichts; Freigabe und Aktivierung laufen über die Regelverwaltung mit zweiter Person. Ohne die Option entsteht keine Regel, pro Bankverbindung höchstens eine.

### Fällige Prüfpunkte des Regelregisters

Auf der Startseite der Buchhaltung listet ein Block die fälligen, datierten Prüfpunkte des Regelregisters. Der Hinweis ist ohne Rechtsfolge: Er erinnert an eine fachliche Prüfung, sperrt nichts und ändert keine Regel.

## Erlöskonto im Honorarformular (AC04)

Das Erlöskonto des Verwalterhonorars wird aus einer Liste gewählt, nicht mehr als ID eingegeben. Angeboten werden die aktiven Konten der Kategorie Erlöse aus den Buchungskreisen des gewählten Objekts. Ohne Auswahl bleibt das Feld leer (optional); das Backend prüft weiterhin, dass das Konto zum Objekt gehört.

## Kontenrahmen: Prüfbericht, Verteilung und Vier-Augen-Freigabe

Unter Einstellungen, Buchhaltung, Kontenrahmen zeigt der Bereich "Prüfbericht und Verteilung" Konten ohne Abrechnungsart, Kostenkonten ohne gültige Schlüsselverteilung und offene Vorschläge (zum Beispiel Abrechnungsart Heizkosten). Im Entwurf lässt sich ein Vorschlag übernehmen und die Verteilung auf mehrere Schlüssel pflegen, die Summe muss 100 Prozent ergeben. Die Freigabe erteilt eine zweite Person; das Abschalten dieser Regel braucht das Freigaberecht und eine Begründung.

## Periodensperre je Objekt und Zeitraum

Unter Einstellungen, Buchhaltung, Periodensperren legen Sie eine Sperre für ein Objekt und einen Zeitraum an. Die Seite zeigt den Hinweis "Entscheidung offen", weil der Umfang der Sperre (P06-02) und die Wiederöffnung (AA08-01) noch nicht entschieden sind. Standard ist die bisherige Festschreibung des ganzen Buchungskreises.

* Schalter "Zusätzlich Objekt und Zeitraum": Buchungen und Stornos mit Zeilen des Objekts im gesperrten Zeitraum werden abgelehnt.
* Schalter "Abschluss einer Abrechnung setzt die Sperre": Beim Abschluss (Status gesperrt) einer Miet- oder Eigentümerabrechnung wird die Sperre für Objekt und Zeitraum angelegt. Ohne den Schalter erscheint nur ein Vorschlag.
* Schalter "Aufhebung zulassen": Eine Sperre wird mit Begründung beantragt und von einer anderen Person freigegeben. Die Sperre bleibt als aufgehoben in der Liste.

## Steuerabzüge bei Habenzinsen

Im Formular Buchung erfassen wählen Sie den Vorgang Zinsbuchung mit Richtung Habenzinsen. Tragen Sie den Bruttozins und die einbehaltene Kapitalertragsteuer, den Solidaritätszuschlag und gegebenenfalls die Kirchensteuer so ein, wie sie auf dem Bankbeleg stehen. Das Formular zeigt die Gutschrift auf dem Geldkonto. Vorher hinterlegen Sie im Block Steuerkonten für Zinsabzüge je Buchungskreis die Konten; ohne Konto wird der Abzug abgelehnt. Es entsteht nur ein Entwurf. Die steuerliche Behandlung klären Sie mit dem Steuerberater. In der Rücklagenentwicklung erscheint der Steuerabzug gebuchter Zinsbuchungen als eigene Spalte.

## Nebenbuchabgleich: ausgebuchte und stornierte Posten

Im Prüfbericht (Auswertungen) werden ausgebuchte Posten und Posten stornierter Buchungen standardmäßig nicht in die offenen Posten und die Differenz gezählt. Ein Hinweis nennt Anzahl und Betrag getrennt. Der Mandantenschalter steht in den Steuereinstellungen (`subledger_exclude_written_off`). Der Export `nebenbuchabgleich.csv` enthält die Spalte Grund. Die Anzeige bucht nichts.

## Objekt der Buchungszeile und Driftbericht

Jede Buchungszeile trägt ein Objekt. Wählen Sie eine Einheit, gilt deren Objekt; eine abweichende Objektangabe wird abgelehnt. Ohne Einheit gilt das Objekt des Vertrags, auf den sich der Buchungssatz bezieht. Für Zeilen ohne Einheit und ohne Vertrag geben Sie das Objekt bei Bedarf über die Schnittstelle an (`lines[].property_id`), sonst steht die Zeile unter ohne Objekt. Ein Storno übernimmt das Objekt der stornierten Zeile; ein falsches Objekt einer gebuchten Zeile berichtigen Sie per Storno und neuer Buchung.

* USt-Übersicht je Objekt, Monatsmatrix und Einnahmen und Ausgaben lassen sich auf ein Objekt einschränken (`property_id`), ebenso das Journal.
* Der Driftbericht (`GET /accounting/ledgers/{id}/reports/line-property-drift`) zeigt Zeilen, deren Objekt nicht zur Einheit passt (Befund, erscheint auch im Prüfbericht), sowie Hinweise: Vertragsobjekt fehlt oder weicht ab, Objekt weicht vom Objekt des Buchungskreises ab. Der Bericht ändert nichts. Eine Oberfläche im CRM folgt.

## ZUGFeRD-Rechnung (Welle 16)

Unter "Honorarrechnungen" steht zu jeder Rechnung und Gutschrift:

- "ZUGFeRD" lädt das Rechnungsdokument auf dem Briefbogen mit den eingebetteten Rechnungsdaten (Factur-X, Profil EN 16931). Es gelten dieselben Pflichtangaben wie bei der XRechnung.
- "ZUGFeRD prüfen" zeigt das Ergebnis der eigenen Strukturprüfung und der eigenen PDF/A-Vorprüfung. Die Datei ist als PDF/A-3 gekennzeichnet, die Konformität ist nicht nachgewiesen; angezeigte Hinweise (zum Beispiel nicht eingebettete Schriften) sind vor einem Versand mit einem PDF/A-Prüfprogramm zu klären.
- "ZUGFeRD ablegen" legt den Beleg einmal mit dem Prüfergebnis im Dokumentenbereich ab. Nichts wird versendet oder gebucht.

## Objektfilter, Kontenpflege, zweite Freigabe und Kautionen (Paket AF05)

- Auswertungen: Monatsmatrix sowie Einnahmen und Ausgaben lassen sich je Objekt filtern. Neue Ansichten: Umsatzsteuer je Objekt und Kostenstelle (Entwurf), Offene Posten Salden (gepflegte Lesekopie) und der Driftbericht zum Objekt der Buchungszeilen. Der Driftbericht ändert nichts, gebuchte Zeilen werden nur per Storno und neuer Buchung berichtigt.
- Buchungsmaske: je Zeile kann ein Objekt gewählt werden. Ohne Auswahl folgt das Objekt der Einheit oder dem Vertrag. Das Journal lässt sich nach Objekt filtern.
- Kontenplan: Steuerkennzeichen (EÜR, USt, gemischte Nutzung) je Konto mit dem Recht zur Freigabe, Erlöskonto je Zahlungsart und die Aktion "Debitorenkonten aus Verträgen übernehmen".
- Rechnung: Die Schaltfläche "Zweite Freigabe erteilen" erscheint, wenn die Betragsgrenze überschritten ist. Die Vier-Augen-Prüfung erfolgt in der API.
- Kautionen: Bewegungen werden erfasst (keine Buchung vor Freigabe der Buchhaltung). Der Jahreslauf legt Zinsentwürfe an, bucht und zahlt nichts.

## Abnahmeregister in der G1 Checkliste, Dauerrechnungen, Honorar und § 35a (Welle 17, AF06)

* G1 Öffnung zeigt den Stand des Abnahmeregisters (nur Anzeige, Link zum Register). Die Ergebnisse der Checkliste bleiben unverändert.
* Dauerrechnung erzeugen liefert weiterhin nur einen Entwurf mit Planentwurfsnummer. Im Schalter "Ausgabe bei geschlossenem G1 ablehnen" wird die Erzeugung abgewiesen, solange G1 geschlossen ist.
* Verwalterhonorar: Honorargutschriften haben XRechnung XML, Prüfung und Ablage.
* Einstellungen, Buchhaltung, Steuern: Ausweis nach § 35a je Mietvertrag als Anzeige und PDF Entwurf (Einschätzung, Prüfung durch die Steuerberatung).
* Zahllauf: Schalter der wöchentlichen Vorschau (Recht Mandanteneinstellungen ändern). Der Nummernmodus der Mietrechnungsentwürfe wird unter Fachliche Regeln geändert, am Vertrag nur angezeigt.

## Bestehende Zuordnungen, Gläubiger-ID und Objektfilter im Excel-Export

Die Kontenmaske zeigt über dem Formular die bereits hinterlegten Zuordnungen Zahlungsart zu Erlöskonto. Unter Einstellungen, Buchhaltung, Gläubiger-ID und unter Bank, Verbindungen steht die hinterlegte Gläubiger-ID je Rechtsträger (nur Anzeige, Änderung in den Einstellungen). Der Excel-Export von Journal, Monatsmatrix und Einnahmen Ausgaben kann auf ein Objekt eingeschränkt werden (Parameter property_id). Die Sachprüfung einer Rechnung zeigt beim Budgetabgleich zusätzlich die Teilbeträge Rechnungen, Gutschriften und Buchungszeilen mit Plankonto.

## Führendes System je Vorgangstyp (Welle 18, AG02)

Im Buchungskreis zeigt der Abschnitt "Führendes System je Vorgangstyp", welches System für Sollstellung, Mahnung, Lastschrift und Zahlungsauftrag heute führt und ob dies aus einer Umschaltung oder aus der Einstellung des Buchungskreises stammt. Wer Freigaberechte hat, beantragt eine Umschaltung mit Vorgangstyp, führendem System, Gültig-ab und optional einem Objekt. Freigeben oder ablehnen muss eine andere Person; die Plattform als führendes System lässt sich nur mit geöffneter Freigabestufe G1 freigeben. Ohne Umschaltung arbeiten alle Läufe wie bisher.

## Liquiditätsvorschau mit Kopfangaben und Freigabeverlauf (Welle 20, AI02)

Die Liquiditätsvorschau auf der Seite Auswertungen zeigt jetzt die gemeinsamen Kopfangaben (Rechtsträger, Stichtag, Datenstand, Status Entwurf) und lässt sich über "Als Excel herunterladen" als Arbeitsmappe speichern (Recht Export). Ein Rücklagenkonto, das nur über die Kontonummer 001201 und nicht über ein verknüpftes Bankkonto erkannt wurde, trägt einen Hinweis; die Verknüpfung mit dem Bankkonto des Objekts ist der verlässliche Weg.

Auf der Rechnungsseite und in der Liste der Zahlungsaufträge öffnet "Freigabeverlauf anzeigen" die Freigabeentscheidungen des Vorgangs mit Schritt, Zeitpunkt, Status und Prüfsumme des freigegebenen Stands. Eine entwertete Freigabe nennt Zeitpunkt und Grund (zum Beispiel geänderter Betrag); Personenhinweise aus der Identitätsprüfung erscheinen als Hinweis. Die Ansicht ist reine Anzeige, eine Freigabe wird an der bisherigen Stelle erteilt.

## Hinweis zum Nummernkreis Bank und Kasse

Neue Konten mit Nummer 001200 bis 001999 sind nur als Bank, Kasse, technisches Konto oder Geldtransit möglich, eine Bankkontoverknüpfung nur an Bank- oder Kassenkonten. Bestehende abweichende Konten bleiben erhalten und zeigen in der Kontenliste einen Hinweis unter der Kategorie.

## Mahnschreiben versenden (gesperrt)

Im Mahnfall mit Status Vorgeschlagen steht die Schaltfläche Mahnschreiben versenden mit dem Stand der Freigabestufe G1. Solange G1 geschlossen ist, bleibt sie gesperrt; auch bei offener Freigabestufe lehnt die Plattform den Versand ab, bis der Versandweg freigegeben ist. Bis dahin wird das Schreiben außerhalb der Plattform versendet und mit Als versendet markieren dokumentiert.
