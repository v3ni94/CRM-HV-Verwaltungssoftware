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
