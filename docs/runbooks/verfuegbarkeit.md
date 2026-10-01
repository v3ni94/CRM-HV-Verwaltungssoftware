# Runbook: Verfügbarkeitsziel und Wartungsfenster

Quelle: MASTER-PROMPT Abschnitt 16 ("99,5 Prozent im Monat, Wartungsfenster angekündigt,
Health-Checks, automatischer Neustart, Statusseite"), Befunde GB16-01 und GB16-02, Regel
PL-AVAIL-01. Technische Überwachung: `monitoring.md` (Uptime Kuma, Beszel).

## 1. Ziel und Messpunkte

Ziel: 99,5 Prozent Verfügbarkeit je Kalendermonat. Rechnerisch sind das bei 30 Tagen
(2.592.000 Sekunden) höchstens 12.960 Sekunden, also 3 Stunden 36 Minuten Ausfall im Monat; bei
31 Tagen 3 Stunden 43 Minuten, im Februar (28 Tage) rund 3 Stunden 22 Minuten.

Messpunkte (je ein Monitor in Uptime Kuma, Prüfung von außen über Traefik):

| Messpunkt | Prüfung |
| --- | --- |
| API | `GET /api/v1/health/ready` |
| CRM | Anmeldeseite des CRM |
| Portal | `GET /api/health` des Portals |

Das Ziel gilt als Produktschutz (Regel PL-AVAIL-01). Es ist keine Zusage gegenüber Dritten,
bevor der Betreiber AD10-02 (Zählung der Wartungsfenster) und die Leistungsbeschreibung für G5
entschieden hat.

## 2. Monatsauswertung

Die Plattform erhebt keine Messwerte selbst. Die Zahl je Messpunkt stammt aus Uptime Kuma und
wird importiert.

1. Am ersten Werktag des Folgemonats in Uptime Kuma je Monitor den Verfügbarkeitswert ablesen.
   Uptime Kuma zeigt Zeiträume wie 24 Stunden, 30 Tage und 1 Jahr; ein Kalendermonat ist darin
   nicht immer genau abgebildet. Den Zeitraum und das Ablesedatum im Quellenhinweis vermerken
   (Anzeige und Zeiträume in der eingesetzten Version prüfen).
2. In der CRM Oberfläche unter Plattform, Wartung und Verfügbarkeit den Monat, den Messpunkt
   und den Wert eintragen (Programmierschnittstelle: `PUT /api/v1/platform/availability`).
   Eine Korrektur überschreibt den Wert; der alte Wert bleibt im Plattformaudit
   (`availability_measurement_recorded`).
3. Die Tabelle zeigt je Monat Ziel und Ist, die geplante Ausfallzeit aus den Wartungsfenstern
   und den Wert ohne geplante Ausfallzeit. Eine Bewertung erscheint erst, wenn alle drei
   Messpunkte vorliegen; der schwächste Messpunkt entscheidet.
4. Verfehlt ein Monat das Ziel, Ursache im Vorfallsprotokoll (`incident.md`) festhalten.
5. Eine automatische Abfrage der Kuma Schnittstelle gibt es nicht; sie wäre nur nach
   Prüfung der eingesetzten Version möglich und bleibt eine offene Option.

## 3. Wartungsfenster ankündigen

Vor jedem Deploy oder sonstigen Eingriff mit Unterbrechung (siehe `deploy.md`):

1. Unter Plattform, Wartung und Verfügbarkeit ein Fenster anlegen: Beginn, Ende (Ortszeit,
   gespeichert in UTC), Text deutsch und englisch (je höchstens 500 Zeichen, Klartext).
2. CRM und Portal zeigen den Hinweis ab der Vorlaufzeit vor Beginn (Standard 48 Stunden,
   Einstellung `MHVP_MAINTENANCE_NOTICE_HOURS`, je Fenster abweichend einstellbar) bis zum Ende.
   Sinnvoll ist eine Ankündigung mindestens 48 Stunden vor Beginn; Eilfälle haben eine kürzere
   Vorlaufzeit und gelten dann nicht als angekündigt im Sinne von AD10-02.
3. Statusseite: Der öffentliche Feed `GET /api/v1/platform/maintenance/current` liefert Status
   (`operational` oder `maintenance`) und Fenster. In Uptime Kuma dasselbe Fenster als Wartung
   anlegen und der Statusseite zuordnen, damit Monitore im Fenster als Wartung und nicht als
   Ausfall erscheinen (Funktion von Uptime Kuma; Bedienung in der eingesetzten Version prüfen).
4. Entfällt der Eingriff, das Fenster absagen (nicht löschen). Das Banner verschwindet sofort,
   die Absage steht im Plattformaudit.
5. Nach dem Eingriff `/api/v1/health/ready` prüfen (`deploy.md` Schritt 4).

Wartungsfenster zählen im Bericht als geplante Ausfallzeit und werden getrennt ausgewiesen.
