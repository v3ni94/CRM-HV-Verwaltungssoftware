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

## Vorgangsarten und Prozessflows

Jede eingehende Mail erhält im KI-Vorschlag eine Vorgangsart aus einem festen Katalog:
Kündigung, Vermietung, Versicherungsschaden, Reparaturanfrage, Beschwerde, Buchhaltung,
Übergabe, Mieterhöhung, Gericht, Übernahme neues Objekt, Abgabe altes Objekt, Kaution. Die
Vorgangsart wird zuerst aus Schlüsselwörtern in Betreff und Text bestimmt und, wenn ein
KI-Anbieter freigegeben ist, durch die KI ergänzt. Angezeigt werden Vorgangsart, Sicherheit in
Prozent und der Grund (die gefundenen Wörter oder der Grund der KI). Die Sicherheit ist ein
Hinweis, keine Freigabe.

Schaltfläche Vorgangsart übernehmen an der Mail: legt das Ticket an, falls noch keines
besteht (Kontakt und Objekt aus der Zuordnung der Mail), und wendet den Prozessflow der
Vorlage an. Am Ticket selbst steht im Abschnitt Prozessflow die Auswahl der Vorgangsart mit
Flow anwenden. Angewendet wird:

- Kategorie und Vorgangsart (Badge in Liste und Detail, Filter Vorgangsart in der Liste).
- Checkliste der Vorlage, einmalig; vorhandene Punkte und Haken bleiben erhalten.
- Zuständige Rolle (Anzeige, keine automatische Zuweisung an eine Person).
- Erforderliche Verknüpfungen (Kontakt, Einheit, Objekt, Vertrag) mit Status vorhanden oder
  fehlt.
- Fristvorschläge: nur der Fristtyp aus dem Katalog (zum Beispiel Kündigung, Vertragsende,
  Auszug). Datum und Dauer trägt der Bearbeiter am Ticket (Fälligkeit) oder im Kalender ein;
  es wird keine Frist automatisch angelegt.
- Zu sammelnde Unterlagen als Liste.

Ein zweites Anwenden derselben Vorgangsart verdoppelt nichts. Status, Abschluss, Buchungen
und Zahlungen bleiben unberührt. Eine Automatisierungsregel kann die Vorgangsart über die
Aktion Feld setzen (Feld Vorgangsart) anwenden.

Unter Einstellungen, Ticketvorlagen legt Prozesskatalog einspielen für jede Vorgangsart eine
Vorlage an, sofern noch keine besteht; bestehende Vorlagen bleiben unverändert. Je Vorlage
lassen sich Vorgangsart, zuständige Rolle, erforderliche Verknüpfungen, verknüpfte Fristtypen
und Unterlagen bearbeiten. Die Checklisten der eingespielten Vorlagen folgen den
Handlungsanweisungen zu Mieterwechsel, Übergabe, Kaution, Mieterhöhung und Verwalterwechsel.

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
Nummer, Titel, Beschreibung, Kontakt und Adresse sowie Betreff und Absender der
verknüpften Mails und die E-Mail-Adresse des Kontakts.

Erledigte Vorgänge (Status erledigt, abgeschlossen, abgelehnt) sind in der Ticketübersicht,
in Meine Tickets, in der Mailübersicht und im Reiter Tickets der Kontakt-, Objekt- und
Einheitenseite standardmäßig ausgeblendet (seit 1.23.0, Reiter seit 1.28.0). Der Umschalter
Erledigte anzeigen blendet sie ein; ein ausdrücklich gesetzter Statusfilter zeigt immer genau
die gewählten Status. Eingeblendete erledigte Tickets erscheinen grün und stehen am Ende.

## Ampel und Sortierung

Jede Ticketzeile trägt seit 1.28.0 eine Farbmarke am linken Rand mit Text (Legende über der
Liste):

- Gelb: neues Ticket, noch ohne Reaktion.
- Orange: seit 24 Stunden keine Reaktion unsererseits.
- Rot: seit 96 Stunden keine Reaktion unsererseits.
- Grün: erledigt, abgeschlossen oder abgelehnt (nie orange oder rot).

Als Reaktion zählen nur Handlungen von Mitarbeitern: Statuswechsel, Zuweisung, interner oder
öffentlicher Kommentar, gesendete Mail, angelegter oder geänderter Arbeitsauftrag. Eingehende
Mails, Portalkommentare von Mietern oder Eigentümern und Erinnerungen von außen setzen die Uhr
nicht zurück; die letzte Nachricht des Kunden wird getrennt ausgewiesen. Bei einem neuen
Ticket ohne Reaktion zählt die Zeit seit Eingang. Der Text nennt die Dauer, zum Beispiel Seit
4 Tagen ohne Reaktion.

