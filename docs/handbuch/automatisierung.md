# Automatisierung (Regel-Engine)

Stand 26.09.2026, Version 1.22.1.

## Zweck

Unter Einstellungen, Automatisierung werden Regeln nach dem Muster "Wenn ein Ereignis
eintritt oder ein Zeitpunkt erreicht ist, dann führe Aktionen aus" gepflegt. Die Regeln
entlasten von Routinearbeit im Ticketwesen (Ticket anlegen, Bearbeiter setzen, intern
benachrichtigen) und bereiten Kommunikation vor (E-Mail-Entwurf, Brief-Entwurf, Webhook,
KI-Aufgabe).

Regeln lösen niemals Buchungen, Zahlungen, Freigaben oder Mailversand aus. Ein
E-Mail-Entwurf aus einer Regel bleibt ein Entwurf im Postfach des Tickets und durchläuft die
Vier-Augen-Freigabe wie jede andere Antwort (Kapitel Mail). Ein Brief-Entwurf wird als
Dokument abgelegt und nicht versendet. Eine KI-Aufgabe liefert nur einen Vorschlag.

## Voraussetzungen

| Tätigkeit | Recht |
| --- | --- |
| Regeln und Protokoll lesen | Mandanteneinstellungen lesen oder Tickets lesen |
| Regel anlegen, ändern, aktivieren, deaktivieren, Testlauf | Mandanteneinstellungen ändern |
| Regel löschen | Mandanteneinstellungen löschen (in der Vorbelegung nur Administrator) |

Für die Aktion Ticket aus Vorlage anlegen muss eine Ticketvorlage bestehen (Einstellungen,
Ticketvorlagen), für E-Mail-Entwurf eine Antwortvorlage (Einstellungen, Antwortvorlagen),
für Brief-Entwurf eine Briefvorlage (Kapitel Dokumente und DMS). Die Aktion KI-Aufgabe
setzt einen freigegebenen KI-Anbieter mit Budget voraus (Einstellungen, KI); ohne Freigabe
wird die Aufgabe nicht gestartet.

## Stufe 1 und Stufe 2

Stufe 1 (seit 1.21.0) umfasst die drei Aktionen Ticket aus Vorlage anlegen, Interne
Benachrichtigung und Ticketfeld setzen (Priorität, Team, Kategorie, Bearbeiter) mit dem
Auslöser Ereignis.

Stufe 2 (seit 1.22.0) ergänzt die Aktionen Webhook senden, E-Mail-Entwurf aus
Antwortvorlage, Brief-Entwurf aus Briefvorlage und KI-Aufgabe starten sowie die Auslöserart
Zeitplan.

## Aufbau einer Regel

Neue Regel öffnet das Formular:

1. Name (je Mandant eindeutig) und Beschreibung.
2. Auslöserart: Ereignis oder Zeitplan.
   - Ereignis: Ereignistyp aus der Liste (Ticket angelegt, Ticket zusammengeführt, SLA
     eskaliert, Kontakt geändert, Dokument angelegt, Objekt angelegt, Einheit angelegt,
     Inserat angelegt, Import übernommen, Zahlungsauftrag zurückgegeben, Portalzugang
     eingeladen) oder Anderer Ereignistyp mit Code, zum Beispiel `ticket.status_changed`.
   - Zeitplan: Häufigkeit täglich, wöchentlich (mit Wochentag) oder monatlich (Tag 1 bis
     28, damit die Regel in jedem Monat läuft) mit Uhrzeit in Europe/Berlin.
3. Bedingungen: Verknüpfung alle treffen zu (und) oder eine trifft zu (oder), je Zeile
   Feld (Ticket Kategorie, Priorität, Thema, Titel, Team, Quelle, Status; Ereignis Quelle,
   Nummer; oder Anderes Feld mit Feldpfad), Operator (gleich, ungleich, enthält, größer als,
   kleiner als) und Wert. Ohne Bedingung gilt die Regel für jedes Ereignis des Auslösers.
   Verschachtelte Bedingungen sind nur in der Expertenansicht (JSON) möglich.
4. Aktionen, in der angegebenen Reihenfolge:

