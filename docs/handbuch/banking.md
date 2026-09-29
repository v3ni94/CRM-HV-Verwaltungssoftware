# Banking

## Zweck

Der Bereich Bank zeigt Kontoauszüge (Dateiupload, finAPI oder FinTS) und schlägt Zuordnungen
zu offenen Posten vor. Die Anbindung ist lesend: keine Überweisung, keine automatische
Verbuchung. Die IBAN allein beweist keinen Schuldner; gebucht wird nur nach Bestätigung
und, bis zur Freigabestufe G1, nicht in der führenden Buchhaltung. Stand 28.09.2026 ist die
tägliche Bankarbeit vollständig in der Oberfläche: Buchen mit Gegenkonto, Teilbeträgen und
Splits, Ausgänge, Umbuchungen, Dublettenklärung, Massenbestätigung, Bankregeln und
Bankabstimmung (Regel UI-BANK-01).

## Einrichtung in drei Schritten

Der Abschnitt Einrichtung in drei Schritten (oben auf der Bankseite, Konto einrichten) führt ein
neues Bankkonto vom Bankzugang bis zur Buchung je Objekt:

1. Bankzugang: FinTS (PIN/TAN, Konten und Umsätze werden bei der Bank abgerufen; Bank
   verbinden öffnet den bekannten Dialog) oder Kontoauszug als Datei (CAMT.053, MT940, CSV;
   das Konto wird mit seiner IBAN angelegt, Auszüge werden danach unter Datei-Upload
   hochgeladen und über die IBAN erkannt).
2. Konto: bei FinTS ein noch nicht zugeordnetes Konto der Bankverbindung, beim Dateiweg die
   IBAN und der Bankname.
3. Objekt und Kontoart: Objekt wählen und die Kontoart festlegen (Mietkonto, WEG-Konto,
   Rücklagenkonto, Kautionskonto). Der Rechtsträger folgt aus dem Objekt: WEG-Konto und
   Rücklagenkonto gehören der Gemeinschaft, Mietkonto und Kautionskonto dem Eigentümer; die
   Verwaltung ist nie Inhaberin verwalteter Gelder (Regel B01). Gibt es mehrere passende
   Rechtsträger (mehrere Eigentümer), wird einer gewählt. Der Kontoinhaber wird mit dem Namen
   des Rechtsträgers vorbelegt.

Der Abschluss zeigt, was jetzt passiert: Umsätze dieses Kontos erscheinen in der Umsatzliste
und werden für das Objekt gegen einen Debitor (Mieter, Eigentümer) oder einen Kreditor
(Dienstleister) gebucht; Vorschläge sind keine Buchung. Kreditoren werden Kontakte: im
Buchungsdialog steht bei einem Ausgang an eine unbekannte Gegenpartei die Schaltfläche
Kreditor anlegen. Sie legt einen Kontakt mit der Rolle Dienstleister an, merkt die IBAN aus dem
Umsatz zur Freigabe durch eine zweite Person vor (nie automatisch freigegeben) und verknüpft
den Kreditor mit dem Objekt des Kontos (Reiter Dienstleister/Handwerker). Ist die Gegenpartei
laut IBAN oder Name schon Kontakt, zeigt der Dialog das mit dem Hinweis kein Beweis und bietet
nur die Verknüpfung an. Bis zur Freigabestufe G1 sind die Buchungen Vergleichsbuchhaltung.
Zuordnungen brauchen das Freigaberecht Bank (FinTS) oder das Schreibrecht Objekte (Dateiweg).

## Datei-Upload

Über Kontoauszug und Importieren lässt sich ein Auszug hochladen. Zulässig sind CAMT.053
(.xml), MT940 (.sta, .mt940, .940, .swi) und Bank-CSV (.csv). CAMT und MT940 werden direkt
importiert; die Ergebniszeile zeigt neue, bereits vorhandene und mögliche doppelte Umsätze
sowie Umbuchungen.

