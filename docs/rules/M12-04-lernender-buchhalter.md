# M12-04 Lernender Buchhalter: Entscheidungsprotokoll, Storno-Grundcode, Regel-Lebenszyklus

| Field | Content |
| --- | --- |
| ID | `M12-04` |
| Title | Lernender Buchhalter: je Bankumsatz werden die gezeigten Vorschläge der Stufe 1 und die Entscheidung einer Person (unverändert übernommen, geändert mit Diff, abgelehnt mit Grund, ignoriert mit Grund, Storno als Gegenbeispiel) als unveränderliches Protokoll gespeichert; Stornos tragen einen Grundcode; Bankregeln erzeugen Lebenszyklus-Ereignisse. Nichts davon bucht, zahlt oder öffnet ein Gate |
| Scope | Alle Mandanten, alle Rechtsträger (WEG, Miete, SEV), Ein- und Ausgänge; nur bei Mandantenschalter `learning_bookkeeper_enabled` (Standard aus). Schritte S0 und S1 des Fahrplans in `docs/plans/M12-lernender-buchhalter-und-luecken-2026-09-28.md`. Nicht erfasst (Folgeschritte): Gedächtnis Stufe 1d (S3), Fallklassen und Stufe L1 (S4), Regelvorschläge aus Wiederholung (S5), Verifier, Runner L2 und Nachkontrolle (S6), KI-Tie-Breaker (S8). Immoware24-Journal, Importrohzeilen, Migrationsjournal, Entwürfe und nicht gebuchte Modellantworten sind nie Lernquelle (7.4 Nr. 6) |
| Source status | Fachliche Umsetzung nach 7.4 Nr. 2 bis 6, 6.9.4, 9.2 und 15.1; Produktschutz (keine Rechtsnorm). B03 (Storno statt Überschreiben) wird um den Grundcode erweitert. Datenschutz: das Protokoll enthält Zahlerdaten in pseudonymer Form (IBAN-Fingerabdruck, Kennungen); Verzeichniseintrag, Aufbewahrung und Löschkonzept sind Betreiberentscheidung M12-06 (`docs/OPEN_QUESTIONS.md`) und harte Vorbedingung des Schalters |
| Acceptance case | D39 (Tilgungsbestimmung bleibt sichtbar, Vorschlag ist Vorschlag), D51 (Regelkonfiguration nie produktiv ohne Entscheidung und Test). Tests `apps/api/tests/unit/test_posting_decision_diff.py` (Diff, Referenzvorschlag, Merkmalshash, konsolidiertes `rule_matches`, Grundcodes), `apps/api/tests/integration/test_m12_posting_decisions.py` (Schalter aus schreibt nichts, Schalter braucht accounting:approve plus tenant_settings:update, Snapshot nach Import-Commit idempotent je Lauf, Refresh bei geändertem Hash, Buchung unverändert und geändert mit Diff, veralteter Vorschlag 409 `MHVP-BANK-0021`, Ablehnung mit Pflichtgrund, Ignorieren und Wiedereröffnen, Storno mit Grundcode über den Watermark-Job mit Gegenbeispiel und Neubuchung, DB-Guard, Mandanten- und Rechtsträgertrennung, Regel-Ereignisse, Massenbestätigung mit Kennzeichen, Import-Job gegen manuelle Buchung) |
| Implementation | Migration `0232_learning_bookkeeper_decisions` (down_revision `0223`, Umkettung durch die Integration). Module `mhvp.banking.features` (Merkmalsextraktion, `RULE_VERSION`), `mhvp.banking.decisions` (reine Diff-Funktionen), `mhvp.banking.proposals` (Tabelle `posting_decision`, Snapshot, Entscheidungen), `mhvp.banking.events_consumer` (Watermark-Job, Tabelle `banking_event_watermark`, Beat `mhvp.banking.process_events`), `mhvp.banking.event_types`, Task `mhvp.banking.compute_proposals`; `mhvp.accounting.models.ReversalReason` und `journal_entry.reversal_reason_code`; Index `ix_journal_entry_bank_transaction`; Endpunkte `POST /banking/transactions/{id}/reject`, `/reopen`, `GET /banking/transactions/{id}/decisions`, `GET`/`PUT /banking/learning`; `BookIn` mit `proposal_id`, `chosen`, `discount`; ADR 0013. S3 (29.09.2026): `mhvp.banking.history` (Gegenparteihistorie aus `posting_decision`, Kreditorverlauf), Quellen `history` und `invoice` sowie Arten `history`, `transfer`, `account_text` in `posting_proposal.propose`; Merkmale `history`, `linked_invoices`, `payment_order`, `transfer_pair`, `account_texts`, `contract_end` in `features.collect`; Feld `evidence` je Vorschlag (Anzahl, Widersprüche, Journalsätze, Periodizität). S7: `GET /receipts/drafts/{id}?ledger_id&provider_contact_id` mit `account_proposals` (Quelle Verlauf je Position), Entscheidungs-Diff in `receipt_draft.account_proposal_decision` und im Ereignis `receipt_draft.confirmed` |
| Change reason | Fahrplan S0 und S1 vom 28.09.2026 (Lückenanalyse): ohne persistierte Vorschläge und Entscheidungen gibt es keine Grundwahrheit für Lernen und Messung (Regel 0.1.8). Freigabe des Schalters durch den Betreiber nach Datenschutzprüfung offen. S3 und S7 (29.09.2026): Sofortwirkung des Gedächtnisses ohne Regel (Fahrplan 3.3) und Kontierung aus verknüpfter Rechnung; Betreiberentscheidung vom 28.09.2026 zu Aufbewahrung, Löschung und Leserecht in M12-06 festgehalten |

