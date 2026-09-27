# M19-02 Beiratsbeteiligung bei Tickets und Aufträgen: Vorlage, Frist, Rückmeldung, kein Geldbezug

| Field | Content |
| --- | --- |
| ID | `M19-02` (Beiratsbeteiligung; die gleichnamige ID der Ticketvorlagen liegt in `M19-02-ticket-templates.md`) |
| Title | Bei WEG-Objekten legt die Verwaltung ein Ticket oder den Auftrag dahinter dem Verwaltungsbeirat zur Kenntnis oder um ein Votum vor; Beiratsmitglieder antworten im Portal oder die Verwaltung erfasst die Rückmeldung; alles steht als Protokoll am Ticket. Das Votum ist Information, die Freigabe bleibt bei der Verwaltung, eine Zahlung entsteht nie |
| Scope | Mandanten mit GdWE (`legal_entity.kind = hoa`), Modul `mhvp.tickets.board` (Tabellen `ticket_board_policy`, `ticket_board_submission`, `ticket_board_vote`, Migration 0203, RLS nach ADR 0002), Portal `/portal/board/submissions`, CRM Ticketseite (`TicketBoardPanel`), Portalseite `/vorlagen` |
| Source status | Rechtsgrundlage nur für die Rolle: § 29 WEG (Anhang C R03), der Beirat unterstützt und überwacht den Verwalter; eine Zuständigkeit des Beirats für die Freigabe von Aufträgen oder Zahlungen folgt daraus nicht. Ob und ab welcher Wertgrenze der Beirat einzubinden ist, ergibt sich aus Beschlüssen und Verwaltervertrag der jeweiligen GdWE, die nicht im Quellenregister stehen. Deshalb Produktschutz (0.2): Wertgrenze und Kategorien sind eine reine Empfehlungsregel je Mandant, keine Rechtsvorgabe. Einschätzung, keine Rechtsberatung; bei Streit Rechtsanwalt. Offene Entscheidung M19-02 (Wertgrenzen und Zuständigkeit je GdWE), Eigentümer Betreiber, Beschlusslage folgt mit M25. Kein Gate betroffen, da kein Geldfluss |
| Acceptance case | Keiner in Anhang D. Tests `apps/api/tests/integration/test_m19_board_submissions.py` (Rollen, nur Beirat der eigenen GdWE, Frist, Mandantentrennung, Protokoll, Freigabe bleibt bei der Verwaltung); `apps/web-crm/src/components/tickets/TicketBoardPanel.test.tsx`; `apps/web-portal/src/components/portal/BoardSubmissions.test.tsx` |
| Implementation | Version nach 1.34.3 (Migration 0203) |
| Change reason | Betreiberauftrag 27.09.2026 (M19-02): Beiratsbeteiligung mit Frist, Portalabstimmung und Protokoll |

## Regel

1. **Beiratsmitglieder aus den Stammdaten.** Mitglieder sind die Ansprechpartner des Objekts
   mit Kategorie `board` (Beirat, `property_contact.category_code`, Abschnitt 6.2), gültig am
   Vorlagetag. Keine eigene Rollentabelle. Die Kontakt-IDs werden auf der Vorlage
   eingefroren (`member_contact_ids`), damit das Protokoll zeigt, wer gefragt wurde.
2. **Vorlage nur bei WEG.** `POST /tickets/{id}/board-submissions` (`tickets:update`) verlangt
   ein Objekt mit GdWE (sonst 422), mindestens ein Beiratsmitglied (sonst 409) und eine
   Frist `due_on` nicht in der Vergangenheit. Art `info` (zur Kenntnis) oder `consent` (um
   Votum), optional Bezug auf einen Auftrag des Tickets; dessen Angebotsbetrag wird als
   `amount` übernommen. Bei Art `consent` mit Auftrag wird `requires_board_approval` am
   Auftrag gesetzt, so dass die bestehende Vermerkpflicht bei der Freigabe greift.
3. **Empfehlungsregel je Mandant.** `ticket_board_policy` (Wertgrenze, Kategorien, Standard
   `instandhaltung`, Standardart, Standardfrist; `GET/PUT /tickets/board/policy`,
   Änderung mit `tickets:approve`) liefert nur eine Empfehlung im Ticket. Sie sperrt keinen
   Auftragsschritt und gibt nichts frei.
4. **Rückmeldung im Portal.** `GET /portal/board/submissions` zeigt nur Vorlagen, auf denen
   der Kontakt des Portalkontos als Mitglied steht; fremde Vorlagen und andere Mandanten
   antworten 404 ohne Hinweis. `POST .../{id}/votes` (Zustimmung, Ablehnung, Kommentar mit
   Text) ist bis einschließlich `due_on` und nur bei offener Vorlage möglich (sonst 409).
   Jede Rückmeldung ist ein eigener Datensatz (append only), nichts wird überschrieben.
5. **Rückmeldung im CRM.** `POST /tickets/board/submissions/{id}/votes` (`tickets:update`)
   erfasst eine anders eingegangene Rückmeldung (Telefon, Brief) für ein vorgelegtes Mitglied
   mit Quelle `crm`; auch nach der Frist, solange die Vorlage offen ist.
   `POST .../close` schließt mit Ergebnisvermerk.
6. **Protokoll am Ticket.** Vorlage, jede Rückmeldung und der Abschluss stehen als
   `ticket_event` (`board_submission`, `board_vote`, `board_submission_closed`) im Verlauf;
   Domänenereignisse `ticket.board_submitted`, `ticket.board_vote`.
7. **Kein Geldbezug.** Das Beiratsvotum ändert keinen Auftragsstatus, keine Freigabe, keine
   Buchung und keine Zahlung. Die Freigabe eines Auftrags bleibt `POST /tickets/work-orders/{id}/steps`
   mit `tickets:approve` und Vermerk (bestehende Regel). G1 bis G5 bleiben unberührt.

## Offene Punkte

- Wertgrenzen und Zuständigkeit je GdWE (Betreiber, M19-02) und Beschlusslage (M25).
- Benachrichtigung der Beiratsmitglieder per E-Mail bei neuer Vorlage ist nicht enthalten
  (nur Portalansicht und Ereignis); Entscheidung Betreiber.
