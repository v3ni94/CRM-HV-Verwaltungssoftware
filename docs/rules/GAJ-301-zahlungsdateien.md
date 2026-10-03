# GAJ-301 Zahlungsdateien nur mit Freigabe G2

- ID: GAJ-301
- Geltungsbereich: Lastschriftdateien (pain.008) und Zahlungsdateien (pain.001), die als Dokument abgelegt sind; allgemeine Dokumentrouten, Portal (Einzeldownload und Sammel-Download), DMS-Spiegelung, Ereignis-Payload.
- Anforderungstyp: Produktschutz (18.0 G2, 7.5 SEPA). Keine Rechtsgrundlage behauptet.
- Quellenstatus Anhang C: nicht einschlägig (Freigabesperre der Plattform).
- Regel: Ein Dokument gilt als Zahlungsdatei, wenn es in der Kategorie `payment_file` liegt oder ein Lastschriftlauf oder Zahlungsstapel darauf verweist. Inhalt und signierte Download-URL gibt es nur bei offenem G2 (sonst 403 MHVP-GATE-0001). Das Portal gibt Zahlungsdateien nie aus (404). Zahlungsdateien werden nicht in Paperless oder Google Drive gespiegelt. Ereignisse zur Lastschriftdatei enthalten keine Dokument-Id. Metadaten bleiben mit Leserecht lesbar.
- Nachkategorisierung: "Fehlende Standardkategorien ergänzen" ordnet bestehende Zahlungsdateien der Kategorie zu; die Sperre hängt nicht davon ab (Verweisprüfung).
- Abnahmefall: tests/integration/test_m15_direct_debits.py::test_direct_debit_run (Umgehungstests AM01).
- Änderungsgrund: Lückenanalyse GAJ, Befund GAJ-301 (Umgehung von G2 über die allgemeinen Dokumentrouten).
