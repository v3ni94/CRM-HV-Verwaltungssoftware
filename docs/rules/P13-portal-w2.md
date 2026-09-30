# P13 Portal Welle 2: Chat am Ticket, Vertreter, Support-Sicht, Eigentümeransicht, Formularbaukasten

| Field | Content |
| --- | --- |
| ID | `P13` (Lückenliste 30.09.2026: M21-01 bis M21-03, M21-05 bis M21-08, SA-01 bis SA-03, SA-05, SA-06) |
| Title | Portal erhält einen Nachrichtenkanal am Ticket, Vertreterrolle mit Vollmacht, lesende Support-Sicht mit Einwilligung, erweiterte Eigentümeransicht, Status neu/gelesen, Standort der Schadensmeldung, Funktionsschalter mit Statistik und einen Formularbaukasten mit 14 Elementtypen |
| Scope | Alle Mandanten, Portalrollen Mieter, Eigentümer, Vertreter; Module `mhvp.portal.chat`, `features`, `management`, `owner_extra`, `forms`, `access`; Tabellen `portal_feature_setting`, `portal_representation`, `portal_support_consent`, `portal_support_access` und Spalten `portal_form_template.delivery`, `delivery_email` (Migration 0262, RLS nach ADR 0002) |
| Source status | Produktschutz (0.2), abgeleitet aus Abschnitt 14 und A.5 (Eigentümeransicht, Verwalteransicht, Formularbaukasten). Keine Rechtsgrundlage aus Anhang C; keine Aussage über die Wirksamkeit einer Vollmacht, über Zugang oder Zustellung |
| Acceptance case | Kein Anhang-D-Fall. Tests `apps/api/tests/integration/test_p13_portal.py`, `apps/api/tests/unit/test_p13_portal_forms.py`, `apps/web-portal/src/components/portal/P13.test.tsx`, `PortalForms.test.tsx`, `apps/web-crm/src/components/settings/PortalManagement.test.tsx` |
| Change reason | Lückenliste 30.09.2026, Entscheidung 6 a (Chat als Nachrichtenkanal am Ticket, KI-Vorqualifizierung nur hinter AVV-Schalter) und 7 a (Vertreterrolle mit Vollmachtsdokument und Zeitraum, Support-Login nur lesend, protokolliert, nur mit Einwilligung) |

## Regeln

1. **Chat (M21-01).** Eine Chatnachricht ist ein externer (nicht interner) `TicketComment` der
   eigenen Meldung; Verlauf, CRM-Sicht und Aufbewahrung bleiben im Ticket. Das Portal liest nur
   externe Kommentare. Nachricht des Nutzers benachrichtigt den Bearbeiter, Antwort der
   Verwaltung (`POST /portal-admin/tickets/{id}/messages`, `tickets:update`) benachrichtigt den
   Portalnutzer. Ohne Schalter `chat_enabled` (Standard aus) antworten alle Chatendpunkte 403.
   Der Chat ist kein Notdienst, der Hinweis wird im Portal immer angezeigt.
2. **Vorqualifizierung (M21-01).** `POST /portal/tickets/{id}/prequalify` liefert einen Vorschlag
   (Themen, Dringlichkeitshinweis), nie eine Entscheidung und keine Änderung am Ticket. Die
   regelbasierte Stufe braucht keinen Anbieter. Die KI-Stufe gilt nur bei eingeschaltetem
   `chat_ai_prequalification_enabled` und wenn das Gateway einen freigegebenen Anbieter mit
   AVV-Nachweis und Opt-out liefert; dieses Paket ruft keinen Anbieter auf (siehe Offene Punkte).
