# GAJ-301 Zahlungsdateien nur mit Freigabe G2

- ID: GAJ-301
- Geltungsbereich: Lastschriftdateien (pain.008) und Zahlungsdateien (pain.001), die als Dokument abgelegt sind; allgemeine Dokumentrouten, Portal (Einzeldownload und Sammel-Download), DMS-Spiegelung, Ereignis-Payload.
- Anforderungstyp: Produktschutz (18.0 G2, 7.5 SEPA). Keine Rechtsgrundlage behauptet.
- Quellenstatus Anhang C: nicht einschlägig (Freigabesperre der Plattform).
- Regel: Ein Dokument gilt als Zahlungsdatei, wenn es in der Kategorie `payment_file` liegt oder ein Lastschriftlauf oder Zahlungsstapel darauf verweist. Inhalt und signierte Download-URL gibt es nur bei offenem G2 (sonst 403 MHVP-GATE-0001). Das Portal gibt Zahlungsdateien nie aus (404). Zahlungsdateien werden nicht in Paperless oder Google Drive gespiegelt. Ereignisse zur Lastschriftdatei enthalten keine Dokument-Id. Metadaten bleiben mit Leserecht lesbar.
- Nachkategorisierung: "Fehlende Standardkategorien ergänzen" ordnet bestehende Zahlungsdateien der Kategorie zu; die Sperre hängt nicht davon ab (Verweisprüfung).
- Abnahmefall: tests/integration/test_m15_direct_debits.py::test_direct_debit_run (Umgehungstests AM01).
- Änderungsgrund: Lückenanalyse GAJ, Befund GAJ-301 (Umgehung von G2 über die allgemeinen Dokumentrouten).

## Ergänzung Welle 24 (AN08, Rest AM01)

- Ablage: Die Zahlungsdatei (pain.001) eines Zahlungsstapels wird bei der Erzeugung direkt in der Kategorie `payment_file` abgelegt (wie bisher die Lastschriftdatei pain.008); "Fehlende Standardkategorien ergänzen" ist dafür nicht mehr nötig.
- Mandantenvollexport (Betriebsexport, `platform/export_job`): Bei geschlossenem G2 enthält das Archiv keinen Inhalt von Zahlungsdateien. Die Metadatenzeile in `data/documents.jsonl` bleibt erhalten; das Manifest führt jede zurückgehaltene Datei unter `documents.withheld` mit Grund `payment_file_g2_closed` und Hinweis. Bei offenem G2 wird der Inhalt exportiert. Ein Fehler bei der Gateprüfung gilt als geschlossen.
- Objektakte-Export: Mit dem Objekt verknüpfte Zahlungsdateien werden bei geschlossenem G2 nicht in das ZIP aufgenommen; das Übergabeprotokoll nennt sie unter "Hinweise", die Zählung `documents_withheld` weist sie aus. Regulär sind Zahlungsdateien nur mit der Gesellschaft verknüpft, nicht mit dem Objekt.
- Offene Entscheidung: Ob der Mandantenvollexport (Admin-Funktion, Datenportabilität) bei geschlossenem G2 den Inhalt enthalten soll, entscheidet der Betreiber; technisch gilt der konservative Stand (zurückgehalten).
- Abnahmefall: tests/integration/test_an08_payment_file_exports.py (Gate zu und offen, Fehler im Resolver).
