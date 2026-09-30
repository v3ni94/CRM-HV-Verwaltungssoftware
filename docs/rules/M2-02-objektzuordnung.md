# M2-02 Objektzuordnung je Mitgliedschaft

| Field | Content |
| --- | --- |
| ID | `M2-02` |
| Title | Optionale Objektzuordnung (`membership.property_ids`): ein Mitglied mit Zuordnung sieht nur die zugeordneten Objekte |
| Scope | Alle Mandanten. Leere Liste bedeutet keine Einschränkung (bisheriges Verhalten). Nicht leere Liste schränkt alle Rollen ein, außer wenn eine Rolle `tenant_admin` oder `administrator` ist (`PROPERTY_UNSCOPED_ROLES`). Nicht wirksam für API-Schlüssel, Plattformadministratoren nach protokolliertem Mandantenwechsel und Worker ohne Anfrageprinzipal |
| Source status | Abschnitt 3.4 (optional Objektzuordnung, Objektverwalter sieht nur zugeordnete Objekte); Produktschutz, kein Rechtssatz aus Anhang C |
| Acceptance case | Kein Fall aus Anhang D; Unit `apps/api/tests/unit/test_p14_auth_security.py`; Integration `apps/api/tests/integration/test_p14_member_scope_webauthn.py`; Komponente `apps/web-crm/src/components/settings/MembersPropertiesEditor.test.tsx` |
| Implementation | `Membership.property_ids` (Migration 0263), `Principal.property_ids`, `mhvp.core.auth.scope` (`allowed_property_ids`, `property_allowed`, `ensure_property_allowed`, `session_allowed_property_ids`, `ensure_session_property_allowed`), Pflege `PUT /tenant/members/{id}/properties` (`tenant_settings:update`), Anzeige in `GET /tenant/members`, CRM Einstellungen, Benutzer (`PropertiesEditor`) |
| Change reason | Lückenliste 30.09.2026 Befunde M2-02 und S16-02 |

## Regeln

- Die Objektzuordnung ist eine weitere Achse neben Mandantentrennung (RLS), Rollenmatrix und
  Zugriffsbereich je Rechtsträger (M18-05); sie ersetzt keine davon.
- Fremde Objekte antworten 404, Listen werden gefiltert. Datensätze ohne Objektbezug sind für
  eingeschränkte Mitglieder nicht sichtbar.
- Stand 30.09.2026: Speicherung, Pflege, Anfrageprinzipal und Prüffunktionen sind umgesetzt.
  Die Filterung in den Fachdomänen (Objekte, Einheiten, Verträge, Tickets, Dokumente) ist noch
  nicht angeschlossen (docs/OPEN_QUESTIONS.md P14-01). Bis dahin wirkt die Zuordnung nicht auf
  Listen und Detailabfragen.
