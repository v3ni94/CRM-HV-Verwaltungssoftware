# GA04-events: Ereignisse und Katalogverweise (AA03)

* ID: GA04-events
* Geltungsbereich: Domänenereignisse ticket.commented (Payload ohne Kommentartext), bank_transaction.imported (gebündelt je Importlauf und Konto, Anzahl), contract.changed und contract_payment.changed (zusätzlich zu den detaillierten Vertragstypen), portal_account.activated (Einlösung der Einladung); ticket.category_id verweist auf ticket_template (Freitext bleibt Fallback); message.delivered_at, read_at, provider_message_id.
* Quellenstatus: Master-Prompt Abschnitte 6.6 und 12 (Fachliche Umsetzung), keine Rechtsnorm.
* Abnahmefall: tests/integration/test_ga04_events.py.
* Änderungsgrund: Lückenliste 01.10.2026 GA04-01 bis GA04-04, GA04-08, GA04-09. Annahmen A-AA03-01 und A-AA03-02, Frage AA03-01.
* Ergänzung AB03: message.delivered_at wird gesetzt, wenn der Transport (Gmail oder SMTP) den Versand angenommen hat (Statuswechsel auf sent) und wenn der Zugangsnachweis einer Zustellung (Dispatch) mit verknüpfter Nachricht erfasst wird. message.read_at wird gesetzt, wenn die empfangende Person im Portal ein Dokument öffnet, das die versendete Nachricht trägt. Beide Werte sind Indizien, kein Zugangs- oder Empfangsnachweis; der erste Wert bleibt erhalten. Eine Zustellbestätigung des Anbieters (Gmail) gibt es nicht, deshalb markiert delivered_at nur die Annahme durch den Transport. Abnahmefall zusätzlich: tests/integration/test_ab03_events_receipts.py.
