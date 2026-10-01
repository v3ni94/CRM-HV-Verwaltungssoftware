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

Es gibt zwei Quellen, die nebeneinander stehen: die Eigenmessung der Plattform (Abschnitt 4,
automatisch) und die Zahl aus Uptime Kuma, die von Hand importiert wird (dieser Abschnitt). Die
Kuma Zahl ist die unabhängige zweite Quelle auf anderer Infrastruktur.

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

## 4. Eigenmessung der Plattform (AE35)

Ein Beat Job (`platform-availability-probe`) ruft jede Minute die Health Adressen von API, CRM
und Portal auf und speichert je Messpunkt und Minute einen Messpunkt (erreichbar oder nicht,
Statuscode, Antwortzeit, kurze Fehlerklasse; keine Adresse, kein Fehlertext). Als erreichbar gilt
nur eine 2xx Antwort innerhalb von `MHVP_AVAILABILITY_TIMEOUT_SECONDS` (Standard 5); eine
Weiterleitung oder 503 zählt als nicht erreichbar.

Einrichtung (Betriebskonfiguration `.env.prod`, siehe `infra/env.prod.example`):

| Einstellung | Wirkung |
| --- | --- |
| `MHVP_AVAILABILITY_API_URL` | Empfohlen die öffentliche Adresse `https://<api-host>/api/v1/health/ready` |
| `MHVP_AVAILABILITY_CRM_URL` | Empfohlen `https://<crm-host>/api/health` |
| `MHVP_AVAILABILITY_PORTAL_URL` | Empfohlen `https://<portal-host>/api/health` |
| `MHVP_AVAILABILITY_TIMEOUT_SECONDS` | Zeitgrenze je Prüfung, 5 Sekunden |
| `MHVP_AVAILABILITY_RETENTION_DAYS` | Aufbewahrung der Minutenwerte, 120 Tage, mindestens 40 |

Leer heißt aus. Sind alle drei Adressen leer, wird der Minutentakt nicht eingeplant (kein Job,
kein Netzaufruf). Nach dem Setzen Beat und Worker neu starten. Öffentliche Adressen messen, was
Nutzer erreichen (DNS, Zertifikat, Traefik); interne Adressen (`http://api:8000/...`) messen nur
die Container.

Auswertung und Löschlauf laufen täglich ohne Netzaufruf:

1. Auswertung (`platform-availability-evaluate`, 03:25 Ortszeit, nach 00:25 UTC): je Messpunkt
   und Kalendermonat (UTC) die Zahl aller Prüfungen, der erreichbaren Prüfungen und der
   Prüfungen innerhalb angekündigter, nicht abgesagter Wartungsfenster. Daraus entstehen der
   Wert aus allen Prüfungen (brutto) und der Wert ohne Wartungsfenster (netto: Prüfungen im
   Fenster fallen aus Zähler und Nenner), jeweils auf acht Stellen abgerundet. Der laufende
   Monat ist vorläufig und wird täglich neu gerechnet; ein beendeter Monat wird festgeschrieben
   und danach nie mehr verändert.
2. Löschlauf (`platform-availability-purge`, 03:55): wertet zuerst alle beendeten Monate aus
   (Nachholen) und löscht dann Minutenwerte, die älter als die Aufbewahrung sind. Minutenwerte
   eines Monats ohne festgeschriebene Auswertung bleiben bestehen. Die Monatsauswertung selbst
   wird nicht gelöscht.

Schalter Wartungsfenster (Frage AD10-02, Standard aus): Unter Plattform, Wartung und
Verfügbarkeit entscheidet der Schalter "Wartungsfenster zählen als Ausfall", welcher Wert gegen
das Ziel bewertet wird. Aus: der Wert ohne Wartungsfenster. Ein: der Wert aus allen Prüfungen.
Beide Werte stehen immer in der Tabelle; die Ausfallminuten innerhalb von Fenstern werden
getrennt als geplante Ausfallzeit ausgewiesen. Jede Umstellung steht im Plattformaudit
(`availability_setting_changed`). Die Umstellung ändert keine gespeicherten Messwerte, nur die
Bewertung.

Grenzen, die gelten und nicht verdeckt werden:

* Die Eigenmessung läuft auf derselben Infrastruktur. Fällt der ganze Server aus, entsteht eine
  Lücke statt fehlgeschlagener Prüfungen. Lücken zählen nicht als Ausfall, senken aber die
  Abdeckung (Anteil der Minuten mit Messpunkt). Ein Monat wird nur bewertet, wenn alle drei
  Messpunkte vorliegen und die Abdeckung mindestens 95 Prozent beträgt (Frage AE35-02).
* Wird ein Wartungsfenster nachträglich abgesagt, ändert das einen festgeschriebenen Monat nicht.
* Für Zusagen an Dritte (G5) ist ein externer Messpunkt (Abschnitt 2) als zweite Quelle zu führen.

Fehlersuche: `GET /api/v1/platform/availability/live` (Anzeige unter Plattform) zeigt je
Messpunkt die letzte Prüfung, die Werte der letzten 24 Stunden und die letzten Fehlschläge.
Bleibt "Letzte Prüfung" stehen, laufen Beat oder Worker (Queue `io`) nicht; die Aufgabe verfällt
nach 55 Sekunden, ein Rückstau entsteht nicht.
