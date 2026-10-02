# AI-MASK-03 IBAN-Maskierung nach realer IBAN-Länge

* ID: AI-MASK-03
* Geltungsbereich: Maskierung vor KI-Anbieteraufrufen in `mhvp.objektakte.masking` und `mhvp.receipts.masking` (einschließlich `iban_candidates` und `contains_iban`).
* Regel: Ein IBAN-förmiges Zeichenmuster (zwei Buchstaben, zwei Ziffern, Gruppen mit oder ohne Trenner) wird nur maskiert, wenn es ohne Trenner 15 bis 34 alphanumerische Zeichen hat. Kürzere Muster wie Dateinamen (`WE12.pdf`) oder Laufkennungen (`bd27d253`) bleiben stehen. Innerhalb der Länge wird auch bei falscher Prüfziffer maskiert (Datenschutz vor Klassifikation). Folgt einer IBAN ohne Trenner ein kurzes Wort, kann dieses mit maskiert werden; das ist bewusst sicher. Die Namensmaskierung bleibt unverändert, eine Übermaskierung zweier großgeschriebener Substantive ist bekannt und nur dokumentiert.
* Quellenstatus Anhang C: Produktschutz (Längenbereich nach ISO 13616, kein gesetzlicher Maßstab für die Maskierung).
* Abnahmefall: `tests/unit/test_m35_masking.py::test_ag15_short_iban_shaped_tokens_not_masked`, `tests/unit/test_receipts_masking.py::test_ag15_short_iban_shaped_tokens_not_masked_receipts`, Eval-Fall `cd-overmask_filename`.
* Änderungsgrund: Rest AF21 aus Welle 17 (Übermaskierung von Dateinamen und Laufkennungen).
