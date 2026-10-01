# Q11 Auftragstermin im Kalender, Benachrichtigungseinstellungen, Sammelaktionen, Regelaktionen, Rechnungseinreichung

| Field | Content |
| --- | --- |
| ID | `Q11` (M19-06, M23-04, M9-04, S15-06, M22-02) |
| Title | Kalendereintrag aus dem Auftragstermin, Benachrichtigungskanäle je Benutzer mit Stummschaltung, Sammelaktionen für Dokumente und Fristaufgaben, Regelaktionen Feld setzen und Entwurf an Dienstleister, Belegentwurf aus angenommener Rechnungseinreichung |
| Scope | `mhvp.workspace` (`jobs._read_work_order_appointments`, `notification_prefs`, `POST /workspace/bulk`, `GET/PUT /workspace/notification-preferences`), `mhvp.automation` (Aktionen `set_field`, `notify_provider`), `mhvp.portal` (`decide`, `_apply_invoice_submission`); Migration 0280 (`notification_preference`, `notification.email_pending`, `notification.email_sent_at`); alle Mandanten |
| Source status | Fachliche Umsetzung nach 18 M9, 15.1, 15.2, 14 und 6.6. Keine Rechtsnorm zitiert. Pflichtmeldungen sind Produktschutz, keine gesetzliche Pflicht |
| Acceptance case | `tests/integration/test_q11_workspace_w3.py` (vorgerechnet: Auftragstermin 06.10.2026 07:30 UTC ergibt 09:30 Uhr Ortszeit am 06.10.2026, Verschiebung um zwei Tage ergibt 08.10.2026, Status erledigt entfernt den Eintrag; Stummschaltung, Kanalwahl und Doppelmailsperre; Sammelaktionen ganz oder gar nicht; Feld setzen hängt an; Belegentwurf mit Brutto 1.190,00 EUR und Status invoiced) |
| Change reason | Lückenliste 30.09.2026, Welle 3, Paket Q11 |

## Regeln

- Auftragstermin (M19-06): Aufträge im Status scheduled oder in_progress mit `scheduled_at` erzeugen
  über den Tagesjob einen internen, geteilten Kalendereintrag (Kategorie `work_order_appointment`,
  Datum in Europe/Berlin, Erinnerung 1 Tag vorher). Keine Einladung, kein externer Kalender. Die
  Ticketfälligkeit (`ticket_due`) bestand bereits. Der Eintrag folgt Terminänderungen und
  verschwindet bei Statuswechsel auf done oder Abbruch.
- Benachrichtigungseinstellungen (M23-04): je Benutzer und Art ein Kanal in der App und per E-Mail,
  Art `*` als Standard, Stummschaltung bis zu einem Zeitpunkt. Ohne Eintrag gilt App an, E-Mail aus.
  Nur E-Mail: der Eintrag entsteht als gelesen, die Mail versendet der Job
  `mhvp.workspace.notification_mails` alle 5 Minuten als Systemmail (kein Netzaufruf in der
  Erzeugungstransaktion). Dieselbe Art und derselbe Bezug lösen innerhalb eines Tages keine zweite
  Mail aus. Verpflichtend und nicht abschaltbar (Produktschutz): `sla_escalation`,
  `compliance_deadline`, `banking.consent_expiring`.
- Sammelaktionen (M9-04): `documents.set_category` (nimmt das zugeordnete Aufbewahrungsprofil der
  Kategorie wie die Einzeländerung), `documents.link_property` (Bezug Anlage), `deadline_entries.done`
  (Fristaufgaben erledigen wie die Einzelaktion). Ganz oder gar nicht, unbekannte Ids ergeben 404,
  Rechte documents:update beziehungsweise tickets:update. Ticketzuweisung und Ticketstatus bestanden.
- Regelaktionen (S15-06): `set_field` setzt nur Notizfelder aus einer geschlossenen Liste
  (Objekt: notes, renovation_notes, garden_notes; Kontakt: notes; Vertrag: notes), standardmäßig
  anhängend mit Datum und Regelname. Kein Zahlungs-, Bank-, Betrags-, Datums-, Status- oder
  Steuerfeld. `notify_provider` legt nur einen E-Mail-Entwurf an den Dienstleister an (Kontakt oder
  aktives Dienstleisterverhältnis der Vertragsart am Objekt des Tickets); Freigabe und Versand bleiben
  manuell. Beide laufen im Testlauf ohne Wirkung.
- Rechnungseinreichung (M22-02): Nimmt die Verwaltung eine Einreichung an, entsteht ein Belegentwurf im
  Belegeingang (Status proposed, Quelle portal, Angaben des Dienstleisters als lokal markiert) und der
  Auftrag wechselt von done auf invoiced. Keine Buchung, keine Zahlung, keine Rechnung; die Bestätigung
  im Belegeingang und die Freigabe der Buchung bleiben hinter G1. Wiederholung verwendet den Entwurf
  zum selben Dokument. Erforderlich zusätzlich: Recht accounting:create. Die Duplikatprüfung gegen die
  Rechnungsnummer liegt beim Einreichen (Paket Portal).