## Ablauf

1. Import (Datei, CSV, finAPI, FinTS) schreibt die Umsätze und committet. Danach berechnet der
   Task `mhvp.banking.compute_proposals` je offenem Umsatz des Laufs den Snapshot der Stufe 1
   (`posting_proposal.propose` auf den Merkmalen aus `features.collect`) und speichert ihn als
   `posting_decision` im Zustand `pending` mit `engine_version`, `rule_version`,
   `features_hash`, Fallklasse, bester Quelle und Konfidenz. Gleicher Hash: keine neue Zeile.
   Geänderter Hash (neuer offener Posten, freigegebene Regel, freigegebene Zahler-IBAN): alte
   Zeile `expired`, neue Runde mit `supersedes_id`. Je Umsatz höchstens eine offene Runde.
2. Anzeige: `GET /banking/transactions/{id}/posting-proposals` liefert unter `learning` die
   Kennung der offenen Runde. Lesen schreibt nie.
3. Entscheidung einer Person schließt die Runde genau einmal: Buchung über
   `POST /banking/transactions/{id}/book` mit `proposal_id` und `chosen` ergibt
   `accepted_unchanged` (genau der gewählte Vorschlag) oder `modified` (Diff aus Posten,
   Gegenkonto und Skonto; Buchungstext zählt nicht); Wahl des zweiten Vorschlags ist keine
   Änderung. `POST .../reject` mit Pflichtgrund (mindestens drei Zeichen) ergibt `rejected`
   und öffnet die nächste Runde, der Umsatz bleibt offen; mit `ai_proposal_id` wird der
   KI-Vorschlag als abgelehnt markiert und über `mhvp.ai.examples.record_rejection` gemeldet.
   `POST .../ignore` ergibt `ignored`; `POST .../reopen` mit Grund macht den Umsatz wieder
   offen und nimmt einen neuen Snapshot. Massenbestätigungen tragen `bulk = true`.
4. Veraltete Kennung: nennt `proposal_id` nicht die offene Runde, antwortet die Plattform mit
   409 `MHVP-BANK-0021`, nichts wird gebucht. Ohne Kennung (Entscheidung vor dem Job) wird
   der Snapshot zum Entscheidungszeitpunkt aufgenommen.
