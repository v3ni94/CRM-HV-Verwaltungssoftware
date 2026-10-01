# AA02 Freigabestufen: Umfang, Checkliste, Nachweis

- ID: AA02-gate-scope-evidence (GA14-02, GA14-03, GA14-04)
- Geltungsbereich: Freigabeanträge G1 bis G5 je Mandant (`release_gate_request`), Resolver
  `DbReleaseGateResolver`.
- Regeln:
  1. Strukturierter Umfang (Objekte, Rechtsträger, Funktionen); leer bedeutet alle. Begrenzte
     Freigaben gelten nur bei passendem Kontext, ohne Kontext bleibt die Stufe geschlossen.
  2. G2 bis G4: Genehmigung nur mit vollständiger Checkliste aus 18.0 und Nachweisdokument
     (`MHVP-GATE-0006`).
  3. Widerruf überschreibt die Öffnungsangaben nicht.
- Quellenstatus (Anhang C): keine Rechtsgrundlage; Produktschutz und Fachliche Umsetzung nach
  18.0 und ADR 0003 Punkt 5. Mindestumfang je Stufe offen (AA02-01).
- Abnahmefall: kein Fall in Anhang D; Tests `tests/integration/test_aa02_gate_scope_evidence.py`.
- Änderungsgrund: Lückenliste 01.10.2026, GA14-02 bis GA14-04.
