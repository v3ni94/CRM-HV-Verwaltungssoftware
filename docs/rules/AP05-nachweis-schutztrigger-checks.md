# AP05: Schutztrigger, Urheberspalten und CHECKs (GAL-104 bis GAL-107)

- ID: AP05-nachweis-schutztrigger-checks
- Geltungsbereich: Mandantentabellen der Bereiche accounting, banking, billing, hoa, imports, portal, platform
- Quellenstatus: Produktschutz (Abschnitt 6 Notation, 6.9.3 E03, 6.9.4 E04, 6.9.6, 6.9.9, 7.1 B03 und B07); keine neue Rechtsregel
- Abnahmefall: Anhang D nicht unmittelbar; Nachweis durch `apps/api/tests/integration/test_ap05_evidence_guards.py`
- Änderungsgrund: Schutz gebuchter und beweiserheblicher Daten hing bisher allein an der Anwendung
- Migration: `0462_ap05_evidence_guards.py`

## Regeln

1. `approval_decision`: kein Löschen; geändert werden darf nur einmalig `invalidated_at` und `invalidation_reason`.
2. `migrated_journal_line` und `statement_event`: nur Einfügen, Änderung und Löschung werden abgelehnt.
3. `hoa_reserve_movement`: Änderung und Löschung nur, solange die zugehörige Abrechnung im Status `draft` ist (Kaskade beim Löschen eines Entwurfs bleibt möglich).
4. `bank_transaction`: kein Löschen; Betrag, Währung, Buchungs- und Valutadatum, Bankreferenz, End-to-End-Referenz, Mandatsreferenz, Hash und Bankkonto sind nach dem Einfügen fest. Status und Zuordnungen bleiben änderbar.
5. `open_item_settlement` und `audit_log` hatten bereits Insert-only-Trigger.
6. Urheberspalten `created_at`, `updated_at`, `created_by`, `updated_by` auf `hoa_reserve_movement`, `economic_plan_item`, `hoa_cost_item`, `invoice_line`, `role_permission`, `membership_role`. Bestehende Zeilen erhalten den Migrationszeitpunkt, der Urheber bleibt dort leer.
7. `access_grant`: `valid_to >= valid_from`; feste Wertelisten für `scope_type`, `right`, `role`, `legal_basis` (Spiegel in `mhvp.portal.models.GRANT_*`).
8. `license` und `property_notice`: Ende nicht vor Beginn.
9. `economic_plan`, `hoa_statement`, `reserve_statement`: ab Status `resolved` ist `resolution_id` Pflicht.
10. `bank_rule`: Status `active` nur mit `approved_by`, `approved_at`, `max_amount > 0` und `test_evidence_document_id`.

CHECKs werden mit NOT VALID angelegt und nur bei null Verstößen validiert; die Zahl der Verstöße steht im Migrationsprotokoll.

## Nicht umgesetzt

- Überlappungssperre für `access_grant`: mehrere Grundlagen (Vertrag, Vollmacht, Mietverwaltung) erzeugen fachlich zulässig überlappende Zeilen; siehe offene Frage AP05-01.
- `price_list_entry` und `ledger_leading_switch` haben nur `valid_from`, ein Perioden-CHECK entfällt. `ai_knowledge_entry` liegt außerhalb des Pakets.
