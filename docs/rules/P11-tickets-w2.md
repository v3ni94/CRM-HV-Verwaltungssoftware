# P11 Aufträge, Teams, Ticketfelder, Kommentararchiv, Dienstleisterportal und Paperless-Dokumente im Ticket

| Feld | Inhalt |
| --- | --- |
| ID | `P11` (Teilregeln M19-01 bis M19-07, M22-02 bis M22-07, Fehler Paperless Ticket #34) |
| Geltungsbereich | `mhvp.tickets` (order_routers, models, routers), `mhvp.portal` (Dienstleisterendpunkte), `mhvp.documents` (Paperless-Ticketliste) |
| Quellenstatus | Keine Rechtsnorm (Anhang C); Fachliche Umsetzung nach Spezifikation 6.6 und 14 sowie Produktschutz |
| Abnahmefall | Keiner in Anhang D; Tests `tests/integration/test_p11_tickets_w2.py`, `tests/integration/test_m21_portal.py`, `tests/unit/test_documents_paperless_search.py`, `tests/integration/test_m31_dms.py` |
| Änderungsgrund | Lückenliste 30.09.2026, Betreibermeldung 30.09.2026 (Reiter Dokumente im Ticket #34 zeigte fremde Dokumente) |

## Regeln

1. Paperless-Dokumente im Ticket zeigen nur Dokumente mit Bezug zum Ticket, zu seinem Kontakt
   oder zu seinem Objekt. Bezug zum Ticket heißt ausdrückliche Referenz ("Ticket 34",
   "Ticket #34", "Vorgang 34") in Titel, Dateiname oder Schlagwort. Die Volltextsuche nach der
   nackten Ticketnummer ist abgeschafft, weil sie jedes Dokument mit diesen Ziffern lieferte
   (Objektlisten, SEPA-Mandat). Bezug zum Kontakt heißt: Korrespondent entspricht exakt dem
   Anzeigenamen des Kontakts. Bezug zum Objekt: Objektnummer-Feld nach Hub-Regel 7.2. Ohne Bezug
   ist die Liste leer und die Oberfläche nennt den Grund (lieber leer als falsch zugeordnet).
2. Auftragsliste `GET /work-orders` (Filter Status, Dienstleister, Objekt, Ticket, Seiten) und
   Auftragsdetail `GET /work-orders/{id}` mit Verlauf und Terminvorschlägen; Recht `tickets:read`.
3. Teams: `GET/PATCH/DELETE /teams/{id}`, `GET /teams`; Ändern und Löschen brauchen
   `tickets:approve`. Ein Team mit Tickets oder Vorlagen wird nicht gelöscht (409).
4. Ticketfelder (Migration 0260): `building_id` (muss zum Objekt des Tickets gehören),
   `start_date`, `follow_up_date`, `external_comments` (none, to_manager, open),
   `external_attachments` (none, initiator_only, open). Die Sichtbarkeitsfelder sind gespeichert,
   die Durchsetzung im Portal ist offen (P11-02).
5. Kommentare werden archiviert statt gelöscht (`removed_at`, `removed_by`); der Text bleibt als
   Nachweis erhalten und erscheint nicht mehr in Ticketansicht und Portal. Ereignis
   `comment_removed` im Ticketverlauf.
6. Dienstleisterportal: Annahme eines Auftrags ohne Angebot (`POST /portal/work-orders/{id}/accept`)
   ist keine Freigabe und ändert den Status nicht; Ablehnung nimmt eine Begründung auf; jeder
   Portalschritt erzeugt das Ereignis `work_order.<status>` und einen Ticketverlaufseintrag;
   der Dienstleister sieht seine Rechnungseinreichungen mit Status und Entscheidungsnotiz und das
   Angebotsdokument; eine Rechnungsnummer wird je Dienstleister nicht doppelt eingereicht (409).
   Keine Buchung, keine Zahlung (Gates G1 und G2 bleiben geschlossen).
7. M19-05 (`approval_workflow_id`) wird nur dokumentiert: OPEN_QUESTIONS P11-01.
