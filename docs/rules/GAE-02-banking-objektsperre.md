# GAE-02 Objektsperre im Banking-Verifier

- ID: GAE-02 (Bezug AE20, P06-02)
- Geltungsbereich: automatische Buchung von Bankumsätzen (L2 und L3), Modus `object_period` des Mandanten
- Quellenstatus Anhang C: Produktschutz, keine Rechtsgrundlage behauptet; Entscheidung P06-02 und AA08-01 bleibt offen
- Regel: Deckt eine aktive Objektsperre eines betroffenen Objekts den Buchungstag ab, wird der Umsatz nicht automatisch gebucht (übersprungen, bleibt zur manuellen Klärung)
- Abnahmefall: tests/unit/test_bank_verifiers.py::test_object_lock_is_skipped_not_refused
- Änderungsgrund: Befund GAE-02, Verifier kannte nur die Ledgersperre
