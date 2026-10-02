# M12-09 G1-Öffnungsliste und Automatikschalter mit Vier Augen

- ID: M12-09 (mit BK2-03)
- Geltungsbereich: Mandantenweite Bankautomatik (`tenant_settings.auto_posting_enabled`) und
  Checkliste der G1-Öffnung (`g1_acceptance`).
- Anforderungsart: Produktschutz (kein Rechtsgrundsatz); Gate G1 nach 18.0, ADR 0003, ADR 0014.
- Quellenstatus (Anhang C): keine Norm; interne Freigaberegel.
- Regel: Je Prüfpunkt der G1-Öffnung werden verantwortliche Person und Nachweis (DMS-Dokument
  oder Verweis) erfasst; ein bestandener Punkt ohne Nachweis wird als Lücke gezeigt. Der
  Automatikschalter wird über die Oberfläche nur bei offener G1 eingeschaltet, mit Antrag
  einer Person und Freigabe einer anderen Person (keine Plattformadministration). Ausschalten
  wirkt sofort. Der Vergleichslauf Automatik gegen manuelle Buchung ist ein reiner Bericht aus
  `posting_decision` und bucht nichts.
- Abnahmefall: Anhang D D50 (Nur-Lese-Nutzer), Tests `tests/integration/test_ae03_g1_switch.py`.
- Änderungsgrund: Prioritätenliste des Betreibers vom 01.10.2026, Punkt 3 (Welle 16, AE03).
- Offen: `PUT /banking/automation` schaltet per API weiterhin ohne G1 und ohne zweite Person
  ein (bestehende Tests und Vergleichsbuchungen M12-07); Entscheidung BK2-03 offen.
- Änderung 02.10.2026 (Welle 18, AG19, AF25-01): Die Ausgangsautomatik folgt demselben
  Antragsweg (Ziel `outgoing`, zweite Person, G1); `PUT /banking/automation/outgoing` schaltet
  nur aus, Einschalten ergibt 409 `MHVP-BANK-0064`. Tests `test_ae03_g1_switch.py`.
