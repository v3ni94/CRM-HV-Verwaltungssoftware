# Aufträge

Seite Aufträge (`/auftraege`) mit Auftragsdetail. Stand: 02.10.2026. Lesen verlangt das Recht Tickets lesen, die
Bearbeitung der Schritte das Recht Tickets bearbeiten. Ergänzend zum Abschnitt "Aufträge, Teams, Kommentare und
Dokumente" im Kapitel [Tickets](tickets.md).

## Zweck

Ein Auftrag ist ein Arbeitsauftrag an einen Dienstleister, meist aus einem Ticket heraus (Mangel, Reparatur,
Wartung). Die Seite zeigt alle Aufträge des Mandanten mit Status, Ticketbezug und Termin. Ein Auftrag bucht nichts
und löst keine Zahlung aus. Rechnungen laufen über den Belegeingang, Zahlungen über die Freigabe der Zahlungen
(gesperrt, solange G2 geschlossen ist).

## Auftragsliste

* Spalten: Auftrag (Beschreibung, führt zum Detail), Status, Ticket (Nummer, führt zum Ticket), Termin.
* Filter Status mit Schaltfläche Filtern: Entwurf, angefragt, Angebot liegt vor, freigegeben, Termin bestätigt, in
  Ausführung, ausgeführt, abgerechnet, abgenommen, abgelehnt, storniert, oder Alle.
* Ohne Treffer erscheint "Keine Aufträge gefunden."

## Auftragsdetail

* Kopf mit Rücksprung zu den Tickets (Brotkrumen).
* Terminvorschläge des Dienstleisters: Der Dienstleister schlägt im Portal bis zu drei Termine je Runde vor, die
  betroffene Bewohnerin oder der Bewohner bestätigt einen. Die Verwaltung sieht das Ergebnis (bestätigter Termin,
  offene Vorschläge, Status je Vorschlag) und kommt mit "Zum Ticket" zurück zum Vorgang.
* Auftragsschritt: Der Status folgt dem Ablauf Entwurf, angefragt, Angebot, freigegeben, Termin, Ausführung,
  ausgeführt, abgerechnet, abgenommen. Abgelehnt und storniert beenden den Auftrag. Es sind nur die Folgeschritte
  wählbar, die zum aktuellen Status passen; die Schnittstelle prüft erneut.
* Bewertung des Auftrags: erst nach Abschluss möglich, je Verwaltung und Bewohner, Sterne von 1 bis 5 mit
  optionaler Anmerkung. Ob Bewertungen angezeigt werden, steuert die Einstellung Bewertungen von Dienstleistern.
* Freigabe-Workflow: nur ein gespeicherter Verweis (Kennung). Maßgeblich bleibt die Beiratsfreigabe des Auftrags.

## Grenzen

* Keine Buchung, keine Zahlung, keine verbindliche Erklärung gegenüber Dritten aus dieser Seite.
* Dienstleister nehmen Aufträge im Portal an oder lehnen sie mit Begründung ab. Jede Änderung steht im Ticketverlauf.
* Kosten über der Freigabegrenze verlangen die Freigabe nach den Regeln des Mandanten (Geschäftsführung).

## Auftragsschritte erfassen (GAI-416, Welle 21)

Auf der Auftragsseite bietet der Abschnitt "Auftragsschritt" (Schreibrecht Tickets) nur die zulässigen Folgeschritte an: Angebot erfassen, Freigeben, Termin, Ausführung, Abrechnung und Abnahme mit Bewertung. Die Schnittstelle prüft den Ablauf erneut, die Freigabe verlangt das Freigaberecht und beachtet das Budget des Auftrags. Es wird nichts gebucht und nichts bezahlt.

## Gespeicherte Filter in der Auftragsliste

Der gewählte Statusfilter lässt sich über die Leiste "Gespeicherte Filter" unter einem Namen speichern und später mit einem Klick wieder anwenden. Die Filter gelten nur für die eigene Person. Dasselbe steht im Journal eines Hauptbuchs für den Objektfilter zur Verfügung.
