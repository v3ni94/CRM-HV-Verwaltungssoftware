# Tickets

## Zweck

Tickets bilden Vorgänge aus Mail, Telefon oder Portal ab: Mängelmeldungen, Aufträge an
Dienstleister, interne Vorgänge. Jedes Ticket hat Status, Priorität, SLA-Frist, Checkliste
und Verlauf.

Im Ticketdetail stehen zusätzlich die interne Beschreibung (nur für Mitarbeiter, nie im
Portal, Feld Interne Beschreibung mit eigener Schaltfläche Speichern), die Kommentare mit
Autor, Sichtbarkeit und Anzahl der angehängten Dokumente, der Verlauf mit Details je Ereignis
(Statuswechsel von und nach, Zuweisung mit Name und Grund, Massenaktion, Bearbeiter) und die
Anhänge der eingegangenen Mails. Der Filter Meine zeigt Tickets, in denen der Benutzer Haupt-
oder Zusatzzuweiser ist.

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

Voraussetzungen: Mailverlauf lesen mit Tickets lesen und Freischaltung für das Postfach des
Tickets (Einstellungen, Postfächer; Standardpostfach oder Administrator); Antwort einreichen
mit Tickets ändern und Kommunikation ändern; Freigabe und Versand mit Kommunikation
freigeben durch eine andere Person als die, die den Entwurf erstellt oder eingereicht hat.

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
die Antwort als eingereichter Entwurf in den Postausgang. Ein Versandfehler erscheint
im Verlauf als fehlgeschlagen mit Fehlertext; der Entwurf bleibt zur erneuten Freigabe
erhalten.

Direktversand oder Freigabe (Betreiberentscheidung vom 26.09.2026): Wer das Recht
Kommunikation freigeben hat, versendet seine Antwort aus dem Ticket sofort über das Postfach
des Tickets; die Freigabe durch dieselbe Person wird protokolliert (Meldung Antwort direkt
versendet). Mitarbeiter mit dem Kennzeichen Freigabepflicht (Azubi oder neuer Mitarbeiter,
gepflegt unter Einstellungen, Benutzer, optional befristet) reichen ihre Antwort als Vorlage
ein: alle übrigen Freigabeberechtigten erhalten eine Benachrichtigung und finden die Vorlage
in ihrer Freigabeliste; eine zweite Person gibt im Postfach frei, der Verfasser selbst kann
nicht freigeben. Dasselbe gilt ohne das Recht Kommunikation freigeben und, unabhängig vom
Kennzeichen, wenn unter Einstellungen, Mandant die Notbremse Freigabe für alle aktiv ist.
Im Mailverlauf steht zu jeder Ausgangsmail, wer sie vorformuliert hat (mit Kennzeichen zum
Zeitpunkt) und wer sie wann freigegeben hat; im Ticketverlauf erscheinen die Ereignisse
Antwort vorformuliert, Antwort freigegeben und Antwort gesendet. Freie Mailentwürfe ohne
Ticket, Playbook-Antworten und Weiterleitungen bleiben beim Vier-Augen-Prinzip.

