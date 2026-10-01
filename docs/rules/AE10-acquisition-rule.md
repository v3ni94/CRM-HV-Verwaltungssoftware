# AE10 Zuordnungsregel bei Eigentümerwechsel je Erwerbsart

* ID: hoa-acquisition-rule-v1 (Befund AA07-01, P01)
* Geltungsbereich: WEG, Schuldnervorschlag für Differenzen aus Sonderumlagen und Abrechnungsergebnis bei Eigentümerwechsel; Mandantenschalter je Erwerbsart (Kauf, Ersterwerb, Erbfall, Zwangsversteigerung, Schenkung, Sonstiger Erwerb).
* Varianten: `manual_release` (Standard, Annahme M24-01 plus Vier-Augen-Freigabe), `by_due_date` (Eigentümer zur Fälligkeit), `by_resolution_date` (Eigentümer zum Beschlussdatum).
* Quellenstatus Anhang C: offen (P01), keine Rechtsregel; Variante ist Konfiguration zur fachlichen Prüfung.
* Abnahmefall: Anhang D D15 (Eigentümerwechsel), Test `tests/integration/test_ae10_acquisition_rule.py`.
* Änderungsgrund: Betreiberliste 01.10.2026 Punkt 10. Gate G4 bleibt geschlossen, bei Standard keine Änderung der Berechnung.
