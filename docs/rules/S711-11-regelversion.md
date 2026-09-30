# S711-11 Regelversionsregister mit Wirksamkeitsdatum

| Field | Content |
| --- | --- |
| ID | `S711-11` |
| Title | Register der Versionen einer Fachregel mit Wirksamkeitsdatum, betroffenen Fallgruppen, Quellenstatus, Änderungsgrund und erfasster fachkundiger Bestätigung |
| Scope | Tabelle `rule_version` (Migration 0259, RLS), `mhvp.accounting.report_routers` (`GET/POST /accounting/rule-versions`, `GET /accounting/rule-versions/effective`, `POST .../{id}/confirm`, `POST .../{id}/withdraw`). Schreiben mit `accounting:approve` |
| Source status | Fachliche Umsetzung zu Abschnitt 7.12 (Regelversion bei gesetzlichen Neuregelungen). Offene Entscheidung P03 für die Bewertung je Fallgruppe. Das Register ist kein Rechtsurteil und keine Freigabe |
| Acceptance case | keine in Anhang D; Test `apps/api/tests/integration/test_p10_reports.py` |
| Implementation | Version je `rule_id` fortlaufend, Wirksamkeitsdatum muss nach dem der letzten Version liegen. Status `draft`, `confirmed`, `withdrawn`. Bestätigung speichert Name und Datum der fachkundigen Person als Eingabe, nie automatisch. Keine Berechnung liest das Register bisher |
| Change reason | Lückenliste 30.09.2026, S711-11, Entscheidung 11 a |

## Regeln

- Eine bestätigte Version ist nicht veränderbar, nur zurückziehbar; eine Korrektur ist eine neue Version.
- Der Abruf der wirksamen Version liefert auch den Status, damit ein Aufrufer unbestätigte Entwürfe erkennt.
- Das Register ersetzt nicht die Regeldateien in `docs/rules/`; dort bleibt die fachliche Beschreibung.
