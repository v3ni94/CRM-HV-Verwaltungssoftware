# GA04-events: Ereignisse und Katalogverweise (AA03)

* ID: GA04-events
* Geltungsbereich: Domänenereignisse ticket.commented (Payload ohne Kommentartext), bank_transaction.imported (gebündelt je Importlauf und Konto, Anzahl), contract.changed und contract_payment.changed (zusätzlich zu den detaillierten Vertragstypen), portal_account.activated (Einlösung der Einladung); ticket.category_id verweist auf ticket_template (Freitext bleibt Fallback); message.delivered_at, read_at, provider_message_id.
* Quellenstatus: Master-Prompt Abschnitte 6.6 und 12 (Fachliche Umsetzung), keine Rechtsnorm.
* Abnahmefall: tests/integration/test_ga04_events.py.
* Änderungsgrund: Lückenliste 01.10.2026 GA04-01 bis GA04-04, GA04-08, GA04-09. Annahmen A-AA03-01 und A-AA03-02, Frage AA03-01.
