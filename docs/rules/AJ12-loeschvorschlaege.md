# AJ12 Löschvorschläge je Datenart und Bereinigung der Sitzungsmetadaten

- ID: AJ12 (Befunde GAI-501, GAI-502, GAI-503, GAI-504, GAI-522)
- Geltungsbereich: `mhvp.privacy.proposals`, `mhvp.privacy.erasure.accept_proposal`, `mhvp.core.auth.session_purge`, Migration 0445
- Art: Fachliche Umsetzung und Produktschutz; keine Rechtsgrundlage festgelegt
- Quellenstatus Anhang C: Löschfristen und Aufbewahrungsmatrix offen (V17); Beschäftigtendatenschutz offen (M20-08-Q7)
- Abnahmefall: kein Anhang D Fall; Integrationstest `tests/integration/test_aj12_privacy_proposals.py`
- Änderungsgrund: Löschprofile waren reine Konfiguration ohne Durchsetzung (Lückenanalyse GAI, 02.10.2026)

## Regeln

1. Nichts löscht automatisch. Der nächtliche Lauf erzeugt ausschließlich Vorschläge.
2. Vorschläge entstehen nur für Löschprofile, die freigegeben sind (Vier-Augen) und bei denen der Schalter `auto_propose` eingeschaltet ist. Standard: aus. Jede Änderung des Profils setzt die Freigabe zurück.
3. Kontakte: Kontakte mit abgelaufenem `delete_after`, nicht anonymisiert und ohne offenen Antrag erhalten einen Löschantrag im Status `proposed` (höchstens 200 je Lauf). Eine erste Person übernimmt ihn (`requested`), eine zweite Person gibt frei (`approved`), die Sperrprüfung läuft bei jedem Schritt erneut. Ein Vorschlag kann von jeder Person mit Freigaberecht verworfen werden.
4. Kommunikation, Tickets, Portalzugänge und `domain_event` (Audit): nur Zählung als Arbeitsliste (älter als die Frist; Tickets nur erledigt, geschlossen oder abgelehnt; Portalzugänge nur abgelaufen, widerrufen oder gesperrt). Ein Lösch- oder Anonymisierungspfad für diese Datenarten folgt erst nach Entscheidung V17. Für `domain_event` gilt damit weiterhin: keine Löschung.
5. Plattformbenutzer (`platform_user`) und Bankrohdaten (`bank_raw`) sind als Datenart im Profil dokumentierbar, erhalten aber keine automatischen Vorschläge (Plattformbenutzer sind mandantenübergreifend; die Aufbewahrungsklasse der Bankrohdaten ist offen, Regel M11-07).
6. Die Kandidatenkriterien sind eine technische Arbeitsliste und kein rechtlicher Fristbeginn; maßgeblich bleibt der Text `start_rule` des Profils.
7. Sitzungsmetadaten: 90 Tage nach Ablauf oder Widerruf werden `refresh_token.user_agent` und `trusted_device.label` geleert (täglich 04:10). Zeilen bleiben als Sicherheitsnachweis erhalten. Die 90 Tage sind eine Produktschutzannahme (ASSUMPTIONS AJ12-01).