| Aktion | Angaben | Wirkung |
| --- | --- | --- |
| Ticket aus Vorlage anlegen | Ticketvorlage, Titel (leer = Titel der Vorlage), Objekt, Einheit oder Kontakt aus dem Ereignis übernehmen | Neues Ticket mit Checkliste und SLA der Vorlage |
| Interne Benachrichtigung | Titel und Text (Platzhalter in geschweiften Klammern, zum Beispiel Ticketnummer), Rollen oder Benutzer | Hinweis im Menü Benachrichtigungen |
| Ticketfeld setzen | Feld Priorität, Team, Kategorie oder Bearbeiter und Wert | Ändert das Ticket des Ereignisses; nur bei Auslöser Ereignis mit Ticketbezug |
| Webhook senden | Ziel-URL (nur https), Geheimnis zur Signatur (mindestens 16 Zeichen), Zusatzfelder | Signierter Aufruf (HMAC SHA-256) mit Regel, Ereignis und Ticketfeldern; genau ein Versuch je Lauf, ohne Wiederholung |
| E-Mail-Entwurf aus Antwortvorlage | Antwortvorlage | Entwurf im Postfach des Tickets; Freigabe und Versand bleiben manuell; nur bei Auslöser Ereignis mit Ticketbezug |
| Brief-Entwurf aus Briefvorlage | Briefvorlage, Empfänger (Kontakt-ID, leer = Kontakt des Tickets, auf einem Zeitplan Pflicht), Unser Zeichen, Platzhalterfelder | Brief auf dem Briefbogen als Dokument; nichts wird versendet |
| KI-Aufgabe starten | Aufgabe (Zusammenfassen, Antwortentwurf, Frage beantworten, E-Mail einordnen), Anweisung mit Platzhaltern | KI-Lauf über den Gateway; Ergebnis ist ein Vorschlag |

Die Satzvorschau unter dem Formular ("Wenn ..., dann ...") zeigt die Regel in Worten.
Speichern legt die Regel inaktiv an; Aktivieren schaltet sie scharf.

Das Geheimnis eines Webhooks wird verschlüsselt gespeichert und nie wieder angezeigt; beim
Bearbeiten bleibt es erhalten, solange das Feld Neues Geheimnis leer bleibt.

## Zeitpläne

Eine Zeitplanregel läuft je Termin genau einmal. Termine vor der Aktivierung werden nicht
nachgeholt; die erste Prüfung nach der Aktivierung setzt nur die Startmarke. Wird der
Zeitplan geändert, beginnt die Zählung neu beim nächsten Termin. Aktionen, die ein Ticket
brauchen (Ticketfeld setzen, E-Mail-Entwurf), sind auf einem Zeitplan nicht wählbar; das
Formular weist sie ab.

## Testlauf

Testlauf öffnet einen Dialog mit Beispiel Ticketfelder (JSON) und Beispiel Ereignisdaten
(JSON); bei einer Zeitplanregel wird der nächste Termin geprüft. Testlauf starten wertet die
Regel aus und zeigt entweder Regel greift mit der Vorschau je Aktion, Bedingungen treffen
nicht zu oder Der Ereignistyp passt nicht zum Auslöser der Regel. Es wird nichts angelegt,
gesetzt, gesendet oder in die Warteschlange gestellt; ein Testlauf hinterlässt keinen
Protokolleintrag.

## Protokoll

Der Reiter Protokoll listet je Lauf Uhrzeit, Regel, Ereignis, Ergebnis (ausgeführt,
fehlgeschlagen) und die ausgeführten Aktionen; Filter nach Regel. Es wird nur ein Lauf
geschrieben, wenn die Bedingungen der Regel zutrafen. Ein fehlgeschlagener Lauf zeigt den
Fehlertext; die übrigen Regeln laufen unabhängig weiter.

Hinweise zur Verarbeitung:

- Ereignisse werden im Hintergrund jede Minute verarbeitet, ein Lauf je Regel und Ereignis
  (keine Doppelausführung).
- Aktionen einer Regel lösen keine weitere Regel aus (Schleifenschutz).
- Löschen einer Regel entfernt auch ihr Protokoll; Deaktivieren erhält es.

## Grenzen

- Keine Buchung, keine Zahlung, keine Freigabe, kein Mailversand, keine Statusänderung von
  Beschlüssen oder Abrechnungen durch Regeln.
- Ein Regel-Webhook wird ohne Wiederholungsplan zugestellt (Betreiberentscheidung M9-08
  offen). Für zuverlässige Anbindung von Fremdsystemen sind die Webhook-Abonnements des
  Mandanten mit Wiederholung gedacht (Kapitel Kommunikation).
- Private Netzwerkziele werden abgewiesen, sofern der Betreiber sie nicht ausdrücklich für
  die Entwicklung freigegeben hat.

## Häufige Fehler

- **Speichern abgewiesen: Eine Regel mit diesem Namen existiert**: Namen sind je Mandant
  eindeutig, anderen Namen wählen.
- **Aktion auf Zeitplan nicht wählbar**: Ticketfeld setzen und E-Mail-Entwurf brauchen ein
  Ticket aus einem Ereignis; Auslöserart auf Ereignis umstellen oder andere Aktion wählen.
- **Webhook ohne Geheimnis**: Ein Webhook wird nur mit Geheimnis (mindestens 16 Zeichen)
  gespeichert.
- **Regel greift im Testlauf, im Betrieb passiert nichts**: Regel ist inaktiv (Aktivieren),
  oder das Ereignis lag vor der Aktivierung.
- **Lauf fehlgeschlagen bei KI-Aufgabe**: Kein freigegebener Anbieter oder Monatsbudget
  ausgeschöpft (Einstellungen, KI).
