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

## Ergänzung AB02 (Welle 13)

- Regel 4: Routen, die ein Objekt kennen, reichen den Kontext an `is_open_for` durch
  (`ensure_release_gate_open_for`): Kontenrahmen führendes System und Sofortbuchung des
  Ausgleichsvorschlags (G1, Objekt und Rechtsträger des Buchungskreises), Zahlungsdatei
  herunterladen und einreichen (G2, Objekt des Bankkontos). Unbegrenzte Freigaben öffnen
  weiterhin alles, begrenzte nur das passende Objekt oder den passenden Rechtsträger; ein
  unbekanntes Objekt wird ohne Kontext geprüft (403 vor 404). Die Granularität bleibt offen
  (AA02-02).
- Abnahmefall: kein Fall in Anhang D; Tests `tests/unit/test_ab02_gate_context.py`,
  `tests/integration/test_ab02_gate_context_platform.py`.
- Änderungsgrund: Lückenliste 01.10.2026, GA14-02 Rest.
