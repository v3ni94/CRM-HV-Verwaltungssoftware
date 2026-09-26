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

## Ablauf über die Oberfläche

1. Im CRM Importe, Importassistent öffnen und im Abschnitt "Immoware24-Listen" die Karte
   "Objektdaten" verwenden. Erforderlich sind die Rechte des Importassistenten (KI anlegen sowie
   Objekte, Kontakte und Verträge anlegen); Nur-Lese-Benutzer erhalten eine Ablehnung.
2. CSV-Datei wählen (UTF-8, Semikolon, wie exportiert, höchstens 20 MB). Im Feld
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

## Adressen nachtragen (Schritt 1a)

Die Objektliste aus Immoware24 enthält keine Adressspalten. Nach dem Import fehlen deshalb Straße, Hausnummer, PLZ und Ort. Auf der Seite Importe, Immoware24 Listenimport, Abschnitt "1a. Adressen nachtragen", gibt es zwei Wege. Beide füllen nur leere Felder, überschreiben nie und können beliebig oft wiederholt werden. Je Weg erst Testlauf, dann Übernehmen; jede Übernahme erscheint als Importlauf (`immoware24:adressen-ableiten` bzw. `immoware24:adressen`).

**Aus Objektnamen ableiten.** Für alle Objekte ohne Straße werden Straße und Hausnummer aus der Bezeichnung gewonnen. Kennzeichen wie `Z ABGEGEBEN`, `Y ABRECHNUNG` und ein führendes `WEG` werden vorher entfernt. Beispiele:

| Bezeichnung | Straße | Hausnummer |
|---|---|---|
| Shalomweg 3 | Shalomweg | 3 |
| Z ABGEGEBEN Brunnenstraße 145 | Brunnenstraße | 145 |
| WEG Am Panke Park 67-85 | Am Panke Park | 67-85 |
| Am Panke Park 1-21 H1 | Am Panke Park | 1-21 H1 |

Namen ohne erkennbare Hausnummer (zum Beispiel "Garagenhof Nord") werden als nicht erkennbar gemeldet und bleiben leer. PLZ und Ort lassen sich aus dem Namen nicht ableiten.

**Adressliste hochladen.** CSV (UTF-8) oder Excel (xlsx) mit einer Kopfzeile. Erkannte Spalten:

- Objektnummer: `Objekt-Nummer`, `Objektnummer`, `Objekt-Nr.`; Immoware24-Formen wie `82`, `082` oder `82.0` werden wie beim Objektimport auf drei Stellen gebracht.
- Straße: `Straße`, `Strasse`, `Str.`; steht die Hausnummer mit in dieser Spalte und fehlt eine eigene Spalte, wird sie abgetrennt.
- Hausnummer: `Hausnummer`, `Nr.`
- PLZ: `PLZ`, `Postleitzahl`
- Ort: `Ort`, `Stadt`

Weicht ein Wert der Liste von einem bereits gefüllten Feld ab, wird das als Konflikt gemeldet (Zeile, Objekt, Feld, vorhandener Wert, Wert laut Liste) und nicht übernommen. Objektnummern, die im Mandanten nicht vorhanden sind, werden unter "Nicht zugeordnet" aufgeführt.

## Ablauf auf dem Server

1. Datei nach `/opt/mhvp/import/objektdaten.csv` legen (UTF-8, Semikolon, wie exportiert).
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
