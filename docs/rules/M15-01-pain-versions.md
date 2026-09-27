# M15-01 Zahlungsdatei pain.001 in der mit der Bank vereinbarten Version, Prüfsumme, Download-Protokoll, Einreichungsweg

| Field | Content |
| --- | --- |
| ID | `M15-01` |
| Title | Überweisungsdatei pain.001 (SEPA Credit Transfer) in der je Bankkonto konfigurierten Version, Anzahl und Kontrollsumme im Sammler, Prüfsumme der abgelegten Datei, Vier-Augen vor Dateierzeugung, Download-Protokoll, manuelle Einreichung als einziger nutzbarer Weg |
| Scope | `mhvp.banking.payments` (`pain001`, `validate_pain001`, `file_sha256`, `control_sum`), `mhvp.banking.payment_submitters` (`PaymentSubmitter`, `FileDownloadSubmitter`, `FintsSubmitter` Gerüst), `mhvp.banking.ebics` (`EbicsSubmitter` Gerüst), `mhvp.banking.models` (`payment_batch` Spalten, `payment_bank_config`, `payment_file_download`), `mhvp.banking.routers` (`/api/v1/banking/payment-batches`, `/payment-bank-config`); alle Mandanten; Datei und Einreichung nur hinter G2 |
| Source status | Formatstruktur aus den öffentlichen ISO-20022-Schemata pain.001.001.03 und pain.001.001.09 (iso20022.org, Kopien unter `apps/api/tests/data/iso20022/`), gegen die die erzeugten Dateien im Test validiert werden. Die Auswahl der Version je Bank, bankspezifische Einschränkungen (DK-Anlage 3), Zeichensatz und Einreichungsweg sind Betreibereingabe und nicht belegt (P05, M15-01). Produktschutz: Vier-Augen (D36), Dateiabgabe nur hinter G2, Prüfsumme, Protokoll |
| Acceptance case | D06, D35, D36 (bestehend); Tests `apps/api/tests/unit/test_pain001_versions.py` (XSD beide Versionen, BIC/BICFI, Kontrollsumme, Manipulation erkannt, Gerüste lehnen ab) und `apps/api/tests/integration/test_m15_payment_submission.py` (10 Überweisungen, 10 Lastschriften, Version aus Kontokonfiguration, G2-Sperre, Download-Protokoll, Einreichung nur nach Download und mit Referenz, FinTS/EBICS 409 `MHVP-BANK-0017`) |
| Implementation | Migration `0197_payment_submission`; Fehlercodes `MHVP-BANK-0017`, `MHVP-BANK-0018` |
| Change reason | M15-01, M15-03, V2 (27.09.2026): Versionswahl je Bank, XSD-Prüfung, Einreichungsschnittstelle, Bank-Sandbox-Testfall |

## Regeln

- Erzeugt werden pain.001.001.03 oder pain.001.001.09 (Vorgabe 09) je nach
  `payment_bank_config.pain001_version` des Auftraggeberkontos; andere Versionen werden mit
  422 abgelehnt. pain.008 bleibt bei pain.008.001.02 (`mhvp.accounting.direct_debit`); die
  Version pain.008.001.08 ist konfigurierbar, wird aber noch nicht erzeugt (offen).
- Ein `PmtInf`-Block je Ausführungsdatum, `BtchBookg = true`, `SvcLvl = SEPA`, `ChrgBr = SLEV`,
  `DbtrAgt` mit BIC (in 09 `BICFI`) oder `Othr/Id = NOTPROVIDED`. Texte werden auf den
  SEPA-Zeichensatz beschränkt (`sepa_text`).
- Der Sammler speichert Anzahl (`transaction_count`), Kontrollsumme (`control_sum`) und
  SHA-256 der abgelegten Datei (`file_sha256`). Vor jeder Abgabe werden die abgelegten
  Bytes gegen die Prüfsumme und die Strukturprüfung geprüft; Abweichung sperrt die Abgabe
  (`MHVP-BANK-0018`).
- Datei nur nach vollständiger Vier-Augen-Freigabe aller Aufträge und nur aus dem
  führenden Buchungskreis; Erzeugung, Download und Einreichung nur hinter G2.
- Jeder Download wird in `payment_file_download` mit Benutzer, Zeit, Prüfsumme und
  Client-Adresse protokolliert und als Ereignis `payment_batch.downloaded` erfasst.
- Einreichungsweg `file`: eine Person bestätigt nach mindestens einem protokollierten
  Download die Einreichung mit Bankreferenz; der Sammler und seine Aufträge werden
  `submitted`. Eine zweite Bestätigung wird abgelehnt. `fints` und `ebics` sind Gerüste
  und lehnen mit `MHVP-BANK-0017` ab, bis Betreiberentscheidung V2, Vertrag,
  Initialisierung und Feature-Flag vorliegen.
- Die Ausführung wird ausschließlich durch den importierten Bankumsatz nachgewiesen (D06);
  Einreichung ändert keinen offenen Posten.

## Nachtrag 27.09.2026 (M15-01, pain.008)

- pain.008 wird nun ebenfalls je Bankkonto in der konfigurierten Version erzeugt
  (`payment_bank_config.pain008_version`, pain.008.001.02 oder pain.008.001.08, Vorgabe .02);
  eine unbekannte Version wird mit 422 abgelehnt. Beide Versionen sind gegen die
  öffentlichen XSD-Schemata getestet (`apps/api/tests/unit/test_pain008_versions.py`,
  `apps/api/tests/data/iso20022/pain.008.001.0{2,8}.xsd`); .08 verwendet `BICFI` statt `BIC`.
- Mandatsangaben (`MndtId`, `DtOfSgntr`), Gläubiger-Identifikationsnummer und die
  Sequenzart (`SeqTp` FRST/RCUR aus der Anzahl vorheriger ausgegebener Läufe unter
  demselben Mandat, `mhvp.accounting.direct_debit.sequence_type`) bleiben unverändert
  aus M15-02.
- Download und Einreichung folgen demselben Muster wie bei pain.001, ohne eigenes
  Schema: der Download wird als Ereignis `direct_debit_run.file_downloaded` mit
  SHA-256-Prüfsumme im `domain_event`-Protokoll erfasst (`GET
  /accounting/direct-debits/{id}/downloads`) statt in einer eigenen Tabelle; die
  Einreichung wird analog zu `FileDownloadSubmitter` durch eine Person mit Bankreferenz
  bestätigt (`POST .../submit`, Ereignis `direct_debit_run.submitted`), ist aber nicht
  dieselbe Klasse (der Lauf trägt kein `PaymentBatch`-Schema). Beide Endpunkte bleiben
  hinter G2; eine zweite Bestätigung ändert die erste Referenz nicht (B08).
- Vorabinformation (Pre-Notification): die Frist vor dem Einzug ist konfigurierbar
  (`lead_days`, Vorgabe 14 Tage) und wird im Text als Entwurf mit offenem
  Quellenstatus ausgewiesen; der bankfachlich verbindliche Mindestwert ist weiterhin
  nicht belegt (siehe `docs/OPEN_QUESTIONS.md`).
- CRM (Lastschriftläufe): Version je Lauf, Download mit Protokollanzeige (Zeit,
  Prüfsumme bzw. Referenz) und Bestätigungsformular für die Einreichung; die Sperre
  hinter G2 bleibt serverseitig, ein Versuch bei geschlossenem Gate zeigt nur die
  Fehlermeldung.
- Migration `0211` ist ein No-op: alle Felder existieren bereits
  (`payment_bank_config.pain008_version`, `direct_debit_run.format`,
  `domain_event`).
