# M2-02 Objektzuordnung je Mitgliedschaft

| Field | Content |
| --- | --- |
| ID | `M2-02` |
| Title | Optionale Objektzuordnung (`membership.property_ids`): ein Mitglied mit Zuordnung sieht nur die zugeordneten Objekte |
| Scope | Alle Mandanten. Leere Liste bedeutet keine Einschränkung (bisheriges Verhalten). Nicht leere Liste schränkt alle Rollen ein, außer wenn eine Rolle `tenant_admin` oder `administrator` ist (`PROPERTY_UNSCOPED_ROLES`). Nicht wirksam für API-Schlüssel, Plattformadministratoren nach protokolliertem Mandantenwechsel und Worker ohne Anfrageprinzipal |
| Source status | Abschnitt 3.4 (optional Objektzuordnung, Objektverwalter sieht nur zugeordnete Objekte); Produktschutz, kein Rechtssatz aus Anhang C |
| Acceptance case | Kein Fall aus Anhang D; Unit `apps/api/tests/unit/test_p14_auth_security.py`; Integration `apps/api/tests/integration/test_p14_member_scope_webauthn.py` und `apps/api/tests/integration/test_q13_property_scope_etag.py`; Komponente `apps/web-crm/src/components/settings/MembersPropertiesEditor.test.tsx` |
| Implementation | `Membership.property_ids` (Migration 0263), `Principal.property_ids`, `mhvp.core.auth.scope` (`allowed_property_ids`, `property_allowed`, `ensure_property_allowed`, `session_allowed_property_ids`, `ensure_session_property_allowed`), Pflege `PUT /tenant/members/{id}/properties` (`tenant_settings:update`), Anzeige in `GET /tenant/members`, CRM Einstellungen, Benutzer (`PropertiesEditor`) |
| Change reason | Lückenliste 30.09.2026 Befunde M2-02 und S16-02 |

## Regeln

- Die Objektzuordnung ist eine weitere Achse neben Mandantentrennung (RLS), Rollenmatrix und
  Zugriffsbereich je Rechtsträger (M18-05); sie ersetzt keine davon.
- Fremde Objekte antworten 404, Listen werden gefiltert. Datensätze ohne Objektbezug sind für
  eingeschränkte Mitglieder nicht sichtbar.
- Stand 30.09.2026 (Paket P14): Speicherung, Pflege, Anfrageprinzipal und Prüffunktionen.
- Stand 30.09.2026 (Paket Q13, schließt P14-01 für die genannten Pfade): die Zuordnung wirkt in
  den Fachdomänen.
  - Objekte: `GET /properties` gefiltert; jeder Pfad mit `{property_id}` im Objekt- und im
    Vertragsrouter antwortet außerhalb der Zuordnung 404 (Router-Abhängigkeit
    `property_path_guard`); Einzelabfragen von Gebäuden, Einheiten, Zählern und weiteren
    Objektdatensätzen prüfen das Objekt des Datensatzes.
  - Verträge: `GET /contracts` gefiltert, `GET /contracts/{id}` und alle Vertragspfade, die den
    Vertrag laden, antworten 404.
  - Tickets: `GET /tickets` gefiltert, `GET` und `PATCH /tickets/{id}` 404; ein Ticket kann
    nicht auf ein nicht zugeordnetes Objekt umgehängt werden. Tickets ohne Objekt sind für
    eingeschränkte Mitglieder nicht sichtbar.
  - Dokumente: sichtbar sind Dokumente, die mit einem zugeordneten Objekt oder mit einer
    Einheit, einem Vertrag oder einem Ticket eines zugeordneten Objekts verknüpft sind
    (Liste, Einzelabfrage, Änderung).
  - Rechnungen: Objekt ist das Objekt des Buchungskreises (`ledger.property_id`); Liste,
    Einzelabfrage und alle Rechnungsaktionen über `_invoice` antworten außerhalb 404.
    Buchungskreise ohne Objekt (Verwaltungsgesellschaft) sind für eingeschränkte Mitglieder
    nicht sichtbar.
  - Nicht angeschlossen: weitere Listen außerhalb der fünf Domänen (Banking, Abrechnungen,
    Zähler als eigene Liste, Berichte, Suche). Sie bleiben offen unter P14-01.
