# Objekte und Einheiten aus der Immoware24-Objektliste anlegen

Stand 26.09.2026. Die Objektliste (Export "Objektdaten", eine Zeile je Einheit mit Objekt-Nummer,
Objekt, Verwaltungsart, Gebäude, VE-Nummer, VE-Beschreibung, VE-Lage, aktueller Eigentümer oder
Mieter und vereinbartem Zahlbetrag) wird mit einem Befehl auf dem Server als Objekte und
Einheiten des gewählten Mandanten angelegt. Derselbe Import steht im CRM unter Importe,
Importassistent, Abschnitt "Immoware24-Listen" ohne Serverzugang zur Verfügung.

## Was angelegt wird

* Je Objekt-Nummer ein Objekt mit Bezeichnung und Verwaltungsart (WEG-Verwaltung,
  Mietverwaltung, WEG mit SE-Verwaltung).
* Je Zeile eine Einheit mit Nummer, Bezeichnung, Gebäude und Lage. Die Einheitenart wird aus der
  Bezeichnung abgeleitet (WE, Wohnung, Etage: Wohnung; Stellplatz, TG, S01: Stellplatz; Garage;
  GE, Gewerbe: Gewerbe). Unklare Bezeichnungen erhalten die Art "Sonstiges" und werden im
  Bericht ausgewiesen; sie sind anschließend in der Einheit zu prüfen.
* Eigentümer, Mieter und vereinbarte Beträge werden nur als Herkunftsnotiz an der Einheit
  gespeichert (Reiter Zusatzfelder, Bereich "altsystem"). Es entstehen keine Kontakte, Verträge,
  Sollstellungen oder Buchungen. Diese folgen über den Importassistenten (Kontakte, Verträge,
  Zahlungen) oder manuell.

## Regeln zur Objektnummer und zum Status

* Die Plattform führt dreistellige Objektnummern. Ein- und zweistellige Nummern werden mit
  führenden Nullen angelegt (81 wird 081). Nummern mit mehr als drei Stellen (10012, 2911,
  999999) werden übersprungen, bis mit `--number-map 10012=012` eine freie dreistellige Nummer
  zugeordnet ist.
* Präfix "Z ABGEGEBEN" (auch Z-ABGEBEN, Z.Abgegeben): Objekt wird ohne Präfix mit Status
  "beendet" angelegt. Mit `--skip-handed-over` werden diese Objekte gar nicht angelegt.
* Präfix "Y ABRECHNUNG": Objekt ohne Präfix mit Status "aktiv". Alle übrigen Objekte erhalten
  den Status "in Übernahme".
* Vorhandene Objekte und Einheiten (gleiche Nummer) werden nie überschrieben. Stimmen die Angaben
  überein, meldet der Bericht "unchanged", sonst "conflict" zur manuellen Prüfung.
* Überzählige führende Nullen (0081) werden entfernt, die Nummer wird als 081 angelegt. Die
  Zuordnung greift auch, wenn die Nummer in der Datei mit führenden Nullen steht (010012 findet
  `10012=012`); ein- und zweistellige Zielnummern der Zuordnung werden aufgefüllt (`10012=12`
  ergibt 012).

## Welche Exportvarianten gelesen werden

Der Import liest die Datei so, wie Immoware24 oder Excel sie liefern, und weist im Bericht unter
"Hinweise zur Datei" aus, was er dabei angeglichen hat:

* Zeichensatz UTF-8 mit und ohne BOM, Windows-1252 (ANSI, Excel) und Latin-1; Umlaute bleiben
  in jedem Fall erhalten.
* Trennzeichen Semikolon, Komma oder Tabulator werden an der Kopfzeile erkannt. Anführungszeichen
  mit eingeschlossenen Trennzeichen ("Müller, Jörg", "250,00") und Zeilenumbrüchen werden korrekt
  gelesen; die Zeilennummern im Bericht sind die der Datei.
* Leerzeichen am Anfang und Ende jeder Zelle, leere Zeilen und wiederholte Kopfzeilen (etwa nach
  dem Zusammenfügen mehrerer Exporte) werden übersprungen und gezählt.
* Die Reihenfolge der Spalten ist beliebig, zusätzliche Spalten werden ignoriert. Kopfzeilen
  werden ohne Rücksicht auf Groß- und Kleinschreibung, Leerzeichen, Bindestriche und
  Umlautschreibweise erkannt (Objekt-Nummer, Objektnummer, Gebäude, Gebaeude). Die beiden
  Spalten "vereinbarter Zahlbetrag" werden in Dateireihenfolge dem Eigentümer und dem Mieter
  zugeordnet.
* Fehlt eine Pflichtspalte (Objekt-Nummer, Objekt, Verwaltungsart, VE-Nummer), bricht der
  Import mit einer Meldung ab, die die fehlende Spalte und die gefundenen Spalten nennt.
* Zeilen ohne Objekt-Nummer oder VE-Nummer werden übersprungen und im Bericht genannt.
* Exakt doppelte Zeilen werden nur einmal übernommen (Hinweis am Objekt). Dieselbe VE-Nummer
  mit abweichenden Angaben bleibt ein Problem, das Objekt wird bis zur Klärung übersprungen.
