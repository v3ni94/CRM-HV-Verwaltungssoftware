# AQ09-01 Kompensation von Dateien bei Transaktionsabbruch

- ID: AQ09-01 (Regelkennung im Code DOC-BLOB-COMP)
- Geltungsbereich: `mhvp.documents.services.store_document` und alle aufrufenden Stellen, insbesondere Zahlungsdateien (pain.008 Lastschriftlauf `POST /accounting/direct-debit-runs/{id}/file`, pain.001 Zahllauf `POST /banking/payment-batches`).
- Regel: Jede Datei, die innerhalb einer Datenbanktransaktion in den Objektspeicher geschrieben wird, wird in der Sitzung vorgemerkt. Wird die Transaktion zurückgerollt, löscht ein after_rollback Hook die vorgemerkten Dateien. Nach erfolgreichem Commit wird die Vormerkung verworfen; bereits referenzierte Dokumente werden nie gelöscht. Aufbewahrungssperren können nicht betroffen sein, da eine nicht festgeschriebene Datei keinem Dokument zugeordnet ist.
- Fehlerfall: Schlägt das Löschen fehl, wird `document.orphan_blob` mit dem Schlüssel als Fehler protokolliert (manuelles Aufräumen).
- Quellenstatus (Anhang C): Produktschutz (Datenschutz, Datenminimierung); keine eigene Rechtsgrundlage behauptet.
- Abnahmefall: `test_debit_file_abort_leaves_no_orphan_blob`, `test_payment_batch_abort_leaves_no_orphan_blob` in `apps/api/tests/integration/test_aq09_money_flow_robustness.py`.
- Änderungsgrund: AP26 (Welle 26), Befund AQ09-01 aus AP09.
