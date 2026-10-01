# M2-02 Objektzuordnung je Mitgliedschaft

| Field | Content |
| --- | --- |
| ID | `M2-02` |
| Title | Optionale Objektzuordnung (`membership.property_ids`): ein Mitglied mit Zuordnung sieht nur die zugeordneten Objekte |
| Scope | Alle Mandanten. Leere Liste bedeutet keine Einschränkung (bisheriges Verhalten). Nicht leere Liste schränkt alle Rollen ein, außer wenn eine Rolle `tenant_admin` oder `administrator` ist (`PROPERTY_UNSCOPED_ROLES`). Nicht wirksam für API-Schlüssel, Plattformadministratoren nach protokolliertem Mandantenwechsel und Worker ohne Anfrageprinzipal |
| Source status | Abschnitt 3.4 (optional Objektzuordnung, Objektverwalter sieht nur zugeordnete Objekte); Produktschutz, kein Rechtssatz aus Anhang C |
| Acceptance case | Kein Fall aus Anhang D; Unit `apps/api/tests/unit/test_p14_auth_security.py`; Integration `apps/api/tests/integration/test_p14_member_scope_webauthn.py` und `apps/api/tests/integration/test_q13_property_scope_etag.py`, `apps/api/tests/integration/test_r08_property_scope_domains.py`; Komponente `apps/web-crm/src/components/settings/MembersPropertiesEditor.test.tsx` |
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
- Stand 01.10.2026 (Paket R08, Rest Q13-01): die Zuordnung wirkt zusätzlich in diesen Bereichen.
  - Banking: ein Bankkonto ist sichtbar, wenn sein Objekt oder eine seiner Objektzuordnungen
    (`bank_account_assignment`) zugeordnet ist. `GET /banking/accounts`, `GET
    /banking/transactions` und `GET /banking/payment-orders` sind gefiltert; jeder Bankpfad mit
    Umsatz, Konto, Zahlungsauftrag oder Sammler antwortet außerhalb 404
    (`mhvp.banking.property_scope.banking_path_guard`).
  - Abrechnungen: Betriebskostenabrechnungen (`/statements/{statement_id}` mit allen
    Unterroutern), Eigentümerabrechnungen und Verbrauchsinformationen über
    `property_column_guard`; die Listen sind gefiltert. WEG: Datensätze mit
    Abrechnung, Wirtschaftsplan, Versammlung, Beschluss, Sonderumlage, Darlehen, Maßnahme,
    Versicherungsfall, Prüfauftrag, Vermögensbericht und Einsichtsanfrage im Pfad sowie die
    Listen mit `legal_entity_id` oder `ledger_id` antworten außerhalb 404
    (`mhvp.hoa.property_scope`).
  - Berichte: alle Auswertungen `/accounting/ledgers/{ledger_id}/reports/...` nach dem Objekt
    des Buchungskreises.
  - Unterrouter mit `{property_id}`: Übernahme, Stammdaten, Kreditoren, Teiländerung,
    Bankkonten und Dienstleister (P16), Verwaltungsende, Aushänge, Verbrauchsinformation,
    Umsatzsteuerprofil. Dienstleisterverträge (Liste, Einzelabruf, Anlage auf fremdem Objekt
    wie unbekanntes Objekt 422), Kautionsabrechnungen über den Vertrag der Kaution.
  - Globale Suche (`GET /workspace/search`): Objekte, Einheiten, Gebäude, Zähler, Verträge,
    Dokumente, Tickets, Buchungen und Rechnungen nach Zuordnung. Kontakte bleiben
    mandantenweit.
  - KI-Nachschlagewerkzeuge (`mhvp.ai.lookup`, `mhvp.ai.lookup_tools`): Objekte, Einheiten,
    Verträge, Tickets, Dokumente, Fristen, generierte Kalendereinträge, WEG-Gemeinschaften,
    Mieterhöhungen, Aufträge, Bankumsätze und offene Posten nach Zuordnung; ein geöffneter
    Datensatz außerhalb wird wie nicht vorhanden behandelt.
  - Nicht angeschlossen: Portalverwaltung (Zugänge und Vorschläge sind kontaktbezogen),
    Objektakte, Importe, Kataloge (mandantenweit ohne Objektbezug), Prüfberichte des Beirats
    (`audit_report` ohne Rechtsträger; der Prüfauftrag selbst ist geschützt).
