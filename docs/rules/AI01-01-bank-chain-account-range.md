# AI01-01 Kettenprüfung der Kontoauszüge und Nummernkreis Bank und Kasse

- **ID:** AI01-01 (Befunde GAH-102, GAH-105, GAH-201)
- **Geltungsbereich:** Bankabstimmung `GET /banking/accounts/{id}/reconciliation`; Anlage von Konten `POST /accounting/ledgers/{id}/accounts`; Kontenliste `GET /accounting/ledgers/{id}/accounts`.
- **Quellenstatus (Anhang C):** Fachliche Umsetzung und Produktschutz zu 7.1 B09 und 7.2. Keine Rechtsgrundlage; die Nummernkreise sind laut 7.2 eine Migrations- und Produktkonvention.
- **Abnahmefall (Anhang D):** B09 (Bankabstimmung), B08 (Dublettenschutz bei Nebenläufigkeit); Tests `tests/unit/test_ai01_bank_chain.py`, `tests/integration/test_ai01_bank_chain_concurrency.py`.

## Regel

1. Je Auszug liefert die Abstimmung einen Status: `ok`, `difference` (Auszugs- oder Sachkontodifferenz) oder `not_checkable` (Anfangs- oder Endsaldo fehlt, typisch bei CSV).
2. Kettenprüfung gegen den vorherigen Auszug desselben Bankkontos (Reihenfolge nach Enddatum, Beginn, Anlage): `chain_status` `first`, `ok`, `break` (mit `chain_difference` = Anfangssaldo n+1 minus Endsaldo n) oder `not_checkable`.
3. Zeitraumprüfung: `period_status` `ok`, `gap` (mit `gap_from`, `gap_to`), `overlap` oder `not_checkable`.
4. Ein Befund wird angezeigt, nie automatisch ausgeglichen.
5. Neue Konten mit Nummer 001200 bis 001999 sind nur mit Kategorie bank, cash, technical oder transit zulässig; eine Bankkontoverknüpfung nur an Konten der Kategorie bank oder cash. Verstoß: 422 `MHVP-ACC-0032`. Bestehende Konten bleiben unverändert und tragen in der Kontenliste den Hinweis `range_warning`.

## Änderungsgrund

Welle 20, Paket AI01: Kettenbrüche und Zeitraumlücken waren nicht sichtbar, CSV-Auszüge ohne Salden lieferten keinen Status; Kostenkonten im Bankbereich konnten Liquidität und B09 verfälschen. technical und transit bleiben im Bereich erlaubt, weil der Standardkontenrahmen (Anhang A.1) dort 001400 und den Geldtransit führt (Annahme A-AI01-01).
