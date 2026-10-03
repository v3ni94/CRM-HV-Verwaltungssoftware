# AO07: Ersteller eines Lastschriftlaufs darf nicht selbst freigeben (GAK-106)

| Feld | Inhalt |
| --- | --- |
| ID | AO07 (GAK-106) |
| Titel | Mandantenschalter `direct_debit_creator_may_not_approve` (Standard aus) |
| Geltungsbereich | Lastschriftläufe (Modul `mhvp.accounting.direct_debit`), je Mandant; betrifft G2 (Zahlungsinitiierung), das Gate bleibt geschlossen |
| Quellenstatus | Offene Entscheidung (OPEN_QUESTIONS AN17-01, Eigentümer Betreiber, Gate G2); keine Rechtsnorm aus Anhang C. Technisch vorbereitet mit konservativem Standard aus |
| Abnahmefall | Annex D nicht unmittelbar; Nachweis durch `apps/api/tests/integration/test_ao07_switch_and_constraints.py` |
| Umsetzung | Migration `0458_ao07_direct_debit_creator_approval.py`, Spalte `tenant_settings.direct_debit_creator_may_not_approve` |
| Änderungsgrund | Bei kleinen Teams mit nur zwei Freigebenden ist offen, ob der Ersteller den Lauf zusätzlich zur Prüfung auf dieselbe Person nicht freigeben darf. Eintrag 03.10.2026 (GAM-810) |

## Regeln

- Schalter aus (Standard): bisheriges Verhalten, Freigabe durch eine zweite Person gemäß der bestehenden Prüfung.
- Schalter an: der Ersteller erhält beim Freigeben 403 `MHVP-GATE-0002` (laut OPEN_QUESTIONS AN17-01).
- Die Entscheidung über den Standardwert trifft der Betreiber (AN17-01); bis dahin bleibt der Schalter aus.
