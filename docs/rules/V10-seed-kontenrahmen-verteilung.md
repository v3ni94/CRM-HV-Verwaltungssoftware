# V10 Seed-Kontenrahmen: Schlüsselverteilung und Art der Abrechnung je Konto

| Field | Content |
| --- | --- |
| ID | `V10` (U07-01) |
| Title | Vorlagenzeilen tragen `allocation_split` (Liste aus `key_code` und `share_percent`, Summe 100); Konto 028100 trägt die Art der Abrechnung Hausgeld |
| Scope | `mhvp.accounting.defaults` (`split_for`, `fill_unset`), `mhvp.accounting.services.default_template` und `create_ledger`. Alle Mandanten |
| Source status | Offene Entscheidung (V8, Steuerberatung). Keine Rechtsregel: nur Konten, deren Zuordnung aus der Kontenbeschreibung und dem Schlüssel aus M10-02 eindeutig ist, erhalten genau einen Schlüssel zu 100 %. Aufteilungen auf mehrere Schlüssel werden nicht vorbelegt |
| Acceptance case | keine in Anhang D; Tests `tests/unit/test_v10_chart_split_seed.py`, `tests/integration/test_m10_chart_template.py` |
| Implementation | Der Seed füllt `allocation_split` nur, wenn es leer ist (gepflegte Verteilungen bleiben, Wiederholung ändert nichts). Beim Anlegen eines Buchungskreises werden die Anteile übernommen, wenn alle Schlüssel im Objekt vorhanden sind, sonst bleibt das Konto ohne Verteilung. Bestehende Buchungskreise bleiben unverändert |
| Change reason | Lücke U07-01: Kontenrahmen ohne Verteilung je Konto. Offene Konten siehe OPEN_QUESTIONS V10-01 |