Eine CSV wird zuerst geprüft (CSV prüfen): Die Vorschau zeigt das erkannte Bankformat mit
Sicherheit, Zeichensatz, Trennzeichen, Zeilenzahl, die ersten Zeilen und Lesefehler je Zeile.
Ist das Format unbekannt, öffnet sich die Spaltenzuordnung: je Feld (Buchungstag, Betrag oder
Soll und Haben getrennt, Valuta, Gegenpartei, IBAN, Verwendungszweck, Referenzen) wird die
passende Spalte gewählt, Vorschau mit Zuordnung prüfen wiederholt die Prüfung. Eine Zuordnung
lässt sich je Bankkonto unter einem Namen speichern und beim nächsten Upload auswählen. CSV
importieren läuft erst, wenn die Vorschau keine Fehler meldet. Welche Bankformate verifiziert
sind, steht in `docs/integrations/bank-csv.md` (offener Punkt M11-02).

## Umsatzliste

Die Liste filtert nach Konto, Status (neu, prüfen, gebucht, ignoriert), Richtung (Eingänge,
Ausgänge) und Zeitraum und blättert in Seiten zu 50 Umsätzen (Zurück, Weiter). Je Zeile
stehen Buchungstag, Konto, Gegenpartei mit IBAN-Endung, Verwendungszweck, Betrag, Status und
die Aktionen: Buchen (öffnet den Buchungsdialog), Ignorieren mit Begründung (mindestens 3
Zeichen), Dublette klären, Regel lernen. Umbuchungen zwischen eigenen Konten tragen die
Kennzeichnung Umbuchung.

## Buchungsdialog

Buchen öffnet den Dialog zum Umsatz. Oben stehen die Vorschläge mit Quelle (Regel, Abgleich,
KI), Konfidenz und Begründung; Übernehmen füllt die Zuordnung mit den Splits des Vorschlags.
Nichts ist vorausgewählt. Darunter:

- Offene Posten: Suche nach Konto, Art oder Vertrag; Hinzufügen übernimmt den Posten mit
  dem Restbetrag, begrenzt auf den noch nicht zugeordneten Zahlbetrag. Der Teilbetrag je
  Posten lässt sich ändern; mehrere Posten sind möglich (Split). Beträge werden in der
  angezeigten Schreibweise eingegeben (1.250,00 oder 1250,00, auch 1250.00); ein nicht
  lesbarer Betrag wird als solcher gemeldet und sperrt das Buchen.
- Gegenkonto: Suche nach Nummer oder Name. Bank-, System- und inaktive Konten werden nicht
  angeboten. Ein Ausgang ohne offenen Posten wird gegen das Gegenkonto gebucht (zum Beispiel
  Bankgebühr gegen Kostenkonto).
- Buchungstext, optional. Skonto ist sichtbar, aber gesperrt, bis die Schnittstelle das Feld
  annimmt (offener Punkt BK2-01).
- Zahlbetrag, Zugeordnet und Rest: Eine Zuordnung über dem Zahlbetrag wird abgelehnt. Bleibt
  ein Rest, braucht er ein Gegenkonto; nur wenn alle Posten auf demselben Personenkonto
  liegen, darf der Rest als Guthaben stehen bleiben (D07).

Buchen zeigt eine Zusammenfassung mit Betrag und Zeilen; erst Buchung bestätigen bucht. Nach
der Buchung ist der Satz unveränderlich, Korrektur nur durch Storno und Neubuchung (B03).

Umbuchungen: Bei einem erkannten Transferpaar bietet der Dialog nur die anderen Bankkonten
des Buchungskreises an; das Konto der Gegenseite ist vorbelegt, wenn die Gegenseite auf
derselben Seite geladen ist. Die Buchung erledigt beide Hälften (D04, B08). Ist die
Gegenseite bereits anders gebucht (zum Beispiel Geldtransit), lässt sich die Hälfte über das
Kästchen gegen ein Gegenkonto buchen.

Ablehnen mit Grund gibt es für KI-Vorschläge; für deterministische Vorschläge folgt es mit dem
Entscheidungsprotokoll (Plan M12, Schritt S1; offener Punkt BK2-01).

