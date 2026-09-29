# M12-05 Automatikstufen, Verifier, Runner und Nachkontrolle

| Field | Content |
| --- | --- |
| ID | `M12-05` |
| Title | Fallklassen und Automatikstufen je Mandant (L0 Vorschlag, L1 Ein-Klick und Massenbestätigung, L2 Regelautomatik mit Tagesprüfung, L3 mit Stichprobe), Anhebung nur mit Antrag und Freigabe durch eine zweite Person, deterministischer Verifier je Klasse mit Fingerprint, Runner nach jedem Import und Sync, Nachkontrolle mit Fälligkeit, Korrektur ausschließlich als Storno mit Grundcode plus Neubuchung |
| Scope | Alle Mandanten, alle Rechtsträger, Bankumsätze der Klassen `debtor_full`, `debtor_collective` (Deckel L1), `creditor_invoice` (Deckel L2), `recurring_expense` (Deckel L2, nur mit `auto_posting_outgoing_enabled` und Belegkette), `transfer_pair`; `excluded` (Rückläufer, Kaution, Teil- und Überzahlung, unklar) bleibt immer L0. Schritte S4 und S6 des Fahrplans `docs/plans/M12-lernender-buchhalter-und-luecken-2026-09-28.md`. Nicht erfasst: Stichprobe als Nachkontrolle im internen Kontrollsystem (M12-08 offen, L3 technisch vorbereitet, nicht vor G1), Ausschluss nicht nachkontrollierter Automatikbuchungen aus Mahnlauf, Tilgungsvorschlag und Lastschriftlauf (offener Punkt, siehe unten), Rückläufer als Nachkontrolle-Item |
| Source status | Fachliche Umsetzung nach 7.4 Nr. 4 (freigegebene Regel, eindeutiger Rechtsträger, Konto, Vorgang, Betrag, zulässige Tilgung, unabhängiger Test, Betrags- und Fallgrenzen, Protokoll, Abschaltung, Nachkontrolle), 6.9.4, E04, 0.1.6, 0.1.7, B01 bis B03, B05, B08, 18.0 (G1), ADR 0003. Produktschutz (keine Rechtsnorm): Stufenmodell, Eignungsschwellen (A-084), Fallgrenzen (A-086), Werktagslogik (A-087). Betreiberentscheidung vom 28.09.2026 (M12-07): der Runner darf vor G1 Vergleichsbuchungen im nicht führenden Buchungskreis erzeugen; im führenden Buchungskreis bucht er nur bei offenem G1 |
| Acceptance case | D39 (Tilgungsbestimmung: Chronologieprüfung im Verifier), D51 (Regel nie produktiv ohne Entscheidung und Test: Aktivierung mit `max_amount` und Testnachweis bleibt Voraussetzung), D04 und B08 (Transferpaar). Tests `tests/unit/test_bookkeeping_levels.py` (Klassifikation, Deckel, Eignung), `tests/unit/test_bank_verifiers.py` (je Klasse Happy Path, Ablehnungsgründe, Chronologie, Konto-Sperrkriterien, Periodensperre, Belegkette, Fingerprint), `tests/unit/test_m12_levels_replay.py` mit `tests/ai_eval/levels_replay/cases.jsonl`, `tests/integration/test_m12_automation_levels.py` (Antrag 409 `MHVP-BANK-0022` ohne Eignung, Vier Augen, Fremdmandant 404, Ein-Klick bei L0 409 `MHVP-BANK-0023` und bei L1 als manuelle Buchung, Absenkung sofort, Runner ohne L2 bucht nichts, Runner bei L2 mit Fingerprint, Nachkontrolle und Ereignis, Verifier-Ablehnung Chronologie, überfällige Nachkontrolle sperrt die Klasse, Nachkontrolle ohne `accounting:review` 403, Korrigieren als Storno plus Neubuchung mit Regelrückstufung über den Watermark-Job, Prüfexport) |
| Implementation | Migration `0241_bookkeeping_automation` (down_revision `0237`): `tenant_settings.bookkeeping_automation`, `auto_posting_outgoing_enabled`, Tabellen `bookkeeping_level_request` und `auto_posting_review` (RLS), `posting_decision.verifier_fingerprint` und `review_due_on`. Module `mhvp.banking.levels` (Klassen, Deckel, Kennzahlen, Anträge, Herabstufung), `mhvp.banking.verifiers` (reine Prüfer je Klasse, `VERIFIER_VERSION`), `mhvp.banking.runner` (Advisory-Lock je Mandant, G1-oder-nicht-führend, Fallgrenzen, Entscheidung `auto_posted`, Nachkontrolle, Sync-Zähler `auto_*` in `bank_sync_run.counts`), `mhvp.banking.review` (Nachkontrolle, `correct`), Recht `accounting:review`, Task `mhvp.banking.levels_refresh` (Nachtjob, nur Herabstufung), Runner-Aufruf in `tasks.compute_proposals_once` nach jedem Import und Sync sowie `POST /banking/auto-post`. Endpunkte `GET /banking/automation/levels`, `GET /banking/automation/metrics`, `POST /banking/automation/level-requests`, `POST .../{id}/approve`, `POST .../{id}/reject`, `PUT /banking/automation/levels` (Absenkung), `PUT /banking/automation/outgoing`, `POST /banking/transactions/{id}/accept`, `POST /banking/transactions/{id}/correct`, `GET /banking/auto-posting/reviews`, `POST /banking/auto-posting/reviews/{id}`. Ereignisse `bookkeeping_level.requested`, `bookkeeping_level.changed`, `bank_transaction.auto_posted`, `bank_transaction.clarification_needed`, `bank_transaction.corrected`, `bank_auto_post.run_stopped`, `auto_posting_review.decided`, `tenant.auto_posting_outgoing_changed`. CRM: `components/banking/AutomationLevels.tsx` (Einstellungen, Buchhaltung, Automatikstufen), `AutoPostingReview.tsx` (Bank, Nachkontrolle mit Korrigieren), Hinweis in `BulkConfirm.tsx`. Prüfexport: Tabellen `entscheidungen`, `nachkontrolle`, `automatikstufen`, `regelvorschlaege`, `bankregeln` |
| Change reason | Fahrplan S4 und S6 vom 28.09.2026 und Betreiberauftrag vom 29.09.2026 (Ablösung Immoware24 ohne Parallelbetrieb, Bankumsätze je Objekt automatisch gegen Debitor oder Kreditor buchen, nachträglich korrigierbar). "Nachträglich bearbeitbar" ist ausschließlich B03: Storno mit Grundcode und Neubuchung (`correct`), nie eine Änderung des gebuchten Satzes |

