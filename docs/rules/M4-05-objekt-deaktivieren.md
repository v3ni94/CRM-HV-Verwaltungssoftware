# M4-05 Objekt deaktivieren bei Beendigung des Verwaltungsverhältnisses

| Field | Content |
| --- | --- |
| ID | `M4-05` |
| Title | Objekte werden bei Beendigung des Verwaltungsverhältnisses deaktiviert (Status `terminated`), bleiben mit allen Daten erhalten, verschwinden aus der Objektliste und können nur durch den Superadmin wieder aktiviert werden |
| Scope | `POST /properties/{id}/terminate` (`properties:update`, Objekt in Status onboarding oder active), `POST /properties/{id}/reactivate` (nur `principal.is_superadmin`, ADR 0011, sonst 403 `MHVP-PROP-0003`), `GET /properties/{id}/termination` (`properties:read`), `GET /properties` (`include_terminated`, nur für den Superadmin wirksam, für alle anderen ohne Wirkung; ein Statusfilter `terminated` liefert Nichtberechtigten eine leere Liste), Tabelle `property_termination` (RLS), alle Mandanten, kein Geldfluss |
| Source status | Fachliche Umsetzung (Betreiberwunsch 27.09.2026). Produktschutz: Wieder aktivieren nur durch den Superadmin und Ausblenden in der Liste sind interne Standards, keine Rechtsgrundlage. Aufbewahrungs- und Abrechnungspflichten nach Ende der Verwaltung werden hier nicht abgebildet (Abrechnungen und Belege bleiben unverändert erhalten) |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_property_termination.py` (Erfassung mit Nachfolgern und Kündigungsschreiben, Ausblenden in der Liste, zweite Beendigung 409, Datumsprüfung 422, Berechtigung 403, Mandantentrennung 404, Reaktivierung nur Superadmin, Änderungsprotokoll), Vitest `PropertyTermination.test.tsx`, `PropertyList.test.tsx` |
| Implementation | Migration 0157 (`property_termination`: `terminated_by` manager, owner, hoa, other; `notice_date`, `effective_date`, `previous_status`, `successor_manager_contact_id`, `successor_owner_contact_id`, `notice_document_id`, `note`, `reactivated_at`, `reactivated_by_user_id`; eine offene Beendigung je Objekt), `mhvp.properties.routers_termination`, `mhvp.properties.routers.list_properties`, Fehlercodes `MHVP-PROP-0001` bis `0004`, `GET /auth/me` gibt `is_superadmin` aus; Web `PropertyTermination`, `PropertyList` (StatusChip Deaktiviert, graue Zeile), `/objekte?deaktivierte=1` (Schalter nur für den Superadmin) |
| Change reason | Betreiberwunsch 27.09.2026: beendete Objekte sollen den Bestand nicht mehr belasten, aber mit Kündigungsdaten, Nachfolgern und Kündigungsschreiben nachvollziehbar bleiben |

## Regeln

- Beenden setzt `Property.status = terminated` und `managed_to` auf das Ende der Verwaltung;
  der vorherige Status wird in `previous_status` gesichert. Ereignis `property.terminated`
  mit Änderungsprotokoll (Status, Verwaltungsende).
- Das Ende der Verwaltung darf nicht vor dem Kündigungsdatum liegen (422 `MHVP-PROP-0004`).
  Nachfolger und Kündigungsschreiben müssen im Mandanten existieren (404).
- Ein deaktiviertes Objekt kann nicht erneut beendet werden (409 `MHVP-PROP-0001`); der
  bisherige Statuswechsel über `POST /properties/{id}/status` bleibt für die Datenübernahme
  erhalten, legt aber keinen Beendigungsdatensatz an.
- Wieder aktivieren schließt die Beendigung (`reactivated_at`, `reactivated_by_user_id`),
  stellt den vorherigen Status wieder her, leert `managed_to` und schreibt
  `property.reactivated`. Der Datensatz der Beendigung wird nie gelöscht; eine erneute
  Beendigung legt einen neuen Datensatz an.
- Keine Löschung, keine Sperre von Buchungen, Abrechnungen oder Dokumenten: die
  Deaktivierung ist ein Anzeige- und Bearbeitungsstatus des Bestands. Die Stammdaten der
  Detailseite sind bei deaktivierten Objekten schreibgeschützt.