## Dublettenklärung

Ein Umsatz im Status prüfen (Dublette?) wurde beim Import als möglicher Doppelumsatz erkannt.
Dublette klären verlangt eine Begründung und bietet Als echten Umsatz behalten (Status neu)
oder Als Dublette ignorieren. Nichts wird gelöscht (B08). Ignorierte Umsätze sind derzeit
endgültig; ein Wiedereröffnen folgt mit Schritt S1 (BK2-01).

## Massenbestätigung

Neue Umsätze der Seite auswählen oder einzelne Kästchen markieren, dann Massenbestätigung.
Der Dialog lädt die Vorschläge der gewählten Umsätze und bereitet nur deterministisch geprüfte
Fälle vor (eindeutiger Vollausgleich oder Treffer einer freigegebenen Regel); alle anderen
erscheinen als Ausnahme und bleiben manuell. Die Vorschau zeigt unter Buchbar nur die Umsätze,
die tatsächlich gebucht werden: von der Schnittstelle gemeldete Ausnahmen (Status, Umbuchung)
zählen nicht mit, weder in der Anzahl noch in der Summe oder den Summen je Rechtsträger, und
werden nicht gesendet. Erst die Bestätigung bucht, je Umsatz ganz oder gar nicht; das Ergebnis
nennt gebuchte und nicht gebuchte Umsätze mit Grund. Jede Buchung ist eine manuelle Buchung der angemeldeten Person.

## Automatik in Stufen

Einstellungen, Buchhaltung, Automatikstufen zeigt je Fallklasse die Stufe, den Deckel und
die Kennzahlen der letzten 90 Tage (Entscheidungen, Präzision der gezeigten Vorschläge,
Automatikbuchungen, Fehlerquote, Abdeckung). Fallklassen: Zahlungseingang mit Vollausgleich,
Sammelzahlung (höchstens L1), Rechnungszahlung mit verknüpfter Rechnung (höchstens L2),
wiederkehrender Aufwand gegen Sachkonto (höchstens L2, nur mit Ausgangsautomatik und Beleg),
Umbuchung zwischen eigenen Konten, Ausgeschlossen (Rückläufer, Kaution, Teil- und
Überzahlung, unklar; immer L0).

Stufen: L0 nur Vorschlag (Standard). L1 zeigt im Buchungsdialog Übernehmen für den
deterministisch geprüften Vorschlag und wählt ihn in der Massenbestätigung vor; jede Buchung
bleibt eine manuelle Buchung der angemeldeten Person, Verlauf und KI werden nie übernommen.
L2 bucht nach jedem Import und Abruf automatisch, wenn eine aktive Regel trifft und die Prüfung
der Klasse besteht (Betrag, ältester offener Posten des Schuldners, Konto ohne Steuerkennzeichen,
Periode offen); jede Automatikbuchung erscheint unter Bank, Nachkontrolle mit Fälligkeit am
nächsten Werktag. L3 ersetzt die Tagesprüfung durch eine Stichprobe (nur Vollausgleich und
Umbuchung, nicht vor der Freigabestufe G1 und der Betreiberentscheidung M12-08).

Anhebung: Stufe beantragen mit Grund; die Plattform prüft die Eignung (zum Beispiel L1 ab 20
Entscheidungen mit Präzision 95 Prozent) und lehnt sonst mit Hinweis ab. Eine andere Person gibt
den Antrag frei; wer beantragt hat, kann nicht freigeben. Absenken geht sofort. Überfällige
Nachkontrollen sperren die Klasse, eine hohe Fehlerquote senkt sie nachts automatisch. Der
Automatikschalter des Mandanten, das Entscheidungsprotokoll und der Schalter der
Ausgangsautomatik sind Voraussetzung; vor G1 bucht die Automatik nur im nicht führenden
Buchungskreis (Vergleichsbuchung, Betreiberentscheidung vom 28.09.2026).

## Buchung korrigieren

