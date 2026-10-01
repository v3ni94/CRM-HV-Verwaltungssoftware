# M25-W3 Benachrichtigung, Eigentümerprüfung und Prüfrolle ohne Buchungsrecht (Lückenliste 30.09.2026, Paket Q09)

Status: umgesetzt am 30.09.2026. Es wird nichts versendet und nichts widerrufen, ohne dass die
Verwaltung es auslöst.

| Feld | Inhalt |
| --- | --- |
| ID | M25-W3 (Befunde M25-05 Rest und M25-07 Rest der Lückenliste 30.09.2026, Regel PÜ08 und PÜ13) |
| Titel | Die Prüfrolle bucht nicht und ändert die geprüften Daten nicht; die Bereitstellung an den Antragsteller wird als eigenes Ereignis protokolliert; bei Eigentümerwechsel wird die Stellung des Antragstellers geprüft |
| Geltung | WEG-Modul (M25): Beiratszugang zum Prüfauftrag (Rolle `board`, Recht `comment`), Einsichtsanfragen außerhalb des Portals |
| Quellenstatus | Produktschutz (stricterer interner Standard, keine gesetzliche Pflicht). Einsichtsrechte und der Umgang mit historischen Ansprüchen nach einem Eigentümerwechsel sind eine Rechtsfrage (Einschätzung, Rechtsanwalt), siehe P08-02. Die Frist der Bereitstellung ist eine Produktvorgabe, keine Rechtsfrist |
| Abnahmefall | Anhang D SD-07 (Protokoll ohne Rechtsfiktion). Erwartete Werte von Hand: Antragsteller ist Eigentümer ab 01.01.2020, Antrag vom 01.06.2019: am Antragstag kein Eigentümer, heute Eigentümer, Änderung erkannt, bei abrufbarem Paket Hinweis auf Prüfung des Widerrufs; Antrag vom 01.06.2021: unverändert. Tests `tests/unit/test_m25_05_audit_role_no_booking.py`, `tests/integration/test_p08_hoa_audit_inspection.py` (Ereignisfolge mit `notified`, Eigentümerprüfung, Leserecht 403, anderer Mandant 404) |
| Umsetzung | (1) Die Prüfrolle ist ein Portalzugang (`AccessGrant` mit Recht `comment`), keine CRM-Rolle. Systemrollen für Portalnutzer tragen keine Berechtigung; die Prüfrolle erhält kein Buchungs-, Freigabe- oder Änderungsrecht. Die Regel ist durch Einheitstests auf die Rollentabelle und den Quelltext des Zugangs sowie den bestehenden Integrationstest der Sperrliste (`test_m21_board_portal.py`) belegt. (2) Nach dem Übergang der Anfrage auf `provided` schreibt die Anwendung das Ereignis `notified` (Empfänger, Zustellart, Ablauf) und das Systemereignis `hoa_inspection.notified`; die Nachricht selbst entsteht als Entwurf im Kommunikationsmodul, versendet wird nicht. (3) `POST /hoa/inspection-requests/{id}/owner-check` vergleicht die Eigentümerstellung des Antragstellers am Antragstag mit heute und protokolliert das Ergebnis als Ereignis `owner_check`. Eine Änderung wird angezeigt, der Widerruf bleibt eine Entscheidung der Verwaltung (Freigabe durch die Geschäftsführung bei haftungsrelevanten Erklärungen) |
| Änderungsgrund | Lückenliste 30.09.2026, Befunde M25-05 und M25-07: die Sperre der Prüfrolle war nur indirekt belegt, Benachrichtigung und Eigentümerwechsel fehlten |
