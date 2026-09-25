# M11-finapi-dedup Umsatzabgleich von finAPI Umsätzen (Wiedereinlesen, Doppelzahlungen)

| Field | Content |
| --- | --- |
| ID | `M11-finapi-dedup` |
| Title | Idempotente Übernahme von finAPI Umsätzen: Bankreferenz vorrangig, Inhalt nur als Hinweis (D05) |
| Scope | Domäne `banking`, Tabellen `bank_transaction`, `finapi_account_link`; gilt nur für Konten mit `connector = aggregator_finapi` |
| Source status | Keine Rechtsnorm im Quellenregister einschlägig; Produktschutz (GoBD-nahe Nachvollziehbarkeit, keine Doppel- oder verlorenen Buchungen) |
| Acceptance case | D05 (annex D), Abnahmefälle 9 bis 13 des Banking-Zusatz-Master-Prompts (Abschnitt 14); Tests `apps/api/tests/banking/test_finapi.py` |
| Implementation | `mhvp.banking.services.import_finapi_transactions` (wiederverwendet `content_hash`/`pair_transfer` aus dem Dateiimport), `mhvp.banking.tasks.finapi_fetch` |
| Change reason | Banking-Zusatz-Master-Prompt Abschnitt 9, Auftrag 25.09.2026 |

## Regeln

- Primärschlüssel je Konto ist die finAPI Transaktions-ID (`bank_reference = "finapi:<id>"`).
  Ein erneuter Abruf mit derselben ID hat keine zusätzliche Wirkung (Wiedereinlesen ohne
  Doppelbuchung).
- Fehlt eine Bankreferenz oder ändert sie sich bei Wiederanbindung, entscheidet ein
  Inhalts-Hash (IBAN-Fingerabdruck, Buchungsdatum, Betrag, Verwendungszweck, End-to-End-ID,
  Gegen-IBAN) nur über eine Prüfkennzeichnung (`needs_review`), nie über ein automatisches
  Zusammenlegen. Zwei echte Zahlungen mit gleichem Betrag, Datum und Text bleiben zwei
  Umsätze, sobald ihre Bankreferenzen verschieden sind.
- Ein bereits verbuchter Umsatz (`journal_entry_id` gesetzt) wird durch einen erneuten Abruf
  nie überschrieben; eine abweichende Referenz erzeugt höchstens einen neuen, zur Prüfung
  markierten Datensatz.
- Interne Umbuchungen zwischen eigenen Konten desselben Rechtsträgers werden wie beim
  Dateiimport gepaart (`pair_transfer`), nicht als Einnahme oder Ausgabe behandelt (D04).
- Als „entfernt“ gemeldete finAPI-Umsätze (`isRemoved`) werden nicht automatisch als Storno
  gebucht; sie werden beim Einlesen ausgelassen und ein bereits übernommener Umsatz bleibt
  bestehen, bis eine Person ihn prüft (kein stillschweigendes Löschen abgestimmter Daten).