Eine gebuchte Buchung wird nie geändert. Korrigieren (Bank, Nachkontrolle, oder über die
Schnittstelle für jeden gebuchten Umsatz) storniert die gültige Buchung mit Grundcode
(Automatikfehler, falsche Zuordnung, falscher Betrag, falsches Datum, doppelt, sonstiges) und
Begründung und bucht den Umsatz im selben Schritt neu gegen das gewählte Gegenkonto. Für
einen Postenausgleich nach dem Storno den Buchungsdialog nutzen. Das Entscheidungsprotokoll
speichert die stornierte Buchung als Gegenbeispiel; bei Grundcode Automatikfehler wird die
Regel von aktiv auf freigegeben zurückgestuft, beim zweiten Fall abgeschaltet. In Ordnung
bestätigt die Automatikbuchung (Recht Nachkontrolle).

## Gelernte Regelvorschläge

Unter Bank, Bankregeln erscheinen Vorschläge, sobald dieselbe Gegenpartei im selben
Rechtsträger mehrfach gleich gebucht wurde (Standard fünf gleiche Entscheidungen, bei
gleichem Betrag drei; Einstellungen des Mandanten). Ein Widerspruch (anderes Konto, Ablehnung,
Storno) zieht den Vorschlag zurück. Annehmen legt die Regel im Zustand vorgeschlagen an; die
Betragsobergrenze darf dabei gesenkt, nie erhöht werden. Freigabe durch eine andere Person und
Aktivierung mit Betragsgrenze und Testnachweis bleiben Pflicht; die Aktivierung ersetzt ältere
gelernte Regeln derselben Gegenpartei. Ein Vorschlag bucht nichts.

## Regel lernen

Bei einem gebuchten Eingang legt Regel lernen einen Regelvorschlag aus IBAN-Fingerabdruck und
gebuchtem Konto an (Zustand vorgeschlagen). Der Vorschlag bucht nichts; Freigabe und
Aktivierung laufen unter Bankregeln.

## Bankregeln

Menü Bank, Bankregeln. Die Seite zeigt oben den Automatikschalter des Mandanten nur lesend
(Standard ausgeschaltet); das Einschalten setzt die offene Betreiberentscheidung zur Automatik
vor G1 (ADR 0014) und den Automatiklauf mit Nachkontrolle voraus (BK2-03).

Regel vorschlagen: Name, Rechtsträger, IBAN der Gegenpartei (gespeichert als Fingerabdruck),
Name enthält, Verwendungszweck als regulärer Ausdruck, Betragsspanne, Priorität und das Konto
der Buchung (Debitorenkonto; leer, wenn der eindeutige offene Posten das Konto bestimmt).
Die Priorität 0 wird als 0 gespeichert (0 zuerst); Beträge werden wie angezeigt eingegeben
(1.250,00), ein nicht lesbarer Betrag wird vor dem Senden gemeldet.
Bankkonto, Betrag und Zweck gelten zusammen; die IBAN allein beweist keinen Schuldner (7.4).

Lebenszyklus mit vier Augen: Freigeben ist für die vorschlagende Person gesperrt und
verlangt eine andere Person. Aktivieren verlangt eine Betragsgrenze und ein hochgeladenes
Testnachweis-Dokument (unabhängiger Testsatz nach D51, ein Backtest allein genügt nicht;
BK2-04). Abschalten beendet die Regel. Aktive und freigegebene Regeln liefern Vorschläge mit
Konfidenz im Buchungsdialog; gebucht wird weiterhin nur durch eine Person.

## Bankabstimmung

Menü Bank, Bankabstimmung: je Auszug Anfangsbestand, Bewegungen, Endbestand, Differenz des
Auszugs sowie Saldo des Sachkontos zum Stichtag und dessen Differenz (B09). Differenzen sind
rot hervorgehoben und ein Befund zur Klärung; die Ansicht korrigiert nichts. Ohne Salden im
Auszug oder ohne verknüpftes Sachkonto bleibt die Spalte leer.

## finAPI Bankanlage

