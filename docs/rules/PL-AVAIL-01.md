# PL-AVAIL-01: Verfügbarkeitsziel und Wartungsfenster

- **ID:** PL-AVAIL-01
- **Geltungsbereich:** Plattform (`mhvp.platform.maintenance`, `mhvp.platform.availability_probe`), Anzeige unter Plattform, Wartung und Verfügbarkeit; Banner in CRM und Portal
- **Anforderungstyp:** Produktschutz (Abschnitt 16, Verfügbarkeit); kein Rechtssatz und keine zugesagte Leistung gegenüber Dritten
- **Quellenstatus (Anhang C):** kein Rechtsbezug; Zielwert 99,5 Prozent je Monat aus Abschnitt 16
- **Abnahmefall:** kein Anhang D Fall; Tests `tests/integration/test_ad10_maintenance_availability.py` mit von Hand gerechneten Werten (Februar 2025: 2.419.200 Sekunden, Fenster 7.200 Sekunden) und `tests/unit/test_ae35_availability.py` (März 2025: 44.640 Prüfungen, 340 ausgefallen, davon 240 im Fenster: brutto 99,23835125, netto 99,77477477 Prozent) sowie `tests/integration/test_ae35_availability_probe.py`
- **Gate:** keines; die Zusage gegenüber Dritt-Mandanten gehört zu G5 (offene Frage AD10-02)
- **Änderungsgrund:** Befunde GB16-01 und GB16-02, Paket AD10, 02.10.2026; Fortschreibung Eigenmessung und Schalter für Wartungsfenster (AD10-02 technisch vorbereitet), Paket AE35 (Welle 16), 01.10.2026

## Regel

1. Wartungsfenster legt nur ein Plattformadministrator an, ändert oder sagt es ab (kein Löschen). Jede Aktion steht im Plattformaudit (`maintenance_window_created`, `_updated`, `_cancelled`).
2. Banner und Statusquelle (`GET /platform/maintenance/current`, öffentlich, nur Zeitraum und Text, keine personenbezogenen Daten) zeigen ein Fenster ab der Vorlaufzeit vor Beginn (Standard 48 Stunden, `MHVP_MAINTENANCE_NOTICE_HOURS`, je Fenster überschreibbar) bis zum Ende.
3. Das Verfügbarkeitsziel ist 99,5 Prozent je Kalendermonat (UTC) an drei Messpunkten: API, CRM, Portal.
4. Die Monatszahl je Messpunkt wird aus der externen Überwachung (Uptime Kuma) importiert (`PUT /platform/availability`) und mit Quellenhinweis im Audit festgehalten. Die Plattform misst, schätzt und ergänzt nichts.
5. Eine Monatsbewertung entsteht nur, wenn alle drei Messpunkte vorliegen; der schwächste Messpunkt entscheidet.
6. Angekündigte, nicht abgesagte Fenster sind geplante Ausfallzeit (Vereinigung überlappender Fenster, höchstens bis zur Gegenwart). Der bereinigte Wert zieht sie von der aus dem Import abgeleiteten Ausfallzeit ab (Obergrenze, Orientierung). Welcher Wert das Ziel belegt, entscheidet der Betreiber (AD10-02).
7. Eigenmessung (AE35): Ein Beat Job prüft jede Minute die konfigurierten Health Adressen (`MHVP_AVAILABILITY_API_URL`, `_CRM_URL`, `_PORTAL_URL`; leer = aus, ohne Adresse kein Minutentakt) und speichert je Messpunkt und Minute genau einen Messpunkt (idempotent). Erreichbar ist nur eine 2xx Antwort innerhalb der Zeitgrenze. Gespeichert werden Ergebnis, Statuscode, Antwortzeit und eine feste Fehlerklasse, nie Adresse oder Fehlertext.
8. Monatsauswertung je Messpunkt und Kalendermonat (UTC), täglich: Wert aus allen Prüfungen (brutto) und Wert ohne Prüfungen in angekündigten, nicht abgesagten Wartungsfenstern (netto, Fenster fallen aus Zähler und Nenner), auf acht Stellen abgerundet (nie überhöht). Der laufende Monat ist vorläufig; ein beendeter Monat wird festgeschrieben und nicht mehr geändert.
9. Der Plattformschalter `maintenance_counts_as_downtime` (Standard aus) bestimmt allein, welcher der beiden Werte gegen das Ziel bewertet wird (aus: netto, ein: brutto). Beide Werte und die gemessene Ausfallzeit innerhalb von Fenstern stehen immer in der Auswertung. Die Umstellung steht im Plattformaudit (`availability_setting_changed`) und ändert keine gespeicherten Werte. Welche Zählweise gegenüber Dritten gilt, ist offen (AD10-02, AE35-01, G5).
10. Bewertung nur mit allen drei Messpunkten und einer Abdeckung von mindestens 95 Prozent (Anteil der Minuten mit Messpunkt; Lücken zählen weder als Ausfall noch als Verfügbarkeit). Die Eigenmessung läuft auf derselben Infrastruktur; die Schwelle und der Umgang mit Lücken sind offen (AE35-02).
11. Aufbewahrung: Minutenwerte werden nach `MHVP_AVAILABILITY_RETENTION_DAYS` (Standard 120, mindestens 40) gelöscht, aber nur für Monate mit festgeschriebener Auswertung; der Löschlauf wertet zuvor beendete Monate nach. Die Monatsauswertung bleibt erhalten.
