# Banking

## Zweck

Der Bereich Bank zeigt Kontoauszüge (Dateiupload oder finAPI) und schlägt Zuordnungen zu
offenen Posten vor. Die Anbindung ist lesend: keine Überweisung, keine automatische
Verbuchung. Die IBAN allein beweist keinen Schuldner; gebucht wird nur nach Bestätigung
und, bis zur Freigabestufe G1, nicht in der führenden Buchhaltung.

## Datei-Upload

Über Kontoauszug (CAMT.053) und Importieren lässt sich ein Auszug hochladen. Die Liste
zeigt Buchungstag, Gegenpartei, Verwendungszweck und Betrag je Umsatz, mit Kennzahlen zu
neuen, bereits vorhandenen und möglichen doppelten Umsätzen sowie Umbuchungen.

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

## Zahlungsaufträge

Zahlungsaufträge (Menü Bank, Zahlungsaufträge) durchlaufen eine Freigabe durch zwei
verschiedene Personen; jede Änderung hebt bereits erteilte Freigaben auf. Die
Zahlungsdatei wird erst mit der Freigabestufe G2 erzeugt; Export oder Einreichung gilt
in keinem Fall als ausgeführte Zahlung.

## Was ist Vorschlag, was verbindlich

Vorschläge zur Zuordnung eines Umsatzes zu einem offenen Posten sind stets zu prüfen;
Zuordnen und buchen ist die verbindliche Handlung. Eine Zahlungsauslösung bleibt bis zur
Freigabestufe G2 vollständig gesperrt.

## Häufige Fehler

- **Bankanbindung noch nicht eingerichtet**: finAPI-Zugangsdaten fehlen unter
  Einstellungen, Bank, oder der finAPI-Vertrag ist noch nicht abgeschlossen.
- **Status Erneute Freigabe nötig / Zustimmung abgelaufen**: Über Erneut freigeben ein
  neues WebForm öffnen und die Bankfreigabe wiederholen.
- **Umsätze abrufen bleibt ohne Ergebnis**: Verbindung steht nicht auf Verbunden; Prüfen
  auslösen und Status abwarten.
- **Kein passender offener Posten**: Zuordnung ist nicht möglich, bis der zugehörige
  Vorgang (Rechnung, Sollstellung) im System angelegt ist; bis dahin mit Begründung
  ignorieren.
