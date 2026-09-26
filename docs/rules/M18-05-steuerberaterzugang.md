# M18-05 Steuerberaterzugang: Zugriffsbereich je Rechtsträger

| Field | Content |
| --- | --- |
| ID | `M18-05` |
| Title | Zugriffsbereich je Mitgliedschaft (`membership.legal_entity_ids`) für die Rolle Steuerberater: Buchungskreise, Auswertungen, Exporte und verknüpfte Dokumente nur für zugewiesene Rechtsträger |
| Scope | Alle Mandanten; Mitgliedschaften, deren Rollen ausschließlich Rollen mit eingeschränktem Bereich sind (`mhvp.core.auth.scope.SCOPED_ROLES`, derzeit nur `tax_advisor`). Wirksam in: Buchungskreisliste und Einzelabruf (`GET /accounting/ledgers`, `/ledgers/{id}` und alle Unterpfade wie Journal, Saldenliste, offene Posten, Kontenblatt, Liquidität, Zahlungen je Debitor, Erträge), Journal- und DATEV-Export, DATEV-Kontenzuordnung (M18-04, gleiche Hilfsfunktion), Prüfexport (Erstellen, Liste, Status, Download), Dokumente mit Verknüpfung `legal_entity`. Nicht wirksam für: Mitgliedschaften mit mindestens einer anderen Rolle, API-Schlüssel, Plattformadministratoren nach protokolliertem Mandantenwechsel, Worker- und Seed-Sitzungen ohne Anfrageprinzipal |
| Source status | Produktschutz (0.2): kein Rechtssatz aus Anhang C, sondern Datenminimierung und Vertraulichkeit gegenüber Dritten (Steuerberater einer Gemeinschaft darf nicht die Buchhaltung anderer Gemeinschaften einsehen). Betreiberentscheidung zu M18-02 (docs/OPEN_QUESTIONS.md) am 26.09.2026 über die Lückenliste A37 |
| Acceptance case | D55 (Steuerberater-/Prüfexport) im Zusammenhang; Integration `apps/api/tests/integration/test_m18_tax_advisor_scope.py` (Liste, Journal, Salden, offene Posten, Exporte, Prüfexport, Dokumente, leerer Bereich, unbeschränkte Rollen, Rechte, Mandantentrennung); Komponententest `apps/web-crm/src/components/settings/MembersAdmin.test.tsx` (Auswahl der Rechtsträger) |
| Implementation | `mhvp.core.auth.scope` (`allowed_legal_entity_ids`, `ensure_legal_entity_allowed`, `ensure_session_legal_entity_allowed`, `session_allowed_legal_entity_ids`, Abhängigkeit `legal_entity_scope`), `Principal.legal_entity_ids` und Anfrageprinzipal auf `AsyncSession.info["mhvp.principal"]` (`tenant_tx`), `Membership.legal_entity_ids` (Migration `0102_membership_legal_entity_ids`), Filter in `mhvp.accounting.routers._ledger` und `list_ledgers`, Hook `mhvp.accounting.reports.ensure_ledger_in_scope`, `mhvp.accounting.audit_export_routers`, `mhvp.documents.routers._scope_filter`, Pflege `PUT /tenant/members/{id}/legal-entities` (`tenant_settings:update`) und `GET /tenant/legal-entities` (`members:read`), CRM Einstellungen, Benutzer (`MembersAdmin`, Auswahl nur bei Steuerberater-Mitgliedschaften) |
| Change reason | Lückenliste 26.09.2026 Aufgabe A37 (M18-02: Beschränkung auf einzelne Rechtsträger mit der Rollenmatrix nicht möglich), umgesetzt 26.09.2026 |

## Regeln

- Die Rollenmatrix (3.4) gilt weiterhin je Mandant. Der Zugriffsbereich ist eine zweite Achse
  daneben: er begrenzt, welche Rechtsträger eine Mitgliedschaft mit eingeschränkter Rolle
  sehen darf. Er ersetzt weder die Mandantentrennung (RLS) noch die Berechtigungsprüfung.
- Wirksam ist der Bereich nur, wenn alle Rollen der Mitgliedschaft Rollen mit
  eingeschränktem Bereich sind (derzeit nur Steuerberater). Sobald eine andere Rolle
  hinzukommt (Administrator, Standard, Buchhalter, eigene Rolle), gilt der volle
  Mandantenumfang und die Liste ist ohne Wirkung. Die Liste wird trotzdem gespeichert und
  wieder wirksam, wenn die anderen Rollen entfernt werden.
- Leerer Bereich bei einer Steuerberater-Mitgliedschaft bedeutet keinen Zugriff auf
  Buchhaltungsdaten: Listen sind leer, Einzelabrufe antworten 404. Ein Steuerberater ohne
  Zuweisung ist damit kein Sicherheitsrisiko, sondern nur nicht arbeitsfähig; der
  Administrator weist die Rechtsträger unter Einstellungen, Benutzer zu.
- Fremde Rechtsträger werden nie als "verboten" (403) gemeldet, sondern wie nicht vorhanden
  (404) behandelt oder aus Listen gefiltert, damit ihre Existenz nicht offengelegt wird.
- Pflege nur mit `tenant_settings:update` (Mandantenadministrator). Unbekannte oder fremde
  Rechtsträger werden abgewiesen (422); die Mitgliedschaft eines anderen Mandanten ist nicht
  erreichbar (404). Jede Änderung erzeugt das Ereignis `membership.legal_entities_changed`
  mit alter und neuer Liste.
- Dokumente: Für beschränkte Mitgliedschaften existieren nur Dokumente mit einer
  Verknüpfung `legal_entity` auf einen zugewiesenen Rechtsträger (Liste, Lesen, Herunterladen
  und alle weiteren Zugriffe über die zentrale Ladehilfe). Die Rolle Steuerberater hat
  standardmäßig kein Dokumentenrecht; der Filter greift, sobald ein Administrator der Rolle
  `documents:read` einräumt.
- Worker und Seeds arbeiten ohne Anfrageprinzipal und sind nicht beschränkt; sie erhalten
  ihre Aufträge nur aus bereits geprüften Anfragen (z. B. Prüfexport-Lauf, dessen Erstellung
  bereits geprüft wurde).
- Offen (docs/OPEN_QUESTIONS.md M18-02): ob weitere Rollen (z. B. Beirat, externe Prüfer)
  einen Zugriffsbereich erhalten sollen; die Menge `SCOPED_ROLES` ist dafür der einzige
  Erweiterungspunkt.
