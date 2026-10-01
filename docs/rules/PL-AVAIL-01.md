# PL-AVAIL-01: Verfügbarkeitsziel und Wartungsfenster

- **ID:** PL-AVAIL-01
- **Geltungsbereich:** Plattform (`mhvp.platform.maintenance`), Anzeige unter Plattform, Wartung und Verfügbarkeit; Banner in CRM und Portal
- **Anforderungstyp:** Produktschutz (Abschnitt 16, Verfügbarkeit); kein Rechtssatz und keine zugesagte Leistung gegenüber Dritten
- **Quellenstatus (Anhang C):** kein Rechtsbezug; Zielwert 99,5 Prozent je Monat aus Abschnitt 16
- **Abnahmefall:** kein Anhang D Fall; Test `tests/integration/test_ad10_maintenance_availability.py` mit von Hand gerechneten Werten (Februar 2025: 2.419.200 Sekunden, Fenster 7.200 Sekunden)
- **Gate:** keines; die Zusage gegenüber Dritt-Mandanten gehört zu G5 (offene Frage AD10-02)
- **Änderungsgrund:** Befunde GB16-01 und GB16-02, Paket AD10, 02.10.2026

## Regel

1. Wartungsfenster legt nur ein Plattformadministrator an, ändert oder sagt es ab (kein Löschen). Jede Aktion steht im Plattformaudit (`maintenance_window_created`, `_updated`, `_cancelled`).
2. Banner und Statusquelle (`GET /platform/maintenance/current`, öffentlich, nur Zeitraum und Text, keine personenbezogenen Daten) zeigen ein Fenster ab der Vorlaufzeit vor Beginn (Standard 48 Stunden, `MHVP_MAINTENANCE_NOTICE_HOURS`, je Fenster überschreibbar) bis zum Ende.
3. Das Verfügbarkeitsziel ist 99,5 Prozent je Kalendermonat (UTC) an drei Messpunkten: API, CRM, Portal.
4. Die Monatszahl je Messpunkt wird aus der externen Überwachung (Uptime Kuma) importiert (`PUT /platform/availability`) und mit Quellenhinweis im Audit festgehalten. Die Plattform misst, schätzt und ergänzt nichts.
5. Eine Monatsbewertung entsteht nur, wenn alle drei Messpunkte vorliegen; der schwächste Messpunkt entscheidet.
6. Angekündigte, nicht abgesagte Fenster sind geplante Ausfallzeit (Vereinigung überlappender Fenster, höchstens bis zur Gegenwart). Der bereinigte Wert zieht sie von der aus dem Import abgeleiteten Ausfallzeit ab (Obergrenze, Orientierung). Welcher Wert das Ziel belegt, entscheidet der Betreiber (AD10-02).