## Fallklassen und Stufen

| Klasse | Bedeutung | Deckel | L1 vorausgewählt | Verifier L2 |
| --- | --- | --- | --- | --- |
| `debtor_full` | Eingang gleicht genau einen offenen Posten voll aus (Stufe 1 `full`, eindeutig) | L3 | ja | aktive Regel, Betrag gleich Rest, ältester offener Posten des Schuldners (Chronologie), kein Kautionsposten, Konto ohne Sperrkriterium |
| `debtor_collective` | Eingang gleicht genau eine Kombination offener Posten aus | L1 | ja | nie automatisch |
| `creditor_invoice` | Ausgang zu einer verknüpften gebuchten Rechnung | L2 | ja | aktive Regel, Rechnungsbetrag gleich Zahlbetrag, Empfänger-IBAN wie Rechnung, Kontierung aus der Rechnung, Konten ohne Sperrkriterium |
| `recurring_expense` | Ausgang gegen Sachkonto nach Regel der Art `posting` | L2 | nur bei Regeltreffer mit Posten | zusätzlich `auto_posting_outgoing_enabled`, Historie gleich Regelkonto, Betrag in beobachteter Spanne, keine abweichende offene Verbindlichkeit, Belegkette (verknüpfter Beleg oder Kennzeichen `no_receipt_required` einer Person), sonst Klärungsstatus `bank_transaction.clarification_needed` statt Buchung |
| `transfer_pair` | Umbuchung zwischen eigenen Konten (D04) | L3 | ja | aktive Regel, Partnerkonto ist Bankkonto des Buchungskreises |
| `excluded` | Rückläufer, Kaution, Teil- und Überzahlung, unklar | L0 | nein | nie |

