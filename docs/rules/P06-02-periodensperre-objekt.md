# P06-02 Periodensperre je Objekt und Zeitraum

| Field | Content |
| --- | --- |
| ID | `P06-02` |
| Title | Periodensperre je Objekt und Zeitraum neben der Festschreibung des Buchungskreises |
| Scope | Alle Mandanten, Buchungskreise und Objekte. Wirkt beim Buchen und Stornieren (`post`, `reverse`) und nur bei Mandantenschalter `lock_mode = object_period`. |
| Source status | Produktschutz und Fachliche Umsetzung. Der Umfang der Sperre je Abrechnung (P06-02) und die Wiederöffnung (AA08-01) sind Offene Entscheidung des Betreibers (Gate G3), nicht entschieden. Anhang C kennt keine Norm dazu. |
| Acceptance case | `tests/integration/test_ae20_period_lock.py` (Sperre 01.04.2026 bis 30.06.2026: Buchung am 30.06.2026 409 `MHVP-ACC-0030`, am 01.07.2026 zulässig, Storno in die Sperre 409, Modus `ledger_only` ohne Wirkung, Aufhebung nur mit Schalter, Antrag, zweiter Person, Zeile bleibt, Fremdmandant 404, Leserecht 403, Abschluss setzt die Sperre idempotent nur mit `auto_lock_on_close`), `tests/unit/test_period_lock_models.py` |
| Implementation | Migration `0376`, `mhvp/accounting/period_lock.py` und `period_lock_routers.py`, Einhängung in `services.post` und `services.reverse`, Abschluss (`locked`) in `billing/routers.py` und `owner_statement_routers.py`, Seite Einstellungen, Buchhaltung, Periodensperren |
| Defaults | `lock_mode = ledger_only`, `auto_lock_on_close = false`, `reopen_enabled = false`. Die Festschreibung des Buchungskreises (B03) bleibt unverändert und nicht aufhebbar. |
| Rules | Eine Sperre betrifft Buchungen, deren Zeilen zum Objekt gehören (Einheit der Zeile oder Objekt des Buchungskreises). Aufhebung: Schalter, Antrag mit Begründung, Freigabe durch eine andere Person (MHVP-GATE-0002), Zeile bleibt mit Zeitstempel und Person erhalten. Abschluss einer Abrechnung ohne Schalter liefert nur `period_lock_proposed`. Nichts wird gebucht, versendet oder gelöscht. |
| Change reason | Prioritätenliste des Betreibers vom 01.10.2026, Punkt 20 (P06-02), AA08-01 |
| Change GAE-01/02 (Welle 17, AF04) | Der Hook `property_ids_of_lines` liest das Objekt direkt aus `journal_line.property_id` (Ersatz aus der Einheit nur für Zeilen ohne Spalte), damit sperren auch Zeilen ohne Einheit. Abschluss der WEG-Hausgeldabrechnung (`POST /hoa/statements/{id}/transition`, Ziel `locked`) setzt die Sperre des Kalenderjahres für das Objekt des Buchungskreises mit Quelle `hoa_statement` (Migration 0398), nur mit `auto_lock_on_close`. `admin_fee_posting` prüft die Objektsperre schon beim Erzeugen der Entwürfe. Abnahmefall: `test_gae01_line_property_without_unit_is_locked`, `test_gae03_hoa_statement_close_sets_lock_via_endpoint`. |

## Änderung Welle 19 (GAG-06, GAE-02)

Der Kontierungsvorschlag eines Bankumsatzes zeigt die Objektsperre an (`object_period_lock`, Code MHVP-ACC-0030), die Buchung eines Umsatzes in den gesperrten Zeitraum wird mit 409 MHVP-ACC-0030 abgelehnt. Die Vorabprüfung der Buchungsentwürfe der Verwaltervergütung ist per Integrationstest abgesichert. Keine neue Fachregel, nur Anzeige und Testabdeckung; Modusschalter und Frage P06-02 bleiben unverändert.
