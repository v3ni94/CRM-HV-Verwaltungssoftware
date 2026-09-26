# Eigentümer und Mieter den Einheiten zuordnen

Stand 26.09.2026. Die Objektliste aus Immoware24 (Export "Objektdaten") nennt je Einheit den
aktuellen Eigentümer und den aktuellen Mieter mit dem vereinbarten Zahlbetrag. Der Befehl
`python -m mhvp.imports.zuordnung` verknüpft diese Namen mit den bereits importierten Kontakten
und legt daraus Verträge mit monatlicher Sollstellung an.

## Reihenfolge

Die drei Befehle bauen aufeinander auf. Jeder Schritt läuft zuerst als Testlauf (ohne
`--apply`, es wird nichts gespeichert), der Bericht wird geprüft, danach folgt derselbe Aufruf
mit `--apply`.

1. Objekte und Einheiten: `python -m mhvp.imports.objektdaten` (siehe `import-objektdaten.md`).
2. Kontakte: `python -m mhvp.imports.kontakte` mit allen Kontaktlisten, also Eigentümer, Mieter,
   Dienstleister und Sonstige (siehe `import-kontakte.md`).
3. Zuordnung: `python -m mhvp.imports.zuordnung` mit derselben Objektliste wie in Schritt 1.

## Was angelegt wird

* Eigentümer bei Verwaltungsart "WEG-Verwaltung" und "WEG mit SE-Verwaltung": Vertrag der Art
  Eigentum, Gläubiger ist die Gemeinschaft der Wohnungseigentümer. Der Zahlbetrag wird als
  Hausgeld (Zahlungsart `hoa_fee`) monatlich zum 1. angelegt.
* Mieter bei Verwaltungsart "Mietverwaltung" und "WEG mit SE-Verwaltung": Vertrag der Art
  Mietverhältnis, der Zahlbetrag wird als Miete (Zahlungsart `rent`) monatlich zum 1. angelegt.
  In Objekten mit SE-Verwaltung erhält das Eigentum der vermieteten Einheit das Kennzeichen SEV;
  Vermieter ist der Eigentümer.
* Vertragspartei ist die Partei des Kontakts (Rolle Hauptpartei), die der Kontaktimport angelegt
  hat; fehlt sie, wird sie angelegt. Je Partei und Einheit entsteht das Debitorenkonto im
  Nummernkreis 090000 bis 099999.
* Der Kontakt erhält die Rolle Eigentümer oder Mieter.
* Beträge werden mit Komma als Dezimalzeichen gelesen (1.019,71 ergibt 1.019,71 EUR), ohne
  Umsatzsteuer. Leere Beträge ergeben einen Vertrag ohne Sollstellung, der Bericht weist ihn aus.
* Vertragsbeginn ist `--start-date JJJJ-MM-TT`. Ohne Angabe gilt der 01.01. des laufenden
  Jahres. Das ist eine Annahme, der Bericht nennt sie; die tatsächlichen Beginn- und
  Übergabedaten sind je Vertrag nachzupflegen.

## Regeln zum Namensabgleich

* Verglichen wird nur mit Kontakten, die eine Immoware24-Nummer tragen (Bestand aus dem
  Kontaktimport). Groß- und Kleinschreibung, mehrfache Leerzeichen und "u." statt "&" spielen
  keine Rolle.
* Gibt es mehrere Kontakte mit demselben Namen, wird nicht geraten. Der Bericht listet die
  Einheit unter "mehrdeutig" mit den Kandidaten (Immoware24-Nummer und Name). Die Zuordnung
  erfolgt dann im CRM von Hand.
* "Leerstand" als Mieter bedeutet keine Zuordnung und wird gezählt.

## Wiederholung und Konflikte

* Ein zweiter Lauf ist unschädlich. Besteht für die Einheit bereits ein aktiver Vertrag gleicher
  Art mit derselben Partei, zählt er als "bereits vorhanden".
* Besteht ein aktiver Vertrag mit einer anderen Partei, wird nichts geändert; der Bericht führt
  die Einheit unter "Konflikte".
* Ebenfalls unter "Konflikte" stehen Mietverhältnisse, für die kein Vermieter feststeht. In
  Objekten mit Mietverwaltung muss dazu zuerst der Eigentümer des Objekts im CRM erfasst sein,
  in Objekten mit SE-Verwaltung ein Eigentum mit SEV zum Vertragsbeginn.

## Bericht

Einheiten gesamt, Eigentümer zugeordnet, Mieter zugeordnet, Leerstand, nicht gefunden (Liste),
mehrdeutig (Liste), Konflikte (Liste), angelegte Parteien, Verträge und Zahlungen sowie die
Monatssummen für Hausgeld und Miete. Einheiten, die Schritt 1 nicht angelegt hat (zum Beispiel
Objekte ohne dreistellige Nummer), erscheinen als Hinweis "Einheit nicht importiert".
Mit `--skip-handed-over` bleiben Einheiten abgegebener Objekte (Präfix "Z ABGEGEBEN") ohne
Zuordnung.

## Ablauf auf dem Server

`./mhvp.sh` ist der Wrapper um `docker compose` (siehe `docs/runbooks/server-setup.md`),
`run --rm` startet einen einmaligen Container des Dienstes `api` mit der Datei als Volume.

1. Objektliste nach `/root/import/neuObjektdaten.csv` legen (UTF-8, Semikolon, wie exportiert).
2. Testlauf:

       cd /opt/mhvp
       ./mhvp.sh run --rm -v /root/import:/import api \
         python -m mhvp.imports.zuordnung /import/neuObjektdaten.csv \
         --tenant <slug> --user timo@muellerhv.de

3. Bericht prüfen: mehrdeutige Namen, nicht gefundene Namen, Konflikte, Annahme zum
   Vertragsbeginn.
4. Übernahme mit denselben Parametern und zusätzlich `--apply`:

       ./mhvp.sh run --rm -v /root/import:/import api \
         python -m mhvp.imports.zuordnung /import/neuObjektdaten.csv \
         --tenant <slug> --user timo@muellerhv.de --apply

5. Im CRM unter Verträge Stichproben prüfen (Partei, Beginn, Hausgeld oder Miete).

Die Verträge und Sollstellungen sind Übernahmedaten aus dem Altsystem. Vor der ersten
Sollstellung oder Buchung sind Beträge und Beginn mit den Unterlagen abzugleichen und von der
Geschäftsführung freizugeben.
