# DATEV-Importtest mit der Steuerberatung

Stand 27.09.2026. Gilt für alle Mandanten. Ziel ist der Nachweis, dass der Buchungsstapel
der Plattform in DATEV importiert werden kann, bevor die Freigabestufe G1 (produktive
Buchhaltung) beantragt wird. Der Importtest ist eine Betreiberaufgabe mit der
Steuerberatung; die Plattform liefert Testdatei, Prüfbericht und Begleitschreiben.

## Ablauf

1. Unter Einstellungen, Mandant, Rechnungsstellung und Steuer die DATEV-Kennzahlen
   eintragen: Beraternummer, Mandantennummer, Kontenrahmen (SKR03 oder SKR04),
   Sachkontenlänge, Wirtschaftsjahresbeginn.
2. Unter Einstellungen, Buchhaltung, DATEV im Abschnitt Testdatei für den Importtest die
   Datei `EXTF_Buchungsstapel_Importtest.csv` herunterladen. Sie enthält 20 fiktive,
   als Testbuchung gekennzeichnete Buchungen auf vierstelligen Beispielkonten und die
   Kennzahlen des Mandanten (ohne Kennzahlen Platzhalter, die die Steuerberatung ersetzt).
3. Die Datei mit dem Begleitschreiben (unten) an die Steuerberatung geben. Die
   Steuerberatung importiert sie in einen Testmandanten oder verwirft den Stapel nach dem
   Import, damit keine Testbuchungen in der Buchführung verbleiben.
4. Rückmeldung der Steuerberatung dokumentieren: importiert ohne Befund, importiert mit
   Hinweisen (welche Felder), abgelehnt (Fehlermeldung von DATEV). Die Rückmeldung als
   Dokument ablegen und in OPEN_QUESTIONS M18-01 vermerken.
5. Erst danach den ersten echten Buchungsstapel eines Buchungskreises erzeugen, unter
   Einstellungen, Buchhaltung, DATEV formal prüfen und mit dem Prüfbericht an die
   Steuerberatung geben.

## Formale Selbstprüfung

Jeder DATEV-Export wird gespeichert und kann im Abschnitt Formale Prüfung des
Buchungsstapels geprüft werden (Recht Buchhaltung exportieren). Der Bericht listet jeden
Befund mit Regel, Zeile, Feld und Quellenstatus:

- belegt: in öffentlich dokumentierten Beispielen des DATEV-Formats nachgewiesen. Ein
  Verstoß ist ein Fehler.
- zu prüfen: gängige Praxis, in dieser Aufgabe nicht gegen die DATEV-Schnittstellenbeschreibung
  verifiziert. Ein Verstoß ist ein Hinweis, den die Steuerberatung bestätigt oder verwirft.

Bekannter Befund: der produktive Export schreibt derzeit je Journalzeile eine Stapelzeile
ohne Gegenkonto. Wie Konto und Gegenkonto aus den Journalzeilen zu bilden sind, wird mit
der Steuerberatung festgelegt (OPEN_QUESTIONS M18-01). Bis dahin ist der Buchungsstapel
mit Echtdaten nicht importfähig; die Testdatei ist davon nicht betroffen.

## Begleitschreiben (Entwurf, Gesellschaft je Mandant einsetzen)

Betreff: Importtest DATEV-Buchungsstapel, Testdatei mit 20 fiktiven Buchungen

Sehr geehrte Damen und Herren,

wir stellen die Buchhaltung der von uns verwalteten Objekte auf eine eigene
Verwaltungsplattform um. Die Plattform übergibt Buchungen künftig als DATEV-Buchungsstapel
im DATEV-Format (Kopfzeile EXTF, Versionsnummer 700, Datenkategorie 21, Formatversion 7).

Anbei erhalten Sie die Testdatei `EXTF_Buchungsstapel_Importtest.csv`. Sie enthält 20
fiktive, als Testbuchung gekennzeichnete Buchungen auf Beispielkonten. Die Datei enthält
keine Echtdaten und keine personenbezogenen Daten. Beraternummer, Mandantennummer,
Kontenrahmen und Sachkontenlänge in der Kopfzeile entsprechen den uns vorliegenden Angaben;
bitte korrigieren Sie diese, falls sie nicht zutreffen.

Wir bitten Sie um folgende Prüfung:

1. Import der Datei in einen Testmandanten oder Verwerfen des Stapels nach dem Import.
2. Rückmeldung, ob der Import ohne Beanstandung möglich war; andernfalls die Fehlermeldung
   von DATEV mit Angabe des betroffenen Feldes.
3. Rückmeldung zu folgenden Punkten, die wir nicht abschließend klären konnten:
   Anzahl der Kopfzeilenfelder, erwarteter Zeichensatz (ANSI oder UTF-8), Schreibweise
   des Kontenrahmens in der Kopfzeile (03 oder SKR03), Sachkontenlänge, zulässige Längen
   von Buchungstext und Belegfeld 1, Verwendung des BU-Schlüssels.
4. Abstimmung, in welcher Form Splitbuchungen mit mehr als zwei Konten übergeben werden
   sollen (Sammelkonto oder Einzelpaare).

Nach Ihrer Rückmeldung stimmen wir die Kontenzuordnung je Konto mit Ihnen ab und übergeben
den ersten echten Buchungsstapel eines Objekts mit dem zugehörigen Prüfbericht.

Mit freundlichen Grüßen

(Unterschrift, Gesellschaft, Pflichtangaben laut Briefbogen der handelnden Gesellschaft)

Hinweis: Das Schreiben ist ein Entwurf. Vor dem Versand die handelnde Gesellschaft
(Hausverwaltung Müller GmbH oder anderer Mandant) festlegen und den jeweiligen Briefbogen
verwenden. Der Versand erfolgt durch den Betreiber.
