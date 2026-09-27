# Runbook Kalendertermine und Fristen aus Stammdaten

Stand 26.09.2026 (P1 AP7, Ergänzung 4.10, Migration 0151).

## Was der Job macht

Der Tagesjob `mhvp.workspace.compliance_deadlines` (Beat 20:00 Uhr) liest je Mandant alle
datierten Felder der Stammdaten über die Leserliste `jobs.calendar_sources()` und schreibt
daraus zwei Ergebnisse:

1. die Fristenliste `compliance_deadline` (nur künftige Daten, Benachrichtigung einmal je
   Zeile bei Erreichen der Vorfrist aus den Einstellungen der Tagesjobs),
2. die erzeugten Kalendertermine in `calendar_entry` (ohne Eigentümer, geteilt, mit Quelle
   `source_type`, `source_id` und Kategorie, Erinnerungscodes nach Anhang B.30, Daten ab
   365 Tagen rückwirkend),
3. die Erinnerungen (`jobs.notify_reminders`): je Erinnerungscode und Termin (bei
   wiederkehrenden Terminen je Vorkommen) genau eine Benachrichtigung `calendar_reminder`,
   sobald der Abstand des Codes erreicht ist (Tagesraster, Codes innerhalb des Tages lösen
   am Termintag aus). Gesendete Codes stehen in `calendar_entry.reminders_sent`
   (`<code>@<Datum>`), ein zweiter Lauf sendet nichts erneut. Erzeugte Termine
   benachrichtigen die Nutzer mit dem Änderungsrecht der Kategorie und verlinken die Quelle,
   manuelle Termine den Eigentümer mit Link in den Kalender. Die Vorfrist der Fristenliste
   (Punkt 1) bleibt eine eigene Benachrichtigung `compliance_deadline`.

Quellen: Eichdatum Zähler, Energieausweis Gebäude, Vertragsende und Kündigung, Einzug und
Auszug, Sanierung und Wartung, Wiedervorlage einer Kontaktnotiz, Eigentümerversammlung und
Beschlussfrist, Ticketfrist, Bankzustimmung, Aufbewahrungsende, Kündigungsfrist
Dienstleistervertrag. Alle Daten sind Orientierung und in der Oberfläche als zu prüfen
gekennzeichnet; eine rechtliche Fristberechnung findet nicht statt (M1-09).

## Eigenschaften

* Deterministisch und idempotent: ein zweiter Lauf auf denselben Daten ändert nichts.
* Verschiebt sich das Quelldatum, wird der Termin aktualisiert. Fällt das Datum weg oder
  wird die Quelle gelöscht, wird der Termin gelöscht.
* Manuelle Termine (mit Eigentümer) werden nie verändert. Google Kalender bleibt unberührt.
* Sichtbarkeit im Kalender nach Leserecht der Kategorie (`DEADLINE_PERMISSIONS`).

## Manuell auslösen

```
cd apps/api && uv run python -c "import asyncio; from mhvp.core.config import get_settings; \
from mhvp.workspace.tasks import deadlines_once; print(asyncio.run(deadlines_once(get_settings())))"
```

Die Ausgabe enthält je Lauf `created`, `updated`, `closed`, `notified` (Fristenliste) und
`calendar_created`, `calendar_updated`, `calendar_deleted` (Kalender).

## Prüfung nach dem Lauf

* `GET /api/v1/workspace/deadlines?kind=<Kategorie>` zeigt die Zeile mit `href` zur Quelle.
* `GET /api/v1/workspace/calendar?start=&end=` zeigt erzeugte Termine mit `category`,
  `reminders`, `href` und `editable=false`.
* Doppelte Termine je Quelle und Kategorie sind durch den Teilindex
  `uq_calendar_entry_generated` ausgeschlossen.

## Bekannte Grenzen

* Eine ungelesene Erinnerung zu demselben Termin und Nutzer wird durch einen weiteren Code
  oder ein weiteres Vorkommen nicht verdoppelt (Idempotenz von `notify`); der Code gilt
  trotzdem als gesendet.
* Wiederholungen (wöchentlich, monatlich, jährlich, mit Enddatum) gibt es nur an manuellen
  Terminen; die Vorkommen werden beim Lesen berechnet (`jobs.expand_occurrences`) und nie
  gespeichert. Der Kalender und die Fristenliste (Art `appointment`, eigene und geteilte
  manuelle Termine mit Erinnerung) zeigen je Vorkommen eine Zeile.
* Die Ticketfrist ist das Feld `due_on` (Migration 0155, Ticketformular und Detail);
  die SLA-Frist `sla_due_at` bleibt getrennt mit eigener Eskalation. Wiedervorlagen werden
  erst gelesen, wenn die Kontaktnotiz `follow_up_on` trägt; die Leser sind in
  `calendar_sources()` hinter einer Prüfung des Modells registriert.