Die Übersicht ist standardmäßig nach Dringlichkeit sortiert, auch über Seiten hinweg: rot
oben (am längsten ohne Rückmeldung zuerst), dann orange, dann gelb und die übrigen offenen,
Erledigte zuletzt. Der Filterhaken Nach Eingang sortiert stattdessen das neueste Ticket nach
oben. Die offenen Tickets auf der Startseite tragen dieselbe Ampel.

## Status und Rollen

Die Statusauswahl im Ticket richtet sich nach der Rolle. Mitarbeiter sehen nur die
zulässigen Folgestatus (neu nach in Bearbeitung, wartend, erledigt oder abgelehnt; in
Bearbeitung nach wartend, erledigt oder abgelehnt; wartend zurück nach in Bearbeitung;
erledigt nach abgeschlossen oder zurück nach in Bearbeitung; abgelehnt zurück nach in
Bearbeitung; abgeschlossen ist Endstatus). Mandantenadministratoren (Recht Tickets löschen)
dürfen jeden Status in jeden anderen setzen, ohne Zwischenschritte; ein solcher Wechsel steht
im Verlauf mit dem Kennzeichen admin_override. Die Abschlussprüfungen (Checkliste,
Pflichtfelder der Vorlage, Erledigungsnotiz) gelten auch für Administratoren.

## Erledigungsnotiz beim Abschluss

Jeder Wechsel auf erledigt, abgeschlossen oder abgelehnt verlangt eine Erledigungsnotiz
(seit 1.24.0): eine Art aus der Liste des Mandanten und ein Freitext. Eingebaut sind
Stammdaten ergänzt, Handwerker beauftragt, Auskunft erteilt, Weitergeleitet, Kein
Handlungsbedarf, Abgelehnt, Zahlung geklärt, Termin vereinbart, Mangel behoben, Vertrag
geändert, Sonstiges (Betreiberentscheidung vom 26.09.2026); bei Sonstiges ist der Freitext
Pflicht, sonst freiwillig. Welche Arten der Dialog anbietet, legt der Mandant unter
Einstellungen, Mandant und Briefbogen, Erledigungsarten fest: eingebaute Arten lassen sich
abschalten (Sonstiges und Zusammengeführt bleiben immer), eigene Arten kommen mit Code und
Bezeichnung hinzu (Kapitel Einstellungen). Der Abschlussdialog lädt diese Liste beim Öffnen.
Er erscheint im Ticketdetail, in der Sammelaktion Status anwenden (eine gemeinsame Notiz für
alle gewählten Tickets) und beim Zusammenführen (gemeinsame Notiz für die Quelltickets; ohne
Eingabe erhalten sie die Art Zusammengeführt mit Verweis auf das Zielticket). Ohne
Erledigungsnotiz lehnt die Plattform den Abschluss ab (Meldung Beim Abschluss ist eine
Erledigungsnotiz erforderlich); eine abgeschaltete oder unbekannte Art wird mit der Meldung
Erledigungsart ist für diesen Mandanten nicht verfügbar abgewiesen.

Die Notiz steht am Ticket (Art, Text, wer abgeschlossen hat) und im Verlauf beim
Statuswechsel. Wird ein Ticket wiedereröffnet, werden Art und Text geleert; beim nächsten
Abschluss ist eine neue Notiz nötig.

### Lernen aus Erledigungen

Jeder Abschluss wird als Lernbeispiel gespeichert (Betreff, Anliegen als Auszug, Kategorie,
Thema, erkanntes Objekt, Einheit und Kontakt; Ergebnis Art, Text, Status und die zuletzt
versendete Antwort als Auszug). Dabei läuft kein KI-Aufruf. Aus einem abgeschlossenen Ticket
gelernte Playbooks erhalten zusätzlich den Schritt Erledigung mit der Notiz; ein bereits
vorhandenes ähnliches Playbook wird um diesen Schritt ergänzt. Bei neuen Mails zeigt der
KI-Vorschlag unter Bei ähnlichen Vorgängen wurde die drei ähnlichsten Erledigungen (Abgleich
über Schlagwörter in Betreff und Anliegen, ohne Anbieteraufruf). Beispiele und Playbooks sind
unter Einstellungen, Wissen einsehbar (Kapitel Einstellungen). Das Lernbeispiel ist ein
Vorschlagsgedächtnis, keine Anweisung: Vorschläge werden weiterhin durch einen Mitarbeiter
bestätigt.

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

