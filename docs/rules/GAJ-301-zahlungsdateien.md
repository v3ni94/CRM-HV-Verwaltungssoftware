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

## Ergänzung Welle 25 (AO06, Review AN14-04 und AN14-12)

- Anhangswege beim Speichern: Wer eine Zahlungsdatei als Anhang einträgt, erhält 422 ("Zahlungsdateien können nicht als Anhang verwendet werden"). Das gilt für Entwurfsanhänge aus dem DMS (`POST /messages/{id}/attachments`), Ticketmails und Antwortvorlagen mit Standardanhängen (`tickets/routers.py`), Portalaushänge (`portal/notice_routers.py`) und die Übergabe an das Schadenstool (`integrations/schadenstool`). Prüfung zentral über `payment_files.ensure_no_payment_attachment`.
- Anhangswege in Hintergrundjobs: Weiterleitung mit Anhängen (`communication/forwarding_dispatch.py`) und Verteilung an Fremdsysteme (`documents/distribution.py`) übernehmen Zahlungsdateien nur bei offenem G2 (`payment_files.releasable_ids`, Fehler gilt als geschlossen). Bei der Weiterleitung zählt eine zurückgehaltene Zahlungsdatei als fehlender Anhang; das Original wird dann nicht archiviert.
- Versand: Der Mailversand prüft weiterhin G2 je Anhang (AN14-01).
- Serienversand und Rechnungskopie hängen nur das jeweils erzeugte Schreiben an; sie sind im Wächtertest als geprüft vermerkt.
- Wächtertest: `tests/unit/test_ao06_attachment_payment_guard.py` listet jedes Modul mit `attachment_document_ids`; ein neues Modul muss die Sperre aufrufen oder mit Begründung eingetragen werden.
- WhatsApp an Kontakte (AN14-12, Produktschutz Einwilligung 0.1.13): Bei Empfängerart `contact` wird die Nummer aus den Telefonnummern des Kontakts genommen (Mobil vor Hauptnummer). Eine übergebene Nummer muss zu einer Nummer des Kontakts passen (Leerzeichen und Trennzeichen werden ignoriert), sonst 422. Die Einwilligungsprüfung bleibt vorgelagert.
- Abnahmefall: tests/integration/test_ao06_attachment_paths.py, tests/unit/test_cov_sla_whatsapp.py (AN14-12).