5. Storno: `POST /accounting/ledgers/{id}/entries/{id}/reverse` verlangt weiterhin den
   Freitext und nimmt zusätzlich `reason_code` (`input_error`, `wrong_assignment`,
   `wrong_amount`, `wrong_date`, `duplicate`, `bank_return`, `run_reversal`,
   `automation_error`, `other`; Standard `other`). Der Watermark-Job liest
   `journal_entry.reversed`, schreibt je gebuchter Entscheidung eine Zeile `reversed`
   (Gegenbeispiel), setzt den Umsatz auf `new` (die Satznummer bleibt als Verlauf) und
   meldet `bank_transaction.posting_reversed`; der Umsatz kann genau einmal neu gebucht
   werden. Lernquelle sind nur Entscheidungen von Personen an nicht stornierten Buchungen.
6. Unveränderlichkeit: der Trigger `mhvp_posting_decision_guard` verbietet Löschen, erlaubt
   nur den Übergang `pending` zu einem Endzustand und sperrt geschlossene Zeilen vollständig.
7. Schalter: `PUT /banking/learning` mit Grund, Recht accounting:approve plus
   tenant_settings:update, Ereignis `tenant.learning_bookkeeper_changed`. Aus: nichts wird
   geschrieben, vorhandene Zeilen bleiben (Aufbewahrung nach M12-06).
8. Ereignisse: `bank_rule.proposed`, `bank_rule.approved`, `bank_rule.activated`,
   `bank_rule.disabled`, `invoice.updated`, `bank_transaction.proposal_rejected`,
   `bank_transaction.reopened`, `bank_transaction.posting_reversed`; `bank_transaction.booked`
   trägt zusätzlich `decision_id`, `decision_status`, `proposal_source`, `discount`, `bulk`.

## Stufe 1d und Kreditorverlauf (S3, S7)

Quelle `history`: bestätigte, nicht stornierte Entscheidungen von Personen derselben
Gegenpartei (IBAN-Fingerabdruck oder Gläubiger-ID) im selben Rechtsträger und derselben
Richtung; Konfidenz 0,4 plus 0,1 je konsistentem Fall, Deckel 0,85, halbiert je Widerspruch,
mindestens zwei Fälle, nie eindeutig (A-080). Ein Storno macht die Buchung sofort zum
Gegenbeispiel, weil der Merkmalshash die Historie enthält und der offene Snapshot erneuert
wird. Automatikbuchungen, Immoware24-Journal, Importrohzeilen, Entwürfe und Modellantworten
sind nie Quelle. Quelle `invoice`: Kreditorenkonto, offener Posten und Kostenkonten der
Positionen einer verknüpften gebuchten Rechnung. End-to-End-Referenz eigener
Zahlungsaufträge, Buchungstexte der Sachkonten, Transferpaare und Vertragsende wirken wie in
A-080 beschrieben. Alles nur mit `learning_bookkeeper_enabled`, nichts davon bucht.

Belegeingang (S7): je Rechnungsposition Kontovorschläge aus dem Verlauf des Ausstellers
(bestätigte Rechnungen im Buchungskreis, Gegenkonten seiner Bankbuchungen), mit Anzahl,
Quelle Verlauf und Grund; nichts ist vorausgewählt. Bei der Bestätigung wird der Vorschlag
neu berechnet und die Abweichung je Position festgehalten (`account_proposal_decision`).
Umlagefähigkeit, Betriebskostenart, § 35a und Umsatzsteuer werden nie aus dem Vorschlag
übernommen (M17-01, M14-02).

## Versionen

| Version | Bedeutung | Änderung |
| --- | --- | --- |
| `ENGINE_VERSION 2026.09.28-1` | Stufe-1-Engine `posting_proposal.propose` | Stand der Konsolidierung, keine fachliche Änderung der Vorschläge |
| `RULE_VERSION 2026.09.28-1` | Merkmalsextraktion `features.collect` | erste Version; Bump bei jeder Änderung der Merkmale |
| `ENGINE_VERSION 2026.09.28-2` | Stufe-1-Engine | S3: Quellen history und invoice, Transferpaar, Buchungstexte, End-to-End-Referenz, Vertragsende |
| `RULE_VERSION 2026.09.28-2` | Merkmalsextraktion | S3: Historie, verknüpfte Rechnungen, Zahlungsauftrag, Transferpaar, Buchungstexte, Vertragsende im Hash |