Unter Einstellungen, Bank werden die finAPI-Zugangsdaten des Mandanten hinterlegt
(Basis-URL, Client-ID, Client-Secret, optional Mandator-ID, Sandbox-Kennzeichen). Ohne
diese Zugangsdaten zeigt die Bankverbindungsseite Bankanbindung noch nicht eingerichtet.

Eine Bankverbindung wird über Verbinden mit Bankname angelegt. Die eigentliche
Bankanmeldung samt IBAN und BIC läuft ausschließlich über das WebForm der Bank in einem
neuen Fenster (kein Bank-PIN oder TAN in der Plattform). Nach Abschluss des WebForms mit
Prüfen den Status abfragen. Möglicher Status: Angelegt, Bankfreigabe ausstehend,
Verbunden, Erneute Freigabe nötig, Zustimmung abgelaufen, Fehler, Getrennt.

**Diese Funktion braucht den finAPI-Vertrag**: Ohne aktivierten finAPI-Zugang (Client-ID
und Client-Secret eines abgeschlossenen finAPI-Vertrags) lässt sich keine Bankverbindung
verbinden. Details und offene Punkte in `docs/integrations/finapi.md` sowie
`docs/OPEN_QUESTIONS.md` (M11-40 bis M11-45).

## Zustimmung erneuern

Die Zustimmung der Bank zum Kontozugriff ist befristet. Zehn Tage vor dem Ablaufdatum
erhalten alle Benutzer mit Buchhaltungsrecht (Rollen mit accounting:update) eine
Benachrichtigung je Bankverbindung, einmal je Ablaufdatum. Auf der Bankverbindungsseite
erscheint ab diesem Zeitpunkt ein Hinweis mit dem Ablaufdatum und der Schaltfläche
Zustimmung erneuern; sie startet dasselbe WebForm der Bank wie Erneut freigeben. Eine
abgelaufene Zustimmung wird als Zustimmung abgelaufen markiert; bis zur Erneuerung werden
keine Umsätze abgerufen. Der Hinweis setzt voraus, dass ein Ablaufdatum bekannt ist
(finAPI liefert es derzeit nicht verifiziert, siehe `docs/integrations/finapi.md`).

## Umsätze abrufen

Nach Verbunden löst Umsätze abrufen einen Hintergrundlauf aus (Abruf eingereiht). Ein
automatischer, zeitgesteuerter Abruf findet nicht statt; jeder Abruf muss ausgelöst
werden.

## Zuordnung

Bankverbindung dauerhaft mit einem Buchungskreis oder Objekt verknüpfen (Zuordnen, ID
des internen Kontos). Je Umsatz zeigt die Spalte Vorschläge mögliche offene Posten;
Zuordnen und buchen verlangt eine Bestätigung des Betrags. Ohne passenden offenen Posten
lässt sich der Umsatz nur mit Begründung (mindestens 3 Zeichen) als Ignorieren
markieren.

## Entscheidungsprotokoll und Ablehnen (lernender Buchhalter)

Mit dem Mandantenschalter Lernender Buchhalter (Standard aus, Einstellungen des Mandanten,
nur mit Freigaberecht und Recht zur Mandantenkonfiguration, mit Grund) merkt sich die
Plattform je Bankumsatz, welche Vorschläge angezeigt wurden und was die Person daraus
gemacht hat: unverändert übernommen, geändert (mit Abweichung bei Posten, Gegenkonto oder
Skonto), abgelehnt mit Grund, ignoriert mit Grund oder nach einem Storno neu gebucht. Das
Protokoll ist nur Nachweis: es bucht nichts, es ändert keine Buchung und es öffnet keine
Freigabestufe. Die Aktivierung setzt die Datenschutzprüfung des Betreibers voraus
(offene Frage M12-06), bis dahin bleibt der Schalter aus.