Passende Playbooks: Hat das Ticket eine Kategorie oder Vorgangsart, zeigt das Antwortformular
die freigegebenen Playbooks (Einstellungen, Wissen) mit Antworttext, deren Kategorie oder
Schlagwort der Kategorie oder Vorgangsart entspricht, mit Anzahl der Nutzungen. Die Auswahl
erfolgt im Browser, da die Playbook-Liste nur nach Status und Titel filtert; ein Objektbezug
ist bei Playbooks nicht hinterlegt, das Objekt des Tickets grenzt daher nicht ein. Einfügen
übernimmt den Antworttext in den Entwurf (bei vorhandenem Text darunter angehängt), sendet
aber nichts. "passt" und "passt nicht" zählen die Rückmeldung am Playbook (sichtbar unter
Einstellungen, Wissen); die Nutzungszahl steigt nur beim Anwenden aus der Mail, nicht beim
Einfügen im Ticket. Antwortvorlagen bleiben der verbindliche Weg, Playbooks sind eine
Empfehlung.

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
Kundenantwort an ein erledigtes oder geschlossenes Ticket öffnet es innerhalb der Frist des
Mandanten wieder (Status in Bearbeitung, Ereignis reopened), danach entsteht ein
Folgevorgang (Abschnitt Wiedereröffnung); Bearbeiter und Zuweiser erhalten bei jedem
Maileingang eine Benachrichtigung. Der Mailverlauf zeigt nur Mails aus Postfächern, für die der Benutzer
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
abgelehnt, öffnet die Plattform das Ticket wieder, wenn der Abschluss höchstens 30
Kalendertage zurückliegt (Frist je Mandant unter Einstellungen, Mandant, Wiedereröffnung
abgeschlossener Tickets per E-Mail; der Tag des Abschlusses und der 30. Tag zählen mit):
Status In Bearbeitung, Ereignis reopened im Verlauf, die SLA-Uhr läuft weiter, Bearbeiter
und Zuweiser werden benachrichtigt. Die zuvor archivierten Mails des Tickets bleiben
archiviert; die neue Mail liegt im Posteingang. Eine Wiedereröffnung von Hand erfolgt über
den Status im Ticketdetail. Zusammengeführte Quelltickets werden nicht wiedereröffnet; eine
Antwort darauf gehört zum Zielticket.

Liegt der Abschluss länger zurück, bleibt das Ticket abgeschlossen und die Mail erhält ein
neues Ticket, den Folgevorgang (Regel M19-10). Er übernimmt Objekt, Einheit und Kontakt des
alten Tickets. Im neuen Ticket steht der Hinweis Folgevorgang zu Ticket mit Verweis auf das
alte, im alten Ticket der Hinweis Folgevorgang mit Verweis auf das neue; beide Tickets
erhalten dazu einen internen Kommentar und einen Eintrag im Verlauf, die Bearbeiter des
alten Tickets eine Benachrichtigung. Weitere Mails im alten Mailverlauf landen danach im
Folgevorgang. Automatische Antworten wie Abwesenheitsnotizen, die der Absender technisch als
solche kennzeichnet, öffnen kein Ticket wieder und legen keinen Folgevorgang an; sie werden
nur am Ticket abgelegt.

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

### Anrufe über die Telefonassistenz (Hallo Heidi)

Die KI-Telefonassistenz Hallo Heidi schickt je Anruf ein Gesprächsprotokoll per Mail an das
Postfach; daraus entsteht wie bei jeder Mail ein Ticket. Erkannt wird eine solche Mail am
Absendermuster (Standard hallo-heidi, halloheidi, hallo.heidi), am Kennwort im Betreff
(Standard hallo heidi) oder am Kennwort im Text, letzteres nur zusammen mit einer
beschrifteten Rufnummer, damit eine Anrede an eine Mitarbeiterin nicht als Anruf zählt.
Muster und Kennwörter sind je Mandant unter Einstellungen, Postfächer, Telefonassistenz
änderbar; dort lässt sich die Erkennung auch abschalten.

