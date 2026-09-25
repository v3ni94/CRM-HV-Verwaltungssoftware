# M36 Tickets zusammenführen in der Oberfläche

Stand 25.09.2026, Version 1.17.0. Baut auf M6 (Migration 0037, `POST /api/v1/tickets/merge`) auf.

## Prüfung des bestehenden Endpunkts (M6)

- Bisher: mindestens zwei Tickets werden zu einem neuen Sammelticket mit neuer Nummer
  zusammengeführt. Kommentare, Nachrichten (Mails) und Verlaufseinträge werden verschoben,
  jede Quelle wird geschlossen und erhält `merged_into_ticket_id`.
- Lücken: kein bestehendes Zielticket möglich, keine SLA-Uhr für das Sammelticket, SLA-Uhren
  der Quellen liefen weiter, Zuweiser (`ticket_assignee`) der Quellen gingen verloren, Kontakt
  und Thema wurden nicht übernommen, Quellen blieben bearbeitbar.

## Umsetzung

- API: `target_ticket_id` (optional). Mit Ziel behält das Ziel Nummer, Status, Priorität und
  Zuweisung; Sichtbarkeit wird vereinigt. Ohne Ziel bleibt das Verhalten aus M6.
- Beide Wege: `merged_from` am Ziel mit Herkunft (Nummer, Titel, Anzahl verschobener
  Kommentare, Nachrichten, Verlaufseinträge), `merged_into` an der Quelle, SLA-Uhr der Quelle
  erledigt, fehlende Zuweiser am Ziel ergänzt (Grund Zusammenführung, append-only).
- Sperre: `PATCH /tickets/{id}`, Checkliste und Kommentar lehnen zusammengeführte Tickets mit
  409 ab.
- Liste: `q` (Nummer oder Titel), `include_merged` (Standard true, Oberfläche sendet false),
  `merged_into`. Kein neuer Endpunkt. Detail: `message_count`.
- Regeln rein in `mhvp/tickets/merge.py`, Unit-Test `tests/unit/test_m36_ticket_merge.py`.
- CRM: `TicketMergeDialog` im Ticketdetail, Banner an Quelle, Hinweis Enthält Ticket am Ziel,
  Filter Zusammengeführte anzeigen in der Ticketliste, BFF-Allowlist, de/en.

## Offene Punkte

- Verschieben von Verlaufseinträgen ist ein Update der Ticketzuordnung (Verhalten aus M6); die
  Herkunft ist über `merged_from` nachvollziehbar, die Einträge selbst tragen keine Quelle.
- Integrationstest `tests/integration/test_m6_ticket_merge.py` deckt den Zielmodus noch nicht ab.
- Anzahl Nachrichten in der Vorschau = Mails plus Kommentare.
