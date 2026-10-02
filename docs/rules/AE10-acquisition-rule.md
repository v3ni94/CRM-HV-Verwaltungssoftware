# AE10 Zuordnungsregel bei Eigentümerwechsel je Erwerbsart

* ID: hoa-acquisition-rule-v1 (Befund AA07-01, P01)
* Geltungsbereich: WEG, Schuldnervorschlag für Differenzen aus Sonderumlagen und Abrechnungsergebnis bei Eigentümerwechsel; Mandantenschalter je Erwerbsart (Kauf, Ersterwerb, Erbfall, Zwangsversteigerung, Schenkung, Sonstiger Erwerb).
* Varianten: `manual_release` (Standard, Annahme M24-01 plus Vier-Augen-Freigabe), `by_due_date` (Eigentümer zur Fälligkeit), `by_resolution_date` (Eigentümer zum Beschlussdatum).
* Quellenstatus Anhang C: offen (P01), keine Rechtsregel; Variante ist Konfiguration zur fachlichen Prüfung.
* Abnahmefall: Anhang D D15 (Eigentümerwechsel), Test `tests/integration/test_ae10_acquisition_rule.py`.
* Änderungsgrund: Betreiberliste 01.10.2026 Punkt 10. Gate G4 bleibt geschlossen, bei Standard keine Änderung der Berechnung.
* Nachtrag 02.10.2026 (Welle 18, AG20, GAE-12): Der Hook `calc.allocation_owner` ist an die Vorschau der Planübernahme (`GET /hoa/plans/{id}/apply/preview`, Feld `allocation_proposal` je Zeile mit Stichtag Wirksamkeitsbeginn, Fälligkeit Wirksamkeitsbeginn und Beschlussdatum des Plans) und an `GET /hoa/statements/{id}/allocation-proposal` (Eigentümer zum Abrechnungsbeschluss, Annahme M24-01, neben dem Vorschlag) angebunden. Nur Anzeige hinter dem Mandantenschalter `hoa_allocation_proposal_setting.enabled` (Standard aus, Migration 0438); Übernahme und Ergebnisbuchung verwenden unverändert `owner_at`. Für das Abrechnungsergebnis gibt es keinen Fälligkeitstag, die Variante `by_due_date` ergibt dort den Eigentümer zum Beschluss. Test `tests/integration/test_ag20_allocation.py`.
