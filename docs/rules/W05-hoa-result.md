# Abrechnungsspitze und Rückstände (7.8, W05)

| Field | Content |
| --- | --- |
| ID | W05 |
| Title | Abrechnungsspitze und Rückstände |
| Scope | WEG statement (M24) |
| Source status | R04, P01 (annex C); D01 and D02 binding acceptance cases |
| Acceptance case | D01, D02, D03: `tests/integration/test_m24_hoa.py` |
| Implementation | `mhvp.hoa.calc.statement_results`: result = cost share minus resolved advances; arrears = resolved minus paid, kept with their original claim; total shown as information only; posting books only the result |
| Change reason | M24, 23.09.2026 |
