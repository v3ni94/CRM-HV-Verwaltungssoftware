# AJ13-datenschutzaufsicht

- ID: AJ13-datenschutzaufsicht
- Geltungsbereich: Auskunft nach Art. 15 DSGVO (Umfang), Fristenüberwachung von Datenschutzanträgen, Einwilligungsübersicht, Verzeichnis nach Art. 30 DSGVO (Detektoren, Vor-G1-Auswertung), Einwilligungsregeln (Maske)
- Abschnitte: 16, 0.1.3; Befunde GAI-506, 507, 508, 509, 510, 414
- Quellenstatus (Anhang C): Art. 15, 17, 30 DSGVO als Norm genannt; Umfang der Auskunft (AC07-01), Länge der Antwortfristen (AJ13-01) und rechtliche Einordnung der Dienste (AE32-01) sind offen. Keine Regel legt hier eine Frist oder einen Umfang fest.
- Status: implemented, not accepted

## Regeln

1. Auskunft: Vorgänge, Nachrichten und Dokumentbezüge des Kontakts sind je Mandantenschalter (`tenant_settings.sources.access_export_sources`) zuschaltbar, Standard aus. Ausgeschaltete Quellen erscheinen nur als Anzahl und als zurückgehaltene Kategorie. Interne Ticketbeschreibungen, Empfängerlisten und Dokumentinhalte werden nie ausgegeben. Der Umfang wird beim Vorbereiten festgehalten.
2. Fristen: Auskunfts-, Lösch- und Vorfrist in Tagen (`sources.privacy_request_deadlines`) haben keinen Standardwert. Ohne Wert zeigt die Überwachung offene Löschanträge mit Zustand "keine Frist hinterlegt". Berechnete Daten sind Orientierung und zu prüfen. Auskunftsanträge haben noch keinen Eingangsdatensatz (Schemabedarf, siehe AJ13-03).
3. Einwilligungsübersicht: Zählung je Zweck (aktiv, widerrufen, Widersprüche, ohne Nachweisdokument); keine Bewertung der Wirksamkeit.
4. Detektoren: zusätzlich OIDC-Anwendungen, Virenscan (ClamAV), externe Datensicherung (`BACKUP_REMOTE`) und Alarm-Webhook (`ALERT_WEBHOOK_URL`), soweit der API-Prozess die Variablen sieht. Basiszinssatz und Mietspiegel werden manuell gepflegt und übermitteln keine Daten.
5. Vor-G1-Auswertung: listet aktiv genutzte Dienste ohne Eintrag und aktive Einträge mit offenem AVV, Drittland oder rechtlicher Prüfung. Sie öffnet kein Gate.

## Abnahmefall

Anhang D: keiner benannt; Testfälle `apps/api/tests/integration/test_aj13_privacy_oversight.py`.

## Änderungsgrund

Lückenanalyse Welle 21 (GAI-506 bis 510, GAI-414).