Aus dem Protokoll liest die Plattform Anrufernummer, Anrufername, Objekt (Nummer oder
Anschrift), Einheit (Whg., WE, Etage) und Anliegen zunächst regelbasiert; die KI-Aufgabe
Anrufzusammenfassung ergänzt nur fehlende Angaben, sieht Rufnummern und Kennungen maskiert
und ist ein Vorschlag. Die Zuordnung des Anrufers läuft in dieser Reihenfolge: Objekt über
Nummer oder Anschrift, dann Personen mit laufendem Miet- oder Eigentumsvertrag an diesem
Objekt per Namensabgleich; ohne Objekt der Name allein, aber nur bei genau einem Treffer
(mehrere Treffer erscheinen als Kandidaten); zuletzt eine eindeutige Rufnummer. Kontakt,
Objekt und Einheit werden am Ticket gesetzt, soweit noch leer; das Ergebnis steht als
Ereignis Anrufzusammenfassung im Verlauf.

Ist die Anrufernummer beim zugeordneten Kontakt noch nicht hinterlegt, entsteht unter
Vorschläge aus der E-Mail der Vorschlag Stammdaten ergänzen: Telefonnummer mit Antwortentwurf
zum Anliegen (aus einem passenden Playbook, sonst ein allgemeiner Text). Akzeptieren übernimmt
nur die Nummer; Freigeben und antworten übernimmt die Nummer und legt die Antwort als
Entwurf am Ticket an, gerichtet an die E-Mail-Adresse des Anrufers. Versendet wird nichts
automatisch; der Entwurf geht den üblichen Weg über Einreichen und Freigabe (Kapitel Mail).
Hat der Kontakt keine E-Mail-Adresse, bleibt der Entwurf ohne Empfänger und ist vor dem
Einreichen zu ergänzen.

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
Ticket gehörenden Mails im Postfach. Maßgeblich bleibt die Postfach-Einstellung Erledigt
archiviert (Einstellungen, Postfächer). Dieselbe Einstellung archiviert seit dem 26.09.2026
auch eine einzelne Mail, die im Posteingang auf erledigt gesetzt wird.

## Abschluss per Mail

Wird die letzte offene eingegangene Mail eines Tickets im Posteingang auf erledigt gesetzt und
hat das Ticket keinen offenen Arbeitsauftrag, schließt die Plattform das Ticket automatisch
mit der Erledigungsart Auskunft erteilt und der Notiz Per E-Mail erledigt; Verfasser ist der
Bearbeiter der Mail, der Verlauf zeigt den Statuswechsel als automatisch. Solange noch eine
eingegangene Mail des Tickets offen ist oder ein Arbeitsauftrag läuft, bleibt das Ticket
offen. Ist die Erledigungsart Auskunft erteilt für den Mandanten deaktiviert oder scheitert
eine Abschlussprüfung, bleibt das Ticket offen und der Verlauf zeigt ein Hinweis-Ereignis mit
Grund. Erledigt meint in allen Fällen erledigt, abgeschlossen oder abgelehnt.

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
  Vorlage fehlen oder die Erledigungsnotiz fehlt (bei Sonstiges auch der Freitext).
- **Ticket ist aus der Liste verschwunden**: Es ist erledigt, abgeschlossen oder abgelehnt
  und deshalb ausgeblendet; Erledigte anzeigen einschalten oder den Statusfilter setzen.
- **Anruf-Mail wurde nicht als Anruf erkannt**: Absendermuster oder Kennwort passen nicht,
  oder das Kennwort steht nur im Text ohne beschriftete Rufnummer; Einstellungen, Postfächer,
  Telefonassistenz prüfen.

## Rechnungskopie aus Lexware Office

Bittet ein Kontakt um eine bereits gestellte Rechnung, entsteht am Ticket eine Anfrage mit der
erkannten Rechnungsnummer; nach Prüfung des Empfängers wird die Rechnungsdatei abgerufen und
ein Antwortentwurf an die bekannte Adresse erstellt (zweite Freigabe). Die Karte
"Rechnungskopie aus Lexware Office" im Ticket zeigt Status, Treffer und Empfängerprüfung und
bietet Anfordern, Korrigieren, Empfänger verknüpfen, Abrufen und Ablehnen. Details in
[Lexware Office](lexware-office.md), Abschnitt Rechnungskopie.

## Aufträge, Teams, Kommentare und Dokumente (Paket P11)

* Unter Aufträge (`/auftraege`) stehen alle Arbeitsaufträge mit Filter nach Status, Verweis auf das Ticket und den Auftrag mit Terminvorschlägen.
* Teams lassen sich über die Schnittstelle ändern und löschen, solange dem Team keine Tickets oder Vorlagen zugeordnet sind.
* Kommentare am Ticket werden archiviert, nicht gelöscht. Der Text bleibt als Nachweis gespeichert, ist aber in der Ticketansicht und im Portal nicht mehr sichtbar.
* Der Reiter Dokumente im Ticket zeigt nur Dokumente mit Bezug zum Ticket (Titel, Dateiname oder Schlagwort nennt "Ticket <Nummer>"), zum Kontakt (Korrespondent) oder zum Objekt. Ohne Bezug erscheint eine leere Liste mit Hinweis. Dokumente, die nur dieselben Ziffern enthalten, werden nicht mehr angezeigt.
* Dienstleister können im Portal einen Auftrag annehmen, mit Begründung ablehnen und den Stand ihrer Rechnungseinreichung sehen. Jede Änderung erscheint im Ticketverlauf.

