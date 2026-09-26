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
* Enthält eine Liste eine Spalte IBAN, wird die IBAN nur als Vorschlag im Bericht und als
  maskierte Notiz am Kontakt ausgewiesen (DE02 **** **** 2051), nie als Bankverbindung
  gespeichert. Bankverbindungen werden manuell erfasst und durch eine zweite Person freigegeben
  (Vier-Augen-Prinzip, Regel M19-05).
* Akademische Titel (Dr., Prof. Dr. med., Dipl.-Ing.) kommen in das Feld Titel; bei Firmen wird
  die Rechtsform (GmbH, GmbH & Co. KG, AG, e.V., eG, GbR, UG) zusätzlich im Feld Rechtsform
  abgelegt, der Firmenname bleibt vollständig.
* Hausnummern mit Zusatz (2a, 2 a, 3-5, 1/2) werden getrennt; ein Zusatz nach Komma ("Whg. 3")
  landet im Adresszusatz. Eine eigene Spalte Hausnummer wird bevorzugt. Zwei Anschriften in
  einem Feld bleiben als Text in der Straße.
* Telefonnummern werden in allen üblichen Schreibweisen zusammengesetzt (+49, 0049, 49, mit
  (0), Schrägstrichen, Bindestrichen, Leerzeichen); eine Nummer, die bereits mit + oder 00
  beginnt, hat Vorrang vor den Spalten Landesvorwahl und Vorwahl. Mehrere E-Mail-Adressen in einer
  Zelle (durch Semikolon oder Komma getrennt, auch "Name <adresse>") werden alle übernommen, die
  erste als Hauptadresse.
* Dieselbe id mehrfach in einer Datei wird nur einmal angelegt; die weiteren Zeilen erhalten den
  Status Duplikat mit Verweis auf die erste Zeile.

## Welche Exportvarianten gelesen werden

Der Import liest die Dateien so, wie Immoware24 oder Excel sie liefern, und weist im Bericht
unter "Hinweise zur Datei" aus, was er dabei angeglichen hat:

* Zeichensatz UTF-8 mit und ohne BOM, Windows-1252 (ANSI, Excel) und Latin-1.
* Trennzeichen Semikolon, Komma oder Tabulator, erkannt an der Kopfzeile; Anführungszeichen mit
  eingeschlossenen Trennzeichen und Zeilenumbrüchen.
* Leerzeichen am Zellenrand, leere Zeilen und wiederholte Kopfzeilen werden übersprungen.
* Beliebige Spaltenreihenfolge, zusätzliche Spalten werden ignoriert; Kopfzeilen werden ohne
  Rücksicht auf Schreibweise erkannt (id, ID; E-Mail, Email; Stadt, Ort; Telefonnummer,
  Telefon; Adresse, Straße).
* Fehlen die Pflichtspalten id oder Name, nennt die Meldung die fehlende Spalte und die
  gefundenen Spalten. Zeilen ohne id oder Name werden übersprungen und genannt.

## Vor dem Import prüfen

Checkliste für den Betreiber, bevor der Testlauf gestartet wird:

1. Richtigen Mandanten wählen; der Import einer Liste in den falschen Mandanten lässt sich nur
   über die Rücknahme des Importlaufs zurückholen.
2. Je Kontaktgruppe eine Datei exportieren und die Rolle je Datei festlegen (Oberfläche:
   Auswahl; Server: Dateiname oder `ROLLE=PFAD`). Eine falsche Rolle wird nicht automatisch
   korrigiert.
3. Datei einmal im Texteditor öffnen: Kopfzeile mit id und Name vorhanden, keine Summen- oder
   Vorschauzeilen, keine Spalte mit Bankdaten, die nicht im Bericht landen soll (eine IBAN wird
   nur maskiert ausgewiesen).
4. Immoware24-Nummern (id) dürfen zwischen den Listen übereinstimmen (derselbe Kontakt in zwei
   Gruppen erhält beide Rollen), innerhalb einer Liste kennzeichnet der Bericht Duplikate.
5. Testlauf ausführen und im Bericht prüfen: Hinweise zur Datei (Zeichensatz, Trennzeichen,
   übersprungene Zeilen), geratene Namensreihenfolge, ungültige Telefonnummern und
   E-Mail-Adressen, unbekannte Länder, Duplikate, ungültige Zeilen.
6. Zählung des Testlaufs mit dem Export vergleichen (Zeilen je Liste). Die Übernahme liefert
   dieselbe Zählung wie der Testlauf.
7. Nach der Übernahme einen zweiten Testlauf mit denselben Dateien starten: alle Kontakte müssen
   als unverändert gemeldet werden.

## Ablauf über die Oberfläche

1. Im CRM Importe, Importassistent öffnen und im Abschnitt "Immoware24-Listen" die Karte
   "Kontakte" verwenden. Erforderlich sind die Rechte des Importassistenten; Nur-Lese-Benutzer
   erhalten eine Ablehnung.
2. Bis zu vier CSV-Dateien wählen (wie exportiert, je höchstens 20 MB; Zeichensatz und
   Trennzeichen werden erkannt) und je
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

1. Die vier Dateien nach `/opt/mhvp/import/` legen (wie exportiert; Zeichensatz und
   Trennzeichen werden erkannt), zum
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
