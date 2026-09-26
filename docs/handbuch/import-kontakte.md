# Kontakte aus den Immoware24-Kontaktlisten anlegen

Stand 26.09.2026. Immoware24 exportiert je Kontaktgruppe eine Liste (Eigentümer, Mieter, Bank,
Sonstige) mit den Spalten id, Name, Briefanrede, Benutzername, Adresse, Stadt, PLZ, Staat, Land,
Landesvorwahl, Vorwahl, Telefonnummer, E-Mail. Ein Befehl auf dem Server legt daraus die Kontakte
des gewählten Mandanten an; die Rolle (Eigentümer, Mieter, Bank, Sonstiges) ergibt sich aus dem
Dateinamen oder wird als `ROLLE=PFAD` angegeben.

## Was angelegt wird

* Je Zeile ein Kontakt mit Rolle, Anschrift (Straße und Hausnummer getrennt, Land aus der
  Spalte Land, Vorgabe DE), Telefon in internationaler Schreibweise aus Landesvorwahl, Vorwahl und
  Nummer, E-Mail. Die Immoware24-Nummer bleibt als externe Kennung erhalten (auch der
  Benutzername, falls vorhanden).
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
  zu Objekten und Einheiten folgt über den Importassistenten (Verträge) oder manuell.

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