## Gespeicherte Filter und Sammelzuweisung (30.09.2026)

Über der Ticketliste speichert die Leiste Gespeicherte Filter die aktuelle Suche und Filter unter
einem Namen; ein Klick auf den Namen stellt sie wieder her. Dieselbe Leiste steht in der
Objektliste, der Vertragsliste und der Dokumentenliste. Gespeicherte Filter gehören der
angemeldeten Person.

Die Schnittstelle `POST /workspace/bulk` mit der Aktion `tickets.assign` weist mehrere Tickets
einer Person zu (Recht Tickets bearbeiten). Die Aktion gilt ganz oder gar nicht: Ist ein Ticket
unbekannt oder zusammengeführt, ändert sich nichts. Verlauf, Benachrichtigung und Ereignis
entstehen wie bei der Einzelzuweisung. Eine Bedienung in der Liste gibt es dafür noch nicht;
die Statusänderung mehrerer Tickets steht in der Liste bereits zur Verfügung.

## Kompaktansicht im Ticket

Im Ticket erscheint zur letzten eingegangenen Mail dieselbe Kompaktansicht wie im Postfach (Zusammenfassung, offene Punkte, CRM Hinweis, Antwortvorschlag, Kurz senden mit Freigabe). Details siehe Kapitel Mail.

## Gebäude, Beginn, Wiedervorlage und Sammelzuweisung (Paket Q05, 30.09.2026)

* **Neues Ticket**: Optional Objekt (Suche), Gebäude des Objekts, Beginn und Wiedervorlage. Leere Felder werden nicht gesendet.
* **Ticket bearbeiten**: Beginn, Wiedervorlage und Gebäude werden direkt geändert, "Entfernen" löscht ein Datum. Das Gebäude kann erst gewählt werden, wenn dem Ticket ein Objekt zugeordnet ist, ein Gebäude eines anderen Objekts lehnt die Schnittstelle ab.
* **Sammelzuweisung** (Ticketliste): Tickets markieren, in der unteren Leiste "Bearbeiter zuweisen" öffnen, Bearbeiter wählen und zuweisen. Die Aktion gilt ganz oder gar nicht, Verlauf und Benachrichtigung entstehen wie bei einer Einzelzuweisung. Recht Tickets ändern nötig.
* **Teams**: Einstellungen, Teams. Anlegen, Umbenennen, Mitglieder ändern und Löschen (Recht Tickets freigeben). Ein Team mit zugeordneten Tickets oder Vorlagen lässt sich nicht löschen.
* **Sammelaktion Status mit Bericht** (API `POST /tickets/bulk`): Status und gemeinsame Erledigungsnotiz für mehrere Tickets. Jedes Ticket wird einzeln verarbeitet, der Bericht nennt je Ticket Erfolg oder den Fehlercode; ein Fehler bricht die übrigen nicht ab. Es gelten dieselben Regeln und Grenzen wie bei der Statusänderung in der Liste.
* **Auftragstermin**: Sobald im Auftrag der Schritt Termin gesetzt wird (auch durch den Dienstleister im Portal), erscheint der Termin sofort im internen Kalender. Es wird keine Einladung versendet.

## Sammelaktionen in der Ticketliste (Priorität, Team, Bearbeiter)

Tickets in der Liste markieren, in der unteren Leiste Status anwenden oder "Bearbeiter zuweisen" öffnen, dort Bearbeiter, Team und Priorität wählen (einzeln oder kombiniert) und anwenden. Danach erscheint ein Bericht "Geändert: x von y" mit den nicht geänderten Tickets und dem Grund. Ohne Freigaberecht sind höchstens 10 Tickets je Aufruf möglich.

## Verlauf bei Priorität und Team

Ändern Sie Priorität oder Team eines Tickets, einzeln oder per Sammelaktion, erscheint im Ticketverlauf ein Eintrag mit altem und neuem Wert, dem Bearbeiter und bei der Sammelaktion dem Hinweis Massenaktion. Gleiche Werte erzeugen keinen Eintrag.
