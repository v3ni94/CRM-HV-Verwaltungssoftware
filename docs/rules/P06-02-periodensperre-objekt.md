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