Zuordnung eingehender Antworten: Antworten mit passenden Thread-Kopfzeilen landen
automatisch im Ticket. Mails mit der Kennung TNR#<nummer> im Betreff werden dem Ticket
zugeordnet, wenn der Absender am Ticket beteiligt ist; sonst zeigt das Postfach nur einen
Vorschlag (mögliche Zuordnung zu TNR#...) und legt wie üblich ein neues Ticket an. Eine
Kundenantwort an ein erledigtes oder geschlossenes Ticket öffnet es wieder (Status in
Bearbeitung, Ereignis reopened); Bearbeiter und Zuweiser erhalten bei jedem Maileingang eine
Benachrichtigung. Der Mailverlauf zeigt nur Mails aus Postfächern, für die der Benutzer
freigeschaltet ist.

Schritt für Schritt (Antwort mit Vorlage):

1. Im Ticketdetail Antworten öffnen, Antwortvorlage wählen; die Vorschau mit ausgefüllten
   Platzhaltern (Anrede, Name, Objekt, Einheit, Ticketnummer, Datum) erscheint.
2. An, Kopie, Betreff (mit TNR#) und Text prüfen; offene Platzhalter im Text sperren den
   Versand (Hinweis Der Text enthält noch offene Platzhalter).
3. Anhänge prüfen, ergänzen (Dokument suchen, Datei hochladen) oder entfernen.
4. Antwort senden. Mit Freigaberecht und ohne Kennzeichen: Meldung Antwort direkt versendet,
   die Mail ist hinaus. Sonst Meldung Antwort eingereicht; Im Postfach öffnen führt zur
   Freigabe.
5. Bei eingereichter Vorlage gibt eine zweite Person im Postfach frei (Kapitel Mail); erst
   dann geht die Mail hinaus.

### Anhänge

Anhänge eingehender Mails erscheinen im Mailverlauf je Mail sowie gesammelt im Abschnitt
Anhänge aus E-Mails. PDF und Bilder (PNG, JPEG) lassen sich per Vorschau öffnen,
herunterladen und mit Als Beleg erfassen in den Belegeingang übernehmen (Kapitel
Belegeingang); andere Dateitypen sind als kein Beleg (Dateityp) gekennzeichnet. Ein
Anhang, dessen Dokument nicht mehr vorhanden ist, zeigt Dokument nicht mehr vorhanden.
Anhänge ausgehender Antworten stammen aus der Antwortvorlage, dem Dokumentenmodul oder
einem Upload; fehlt beim Versand eines dieser Dokumente, bricht der Versand ab, damit
keine unvollständige Antwort hinausgeht.

### Wiedereröffnung

Antwortet ein Kunde per Mail auf ein Ticket im Status erledigt, abgeschlossen oder
abgelehnt, öffnet die Plattform das Ticket wieder: Status In Bearbeitung, Ereignis reopened
im Verlauf, die SLA-Uhr läuft weiter, Bearbeiter und Zuweiser werden benachrichtigt. Die
zuvor archivierten Mails des Tickets bleiben archiviert; die neue Mail liegt im Posteingang.
Eine Wiedereröffnung von Hand erfolgt über den Status im Ticketdetail. Zusammengeführte
Quelltickets werden nicht wiedereröffnet; eine Antwort darauf gehört zum Zielticket.

### Terminvorschläge des Dienstleisters

Bei einem Auftrag an einen Dienstleister mit Portalzugang kann dieser nach Freigabe des
Auftrags bis zu drei Termine vorschlagen. Der betroffene Bewohner bestätigt einen davon im
Portal (Kapitel Portal); die Bestätigung setzt den Termin am Auftrag und erscheint als
Kommentar im Ticketverlauf. Bis dahin zeigt der Auftrag die offenen Vorschläge. Die
Verwaltung kann den Termin weiterhin über Termin anlegen im Kalender führen (siehe oben).

### Rückruf aus der Telefonie

Verpasste Anrufe und Anrufe von Kontakten mit offenem Ticket erzeugen am Kontakt einen
Vorschlag Rückruf. Ticket Rückruf anlegen legt ein Ticket mit Quelle Telefon an; ein
offenes Ticket wird als übergeordnetes Ticket verknüpft (Kapitel Kommunikation).

### Vorschläge aus der E-Mail (Stammdatenänderung)

Kündigt eine eingehende Mail eine Änderung der eigenen Stammdaten an (Anschrift, Telefon,
E-Mail, Name), zeigt das Ticket unter Vorschläge aus der E-Mail die erkannten Felder mit Alt
und Neu. Akzeptieren übernimmt sie in den Kontakt, Korrigieren erlaubt Änderungen vor der
Übernahme, Ablehnen verwirft mit optionalem Grund. Bankverbindungen werden nie
vorgeschlagen (Hinweis: Bankdaten werden nie automatisch übernommen, bitte manuell mit
Nachweis pflegen; Kapitel Kontakte, IBAN-Freigabe). Antwortentwurf legt eine vorbereitete
Antwort am Ticket an und reicht sie zur Freigabe ein.

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
