# AN20 Seitengröße, Abschlussereignis Auftrag, Nachweise Anhang D bis F

- ID: AN20-01 (GAK-301), AN20-02 (GAK-302, GAK-303), AN20-03 (GAK-401 bis GAK-406)
- Geltungsbereich: alle GET-Listen der API, Dienstleisterauftrag (CRM, Portal, Regel-Engine), Testwächter, Abnahmeprotokolle, Backup.
- Anforderungstyp: Fachliche Umsetzung, Produktschutz (Betriebs- und Nachweisstandard); keine Rechtsgrundlage.
- Quellenstatus (Anhang C): Abschnitt 12 (page_size max 200, Ereignistypen), Anhang D.3 und E, Abschnitt 16; keine Norm betroffen.
- Regel:
  - AN20-01: `MAX_PAGE_SIZE = 200` in `mhvp/core/listparams.py`; kein Query-Parameter `page_size`, `limit` oder `per_page` darf mehr als 200 zulassen, und kein Standardwert darf darüber liegen (Wächtertest `tests/unit/test_an20_page_size_cap.py` liest das OpenAPI-Schema). Größere Mengen gehören in Export- oder Sammelendpunkte. Das CRM lädt Listen über 200 Zeilen seitenweise (`apps/web-crm/src/lib/list-all.ts`).
  - AN20-02: `work_order.completed` wird bei jedem Weg nach DONE genau einmal neben `work_order.done` ausgegeben (CRM, Dienstleisterportal, Regel-Engine) über `mhvp/tickets/order_events.py`; Wiederholung verdoppelt nichts, weil der Statusfluss DONE nur einmal zulässt. `work_order.done` bleibt als älterer Name bestehen.
  - AN20-03: Wächter Anhang D deckt D01 bis D58 ab; jeder Fall hat mindestens zwei unabhängige Tests (zweite Tests für D50, D51, D53, D54, D56, D58 in `tests/integration/test_an20_annex_d_second.py`, Sollwerte von Hand im Docstring). Abnahmeprotokolle folgen D.3 (`scripts/check_acceptance_protocols.py`), das Belegregister E01 bis E16 steht in `docs/rules/anhang-e-register.md`, das Löschjournal wird mit jedem Dump verschlüsselt gesichert (`scripts/backup.sh`, geprüft von `scripts/backup-verify.sh`), der Sollstellungslauf für 1.000 Verträge hat einen Leistungstest (Marker `slow`, 120 Sekunden).
- Abnahmefall: Anhang D D47 (Wiederherstellung nach Löschung), D50, D51, D53, D54, D56, D58; Abschnitt 16 (Leistung).
- Änderungsgrund: Welle 24, Paket AN20 (Lückenanalyse GAK-301 bis GAK-406).
