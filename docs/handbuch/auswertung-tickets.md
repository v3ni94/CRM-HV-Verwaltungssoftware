# Auswertung Tickets

Stand: 26.09.2026, Version 1.25.0. Betreiberauftrag vom 26.09.2026: eine Auswertung, mit der
Wirksamkeit und Durchsatz eingehender und ausgehender Tickets und Mails verfolgt werden.

## Zweck

Die Seite Auswertung Tickets (Hauptnavigation, Bereich Übersicht) zeigt je Zeitraum, wie viele
Tickets angelegt, erledigt und wiedereröffnet wurden, wie sich der Rückstand offener Tickets
entwickelt, wie viele Mails eingegangen und gesendet wurden und wie schnell das Team reagiert.
Alle Werte sind Orientierungswerte für die Steuerung des Teams. Sie sind keine Grundlage für
Abrechnungen, Fristen oder Rechtsfolgen.

## Voraussetzungen

Nur Mandantenadministratoren (Rollen `tenant_admin` und `administrator`, technisch das
Administratorkennzeichen `tickets:delete` nach Regel M2-07) sowie Plattformadministratoren
(Betreiberentscheidung 27.09.2026). Andere Benutzer sehen weder den Menüpunkt noch die Seite,
die Schnittstelle antwortet mit 403. Der Bearbeiterfilter braucht kein weiteres Recht. Die
Postfachliste im Filter stammt aus der Auswertung selbst, das Postfachverwaltungsrecht ist nicht
erforderlich.

## Ablauf

1. Zeitraum wählen: Tag (Stundenscheiben), Woche und Monat (Tagesscheiben), Quartal
   (Wochenscheiben ab Montag), Jahr (Monatsscheiben) oder Frei mit Von und Bis (höchstens 400
   Tage). Alle Zeitscheiben rechnen in der Zeitzone Europe/Berlin; der Zeitraum wird auf ganze
   Scheiben ausgerichtet, die letzte Scheibe kann kürzer sein.
2. Filter setzen: Bearbeiter (Tickets nach zugewiesenem Bearbeiter, gesendete Mails nach
   Verfasser, eingegangene Mails über das zugewiesene Ticket), Postfachart (persönliche
   Postfächer sind Postfächer, die einzelnen Benutzern freigegeben sind; das Standardpostfach ist
   das als Standard markierte Postfach, zum Beispiel info@) und ein einzelnes Postfach.
3. Kennzahlen lesen (Kacheln), Diagramme prüfen (Angelegt und erledigt je Zeitscheibe,
   offene Tickets am Ende der Zeitscheibe) oder auf Als Tabelle anzeigen wechseln.
4. Tabellen je Bearbeiter und je Postfach auswerten.
5. CSV exportieren: Die Datei enthält die aktuelle Ansicht (Zeitscheiben mit allen Kennzahlen,
   Summe, Bearbeiter, Postfächer) mit Semikolon als Trennzeichen und Komma als Dezimalzeichen.

## Kennzahlen und Definitionen

- Tickets angelegt: nach Anlagezeitpunkt.
- Tickets erledigt: Statuswechsel in Erledigt, Geschlossen oder Abgelehnt aus einem offenen
  Status, nach Zeitpunkt des Wechsels. Der Wechsel von Erledigt nach Geschlossen zählt nicht
  erneut.
- Wiedereröffnet: Statuswechsel aus einem abschließenden Status zurück in einen offenen.
- Offen am Ende: offene Tickets am Ende der Zeitscheibe, fortgeschrieben aus dem Rückstand
  vor dem Zeitraum plus angelegt minus erledigt plus wiedereröffnet.
- Mails eingegangen: eingehende Mails nach Empfangszeit. Mails gesendet: ausgehende Mails mit
  Versandnachweis nach Versandzeit; Entwürfe und wartende Freigaben zählen nicht.
- Antworten je Ticket: gesendete Mails mit Ticketbezug geteilt durch angelegte Tickets der
  Zeitscheibe.
- Erstreaktion: Minuten von der Anlage bis zur ersten gesendeten Mail oder zum ersten
  Kommentar eines Mitarbeiters, zugeordnet zur Anlagescheibe. Median und 90. Perzentil mit
  linearer Interpolation, nur Tickets mit Reaktion.
- Erledigung Median: Minuten von der Anlage bis zum Abschluss, zugeordnet zur Abschlussscheibe.
- Erledigt je Minute: erledigte Tickets geteilt durch die Minuten der Zeitscheibe, zwei
  Nachkommastellen. Erledigt je Stunde: derselbe Wert mal 60.
- Je Bearbeiter: erledigt (wer den Status gesetzt hat), angelegt (wer das Ticket angelegt
  hat), Antworten gesendet (Verfasser der Mail), Erstreaktion Median (Tickets, die dem
  Bearbeiter zugewiesen sind), aktuell offen (zugewiesene offene Tickets, unabhängig vom
  Zeitraum).
- Je Postfach: Eingang, Ausgang, Tickets daraus (Tickets, deren erste eingehende Mail aus dem
  Postfach stammt), Anteil am Eingang. Darüber der Anteil persönlicher Postfächer und des
  Standardpostfachs am Eingang.

## Grenzen

- Statuswechsel vor Einführung des Ereignisprotokolls fehlen im Rückstand; Tickets, die nur
  über das Feld Erledigt am geschlossen wurden, erscheinen dort als offen.
- Tickets ohne eingehende Mail (Telefon, Portal, manuell) fallen unter Sonstige und sind mit
  Postfachfiltern nicht sichtbar.
- Keine Geldkennzahlen; die Freigabestufen G1 bis G5 bleiben unberührt.

## Fehlersuche

Zeigt die Seite "Die Auswertung ist derzeit nicht verfügbar.", steht darunter die Antwort der
Schnittstelle (Titel oder Detail, Fehlercode und HTTP-Status nach ADR 0004). Auf dem Server
(`/opt/mhvp`) liefert der API-Log die Ursache:

```sh
./mhvp.sh logs --tail 300 api | grep -B 3 -A 25 "ticket-analytics"
```

Direkter Aufruf der Schnittstelle mit einem Zugriffstoken (Anmeldung über
`POST /api/v1/auth/login`, Mandant über `POST /api/v1/auth/switch-tenant`):

```sh
curl -sS -H "Authorization: Bearer $TOKEN" \
  "https://<api-host>/api/v1/workspace/ticket-analytics?range=week"
```
