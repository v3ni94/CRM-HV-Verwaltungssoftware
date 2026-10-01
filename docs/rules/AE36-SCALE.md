# AE36-SCALE: Auslöser der Jahrespartitionierung als Plattformkennzahlen (AC09-01)

- **ID:** AE36-SCALE
- **Geltungsbereich:** Plattform, Tabellen `journal_entry`, `journal_line`, `bank_transaction`, Listen Journal und Bankumsätze; ADR 0021 (Abschnitt Auslöser). Mandantenunabhängig.
- **Art:** Fachliche Umsetzung (Abschnitt 16 Skalierung und Beobachtbarkeit) und Produktschutz. Alle Werte sind Betreibervorschläge aus ADR 0021, keine Rechtsregeln; die Entscheidung AC09-01 bleibt offen.
- **Quellenstatus (Anhang C):** keine Rechtsnorm.
- **Abnahmefall:** kein Fall aus Anhang D; Tests `apps/api/tests/unit/test_ae36_scale.py` (Handwerte), `apps/api/tests/integration/test_ae36_demo_scale.py`.

## Regel

1. Gemessen werden Zeilen und Größe mit Indizes je Tabelle (bis 1.000.000 Zeilen exakt je Mandant gezählt, darüber Schätzung der Datenbank aus `pg_class`; Kennzeichen `exact`), das P95 der Journalliste und der Bankumsatzliste aus echten Aufrufen der letzten sieben Tage (Mindestzahl 20 Aufrufe, Nächster-Rang-Verfahren, getrennt nach tiefem Zugriff ab Versatz 10.000), die Dauer des letzten Wiederherstellungstests und die Zahl produktiver Mandanten ohne Demo-Mandanten. Die Stichproben enthalten nur Zeitpunkt und Dauer, weder Mandant noch Benutzer noch Suchwerte.
2. Auslöser (Vorschläge aus ADR 0021, je einstellbar durch Plattformadministratoren, alle Änderungen im Plattformaudit): 20.000.000 Zeilen je Tabelle, 50 GB je Tabelle mit Indizes (1 GB = 1024³ Byte), P95 über 300 ms (tiefer Zugriff 1.000 ms) in drei aufeinanderfolgenden Wochenmessungen, Wiederherstellungstest über 14.400 Sekunden (RTO 4 Stunden). Erreicht ist ein Wert ab der Schwelle bei Zeilen und Größe, bei den P95 und der Dauer erst über der Schwelle. Diese Auslöser heißen "Partitionierung planen". Die Marke 20 produktive Mandanten heißt "Messung wiederholen" und verlangt keinen Umbau.
3. Wochenmessung: Job `ops-scale-snapshot` (montags 03:10, Europe/Berlin) speichert eine Messung je ISO-Woche (`platform_scale_snapshot`); eine zweite Messung derselben Woche ersetzt die erste. Die P95-Auslöser prüfen die letzten Messungen in Folge, Lücken im Kalender unterbrechen die Folge nicht, eine Messung ohne P95-Wert (zu wenige Aufrufe) unterbricht sie.
4. Alarm: Ein Auslöser, der bei der vorigen Messung nicht aktiv war, schreibt ein Plattformaudit-Ereignis (`scale.trigger_reached`) und einen Hinweis in der Glocke an jeden aktiven Plattformadministrator in jedem seiner Mandanten (Art `platform_scale_trigger`, Ziel Seite Plattform, Betrieb). Der Alarmschalter `alarm_enabled` (Standard an) unterdrückt nur diese Hinweise, die Messung bleibt. Bis der Auslöser entfällt, steht er in `/platform/ops/metrics` unter `alerts` (`scale_trigger_partition_review`, `scale_trigger_measure_again`) und kann über die Überwachung (Uptime Kuma, Schlüsselwort oder Prometheus) per E-Mail gemeldet werden; die Plattform selbst sendet keine E-Mail.
5. Die Messung baut nichts um, verschiebt und löscht nichts und öffnet kein Gate. Der Umbau bleibt nach ADR 0021 Stufe 2 mit Freigabe der Geschäftsführung und Information des Steuerberaters.

## Änderungsgrund

Betreiberliste vom 01.10.2026, Punkt 27 (AC09-01): Auslöser der Partitionierung als Plattformkennzahlen mit Alarm, damit der Zeitpunkt der Planung aus Messwerten und nicht aus Vermutung folgt.
