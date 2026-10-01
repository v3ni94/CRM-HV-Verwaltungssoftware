# W02 Ticket-Ereignisse für Priorität und Team

* ID: W02 (V11-09, ergänzt M19-09)
* Geltungsbereich: Tickets, `PATCH /tickets/{id}` und `POST /tickets/bulk`, Ticketverlauf.
* Quellenstatus Anhang C: keine Rechtsnorm, Produktschutz (Nachvollziehbarkeit).
* Regel: Jede tatsächliche Änderung von Priorität oder Team schreibt ein Ereignis `priority_changed` bzw. `team_changed` mit Vorher und Nachher und Bearbeiter, bei Sammelaktion mit `bulk`. Gleiche Werte schreiben nichts. Status und Zuständiger schreiben wie bisher `status` und `assigned`.
* Abnahmefall: `tests/integration/test_u06_ticket_bulk.py::test_priority_and_team_changes_write_ticket_events`.
* Änderungsgrund: Sammelaktion und Einzeländerung hinterließen für Priorität und Team keine Spur im Verlauf.