3. **Vertreter (M21-05).** `POST /portal-admin/representations` (`tenant_settings:update`) legt
   eine Vollmacht an: Portalzugang des Vertreters, vertretener Kontakt, Vollmachtsdokument
   (Pflicht), Beginn, optional Ende. Der Vertreter erhält lesende Rechte (`read`, `download`,
   Grant `legal_basis = representation`, Rolle `owner`) auf die Eigentumsverträge des
   Vertretenen, begrenzt auf den Zeitraum. Widerruf (`.../revoke`) beendet den Zugriff sofort.
   Das System prüft nicht die Wirksamkeit der Vollmacht; Anlegen und Widerruf sind Erklärungen
   mit Rechtswirkung und liegen bei der Geschäftsführung.
4. **Support-Sicht (SA-02).** Kein Login als Nutzer. `GET /portal-admin/accounts/{id}/support-view`
   liefert einen festen lesenden Auszug (Rollen, Verträge, Meldungen, Dokumenttitel), nur wenn der
   Mandantenschalter `support_login_enabled` an ist und eine gültige, widerrufbare Einwilligung
   des Nutzers (1 bis 72 Stunden) vorliegt. Jeder Aufruf schreibt Protokoll (`portal_support_access`:
   Mitarbeiter, Grund, Einwilligung, Bereiche) und Ereignis; das Protokoll wird nicht geändert.
5. **Eigentümeransicht (M21-06, M21-07, SA-05).** Lesend: Meldungen zu den eigenen Objekten,
   die für Eigentümer freigegeben sind (`visible_for` enthält `owner`); bekanntgegebene Beschlüsse
   zu Wirtschaftsplan oder Sonderumlage mit Geltungsdauer, Rhythmus, Raten und dem Standardkonto der
   Gemeinschaft als Zahlungsempfänger; Verbrauchsinformation für selbst genutzte Einheiten
   (Vertrag des Eigentümers, gleiche Sperre wie Regel H03, Mietermonate bleiben verborgen).
   Keine Zahlung, kein Anspruch; die individuelle Sollstellung steht im Hausgeldkonto.
6. **Status neu/gelesen (M21-02, SA-06).** `GET /portal/documents` liefert `is_new`,
   `first_opened_at`, `last_opened_at` und `context` (Dokumentkategorie) aus den eigenen
   Lesebestätigungen. Indiz, keine Zustellung (`read_receipts.LEGAL_NOTE`); Listen schreibt nichts.
7. **Standort (M21-03).** `location` (Freitext, höchstens 200 Zeichen) wird der öffentlichen
   Beschreibung der Meldung als Zeile "Standort" vorangestellt. Keine Geokoordinaten (Datenminimierung).
8. **Funktionsschalter und Statistik (M21-08, SA-01).** `GET/PATCH /portal-admin/features`
   (Schreiben `tenant_settings:update`), alle Schalter standardmäßig aus; Abschalten des Chats
   schaltet die KI-Stufe ab. `GET /portal-admin/statistics` zählt Zugänge je Status, aktive Nutzer
   (Anmeldung in 30 Tagen), Dokumentabrufe, Formulareinreichungen und Portalmeldungen, ohne
   personenbezogene Angaben.
9. **Formularbaukasten (SA-03).** 14 Elementtypen: text, textarea, number, date, time, select,
   radio, multiselect, checkbox, email, phone, file, heading, info (die beiden letzten ohne Wert).
   Zustellung `ticket` (Standard) oder `email` mit Adresse der Verwaltung; das Ticket entsteht
   immer als Nachweis, bei `email` wird zusätzlich gesendet, ein Fehlschlag wird dem Nutzer nur als
   `delivery_failed` gemeldet. Freigabe je Rolle über die bestehende Zielgruppe (tenant, owner, all).

## Offene Punkte

* KI-Aufruf der Vorqualifizierung (Maskierung, Anbieteraufruf, Protokoll) ist nicht umgesetzt.
* Mieterträge je Objekt und Umlageeigenschaften (A.5) sowie der eigene Anteil an Sonderumlage
  und Wirtschaftsplan fehlen; siehe docs/OPEN_QUESTIONS.md (P13-01).
* Ein Rollenwechsel im Portal für Konten mit mehreren Rollen und die Pflege der Vollmacht im CRM
  (Oberfläche) sind offen; die API ist vollständig.