Ablehnen: Passt kein Vorschlag, lehnt die Person die Vorschläge mit einem Grund von
mindestens drei Zeichen ab. Der Umsatz bleibt offen und kann später gebucht oder ignoriert
werden. Ein ignorierter Umsatz lässt sich mit Grund wieder eröffnen. Ein gebuchter Umsatz
wird nie geändert, sondern storniert (mit Grundcode, zum Beispiel falscher Posten oder
falscher Betrag) und einmal neu gebucht.

Veralteter Vorschlag: Ändern sich die Fakten (neuer offener Posten, freigegebene Regel),
erneuert die Plattform den Vorschlag im Hintergrund. Eine Buchung, die sich noch auf den
alten Vorschlag bezieht, wird mit dem Hinweis Vorschlag veraltet abgewiesen; nach dem Neuladen
der Vorschläge kann die Person erneut entscheiden.

Verlauf: Mit dem Schalter zeigt die Plattform ab der zweiten bestätigten Buchung derselben
Gegenpartei (gleiche IBAN oder Gläubiger-ID, gleicher Rechtsträger, gleiche Richtung) das
zuletzt gewählte Konto als Vorschlag Verlauf mit dem Hinweis zuletzt n mal so gebucht, k
Widersprüche und den Verweisen auf die Journalsätze. Ein Storno zählt sofort als Widerspruch
und senkt die Konfidenz. Ist eine gebuchte Rechnung mit dem Umsatz verknüpft, erscheint
ihre Kontierung (Kreditorenkonto, Kostenkonten der Positionen) als Vorschlag Rechnung.
Regelmäßigkeit (etwa monatlich) wird nur als Begründung genannt. Ein Vertrag, der vor dem
Buchungstag endete, schließt Regel und Verlauf aus. Alle diese Vorschläge sind nie
eindeutig und werden nie vorausgewählt; gebucht wird nur durch die Person.

## Zahlungsaufträge

Zahlungsaufträge (Menü Bank, Zahlungsaufträge) durchlaufen eine Freigabe durch zwei
verschiedene Personen; jede Änderung hebt bereits erteilte Freigaben auf. Die
Zahlungsdatei wird erst mit der Freigabestufe G2 erzeugt; Export oder Einreichung gilt
in keinem Fall als ausgeführte Zahlung.

## Was ist Vorschlag, was verbindlich

Vorschläge zur Zuordnung eines Umsatzes sind stets zu prüfen; Buchung bestätigen im
Buchungsdialog und die Bestätigung der Massenbestätigung sind die verbindlichen Handlungen.
Ein Regelvorschlag, eine freigegebene oder aktive Regel bucht nichts; der Automatiklauf ist
nicht Teil der Oberfläche. Eine Zahlungsauslösung bleibt bis zur Freigabestufe G2 vollständig
gesperrt.

## Häufige Fehler

- **Bankanbindung noch nicht eingerichtet**: finAPI-Zugangsdaten fehlen unter
  Einstellungen, Bank, oder der finAPI-Vertrag ist noch nicht abgeschlossen.
- **Status Erneute Freigabe nötig / Zustimmung abgelaufen**: Über Erneut freigeben ein
  neues WebForm öffnen und die Bankfreigabe wiederholen.
- **Umsätze abrufen bleibt ohne Ergebnis**: Verbindung steht nicht auf Verbunden; Prüfen
  auslösen und Status abwarten.
- **Kein passender offener Posten**: Den Umsatz gegen ein Gegenkonto buchen oder, wenn der
  Vorgang (Rechnung, Sollstellung) noch fehlt, mit Begründung ignorieren.
- **Der Restbetrag braucht ein Gegenkonto**: Die Zuordnung deckt den Zahlbetrag nicht; einen
  weiteren offenen Posten hinzufügen oder ein Gegenkonto wählen.
- **Das Bankkonto ist keinem Sachkonto zugeordnet**: Im Buchungskreis des Rechtsträgers fehlt
  das Sachkonto mit Verweis auf das Bankkonto; unter Buchhaltung anlegen.
- **Die Freigabe muss eine andere Person erteilen**: Regeln werden nie von der vorschlagenden
  Person freigegeben (Vier Augen).