Stufen: L0 nur Vorschlag (Standard). L1 zeigt `Übernehmen` (`POST /transactions/{id}/accept`) und
wählt in der Massenbestätigung nur deterministisch geprüfte Vorschläge vor; jede Buchung bleibt
eine manuelle Buchung der Person (`created_by` gesetzt), Historie- und KI-Vorschläge nie. L2: der
Runner bucht nach jedem Import und Sync, Nachkontrolle am nächsten Werktag, überfällige
Nachkontrollen sperren die Klasse. L3: gleicher Buchungspfad, Nachkontrolle nur für die
deterministische Stichprobe (Hash der Umsatz-ID, 10 Prozent, 7 Tage), nur `debtor_full` und
`transfer_pair`; produktiv erst nach M12-08 und G1.

Eignung (Produktschutz, A-084): L1 ab `n_decided >= 20` in 90 Tagen und `precision_manual >= 0,95`;
L2 zusätzlich 30 Tage auf L1 und `n_decided >= 50`, `precision_manual >= 0,98`; L3 zusätzlich 60
Tage auf L2, `n_auto >= 100`, `error_rate_auto <= 0,005`. Anhebung nur eine Stufe je Antrag,
Antrag mit Eignungsbericht als Nachweis, Freigabe durch eine andere Person (kein Plattformadmin),
Absenkung durch eine Person sofort. Automatische Herabstufung (Nachtjob `levels_refresh`, nur
abwärts): Fehlerquote der Automatik über 30 Tage größer 0,02 (L3 0,01) senkt eine Stufe, drei
Korrekturen einer L1-Klasse in 30 Tagen senken auf L0.

## Runner

Voraussetzungen, alle im Runner geprüft, nie durch Konfidenz ersetzt: `auto_posting_enabled`
und `learning_bookkeeper_enabled` des Mandanten, Klasse auf L2 oder L3 und nicht durch
überfällige Nachkontrolle gesperrt, G1 offen oder Buchungskreis nicht führend (M12-07), aktive
Regel des Rechtsträgers innerhalb `max_amount`, Verifier der Klasse besteht auf dem neu
berechneten Fall (Snapshot zum Buchungszeitpunkt). Fallgrenzen (A-086): 50 je Regel und Tag,
200 je Lauf, 500 je Mandant und Tag; Erreichen stoppt den Lauf mit `bank_auto_post.run_stopped`.
Periodensperre wird gezählt und übersprungen (`auto_period_locked`), nie umdatiert. Jede
Automatikbuchung: `book_payment` ohne Person, Entscheidung `auto_posted` mit
`verifier_fingerprint` (SHA-256 über Verifier-, Engine- und Regelversion, Merkmalshash, Regel,
Klasse und Buchung) und `review_due_on`, Nachkontrolle-Item, Ereignis
`bank_transaction.auto_posted`, Zähler im Sync-Lauf. Advisory-Lock je Mandant
(`pg_try_advisory_xact_lock`), Zeilensperre je Umsatz wie bei der manuellen Buchung.

## Nachkontrolle und Korrektur

`GET /banking/auto-posting/reviews` listet offene Items mit Fälligkeit; `POST .../{id}` mit
`ok` braucht `accounting:review`. `corrected` und `cancelled` setzen einen Storno voraus:
`POST /banking/transactions/{id}/correct` storniert die gültige Buchung mit Grundcode und
Freitext, meldet `journal_entry.reversed`, schließt die Nachkontrolle als `corrected` und bucht
den Umsatz in derselben Transaktion neu (manuelle Buchung der Person, neue Entscheidungsrunde).
Der Watermark-Job schreibt das Gegenbeispiel, zählt den Widerspruch an der Regel und stuft sie
bei Grundcode `automation_error` von aktiv auf freigegeben zurück (zweiter Fall: abgeschaltet,
Ereignis `bank_rule.downgraded`). Ein Storno über den Buchungskreis ohne Neubuchung schließt
die Nachkontrolle als `cancelled`.

## Offene Punkte

- Ausschluss nicht nachkontrollierter Automatikbuchungen aus Mahnlauf, Tilgungsvorschlag und
  Lastschriftlauf ist noch nicht umgesetzt (Fahrplan S6, `mhvp.accounting.dunning` und
  `direct_debit`); bis dahin gilt: keine Stufe L2 für Mandanten mit produktivem Mahn- oder
  Lastschriftlauf (beide bleiben hinter G1 und G2).
- Rückläufer einer automatisch gebuchten Zahlung erzeugen noch kein Nachkontrolle-Item der Art
  `return`; die Klasse `excluded` verhindert nur die Automatik des Rückläufers selbst.
- Feiertage werden bei der Fälligkeit nicht berücksichtigt (A-087).
