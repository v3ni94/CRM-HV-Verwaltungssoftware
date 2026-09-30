# M20-09 IMAP-Abruf, Kompaktansicht, HTML-Text und KI-Felder classify_email v3

| Field | Content |
| --- | --- |
| ID | `M20-09` |
| Title | IMAP-Abruf für Postfächer `kind = imap`, Textgewinnung aus HTML-Mails, Kompaktansicht (Zusammenfassung, CRM-Hinweis, Antwortvorschlag), zusätzliche geprüfte Ausgabefelder von `classify_email` |
| Scope | `mhvp.communication.imap`, `mhvp.communication.html` (`html_to_text`, `display_body`), `mhvp.communication.compact`, `mhvp.communication.suggest.merge_v3_fields`, `mhvp.ai.tasks.MailSuggestion` (Prompt v3), `Mailbox.reply_style` |
| Source status | Keine Rechtsnorm einschlägig. Fachliche Umsetzung (13.4, 9.2, 18 M20) und Produktschutz (Datensparsamkeit, DSGVO Art. 5 Abs. 1 lit. c); Entscheidung 5 a vom 30.09.2026 (IMAP) |
| Acceptance case | keiner in Anhang D; Tests `tests/unit/test_mail_html_text.py`, `tests/unit/test_imap_collect.py`, `tests/unit/test_mail_suggestion_v3.py`, `tests/integration/test_p12_mail_compact.py`, `apps/web-crm/src/components/mail/CompactView.test.tsx` |
| Implementation | Migration `0261_mailbox_imap_cursor` (`mailbox.imap_uidvalidity`, `mailbox.reply_style`, `mailbox.last_uid` BIGINT); Beat `communication-imap-sync` (120 s); `POST /mail/mailboxes/{id}/sync` auch für IMAP; `GET /mail/messages/{id}/compact`, `POST /mail/messages/{id}/compact/summary` |
| Change reason | Lückenliste 30.09.2026 (M20-01, M20-02, M20-03, S13-08), Betreiberwunsch Kompaktansicht und Betreibermeldung HTML-Mails vom 30.09.2026 |

## Regeln

- IMAP: Abruf nur lesend (`BODY.PEEK[]`, INBOX `readonly`); auf dem Server wird nichts
  verschoben, markiert oder gelöscht. Jede Mail läuft durch `services.ingest_raw` wie beim
  Gmail-Abruf (Dokument, Anhänge, Zuordnung, Duplikatgruppe, Ticket, SLA-Uhr), je Mail in
  eigenem Savepoint. Zugangsdaten sind `username` und das verschlüsselte `secret` des
  Postfachs; das Geheimnis erscheint nie in Fehlertexten oder Logs.
- Cursor `last_uid` gehört zu `imap_uidvalidity`. Ändert der Server UIDVALIDITY, beginnt der
  Cursor neu; erneut geholte Mails erkennt die Duplikatprüfung. Der erste Abruf holt nur die
  letzten 30 Tage (Annahme A-P12-01). Eine nicht speicherbare Mail wird mit UID in
  `last_error` genannt, der Cursor läuft weiter, damit spätere Mails nicht blockiert werden.
- HTML-Text: Text bevorzugt aus `text/plain`; aus HTML nur über `html_to_text` (entfernt head,
  style, script, Kommentare, fasst Leerraum zusammen). Enthält ein gespeicherter Text noch
  CSS oder Tags aus der früheren Extraktion, wird er beim Lesen aus dem HTML-Teil neu
  gewonnen (`display_body`), ohne Datenmigration. HTML wird beim Lesen erneut bereinigt.
- Kompaktansicht: Zusammenfassung nur aus gespeichertem Ergebnis der Aufgabe `summarize`
  (nur bei freigegebenem Anbieter, IBAN maskiert), sonst deterministischer Auszug der ersten
  Sätze. CRM-Hinweis nur aus der vorhandenen Zuordnung und nur mit dem jeweiligen Leserecht
  (Kontakte, Objekte, Tickets, Buchhaltung). Offene Posten: Rest je Posten = Betrag minus
  Ausgleiche bis heute (B07), nur lesend. "Kurz senden" legt den Antwortentwurf an und
  reicht ihn über `POST /mail/messages/{id}/submit` ein; Vier-Augen-Regel und
  Re-Authentifizierung der Freigabe gelten unverändert, es gibt keinen direkten Versand.
- `classify_email` v3: `contact_id`/`property_id` nur aus der Kandidatenliste (Zuordnung und
  genannte Objektnummer; Kontakt ohne Namen an den Anbieter), Termin nur mit Datum, das im
  Text steht, `intent`/`invoice_number` zuerst aus der Schlüsselwortregel, eine KI-Nummer nur
  wörtlich aus dem Text, Tonfall und Platzhalter nur aus festen Listen. Anhänge gehen nur mit
  Dateiname und Typ ein. Stilvorgaben aus `Mailbox.reply_style`, sonst Standardpostfach.
  Alles bleibt Vorschlag (Regel 0.1.6).
