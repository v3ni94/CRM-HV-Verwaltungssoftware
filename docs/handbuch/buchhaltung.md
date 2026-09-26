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

## Offene Posten und Bankabgleich

Offene Posten entstehen aus Sollstellungen und gebuchten Eingangsrechnungen und werden
durch bestätigte Bankumsätze ausgeglichen. Der Bankabgleich (Menü Bank) zeigt Umsätze aus
CAMT.053-Dateien oder finAPI, schlägt Zuordnungen mit Begründung vor und bucht nur nach
Bestätigung; ohne passenden Posten wird ein Umsatz mit Begründung ignoriert. Bankregeln
für die Automatik werden vorgeschlagen, von einer zweiten Person fachlich freigegeben und
mit Betragsgrenze aktiviert; die Automatik ist je Mandant abgeschaltet, bis der Betreiber
sie einschaltet. Einzelheiten im Kapitel Banking.

## Mahnwesen

Buchhaltung, Mahnwesen: Stichtag wählen, Vorschau erstellen. Der Mahnlauf ist zunächst
Vorschau und listet je Fall Stufe, Betrag, Mahngebühr, Status (vorgeschlagen,
ausgeschlossen, versandt) und Begründung. Ausgeschlossen sind unter anderem Fälle mit
Mahnsperre am Vertrag, unter der Mahngrenze und alle Fälle eines Buchungskreises, der nicht
führend ist. Solange G1 geschlossen ist, ist deshalb kein Fall vorgeschlagen und die
Schaltfläche Mahnlauf freigeben erscheint nicht; die Freigabe müsste ohnehin eine zweite
Person erteilen (nicht der Ersteller des Laufs).

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

## Häufige Fehler

- Sollstellung blockiert: Erlöskonto je Zahlungsart oder Buchungskreis des Rechtsträgers
  fehlt.
- Sollstellung für diesen Zeitraum wurde bereits gebucht: je Monat und Vertrag nur ein
  gebuchter Lauf; Korrektur per Storno.
- Alle Mahnfälle ausgeschlossen mit Begründung nicht führend: erwartetes Verhalten bis G1.
- Die Freigabe muss eine andere Person erteilen: Ersteller und Freigebender müssen
  verschieden sein (Mahnlauf, Rechnung, Zahlungsauftrag, Anfangsbestand).
