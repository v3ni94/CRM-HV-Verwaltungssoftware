# AA01 Prüfbericht Buchungsregister, versionierte Vermerke, Freigabestufen in Jobs

| Field | Content |
| --- | --- |
| ID | `AA01` (Befunde GA05-01, GA05-02, GA05-03, GA14-01, GA14-06) |
| Title | Konsistenzprüfung mit Nummernlücken und Nebenbuchabgleich, Vermerke zu gebuchten Sätzen getrennt und versioniert, Jobs lesen die Freigabestufe je Mandant aus der Datenbank, Register der gate-pflichtigen Routen |
| Scope | `mhvp.accounting.services.checks`, `numbering_findings`, `subledger_findings`, `subledger_reconciliation`, `GET /accounting/ledgers/{id}/checks`, `JournalEntryNote` mit `GET/POST /accounting/ledgers/{id}/entries/{id}/notes` (Migration 0303), `mhvp.core.release_gates.JobDbReleaseGateResolver`, Worker-Start `mhvp.worker`, CRM `EntryNotes` |
| Source status | Fachliche Umsetzung von 7.1 B03 Satz 3, B04 Satz 3, B09 Satz 4 und Regel 0.1.4, 18.0. Keine Rechtsaussage; die Einstufung der ungegateten Geldrouten ist offen (AA01-01) |
| Acceptance case | Tests `apps/api/tests/integration/test_ga05_ledger_checks.py`, `test_ga14_job_gates.py`, `apps/api/tests/unit/test_ga14_gate_coverage.py`; Web: `EntryNotes.test.tsx` |
| Implementation | Migration 0303 |
| Change reason | Lückenliste 01.10.2026: Nummernlücken und Zählerabweichung nicht prüfbar, Vermerke fehlten, Nebenbuchabgleich fehlte, Worker blieb bei geöffnetem G1 geschlossen, kein Abdeckungsnachweis der Gates |

## Regel

1. **Nummernfolge (B04).** Je Buchungskreis und Geschäftsjahr laufen die Nummern gebuchter
   Sätze von 1 bis zur höchsten Nummer ohne Lücke; jede fehlende Nummer ist ein Befund
   `Nummernlücke JJJJ-n`. Weicht der Zählerstand `journal_number_counter.last_number` von der
   höchsten Nummer ab (auch Zähler ohne Sätze), ist das ein Befund. Befunde setzen `ok` auf false.
2. **Nebenbuch (B09), harte Prüfung.** Je Debitoren- und Kreditorenkonto übersteigen die
   offenen Posten nie die Sollseite (Kreditor: Habenseite) und die Ausgleiche nie die Gegenseite;
   Ausgleiche werden je Posten zuerst summiert, damit kein Posten mehrfach zählt.
3. **Nebenbuch (B09), Abgleich.** `subledger` zeigt je Konto Hauptbuchsaldo (Soll minus Haben),
   Restbetrag der offenen Posten (Forderung positiv, Verbindlichkeit negativ) und Differenz zum
   Stichtag `as_of`. Eine Differenz ist kein Fehler (nicht zugeordnete Zahlungen, Buchungen ohne
   Posten), sie steht in `subledger_differences` zur Prüfung und setzt `ok` nicht.
4. **Vermerke (B03).** Vermerke gibt es nur zu gebuchten Sätzen (sonst 409 `MHVP-ACC-0009`).
   Sie ändern den Buchungsinhalt nicht. Die Tabelle ist append only (Trigger
   `forbid_mutation`, auch für den Tabelleneigentümer). Eine Änderung ist eine neue Version mit
   `supersedes_id` auf die aktuelle Version derselben Kette (`note_key`); eine bereits ersetzte
   Version kann nicht erneut ersetzt werden (409 `MHVP-ACC-0010`). Lesen mit
   `accounting:read`, Schreiben mit `accounting:update`. Kein Gate: ein Vermerk ist keine Buchung.
5. **Freigabestufen in Jobs (0.1.4).** Der Worker setzt beim Start (`worker_init`,
   `worker_process_init`) `job_release_gate_resolver` auf `JobDbReleaseGateResolver`; dieser
   liest je Aufruf mit eigener Verbindung ohne Pool den genehmigten Antrag des Mandanten
   (Laufzeitrolle, RLS). Fehler bedeuten geschlossen. Ohne Worker-Start bleibt der Standard
   `ClosedReleaseGateResolver`.
6. **Abdeckungsnachweis (18.0).** `GATED_ROUTES` im Test `test_ga14_gate_coverage.py` ist das
   Register der Routen mit Gate-Prüfung (statisch belegt bis fünf Aufrufebenen und
   Abhängigkeiten). Jede neue schreibende Route mit Geld-, Abrechnungs- oder Versandpfad ohne
   Gate lässt den Test fehlschlagen, bis sie gegatet oder in `REVIEWED_UNGATED` eingestuft ist.
   `REVIEWED_UNGATED` ist eine Bestandsaufnahme vom 01.10.2026, keine Freigabe (AA01-01).
