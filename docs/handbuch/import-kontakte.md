# Kontakte aus den Immoware24-Kontaktlisten anlegen

Stand 26.09.2026. Immoware24 exportiert je Kontaktgruppe eine Liste (Eigentümer, Mieter, Dienstleister,
Bank, Sonstige) mit den Spalten id, Name, Briefanrede, Benutzername, Adresse, Stadt, PLZ, Staat, Land,
Landesvorwahl, Vorwahl, Telefonnummer, E-Mail. Ein Befehl auf dem Server legt daraus die Kontakte
des gewählten Mandanten an; die Rolle (Eigentümer, Mieter, Dienstleister, Bank, Sonstiges) ergibt sich aus dem
Dateinamen oder wird als `ROLLE=PFAD` angegeben. Derselbe Import steht im CRM unter Importe,
Importassistent, Abschnitt "Immoware24-Listen" ohne Serverzugang zur Verfügung.

## Was angelegt wird

* Je Zeile ein Kontakt mit Rolle, Anschrift (Straße und Hausnummer getrennt, Land aus der
  Spalte Land, Vorgabe DE), Telefon in internationaler Schreibweise aus Landesvorwahl, Vorwahl und
  Nummer, E-Mail. Die Immoware24-Nummer bleibt als externe Kennung erhalten, ebenso der Name
  wie exportiert (für die Zuordnung zu Einheiten) und der Benutzername, falls vorhanden.
* Briefanrede und Staat (Bundesland) haben kein eigenes Feld; sie stehen als Notiz "laut
  Altsystem" am Kontakt.
* Personen und Firmen werden am Namen unterschieden (Rechtsform, Bank, Sparkasse, WEG, Stadt,
  Amt, Verein und weitere Schlüsselwörter; Banklisten immer Firma). "Nachname, Vorname" wird
  direkt übernommen. Bei "Vorname Nachname" entscheidet der Nachname aus der Briefanrede
  ("Sehr geehrte Frau Joachims"); fehlt er, gilt das letzte Wort als Nachname und der Bericht
  weist die Zeile aus. Anrede Herr oder Frau kommt aus der Briefanrede.
* Kontakte ohne Anschrift werden als unvollständig gekennzeichnet.
* Ungültige Telefonnummern oder E-Mail-Adressen werden nicht als Kontaktdaten gespeichert,
  sondern nur als Notiz "laut Altsystem" am Kontakt; der Bericht listet sie auf.
* Derselbe Kontakt in zwei Listen (zum Beispiel Eigentümer und Sonstige mit gleicher id) wird
  nur einmal angelegt und erhält beide Rollen.
* Es entstehen keine Verträge, Sollstellungen, Bankverbindungen oder Buchungen. Die Zuordnung
  zu Einheiten folgt mit `python -m mhvp.imports.zuordnung` (siehe `import-zuordnung.md`),
  über den Importassistenten (Verträge) oder manuell.

## Ablauf über die Oberfläche

1. Im CRM Importe, Importassistent öffnen und im Abschnitt "Immoware24-Listen" die Karte
   "Kontakte" verwenden. Erforderlich sind die Rechte des Importassistenten; Nur-Lese-Benutzer
   erhalten eine Ablehnung.
2. Bis zu vier CSV-Dateien wählen (UTF-8, Semikolon, wie exportiert, je höchstens 20 MB) und je
   Datei die Rolle festlegen (Eigentümer, Mieter, Bank, Sonstige). Die Rolle wird hier nicht aus
   dem Dateinamen abgeleitet, sondern immer aus der Auswahl.
3. Testlauf ausführen. Es wird nichts gespeichert. Der Bericht zeigt die Zählung und alle Zeilen
   mit Hinweisen oder Problemen (geratene Namensreihenfolge, ungültige Telefonnummern oder
   E-Mail-Adressen, unbekannte Länder, ungültige Zeilen).
4. Übernehmen ist erst nach einem Testlauf mit denselben Dateien und Rollen freigeschaltet und
   fragt vor dem Speichern nach.
5. Nach der Übernahme erscheint der Lauf unter Importe mit der Quelle "Immoware24-Liste:
   Kontakte". Er lässt sich dort zurücknehmen, soweit keine späteren Daten auf den Kontakten
   aufbauen. Eine nur ergänzte Rolle an einem vorhandenen Kontakt wird durch die Rücknahme
   nicht entfernt.

Über die Schnittstelle: `POST /api/v1/imports/immoware24/lists/kontakte?mode=preview` oder
`mode=apply` als multipart mit den Feldern `files` und `roles` in gleicher Reihenfolge (eine
Rolle je Datei: eigentuemer, mieter, dienstleister, bank, sonstige). Die Antwort ist der Bericht des Befehls,
bei Übernahme zusätzlich `import_run_id`.

## Ablauf auf dem Server

1. Die vier Dateien nach `/opt/mhvp/import/` legen (UTF-8, Semikolon, wie exportiert), zum
   Beispiel `eigentuemer.csv`, `mieter.csv`, `bank.csv`, `sonstige.csv`.
2. Testlauf, es wird nichts gespeichert; der Bericht zeigt Zählung und alle Zeilen mit Hinweisen:

       cd /opt/mhvp
       ./mhvp.sh run --rm -v /opt/mhvp/import:/import:ro api \
         python -m mhvp.imports.kontakte \
         /import/eigentuemer.csv /import/mieter.csv /import/bank.csv /import/sonstige.csv \
         --tenant hausverwaltung-mueller --user timo@muellerhv.de

3. Bericht prüfen (geratene Namensreihenfolge, ungültige Telefonnummern, unbekannte Länder).
4. Übernahme mit denselben Parametern und zusätzlich `--apply`.
5. Im CRM unter Kontakte die Anzahl je Rolle und Stichproben prüfen.

Ein zweiter Lauf mit denselben Dateien ist unschädlich; vorhandene Kontakte werden als
unverändert gemeldet. Erkennt der Befehl die Rolle nicht am Dateinamen, die Datei als
`mieter=/import/liste.csv` angeben.
