# R07-01 Protokollabschluss der Eigentümerversammlung

* ID: R07-01
* Geltungsbereich: `POST /hoa/meetings/{id}/close`, `/close/confirm`, `/close/withdraw`
  (`mhvp.hoa.meetings`), Spalten `owners_meeting.close_requested_by`, `close_requested_at`,
  `closed_by`, `closed_at` (Migration 0302).
* Regel: Abschluss nur aus Status `held` mit Pflichtangabe `minutes_document_id` (vorhandenes
  Dokument, sonst 422). Antrag setzt Status `closing`, Bestätigung durch eine zweite Person mit
  demselben Dokument setzt `closed` und erzeugt das Ereignis `meeting.closed` (Webhook). Ab
  `closing` beantworten Tagesordnung, Anwesenheit, Stimme, Verkündung, Störung und
  Beschlussfrist Änderungen mit 409. Rückzug nur aus `closing`.
* Quellenstatus (Anhang C): Fachliche Umsetzung und Produktschutz (Vier-Augen-Prinzip). Eine
  gesetzliche Protokollfrist wird nicht hinterlegt und nicht gesperrt; Hinweistext ohne
  Sperre, offene Frage R07-01 in `docs/OPEN_QUESTIONS.md`.
* Abnahmefall: `tests/integration/test_r07_01_meeting_close.py`, CRM `MeetingClose.test.tsx`;
  fachliche Abnahme durch den Betreiber offen.
* Änderungsgrund: Lückenliste 30.09.2026, Befund R07-01 (Welle 7, Paket V05).
