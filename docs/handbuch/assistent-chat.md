# KI-Assistent im Chat

Stand: 28.09.2026. Die Chatblase unten rechts steht auf jeder Seite des CRM bereit. Regel
AI-LOOKUP-01 in `docs/rules/AI-LOOKUP-01.md`.

## Fragen zu Kontakten, Objekten, Verträgen und Tickets

Schreiben Sie Ihre Frage wie an eine Kollegin, zum Beispiel "Telefonnummer von Herrn
Kowalski", "Mietvertrag von Schmidt", "Einheit 07 im Lindenhof" oder "Status von Ticket 4711".
Die Plattform sucht selbst in Kontakten, Objekten, Einheiten, Verträgen und Tickets, jeweils nur
in den Bereichen, für die Sie eine Berechtigung haben. Unter der Antwort stehen die gefundenen
Datensätze als Links, ein Klick öffnet den Datensatz. Findet die Plattform nichts, sagt der
Assistent das ausdrücklich. Er erfindet keine Datensätze.

## Wo finde ich

Fragen wie "Wo finde ich die Markenfarben?" oder "Wo lege ich eine Rolle an?" beantwortet der
Assistent aus dem Handbuch und dem Verzeichnis der Einstellungsseiten, mit einem Link zur Seite.

## Vorschläge je Seite

Beim Öffnen zeigt der Chat Vorschläge passend zur Seite und zum geöffneten Datensatz, zum
Beispiel auf einem Kontakt "Was ist offen bei diesem Kontakt?" oder auf einem Ticket
"Antwortentwurf erstellen". Ein Klick stellt die Frage. Der Assistent bezieht sich dann auf den
geöffneten Datensatz, auch ohne dass Sie den Namen nennen.

## Gespräch mit Rückfragen

Jede Nachricht geht an den freigegebenen KI-Anbieter, mit Seite, Datensatz, den Treffern und
dem bisherigen Gespräch. Anmerkungen und Anschlussfragen ("Und seit wann?") versteht der
Assistent deshalb im Zusammenhang. Ist kein Anbieter freigegeben oder das Monatsbudget
erreicht, zeigt der Chat nur die Treffer der Plattformsuche und sagt das in einem Satz.

## Änderungen über den Chat

Bitten Sie zum Beispiel "Neue Telefonnummer von Kowalski: 0211 7654321", "Notiz an Kowalski:
Rückruf erbeten" oder "Lege ein Ticket für Kowalski an", erstellt der Assistent nur einen
Vorschlag. Die Karte zeigt, was geändert würde. Erst mit "Bestätigen und übernehmen" wird die
Änderung gespeichert, über denselben Weg wie in der Kontaktakte oder beim Ticket anlegen, mit
Änderungshistorie. "Verwerfen" ändert nichts. Bankverbindungen ändert der Chat nie; sie werden
in der Kontaktakte erfasst und laufen dort über die Vier-Augen-Freigabe.

## Datenschutz und Protokoll

Telefonnummern, E-Mail-Adressen und Bankverbindungen verlassen die Plattform nur maskiert. Die
Trefferliste mit den vollständigen Angaben sehen Sie im Chat, sie kommt nicht von der KI. Alle
Fragen, Antworten, Links und Vorschläge bleiben im Assistentenprotokoll nachvollziehbar.

## Grenzen

- Für WEG-Seiten, Übergabeprotokolle und das Postfach gibt es Vorschläge, aber noch keine
  eigene Datenabfrage zu Beschlüssen, Versammlungen, Rücklagen, Mängeln, Zählerständen oder
  Unterschriften; der Assistent kennt dort nur Seite und Datensatz.
- Die Plattform wählt die Suchbereiche nach festen Regeln; die KI selbst löst keine Abfragen aus.
