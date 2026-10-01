# Einheitliches Statusmodell der Abrechnungsobjekte (6.9.3, E03, S69-01)

| Field | Content |
| --- | --- |
| ID | S69-01 |
| Title | Statusmodell für Hausgeldabrechnung, Eigentümerabrechnung und Rücklagenabrechnung |
| Scope | `hoa_statement` (unchanged), `owner_statement` (Miete, SEV) and the new `reserve_statement` (Rücklagenabrechnung je GdWE-Buchungskreis und Jahr); per tenant; excluded: operating cost statements (own status table `billing/status.py`, already uniform) |
| Source status | Fachliche Umsetzung of 6.9.3 and E03 (no legal norm claimed). W06 (issue only after the resolution), D13 (posting only with a binding resolution) and D14 (resolution bound to the snapshot) per annex C as already applied to the Hausgeldabrechnung. Four eyes: Produktschutz 6.9.9. Release: not released; G3 (owner statements) and G4 (reserve statements) closed |
| Acceptance case | `apps/api/tests/integration/test_s69_statement_status.py` (owner statement: four eyes, resolved refused, G3 lock, posted only with posted entries, locked final; reserve statement: derived from the Hausgeldabrechnung, opening 1.000,00 and closing 1.000,00, four eyes, issued only after resolved, G4 lock, tenant separation 404, rights 403, validation 422), `apps/api/tests/unit/test_s69_statement_lifecycle.py`; no annex D case yet |
| Implementation | `mhvp.billing.status` (transition table), `mhvp.billing.statement_lifecycle` (four eyes, status log, posted entry check), `mhvp.billing.owner_statement_routers` (`POST /billing/owner-statements/{id}/transition`), `mhvp.hoa.reserve_statement` (`/hoa/reserve-statements`), migration 0295; CRM: status actions in the Eigentümerabrechnung and the panel Rücklagenabrechnung on the page WEG, Rücklagen |
| Change reason | Lückenliste 30.09.2026 S69-01: owner_statement ended at internally_approved, reserve_statement did not exist |

## Rules

1. Transitions follow `check_transition` (6.9.3): draft, calculated, internally_approved,
   optional board_reviewed, resolved (WEG only), issued, due, posted, locked. No step back; a
   change after the approval needs a new statement.
2. Internal approval only by a person other than the creator and the calculating person
   (MHVP-GATE-0002), as for the Hausgeldabrechnung.
3. issued, due and posted check the release gate first: G3 for owner statements (rental
   statements, 18.0), G4 for reserve statements (WEG statements). Deviation from the package
   text "posted and issued behind G4": owner statements are rental statements and follow G3
   like their PDF; see OPEN_QUESTIONS S69-01-01.
4. posted never creates an entry; it records posted journal entries of the statement's ledger
   (references only, B05). A draft entry or an entry of another ledger is refused (409).
5. Reserve statement: content is the reserve block and the positions per earmarked reserve of
   the calculated Hausgeldabrechnung of the same year plus the master data per reserve
   (opening balance, opening year, bank account, migration 0294); nothing is recomputed. The
   internal approval is refused when the Hausgeldabrechnung was recalculated since
   (`source_snapshot_hash`). `resolved` accepts a binding resolution on the reserve statement's
   own snapshot or on the source snapshot of the Hausgeldabrechnung (assumption A-S69-01-01).
6. Every status change is written to `status_log` (from, to, by, at, note).
