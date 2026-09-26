# Objekte und Einheiten aus der Immoware24-Objektliste anlegen

Stand 26.09.2026. Die Objektliste (Export "Objektdaten", eine Zeile je Einheit mit Objekt-Nummer,
Objekt, Verwaltungsart, Gebäude, VE-Nummer, VE-Beschreibung, VE-Lage, aktueller Eigentümer oder
Mieter und vereinbartem Zahlbetrag) wird mit einem Befehl auf dem Server als Objekte und
Einheiten des gewählten Mandanten angelegt.

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