* Die Verwaltungsart wird in üblichen Schreibweisen erkannt (WEG-Verwaltung, WEG,
  Mietverwaltung, WEG mit SE-Verwaltung, Sondereigentumsverwaltung, SEV).

## Vor dem Import prüfen

Checkliste für den Betreiber, bevor der Testlauf gestartet wird:

1. Richtigen Mandanten wählen (Hausverwaltung Müller GmbH oder Timo Müller); ein Import lässt
   sich nur über die Rücknahme des Importlaufs zurückholen.
2. Export in Immoware24 vollständig ziehen (alle Objekte, auch abgegebene) und die Datei einmal
   in einem Texteditor öffnen: Kopfzeile mit Objekt-Nummer, Objekt, Verwaltungsart, VE-Nummer
   vorhanden, keine leeren Spalten in der Kopfzeile, keine Vorschau- oder Summenzeilen.
3. Objektnummern mit mehr als drei Stellen (10012, 2911, 999999) vorab in der Nummernzuordnung
   festlegen; die Zielnummer darf nicht bereits belegt sein.
4. Entscheiden, ob abgegebene Objekte (Präfix Z ABGEGEBEN) mit angelegt werden sollen.
5. Testlauf ausführen und im Bericht prüfen: Hinweise zur Datei (Zeichensatz, Trennzeichen,
   übersprungene und doppelte Zeilen), übersprungene Objekte, Einheitenart "Sonstiges",
   Konflikte mit vorhandenen Objekten.
6. Zählung des Testlaufs mit dem Export vergleichen (Anzahl Objekte und Einheiten). Die Übernahme
   liefert dieselbe Zählung wie der Testlauf.
7. Nach der Übernahme einen zweiten Testlauf mit derselben Datei starten: alle Datensätze müssen
   als unverändert gemeldet werden.

## Ablauf über die Oberfläche

1. Im CRM Importe, Importassistent öffnen und im Abschnitt "Immoware24-Listen" die Karte
   "Objektdaten" verwenden. Erforderlich sind die Rechte des Importassistenten (KI anlegen sowie
   Objekte, Kontakte und Verträge anlegen); Nur-Lese-Benutzer erhalten eine Ablehnung.
2. CSV-Datei wählen (wie exportiert, höchstens 20 MB; Zeichensatz und Trennzeichen werden
   erkannt). Im Feld
   Nummernzuordnung die Paare `ALT=NEU` je Zeile oder durch Komma getrennt eintragen, zum
   Beispiel `10012=012`. Häkchen "Abgegebene Objekte überspringen" entspricht
   `--skip-handed-over`.
3. Testlauf ausführen. Es wird nichts gespeichert. Der Bericht zeigt die Zählung sowie Tabellen
   der übersprungenen Objekte (Nummern zuordnen), der Hinweise (führende Nullen, Status aus
   dem Präfix) und der Konflikte einschließlich Einheiten mit Meldungen.
4. Übernehmen ist erst nach einem Testlauf mit derselben Datei und denselben Einstellungen
   freigeschaltet und fragt vor dem Speichern nach. Jede Änderung an Datei, Zuordnung oder
   Häkchen setzt die Freischaltung zurück.
5. Nach der Übernahme erscheint der Lauf unter Importe mit der Quelle "Immoware24-Liste:
   Objektdaten". Er lässt sich dort wie andere Importläufe zurücknehmen, soweit keine späteren
   Daten auf den Objekten und Einheiten aufbauen.

Über die Schnittstelle: `POST /api/v1/imports/immoware24/lists/objektdaten?mode=preview` oder
`mode=apply` als multipart mit `file`, `number_map` (Text) und `skip_handed_over` (true oder
false). Die Antwort ist der Bericht des Befehls, bei Übernahme zusätzlich `import_run_id`.

## Ablauf auf dem Server

1. Datei nach `/opt/mhvp/import/objektdaten.csv` legen (wie exportiert; Zeichensatz und
   Trennzeichen werden erkannt).
2. Testlauf, es wird nichts gespeichert:

       cd /opt/mhvp
       ./mhvp.sh run --rm -v /opt/mhvp/import:/import:ro api \
         python -m mhvp.imports.objektdaten /import/objektdaten.csv \
         --tenant hausverwaltung-mueller --user timo@muellerhv.de

3. Bericht prüfen: übersprungene Objekte (Nummern zuordnen), Einheitenarten "other", Konflikte.
4. Übernahme mit denselben Parametern und zusätzlich `--apply`. Für die Liste vom 26.09.2026 hat
   der Betreiber die Nummern festgelegt: `--number-map 10012=012,10013=013,10014=014,999999=999`.
   Objekt 2911 (Schadestraße 3) bleibt ausgenommen, bis eine freie dreistellige Nummer benannt ist
   (291 ist durch Schadestraße 3a belegt).

       ./mhvp.sh run --rm -v /opt/mhvp/import:/import:ro api \
         python -m mhvp.imports.objektdaten /import/objektdaten.csv \
         --tenant hausverwaltung-mueller --user timo@muellerhv.de \
         --number-map 10012=012,10013=013,10014=014,999999=999 --apply
5. Im CRM unter Objekte die Anzahl und Stichproben prüfen (Bezeichnung, Verwaltungsart, Einheiten).

Ein zweiter Lauf mit derselben Datei ist unschädlich; er meldet alle Datensätze als unverändert.
