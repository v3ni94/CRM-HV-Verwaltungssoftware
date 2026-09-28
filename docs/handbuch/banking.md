# Banking

## Zweck

Der Bereich Bank zeigt Kontoauszüge (Dateiupload, finAPI oder FinTS) und schlägt Zuordnungen
zu offenen Posten vor. Die Anbindung ist lesend: keine Überweisung, keine automatische
Verbuchung. Die IBAN allein beweist keinen Schuldner; gebucht wird nur nach Bestätigung
und, bis zur Freigabestufe G1, nicht in der führenden Buchhaltung. Stand 28.09.2026 ist die
tägliche Bankarbeit vollständig in der Oberfläche: Buchen mit Gegenkonto, Teilbeträgen und
Splits, Ausgänge, Umbuchungen, Dublettenklärung, Massenbestätigung, Bankregeln und
Bankabstimmung (Regel UI-BANK-01).

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
  Posten lässt sich ändern; mehrere Posten sind möglich (Split).
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
erscheinen als Ausnahme und bleiben manuell. Die Vorschau zeigt Anzahl, Summe, Summen je
Rechtsträger und die von der Schnittstelle gemeldeten Ausnahmen (Status, Umbuchung). Erst die
Bestätigung bucht, je Umsatz ganz oder gar nicht; das Ergebnis nennt gebuchte und nicht
gebuchte Umsätze mit Grund. Jede Buchung ist eine manuelle Buchung der angemeldeten Person.

## Regel lernen

Bei einem gebuchten Eingang legt Regel lernen einen Regelvorschlag aus IBAN-Fingerabdruck und
gebuchtem Konto an (Zustand vorgeschlagen). Der Vorschlag bucht nichts; Freigabe und
Aktivierung laufen unter Bankregeln.

## Bankregeln

Menü Bank, Bankregeln. Die Seite zeigt oben den Automatikschalter des Mandanten nur lesend
(Standard ausgeschaltet); das Einschalten setzt die offene Betreiberentscheidung zur Automatik
vor G1 (ADR 0013) und den Automatiklauf mit Nachkontrolle voraus (BK2-03).

Regel vorschlagen: Name, Rechtsträger, IBAN der Gegenpartei (gespeichert als Fingerabdruck),
Name enthält, Verwendungszweck als regulärer Ausdruck, Betragsspanne, Priorität und das Konto
der Buchung (Debitorenkonto; leer, wenn der eindeutige offene Posten das Konto bestimmt).
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
