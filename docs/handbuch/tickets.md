# Tickets

## Zweck

Tickets bilden Vorgänge aus Mail, Telefon oder Portal ab: Mängelmeldungen, Aufträge an
Dienstleister, interne Vorgänge. Jedes Ticket hat Status, Priorität, SLA-Frist, Checkliste
und Verlauf.

## Anlegen und bearbeiten

Schaltfläche Ticket anlegen. Titel, Beschreibung, Priorität, optional eine Vorlage
(Vorlage, Feld Vorlage) mit vorbelegter Checkliste und Pflichtfeldern, zum Beispiel IBAN
beim Kautionsticket. Ohne ausgefüllte Pflichtfelder lässt sich das Ticket nicht
abschließen (Checkliste unvollständig).

## Sammelstatus

In der Ticketliste Zeilen markieren (Ticket auswählen, Alle auswählen) und über Status
anwenden gemeinsam auf einen neuen Status setzen. Mitarbeiter ohne Freigaberecht dürfen
höchstens 10 Tickets je Aufruf ändern, Administratoren unbegrenzt. Fehlgeschlagene Zeilen
werden einzeln ausgewiesen (Fehlgeschlagen / Geändert).

## Vorlagen

Unter Einstellungen, Ticketvorlagen werden Checklisten und Zusatzfelder für
wiederkehrende Vorgänge gepflegt (zum Beispiel Vermietung, Kaution). Eine Vorlage legt
Kategorie, Standardpriorität, Team und SLA-Regel fest.

## Zusammenführen

Im Ticketdetail über die Aktion Zusammenführen: Zielticket über Nummer oder Titel suchen,
Vorschau von Quell- und Zielticket prüfen, mit Zusammenführen bestätigen abschließen.
Danach:

- Das Quellticket wird geschlossen, verweist auf das Zielticket und ist für Bearbeitung,
  Checkliste und Kommentare gesperrt.
- Das Zielticket zeigt unter Enthält Ticket alle zusammengeführten Quelltickets.
- Die SLA-Uhr des Quelltickets wird als erledigt markiert, Bearbeiter des Quelltickets
  werden am Ziel ergänzt.

Zusammengeführte Tickets sind in der Liste standardmäßig ausgeblendet; der Filter
Zusammengeführte anzeigen zeigt sie wieder.

## Filter

Weitere Filter bietet die Ticketliste über Weitere Filter: Meine Tickets, Bearbeiter,
Objekt, Einheit, Kontakt, Rolle (Eigentümer/Mieter), Status, Priorität, Kategorie sowie
Erstellt ab/bis. Zurücksetzen löscht alle gesetzten Filter. Die freie Suche durchsucht
Nummer, Titel, Beschreibung, Kontakt und Adresse.

## Termin anlegen

Im Ticketdetail legt Termin anlegen einen Kalendertermin mit Bezug zum Ticket an (siehe
Kapitel Kalender). Der Termin ist zunächst unbestätigt; Einladungen an externe Beteiligte
gehen erst nach Bestätigung hinaus.

## Mailverlauf und Antworten

Im Ticket steht unter Mailverlauf jede ein- und ausgehende E-Mail chronologisch: Richtung
(Eingang, Ausgang), Status (neu, zugeordnet, Entwurf, zur Freigabe, gesendet,
fehlgeschlagen), Absender, Empfänger, Kopie, Datum, Betreff und Text. HTML-Mails werden
bereinigt angezeigt, mit Umschalter auf die Textansicht; zitierter Text älterer Mails ist
eingeklappt (Zitierten Text anzeigen). Je Mail sind die Anhänge mit Name, Größe und Typ
gelistet; Bilder und PDF lassen sich per Vorschau direkt öffnen, jede Datei herunterladen,
PDF- und Bildanhänge eingehender Mails zusätzlich als Beleg erfassen.

Antworten: Über Auf diese Mail antworten oder direkt im Formular Antworten. An und Kopie
sind aus der Ursprungsmail vorbelegt, jedoch nur mit am Ticket beteiligten Adressen
(Ticketkontakt, ursprünglicher Absender, Empfänger früherer Antworten). Ein fremder
Absender wird als Hinweis gezeigt und erst nach Klick auf Als Empfänger übernehmen
eingetragen. Der Betreff erhält automatisch die Kennung TNR#<Ticketnummer>, zum Beispiel
"AW: Wasserschaden Küche TNR#412", immer genau einmal. Der Text ist frei oder aus einer
Antwortvorlage (Einstellungen, Antwortvorlagen); Anhänge kommen aus der Vorlage, über
Dokument suchen aus dem Dokumentenmodul oder per Datei hochladen. Mit Antwort senden geht
die Antwort als eingereichter Entwurf in den Postausgang; versendet wird erst nach der
Vier-Augen-Freigabe im Postfach über das Postfach des Tickets. Ein Versandfehler erscheint
im Verlauf als fehlgeschlagen mit Fehlertext; der Entwurf bleibt zur erneuten Freigabe
erhalten.

Zuordnung eingehender Antworten: Antworten mit passenden Thread-Kopfzeilen landen
automatisch im Ticket. Mails mit der Kennung TNR#<nummer> im Betreff werden dem Ticket
zugeordnet, wenn der Absender am Ticket beteiligt ist; sonst zeigt das Postfach nur einen
Vorschlag (mögliche Zuordnung zu TNR#...) und legt wie üblich ein neues Ticket an. Eine
Kundenantwort an ein erledigtes oder geschlossenes Ticket öffnet es wieder (Status in
Bearbeitung, Ereignis reopened); Bearbeiter und Zuweiser erhalten bei jedem Maileingang eine
Benachrichtigung. Der Mailverlauf zeigt nur Mails aus Postfächern, für die der Benutzer
freigeschaltet ist.

## Abschluss archiviert Mails

Jeder Abschlussstatus (erledigt, abgeschlossen, abgelehnt) archiviert automatisch die zum
Ticket gehörenden Mails im Postfach. Maßgeblich bleibt die Postfach-Einstellung zur
Archivierung (Einstellungen, Postfächer).

## Was ist Vorschlag, was verbindlich

Die automatische Bearbeiterzuweisung (nach Postfach, Anrede, Signatur, Kompetenz und
bisheriger Zuordnung) sowie KI-Vorschläge zu Kategorie und Antwort sind Vorschläge und
müssen durch einen Mitarbeiter bestätigt werden. Fristzusagen, Kündigungen oder
Zahlungszusagen in einem Ticket sind vor verbindlicher Erklärung mit der Geschäftsführung
abzustimmen.

## Häufige Fehler

- **Zusammenführen schlägt fehl, Zielticket nicht gefunden**: Suche nach Nummer oder
  Titel liefert kein Ergebnis (Kein passendes Ticket gefunden); Schreibweise prüfen, ein
  bereits zusammengeführtes Ticket kann nicht erneut Ziel sein.
- **Sammelstatus bricht mit Fehlgeschlagen ab**: einzelne Tickets erfüllen die
  Checkliste nicht oder sind bereits gesperrt (zusammengeführt); diese Zeilen einzeln im
  Ticketdetail prüfen.
- **Ticket lässt sich nicht abschließen**: Checkliste unvollständig, Pflichtfelder der
  Vorlage fehlen.
