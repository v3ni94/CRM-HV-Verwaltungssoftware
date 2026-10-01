# Q01 Zentrale Freigabeentscheidung, Personenprüfung, offene Posten zum Stichtag

| Field | Content |
| --- | --- |
| ID | `Q01` (S69-02, S69-03, S69-04, M10-05, P02-03; M15-07 offen) |
| Title | Freigabeentscheidung mit Hash des Vorgangs, Warnung bei möglicher Personengleichheit, gepflegte Tabelle offener Posten zum Stichtag, Kreditorenkonto beim Anlegen des Dienstleisterverhältnisses, Schalter Monatsvorschau |
| Scope | `mhvp.accounting.approval_decisions` (`approval_decision`, `GET /accounting/approval-decisions`), `mhvp.banking.payments.approve` und `invalidate`, `accounting.routers` Rechnungsfreigabe und Rechnungsänderung, `accounting.tax.add_second_approval`; `mhvp.accounting.open_item_balances` (`open_item_balance`, `GET/POST /accounting/ledgers/{id}/open-item-balances[/refresh]`, Job `mhvp.accounting.open_item_balance_refresh`); `properties.routers.add_provider`; `platform.schemas.ReceivableRulesConfig.monthly_preview_enabled`; Migration 0271; alle Mandanten |
| Source status | Fachliche Umsetzung nach 6.9.9, 6.9.13, E09, E15, B07 und 7.2. Keine Rechtsnorm zitiert. Die Namens- und Geburtsdatumsprüfung ist Produktschutz, keine Rechtspflicht |
| Acceptance case | `tests/integration/test_q01_approvals_open_items.py` (vorgerechnet: Forderung 1.000,00, Zahlung 600,00 am 10.01.2026, Rest zum 05.01.2026 1.000,00, zum 31.01.2026 400,00; Freigabe gültig, nach Änderung invalidated; zwei Konten mit getrennten Kontakten gleichen Namens und Geburtsdatums: Freigabe erteilt, Warnung sichtbar; Rechte 403, anderer Mandant 404, Validierung 422), `tests/unit/test_q01_person_warnings.py` |
| Change reason | Lückenliste 30.09.2026, Welle 3, Paket Q01 |

## Regeln

- Jede Zahlungsfreigabe, Rechnungsfreigabe und zweite Rechnungsfreigabe schreibt zusätzlich eine
  `approval_decision` mit `subject_snapshot_hash` (Zahlungsauftrag: `payments.snapshot`, Rechnung:
  `invoices.payment_hash`). Die bisherigen Datensätze bleiben und entscheiden weiter die Prüfungen.
- Ändert sich der Vorgang, wird jede gültige Entscheidung mit abweichendem Hash dauerhaft auf
  `invalidated` gesetzt (Zeitpunkt, Grund). Nichts wird gelöscht.
- Personenprüfung: gleiche Benutzer-E-Mail oder gleicher verknüpfter Kontakt sperren weiter (D36).
  Neu und nur als Warnung: gleiche E-Mail-Adresse in getrennten Kontakten, gleicher Name mit gleichem
  Geburtsdatum, gleicher Name ohne hinterlegtes Geburtsdatum. Gleicher Name mit verschiedenem
  Geburtsdatum bleibt ohne Hinweis. Die Warnung steht an der Entscheidung und im Zahlungsauftrag.
- Offene Posten zum Stichtag: gepflegte Mandantentabelle mit RLS statt Materialized View (eine
  Materialized View kennt keine RLS). Jede Aktualisierung rechnet aus den Ausgleichen neu
  (`services.open_items`); die Live-Berechnung bleibt maßgeblich. Der Nachtjob schreibt den
  Tagesstand und entfernt ältere Jobstände; manuelle Stichtage bleiben bis zur Neuberechnung.
- Kreditorenkonto: Beim Anlegen eines Dienstleisterverhältnisses entsteht das Kreditorenkonto
  070000 bis 079999 in jedem Buchungskreis des Objekts und wird verknüpft. Nur Stammdaten, keine
  Buchung.
- `monthly_preview_enabled` (Standard aus) schaltet den monatlichen Vorschaulauf der
  Sollstellungen; es entstehen nur Vorschauen, Buchen bleibt manuell hinter G1.
