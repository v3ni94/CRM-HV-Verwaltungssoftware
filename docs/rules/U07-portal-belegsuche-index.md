# U07: Trigramm-Index der Portal-Belegsuche und Anzeige Art der Abrechnung je Konto

* ID: U07-01 (M25-06 Rest), U07-02 (SA-08)
* Geltungsbereich: Portal-Belegliste (`GET /api/v1/portal/documents` mit `q`), Kontenplan im CRM.
* Quellenstatus (Anhang C): Fachliche Umsetzung (Produktschutz Leistung), keine Rechtsgrundlage berührt.
* Abnahmefall: `tests/integration/test_u07_document_search_perf.py` (Index vorhanden; mit `MHVP_PERF=1` Messung mit 5.000 Dokumenten), `AccountsManager.test.tsx`.
* Änderungsgrund: Die Suche vergleicht `lower(title)` und `lower(filename)`; der bisherige Index `ix_document_title_trgm` auf `title` kann diese Ausdrücke nicht bedienen. Migration 0299 legt GIN-Trigramm-Indizes auf `lower(title)` und `lower(filename)` an (`pg_trgm` ist laut Baseline 0001 als vertrauenswürdige Erweiterung vorhanden).

Messung (Handmessung auf Entwicklungsdatenbank, 5.000 Dokumente, ein Mandant): Sequenzscan 3,5 ms, der Planer wählt bei dieser Größe den Sequenzscan. Der Index lohnt sich erst bei deutlich größeren Beständen; er ist ohne Risiko für Schreibpfade, aber nicht belegbar wirksam bei 5.000 Zeilen.

SA-08: Der Kontenplan führt `statement_kind` (Hausgeld, Rücklage, Betriebskosten, Sonderumlage, Heizkosten) und die Mehrschlüsselverteilung (`LedgerAccountAllocation`, API vorhanden). Im CRM fehlte nur die Anzeige; sie ist ergänzt. Der Seed-Kontenrahmen setzt `allocation_key_code` weiterhin nur einfach (Fremdbereich accounting, siehe OPEN_QUESTIONS U07-01).
