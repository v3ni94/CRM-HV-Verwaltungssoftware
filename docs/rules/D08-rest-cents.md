# Restcentverteilung (6.9.8, B06)

| Field | Content |
| --- | --- |
| ID | B06 / D08 |
| Title | Präzision, Centverteilung |
| Scope | all distributions of the operating cost statement (M17) |
| Source status | product standard (6.9.8); no legal rule claimed |
| Acceptance case | D08, `tests/integration/test_m17_operating_costs.py::test_d08_d10_units` |
| Implementation | `mhvp.billing.calc.distribute`: floor to cents, largest remainder, ties by stable key (unit number, occupant key) |
| Change reason | M17, 23.09.2026 |
