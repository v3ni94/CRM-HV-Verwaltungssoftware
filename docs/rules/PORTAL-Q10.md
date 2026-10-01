# PORTAL-Q10 Portalsichtbarkeit Tickets und Belegsuche

- ID: PORTAL-Q10
- Geltungsbereich: Portal (Mieter, Eigentümer, Dienstleister), Ticketkommentare und Anhänge, Belegliste.
- Quellenstatus: Fachliche Umsetzung (Abschnitt 6.6 Ticket, 7.9.2 PÜ12), keine Rechtsgrundlage aus Anhang C.
- Regel: external_comments none zeigt keine Kommentare und lehnt Portalkommentare mit 403 ab, to_manager zeigt nur eigene Kommentare, open alle nicht internen. external_attachments none blendet Anhänge aus, initiator_only zeigt nur eigene Portal-Uploads, open alle. Belegsuche, Sortierung und ZIP-Sammeldownload wirken nur innerhalb der sichtbaren Dokumente (gleiche Prüfung wie Einzelabruf).
- Abnahmefall: tests/unit/test_q10_portal_w3.py (Suche, Sortierung, Standard open).
- Änderungsgrund: Lückenliste 30.09.2026, M19-03, M25-06, S16-10.

## Ergänzung Welle 3 (Fortsetzung)

- M24-03: Einzelabrechnung im Eigentümerportal nur bei Status issued, due, posted oder locked, nur für eigene Einheiten, Freigabestufe G4 offen. Andere Fälle 404 ohne Hinweis. Quellenstatus: Fachliche Umsetzung (7.8 W12).
- M22-01: XML-E-Rechnung im Dienstleisterportal wird mit `mhvp.receipts.einvoice` gelesen, Werte nur als Vorschlag, IBAN wird nicht ausgegeben, keine Buchung. Nicht lesbare Dateien 422.
- M21-06 und SA-05: `own_share` nur aus dem berechneten Snapshot, nie neu gerechnet; Mieterträge nur bei aktivierter Sondereigentumsverwaltung, ohne Mietername und Zahlungsstatus.
- M25-04: Kontext einer Prüfposition lesend, ohne IBAN, nur Datensätze der Position.
- Abnahmefälle: tests/integration/test_q10_portal_w3.py, test_m21_portal.py (E-Rechnung), test_m21_board_portal.py (Kontext).
